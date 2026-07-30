# Farm Optimization Model — v2 Technical Specification

**Status:** Design complete, ready for implementation
**Supersedes:** `farm_optimization (1).ipynb` (v1, 12-month monthly model)
**Date:** 2026-03-10

---

## 1. Overview

v2 expands the farm crop-mix MILP from a 12-month monthly model with 6 fixed crops and a single blended price to a 52-week weekly model with:

- **User-defined crops** — any number, defined by days-to-maturity and seasonality windows; succession slots auto-generated at weekly spacing
- **User-defined sales channels** — any number, named by the user, with per-channel pricing and demand caps
- **Flexible water model** — rainfall (historical weekly averages by location), catchment, well, and optional city (purchased) water
- **Detailed labor model** — salaried and hourly year-round and seasonal employees with wages, benefits, overtime, and piece-rate harvest labor
- **Channel sales optimization** — optimizer decides how to allocate each crop's weekly harvest across channels to maximize revenue
- **Equipment proxy constraints** — max plantable and max harvestable acres per week

Grade A/B differentiation is **deferred to v2.1**. The 1.04 channel premium multiplier from v1 is **removed**. Revenue is computed directly from channel sales variables.

---

## 2. Assumptions (to be displayed prominently in the app)

1. **Fixed yields** — yield per acre per harvest week is a constant input. No weather-driven yield variability, no crop failure.
2. **Transplants available on demand** — transplanted crops are assumed purchased from nurseries as needed. No propagation or greenhouse modeling.
3. **Weekly allotment water model** — water availability is a weekly flow, not an inventory. Surplus in one week cannot carry to the next.
4. **No harvest inventory carryover** — what is harvested in a given week must be sold or is lost. The model treats harvest storage as temporary weekly staging, not multi-week cold storage.
5. **Sale occurs in harvest week** — revenue is booked in the same week the crop is harvested. No market lag.
6. **Unsold harvest is waste** — harvest not allocated to a channel earns no revenue and incurs no additional cost.
7. **No demand in unspecified weeks** — for varying weekly demand caps, any week without an explicit range has zero demand for that channel/crop combination. The optimizer will not schedule harvests for those weeks.
8. **Labor is fungible** — any worker can perform any task. The constraint is total labor hours, not position-specific allocation.
9. **Piece-rate labor treated as variable packaging cost** — piece-rate harvest workers (paid per lb) are modeled as an additional $/lb cost on harvest output, equivalent to packaging cost.
10. **Crop diversity constraint as rotation proxy** — the constraint that limits simultaneous land use per crop is a simplified proxy for crop rotation. True rotation management (preventing same crop family in same field in consecutive seasons) is not modeled.
11. **No equipment-specific limits** — equipment availability is proxied by max plantable and max harvestable acres per week. Farmers must separately account for their specific equipment fleet.
12. **Rainfall is historical weekly average** — water model uses historical average weekly rainfall for the farm location, fetched at model setup time. Not live or forecast data.
13. **Catchment and rainfall offset are fixed efficiency rates** — catchment efficiency (fraction of rain reaching storage) and field rainfall offset fraction (fraction of field rainfall reducing irrigation need) are hard-coded defaults, not user inputs.
14. **No year-boundary crops** — crops must complete their full cycle within weeks 1–52. Garlic-type overwintering crops are handled by configuring a season window starting at week 1 (implying fall planting in the prior year is treated as the initial state).
15. **No soil health or multi-year planning** — the model maximizes annual profit only. Soil depletion, crop rotation benefits, and year-over-year effects are not modeled.
16. **Minimum viable acreage enforced** — if a succession is planted, it must meet a user-configured minimum acreage per crop. Fractions below this threshold are not allowed.

---

## 3. Time Model

- **Planning horizon:** 52 weeks (weeks 1–52, where week 1 = first week of January)
- **Week definition:** ISO week numbering; week 1 is the week containing January 4th
- **Utility:** A `week_of_year(date_string)` helper converts "MM-DD" to week number 1–52

---

## 4. Decision Variables

### 4A. Succession land variables
For each auto-generated succession slot `i`:

