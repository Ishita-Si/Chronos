"""SQLite connection management and thin query helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .. import config
from ..util import now, to_iso, short_id

_SCHEMA = Path(__file__).with_name("schema.sql")


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False) -> None:
    """Create the schema. If reset, drop the existing database file first."""
    config.ensure_dirs()
    if reset and config.DB_PATH.exists():
        # remove WAL side files too
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(config.DB_PATH) + suffix)
            if p.exists():
                p.unlink()
    conn = connect()
    with conn:
        conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.close()


def is_seeded() -> bool:
    if not config.DB_PATH.exists():
        return False
    try:
        conn = connect()
        n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        return n > 0
    except sqlite3.Error:
        return False


# --- convenience query helpers --------------------------------------------

def query(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> dict | None:
    row = conn.execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


def add_edge(conn: sqlite3.Connection, src_type: str, src_id: str, rel: str,
             dst_type: str, dst_id: str, valid_from: str | None = None,
             valid_to: str | None = None, confidence: float = 1.0) -> None:
    edge_id = short_id(src_type, src_id, rel, dst_type, dst_id, valid_from)
    conn.execute(
        "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?,?,?)",
        (edge_id, src_type, src_id, rel, dst_type, dst_id,
         valid_from, valid_to, confidence),
    )


def add_lineage(conn: sqlite3.Connection, record_id: str, record_kind: str,
                source: str, source_ref: str, confidence: float = 1.0) -> None:
    conn.execute(
        "INSERT INTO lineage VALUES (?,?,?,?,?,?)",
        (record_id, record_kind, source, source_ref, to_iso(now()), confidence),
    )
