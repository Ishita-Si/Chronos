# CHRONOS — demo script

**Setup (once):**
```bash
python -m chronos.pipeline --reset
python -m chronos.server          # open http://127.0.0.1:8000
```
Total runtime ≈ 4 minutes. Keep the role selector (top-right) on **Engineer**.

---

## 0 · The hook (15s)
> "Every plant already holds the knowledge to prevent its next failure — buried
> across SCADA, alarms, work orders, inspections, SOPs and P&IDs. CHRONOS reads
> all of it into one temporal memory and tells you what's about to break."

Land on **🏠 Home**. It opens calm and human: a status line *"1 asset needs
attention. Everything else is running normally."* and a single **Needs attention
now** card in plain English — no jargon. (The engineering numbers live under
*"Knowledge engine · under the hood"*.)

---

## 1 · Flow A — Technician, one tap from the home screen (60s)
1. On **Home**, the P-204 card reads: *"This equipment is repeating a failure
   pattern that has ended in a trip 3 times before. At the current pace it could
   trip in about 2 days."*
2. Click **"See the recommended fix →"** — it jumps to **💬 Ask** and answers
   automatically. (Or open **Ask** and click a suggested question.)
3. Read the answer aloud:
   - **96% confidence** badge (top).
   - *"When did we see this before?"* → **3 similar past trips** (P-204, P-101, P-305).
   - *Most likely root cause* → **shaft misalignment after seal replacement (100%)**.
   - *Pattern we are entering now* → the full trajectory + **~2 days to trip**.
   - **Recommended action checklist** (laser alignment per SOP-PUMP-ALIGN v2).
   - **Citations** to the exact alarms / SOP sections.

> "Not a manual lookup — a source-backed answer that replays what worked before."

---

## 2 · Flow B — Reliability engineer (60s)
1. Go to **⚠ Risk**. P-204 shows **AT RISK 92%**.
2. Click **P-204** → the detail panel:
   - The matched trajectory chain (matched stages highlighted, **trip** in red).
   - **Connected equipment from the P&ID** (V-7 upstream, HX-11 downstream).
   - **Vibration trend** sparkline.
3. Click **▶ Simulate: act today vs defer 7 days**:
   - Act today → **8% trip risk**. Defer 7 days → **97%**. **89-point** reduction.
4. Click **🔍 Run RCA + lessons learned** → causal chain + preventive playbook.

---

## 3 · P&ID parsing (30s)
1. Go to **🗺 P&ID**.
2. Show the parsed drawing, **5 extracted tags**, **4 inferred connections**.
3. Note: **FCV-204** and **TK-2** were on the drawing but missing from CMMS/SCADA —
   auto-discovered and added to the graph.

---

## 4 · Flow C — Compliance officer (45s)
1. Go to **✓ Compliance**. Summary: compliant / due-soon / **gaps**.
2. Scan the clause-by-clause evidence map (OISD-130, Factory Act, PESO).
3. Click a **non_compliant** / **missing** row (e.g. C-12 · PESO-CG-4) →
   an **audit-ready evidence pack** with the clause text, status and supporting
   records (or the explicit gap).

---

## 5 · Trust, security & proof (30s)
1. Go to **📊 Benchmark**: entity-extraction F1 0.97, P&ID F1 1.0, trajectory
   prediction F1 1.0, **100% citation rate**, and the **CHRONOS vs traditional
   search** comparison.
2. Change the role (top-right) to **Technician** → revisit **Benchmark** /
   **Simulate**: **🔒 Access denied** (RBAC). Switch to **Admin** → it works, and
   every call is in the audit trail.

---

## 6 · Close (15s)
> "Decades of unread plant memory, now a living decision system: it sees the
> failure pattern forming, estimates the lead time, prescribes the source-backed
> fix, and proves compliance — fully on-prem, fully cited."
