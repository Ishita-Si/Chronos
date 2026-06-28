"""
Memory Copilot (Module 4 — Decision Replay & Action Guidance).

Hybrid retrieval: semantic search over the passage corpus + temporal-graph
context (asset timeline, governing SOPs, similar past cases, live trajectory
risk). Produces a source-backed answer with an explicit confidence score and
citations for every claim — the trust contract the spec requires.
"""
from __future__ import annotations

import sqlite3

from ..util import clamp
from ..ingest import extract
from . import graph, sequence, rca, vectorstore


def answer(conn, store: "vectorstore.VectorStore", question: str,
           asset_id: str | None = None) -> dict:
    tags = extract.extract_tags(question)
    asset_id = asset_id or (tags[0] if tags else None)
    asset = graph.get_asset(conn, asset_id) if asset_id else None

    hits = store.search(question, k=6, asset_id=asset_id)
    citations = [{
        "ref": h["source_ref"], "kind": h["kind"], "score": h["score"],
        "snippet": h["text"][:240], "asset_id": h.get("asset_id"),
        "link": _link(h),
    } for h in hits]

    sections: list[dict] = []
    recommended: list[str] = []
    risk = None
    root = None

    if asset:
        risk = sequence.detect(conn, asset_id)
        root = rca.likely_root_cause(conn, asset_id)

        # Decision-replay block: "when did we see this before / what was done"
        cases = (risk.get("similar_cases") or []) if risk.get("at_risk") else []
        if cases:
            sections.append({
                "heading": "When did we see this before?",
                "body": _format_cases(conn, cases),
            })
        if root:
            sections.append({
                "heading": "Most likely root cause",
                "body": (f"{root['cause'].capitalize()} "
                         f"(seen in {root['occurrences']} comparable case(s), "
                         f"confidence {int(root['confidence']*100)}%)."),
            })
        if risk.get("at_risk"):
            sections.append({
                "heading": "Pattern we are entering now",
                "body": risk["message"] + f"  Trajectory: {risk['trajectory_label']}.",
            })
        recommended = rca._recommended_actions(conn, asset_id, root)

    # Knowledge block from the retrieved documents (always grounded)
    if hits:
        sections.append({
            "heading": "What the records and procedures say",
            "body": _format_evidence(hits),
        })

    confidence = _confidence(hits, asset is not None, bool(root))
    summary = _summary(question, asset, risk, root)

    return {
        "question": question,
        "asset_id": asset_id,
        "asset_name": asset["name"] if asset else None,
        "summary": summary,
        "sections": sections,
        "recommended_actions": recommended,
        "risk": risk if (risk and risk.get("at_risk")) else None,
        "citations": citations,
        "confidence": confidence,
    }


def _summary(question, asset, risk, root) -> str:
    if asset and risk and risk.get("at_risk"):
        rc = f" Likely root cause: {root['cause']}." if root else ""
        lead = risk.get("lead_time_days")
        lead_txt = (f" Estimated ~{lead:g} days to trip." if lead and lead > 0
                    else " Failure is imminent." if lead is not None else "")
        return (f"{asset['asset_id']} matches a known failure trajectory "
                f"({int(risk['confidence']*100)}% confidence).{lead_txt}{rc} "
                f"Recommended actions below, with citations.")
    if asset:
        return (f"Here is what plant memory holds for {asset['asset_id']} "
                f"({asset['name']}), with sources.")
    return "Answer assembled from plant memory with citations below."


def _format_cases(conn, cases) -> str:
    lines = []
    for c in cases:
        a = graph.get_asset(conn, c["asset_id"])
        name = a["name"] if a else c["asset_id"]
        lines.append(f"- {c['asset_id']} ({name}) tripped on "
                     f"{c['trip_ts'][:10]} via the same precursor sequence.")
    return "\n".join(lines)


def _format_evidence(hits) -> str:
    lines = []
    for h in hits[:4]:
        lines.append(f"- {h['text'][:200].strip()}  [{h['source_ref']}]")
    return "\n".join(lines)


def _link(h: dict) -> str | None:
    if h.get("doc_id"):
        return f"/api/document/{h['doc_id']}"
    if h.get("event_id"):
        return f"/api/event/{h['event_id']}"
    return None


def _confidence(hits, has_asset: bool, has_root: bool) -> float:
    if not hits:
        return 0.1
    top = clamp(hits[0]["score"] / 0.4)          # TF-IDF scores are modest
    evidence = clamp(len(hits) / 4.0)
    context = 1.0 if has_asset else 0.45
    root_bonus = 0.1 if has_root else 0.0
    return round(clamp(0.5 * top + 0.22 * evidence + 0.18 * context + root_bonus), 2)
