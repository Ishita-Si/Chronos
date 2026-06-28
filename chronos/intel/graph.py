"""
Temporal knowledge-graph query helpers.

Thin, readable accessors over the SQLite property graph: asset timelines,
governing documents, applicable clauses, similar past cases. These are the
graph half of the copilot's hybrid retrieval.
"""
from __future__ import annotations

import sqlite3

from ..store import db


def get_asset(conn, asset_id: str) -> dict | None:
    return db.one(conn, "SELECT * FROM assets WHERE asset_id=?", (asset_id,))


def list_assets(conn) -> list[dict]:
    return db.query(conn, "SELECT * FROM assets ORDER BY criticality, asset_id")


def asset_events(conn, asset_id: str, etypes: tuple[str, ...] | None = None,
                 since: str | None = None, until: str | None = None,
                 limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM events WHERE asset_id=?"
    params: list = [asset_id]
    if etypes:
        sql += " AND etype IN (%s)" % ",".join("?" * len(etypes))
        params += list(etypes)
    if since:
        sql += " AND ts >= ?"
        params.append(since)
    if until:
        sql += " AND ts <= ?"
        params.append(until)
    sql += " ORDER BY ts LIMIT ?"
    params.append(limit)
    return db.query(conn, sql, params)


def significant_events(conn, asset_id: str, significant: set[str],
                       since: str | None = None) -> list[dict]:
    """Ordered timeline of trajectory-relevant events for an asset."""
    rows = asset_events(conn, asset_id, since=since)
    return [e for e in rows if e["subtype"] in significant]


def governing_documents(conn, asset_id: str) -> list[dict]:
    return db.query(conn,
        "SELECT d.* FROM documents d "
        "JOIN edges e ON e.src_id=d.doc_id AND e.rel='DOC_GOVERNS_ASSET' "
        "WHERE e.dst_id=? AND (d.supersedes IS NULL OR d.doc_id NOT IN "
        "(SELECT dst_id FROM edges WHERE rel='DOC_SUPERSEDES_DOC'))",
        (asset_id,))


def applicable_clauses(conn, asset_id: str) -> list[dict]:
    return db.query(conn,
        "SELECT c.* FROM clauses c "
        "JOIN edges e ON e.src_id=c.clause_id AND e.rel='CLAUSE_APPLIES_TO_ASSET' "
        "WHERE e.dst_id=?", (asset_id,))


def trips(conn, asset_id: str | None = None) -> list[dict]:
    if asset_id:
        return db.query(conn,
            "SELECT * FROM events WHERE etype='TRIP' AND asset_id=? ORDER BY ts",
            (asset_id,))
    return db.query(conn, "SELECT * FROM events WHERE etype='TRIP' ORDER BY ts")


def connected_assets(conn, asset_id: str) -> list[dict]:
    """Process-connected neighbours from P&ID connectivity (both directions)."""
    rows = db.query(conn,
        "SELECT dst_id AS tag, 'downstream' AS direction FROM edges "
        "WHERE rel='CONNECTED_TO' AND src_id=? "
        "UNION SELECT src_id AS tag, 'upstream' AS direction FROM edges "
        "WHERE rel='CONNECTED_TO' AND dst_id=?", (asset_id, asset_id))
    for r in rows:
        a = get_asset(conn, r["tag"])
        r["name"] = a["name"] if a else r["tag"]
    return rows


def person(conn, person_id: str | None) -> dict | None:
    if not person_id:
        return None
    return db.one(conn, "SELECT * FROM persons WHERE person_id=?", (person_id,))
