"""Central configuration and filesystem paths for CHRONOS."""
from __future__ import annotations

import os
from pathlib import Path

# Repository root (the folder that contains the `chronos/` package).
ROOT = Path(__file__).resolve().parent.parent

# Authored corpus that ships with the repo (committed to git).
DATA_DIR = ROOT / "data"
SOP_DIR = DATA_DIR / "sops"
REGS_FILE = DATA_DIR / "regulations" / "clauses.json"

# Runtime working area (generated artefacts, git-ignored).
VAR_DIR = ROOT / "var"
WAREHOUSE_DIR = VAR_DIR / "warehouse"   # generated source-system exports (CSV)
DB_PATH = VAR_DIR / "chronos.db"        # the unified plant memory store

# Frontend static assets.
FRONTEND_DIR = ROOT / "frontend"

# Deterministic seed so the synthetic plant is reproducible across machines.
RANDOM_SEED = int(os.environ.get("CHRONOS_SEED", "20260628"))

# Fixed "now" for the demo so risk/compliance results are reproducible and the
# generated live trajectory always lines up. Override via env for live use.
AS_OF = os.environ.get("CHRONOS_AS_OF", "2026-06-28T08:00:00")

# Server defaults.
HOST = os.environ.get("CHRONOS_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHRONOS_PORT", "8000"))

# Sequence-intelligence tuning.
TRAJECTORY_WINDOW_DAYS = 21       # look-back window for precursor sequences
MIN_PATTERN_SUPPORT = 2          # min historical occurrences to call it a pattern
TERMINAL_EVENT_TYPES = {"TRIP", "FAILURE"}

# Event subtypes that constitute a failure trajectory (shared by ingestion
# normalization and the sequence-mining layer).
SIGNIFICANT_SUBTYPES = {
    "alignment_marginal", "vibration_rise", "vibration_high", "temporary_bypass",
    "wo_deferred", "trip", "fouling_detected", "dp_high", "cleaning",
    "seal_replacement", "repair", "post_repair",
}


def ensure_dirs() -> None:
    """Create runtime directories if they do not yet exist."""
    for d in (VAR_DIR, WAREHOUSE_DIR, SOP_DIR, REGS_FILE.parent):
        d.mkdir(parents=True, exist_ok=True)
