"""
CHRONOS - Unread Plant Memory Engine (UPME)

Turns decades of ignored plant data (SCADA, alarms, CMMS work orders,
inspections, SOPs) into a queryable, causal, continuously-learning
operational memory.

The package is intentionally dependency-free (Python standard library only)
so the prototype runs anywhere with `python -m chronos.pipeline` and
`python -m chronos.server`. Production swap-ins (Neo4j, pgvector,
sentence-transformers, FastAPI) are documented in the README.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
