---
doc_id: SOP-VIB-MON
title: Rotating Equipment Vibration Monitoring and Alarm Response
type: sop
version: "1.3"
valid_from: 2024-06-01
applies_to: pump
---

# SOP-VIB-MON v1.3 — Vibration Monitoring and Alarm Response

## 1. Purpose
Define monitoring cadence and the mandatory response to vibration alarms on
rotating equipment (pumps, compressors).

## 2. Monitoring Cadence
- Monthly vibration route reading for all Criticality A and B pumps.
- Continuous online vibration monitoring where trip interlocks are installed.

## 3. Alarm Thresholds
- VIB-HI (high): 7.1 mm/s — acknowledge and investigate within the shift.
- VIB-HH (high-high) / TRIP: 9.0 mm/s — automatic trip.

## 4. Alarm Chatter
Three or more VIB-HI alarms within 48 hours constitutes **alarm chatter** and
indicates an accelerating fault. Raise a corrective work order immediately;
do **not** simply re-acknowledge.

## 5. Trip Interlock Bypass (controlled action)
A vibration trip interlock may be bypassed **only** with written authorisation
from both the Maintenance Lead and the Reliability Engineer, for a maximum of
24 hours, with a corrective work order already scheduled. An un-removed bypass
combined with a deferred corrective work order is the highest-risk state for an
unplanned trip and must be escalated.

## 6. Escalation
If vibration is rising AND a corrective work order is deferred, escalate to the
Reliability Engineer the same day. This combination has historically preceded
pump trips by 4–7 days.
