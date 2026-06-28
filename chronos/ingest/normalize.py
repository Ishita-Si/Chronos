"""
Normalization: map heterogeneous source records onto the common Event schema,
populate the temporal knowledge graph, build the retrieval passage index, and
record lineage + cross-system auto-links.

This is Module 1 (Unified Ingestion & Auto-Linking) + Module 2 (Plant Memory
Graph) of the UPME spec.
"""
from __future__ import annotations

import sqlite3

from ..util import short_id, to_iso, now
from ..store import db
from . import connectors, extract, pid

# Subtypes that make up failure trajectories (drives Module 3); see config.
from ..config import SIGNIFICANT_SUBTYPES as SIGNIFICANT


def ingest_all(conn: sqlite3.Connection) -> dict:
    counts = {"assets": 0, "persons": 0, "events": 0, "passages": 0,
              "documents": 0, "clauses": 0, "edges": 0,
              "pid_tags": 0, "connections": 0, "discovered_assets": 0}
    _ingest_assets(conn, counts)
    _ingest_persons(conn, counts)
    _ingest_documents(conn, counts)
    _ingest_clauses(conn, counts)
    _ingest_scada(conn, counts)
    _ingest_alarms(conn, counts)
    _ingest_workorders(conn, counts)
    _ingest_inspections(conn, counts)
    _ingest_pids(conn, counts)
    conn.commit()
    counts["edges"] = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    return counts


# --- nodes -----------------------------------------------------------------

def _ingest_assets(conn, counts):
    for a in connectors.read_assets():
        conn.execute("INSERT OR REPLACE INTO assets VALUES (?,?,?,?,?,?)",
                     (a["asset_id"], a["name"], a["type"], a["area"],
                      a["criticality"], a["install_date"]))
        counts["assets"] += 1


def _ingest_persons(conn, counts):
    for p in connectors.read_persons():
        conn.execute("INSERT OR REPLACE INTO persons VALUES (?,?,?)",
                     (p["person_id"], p["name"], p["role"]))
        counts["persons"] += 1


def _ingest_documents(conn, counts):
    asset_types = {a["asset_id"]: a["type"] for a in connectors.read_assets()}
    for d in connectors.read_documents():
        conn.execute(
            "INSERT OR REPLACE INTO documents "
            "(doc_id,title,type,path,version,valid_from,valid_to,supersedes,text) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (d["doc_id"], d["title"], d["type"], d["path"], d["version"],
             d["valid_from"], None, d["supersedes"], d["text"]))
        counts["documents"] += 1
        # DOC_SUPERSEDES_DOC
        if d.get("supersedes"):
            db.add_edge(conn, "document", d["doc_id"], "DOC_SUPERSEDES_DOC",
                        "document", d["supersedes"])
        # DOC_GOVERNS_ASSET for every asset of the applicable type
        if d.get("applies_to"):
            for aid, atype in asset_types.items():
                if atype == d["applies_to"]:
                    db.add_edge(conn, "document", d["doc_id"], "DOC_GOVERNS_ASSET",
                                "asset", aid)
        # chunk into passages (one per section heading)
        for ordinal, (section, body) in enumerate(_chunk_sections(d["text"])):
            pid = short_id("doc", d["doc_id"], ordinal)
            kind = "manual_chunk" if d["type"] == "oem_manual" else "sop_chunk"
            ref = f"{d['doc_id']} v{d['version']} — {section}"
            conn.execute(
                "INSERT OR REPLACE INTO passages "
                "(passage_id,kind,asset_id,ts,title,text,source_ref,doc_id,event_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, kind, None, d["valid_from"], f"{d['title']} — {section}",
                 body, ref, d["doc_id"], None))
            counts["passages"] += 1


def _ingest_clauses(conn, counts):
    asset_types = {a["asset_id"]: a["type"] for a in connectors.read_assets()}
    for c in connectors.read_clauses():
        conn.execute("INSERT OR REPLACE INTO clauses VALUES (?,?,?,?,?,?,?)",
                     (c["clause_id"], c["standard"], c["title"], c["text"],
                      c["evidence_type"], c["frequency_days"], c["applies_to_type"]))
        counts["clauses"] += 1
        for aid, atype in asset_types.items():
            if atype == c["applies_to_type"]:
                db.add_edge(conn, "clause", c["clause_id"], "CLAUSE_APPLIES_TO_ASSET",
                            "asset", aid)


