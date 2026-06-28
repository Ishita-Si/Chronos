"""
Console walkthrough that exercises every intelligence module end-to-end
without the web server — proof the engine is fully functional.

Run:  python -m chronos.demo
"""
from __future__ import annotations

import sys

from .store import db
from .pipeline import ensure_built
from .intel import vectorstore, copilot, sequence, rca, compliance


def _rule(title: str) -> None:
    print("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows console -> UTF-8
    except Exception:
        pass
    ensure_built()
    conn = db.connect()
    store = vectorstore.build_store(conn)

    _rule("DISCOVERED FAILURE TRAJECTORIES (mined from history)")
    for t in sequence.discover_trajectories(conn):
        print(f"  {t['trajectory_id']}  (support={t['support']})")
        print(f"    {t['label']}")
        print(f"    stage offsets (days before trip): "
              f"{t['stage_offsets_days_before_trip']}")

    _rule("FLEET RISK SCAN (live)")
    for r in sequence.fleet_risk(conn):
        print(f"  {r['asset_id']} [{r['criticality']}] {r['asset_name']}: "
              f"{int(r['confidence']*100)}% — stage '{r['current_stage']}', "
              f"~{r['lead_time_days']}d to trip")

    _rule("COPILOT — Flow A: technician asks about P-204")
    ans = copilot.answer(conn, store,
                         "Why is high vibration recurring this month on P-204?")
    print(f"  Q: {ans['question']}")
    print(f"  Confidence: {int(ans['confidence']*100)}%")
    print(f"  Summary: {ans['summary']}")
    for s in ans["sections"]:
        print(f"\n  ## {s['heading']}\n     " + s["body"].replace("\n", "\n     "))
    print("\n  Recommended actions:")
    for a in ans["recommended_actions"]:
        print(f"    - {a}")
    print("\n  Citations:")
    for c in ans["citations"][:5]:
        print(f"    [{c['score']}] {c['ref']}")

    _rule("DECISION SIMULATION — act today vs defer 7 days (P-204)")
    sim = sequence.simulate(conn, "P-204", defer_days=7)
    print(f"  {sim}")

    _rule("RCA + LESSONS LEARNED (P-204 historical trip)")
    report = rca.rca(conn, "P-204")
    print(f"  Mode: {report['mode']}  Confidence: {int(report['confidence']*100)}%")
    print("  Causal chain:")
    for step in report["causal_chain"]:
        print(f"    {step['ts'][:10]}  {step['stage']}")
    print("  Probable causes:")
    for pc in report["probable_causes"]:
        print(f"    - {pc['cause']} ({int(pc['confidence']*100)}%)")
    print(f"  Lessons learned: {report['lessons_learned']['title']}")

    _rule("COMPLIANCE GAP SCAN (all standards)")
    rep = compliance.report(conn)
    print(f"  Summary: {rep['summary']}")
    print("  Gaps:")
    for g in rep["gaps"]:
        print(f"    [{g['status']}] {g['asset_id']} — {g['clause_id']} "
              f"({g['standard']}): {g['detail']}")

    conn.close()
    print("\nAll modules executed successfully.\n")


if __name__ == "__main__":
    main()
