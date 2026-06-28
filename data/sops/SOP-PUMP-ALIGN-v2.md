---
doc_id: SOP-PUMP-ALIGN
title: Centrifugal Pump Mechanical Seal Replacement and Shaft Alignment
type: sop
version: "2.0"
valid_from: 2025-01-15
supersedes: SOP-PUMP-ALIGN-v1
applies_to: pump
---

# SOP-PUMP-ALIGN v2.0 — Mechanical Seal Replacement and Shaft Alignment

## 1. Purpose
Standardise mechanical seal replacement on centrifugal pumps and **eliminate
misalignment-induced bearing failures** that have historically followed seal
jobs.

## 2. Scope
All centrifugal pumps in Area-1 through Area-4, including boiler feed water,
cooling water and condensate transfer pumps (e.g. P-101, P-204, P-305).

## 3. Critical Requirement (Rev 2 change)
> After **every** mechanical seal replacement, a **laser shaft alignment**
> MUST be performed and recorded before the pump is returned to service.
> Dial-indicator alignment alone is **not** acceptable. Soft-foot must be
> checked and corrected.

Rationale: repeated drive-end bearing failures were traced to shaft
misalignment introduced during seal replacement. Marginal alignment produces a
rising 1x running-speed vibration that escalates to a trip within ~2–3 weeks.

## 4. Procedure
1. Isolate, de-energise and lock out the pump.
2. Replace the mechanical seal per OEM manual MAN-PUMP-OEM.
3. Re-install coupling; check and correct soft-foot.
4. Perform **laser alignment** to within 0.05 mm parallel / 0.05 mm angular.
5. Record alignment readings on the work order.
6. Baseline vibration after restart; confirm below 4.5 mm/s.

## 5. Vibration Acceptance
- Normal: < 4.5 mm/s RMS
- Alert: 4.5–7.1 mm/s — schedule corrective action within 7 days
- Danger: > 7.1 mm/s — do not run; raise immediate work order

## 6. Prohibited Actions
- Returning a pump to service after a seal job without recorded laser alignment.
- Bypassing the vibration trip interlock without written authorisation from the
  Maintenance Lead and Reliability Engineer (see SOP-VIB-MON §5).
