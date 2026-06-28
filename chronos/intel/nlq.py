"""
Natural-language query planner (the "deeper AI" layer).

Turns a free-text question into a structured plan — intent + entity-type +
parameter + status filters — then executes it across the right agents (graph,
sequence-risk, compliance, retrieval) and synthesizes a cited, confidence-scored
answer. This lets CHRONOS handle *analytical, cross-functional* questions
("which pumps are overdue for vibration checks and at risk?") rather than only
single-asset lookups.

Rule-based and fully offline — no LLM/API dependency — but structured exactly
like an agentic planner so an LLM planner is a drop-in upgrade.
"""
from __future__ import annotations

import re
import sqlite3

from ..util import clamp
from ..ingest import extract
from . import graph, sequence, compliance

# free-text -> canonical asset type
_TYPE_WORDS = {
    "pump": "pump", "pumps": "pump",
    "exchanger": "heat_exchanger", "exchangers": "heat_exchanger",
    "heat exchanger": "heat_exchanger",
    "compressor": "compressor", "compressors": "compressor",
    "vessel": "vessel", "vessels": "vessel", "drum": "vessel",
}
_RISK_WORDS = ("at risk", "risk", "fail", "failing", "trip", "breakdown",
               "most likely", "going to", "about to", "downtime")
_COMP_WORDS = ("overdue", "compliance", "compliant", "inspection", "inspections",
               "evidence", "gap", "gaps", "audit", "due", "missing", "certif")
_PROC_WORDS = ("sop", "procedure", "how do i", "how to", "what does", "limit",
               "tolerance", "should i", "manual", "spec")
_LIST_WORDS = ("list", "which", "show all", "how many", "what assets", "all ")


def _detect_type(q: str) -> str | None:
    for word, canonical in _TYPE_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", q):
            return canonical
    return None


def classify(question: str) -> dict:
    q = question.lower()
    tags = extract.extract_tags(question)
    asset_type = _detect_type(q)
    params = extract.extract_params(question)
    has_risk = any(w in q for w in _RISK_WORDS)
    has_comp = any(w in q for w in _COMP_WORDS)
    has_proc = any(w in q for w in _PROC_WORDS)
    is_list = any(w in q for w in _LIST_WORDS)

    if has_risk and has_comp:
        intent = "risk_and_compliance"
    elif has_comp:
        intent = "compliance"
    elif has_risk:
        intent = "risk"
    elif has_proc and not tags:
        intent = "procedure"
    elif is_list and asset_type:
        intent = "enumerate"
    else:
        intent = "asset" if tags else "fallback"

    return {"intent": intent, "tags": tags, "asset_type": asset_type,
            "params": params}


def try_analytical(conn, store, question: str) -> dict | None:
    """Handle analytical/cross-asset questions. Returns None to defer to the
    single-asset copilot path."""
    plan = classify(question)
    intent = plan["intent"]
    if intent in ("asset", "fallback"):
        return None
    handler = {
        "risk": _h_risk,
        "compliance": _h_compliance,
        "risk_and_compliance": _h_risk_and_compliance,
        "enumerate": _h_enumerate,
        "procedure": _h_procedure,
    }.get(intent)
    if not handler:
        return None
    return handler(conn, store, question, plan)


# --- handlers ---------------------------------------------------------------

def _type_label(t: str | None) -> str:
    return {"pump": "pumps", "heat_exchanger": "heat exchangers",
            "compressor": "compressors", "vessel": "vessels"}.get(t, "assets")


def _wrap(question, summary, sections, table, citations, confidence, intent,
          actions=None):
    return {"question": question, "asset_id": None, "asset_name": None,
            "summary": summary, "sections": sections or [], "table": table,
            "recommended_actions": actions or [], "risk": None,
            "citations": citations or [], "confidence": round(confidence, 2),
            "intent": intent}


def _h_risk(conn, store, question, plan):
    fleet = sequence.fleet_risk(conn)
    if plan["asset_type"]:
        keep = {a["asset_id"] for a in graph.list_assets(conn)
                if a["type"] == plan["asset_type"]}
        fleet = [r for r in fleet if r["asset_id"] in keep]
    label = _type_label(plan["asset_type"])
    if not fleet:
        return _wrap(question, f"No {label} are currently matching a known failure "
                     "trajectory — the fleet looks healthy.", [], None, [], 0.6, "risk")
    rows = [[r["asset_id"], r.get("asset_name", ""), f"{int(r['confidence']*100)}%",
             r["current_stage"].replace("_", " "),
             ("imminent" if (r.get("lead_time_days") or 0) <= 0
              else f"~{round(r['lead_time_days'])}d")] for r in fleet]
    cites = [{"ref": r.get("trajectory_label", ""), "kind": "trajectory",
              "snippet": r.get("message", ""), "score": r["confidence"]} for r in fleet]
    top = fleet[0]
    one = len(fleet) == 1
    noun = label[:-1] if one and label.endswith("s") else label
    summary = (f"{len(fleet)} {noun} {'is' if one else 'are'} trending "
               f"toward failure. Highest risk: {top['asset_id']} "
               f"({int(top['confidence']*100)}%, {top['current_stage'].replace('_',' ')}).")
    return _wrap(question, summary, [], {
        "columns": ["Asset", "Name", "Risk", "Stage", "Time to trip"], "rows": rows},
        cites, 0.9, "risk")


