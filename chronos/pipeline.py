"""
End-to-end build pipeline: generate synthetic plant -> initialise the store ->
ingest & normalise everything into the temporal knowledge graph.

Run:  python -m chronos.pipeline           (build if needed)
      python -m chronos.pipeline --reset   (rebuild from scratch)
"""
from __future__ import annotations

import sys

from . import config
from .datagen import generator
from .store import db
from .ingest import normalize


def build(reset: bool = True, verbose: bool = True) -> dict:
    config.ensure_dirs()
    if verbose:
        print("[1/3] Generating synthetic plant data ...")
    gen = generator.generate()

    if verbose:
        print(f"      sources: {gen}")
        print("[2/3] Initialising plant memory store ...")
    db.init_db(reset=reset)

    if verbose:
        print("[3/3] Ingesting & normalising into the knowledge graph ...")
    conn = db.connect()
    counts = normalize.ingest_all(conn)
    conn.close()

    if verbose:
        print(f"      graph: {counts}")
        print(f"      database: {config.DB_PATH}")
        print("Done. Start the app with:  python -m chronos.server")
    return {"sources": gen, "graph": counts}


def ensure_built() -> None:
    if not db.is_seeded():
        build(reset=True, verbose=True)


if __name__ == "__main__":
    build(reset="--reset" in sys.argv or not db.is_seeded())
