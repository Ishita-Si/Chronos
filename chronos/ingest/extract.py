"""
Entity / information extraction.

In production this is a fine-tuned transformer NER + rules. Here it is a
transparent rule+regex extractor that pulls the entities the knowledge graph
needs from any free-text field: equipment tags, process parameters, numeric
limits with units, dates, parts and personnel references. Every extraction is
deterministic and explainable, which keeps citation/confidence honest.
"""
from __future__ import annotations

import re

# Equipment tag, e.g. P-204, HX-11, C-12, V-7
TAG_RE = re.compile(r"\b([A-Z]{1,3}-\d{1,4})\b")

PARAM_LEXICON = {
    "vibration": ["vibration", "vib"],
    "pressure": ["pressure", "discharge pressure", "delta-p", "delta p", "differential pressure", "dp"],
    "temperature": ["temperature", "temp", "bearing temp", "outlet temp", "approach temperature"],
    "alignment": ["alignment", "misalignment", "soft-foot", "soft foot", "coupling"],
    "seal": ["seal", "mechanical seal"],
    "bearing": ["bearing", "drive end", "drive-end", "non-drive-end"],
    "fouling": ["fouling", "biofilm", "scaling"],
}

# value + unit, e.g. "7.1 mm/s", "0.05 mm", "12 months", "24h"
MEASURE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm/s|mm|bar|degc|°c|months?|hours?|h|hrs?|days?|%)",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# action / failure-mode keywords that drive RCA and trajectory typing
ACTION_KEYWORDS = {
    "seal_replacement": ["seal replacement", "replaced mechanical seal", "seal job"],
    "alignment": ["laser alignment", "shaft alignment", "alignment correction"],
    "bypass": ["bypass", "bypassed", "interlock"],
    "deferral": ["deferred", "deferral", "delayed", "awaited"],
    "cleaning": ["cleaning", "chemical clean", "cleaned"],
    "bearing_replacement": ["replaced bearing", "bearing replacement", "de bearing"],
}


def extract_tags(text: str) -> list[str]:
    if not text:
        return []
    return sorted(set(TAG_RE.findall(text)))


def extract_params(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower()
    found = []
    for canonical, variants in PARAM_LEXICON.items():
        if any(v in low for v in variants):
            found.append(canonical)
    return found


def extract_measures(text: str) -> list[dict]:
    if not text:
        return []
    out = []
    for val, unit in MEASURE_RE.findall(text):
        out.append({"value": float(val), "unit": unit.lower()})
    return out


def extract_dates(text: str) -> list[str]:
    return DATE_RE.findall(text or "")


def extract_actions(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower()
    return [a for a, kws in ACTION_KEYWORDS.items() if any(k in low for k in kws)]


def extract_all(text: str) -> dict:
    """Full extraction bundle for one text field."""
    return {
        "tags": extract_tags(text),
        "params": extract_params(text),
        "measures": extract_measures(text),
        "dates": extract_dates(text),
        "actions": extract_actions(text),
    }
