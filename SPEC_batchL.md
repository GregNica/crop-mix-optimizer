# SPEC — Batch L: the labour batch

**Status:** DRAFT 2026-10-21, written for the grower to rule on the open questions (§2) before
any code. Source rulings: `DECISIONS.md` GROUP F (F1 superseded → grower's design, F2, F3, F4),
GROUP I (I2, I2a, I2b), GROUP H decision 4; `PLAN.md` "Batch L". Reference derivation:
`toy_models/toy_v11_lp.py` (per-role overtime, extra heads, allowance cap — already built and
mutation-guarded). Batch L starts only after Batch 2 has landed (BACKLOG BC1).

---

## 1. Where the code is today (measured, with refs)

| Thing | Today | Defect / note |
|---|---|---|
| Roster | `employees[]` rows: `position, type (salary/hourly/seasonal), count, wage, hours_per_week, field_time_pct, start_week, end_week` (`index.html` `renderLaborRow` ~2103, defaults ~2097) | Right shape. Every Batch L input becomes a COLUMN on this row (grower's design) |
| Capacity | `labor.py compute_labor_arrays` builds `labor_capacity`, `committed_weekly_wages`, `hourly_weighted_wages/hours` | Per-role arrays are summed and thrown away; `hourly_weighted_hours` is computed and never returned (F2/F3) |
| Main solve | Fixed staff only. C2: crop hours ≤ `labor_capacity[w]` | Overtime and hire exist ONLY in the What-If "Plan optimal labor" re-solve (`buildLaborFlexParams` ~9876) |
| Overtime | ONE blended rate (`overtime_hour_wage` × multiplier, default 1.5×), ONE flat cap `max_overtime_hrs_per_week` = 200 for all 52 weeks (`solver.py` ~1087) | **L2 live defect:** 15/52 weeks the cap exceeds the whole crew's hours; week 44 buys 191 OT h on 299 crew h. Blend cannot say WHO stays late (F4) |
| Hire | 52 spot `hire[w]` vars, `max_hire_hrs_per_week`, `hired_wage_per_hr` (inferred if blank), `hire_wage_markup` | F1: a spot market no farm has (2-hour weeks, 9 on/off switches). Deleted by the grower's design |
| Payroll load | One `payroll_load_pct` = 25%, on everything incl. OT premium | I2b: split into all-pay (FICA) + straight-time |
| Field % | `field_time_pct` = cap on share of hours available to crops | I2a: becomes Admin % (= 100 − Field %), inverse meaning |
| Indexing | `weekly_labor_supply` 52-long 0-indexed vs `overtime_hours_weekly` 53-long 1-indexed in the SAME result | Produced a false finding during F2's own measurement. L.1 fixes it |

The golden farm has labour flex **OFF**, so none of L.2/L.3 can move it — the "defaulting a
feature off leaves it unguarded" trap (third instance). Hence the flex-ON fixture (§4).

---

## 2. Open questions — need a grower ruling before build

**Q1 · Does overtime enter the MAIN plan, or stay in the What-If?** ⭐ the big one.
F1 says overtime is "genuinely a within-plan flex — your crew staying late, no lead time" and
"stays a decision variable". But today the main plan never buys overtime; only the What-If does.
- (a) **Recommended:** overtime ON in the main plan, governed by each role's allowance (default
  125% hourly/seasonal, 100% salaried). It is a real lever every farm pulls, and with a derived
  cap it can no longer run wild. ⚠️ This MOVES the golden farm (profit up, wherever the crew is
  at capacity — 26 of 52 weeks) → one deliberate re-pin, in L.2's commit, with deltas recorded.
- (b) Keep overtime What-If-only, as today. Golden does not move; the flex-ON fixture carries it.
- A grower who wants no overtime sets the allowance to 100% on every row — no separate toggle.

**Q2 · Extra hires: two farm-wide knobs or none?** The grower's design is "zero new inputs —
extra heads inherit the row". Toy v11 nonetheless carries two farm-wide parameters:
**new-hire productivity %** (default 70%) and **one-off cost per head** (default $800,
charged in the role's start week — recruiting/onboarding). The v10 measurement: hire-vs-overtime
flips at ~65% productivity, so that one factor decides the answer.
- Recommended: keep both, as two farm-wide boxes beside the roster, with sourced defaults
  later. Dropping them makes a new head as fast and as free to onboard as a 5-season veteran.

**Q3 · Extra hires: main plan or What-If?** Recommended: **What-If only** ("Plan optimal labor"
keeps its button, now answering per row). Hiring is decided before the season (60–75 days lead,
F1(b)), so it is advice you act on, not a decision the plan can make for you — matches F1's
"Plan vs Advisory" split. The output's `EXTRA HIRED` column gets an **"Add to roster"** action
that adds the heads to that row's Count, so the round trip is one click.

**Q4 · Tags before their demand exists.** Post-harvest and selling hours only get DEMAND in
Batch 3 (3.6/3.7). In Batch L the only task with demand is field work.
- Recommended: L.4 ships the tag **columns, storage, migration and the field tag's effect**
  (field tag off → that row adds no field capacity). The 3-pool LP (`h[role,task,week]`) is
  built in Batch 3 with the demand it serves. Building it now means machinery no test can make
  bind — the inert-guard trap this repo has paid for repeatedly.

**Q5 · Straight-time load default (I2b).** Needs a source. Statutory total ~12–17% non-H-2A
(GROUP H research) minus FICA 7.65% → ~5–9% before benefits. Proposed default **8%** pending a
citation; migration keeps old plans' regular cost exact regardless (§3 L.5).

**Q6 · Label wording for the allowance** (ruled: must not read as 125% ON TOP). Proposed:
column **"Max week incl. overtime"**, entered as %, with the hours shown live beside it:
`125%  → 50 h/wk (40 regular + 10 OT)`. Tooltip: "100% = no overtime for this role."

---

## 3. Build steps (PLAN order L.1 → L.5, one proposed swap)

⚠️ **Proposed reorder: L.5 (payroll split) BEFORE L.2.** L.2 prices overtime per role using the
load; if the split lands after, every overtime price changes twice and L.2's mutation-verified
guards must be re-derived (the W6 lesson in CLAUDE.md). L.5 is golden-neutral by construction
(migration keeps regular pay exact; golden buys no OT). New order: **L.1 → L.5 → L.2 → L.3 → L.4.**

### L.1 · F3 — the labour block as named per-role arrays (behaviour-neutral)
- `labor.py` returns, per role r and week w: `heads[r][w]`, `paid_hours[r][w]`,
  `task_hours[r][w]` (= paid × (1 − admin)), `cost[r][w]`, plus `is_hourly[r]`. The farm totals
  (`labor_capacity`, `committed_weekly_wages`) become SUMS of these, computed once.
- Every weekly labour array in the result is **52-long, 0-indexed** (fixes the 52/53 split; the
  adapter is the one place that converts if the UI wants week numbers).
- Publish `labor_by_role` in the payload (adapter + `test_adapter_contract.py`: a key added to
  the solver but not the adapter is the W6 failure).
- **Proof of neutrality:** golden farm byte-equivalent, profit to the last digit (the E2 method).

### L.5 · I2b — payroll load split (golden-neutral)
- Replace `payroll_load_pct` with `fica_pct` (default 7.65; 0 for H-2A rows — not modelled yet,
  tooltip says so) and `straight_time_load_pct` (default per Q5).
- Cost of a regular hour = wage × (1 + fica + straight). Cost of an OT hour =
  wage × mult × (1 + fica) + wage × straight (the premium carries FICA only).
- Salaried: annual × (1 + fica + straight).
- **Migration** (form load + saved plans, E5 rename path, reported in the load report): old
  25% → fica 7.65 + straight 17.35, so regular pay is unchanged to the cent and only overtime
  gets cheaper. Load report says exactly that.
- Chat allowlist (`fields.js`, `worker/grounding.ts`) updated; `payroll_load_pct` removed.

### L.2 · F2 + F4 — overtime per role, cap derived from the roster
- Variables `ot[r][w] ≥ 0` for hourly/seasonal roles in their window only (salaried: none).
- Cost `Σ ot[r][w] × ot_rate[r]`, `ot_rate[r]` per L.5 with **multiplier default 1.0×**
  (FLSA ag exemption; tooltip: 1.5× where state law requires it).
- Cap: `ot[r][w] ≤ (allowance[r] − 1) × count[r] × hours[r] × (1 − admin[r])`.
- C2: crop hours ≤ `labor_capacity[w] + Σ_r ot[r][w]`. C13 cash: OT paid in its week.
- **Deleted:** `max_overtime_hrs_per_week`, the blended `overtime_hour_wage`, BACKLOG L5.
  Migration drops the old cap with a load-report line ("overtime is now limited per role").
- Results: overtime hours **by role and week** (answers "who do I ask to stay late").
- **Flex-ON golden fixture lands in THIS commit** (§4). If Q1(a): the golden re-pin too.

### L.3 · F1 — `Hire more?` / `Max more` / `EXTRA HIRED`
- Row columns `hire_more` (bool, default off) and `max_more` (int). Solver: integer
  `extra[r] ∈ [0, max_more[r]]` where `hire_more[r]`.
- An extra head inherits the row's wage, hours, admin %, tags, allowance and window; it adds
  `extra × hours × (1−admin) × productivity` capacity in every window week, costs the row's full
  weekly pay in every window week (committed, W12) + the one-off per-head cost in the start
  week (Q2), and raises that row's OT cap.
- **Deleted:** `hire_enabled`, `max_hire_hrs_per_week`, `hired_wage_per_hr`,
  `hire_wage_markup`, the 52 `hire[w]` vars, W15's pricing question, W17. Migration drops them
  with a load-report line.
- Tooltip teaches the shape: "Need a different window or wage? Add a new row with the same title
  — a different window is a different job offer."
- Expected answer on the shipped farm: **zero extra heads** (F1 measured every role losing
  money: Farm Manager −$65,714 … Equipment Operator −$9,098). A zero is a real answer, so the
  results must SAY it ("no extra hire pays for itself — here is why"), not show an empty column.
- Measure MILP solve time with the new integers before and after (budget: no golden-farm
  slowdown a grower would notice; record the numbers).

### L.4 · I2/I2a — task tags + Admin %
- Column `field_time_pct` → `admin_pct` (= 100 − old). Migration on load, reported. Shipped
  defaults: manager 20, operators 10, crews 0.
- Columns `task_field`, `task_postharvest`, `task_selling` (bools, default all ON). In Batch L
  only `task_field` has an effect (Q4). The other two are stored, round-trip, and say
  "(used from Batch 3)" in their tooltip — no claim the model uses them yet (the untrue-label
  class, W6).
- With all tags on and admin = 100 − field, golden is byte-equivalent.

---

## 4. Guards (written AFTER `/simplify` on each step's working code — CLAUDE.md order)

- **Flex-ON golden fixture** (`tests/golden/`, with L.2): shipped roster, overtime allowed at
  125%, hire-more on two rows. Pins profit, OT hours by role, extra heads. Re-derived, not
  copied, for each later step that moves it.
- **Second derivation:** the toy v11 LP on a matching config must agree with the app on OT hours
  and extra heads (it is the only derivation not downstream of `solver.py`).
- **Two-condition fixtures** (the shelf-life lesson): the cap test needs a week where the crew is
  short AND an hourly role is on; the per-role price test needs two hourly roles with DIFFERENT
  wages both on in a short week (else "cheapest role first" is untestable); the extra-head test
  needs a forced-extra-head fixture, since the optimum is zero.
- Mutations to catch, at minimum: cap uses `allowance` not `allowance − 1`; salaried role gets
  OT; OT rate uses the blend; premium carries the straight-time load; extra head billed one week
  instead of the window; per-head cost charged every week ($800 × 33); admin applied as field %;
  migration off by the inverse; a field-tag-off row still adds capacity.
- Client: `labor_ui_client.cjs` (columns render, live hours readout for the allowance),
  `form_state_client.cjs` (migrations idempotent, nothing dropped), `field_registry` + chat
  allowlist, import/export roster columns, golden payload `--check`.

## 5. Not in Batch L
Piece rate (F5) → Batch 6. Post-harvest/selling demand + the 3-pool LP (I1, I3, 3.6/3.7) →
Batch 3. H-2A modelling (FICA 0, housing) → later. L6 (crop size per bushel) → Batch 3 agronomy.

## 6. Process
Per step: measure → working code + enough tests → `/simplify` → deep guards + mutation → next
step. One browser pass at the END of the batch. `/code-review max` (or ultra) + `/simplify` on
the branch before landing. Branch: `batchL/labour` off `feat/server-llm-expansion` AFTER Batch 2
lands.
