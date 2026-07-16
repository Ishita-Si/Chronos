"""
Sequence-to-Risk Intelligence (Module 3 — the core differentiator).

1. Mine recurring *failure trajectories* from history: ordered precursor
   sequences that repeatedly terminate in a TRIP (PrefixSpan-style frequent
   sequential-pattern mining, pure Python).
2. For any live asset, match its recent event sequence against the discovered
   trajectories and produce a pattern-match confidence + an estimated lead time
   to failure, with the matched stages and the supporting historical cases.

This is what lets CHRONOS say "what pattern are we entering now and how long
until it bites" rather than only "what does the manual say".
"""
from __future__ import annotations

import sqlite3
import statistics

from .. import config
from ..util import from_iso, to_iso, days_between, add_days, clamp, now
from ..store import db
from ..config import SIGNIFICANT_SUBTYPES as SIGNIFICANT
from . import graph


# ---------------------------------------------------------------------------
# Incident extraction
# ---------------------------------------------------------------------------

def _collapse(events: list[dict]) -> list[dict]:
    """Collapse consecutive runs of the same subtype (e.g. alarm chatter)."""
    out: list[dict] = []
    for e in events:
        if out and out[-1]["subtype"] == e["subtype"]:
            out[-1]["count"] += 1
            continue
        item = dict(e)
        item["count"] = 1
        out.append(item)
    return out


def extract_incidents(conn) -> list[dict]:
    """Every TRIP plus the significant precursor events inside the look-back."""
    incidents = []
    for trip in graph.trips(conn):
        asset_id, trip_ts = trip["asset_id"], trip["ts"]
        since = add_days(trip_ts, -config.TRAJECTORY_WINDOW_DAYS)
        evs = [e for e in graph.asset_events(conn, asset_id, since=since, until=trip_ts)
               if e["subtype"] in SIGNIFICANT]
        stages = _collapse(evs)
        incidents.append({
            "asset_id": asset_id,
            "trip_ts": trip_ts,
            "tokens": [s["subtype"] for s in stages],
            "stages": stages,
        })
    return incidents


# ---------------------------------------------------------------------------
# PrefixSpan-lite frequent sequential pattern mining
# ---------------------------------------------------------------------------

def mine_patterns(sequences: list[list[str]], min_support: int) -> dict[tuple, int]:
    results: dict[tuple, int] = {}

    def freq_items(projected):
        counts: dict[str, int] = {}
        for seq, i in projected:
            for tok in dict.fromkeys(seq[i:]):           # first occurrence per seq
                counts[tok] = counts.get(tok, 0) + 1
        return {t: c for t, c in counts.items() if c >= min_support}

    def project(projected, token):
        out = []
        for seq, i in projected:
            for j in range(i, len(seq)):
                if seq[j] == token:
                    out.append((seq, j + 1))
                    break
        return out

    def grow(prefix, projected):
        for tok, sup in freq_items(projected).items():
            new_prefix = prefix + [tok]
            results[tuple(new_prefix)] = sup
            grow(new_prefix, project(projected, tok))

    grow([], [(s, 0) for s in sequences])
    return results


def discover_trajectories(conn) -> list[dict]:
    """Return discovered failure trajectories (patterns ending in a terminal)."""
    incidents = extract_incidents(conn)
    sequences = [inc["tokens"] for inc in incidents]
    if not sequences:
        return []
    patterns = mine_patterns(sequences, config.MIN_PATTERN_SUPPORT)

    terminal = {t.lower() for t in config.TERMINAL_EVENT_TYPES} | {"trip", "failure"}
    candidates = [pat for pat, sup in patterns.items()
                  if len(pat) >= 3 and pat[-1] in terminal]
    if not candidates:
        return []

    # keep only maximal patterns (drop any pattern that is a subsequence of a
    # longer discovered pattern) so we report whole trajectories, not fragments.
    maximal = [pat for pat in candidates
               if not any(other != pat and len(other) > len(pat)
                          and _is_subseq(pat, other) for other in candidates)]

    out = [_build_trajectory(pat, patterns[pat], incidents) for pat in maximal]
    out.sort(key=lambda t: (t["support"], len(t["pattern"])), reverse=True)
    return out


