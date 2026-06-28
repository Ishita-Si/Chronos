"""
CHRONOS engine tests. Runs with pytest *or* standalone:

    python tests/test_engine.py
    python -m pytest -q
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chronos.pipeline import build
from chronos.store import db
from chronos.intel import vectorstore, copilot, sequence, rca, compliance, graph
from chronos.eval import benchmark


def setup_module(module=None):
    build(reset=True, verbose=False)


def test_graph_populated():
    conn = db.connect()
    assert len(graph.list_assets(conn)) >= 6
    n_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert n_events > 1000
    conn.close()


def test_trajectory_discovered():
    conn = db.connect()
    trajs = sequence.discover_trajectories(conn)
    assert trajs, "no failure trajectory mined"
    pat = trajs[0]["pattern"]
    assert pat[-1] == "trip"
    assert "temporary_bypass" in pat and "wo_deferred" in pat
    assert trajs[0]["support"] >= 2
    conn.close()


def test_live_asset_at_risk():
    conn = db.connect()
    det = sequence.detect(conn, "P-204")
    assert det["at_risk"] is True
    assert det["confidence"] >= 0.5
    assert det["lead_time_days"] is not None
    conn.close()


def test_copilot_cited_and_confident():
    conn = db.connect()
    store = vectorstore.build_store(conn)
    ans = copilot.answer(conn, store, "Why is high vibration recurring on P-204?")
    assert ans["confidence"] >= 0.5
    assert ans["citations"], "answer has no citations"
    assert ans["asset_id"] == "P-204"
    conn.close()


def test_rca_root_cause():
    conn = db.connect()
    r = rca.rca(conn, "P-204")
    assert r["available"]
    causes = " ".join(c["cause"] for c in r["probable_causes"]).lower()
    assert "misalign" in causes
    assert r["causal_chain"], "no causal chain built"
    conn.close()


def test_compliance_finds_gaps():
    conn = db.connect()
    rep = compliance.report(conn)
    assert rep["summary"]["total_checks"] > 0
    assert len(rep["gaps"]) >= 1
    conn.close()


def test_pid_extraction():
    b = benchmark.pid_extraction()
    assert b["available"]
    assert b["tag_f1"] == 1.0
    assert b["connectivity_f1"] == 1.0


def test_benchmark_sequence_perfect_on_demo():
    conn = db.connect()
    sp = benchmark.sequence_prediction(conn)
    assert sp["fp"] == 0 and sp["fn"] == 0
    assert sp["f1"] == 1.0
    conn.close()


if __name__ == "__main__":
    setup_module()
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed.")
    sys.exit(0 if passed == len(tests) else 1)
