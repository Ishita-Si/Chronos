"""
Compliance & Quality Intelligence (Module 6).

Maps regulatory/SOP clauses to the actual inspection & maintenance records in
plant memory, flags missing or overdue evidence, and assembles an audit-ready
evidence pack per clause — with citations to the satisfying records.
"""
from __future__ import annotations

import sqlite3

from .. import config
from ..util import days_between
from . import graph

# Which event subtypes satisfy each clause's required evidence_type.
EVIDENCE_SUBTYPES = {
    "vibration_route": {"vibration_route", "vibration_rise"},
    "alignment_check": {"alignment_marginal", "alignment_check", "post_repair"},
    "psv_test": {"psv_test"},
    "integrity_inspection": {"integrity_inspection"},
    "thermography": {"thermography", "fouling_detected"},
}


def _satisfying_events(conn, asset_id: str, evidence_type: str) -> list[dict]:
    subtypes = EVIDENCE_SUBTYPES.get(evidence_type, {evidence_type})
    evs = graph.asset_events(conn, asset_id, etypes=("INSPECTION",))
    return [e for e in evs if e["subtype"] in subtypes]


def evaluate_clause(conn, clause: dict, asset_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or config.AS_OF
    evs = _satisfying_events(conn, asset_id, clause["evidence_type"])
    latest = max(evs, key=lambda e: e["ts"]) if evs else None
    freq = clause.get("frequency_days")

    result = {
        "clause_id": clause["clause_id"],
        "standard": clause["standard"],
        "title": clause["title"],
        "asset_id": asset_id,
        "evidence_type": clause["evidence_type"],
        "frequency_days": freq,
        "evidence_count": len(evs),
        "latest_evidence_ts": latest["ts"] if latest else None,
        "latest_evidence_ref": latest["source_ref"] if latest else None,
    }

    if not evs:
        result["status"] = "missing"
        result["detail"] = "No evidence on record."
        result["days_overdue"] = None
        return result

    if freq:
        age = days_between(latest["ts"], as_of)
        result["days_since_last"] = round(age, 0)
        if age <= freq * 0.8:
            result["status"] = "compliant"
        elif age <= freq:
            result["status"] = "due_soon"
        else:
            result["status"] = "non_compliant"
            result["days_overdue"] = round(age - freq, 0)
        result.setdefault("days_overdue", 0 if result["status"] != "non_compliant" else result.get("days_overdue"))
        result["detail"] = (f"Last {clause['evidence_type']} was {int(age)} days ago "
                            f"(required every {freq} days).")
    else:
        # event-triggered clause (e.g. alignment after every seal replacement)
        result["status"] = "compliant"
        result["detail"] = "Required evidence present on record."
        result["days_overdue"] = None
    return result


def report(conn, asset_id: str | None = None, standard: str | None = None,
           as_of: str | None = None) -> dict:
    as_of = as_of or config.AS_OF
    clauses = graph.db.query(conn, "SELECT * FROM clauses")
    if standard:
        clauses = [c for c in clauses if c["standard"] == standard]

    rows: list[dict] = []
    for clause in clauses:
        assets = graph.applicable_clauses  # noqa  (kept for readability)
        targets = graph.db.query(conn,
            "SELECT dst_id FROM edges WHERE rel='CLAUSE_APPLIES_TO_ASSET' AND src_id=?",
            (clause["clause_id"],))
        for t in targets:
            aid = t["dst_id"]
            if asset_id and aid != asset_id:
                continue
            rows.append(evaluate_clause(conn, clause, aid, as_of))

    gaps = [r for r in rows if r["status"] in ("missing", "non_compliant")]
    summary = {
        "total_checks": len(rows),
        "compliant": sum(1 for r in rows if r["status"] == "compliant"),
        "due_soon": sum(1 for r in rows if r["status"] == "due_soon"),
        "non_compliant": sum(1 for r in rows if r["status"] == "non_compliant"),
        "missing": sum(1 for r in rows if r["status"] == "missing"),
    }
    summary["compliance_rate"] = (round(summary["compliant"] / len(rows), 2)
                                  if rows else 1.0)
    return {"as_of": as_of, "summary": summary, "results": rows, "gaps": gaps}


def evidence_pack(conn, clause_id: str, asset_id: str,
                  as_of: str | None = None) -> dict:
    """Audit-ready evidence package for one clause/asset (Flow C)."""
    clause = graph.db.one(conn, "SELECT * FROM clauses WHERE clause_id=?", (clause_id,))
    if not clause:
        return {"error": f"Unknown clause {clause_id}"}
    asset = graph.get_asset(conn, asset_id)
    evs = _satisfying_events(conn, asset_id, clause["evidence_type"])
    evs.sort(key=lambda e: e["ts"], reverse=True)
    status = evaluate_clause(conn, clause, asset_id, as_of)
    return {
        "clause": clause,
        "asset": asset,
        "status": status,
        "evidence_records": [{
            "ts": e["ts"], "subtype": e["subtype"], "status": e["status"],
            "note": e.get("text"), "source_ref": e["source_ref"],
            "performed_by": e.get("person_id"),
        } for e in evs],
        "generated_as_of": as_of or config.AS_OF,
    }