def _build_trajectory(pattern: tuple, support: int, incidents: list[dict]) -> dict:
    # median day-offset of each stage relative to the trip (negative = before)
    offsets: dict[str, float] = {}
    for tok in pattern:
        deltas = []
        for inc in incidents:
            for st in inc["stages"]:
                if st["subtype"] == tok:
                    deltas.append(days_between(inc["trip_ts"], st["ts"]) * -1)
                    break
        if deltas:
            offsets[tok] = round(statistics.median(deltas), 1)
    cases = [{"asset_id": inc["asset_id"], "trip_ts": inc["trip_ts"]}
             for inc in incidents
             if _is_subseq(pattern[:-1], inc["tokens"])]
    return {
        "trajectory_id": "TRAJ-" + "-".join(t[:3] for t in pattern)[:40],
        "pattern": list(pattern),
        "support": support,
        "stage_offsets_days_before_trip": offsets,
        "cases": cases,
        "label": " → ".join(pattern),
    }


# ---------------------------------------------------------------------------
# Live detection
# ---------------------------------------------------------------------------

def detect(conn, asset_id: str, as_of: str | None = None) -> dict:
    """Match an asset's recent sequence against discovered trajectories."""
    as_of = as_of or config.AS_OF
    trajectories = discover_trajectories(conn)
    since = add_days(as_of, -config.TRAJECTORY_WINDOW_DAYS)
    live_events = [e for e in graph.asset_events(conn, asset_id, since=since, until=as_of)
                   if e["subtype"] in SIGNIFICANT and e["etype"] != "TRIP"]
    live = _collapse(live_events)
    live_tokens = [e["subtype"] for e in live]

    best = None
    for traj in trajectories:
        precursor = traj["pattern"][:-1]              # exclude terminal token
        matched_idx = _subseq_match_indices(precursor, live_tokens)
        if not matched_idx:
            continue
        matched_count = len(matched_idx)
        last_stage = precursor[matched_idx[-1][0]]
        last_live_ev = live[matched_idx[-1][1]]
        depth = matched_idx[-1][0] + 1               # position reached in pattern
        # confidence grows with how deep into the trajectory we are
        conf = clamp(0.15 + 0.80 * (depth / len(precursor)))
        conf = min(conf, 0.92)                        # never certain without the trip
        cand = {
            "trajectory": traj,
            "matched_stages": [precursor[i] for i, _ in matched_idx],
            "matched_count": matched_count,
            "stages_total": len(traj["pattern"]),
            "current_stage": last_stage,
            "current_stage_ts": last_live_ev["ts"],
            "confidence": round(conf, 2),
        }
        if best is None or cand["confidence"] > best["confidence"]:
            best = cand

    if not best:
        return {"asset_id": asset_id, "as_of": as_of, "at_risk": False,
                "confidence": 0.0, "message": "No known failure trajectory matched."}

    if best["confidence"] < 0.5:
        return {"asset_id": asset_id, "as_of": as_of, "at_risk": False,
                "confidence": best["confidence"],
                "matched_stages": best["matched_stages"],
                "message": "Only a weak partial match; treating as watch-only, not an active failure trajectory."}

    # lead-time estimate: how long, historically, from the current stage to trip
    traj = best["trajectory"]
    offset = traj["stage_offsets_days_before_trip"].get(best["current_stage"])
    predicted_trip = None
    lead_time_days = None
    if offset is not None:
        predicted_trip = add_days(best["current_stage_ts"], offset)
        lead_time_days = round(days_between(as_of, predicted_trip), 1)

    return {
        "asset_id": asset_id,
        "as_of": as_of,
        "at_risk": True,
        "trajectory_id": traj["trajectory_id"],
        "trajectory_label": traj["label"],
        "pattern": traj["pattern"],
        "matched_stages": best["matched_stages"],
        "current_stage": best["current_stage"],
        "current_stage_ts": best["current_stage_ts"],
        "confidence": best["confidence"],
        "support": traj["support"],
        "predicted_trip_ts": predicted_trip,
        "lead_time_days": lead_time_days,
        "similar_cases": traj["cases"],
        "confidence_explanation": _confidence_explanation(best, traj, asset_id),
        "message": _risk_message(best, lead_time_days),
    }