| Variable | Type | Bounds | Meaning |
|----------|------|--------|---------|
| `x[i]` | Continuous | [0, 1] | Fraction of total land allocated to succession i |
| `y[i]` | Binary | {0, 1} | 1 if succession i is planted, 0 otherwise |

### 4B. Channel sales variables
For each crop `c`, channel `ch`, and week `w`:

| Variable | Type | Bounds | Meaning |
|----------|------|--------|---------|
| `v[c, ch, w]` | Continuous | ≥ 0 | Pounds sold to channel ch from crop c in week w |

### 4C. City water variable (only if city water is enabled)
For each week `w`:

| Variable | Type | Bounds | Meaning |
|----------|------|--------|---------|
| `city_water[w]` | Continuous | ≥ 0 | Liters of city water purchased in week w |

Note: this is not a user decision — it is derived by the solver from the water deficit. When city water is enabled, the solver will use as little as needed (it adds to cost).

### 4D. Overtime variable (only if overtime is configured)
For each week `w`:

| Variable | Type | Bounds | Meaning |
|----------|------|--------|---------|
| `overtime[w]` | Continuous | ≥ 0 | Overtime hours worked in week w above regular capacity |

---

## 5. Parameters — Complete Input Schema

### 5A. Farm Infrastructure
```python
TOTAL_LAND            # acres — total available farm land
BUDGET                # $/year — total annual budget constraint
HARVEST_STORAGE_CAP   # m³ — weekly staging/cold storage capacity
EQUIP_STORAGE         # m³ — equipment & general storage (for fixed cost)
FUEL_STORAGE          # liters — fuel tank capacity (for fixed cost)
```

### 5B. Fixed Cost Unit Rates
```python
OPERATING_WEEKS          # weeks/year farm incurs infrastructure costs (typically 48-52)
RATE_HARVEST_STORAGE     # $/m³/week
RATE_WATER_STORAGE       # $/liter/week  (for any on-farm water tank)
RATE_IRRIGATION          # $/acre/week   (irrigation system amortized)
RATE_EQUIP_STORAGE       # $/m³/week
RATE_FUEL_STORAGE        # $/liter/week
RATE_MACHINERY           # $/week        (fixed machinery lease or amortization)
```

### 5C. Water Configuration
```python
# Location for historical rainfall lookup
FARM_LOCATION = {
    "city":    "...",
    "state":   "...",
    "country": "..."
}

# Pre-fetched at setup time — 52-element array, liters/acre/week
# (built-in historical weekly average rainfall for the farm location)
RAINFALL_WEEKLY_L_PER_ACRE  # [52]

# Hard-coded defaults (not user input):
RAINFALL_OFFSET_FRACTION = 0.65    # fraction of field rainfall that reduces irrigation need
CATCHMENT_EFFICIENCY     = 0.85    # fraction of catchment rainfall that reaches storage

# Water source selection (user chooses which sources are available)
CATCHMENT_ENABLED          # bool
CATCHMENT_SURFACE_AREA     # m² — roof/pond/pad area draining to storage tank
WATER_STORAGE_CAPACITY     # liters — catchment tank capacity

WELL_ENABLED               # bool
WELL_WEEKLY_CAP            # liters/week — constant year-round
WELL_COST_PER_L            # $/liter

CITY_WATER_ENABLED         # bool
CITY_WATER_COST_PER_L      # $/liter (variable, above free-water threshold)
CITY_WATER_FIXED_FEE_PER_WEEK  # $/week (standing connection fee, if enabled)
```

**Derived weekly water supply (computed before solve, not decision variables):**
```
catchment_supply[w] = RAINFALL_WEEKLY[w] × CATCHMENT_SURFACE_AREA × CATCHMENT_EFFICIENCY
well_supply[w]      = WELL_WEEKLY_CAP  (if well enabled, else 0)
free_water[w]       = catchment_supply[w] + well_supply[w]
```

