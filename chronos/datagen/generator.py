"""
Deterministic synthetic plant generator.

Real SCADA/CMMS data is proprietary and cannot be shipped in a public repo,
so CHRONOS generates a *realistic* plant that mirrors the structure of genuine
source-system exports — and, crucially, embeds the recurring failure
trajectories the Sequence Intelligence layer is meant to discover:

    seal replacement -> alignment marginal -> vibration rise -> alarm chatter
    -> temporary trip-interlock bypass -> deferred work order -> TRIP

Each source is written in its own column shape (different tag columns, date
formats, status vocabularies) so the ingestion layer has to do real
normalization and cross-system auto-linking — not just read a clean table.
"""
from __future__ import annotations

import csv
import random
from datetime import timedelta
from pathlib import Path

from .. import config
from ..util import from_iso, to_iso

TODAY = from_iso("2026-06-28T08:00:00")

ASSETS = [
    # asset_id, name, type, area, criticality, install_date
    ("P-204", "Boiler Feed Water Pump A", "pump", "Area-2 Utilities", "A", "2016-03-11"),
    ("P-101", "Cooling Water Pump 1", "pump", "Area-1 Cooling", "B", "2015-07-22"),
    ("P-305", "Condensate Transfer Pump", "pump", "Area-3 Recovery", "B", "2017-11-02"),
    ("HX-11", "Crude Preheat Exchanger", "heat_exchanger", "Area-2 Utilities", "A", "2014-05-19"),
    ("C-12", "Process Air Compressor", "compressor", "Area-4 Air", "A", "2013-09-30"),
    ("V-7", "Suction Knockout Drum", "vessel", "Area-2 Utilities", "B", "2014-05-19"),
]

PERSONS = [
    ("T01", "Ravi Kumar", "Technician"),
    ("T02", "Anita Deshmukh", "Technician"),
    ("E01", "S. Iyer", "Reliability Engineer"),
    ("E02", "M. Khan", "Maintenance Lead"),
    ("C01", "P. Nair", "Compliance Officer"),
]


class _Sink:
    """Accumulates source-shaped rows for each emulated source system."""

    def __init__(self) -> None:
        self.scada: list[dict] = []
        self.alarms: list[dict] = []
        self.workorders: list[dict] = []
        self.inspections: list[dict] = []
        self.dirty_records: list[dict] = []
        self._wo = 4000

    def reading(self, tag, ts, signal, value, units):
        self.scada.append({"tag": tag, "timestamp": to_iso(ts),
                           "signal": signal, "reading": round(value, 2), "units": units})

    def alarm(self, equip, ts, code, priority, desc, ack="T01"):
        self.alarms.append({"equipment": equip, "occurred": to_iso(ts),
                            "alarm_code": code, "priority": priority,
                            "description": desc, "ack_by": ack})

    def workorder(self, equip, ts, wo_type, state, summary, craft, who):
        self._wo += 1
        self.workorders.append({"wo_no": f"WO-{self._wo}", "equip": equip,
                                "raised_on": to_iso(ts), "wo_type": wo_type,
                                "state": state, "summary": summary,
                                "craft": craft, "assigned_to": who})

    def inspection(self, asset_tag, ts, check_type, outcome, remarks, inspector):
        self.inspections.append({"asset_tag": asset_tag, "date": to_iso(ts),
                                 "check_type": check_type, "outcome": outcome,
                                 "remarks": remarks, "inspector": inspector})

    def dirty(self, system, asset_tag, ts, record_type, notes, value="", unit=""):
        self.dirty_records.append({"source_system": system, "equipment_tag": asset_tag,
                                   "event_time": to_iso(ts) if ts else "",
                                   "record_type": record_type, "reading": value,
                                   "unit": unit, "notes": notes})


def _routine_readings(sink: _Sink, rng: random.Random):
    """Background SCADA noise so the failure signal is not trivially obvious."""
    start = TODAY - timedelta(days=730)
    for asset_id, _n, atype, *_ in ASSETS:
        day = start
        base_vib = 2.3 if atype == "pump" else 1.5
        while day < TODAY:
            if atype == "pump":
                sink.reading(asset_id, day, "vibration", base_vib + rng.uniform(-0.4, 0.5), "mm/s")
                sink.reading(asset_id, day, "discharge_pressure", 11.0 + rng.uniform(-0.6, 0.6), "bar")
                sink.reading(asset_id, day, "bearing_temp", 58 + rng.uniform(-4, 5), "degC")
            elif atype == "heat_exchanger":
                sink.reading(asset_id, day, "delta_p", 0.45 + rng.uniform(-0.05, 0.08), "bar")
                sink.reading(asset_id, day, "outlet_temp", 182 + rng.uniform(-3, 3), "degC")
            elif atype == "compressor":
                sink.reading(asset_id, day, "discharge_pressure", 7.2 + rng.uniform(-0.3, 0.3), "bar")
                sink.reading(asset_id, day, "vibration", base_vib + rng.uniform(-0.3, 0.3), "mm/s")
            day += timedelta(days=7)