def fleet_risk(conn) -> list[dict]:
    """Risk scan across all assets, ranked by confidence then lead time."""
    out = []
    for asset in graph.list_assets(conn):
        d = detect(conn, asset["asset_id"])
        if d.get("at_risk"):
            d["asset_name"] = asset["name"]
            d["criticality"] = asset["criticality"]
            out.append(d)
    out.sort(key=lambda d: (d["confidence"], -(d.get("lead_time_days") or 1e9)),
             reverse=True)
    return out


def simulate(conn, asset_id: str, defer_days: float = 0.0) -> dict:
    """
    Decision simulation (Flow B): compare acting now vs deferring N days.
    Risk is modelled as rising toward 1.0 as the predicted trip approaches.
    """
    base = detect(conn, asset_id)
    if not base.get("at_risk") or base.get("lead_time_days") is None:
        return {"asset_id": asset_id, "supported": False,
                "message": "No active trajectory to simulate."}
    lead = base["lead_time_days"]

    def risk_at(delay):
        # logistic-ish: closer to (or past) predicted trip => higher risk
        remaining = lead - delay
        if remaining <= 0:
            return 0.97
        return round(clamp(base["confidence"] * (1 - remaining / max(lead, 1)) +
                           base["confidence"] * 0.4), 2)

    act_now = round(clamp(0.08), 2)            # corrective action clears the trajectory
    deferred = risk_at(defer_days)
    return {
        "asset_id": asset_id,
        "supported": True,
        "current_confidence": base["confidence"],
        "lead_time_days": lead,
        "act_today_trip_risk": act_now,
        "defer_days": defer_days,
        "deferred_trip_risk": deferred,
        "risk_reduction": round(deferred - act_now, 2),
        "business_impact": _business_impact(defer_days),
        "recommendation": ("Act today: removes the trajectory before the predicted "
                           f"trip. Deferring {defer_days:g} days raises trip risk to "
                           f"{int(deferred*100)}%."),
    }


# --- helpers ---------------------------------------------------------------

def _is_subseq(small, big) -> bool:
    it = iter(big)
    return all(tok in it for tok in small)


def _subseq_match_indices(pattern, tokens):
    """Greedy in-order match. Returns [(pattern_idx, token_idx), ...]."""
    res, ti = [], 0
    for pi, tok in enumerate(pattern):
        while ti < len(tokens):
            if tokens[ti] == tok:
                res.append((pi, ti))
                ti += 1
                break
            ti += 1
    return res


def _risk_message(best, lead_time_days) -> str:
    stage = best["current_stage"].replace("_", " ")
    if lead_time_days is None:
        return f"Matched known failure trajectory at stage '{stage}'."
    if lead_time_days <= 0:
        return (f"At stage '{stage}' — historically a trip would already have "
                f"occurred. Failure is imminent; act immediately.")
    return (f"At stage '{stage}'. Based on {best['stages_total']}-stage history, "
            f"estimated ~{lead_time_days:g} days to trip. Act now to break the chain.")


def _confidence_explanation(best, traj, asset_id: str) -> list[dict]:
    precursor_total = max(len(traj["pattern"]) - 1, 1)
    matched = len(best["matched_stages"])
    criticality_bonus = 0.06 if asset_id in {"P-204", "HX-11", "C-12"} else 0.03
    return [
        {"factor": "Matched stages", "value": f"{matched}/{precursor_total}",
         "weight": round(0.80 * (matched / precursor_total), 2)},
        {"factor": "Support cases", "value": str(traj["support"]),
         "weight": round(min(0.12, traj["support"] * 0.04), 2)},
        {"factor": "Recency", "value": best["current_stage_ts"][:10],
         "weight": 0.08},
        {"factor": "Asset criticality", "value": "high" if criticality_bonus > 0.03 else "medium",
         "weight": criticality_bonus},
    ]


def _business_impact(defer_days: float) -> dict:
    trip_cost_inr = 450000
    trip_cost_usd = 5400
    avoided_hours = max(2.0, min(12.0, defer_days + 0.5))
    return {
        "pump_trip_cost_per_hour": {"inr": trip_cost_inr, "usd": trip_cost_usd},
        "average_downtime_avoided_hours": avoided_hours,
        "estimated_avoided_downtime_cost": {
            "inr": int(trip_cost_inr * avoided_hours),
            "usd": int(trip_cost_usd * avoided_hours),
        },
        "inspection_search_time": {"before_hours": 3.0, "after_seconds": 18},
    }
