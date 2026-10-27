# CLAUDE.md — Farm Crop-Mix Optimization Project

## Project Overview

This project translates a farm profit-maximization Excel Solver model ("Group 5_Baby Model_Final") into a Python Jupyter notebook (`farm_optimization.ipynb`). The model finds the optimal crop planting schedule for a 150-acre farm to maximize annual profit subject to land, water, labor, storage, demand, diversity, and budget constraints.

> **Note:** the sections below document the *original* Excel/notebook model (150-acre, fixed parameters). The current deliverable is the in-browser web app (`index.html`, `farm_v2/` solver), which has evolved substantially — including a smaller **~80-acre** default farm, sell-through/overhead/interest realism, per-channel sales, and labor flexibility. Treat the 150-acre figures and the cost tables here as legacy reference for the source model, not the current app defaults.

---

## Development Workflow — Review Before Committing (DEFAULT)

Run the review skills before finalizing work — this is the project default, not optional:

- **Before committing** non-trivial changes to a branch: run **`/simplify`** on the diff (reuse/simplification/efficiency cleanup — quality only, not a bug hunt). Apply its fixes, then commit.
- **Before landing a branch** (opening a PR / merging to `master`): run **`/code-review high`** (bug hunt) *and* `/simplify` across the branch diff. **Never launch `/code-review max` or `/code-review ultra` on your own (grower ruling 2026-10-26)** — they are expensive and the max run that day hit the usage limit mid-review. If a landing seems to warrant one (a golden re-pin, a large money-path diff), say so with the reason and ASK; launch only on a yes. `ultra` is a billed cloud review only the grower can launch.

Trivial/mechanical edits (a one-line copy fix, a comment) may skip `/simplify`. Everything touching the solver, payload builder, cost/accounting math, or the unit system should get it. If the user is committing themselves, remind them to run these first.

### Order: working code → `/simplify` → the deep guards

When a change earns **mutation-tested guards** (the money path, a new payload field, anything with three-layer coverage like W1's `channel_sales` or W6's `demand_saturation`), run `/simplify` on the *working* implementation **before** writing those guards, not after.

**Why, measured on W6 (2026-07-30):** the guards were written and all 16 mutations verified, then `/simplify` refactored the code they were written against — the two-branch entry literal collapsed, the basis lookup moved to `annual_rows`, `atCapWks` became `weeksAtCap.length`. Every mutation pattern had to be re-derived and both suites re-run, and that second pass surfaced **four more inert guards**. A whole cycle, avoidable purely by ordering.

Sequence that works:

1. Reproduce and **measure** the defect (see the Verify-first rule below).
2. Make it work. Enough tests to know it works — not the full guard set.
3. **`/simplify`** — let it move the code while moving it is still cheap.
4. *Then* write the deep guards and mutation-test them, against code that has settled.
5. Browser QA **last**, after all edits. Re-verifying after each refactor is the same waste in a slower loop.
   **Before asking the grower to look, run `node scripts/screenshot_form.mjs` and READ the PNGs** — jsdom has
   no layout, and three layout defects reached the grower in one pass (2026-10-27) that a screenshot shows
   in seconds (a stretched checkbox, a clipped label, a heading that lost its grid span).
6. `/code-review` before landing.

Not a reason to defer guards indefinitely: step 2 still needs enough coverage that step 3 cannot break the thing silently. The rule is about *when the expensive, mutation-verified layer* gets built, not about writing tests late.

### Mutation testing — where it earns its cost, and how to keep it fast (grower ruling 2026-10-25)

