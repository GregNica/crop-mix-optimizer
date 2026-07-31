# Farm Crop-Mix Optimization — Project README

## What This Project Does

This project answers one question: **what should a farm grow, and when, to maximize annual profit?**

A team (Group 5) built an Excel spreadsheet with Microsoft Solver to figure this out. That model was then translated into a Python solver, and finally into a **full web application** (`index.html`) that any farmer can use without any coding or installation.

---

## Project Evolution

| Phase | Artifact | Status |
|-------|----------|--------|
| Phase 0 | `Group 5_Baby Model_Final (2).xlsx` — original Excel Solver model | Reference only (see Historical Files) |
| Phase 1 | `farm_optimization (1).ipynb` — Python notebook replicating the Excel model | Reference only (see Historical Files) |
| Phase 2 | 52-week generalized model with MC | Superseded by `farm_v2/` + the web app; the notebook was retired 2026-07-31 (see below) |
| Phase 3–4 | `index.html` — full web application | **Current deliverable** |

---

## Current Deliverable — `index.html`

A self-contained single-file web application. No installation, no server required in principle (see below). The farmer configures their crops, costs, water, and labor; the app runs a Mixed-Integer Linear Program (MILP) and returns an optimal planting plan with sensitivity analysis and Monte Carlo risk simulation.

### How to run

**Recommended (local server, avoids browser file:// restrictions):**
```bash
python3 -m http.server 3000
# then open http://localhost:3000 in Chrome or Edge
```

**WSL2 users:** Run the command above in a WSL2 terminal. Chrome/Edge on Windows will reach `localhost:3000` automatically.

### What it includes

- Guided parameter walkthrough with progressive disclosure (start simple, add detail as needed)
- Benchmark defaults with source provenance (UC Cooperative Extension, USDA)
- Optimal planting schedule output with a week-by-week planting calendar and profit waterfall
- Sensitivity analysis (labor, credit line, binding constraint sweep)
- Monte Carlo simulation — upload historical yield/price/demand data; app computes mean and variability for P10/P50/P90 forecast
- Historical rainfall upload for empirical weather variability
- Sales-spread window per crop (shelf-stable crops like garlic can sell across multiple post-harvest weeks)
- Depreciation-based fixed cost model (harvest storage, water tank, irrigation, equipment, fuel storage)
- Cash flow constraint with opening cash and credit line

---

## `farm_v2/` — Python Solver Source

The `farm_v2/` directory contains the Python solver that powers the web app. The solver code runs **inside the browser** via [Pyodide](https://pyodide.org) (Python compiled to WebAssembly) — the `farm_v2/` source files are embedded as strings inside `index.html` at build time.

### Relationship between `farm_v2/` and `index.html`

```
farm_v2/solver.py   ←→   embedded in index.html as FARM_V2_FILES["farm_v2/solver.py"]
farm_v2/utils/*.py  ←→   embedded in index.html as FARM_V2_FILES["farm_v2/utils/..."]
```

**Important:** These are kept in sync manually. If you modify solver logic:
1. Edit the source file in `farm_v2/`
2. Copy the updated content into the corresponding string inside `FARM_V2_FILES` in `index.html`
3. Test via the web app

Failing to update both will cause `farm_v2/` and `index.html` to diverge silently — the web app will use the old embedded version while `farm_v2/` shows the new code.

### Running the solver standalone (without the web app)

```bash
pip install scipy numpy pandas
python3 -c "
from farm_v2.solver import solve_farm_v2
# see farm_v2/solver.py for full parameter list
"
```

---

## The Model

This is a **Mixed-Integer Linear Program (MILP)**:
- **Continuous variables** `x[i]`: fraction of farm land allocated to each succession
- **Binary variables** `y[i]`: whether to plant a succession at all (yes/no)
- **Sales variables** `v[crop, channel, week]`: lbs sold per crop per channel per week
- **Objective**: maximize annual profit
- **Constraints**: land, water, labor, harvest storage, weekly demand caps, crop diversity, cash flow

The solver is `scipy.optimize.milp` (wraps the open-source HiGHS solver). Typical solve time: under 5 seconds.

---

## Historical Files

These files are not tracked in git but exist locally as reference artifacts. They document the earlier phases of the project.

| File | What It Is |
|------|-----------|
| `Group 5_Baby Model_Final (2).xlsx` | Original Excel model with Solver (Group 5 class project) |
| `farm_optimization (1).ipynb` | Phase 1 Python notebook — reproduces Excel model exactly using scipy.milp |
| ~~`farm_optimization_v2.ipynb`~~ | **Retired 2026-07-31.** Recoverable from git history at `48203a8~1`. It carried no saved outputs, so it was only meaningful when RUN — and `build_notebook_v2.py` imported the live solver, so running it produced wrong money as the model moved on: measured $684,000 of wages charted as infrastructure and packaging understated by $71,561. Repair was not one-off (it re-broke on every solver change, with no test or CI), and its March-vintage model predates the inventory core, two storage pools, per-channel sales and committed labour. The web app is the deliverable; `tests/test_golden_farm.py` does the money verification it was standing in for |
| ~~`build_notebook_v2.py`~~ | Retired with it — the generator |
| ~~`test_notebook_v2.py`~~ | Retired with the notebook it ran |
| `tests/` | Phase 2 unit tests for the Python solver modules |
| `validation/` | Validation runs comparing notebook output to Excel |

These are intentionally not committed to keep the repository clean. The Phase 1 notebook verified Python results match Excel to within $0.01 (< 0.0001%) on all metrics. That verification is the foundation the web app builds on.

---

## Key Assumptions & Limitations

- Fixed yields per acre — no crop failure, weather damage, or pest pressure modeled in the deterministic solve (Monte Carlo handles variability)
- Revenue accrues in the week sales occur — no receivables lag
- Harvest storage constraint applies at harvest week; sales-spread crops must have adequate storage capacity set
- Land costs (rent/mortgage) default to $0 — users with leased land should enter their actual weekly cost
- No crop rotation or multi-year soil health modeling
- Labor is treated as a cost, not a decision variable (Phase 5 scope)

---

## Technical Documentation

- `CLAUDE.md` — detailed model architecture, constraint definitions, solver parameter reference
- `SPEC_v2.md` — full specification for the 52-week generalized model (Phase 2)
- `CLAUDE_PROMPT_PACK.md` — complete development history, phase-by-phase implementation prompts