### 5D. Labor Configuration
```python
YEAR_ROUND_EMPLOYEES = [
    {
        "position":        str,
        "count":           int,
        "type":            "salary" | "hourly",
        "wage":            float,   # $/year if salary; $/hour if hourly
        "hours_per_week":  int,     # standard weekly hours (used for capacity + cost)
        "benefits_pct":    float,   # e.g., 0.25 for 25% overhead on top of wage
    },
    ...
]

SEASONAL_EMPLOYEES = [
    {
        "position":              str,
        "count":                 int,
        "type":                  "FT" | "PT",
        "start_week":            int,    # week they become available
        "end_week":              int,    # last week they are available
        "wage":                  float,  # $/hour
        "hours_per_week":        int,    # standard weekly hours
        "benefits_pct":          float,
        "min_guaranteed_hours":  int,    # ⚠️ ACCEPTED AND IGNORED since W12 (2026-07-31): committed wages already pay count x hours_per_week, which is >= count x min(min_guaranteed, hours) for every input, so it can never bind
        "piece_rate_per_lb":     float,  # optional; $/lb harvested (treated as packaging cost)
    },
    ...
]

# Overtime (applies to hourly employees only)
OVERTIME_ENABLED         # bool
OVERTIME_THRESHOLD_HRS   # hours/week before overtime kicks in (typically 40)
OVERTIME_RATE_MULTIPLIER # e.g., 1.5 for time-and-a-half
```

**Derived weekly labor capacity and cost (computed before solve):**
```
regular_capacity[w]  = sum of (count × hours_per_week) for all hourly employees available in week w
salaried_capacity[w] = sum of (count × hours_per_week) for all salaried employees
total_capacity[w]    = regular_capacity[w] + salaried_capacity[w]

salaried_weekly_cost = sum of (count × annual_wage × (1 + benefits_pct) / 52) for salaried employees
                       → goes into FIXED_LABOR_COST (added to infrastructure fixed costs)

hourly_blended_rate[w] = weighted average $/hour across all hourly employees available in week w
                          (weighted by count × hours_per_week, including benefits)
```

### 5E. Equipment Proxy Constraints
```python
MAX_PLANT_ACRES_PER_WEEK    # acres — max land that can be planted in any single week
MAX_HARVEST_ACRES_PER_WEEK  # acres — max land that can be harvested in any single week
```

### 5F. Sales Channels
User defines any number of named channels:
```python
CHANNELS = [
    {
        "name":  str,   # e.g., "Wholesale", "Farmers Market", "Restaurant B2B"
    },
    ...
]
```

### 5G. Crop Definitions
```python
CROPS = [
    {
        # Identity
        "name":               str,

        # Cycle
        "days_to_maturity":   int,    # primary input; total_weeks = ceil(days / 7)
        "planting_weeks":     int,    # weeks in planting phase (minimum 1)
        "harvest_weeks":      int,    # weeks in harvest phase (minimum 1)
        # growing_weeks is derived: total_weeks - planting_weeks - harvest_weeks
        # validation: planting_weeks + harvest_weeks < total_weeks

        # Season windows — list of {start, end} as "MM-DD" strings
        # Successions auto-generated at weekly spacing for each window
        # Succession slot i starts at start_week, i+1 starts at start_week+1, etc.
        # Only slots where start_week + total_weeks - 1 ≤ end_week are generated
        "seasons": [
            {"start": "MM-DD", "end": "MM-DD"},
            ...
        ],

        # Land
        "min_acreage_if_planted":  float,  # acres — minimum viable plot size
        "crop_diversity_max":      float,  # fraction of TOTAL_LAND; at any week, total
                                           # planted land for this crop ≤ this fraction

        # Yield and storage
        "yield_per_acre":          float,  # lbs/acre/harvest-week
        "crop_size_m3_per_lb":     float,  # m³/lb — for harvest storage constraint

        # Seed / transplant cost
        "planting_type":           "seed" | "transplant",
        "seed_transplant_cost_per_acre":  float,  # $/acre, incurred once at planting

        # Resource usage per phase per week (all per acre)
        "labor_plant":  float,  # hrs/acre/week
        "labor_grow":   float,
        "labor_harv":   float,
        "water_plant":  float,  # liters/acre/week (total crop water need; rainfall offset applied)
        "water_grow":   float,
        "water_harv":   float,
        "fert_plant":   float,  # lbs/acre/week
        "fert_grow":    float,
        "fert_harv":    float,
        "fuel_plant":   float,  # liters/acre/week
        "fuel_grow":    float,
        "fuel_harv":    float,

        # Per-channel market data (one entry per channel, by channel name)
        "channels": {
            "<channel_name>": {
                "price_per_lb":           float,  # $/lb selling price
                "packaging_cost_per_lb":  float,  # $/lb (incl. piece-rate if applicable)
                "demand_cap_type":        "annual" | "weekly_flat" | "weekly_varying",

                # If annual:
                "annual_demand_lbs":      float,

                # If weekly_flat:
                "weekly_demand_lbs":      float,

                # If weekly_varying: list of ranges
                # Weeks not covered by any range → demand = 0 (optimizer will not
                # schedule harvest for this channel/crop in those weeks)
                "demand_ranges": [
                    {"weeks": "W1-W2", "weekly_lbs": float},
                    ...
                ],
            },
            ...
        },

        # Variable cost rates (farm-wide rates set in 5H, but crop-specific fert rate
        # multiplier can be set here if needed — optional override)
    },
    ...
]
```