# --- events ----------------------------------------------------------------

def _add_event(conn, counts, *, asset_id, ts, etype, subtype, source, source_ref,
               param=None, value=None, unit=None, severity=None, status=None,
               text=None, person_id=None, confidence=1.0, make_passage=False,
               passage_kind=None):
    event_id = short_id(source, source_ref, asset_id, ts, subtype)
    conn.execute(
        "INSERT OR REPLACE INTO events "
        "(event_id,asset_id,ts,etype,subtype,param,value,unit,severity,status,"
        "text,person_id,source,source_ref,confidence,valid_from,valid_to) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, asset_id, ts, etype, subtype, param, value, unit, severity,
         status, text, person_id, source, source_ref, confidence, ts, None))
    counts["events"] += 1
    db.add_edge(conn, "asset", asset_id, "ASSET_HAS_EVENT", "event", event_id, ts)
    if person_id:
        db.add_edge(conn, "event", event_id, "EVENT_INVOLVES_PERSON",
                    "person", person_id, ts)
    db.add_lineage(conn, event_id, "event", source, source_ref, confidence)

    # cross-system auto-link: any *other* asset tag mentioned in the text
    for tag in extract.extract_tags(text or ""):
        if tag != asset_id:
            db.add_edge(conn, "event", event_id, "EVENT_MENTIONS_ASSET",
                        "asset", tag, ts, confidence=0.8)

    if make_passage and text:
        pid = short_id("pass", event_id)
        conn.execute(
            "INSERT OR REPLACE INTO passages "
            "(passage_id,kind,asset_id,ts,title,text,source_ref,doc_id,event_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, passage_kind, asset_id, ts, f"{passage_kind} — {asset_id}",
             text, source_ref, None, event_id))
        counts["passages"] += 1
    return event_id


def _ingest_pids(conn, counts):
    """Parse P&IDs: register tags, infer CONNECTED_TO, surface new equipment."""
    for doc in pid.read_pids():
        # store the drawing as a document + a searchable passage
        tag_list = ", ".join(n["tag"] for n in doc["nodes"])
        conn.execute(
            "INSERT OR REPLACE INTO documents "
            "(doc_id,title,type,path,version,valid_from,valid_to,supersedes,text) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (doc["doc_id"], f"P&ID {doc['doc_id']}", "pid", doc["path"], "B",
             None, None, None, f"Piping & Instrumentation Diagram. Equipment: {tag_list}."))
        counts["documents"] += 1
        pid_passage = short_id("pid", doc["doc_id"])
        conn.execute(
            "INSERT OR REPLACE INTO passages "
            "(passage_id,kind,asset_id,ts,title,text,source_ref,doc_id,event_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (pid_passage, "pid_chunk", None, None, f"P&ID {doc['doc_id']}",
             f"P&ID {doc['doc_id']} connects: " +
             "; ".join(f"{c['from']}→{c['to']}" for c in doc["connections"]),
             f"{doc['doc_id']} (P&ID drawing)", doc["doc_id"], None))
        counts["passages"] += 1

        known = {a["asset_id"] for a in db.query(conn, "SELECT asset_id FROM assets")}
        for node in doc["nodes"]:
            counts["pid_tags"] += 1
            # auto-discover equipment present on the drawing but not in CMMS/SCADA
            if node["tag"] not in known:
                conn.execute("INSERT OR REPLACE INTO assets VALUES (?,?,?,?,?,?)",
                             (node["tag"], f"{node['tag']} (from P&ID)", node["type"],
                              "Area-2 Utilities", "C", None))
                known.add(node["tag"])
                counts["discovered_assets"] += 1
                db.add_lineage(conn, node["tag"], "asset", "pid",
                               f"{doc['doc_id']} (P&ID drawing)", 0.7)
            db.add_edge(conn, "document", doc["doc_id"], "PID_SHOWS_ASSET",
                        "asset", node["tag"])

        for c in doc["connections"]:
            db.add_edge(conn, "asset", c["from"], "CONNECTED_TO", "asset", c["to"],
                        confidence=0.9)
            counts["connections"] += 1