def _h_compliance(conn, store, question, plan):
    rep = compliance.report(conn)
    gaps = rep["gaps"]
    if plan["asset_type"]:
        keep = {a["asset_id"] for a in graph.list_assets(conn)
                if a["type"] == plan["asset_type"]}
        gaps = [g for g in gaps if g["asset_id"] in keep]
    if plan["params"]:
        gaps = [g for g in gaps
                if any(p in g["evidence_type"] for p in plan["params"])]
    label = _type_label(plan["asset_type"])
    if not gaps:
        return _wrap(question, f"No open compliance gaps found for {label}.",
                     [], None, [], 0.7, "compliance")
    rows = [[g["asset_id"], g["clause_id"], g["standard"],
             g["status"].replace("_", " "), g.get("detail", "")] for g in gaps]
    cites = [{"ref": g["clause_id"] + " · " + g["standard"], "kind": "clause",
              "snippet": g.get("detail", ""), "score": 1.0} for g in gaps]
    summary = (f"{len(gaps)} compliance gap(s) found for {label}: "
               + ", ".join(f"{g['asset_id']} ({g['clause_id']})" for g in gaps[:4])
               + ("…" if len(gaps) > 4 else "") + ".")
    return _wrap(question, summary, [], {
        "columns": ["Asset", "Clause", "Standard", "Status", "Detail"], "rows": rows},
        cites, 0.88, "compliance",
        actions=["Schedule the missing inspections/tests above.",
                 "Generate an evidence pack per clause from the Compliance tab."])


def _h_risk_and_compliance(conn, store, question, plan):
    fleet = {r["asset_id"]: r for r in sequence.fleet_risk(conn)}
    rep = compliance.report(conn)
    gaps_by_asset = {}
    for g in rep["gaps"]:
        gaps_by_asset.setdefault(g["asset_id"], []).append(g)
    both = sorted(set(fleet) & set(gaps_by_asset))
    if plan["asset_type"]:
        keep = {a["asset_id"] for a in graph.list_assets(conn)
                if a["type"] == plan["asset_type"]}
        both = [a for a in both if a in keep]
    label = _type_label(plan["asset_type"])
    if not both:
        risk_list = ", ".join(sorted(fleet)) or "none"
        gap_list = ", ".join(sorted(gaps_by_asset)) or "none"
        sections = [
            {"heading": "At risk of failure", "body": risk_list},
            {"heading": "Open compliance gaps", "body": gap_list},
        ]
        return _wrap(question,
                     f"No single {label[:-1] if label.endswith('s') else label} is "
                     "both at-risk and non-compliant right now — the at-risk assets "
                     "are still being actively monitored. Cross-functional picture below.",
                     sections, None, [], 0.72, "risk_and_compliance")
    rows = [[a, f"{int(fleet[a]['confidence']*100)}%",
             ", ".join(g["clause_id"] for g in gaps_by_asset[a])] for a in both]
    cites = [{"ref": fleet[a].get("trajectory_label", a), "kind": "combined",
              "snippet": fleet[a].get("message", ""), "score": fleet[a]["confidence"]}
             for a in both]
    summary = (f"{len(both)} {label} {'is' if len(both)==1 else 'are'} the top "
               f"priority — failing trajectory AND missing compliance evidence: "
               + ", ".join(both) + ".")
    return _wrap(question, summary, [], {
        "columns": ["Asset", "Failure risk", "Open clauses"], "rows": rows},
        cites, 0.92, "risk_and_compliance",
        actions=["Treat these as P1: they carry both failure and audit exposure.",
                 "Act on the failure trajectory first, then close the evidence gap."])


def _h_enumerate(conn, store, question, plan):
    assets = [a for a in graph.list_assets(conn)
              if not plan["asset_type"] or a["type"] == plan["asset_type"]]
    label = _type_label(plan["asset_type"])
    rows = [[a["asset_id"], a["name"], a["criticality"], a["area"]] for a in assets]
    summary = f"{len(assets)} {label} on record."
    return _wrap(question, summary, [], {
        "columns": ["Asset", "Name", "Criticality", "Area"], "rows": rows}, [],
        0.85, "enumerate")


def _h_procedure(conn, store, question, plan):
    hits = store.search(question, k=5)
    if not hits:
        return _wrap(question, "No matching procedure or document found.", [],
                     None, [], 0.2, "procedure")
    body = "\n".join(f"- {h['text'][:220].strip()}  [{h['source_ref']}]"
                     for h in hits[:3])
    cites = [{"ref": h["source_ref"], "kind": h["kind"], "score": h["score"],
              "snippet": h["text"][:240]} for h in hits]
    top = hits[0]
    summary = f"Per {top['source_ref']}: {top['text'][:180].strip()}"
    conf = clamp(0.5 * clamp(top["score"] / 0.4) + 0.3)
    return _wrap(question, summary,
                 [{"heading": "What the procedures say", "body": body}],
                 None, cites, conf, "procedure")