### 5H. Variable Cost Unit Rates
```python
COST_FERT_PER_LB    # $/lb fertilizer+pesticide
COST_FUEL_PER_L     # $/liter fuel
COST_WELL_PER_L     # $/liter well water (often 0 or near-zero)
# Labor cost is derived from employee configs in 5D
# City water cost is in 5C
# Seed/transplant cost is per-crop in 5G
# Packaging cost is per-channel per-crop in 5G
```

---

## 6. Auto-Generated Succession Calendar

### Algorithm
```
for each crop c:
    total_weeks[c] = ceil(days_to_maturity[c] / 7)
    grow_weeks[c]  = total_weeks[c] - planting_weeks[c] - harvest_weeks[c]
    validate: grow_weeks[c] >= 0

    phases[c] = [0] * planting_weeks[c] +
                [1] * grow_weeks[c]     +
                [2] * harvest_weeks[c]

    for each season window (start_date, end_date):
        start_w = week_of_year(start_date)
        end_w   = week_of_year(end_date)

        for slot_start = start_w to (end_w - total_weeks[c] + 1):
            weeks = list(range(slot_start, slot_start + total_weeks[c]))
            generate succession {
                name:   f"{crop.name} W{slot_start}",
                crop:   c,
                weeks:  weeks,          # list of week numbers (1-indexed)
                phases: phases[c],      # phase for each week in the succession
            }
```

### Succession indexing
All auto-generated successions are collected into a flat list `SUCCESSIONS` ordered by crop then start week. The index `i` into this list is used for `x[i]` and `y[i]`.

---

## 7. Derived Weekly Lookup Tables (computed before solve)

```python
# For each succession i and week w: what phase is succession i in during week w?
# Returns None if succession i is not active in week w
phase_in_week[i][w]  # 0=plant, 1=grow, 2=harvest, None=inactive

# Net water needed from supplemental sources per acre per week
# (crop water requirement minus rainfall offset, floored at 0)
net_water_rate[i][w] = max(0,
    water_by_phase[phase_in_week[i][w]][crop(i)]
    - RAINFALL_WEEKLY[w] * RAINFALL_OFFSET_FRACTION
)

# Labor rate per acre per week for succession i in week w
labor_rate[i][w] = labor_by_phase[phase_in_week[i][w]][crop(i)]

# Free water available per week (pre-computed constant)
free_water[w] = catchment_supply[w] + well_supply[w]

# Demand cap per crop per channel per week (expanded from demand_cap_type)
demand_cap[c][ch][w]  # lbs; 0 for unspecified weeks in weekly_varying mode

# Blended hourly labor cost rate per week (accounting for employee mix)
hourly_labor_rate[w]  # $/hour

# Regular labor capacity per week
labor_capacity[w]     # hours (salaried + hourly, only employees available that week)
```

---

## 8. Constraints

### C1. Land (52 constraints)
For each week `w`:
```
Σ_{i: w in succession_i.weeks} x[i] ≤ 1
```

### C2. Labor (52 constraints)
For each week `w`:
```
Σ_{i: w in succession_i.weeks} x[i] × TOTAL_LAND × labor_rate[i][w] ≤ labor_capacity[w] + overtime[w]
```
If overtime not enabled: `overtime[w]` term is absent and the constraint is a hard cap.

