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

A single-page web application. The farmer configures their crops, costs, water, and labor; the app runs a Mixed-Integer Linear Program (MILP) and returns an optimal planting plan with sensitivity analysis and Monte Carlo risk simulation. **The solve is 100% client-side** (Pyodide/WebAssembly) — the server never solves — but the app ships as a **Cloudflare Worker** that serves the page, gates login, and handles `/api/*`. See `SETUP.md`.

### How to run

**The real app — use this:**
```bash
npm install
npm run dev          # wrangler dev → http://localhost:8787
```
That is the Worker: static app + login gate + `/api/*`. Check `http://localhost:8787/api/health` returns `{"ok":true,...}`.

**Static-only fallback**, for solver/UI work when you don't need the API:
```bash
python3 -m http.server 3000
# then open http://localhost:3000/public/index.html
```
⚠️ This serves the file directly, so the **login gate is bypassed and every `/api/*` call 404s**. The solver is client-side, so optimization, charts and Monte Carlo all work — but this is not the app as it ships. Don't QA auth, saved plans or the chatbot here.

⚠️ **Check for a stale server before QA:** `ss -ltnp | grep 878`. A leftover `wrangler dev` holding 8787 will push a fresh one to 8788, and opening the habitual URL then tests old code. One server only.

**WSL2 users:** Run these in a WSL2 terminal. Chrome/Edge on Windows reach `localhost` automatically.

### What it includes

- Guided parameter walkthrough with progressive disclosure (start simple, add detail as needed)
- Benchmark defaults with source provenance (UC Cooperative Extension, USDA)
- Optimal planting schedule output with a week-by-week planting calendar and profit waterfall
- Sensitivity analysis (labor, credit line, binding constraint sweep)
- Monte Carlo simulation — upload historical yield/price/demand data; app computes mean and variability for P10/P50/P90 forecast
- Historical rainfall upload for empirical weather variability
- Per-crop **shelf life** with weekly storage shrink (shelf-stable crops like garlic sell across many post-harvest weeks; `sales_spread_weeks` is the deprecated predecessor and still imports 1:1)
- Depreciation-based fixed cost model (harvest storage, water tank, irrigation, equipment, fuel storage)
- Cash flow constraint with opening cash and credit line

---

## `farm_v2/` — Python Solver Source

The `farm_v2/` directory contains the Python that powers the web app — the MILP solver, the JSON-in/JSON-out adapter every caller converges on, and the chart renderer. It runs **inside the browser** via [Pyodide](https://pyodide.org) (Python compiled to WebAssembly): all ten `farm_v2/*.py` files are embedded in `index.html` as one JSON blob, `FARM_V2_FILES`.

### Relationship between `farm_v2/` and `index.html`

```
farm_v2/{solver,adapter,charts,validate}.py  ←→  embedded in index.html as
farm_v2/utils/{calendar,demand,labor,water}.py    FARM_V2_FILES["farm_v2/<path>.py"]
```

**Do NOT hand-edit the blob.** After changing anything under `farm_v2/`:
```bash
python3 scripts/sync_solver_blob.py      # rewrites the blob from disk
npm run test:blob && npm run test:payload # verifies embed == disk, and the golden payload
```
The script owns the escaping (every `<` becomes `\u003c`, so a `</script` in a docstring cannot close the inline `<script>` and blank the page) — copying content in by hand loses that.

Failing to sync makes `farm_v2/` and `index.html` diverge **silently**: pytest runs the fresh code while the browser runs the stale blob. `npm run test:blob` is the guard, and it is fail-closed.

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
- **Inventory variables** `inv[crop, week]`, `waste[crop, week]`: lbs held and lbs discarded
- **Constraints**: land, labor, water (with an on-farm tank that actually banks), an inventory balance with shelf-life and per-week shrink, two capped storage pools (refrigerated + ambient), weekly *and* annual demand caps, crop diversity, committed acres, planting/harvest throughput, and a weekly cash floor

The solver is `scipy.optimize.milp` (wraps the open-source HiGHS solver). A single solve of the demo farm is ~3.5 s in CPython and **~12 s in the browser** (wasm costs roughly 3.5x — measured, not extrapolated). Monte Carlo is 100 full solves, so budget ~20 minutes for a 100-draw run.

---

## Historical Files

Reference artifacts from the earlier phases. **All of these are tracked in git** — the repo keeps its own provenance.

| File | What It Is |
|------|-----------|
| `Group 5_Baby Model_Final (2).xlsx` | Original Excel model with Solver (Group 5 class project) |
| `farm_optimization (1).ipynb` | Phase 1 Python notebook — reproduces Excel model exactly using scipy.milp |
| ~~`farm_optimization_v2.ipynb`~~ | **Retired 2026-07-31.** Recoverable from git history at `48203a8~1`. It carried no saved outputs, so it was only meaningful when RUN — and `build_notebook_v2.py` imported the live solver, so running it produced wrong money as the model moved on: measured $684,000 of wages charted as infrastructure and packaging understated by $71,561. Repair was not one-off (it re-broke on every solver change, with no test or CI), and its March-vintage model predates the inventory core, two storage pools, per-channel sales and committed labour. The web app is the deliverable; `tests/test_golden_farm.py` does the money verification it was standing in for |
| ~~`build_notebook_v2.py`~~ | Retired with it — the generator |
| ~~`test_notebook_v2.py`~~ | Retired with the notebook it ran |
| `tests/` | Phase 2 unit tests for the Python solver modules |
| `validation/` | Validation runs comparing notebook output to Excel |

The Phase 1 notebook verified Python results match Excel to within $0.01 (< 0.0001%) on all metrics. That verification is the foundation the web app builds on. The struck-through rows above are the only ones actually removed; they are recoverable from git history at the commits named.

---

## Key Assumptions & Limitations

- Fixed yields per acre — no crop failure, weather damage, or pest pressure modeled in the deterministic solve (Monte Carlo handles variability)
- Revenue accrues in the week sales occur — no receivables lag
- Storage is measured as **room occupancy** — opening stock plus the whole of that week's harvest, counted before any of it ships — so it sizes a cooler rather than reporting what sleeps in it. Crops flagged `cold_storage: false` (cured alliums, winter squash) use a separate, also-capped ambient pool
- Land costs (rent/mortgage) default to $0 — users with leased land should enter their actual weekly cost
- No crop rotation or multi-year soil health modeling
- Labor capacity is a constraint and wages are a **committed** weekly cost — every listed worker is paid for their stated hours whether the crops need them or not, so a marginal crop hour is free and is rationed by capacity rather than by price. Hours bought *beyond* the crew (overtime, hired hands) **are** decision variables, priced separately: overtime at your crew's blended rate × a multiplier, hire at an entered market wage

---

## Technical Documentation

- `CLAUDE.md` — detailed model architecture, constraint definitions, solver parameter reference
- `SPEC_v2.md` — full specification for the 52-week generalized model (Phase 2)
- `CLAUDE_PROMPT_PACK.md` — complete development history, phase-by-phase implementation prompts