def _pump_failure_trajectory(sink: _Sink, rng: random.Random, asset_id: str,
                             start: str, ongoing: bool = False):
    """
    Emit the canonical pump failure trajectory. When `ongoing` is True the
    sequence stops *before* the trip (the live, in-progress case the detector
    must catch early).
    """
    t0 = from_iso(start)

    # Stage 0 - the seeding action: a seal replacement (root cause origin).
    # Note references the upstream suction drum (cross-system auto-link target).
    sink.workorder(asset_id, t0, "corrective", "closed",
                   "Replaced mechanical seal on drive end; isolated suction from "
                   "V-7 during the job. Pump returned to service.",
                   "mechanical", "T01")

    # Stage 1 - alignment check flags a marginal result (the latent defect)
    sink.inspection(asset_id, t0 + timedelta(days=5), "alignment_check", "marginal",
                    "Coupling alignment marginal after seal job. Soft-foot suspected. "
                    "Recommend laser alignment before next run hour milestone.", "T02")

    # Stage 2 - vibration rises on the historian (precursor signal)
    for i, d in enumerate((8, 9, 10, 11)):
        sink.reading(asset_id, t0 + timedelta(days=d), "vibration",
                     3.2 + i * 0.9 + rng.uniform(0, 0.3), "mm/s")
    sink.inspection(asset_id, t0 + timedelta(days=10), "vibration_route", "rising",
                    "Vibration trending upward, 1x running speed dominant — classic "
                    "misalignment signature. Flagged for follow-up.", "E01")

    # Stage 3 - alarm chatter (repeated high-vibration alarms, before the bypass)
    for d, h in ((12, 3), (12, 14), (13, 6), (13, 11), (13, 19)):
        sink.alarm(asset_id, t0 + timedelta(days=d, hours=h),
                   "VIB-HI", "high", "High vibration alarm on pump drive end bearing.")

    # Stage 4 - temporary bypass of the trip interlock to keep producing
    sink.workorder(asset_id, t0 + timedelta(days=14), "operations", "closed",
                   "Vibration trip interlock temporarily bypassed to sustain "
                   "production through shift and protect downstream HX-11 duty. "
                   "Bypass to be removed within 24h.",
                   "operations", "E02")

    # Stage 5 - corrective work order deferred (the fatal delay)
    sink.workorder(asset_id, t0 + timedelta(days=16), "corrective", "deferred",
                   "Alignment correction + bearing inspection deferred — spares "
                   "awaited and production priority. Risk accepted by shift lead.",
                   "mechanical", "E02")

    if ongoing:
        # one fresh high-vibration alarm to show the situation is live
        sink.alarm(asset_id, t0 + timedelta(days=17), "VIB-HI", "high",
                   "High vibration alarm — interlock still bypassed.")
        return

    # Stage 6 - TRIP / failure
    sink.alarm(asset_id, t0 + timedelta(days=20), "TRIP", "critical",
               "Pump tripped on high vibration. Drive-end bearing failure suspected.")

    # Stage 7 - repair closes the loop and records the verified root cause
    sink.workorder(asset_id, t0 + timedelta(days=21), "corrective", "closed",
                   "Replaced drive-end bearing and performed laser shaft alignment. "
                   "Confirmed root cause: shaft misalignment introduced during prior "
                   "seal replacement. Updated SOP to mandate laser alignment post-seal.",
                   "mechanical", "T01")
    sink.inspection(asset_id, t0 + timedelta(days=22), "post_repair", "pass",
                    "Post-repair vibration 2.1 mm/s, alignment within tolerance. "
                    "Lesson: enforce laser alignment after every seal replacement.", "E01")


def _hx_fouling_trajectory(sink: _Sink, rng: random.Random, asset_id: str, start: str):
    t0 = from_iso(start)
    for i, d in enumerate((0, 7, 14, 21)):
        sink.reading(asset_id, t0 + timedelta(days=d), "delta_p",
                     0.5 + i * 0.18 + rng.uniform(0, 0.03), "bar")
    sink.inspection(asset_id, t0 + timedelta(days=15), "thermography", "degraded",
                    "Approach temperature widening, fouling on tube side suspected.", "E01")
    sink.alarm(asset_id, t0 + timedelta(days=22), "DP-HI", "high",
               "High differential pressure across exchanger — fouling indicated.")
    sink.workorder(asset_id, t0 + timedelta(days=25), "corrective", "closed",
                   "Chemical cleaning of tube bundle performed; delta-P restored. "
                   "Root cause: cooling-water side fouling from biofilm.", "mechanical", "T02")