### C3. Water — no city water (52 constraints, only if city water disabled)
For each week `w`:
```
Σ_{i: w in succession_i.weeks} x[i] × TOTAL_LAND × net_water_rate[i][w] ≤ free_water[w]
```

### C3b. Water — city water enabled (52 constraints, if city water enabled)
For each week `w`:
```
city_water[w] ≥ Σ_{i} x[i] × TOTAL_LAND × net_water_rate[i][w] - free_water[w]
city_water[w] ≥ 0
```
(The objective minimizes cost, so city_water[w] will be set to the minimum needed.)

### C4. Harvest storage (52 constraints)
For each week `w`:
```
Σ_{i: harvest phase in week w} x[i] × TOTAL_LAND × yield_per_acre[crop(i)] × crop_size_m3_per_lb[crop(i)] ≤ HARVEST_STORAGE_CAP
```

### C5. Channel sales ≤ harvest (n_crops × 52 constraints)
For each crop `c` and week `w`:
```
Σ_ch v[c, ch, w] ≤ Σ_{i: crop(i)=c, harvest phase in week w} x[i] × TOTAL_LAND × yield_per_acre[c]
```

### C6. Channel sales ≤ demand cap (n_crops × n_channels × 52 constraints)
For each crop `c`, channel `ch`, and week `w`:
```
v[c, ch, w] ≤ demand_cap[c][ch][w]
```

### C7. Production ≤ total market capacity (n_crops × 52 constraints)
For each crop `c` and week `w`:
```
Σ_{i: crop(i)=c, harvest in week w} x[i] × TOTAL_LAND × yield_per_acre[c] ≤ Σ_ch demand_cap[c][ch][w]
```

### C8. Crop diversity — weekly simultaneous land use (n_crops × 52 constraints)
For each crop `c` and week `w`:
```
Σ_{i: crop(i)=c, w in succession_i.weeks} x[i] ≤ crop_diversity_max[c]
```
Note: this replaces the per-succession diversity formula from v1 (which broke down with many auto-generated successions).

### C9. Succession upper bound — binary linkage (n_successions constraints)
For each succession `i`:
```
x[i] ≤ y[i]
```
(Upper bound of 1 from variable bounds; y[i]=0 forces x[i]=0.)

### C10. Minimum acreage if planted (n_successions constraints)
For each succession `i`:
```
x[i] ≥ y[i] × (min_acreage_if_planted[crop(i)] / TOTAL_LAND)
```
Rearranged for MILP: `−x[i] + y[i] × min_frac[crop(i)] ≤ 0`

### C11. Max planting acres per week (52 constraints)
For each week `w`:
```
Σ_{i: planting phase in week w} x[i] × TOTAL_LAND ≤ MAX_PLANT_ACRES_PER_WEEK
```

### C12. Max harvesting acres per week (52 constraints)
For each week `w`:
```
Σ_{i: harvest phase in week w} x[i] × TOTAL_LAND ≤ MAX_HARVEST_ACRES_PER_WEEK
```

### C13. Budget (1 constraint)
```
FIXED_COST + variable_cost_total + city_water_cost + overtime_cost ≤ BUDGET
```
Where:
```
variable_cost_total = Σ_i x[i] × var_cost_coeff[i]

var_cost_coeff[i] = (
    TOTAL_LAND × seed_transplant_cost_per_acre[crop(i)]        # once, at planting
  + Σ_{w in succession_i.weeks} TOTAL_LAND × net_water_rate[i][w] × COST_WELL_PER_L
  + Σ_{w} TOTAL_LAND × fert_rate[i][w] × COST_FERT_PER_LB
  + Σ_{w} TOTAL_LAND × fuel_rate[i][w] × COST_FUEL_PER_L
  + Σ_{w} TOTAL_LAND × labor_rate[i][w] × hourly_labor_rate[w]
)
# Note: packaging cost is handled through channel sales variables (see objective)
```

```
FIXED_COST = (
    infrastructure fixed costs (storage, irrigation, equipment, fuel tank, machinery)
  + FIXED_LABOR_COST (salaried employees × 52 weeks)
  + CITY_WATER_FIXED_FEE_PER_WEEK × OPERATING_WEEKS  (if city water enabled)
)
```

