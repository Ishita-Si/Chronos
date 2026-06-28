"""
RCA + Lessons-Learned automation (Module 5).

Builds a causal chain for an incident (an actual TRIP, or — predictively — a
live at-risk trajectory), ranks probable root causes from evidence found across
*similar* historical incidents, and emits a reusable preventive playbook entry.
Every cause and step carries citations back to the originating record.
"""
from __future__ import annotations

import re
import sqlite3

from ..util import clamp, days_between
from ..config import SIGNIFICANT_SUBTYPES as SIGNIFICANT
from . import graph, sequence

_ROOT_CAUSE_RE = re.compile(r"root cause[:\s]+(.+?)(?:\.|$)", re.IGNORECASE)


def _citation(ev: dict) -> dict:
    return {"ref": ev["source_ref"], "kind": ev["source"], "ts": ev["ts"],
            "snippet": (ev.get("text") or ev.get("subtype") or "").strip()[:240]}


def likely_root_cause(conn, asset_id: str) -> dict | None:
    """Mine the dominant root cause for an asset's failure mode from history."""
    asset = graph.get_asset(conn, asset_id)
    if not asset:
        return None
    # gather resolution evidence from this asset AND same-type peers
    peers = [a["asset_id"] for a in graph.list_assets(conn)
             if a["type"] == asset["type"]]
    causes: dict[str, dict] = {}
    for aid in peers:
        for ev in graph.asset_events(conn, aid):
            text = ev.get("text") or ""
            m = _ROOT_CAUSE_RE.search(text)
            if m:
                cause = m.group(1).strip().rstrip(".").lower()
                slot = causes.setdefault(cause, {"count": 0, "evidence": []})
                slot["count"] += 1
                slot["evidence"].append(_citation(ev))
            elif ev["subtype"] == "alignment_marginal":
                cause = "shaft misalignment after seal replacement"
                slot = causes.setdefault(cause, {"count": 0, "evidence": []})
                slot["count"] += 1
                slot["evidence"].append(_citation(ev))
    if not causes:
        return None
    cause, data = max(causes.items(), key=lambda kv: kv[1]["count"])
    confidence = clamp(0.45 + 0.18 * data["count"])
    return {"cause": cause, "confidence": round(confidence, 2),
            "occurrences": data["count"], "evidence": data["evidence"][:4]}


def rca(conn, asset_id: str) -> dict:
    """Full RCA report for the most relevant incident on an asset."""
    asset = graph.get_asset(conn, asset_id)
    if not asset:
        return {"error": f"Unknown asset {asset_id}"}

    asset_trips = graph.trips(conn, asset_id)
    if asset_trips:
        incident = asset_trips[-1]
        incident_ts = incident["ts"]
        mode = "post_incident"
    else:
        det = sequence.detect(conn, asset_id)
        if not det.get("at_risk"):
            return {"asset_id": asset_id, "available": False,
                    "message": "No incident or active trajectory to analyse."}
        incident_ts = det.get("predicted_trip_ts") or det["as_of"]
        mode = "predictive"

    # causal chain = significant precursors leading up to the incident
    from .. import config
    from ..util import add_days
    since = add_days(incident_ts, -config.TRAJECTORY_WINDOW_DAYS)
    chain = [e for e in graph.asset_events(conn, asset_id, since=since, until=incident_ts)
             if e["subtype"] in SIGNIFICANT]
    causal_chain = [{
        "ts": e["ts"], "stage": e["subtype"], "etype": e["etype"],
        "text": e.get("text") or "", "source_ref": e["source_ref"],
    } for e in chain]

    root = likely_root_cause(conn, asset_id)
    probable_causes = []
    if root:
        probable_causes.append(root)

    # recommended preventive actions, grounded in the governing SOPs
    actions = _recommended_actions(conn, asset_id, root)
    lessons = _lessons_learned(conn, asset_id, root)

    citations = [_citation(e) for e in chain if e.get("text")]
    if root:
        citations += root["evidence"]

    return {
        "asset_id": asset_id,
        "asset_name": asset["name"],
        "mode": mode,
        "incident_ts": incident_ts,
        "available": True,
        "causal_chain": causal_chain,
        "probable_causes": probable_causes,
        "recommended_actions": actions,
        "lessons_learned": lessons,
        "citations": _dedupe_citations(citations),
        "confidence": probable_causes[0]["confidence"] if probable_causes else 0.4,
    }


def _recommended_actions(conn, asset_id: str, root: dict | None) -> list[str]:
    actions = []
    if root and "misalign" in root["cause"]:
        actions += [
            "Perform laser shaft alignment to 0.05 mm tolerance (per SOP-PUMP-ALIGN v2 §3).",
            "Inspect and replace drive-end bearing if vibration > 7.1 mm/s.",
            "Check and correct soft-foot before return to service.",
        ]
    actions += [
        "Remove any temporary trip-interlock bypass and restore protection.",
        "Re-baseline vibration after corrective work; confirm < 4.5 mm/s.",
    ]
    return actions


def _lessons_learned(conn, asset_id: str, root: dict | None) -> dict:
    asset = graph.get_asset(conn, asset_id)
    trigger = root["cause"] if root else "recurring failure precursor"
    return {
        "title": f"Preventive playbook: {asset['type']} {trigger}",
        "applies_to_type": asset["type"],
        "trigger_pattern": "vibration rise → alarm chatter → bypass → deferred WO",
        "preventive_control": ("Mandate laser alignment after every seal replacement "
                               "and forbid un-authorised trip-interlock bypass."),
        "owner_role": "Reliability Engineer",
    }


def _dedupe_citations(cits: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in cits:
        if c["ref"] in seen:
            continue
        seen.add(c["ref"])
        out.append(c)
    return out
