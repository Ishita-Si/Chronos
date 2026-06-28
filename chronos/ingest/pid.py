"""
P&ID parsing (layout + symbol/tag extraction).

In production this is Azure Document Intelligence / LayoutParser running on
scanned drawings. Here we parse a vector P&ID: equipment tags are extracted
geometrically from text nodes, and process connectivity is *inferred* by
matching each connector line's endpoints to the nearest equipment tag — the
same nearest-symbol heuristic a layout model applies to detected boxes.

The output enriches the knowledge graph with CONNECTED_TO relationships and can
surface equipment tags that exist on the drawing but not yet in CMMS/SCADA.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import config
from .extract import TAG_RE

# symbol shape -> equipment type (a tiny symbol classifier)
_SHAPE_TYPE = {"circle": "pump", "rect": "equipment"}


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _nearest(point, nodes):
    px, py = point
    best, best_d = None, 1e18
    for n in nodes:
        d = math.hypot(px - n["x"], py - n["y"])
        if d < best_d:
            best, best_d = n, d
    return best, best_d


def parse_pid(path: Path) -> dict:
    """Return {nodes:[{tag,x,y,symbol,type}], connections:[{from,to}], svg}."""
    raw = path.read_text(encoding="utf-8")
    root = ET.fromstring(raw)

    # 1) tag/symbol extraction from <text> nodes
    nodes: list[dict] = []
    texts = []
    for el in root.iter():
        if _strip_ns(el.tag) == "text" and el.text:
            m = TAG_RE.search(el.text.strip())
            if m:
                x = float(el.get("x", 0)); y = float(el.get("y", 0))
                texts.append((m.group(1), x, y))

    # associate a nearby symbol shape with each tag (for type inference)
    shapes = []
    for el in root.iter():
        t = _strip_ns(el.tag)
        if t == "circle":
            shapes.append(("circle", float(el.get("cx", 0)), float(el.get("cy", 0))))
        elif t == "rect" and float(el.get("width", 0)) < 200:  # skip page bg
            cx = float(el.get("x", 0)) + float(el.get("width", 0)) / 2
            cy = float(el.get("y", 0)) + float(el.get("height", 0)) / 2
            shapes.append(("rect", cx, cy))

    for tag, x, y in texts:
        sym, _d = _nearest((x, y), [{"x": s[1], "y": s[2], "shape": s[0]} for s in shapes]) \
            if shapes else (None, 0)
        symbol = sym["shape"] if sym else "rect"
        nodes.append({"tag": tag, "x": x, "y": y, "symbol": symbol,
                      "type": _SHAPE_TYPE.get(symbol, "equipment")})

    # 2) connectivity inference from connector lines
    connections: list[dict] = []
    for el in root.iter():
        if _strip_ns(el.tag) != "line":
            continue
        p1 = (float(el.get("x1", 0)), float(el.get("y1", 0)))
        p2 = (float(el.get("x2", 0)), float(el.get("y2", 0)))
        a, da = _nearest(p1, nodes)
        b, db = _nearest(p2, nodes)
        if a and b and a is not b and da < 90 and db < 90:
            connections.append({"from": a["tag"], "to": b["tag"]})

    # de-duplicate
    seen, conns = set(), []
    for c in connections:
        key = (c["from"], c["to"])
        if key not in seen:
            seen.add(key)
            conns.append(c)

    return {"doc_id": path.stem, "path": f"data/pid/{path.name}",
            "nodes": nodes, "connections": conns, "svg": raw}


def read_pids() -> list[dict]:
    out = []
    pid_dir = config.DATA_DIR / "pid"
    if not pid_dir.exists():
        return out
    for path in sorted(pid_dir.glob("*.svg")):
        out.append(parse_pid(path))
    return out