### C14. Overtime derived constraint (52 constraints, if overtime enabled)
For each week `w`:
```
overtime[w] ≥ labor_used[w] - labor_capacity_hourly_only[w]
overtime[w] ≥ 0
```

---

## 9. Objective Function

**Maximize:**
```
  Σ_{c, ch, w} v[c, ch, w] × (price_per_lb[c][ch] - packaging_cost_per_lb[c][ch])
- Σ_i x[i] × var_cost_coeff[i]
- Σ_w city_water[w] × CITY_WATER_COST_PER_L       (if city water enabled)
- Σ_w overtime[w] × hourly_labor_rate[w] × (OVERTIME_RATE_MULTIPLIER - 1)
                                                    (if overtime enabled)
- FIXED_COST
```

Equivalently (since FIXED_COST is constant), the solver minimizes the negated variable portion.

---

## 10. Variable Count Estimates (example: 10 crops, 3 channels, ~20 successions/crop)

| Variable group | Count |
|----------------|-------|
| x[i] continuous succession | ~200 |
| y[i] binary succession | ~200 |
| v[c, ch, w] channel sales | 10 × 3 × 52 = 1,560 |
| city_water[w] | 52 |
| overtime[w] | 52 |
| **Total** | **~2,064** |

## 11. Constraint Count Estimates

| Constraint group | Count |
|------------------|-------|
| C1 Land | 52 |
| C2 Labor | 52 |
| C3/C3b Water | 52 |
| C4 Harvest storage | 52 |
| C5 Sales ≤ harvest | 10 × 52 = 520 |
| C6 Sales ≤ demand cap | 10 × 3 × 52 = 1,560 |
| C7 Production ≤ market | 10 × 52 = 520 |
| C8 Crop diversity | 10 × 52 = 520 |
| C9 Binary linkage upper | ~200 |
| C10 Min acreage lower | ~200 |
| C11 Max plant acres | 52 |
| C12 Max harvest acres | 52 |
| C13 Budget | 1 |
| C14 Overtime | 52 |
| **Total** | **~3,885** |

HiGHS solves problems of this scale in under 5 seconds.

---

## 12. Removed from v1

| v1 element | Disposition |
|-----------|-------------|
| `CHANNEL_PREMIUM = 1.04` | Removed. Revenue now from explicit channel sales variables. |
| `WEIGHTED_AVG_PRICE` | Removed. Replaced by per-channel `price_per_lb` per crop. |
| `WEIGHTED_AVG_PKG` | Removed. Replaced by per-channel `packaging_cost_per_lb` per crop. |
| Fixed 6-crop list | Replaced by user-defined `CROPS` list. |
| Fixed 14-succession list | Replaced by auto-generated succession calendar. |
| 12-month loop `range(12)` | Replaced by 52-week loop `range(52)`. |
| Monthly availability arrays (12 elements) | Replaced by weekly arrays (52 elements) derived from labor/water configs. |
| Per-succession diversity constraint | Replaced by per-week, per-crop diversity constraint (C8). |

---

## 13. Implementation Plan

### Phase 1 — Core model (no UI, notebook format)
1. `utils/calendar.py` — `week_of_year()`, `generate_successions()`, `monthly_to_weekly()`
2. `utils/water.py` — rainfall lookup, catchment/well/city water derived arrays
3. `utils/labor.py` — labor capacity and cost arrays from employee config
4. `utils/demand.py` — expand demand_cap_type to per-week arrays (52 elements)
5. `solver.py` — `solve_farm_optimization()` accepting full v2 parameter set
6. `validate.py` — input validation and infeasibility pre-checks
7. Updated notebook with v2 parameter sections and sensitivity analysis

### Phase 2 — Reporting
- Weekly planting schedule output
- Channel sales allocation table
- Profit waterfall (channel revenue vs. cost components)
- Water usage chart (supply vs. demand by week)
- Labor utilization chart by week

### Phase 3 — v2.1 additions (future)
- Grade A/B split (fixed % per crop, separate per-grade per-channel pricing)
- Rotation constraints (crop family tracking by field block)
- Stochastic yield scenarios (Monte Carlo sensitivity)