def _routine_inspections(sink: _Sink, rng: random.Random):
    """
    Monthly vibration routes on pumps — but deliberately MISS some months so
    the compliance agent has real gaps to find. P-305 is left non-compliant.
    """
    start = TODAY - timedelta(days=400)
    for asset_id, _n, atype, *_ in ASSETS:
        if atype != "pump":
            continue
        day = start
        skip_factor = 3 if asset_id == "P-305" else 1  # P-305 inspected sporadically
        i = 0
        while day < TODAY - timedelta(days=20):
            i += 1
            if i % skip_factor == 0:
                sink.inspection(asset_id, day, "vibration_route", "ok",
                                "Routine vibration route reading within normal limits.",
                                rng.choice(["T01", "T02"]))
            day += timedelta(days=30)
    # PSV / pressure-vessel inspection on the drum (one, then a long gap -> due)
    sink.inspection("V-7", TODAY - timedelta(days=380), "psv_test", "pass",
                    "Pressure safety valve pop-tested and certified.", "T01")


def _noise_and_counterexamples(sink: _Sink, rng: random.Random):
    """Messy plant records that should not become clean failure evidence."""
    # False alarms: vibration alerts without the causal precursor chain.
    for asset_id, day in (("C-12", 36), ("P-101", 52)):
        ts = TODAY - timedelta(days=day)
        sink.alarm(asset_id, ts, "VIB-HI", "medium",
                   "Short vibration spike during startup; cleared after load stabilized.")
        sink.reading(asset_id, ts + timedelta(minutes=2), "vibration",
                     7.0 + rng.uniform(0.1, 0.4), "mm/s")
        sink.reading(asset_id, ts + timedelta(hours=2), "vibration",
                     2.4 + rng.uniform(-0.2, 0.2), "mm/s")

    # Incomplete and typo-filled records kept as a dirty import sample, rather
    # than blindly trusted source-of-record data.
    sink.dirty("cmms_export", "", TODAY - timedelta(days=2), "work_order",
               "Wrkord incomplete: alignmnt correction pending, missing equip tag")
    sink.dirty("inspection_app", "P-204", TODAY - timedelta(days=1, hours=5),
               "inspection", "Vibrtion route shows 1x dominant; tag verified manually",
               "7.4", "mm/s")
    sink.dirty("dcs_alarms", "HX-11?", TODAY - timedelta(days=4), "alarm",
               "Operator note says pump vib high, but tag field contains exchanger typo")
    sink.dirty("cmms_export", "P-305", None, "work_order",
               "Incomplete work order export: bearing insp pending, timestamp missing")


def generate(out_dir: Path | None = None) -> dict:
    """Generate all source files. Returns a small manifest of counts."""
    out_dir = out_dir or config.WAREHOUSE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(config.RANDOM_SEED)
    sink = _Sink()

    _routine_readings(sink, rng)
    _routine_inspections(sink, rng)

    # Three historical pump failures (the "3 similar cases in 2 years")
    _pump_failure_trajectory(sink, rng, "P-204", "2024-09-10T06:00:00")
    _pump_failure_trajectory(sink, rng, "P-101", "2025-02-03T06:00:00")
    _pump_failure_trajectory(sink, rng, "P-305", "2025-08-15T06:00:00")
    # One historical exchanger fouling case
    _hx_fouling_trajectory(sink, rng, "HX-11", "2025-04-01T06:00:00")
    # The LIVE, in-progress P-204 trajectory (no trip yet) — detector must catch it
    _pump_failure_trajectory(sink, rng, "P-204", "2026-06-10T06:00:00", ongoing=True)
    _noise_and_counterexamples(sink, rng)

    _write_csv(out_dir / "assets.csv",
               ["asset_id", "name", "type", "area", "criticality", "install_date"],
               [dict(zip(["asset_id", "name", "type", "area", "criticality", "install_date"], a))
                for a in ASSETS])
    _write_csv(out_dir / "persons.csv", ["person_id", "name", "role"],
               [dict(zip(["person_id", "name", "role"], p)) for p in PERSONS])
    _write_csv(out_dir / "scada.csv",
               ["tag", "timestamp", "signal", "reading", "units"], sink.scada)
    _write_csv(out_dir / "alarms.csv",
               ["equipment", "occurred", "alarm_code", "priority", "description", "ack_by"],
               sink.alarms)
    _write_csv(out_dir / "workorders.csv",
               ["wo_no", "equip", "raised_on", "wo_type", "state", "summary", "craft", "assigned_to"],
               sink.workorders)
    _write_csv(out_dir / "inspections.csv",
               ["asset_tag", "date", "check_type", "outcome", "remarks", "inspector"],
               sink.inspections)
    _write_csv(out_dir / "dirty_records.csv",
               ["source_system", "equipment_tag", "event_time", "record_type", "reading", "unit", "notes"],
               sink.dirty_records)

    return {
        "assets": len(ASSETS), "persons": len(PERSONS),
        "scada": len(sink.scada), "alarms": len(sink.alarms),
        "workorders": len(sink.workorders), "inspections": len(sink.inspections),
        "dirty_records": len(sink.dirty_records),
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    print(generate())
