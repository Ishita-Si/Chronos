"""
Source connectors.

Each connector reads one source system's native export shape and yields raw
records. The differing column names (tag / equipment / equip / asset_tag) are
exactly the cross-system identity problem the normalizer resolves.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .. import config


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_assets() -> list[dict]:
    return _read_csv(config.WAREHOUSE_DIR / "assets.csv")


def read_persons() -> list[dict]:
    return _read_csv(config.WAREHOUSE_DIR / "persons.csv")


def read_scada() -> list[dict]:
    """SCADA historian export: tag, timestamp, signal, reading, units."""
    return _read_csv(config.WAREHOUSE_DIR / "scada.csv")


def read_alarms() -> list[dict]:
    """DCS alarm/event log: equipment, occurred, alarm_code, priority, ..."""
    return _read_csv(config.WAREHOUSE_DIR / "alarms.csv")


def read_workorders() -> list[dict]:
    """CMMS export: wo_no, equip, raised_on, wo_type, state, summary, ..."""
    return _read_csv(config.WAREHOUSE_DIR / "workorders.csv")


def read_inspections() -> list[dict]:
    """Inspection app export: asset_tag, date, check_type, outcome, ..."""
    return _read_csv(config.WAREHOUSE_DIR / "inspections.csv")


def read_documents() -> list[dict]:
    """Parse front-matter Markdown SOP / manual documents from data/sops."""
    docs = []
    for path in sorted(config.SOP_DIR.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        docs.append({
            "doc_id": meta.get("doc_id", path.stem),
            "title": meta.get("title", path.stem),
            "type": meta.get("type", "sop"),
            "version": str(meta.get("version", "")),
            "valid_from": meta.get("valid_from"),
            "supersedes": meta.get("supersedes"),
            "applies_to": meta.get("applies_to"),
            "path": f"data/sops/{path.name}",
            "text": body.strip(),
        })
    return docs


def read_clauses() -> list[dict]:
    if not config.REGS_FILE.exists():
        return []
    return json.loads(config.REGS_FILE.read_text(encoding="utf-8"))


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Minimal YAML-ish front-matter parser (no external deps)."""
    if not raw.startswith("---"):
        return {}, raw
    _, fm, body = raw.split("---", 2)
    meta: dict = {}
    for line in fm.strip().splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        val = val.strip().strip('"')
        meta[key.strip()] = None if val in ("", "null") else val
    return meta, body