Mutations rarely find a bug in the code; they find **guards that cannot fail** (W6's four inert guards, the overtime cap, the toy's "annual floor counts the perennial", a deliver contract's dead price box). That is worth paying for where a green suite would otherwise mean nothing — and only there.

- **App money path** (solver, payload fields, cost/accounting math, units): mutation-test, once, after `/simplify`.
- **Toy model:** only when a new verifier/sheet check is added, and keep it to ~5–8 targeted mutants. The toy already has an independent second derivation (sheet = simulator = LP to the cent).
- **Docs, UI copy, mechanical edits:** none.
- **Keep it fast:** run each mutant against ONLY the test(s) written to catch it (seconds, not a 7-minute suite), in parallel, each in its own repo copy (never mutate the real tree — an interrupted run then cannot leave a mutant behind). Run the full suite only to confirm a survivor.
- **After `/code-review` fixes:** re-run only the mutants that touch changed code, never the whole set.
- **Review depth by stakes:** `/code-review medium` for toy and doc changes; `high` for the app money path and branch landings. `max`/`ultra` only when proposed with a reason and approved by the grower (ruling 2026-10-26).

### Verify first, and verify twice when the fix looks like one line

A backlog entry that names the fix is a hypothesis, not a spec. W6's entry said "swap the numerator, the honest one now exists" — true, and shipping only that would have replaced one wrong number with another (Garlic/Farmers Market reads 50% on the annual basis while its weekly cap binds in every week it sells). The first measurement confirmed the defect; the **second** measurement, on a different axis, is what showed the prescribed fix was also wrong. Measure the axis the fix does *not* mention.

---

## Files

| File | Description |
|------|-------------|
| `Group 5_Baby Model_Final (2).xlsx` | Original Excel model with Solver. Sheets: Summary, Model, Fact Sheet, Appendix 1, Appendix 2 |
| `farm_optimization (1).ipynb` | Python notebook replicating the Excel Solver using `scipy.optimize.milp` |

---

## Model Architecture

### Decision Variables (28 total)
- **14 continuous** `x[i]` ∈ [0, 1]: land fraction allocated to succession i
- **14 binary** `y[i]` ∈ {0, 1}: plant succession i (yes/no)

### Crops & Successions
| Crop | # Successions | Crop Cycle |
|------|--------------|------------|
| Spinach | 5 (#1–#5) | 3 months: Plant→Grow→Harvest |
| Cucumbers | 3 (#1–#3) | 3 months: Plant→Grow→Harvest |
| Sweet Corn | 2 (#1–#2) | 4 months: Plant→Grow→Grow→Harvest |
| Napa Cabbage | 2 (#1–#2) | 4 months: Plant→Grow→Grow→Harvest |
| Hot Peppers | 1 (#1) | 7 months: Plant→Grow×3→Harvest×3 |
| Garlic | 1 (#1) | 7 months: Plant→Grow×5→Harvest |

### Objective Function
Maximize:
`Σ (n_harvests × land × yield/acre × avg_price × 1.04 − variable_costs) × x[i] − fixed_cost`

The `1.04` factor encodes the 80/20 channel mix (80% base price + 20% at 120% premium = 1.04× average).

### Constraints (7 types, 69 rows total)
1. **Land** (12): Monthly Σ x[i] ≤ 1 (100% of 150 acres)
2. **Labor** (12): Monthly labor hours ≤ seasonal availability (1,280–7,680 hrs/month)
3. **Water** (12): Monthly water ≤ min(catchment, 15,000 L × 10)
4. **Harvest Storage** (12): Monthly harvest volume ≤ 24,000 m³
5. **Annual Demand** (6): Per-crop annual yield ≤ 11× monthly demand cap
6. **Crop Diversity** (14): `x[i] ≤ y[i] × (diversity_limit / num_successions)`
7. **Budget** (1): Fixed + variable costs ≤ $3,000,000

### Fixed Costs (Annual)
| Component | Formula | Value |
|-----------|---------|-------|
| Harvest Storage | 24,000 m³ × $2/m³ × 11 months | $528,000 |
| Water Storage | 15,000 L × $0.002/L × 11 | $330 |
| Irrigation | 150 acres × $175/acre × 11 | $288,750 |
| Equipment Storage | 30,000 m³ × $2/m³ × 11 | $660,000 |
| Fuel Storage | 750 L × $0.20/L × 11 | $1,650 |
| Machinery | $2,600/month × 11 | $28,600 |
| **Total** | | **$1,507,330** |

### Variable Costs (per unit x[i], scaled by total land = 150 acres)
- Seed cost (once, at planting phase)
- Water cost ($0.002/liter)
- Fertilizer ($2.00/lb)
- Packaging & SG&A (weighted avg $/lb × yield)
- Fuel ($1.00/liter)
- Seasonal labor ($20.00/hr)

---

## Verified Results

All 14 succession land fractions, financials, and constraint values match the Excel Solver solution exactly (differences < $0.01 due to floating-point rounding):

| Metric | Python (scipy.milp) | Excel Solver |
|--------|---------------------|--------------|
| Total Revenue | $9,080,159.17 | $9,080,159.16 |
| Total Variable Cost | $1,365,116.10 | $1,365,116.09 |
| Total Fixed Cost | $1,507,330.00 | $1,507,330.00 |
| Total Cost | $2,872,446.10 | $2,872,446.09 |
| **Total Profit** | **$6,207,713.07** | **$6,207,713.07** |

### Optimal Planting Plan
| Succession | Land Fraction | Acres |
|-----------|--------------|-------|
| Spinach #1 | 0.1108 | 16.6 |
| Spinach #2 | 0.1600 | 24.0 |
| Spinach #3 | 0.0000 | 0 (not planted) |
| Spinach #4 | 0.1264 | 18.9 |
| Spinach #5 | 0.0550 | 8.2 |
| Cucumbers #1 | 0.1000 | 15.0 |
| Cucumbers #2 | 0.1000 | 15.0 |
| Cucumbers #3 | 0.0949 | 14.2 |
| Sweet Corn #1 | 0.0000 | 0 (not planted) |
| Sweet Corn #2 | 0.0949 | 14.2 |
| Napa Cabbage #1 | 0.0949 | 14.2 |
| Napa Cabbage #2 | 0.1182 | 17.7 |
| Hot Peppers #1 | 0.2102 | 31.5 |
| Garlic #1 | 0.4000 | 60.0 |

---

## User-Configurable Parameters (refactored 2026-03-10)

All parameters are now exposed as globals in **Section 3** and as keyword arguments on `solve_farm_optimization()`. Nothing is hard-coded inside the function body. Parameters are organized into 7 subsections:

| Section | Parameters |
|---------|-----------|
| 3A — Farm Infrastructure | `TOTAL_LAND`, `BUDGET`, `HARVEST_STORAGE_CAP`, `WATER_STORAGE`, `EQUIP_STORAGE`, `FUEL_STORAGE` |
| 3B — Fixed Cost Unit Rates | `RATE_HARVEST_STORAGE`, `RATE_WATER_STORAGE`, `RATE_IRRIGATION`, `RATE_EQUIP_STORAGE`, `RATE_FUEL_STORAGE`, `RATE_MACHINERY`, `OPERATING_MONTHS` |
| 3C — Variable Cost Unit Rates | `COST_WATER_PER_L`, `COST_FERT_PER_LB`, `COST_LABOR_PER_HR`, `COST_FUEL_PER_L` |
| 3D — Monthly Availability | `AVAILABLE_WATER_CATCHMENT` (12-element array), `AVAILABLE_LABOR` (12-element array) |
| 3E — Crop Parameters | `YIELD_PER_ACRE`, `CROP_SIZE_M3_PER_LB`, `SEED_REQ_PER_ACRE`, `SEED_COST_PER_LB`, `CROP_DIVERSITY`, `MONTHLY_DEMAND`, `WEIGHTED_AVG_PRICE`, `WEIGHTED_AVG_PKG`, `CHANNEL_PREMIUM` |
| 3F — Resource Usage Per Phase | `LABOR_PLANT/GROW/HARV`, `WATER_PLANT/GROW/HARV`, `FERT_PLANT/GROW/HARV`, `FUEL_PLANT/GROW/HARV` |
| 3G — Succession Calendar | `SUCCESSIONS` (list of dicts with name, crop index, months, phases) |

To run a scenario without changing Section 3: `solve_farm_optimization(budget=2_000_000)` — any unspecified parameter uses the Section 3 global default.

---

## Solver Details

- **Library**: `scipy.optimize.milp` (wraps HiGHS MILP solver)
- **Problem type**: Mixed-Integer Linear Program (MILP)
- **Variables**: 28 (14 continuous + 14 binary)
- **Constraints**: 69 linear inequality constraints
- **Status**: Optimal (HiGHS Status 7)
- **Excel equivalent**: OpenSolver/Solver with Simplex LP + binary integer variables

---

## Notebook Structure

| Section | Purpose |
|---------|---------|
| 1 — Install Dependencies | pip installs for Colab/local |
| 2 — Imports | numpy, pandas, scipy, matplotlib |
| 3 — Parameters | All fixed inputs from Fact Sheet |
| 4 — Solver Function | `solve_farm_optimization()` — parameterized, self-contained MILP |
| 5 — Solve and Verify | Run solver, assert results match Excel within 1% |
| 6 — Results | Detailed tables + profit waterfall + land heatmap |
| 7 — Sensitivity Analysis | Budget sweep ($2M–$5.25M) and land sweep (50–300 acres) |

---

## Key Assumptions (from Excel Summary sheet)

- Fixed yields, no crop failure
- Revenue = yield × avg_price × 1.04 (80/20 channel split)
- Yearly demand cap (not monthly — simplified)
- Fixed infrastructure costs regardless of what is planted
- Binary planting decisions (planted or not, no partial activation)
- Each crop has a rigid 3–7 month cycle with fixed phase months

---

## How to Run

```bash
pip install scipy numpy pandas matplotlib openpyxl
jupyter notebook "farm_optimization (1).ipynb"
```

Or on Google Colab: upload the notebook and run all cells (installs happen automatically in Section 1).