def _ingest_scada(conn, counts):
    for r in connectors.read_scada():
        ts = r["timestamp"]
        _add_event(conn, counts, asset_id=r["tag"], ts=ts, etype="READING",
                   subtype=r["signal"], source="scada",
                   source_ref=f"SCADA {r['tag']} {r['signal']} @ {ts}",
                   param=r["signal"], value=float(r["reading"]), unit=r["units"],
                   text=None)


def _ingest_alarms(conn, counts):
    for r in connectors.read_alarms():
        code = r["alarm_code"]
        if code == "TRIP":
            etype, subtype = "TRIP", "trip"
        elif code == "VIB-HI":
            etype, subtype = "ALARM", "vibration_high"
        elif code == "DP-HI":
            etype, subtype = "ALARM", "dp_high"
        else:
            etype, subtype = "ALARM", code.lower()
        _add_event(conn, counts, asset_id=r["equipment"], ts=r["occurred"],
                   etype=etype, subtype=subtype, severity=r["priority"],
                   source="dcs_alarms",
                   source_ref=f"DCS alarm {code} on {r['equipment']} @ {r['occurred']}",
                   text=r["description"], person_id=r.get("ack_by"),
                   make_passage=True, passage_kind="alarm")


def _ingest_workorders(conn, counts):
    state_map = {"closed": "done", "deferred": "deferred", "open": "open"}
    for r in connectors.read_workorders():
        summary = r["summary"]
        actions = extract.extract_actions(summary)
        state = state_map.get(r["state"], r["state"])
        etype = "WORKORDER"
        if "bypass" in actions:
            etype, subtype = "BYPASS", "temporary_bypass"
        elif state == "deferred":
            subtype = "wo_deferred"
        elif "seal_replacement" in actions:
            subtype = "seal_replacement"
        elif "bearing_replacement" in actions or "alignment" in actions:
            subtype = "repair"
        elif "cleaning" in actions:
            subtype = "cleaning"
        else:
            subtype = "workorder"
        _add_event(conn, counts, asset_id=r["equip"], ts=r["raised_on"],
                   etype=etype, subtype=subtype, status=state, source="cmms",
                   source_ref=f"CMMS {r['wo_no']} ({r['state']}) on {r['equip']}",
                   text=summary, person_id=r.get("assigned_to"),
                   make_passage=True, passage_kind="workorder")


def _ingest_inspections(conn, counts):
    for r in connectors.read_inspections():
        ct, outcome = r["check_type"], r["outcome"]
        if ct == "alignment_check" and outcome == "marginal":
            subtype = "alignment_marginal"
        elif ct == "vibration_route" and outcome == "rising":
            subtype = "vibration_rise"
        elif ct == "thermography" and outcome == "degraded":
            subtype = "fouling_detected"
        elif ct == "post_repair":
            subtype = "post_repair"
        else:
            subtype = ct
        _add_event(conn, counts, asset_id=r["asset_tag"], ts=r["date"],
                   etype="INSPECTION", subtype=subtype, status=outcome,
                   source="inspection",
                   source_ref=f"Inspection {ct} ({outcome}) on {r['asset_tag']} @ {r['date']}",
                   text=r["remarks"], person_id=r.get("inspector"),
                   make_passage=True, passage_kind="inspection")


def _chunk_sections(text: str) -> list[tuple[str, str]]:
    """Split a markdown doc into (section_title, body) chunks by '## ' headings."""
    chunks, title, buf = [], "Overview", []
    for line in text.splitlines():
        if line.startswith("## "):
            if buf:
                chunks.append((title, "\n".join(buf).strip()))
            title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        chunks.append((title, "\n".join(buf).strip()))
    return [(t, b) for t, b in chunks if b]
