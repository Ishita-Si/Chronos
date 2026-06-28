"""Small shared utilities: ids, dates, text tokenisation."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

ISO = "%Y-%m-%dT%H:%M:%S"

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]*")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "as",
    "at", "by", "from", "we", "our", "their", "has", "had", "have", "will",
    "shall", "should", "must", "not", "no", "if", "then", "than", "when",
    "what", "why", "how", "did", "do", "does", "due", "per",
}


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def to_iso(dt: datetime) -> str:
    return dt.strftime(ISO)


def from_iso(s: str) -> datetime:
    return datetime.strptime(s[:19], ISO)


def days_between(a: str, b: str) -> float:
    """Signed days from a -> b (positive if b is later)."""
    return (from_iso(b) - from_iso(a)).total_seconds() / 86400.0


def short_id(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stopwords removed, equipment tags kept."""
    if not text:
        return []
    toks = _TOKEN_RE.findall(text.lower())
    return [t for t in toks if t not in _STOPWORDS and len(t) > 1]


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse term-weight vectors."""
    if not a or not b:
        return 0.0
    # iterate the smaller vector for the dot product
    if len(a) > len(b):
        a, b = b, a
    dot = sum(w * b.get(t, 0.0) for t, w in a.items())
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def add_days(iso: str, days: float) -> str:
    return to_iso(from_iso(iso) + timedelta(days=days))


def uniq(seq: Iterable) -> list:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
