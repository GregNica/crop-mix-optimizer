# SPEC v3 — Solver Reformulation (Phase B: "Make the constraints honest")

Status: §3 REVISED 2026-07-27 after adversarial review found three structural defects in it (see §3.0). Phase B.1 has landed (`0f56ce9`, `6338359`); §3 is next.
Prereq: Phase A of the audit plan (`~/.claude/plans/eager-petting-hare.md`) — the numbers-true fixes — should land first or together; this spec assumes A1 (rainfall, done) and takes over A3/A5 (labor rate basis, well cost) because they change the constraint matrix.
Supersedes: SPEC_v2.md §5 constraint semantics where they conflict. Everything not mentioned here carries over from v2 unchanged.

**⚠️ Read §3.0 before implementing §3.** The version of §3 that was externally reviewed in
July 2026 does not work: its periodic boundary leaves inventory undetermined, and its
shelf-life rows are tautologies in exactly the cases they were written for. Both are fixed
below. The external reviewer confirmed the broken construction as sound, which is the
concrete cost of a review that confirms more than it stress-tests (§12).

## 0. What this fixes (audit trace)

| Audit item | Defect | v3 resolution |
|---|---|---|
| B1 | C7 caps each succession's production at ONE week's demand | C7 deleted; inventory balance makes overproduction unprofitable instead of infeasible |
| B2 | C5b double-counts overlapping spread windows (−50% revenue on shipped Garlic) | C5a/C5b deleted; sales draw from a real inventory pool |
| B3 | C4 charges full annual yield to storage in every harvest week | C4 deleted; storage bounds actual held inventory |
| B4 | "Annual total" demand enforced as annual/52 every week | True annual row per crop×channel |
| B5 | Season windows must contain the whole crop cycle → 3 shipped templates generate zero plantings | Seasons redefined as **planting windows** |
| B6 | No year-wrap; nothing plantable after ~W45; no overwintered crops | Cyclic steady-state year (weeks mod 52) |
| B7 | Water tank is billed but stores nothing | Tank state variable with carryover balance |
| B8 | Overlapping demand ranges overwrite (`=`) instead of accumulate | `+=` |
| A3 | Labor blend charged on all hours; salary-only farm gets $0/hr labor incl. OT/hire; mixed crew double-charged | Labor split into cost classes with hours-used variables |
| A4 | Idle contracted payroll silently free | Disclosed; optional committed-hours mode |
| A5 | `well_cost_per_L` never wired; well water free | Sourced water supply variables with per-source cost |
| 1.4 | Time-limit incumbent discarded; `validate.py` never called; `y` unbounded above | All three fixed |

Additional defects found by the 2026-07-24 adversarial gap-check (not in the original audit), also resolved here:

| Gap-check item | Defect | v3 resolution |
|---|---|---|
| F1/N1 | Post-solve hire/OT split reconstructed "hire-first," but the LP buys the cheaper lever — reported profit ≠ optimized objective when `hire_wage_markup > mult−1` (measured: enabling the hire *option* dropped reported profit $15k on an identical plan) | Labor hours become real variables (§4); costs reported directly from them, reconstruction deleted |
| F2 | Spread window anchored at the **last** harvest week — multi-harvest-week spread crops can't sell during their first k−1 real harvest weeks (measured −67%), and the window truncates at W52 | Dies with C5a/C5b deletion (§3.5) |
| F3 | C11/C12 charge **full** succession acreage in every plant/harvest week (no even-split divide) — a 3-harvest-week succession triple-counts against the equipment cap (measured: 4 ac planted where 12 fit) | Even-split coefficients (§6.5) |
| F4 | `piece_rate_per_lb` documented, collected, never charged — API users get free harvest crews | Parameter removed; validation rejects it (§4.4) |
| F5 | `overtime_rate_multiplier < 1` → unbounded MILP; `min_acreage_if_planted > total_land` → silent zero-acre crop | Validator additions (§7.2) |
| N2/N3 | Mixed week conventions: depreciation rates built ÷52 but charged ×`operating_weeks` (−7.7%); fixed selling ×52 in cash but ×`operating_weeks` in P&L | One canonical convention (§6.6) |
| N4 | `variable_selling_cost_per_lb` silently netted into price pre-solve: "Gross Revenue" is net, the cost is itemized nowhere, overhead base eroded ($5.1k at defaults) | Explicit per-lb cost coefficient on `v`; overhead on true gross (§6.7) |
| N5/N6 | Client recomputes capacity/supply series with different physics than the constraints (field_time_pct, rainfall offsets ignored) → bottleneck misdiagnosis; `city_water_cost` dropped by the adapter | Solver returns authoritative `capacity_series` + all cost lines; client renders, never recomputes (§9) |
| N7 | **Trap for Phase A:** `well_cost_per_L` is charged on all net irrigation (solver.py:231) — wiring it as scoped would double-charge city-water litres | §5 attaches cost to source draws; **Phase A must NOT wire the knob into the v2 var-cost path** |

Design principle carried over from v2: the solver stays a **pure LP/MILP** built for scipy.milp/HiGHS, all data precomputed into arrays, one flat variable vector. No new binaries beyond the existing `y[i]`.

---

## 1. Calendar semantics: planting windows + cyclic year (B5, B6)

### 1.1 Season = planting window

`crop["seasons"] = [{"start": "MM-DD", "end": "MM-DD"}]` now means: **the crop may be *planted* in any week whose start-date falls inside the window.** The cycle no longer needs to fit inside the window.

In `generate_successions()`:

```
for slot_start in range(start_w, end_w + 1):        # was: range(start_w, last_start + 1)
    weeks = [((slot_start - 1 + k) % 52) + 1 for k in range(total_weeks)]   # cyclic
```

- Drop the `last_start = min(end_w - total_weeks + 1, 52 - total_weeks + 1)` truncation and the `slot_end > 52 → skip` rejection.
- A crop whose cycle would exceed 52 weeks total is still rejected (validation error, not silent).
- If a season window itself wraps (start "10-01", end "02-28"): `start_w > end_w` → planting weeks are `range(start_w, 53) ∪ range(1, end_w + 1)`. This is now legal.

### 1.2 Steady-state year

The model becomes a **repeating annual plan**: a succession planted W44 with a 20-week cycle occupies W44–52 and W1–11 *of the same modeled year*, harvesting in early spring. Interpretation: in any steady operating year you are simultaneously harvesting last fall's planting and making this fall's. This is the standard cyclic formulation for annual planning and requires **no horizon extension** — all per-week constraints (land, labor, water, storage, cash) already index weeks 1–52 and pick up wrapped weeks automatically through `phase_table`.

Consequences to implement:
- `build_phase_table` unchanged (it maps whatever weeks the succession lists).
- Anywhere that assumes `s["weeks"]` is contiguous/ascending must be audited: `succ_last_harv` ordering, seed-cost "first week" (stays `s["weeks"][0]` = planting week, correct), cumulative-cost logic in C13 (see §6.3).
- **Disclosure (UI copy, ship with the feature):** "The plan is a repeating annual cycle: costs late in the year belong to plantings harvested early in the same displayed year. Year 1 of a new farm will differ."

---

## 2. Variable layout (v3)

All continuous ≥ 0 unless noted. `n_c` = crops, `n_ch` = channels, `W` = 52.

| Block | Size | Meaning | Present when |
|---|---|---|---|
| `x[i]` | N_S | land fraction, ub 1 | always |
| `y[i]` | N_S | binary, **lb 0 ub 1** (fixes unbounded-y) | always |
| `v[c,ch,w]` | n_c·n_ch·W | lbs sold | always |
| `inv[c,w]` | n_c·W | lbs of crop c held in storage at END of week w | always |
| `waste[c,w]` | n_c·W | lbs discarded in week w (free disposal, earns nothing) | always |
| `h_hr[w]` | W | hourly-staff hours used | any hourly/seasonal staff |
| `h_ot[w]` | W | overtime hours | overtime_enabled |
| `h_hire[w]` | W | hired hours, ub max_hire_hrs_per_week | hire_enabled |
| `wtr_well[w]` | W | liters drawn from well, ub well_weekly_cap_L | well_enabled |
| `wtr_city[w]` | W | liters of city water | city_water_enabled |
| `wtr_draw[w]` | W | liters drawn from tank | tank active (§5) |
| `tank[w]` | W | liters in tank at END of week w, ub water_storage_capacity | tank active |

Notes:
- `h_sal` (salaried hours used) needs **no variable**: salaried capacity is free at the margin, so it is folded into the labor balance as slack against `cap_sal[w]` (§4).
- Optional blocks are only added when their feature flag is on — same pattern as v2 — to keep the Pyodide solve budget flat for simple farms.
- `storage_type` per crop (§3.3) is **data, not a variable** — it selects which capacity row a
  crop's `inv` column joins. No branching in the matrix.
- **Sizing, measured on the golden payload rather than estimated** (the original estimate here
  assumed ~40 successions; the real figure is **N_S = 101** — Spinach 26, Kale 22, Basil 16,
  Tomatoes 15, Cucumbers 9, Peppers 9, Garlic 4 — so every number below was low):

  | | v2 as shipped | v3 |
  |---|---|---|
  | variables | 930 | ~2,020 (202 x/y + 728 v + 364 inv + 364 waste + ≤156 labor + ≤208 water) |
  | rows | 1,981 (cash floor off) / 2,033 (on) | ~2,190 |
  | **nonzeros** | **6,787** / 29,224 with C13 | see below |

- **Nonzeros are the budget, not rows, and the original §3.4 blew it.** The dense cumulative
  shelf-life rows would have been ~62,000 nnz at demo scale — nine times the entire current
  matrix. §3.4's rolling form is ~1,800. Watch this number, not the row count, when adding
  constraint families. Also unbudgeted: deleting C7 alone moved a local solve **0.27 s →
  1.68 s** (fewer rows, harder LP), and §7.4(d) fires one extra LP relaxation *per zero-acre
  crop*. The "budget stays flat / ≤15 s" claim was never supported; measure it.

---

## 3. Inventory core (replaces C4, C5a, C5b, C7) — fixes B1, B2, B3

### 3.0 What changed on 2026-07-27, and why

Four adversarial agents reviewed the Phase-B plan against the live solver. Three findings
land on this section. They are recorded here because each one looks like a detail and is
not, and because the first version of §3 read as correct to two prior reviewers.

**(a) The periodic boundary `inv[c,0] ≡ inv[c,52]` leaves the inventory LEVEL free.** Sum the
balance over w = 1..52 and the level cancels: you are left with the annual identity
`Σ_w(sales + waste) = Σ_w st·H`. The 52 balance rows therefore have rank **51, not 52**, and
`inv[c,52]` is pinned only by `inv ≥ 0` from below and the storage row from above.
Demonstrated on a two-week fixture: identical `x`, identical `v`, identical objective, and
peak inventory anywhere in **8,500–50,000 lbs** depending on a ±1e-6 tie-break. So the
`inventory` array §9 promises to return is **not a well-defined output** — the UI would
render whichever vertex HiGHS happened to stop at.

It is also wrong in a second way. The periodic year lets a W52 harvest be sold in W5 *of the
same displayed year*, while C13, the interest calculation and the peak-borrowing curve are
all **calendar-anchored**: revenue books 47 weeks before the cost that produced it, and the
cash floor passes on money the farm does not have. §1.2's disclosure covers only the reverse
case (costs late in the year belonging to early harvests). Nothing disclosed early-year
revenue from a late-year harvest, because nobody had noticed it was possible.

**(b) §3.4's doubled-104-week shelf-life construction enforced nothing.** Under the periodic
boundary, write the doubled row at `wd = 52 + k`. Its LHS is `A + S(k)` where `A` is the
annual sales+waste total; its RHS is `st·Σ_{t ≤ k+52−L} H`. For `k ≥ L` the annual term
cancels on both sides and the row collapses to the plain within-year row. For **`k < L` —
exactly the wrap cases the doubling was added to catch** — the RHS falls *below* `A` and the
row becomes `S(k) ≥ −(non-negative)`, a tautology. Verified by construction: harvest 10,000
lb in W52, `shelf_life_weeks = 1`, sole buyer in W5 (true age at sale: 5 weeks). The spec's
rows permit the sale, **bit-identical to having no shelf-life constraint at all**. Every case
where the sale week precedes the harvest week in the calendar passes. Since §1 exists
precisely to enable overwintered and late-planted crops, the defect lands squarely on the
crops the reformulation was written for.

**(c) An uncapped "ambient" storage class is an unbounded ray and a user-accessible money
exploit.** This was a proposal made while drafting, not in the reviewed spec, and it is
recorded so it is not proposed again. An `inv` block with no upper bound and no objective
coefficient returns HiGHS status 3. Worse, `harvest_storage_cap` is a plain form input with
`min` set: marking every crop ambient and setting the cap to its minimum moved profit
**$494,134 → $585,408 with the plan otherwise unchanged**, because capacity bills
`cap × rate × 52`. The model would pay a grower to relabel their cold store as a barn.
**Ambient storage gets its own capacity and its own (much cheaper) rate. Never zero, never
unbounded.**

**The fix for (a) and (b) is the same one line: anchor at `inv[c,0] = 0`.** That single change
restores full rank, kills the sell-before-you-grow window, makes the plain lagged shelf-life
rows correct, and removes the need for the doubled index set entirely. What it costs is
stated honestly in §3.2.

### 3.1 Harvest inflow (data, not a variable)

`H[c,w] = Σ_{i: crop(i)=c, phase_table[i][w]=2} x[i] · total_land · yield_per_acre[c] / n_harv_weeks[i]`

Even-split-across-harvest-weeks convention is retained from v2. `n_harv_weeks[i]` comes from
`harvest_weeks_of()` in `farm_v2/utils/calendar.py` — one clamped definition, added in B.1
because this divisor had drifted into three differently-scoped copies.

### 3.2 Weekly balance (equality rows, n_c·W)

```
inv[c,w] = inv[c,w-1] + st[c]·H[c,w] − Σ_ch v[c,ch,w] − waste[c,w]        ∀ c, w
inv[c,0] = 0
```

where `st[c]` = per-crop sell-through (fallback to farm-wide default, as in v2).

**Boundary: `inv[c,0] = 0`, NOT periodic.** See §3.0(a). This is the sparse, well-determined,
calendar-honest formulation: 52 rows of rank 52, ~5 nonzeros each, one solution.

**What the anchor costs, stated plainly.** A succession planted in the autumn cannot sell
stock in the early weeks of the same displayed year — its inventory starts empty. That is
audit item **B6 (no year-wrap)**, and it is §1's job, not §3's. Two things make the trade
acceptable: no crop in the current 30-template library overwinters, so nothing shipped
regresses; and `inv[c,0] = 0` is the honest reading of *year one of a plan*, which is what a
grower entering their farm for the first time is actually asking about. If §1's cyclic year
later needs a non-zero opening stock, the correct construction is an explicit `open[c] ≥ 0`
variable **priced at the carrying cost** — never a free periodic identity, which is what made
the level indeterminate in the first place.

`waste[c,w]` is free disposal (earns nothing, costs nothing further). It is necessary because
the balance is an equality: without it, a shelf-life bound would *force* sales that demand
cannot absorb and turn a modelling limit into an infeasibility — the exact B1 failure mode
this section exists to remove.

### 3.3 Storage capacity — two pools (replaces C4)

Per-crop `storage_type ∈ {refrigerated, ambient}` routes each crop's inventory to one of two
capacities, each with its own capital cost, depreciation life and derived weekly rate:

```
Σ_{c: refrigerated} inv[c,w] · crop_size_m3_per_lb[c] ≤ cold_storage_cap       ∀ w   (W rows)
Σ_{c: ambient}      inv[c,w] · crop_size_m3_per_lb[c] ≤ ambient_storage_cap    ∀ w   (W rows)
```

**Why two and not one.** Cured storables — garlic, onions, winter squash — want 50–60 °F and
50–70% RH. Winter squash takes **chilling injury below 50 °F**, so a cooler does not merely
waste money on it, it damages the crop. Charging six months of cured garlic against the
refrigerated cap models the wrong physical thing. The converse also holds and is the reason a
shelf-life-based derivation will not do: carrots, beets and cabbage are *refrigerated*
long-hold (0 °C, high RH) and genuinely do occupy the cooler for months.

**Why the split is not optional.** A single 20-acre potato or winter-squash block is
~630 m³ / ~515 m³ of held volume — more than an honestly-sized cooler on its own. With one
pool, a bulky ambient storable crowds out the perishables that actually need refrigeration,
and the model silently suppresses a profitable crop. Deleting C7 makes this *more* likely,
not less: storable acreage roughly doubles once production stops being pinned to one week's
demand (measured: Garlic 11.6 → 23.5 acres).

**Sizing and rates** (see `BENCHMARK_DEFAULTS` in `public/index.html` for provenance):

| pool | shipped default | capital | life | rate $/m³/wk |
|---|---|---|---|---|
| refrigerated | 275 m³ | $500/m³ | 20 yr | 0.4808 |
| ambient | 150 m³ | $120/m³ | 30 yr | 0.0769 |

Ambient is cheap, **not free** (§3.0(c)). Document in the field's help text that a real
15–20 acre storage-crop program needs 500–700 m³ of ambient space.

**Modeling choice, unchanged from the reviewed draft:** produce sold in its harvest week never
touches storage (`inv` is end-of-week), so field-to-truck sales consume no capacity. Note the
consequence: v3 then has **no volumetric throughput cap at all** — C4 was the only m³/week
row, and C11/C12 cap harvest *acres*, not volume. A farm could push unlimited tonnage through
a packing shed in one week. If that matters, add an explicit `max_harvest_m3_per_week`; it is
deliberately **not** in this phase.

**Expect the reported storage number to move when this lands.** B.1 made C4 charge *physical*
volume on the conservative reading that spoiled and unsold product still occupies the cooler.
Here the inflow is `st·H` — sellable only — on the assumption that grade-out happens at
harvest and culls never enter storage. Both are defensible; they are the two ends of a
quantity the model cannot split without a field-loss-vs-storage-loss parameter nobody wants
to enter. The inventory model earns the more precise end because it can price holding. On the
shipped farm this is 163 m³ → 139 m³ of counted inflow, against a peak *held* figure of
~178 m³ that C4 could not see at all.

### 3.4 Shelf life — a rolling bound (replaces `sales_spread_weeks`)

New per-crop param `shelf_life_weeks` (int ≥ 1; default 1 = must sell or dump in the harvest
week — the v2 spread=1 behavior). Skip the row when `L ≥ 52` (non-perishable).

```
inv[c,w] ≤ st[c] · Σ_{k=0..L−1} H[c, w−k]        ∀ c, w        (n_c·W rows, ~L nonzeros each)
```

"Nothing in the cooler is older than L weeks" — inventory may not exceed what arrived in the
last L weeks. Anchor-free, correct under either boundary, and it replaces the doubled
104-week cumulative construction that §3.0(b) showed to be vacuous. It is also **~1,800
nonzeros instead of ~62,000**: the cumulative form's rows grow with `w`, this one does not.

With `inv[c,0] = 0` the `w−k < 1` terms are simply absent (no wrap, no index mapping). If §1
later introduces cyclic planting, `w−k` becomes `((w−k−1) mod 52) + 1` and the row stays
correct — that is the property the cumulative form did not have.

**Migration:** `sales_spread_weeks` is deprecated; loader maps
`shelf_life_weeks = max(sales_spread_weeks, 1)` when the new key is absent. Then the UI
renames the field ("How many weeks after harvest can this crop still be sold?" — same grower
question, honest semantics).

**⚠️ Raise the 8-week clamp at `solver.py:581` before shipping honest defaults.** It currently
does `min(8, ...)`, so a UI offering carrots 12 or garlic 16 would display one number and
solve another, silently.

**⚠️ Shelf life cannot ship long defaults until holding costs something.** Today holding is
free in every dimension: no shrink, no quality/price decay, no per-lb-week charge. A longer
shelf life is therefore pure upside in the objective at zero cost, and the crops it distorts
worst are exactly the high-volume ones with the widest wholesale→retail spread (potatoes
$0.25→$0.70 at 30,000 lb/ac, carrots $0.40→$1.00, cabbage, onions). The plan would read "hold
it and sell retail all winter" with no washing labour, no shrink, and a farmers' market
absorbing storage-grade product at peak prices in February. **Ship conservative defaults**
(the error is one-sided: optimism here is invisible and unrecoverable), and treat a per-crop
`storage_loss_pct_per_week` in the balance — `inv[c,w] = inv[c,w−1]·(1−loss_c) + …`, still
linear — as the prerequisite for anything above ~4 weeks. It also happens to make the
minimum-inventory solution strictly optimal, which is a second, independent reason to want it.

### 3.5 What deletes

- **C5a per-week supply rows** — gone; the balance covers it.
- **C5b cumulative window rows** — gone; this is the B2 fix. No window bookkeeping exists to
  double-count. F2 (window anchored at the LAST harvest week, truncated at W52) dies with it.
- **C7 production ≤ capacity rows** — gone; this is the B1 fix. Overproduction becomes `waste`
  that cost money to grow and earns nothing, so the optimizer prices it out instead of the
  model forbidding it. Measured: profit +$84,857, Garlic 11.6 → 23.5 acres.
- **C4** — replaced by §3.3.

**Three consequences of deleting C7 that are not automatic — handle them or they ship:**

1. **Free disposal turns modelling bugs into invisible waste.** With C7 gone the shipped
   Garlic grows 200,205 sellable lbs and sells 120,103 — 40% dumped, and that is the F2 window
   bug, not economics. With C7 present the same defect expressed as suppressed acreage, which
   at least *looked* wrong. **The result dict must return waste per crop and the UI must show
   it**, or the next bug hides the same way. (Live today, unrelated to C7: the shipped default
   plan already discards 44,600 lb of garlic — 45.2% of sellable output — with nothing
   anywhere saying so.)
2. **The overhead base breaks.** `overhead_pct_of_revenue` proxies insurance, tax, admin and
   R&M — costs that scale with the size of the operation. C7 was accidentally holding
   production ≈ sales; without it a farm that grows 2× and sells 1× pays overhead as if it
   were half its real size.
3. **C7 + §6.1 together remove every weekly sales limit.** §6.1 drops the weekly C6 rows for
   `annual` channels and C7 deletion drops the weekly production cap, so a crop could clear an
   entire annual contract in whichever single week most flatters the cash floor. In v2 both
   rows bound weekly flow. Keep `max_weekly_lbs` available, or keep a weekly row.

Expected observable effects (assert in tests): shipped Garlic revenue ≈ doubles (B2); Garlic
acreage responds to profitability, not `demand/yield` (B1); a 4-harvest-week crop no longer
needs 4× storage (B3, already delivered by B.1's divisor fix).


## 4. Labor cost classes (fixes A3; discloses A4)

### 4.1 New arrays from `compute_labor_arrays`

Per week: `cap_sal[w]` (salaried field-hours capacity), `cap_hr[w]` (hourly+seasonal capacity — the existing `labor_capacity_hourly`), `rate_hr[w]` (blend over hourly staff only — existing), and scalars `salaried_weekly_cost` (unchanged, stays in fixed cost).

New required param when `hire_enabled`: **`hire_wage_per_hr`** (explicit $/hr, loaded with payroll like other wages). The v2 formulation (`rate_hr × (1+markup)`) is invalid because `rate_hr` is legitimately 0 on salary-only farms — the A3 free-hire bug. `hire_wage_markup` is deprecated; loader maps `hire_wage_per_hr = rate_hr_mean × (1 + markup)` only when both old key present and `rate_hr_mean > 0`, else requires the new key.

Overtime rate: `rate_ot[w] = rate_hr[w] · overtime_rate_multiplier` — **full** rate, not the v2 increment, because in v3 base wages are no longer pre-charged on every hour (§4.2). If `cap_hr` is all-zero (salary-only farm), overtime is meaningless (salaried staff aren't paid OT): validation warns and disables the toggle rather than pricing OT at $0.

### 4.2 Labor balance (replaces the labor part of var_cost and C2)

Demand: `L[w] = Σ_i x[i] · total_land · labor_rate[i][w]` (existing lookup).

```
L[w] ≤ cap_sal[w] + h_hr[w] + h_ot[w] + h_hire[w]        ∀ w      (C2′, W rows)
h_hr[w] ≤ cap_hr[w]
h_ot[w] ≤ max_overtime_hrs_per_week   (and ≤ ot_frac·cap_hr[w] if a legal cap is configured)
h_hire[w] ≤ max_hire_hrs_per_week
```

Objective cost: `Σ_w ( rate_hr[w]·h_hr[w] + rate_ot[w]·h_ot[w] + hire_wage_per_hr·h_hire[w] )`.

The LP fills salaried capacity first (free at margin), then the cheapest paid class — the ordering falls out of prices, no big-M needed. This kills both A3 failure modes: a salary-only farm pays `hire_wage_per_hr` for extra hours (never $0), and a mixed crew is no longer charged `rate_hr` for hours its salaried staff covered.

**Reporting reads the variables (kills F1/N1).** `overtime_cost = Σ rate_ot[w]·h_ot[w]`, `hire_cost = Σ hire_wage_per_hr·h_hire[w]` — taken directly from the solution vector. The v2 post-solve "hire-first" reconstruction (solver.py:716-739) is **deleted**; it disagreed with the objective whenever hire was priced above overtime, so reported profit, the cash curve, peak borrowing, interest, and the staffing recommendation were all wrong in that half of the config space. If two levers are priced identically the LP split is degenerate but cost-identical — report it as returned.

**Remove labor from `var_cost_coeff` / `var_cost_weekly` entirely** (the `labor_c` term at solver.py:234). Labor cash now flows through the `h_*` variables — C13 and the reporting cash curve must pick them up (§6.3).

### 4.3 Piece-rate removal (F4)

`piece_rate_per_lb` promised a $/lb harvest cost, was collected by `compute_labor_arrays`, and charged nowhere — an API user configuring a piece-rate crew harvests for free. There is no crop↔worker mapping to charge it correctly, and no UI field exists. **Remove the parameter**; `validate.py` rejects it with a pointer to per-channel `packaging_cost_per_lb` as the interim home for per-lb handling costs. Revisit only if a real crew-assignment model is ever built.

### 4.4 Idle-payroll disclosure (A4)

Default behavior unchanged (hourly staff paid only for hours used — SPEC_v2 §5D stands). Two additions:
1. **UI copy** on the labor section: "Hourly and seasonal staff are costed only for hours the plan uses. If you guarantee minimum hours, enter them — idle guaranteed hours are a real cost."
2. Optional `hourly_committed: true` per employee row: their weekly cost becomes `count·hours_per_week·wage·(1+benefits)` **fixed** (moved into `salaried_weekly_cost` mechanics) while still contributing `cap_hr`. This also finally uses the currently-discarded `min_guaranteed_hours`: `guaranteed_hourly_cost[w]` joins fixed weekly cost, and hours below the guarantee are free at the margin. **Implementation (per external review):** split hourly labor into two plain continuous variables — `h_hr_guar[w]` (objective cost 0, ub `g[w]`) and `h_hr_paid[w]` (cost `rate_hr[w]`, ub `cap_hr[w] − g[w]`) — both entering the C2′ balance. No piecewise cost, no extra binaries; the LP drains the free block first automatically. When no guarantees exist, `g[w]=0` and this degenerates to plain `h_hr`.

---

## 5. Water: sourced supply + real tank (fixes B7, A5)

Irrigation demand: `N[w] = Σ_i x[i] · total_land · net_water_rate[i][w]` (rain-offset stays inside `net_water_rate`, unchanged).

Catchment inflow (data): `catch[w] = catchment_surface_area_m2 · rain_mm-equivalent[w] · efficiency` — the existing `compute_free_water` catchment term, now routed into the tank instead of a same-week allowance.

```
N[w] ≤ wtr_draw[w] + wtr_well[w] + wtr_city[w]                       ∀ w   (C3′)
tank[w] ≤ tank[w-1] + catch[w] − wtr_draw[w]                          ∀ w   (tank balance, ≤ so overflow spills)
tank[w] ≤ water_storage_capacity                                      (bound)
tank[0] = 0          (NOT periodic — see below, and §3.0(a))
```

⚠️ **`tank` has exactly the degeneracy §3.0(a) describes, for the same reason.** It carries no
objective coefficient, its balance is `≤`, and a periodic boundary would leave the level free —
so `tank_level` in the §9 result contract would not be a physical quantity, and the tank could
start the year full for free, serving W1–W20 irrigation from rain that falls in W45. That is
the water twin of "sell before you grow", and equally undisclosed. Anchor at zero for the same
reasons and with the same cost (a genuinely Mediterranean farm that fills its tank over winter
loses that carryover until §1's cyclic year lands, at which point it needs a **priced**
opening-stock variable, not a free identity). Aggregate conservation (`Σ draw ≤ Σ catch`) holds
either way; it is the *reported series* that is meaningless under the periodic form.

- Tank block active when `catchment_enabled AND water_storage_capacity > 0`. Catchment with no tank degrades to the v2 same-week behavior (`wtr_draw[w] ≤ catch[w]`, no state).
- Objective: `well_cost_per_L · Σ wtr_well + city_water_cost_per_L · Σ wtr_city`. Tank draw free.
- **A5:** `well_cost_per_L` must be added to the client payload builder (it exists in the form; it is dropped on the way to Python). The v2 hack of charging `well_cost_per_L` on `net_water_rate` inside var_cost (solver.py:231) is removed — water cost now attaches to actual source draws. C13 picks up both paid sources (§6.3).
- Well/city weekly caps and fixed fees unchanged.

---

## 6. Demand, diversity, cash

### 6.1 Annual demand as an annual row (B4)

For `demand_cap_type == "annual"`: **one row** per crop×channel: `Σ_w v[c,ch,w] ≤ annual_demand_lbs`, and **no weekly cap** from this channel (weekly limit comes only from harvest+inventory physics). Docstring finally true. Optional `max_weekly_lbs` key if a buyer also has a weekly ceiling — when present, add the flat weekly rows too.

### 6.2 Overlapping ranges accumulate (B8)

`demand.py:100`: `arr[start-1:end] = value` → `arr[start-1:end] += value`. Two overlapping contracts now add. One-line fix + regression test.

### 6.3 C13 cash floor and the reporting cash curve

Same cumulative structure as v2, with the cost columns updated to the new variables:

- revenue: `+net_after_price[c,ch] · v[c,ch,w]` for w ≤ W (unchanged);
- `x[i]`: `−cum_var[i,W]` where cum_var now **excludes labor** (§4.2) and **excludes water** (§5);
- labor: `−rate_hr[w]·h_hr[w] − rate_ot[w]·h_ot[w] − hire_wage_per_hr·h_hire[w]` for w ≤ W;
- water: `−well_cost_per_L·wtr_well[w] − city_water_cost_per_L·wtr_city[w]` for w ≤ W;
- rhs: unchanged (fixed_weekly + fixed_selling_per_week), plus `guaranteed_hourly_cost` when §4.3's committed mode is on.

The post-solve reporting curve (`weekly_cash_flow`) mirrors the same terms — one shared helper builds the weekly cost series for both, so the floor and the curve cannot drift apart again.

`fixed_selling_per_week` also joins `fixed_cost` in the P&L (audit A6 — Phase A item, restated here because C13 already carries it and the two must agree).

### 6.4 Diversity (C8) — no math change

Keep acre-weeks semantics; fix the label (audit Part 3): "max share of annual field-time (acre-weeks), not a peak land share." Out of scope for the matrix.

### 6.5 C11/C12 even-split coefficients (F3)

The plant/harvest equipment caps must use the same even-split convention as the harvest supply: coefficient `total_land / n_plant_weeks[i]` (C11) and `total_land / n_harv_weeks[i]` (C12) instead of `total_land`. A succession planting over 2 weeks works `a/2` acres per week, not `a` in each. Without this, any real equipment cap over-restricts by the phase-week count (measured: 4 acres planted where 12 fit).

### 6.6 One week-count convention (N2, N3)

All recurring weekly fixed lines — depreciation-derived rates, machinery, rent/mortgage, other debt service, fixed selling, city-water fixed fee — are charged **× 52** in the P&L, in C13, and in the cash curve. Rationale: depreciation is calendar-time, and rent, debt service, and stall retainers are paid in the off-season too; charging them ×`operating_weeks` (48) silently understated fixed costs ~7.7% while the cash curve charged 52 — cash and P&L could never both be right. `operating_weeks` is **deprecated as a cost multiplier** (it never shortened the planning horizon despite its tooltip); keep the input, ignore it in cost math, update the tooltip, and remove it in a later major version. The payload builder's `capital/(years×52)` rate derivation is then exactly right.

### 6.7 Variable selling cost as an explicit term (N4)

Stop netting `variable_selling_cost_per_lb` into prices before the solve. It becomes an explicit objective/C13 coefficient on `v` (exactly like packaging) and its own returned P&L line (`variable_selling_cost`). Revenue is then genuinely Σ v × user-entered price — the line labeled "Gross Revenue" stops lying — and `overhead_pct_of_revenue` is charged on the true gross price, closing the quiet overhead-base erosion (~$5.1k at shipped defaults).

---

## 7. Solver mechanics & failure surfaces (audit 1.4)

1. **Time-limit incumbent:** scipy `milp` status 1 with `result.x is not None` → extract normally, return `status="time_limit_feasible"`, add `"gap_note"` to the dict. UI shows the plan with a "best plan found within time budget" banner instead of a bare failure.
2. **Wire `validate.py`:** `solve_farm_v2` calls `validate_all(params)` first; violations return `{"status":"invalid_input", "errors":[...]}` — never a raw traceback into Pyodide. Add the missing checks while there: NaN-safe positivity (`not (val > 0)` instead of `val <= 0`), crop-name uniqueness (the chatbot addresses crops by name), season-window sanity under the new §1 semantics, `overtime_rate_multiplier ≥ 1` (F5: below 1 the OT coefficient goes negative and an uncapped OT variable makes the MILP unbounded), `min_acreage_if_planted ≤ total_land` (F5: above it, C9+C10 silently force the crop to zero), and rejection of the removed `piece_rate_per_lb` (§4.3). Per external review: warn when `hire_enabled` with `max_hire_hrs_per_week == 0` (mathematically inert, user-confusing) — same treatment as the salary-only overtime case in §4.1.
3. **`y` bounds:** `ub[y]=1` (§2).
4. **Zero-acre explanations** (audit Part 3, the top trust feature — the solver half lives here): post-solve, for each crop with total acres < ε, classify in order and return `"zero_acre_reasons": {crop: reason}`:
   a. dropped by margin hurdle (once the hurdle moves into Python — see §8);
   b. zero effective demand (all caps 0 after expansion);
   c. `min_acreage_if_planted` infeasibility: max sellable acres implied by demand+shelf-life < min acreage;
   d. otherwise *outcompeted*: re-solve the **LP relaxation** once with `y[best succession of c] = 1` fixed and report the profit delta ("planting ≥ min acreage of X costs ~$Δ vs. the optimal plan"). One extra LP per zero crop, relaxation only, behind a `explain_zero_acres=True` flag so the What-If loop can skip it.

## 8. One cost basis (audit 1.3, the solver-side half)

Move the min-viable-margin hurdle from JS into Python: a pre-solve `channel_contribution_margins(params)` computed from the **same arrays the objective uses** (`net_after_price`, `var_cost` components, `rate_hr` blend). It returns per crop×channel CM%; channels below `min_viable_margin_pct` get their demand zeroed **in Python**, and the exclusions list is returned in the result dict for the banner. The three JS copies of the margin kernel then become renderers of returned numbers, not recomputations (client work tracked in Phase C/E, but the Python API lands here so they have something to read).

---

## 9. Result-dict contract additions

New keys (all existing keys unchanged): `inventory` (n_c×53), `waste` (n_c×53), `labor_hours` `{salaried_used, hourly, overtime, hired}` weekly arrays, `water_sources` `{tank_draw, well, city, tank_level}` weekly arrays, `zero_acre_reasons`, `channel_margins`, `excluded_channels`, `gap_note`, `variable_selling_cost` (§6.7), and **`capacity_series`** `{labor, water, storage}` — the exact per-week capacity arrays the constraints used (post `field_time_pct`, post rainfall-offset/efficiency). N5/N6 rule: **the client renders returned numbers and never recomputes physics** — the adapter must serialize every cost line the solver returns (`city_water_cost` is currently dropped) and the utilization/bottleneck displays must read `capacity_series`, not rebuild supply from form fields with different physics. The per-channel weekly sales the UI needs (audit Phase C) are already in `v` — Phase C's job is transport/rendering, not solver work.

Three additions, each closing something B.1 could only paper over:

- **`storage` belongs in `capacity_series`** (it was omitted). B.1 left the adapter recomputing
  the storage series in Python because there was no key to read; it now understates any plan
  that holds stock, and there is a `⚠️` marker at that site pointing here. When §3.3 lands the
  solver must return **two** occupancy series (refrigerated and ambient) plus their caps, and
  the adapter's copy must be **deleted, not corrected** — it is the last of the four
  hand-written copies of this quantity.
- **`waste_by_crop`** — annual lbs discarded per crop, and the fraction of sellable output it
  represents. Not optional: §3.5 explains that free disposal converts modelling bugs into
  invisible waste, and the shipped plan is *already* dumping 45.2% of its garlic with nothing
  saying so. A number nobody can see is a number nobody can audit.
- **`held_peak_m3`** per pool — the actual peak the plan needs, so the UI can tell a grower how
  big a building to put up instead of making them infer it from a utilisation percentage.

## 10. Test plan (binding-behavior suite — audit Part 7 item 2)

Every constraint family gets a squeeze/relax pair: solve generous → solve squeezed → assert profit strictly drops AND the binding series touches its cap → relax → recovery. Plus targeted pins:

**Mutation-test every one of these.** Two guards in this repo shipped inert before that became
the habit, and three more did during Phase B.1 — including one that passed with a factor
deleted from the solver, because the shared fixture omitted `sell_through_fraction` and it
defaulted to 1.0. A guard that has never been seen to fail is not evidence. Two specific traps,
both live: a tolerance wider than the smallest error it must catch (B.1 used 20% against a
1/0.85 = 1.176× error), and a fixture default that makes the thing under test a no-op.

1. **Inventory:** single crop, 1 harvest week, shelf 4, demand spread over 4 weeks → all harvest sells across the window; total sold == st·H (B2 dead). Overlapping successions (the Garlic repro): revenue at shelf 8 == revenue at shelf 1 when demand is ample in-week (no window double-count).
2. **B1 dead:** demand < yield·min_acreage → crop plants at min acreage and wastes the excess **iff** still CM-positive; zero_acre_reasons fires when not.
3. **Storage:** inventory held N weeks occupies capacity all N weeks; same-week sales occupy none; squeeze cap → profit drops, `inv·size` touches cap. Plus the two-pool rows: an ambient crop must **not** consume the cold cap and vice versa, and neither cap may be unbounded (§3.0(c) — assert a finite bound exists, since the failure mode there was HiGHS status 3, not a wrong number).
3b. **Determinacy (guards §3.0(a)):** solve the same fixture twice with a ±1e-6 perturbation on
    one objective coefficient and assert the returned `inventory` series is identical to
    within tolerance. Under the periodic boundary this test fails by 6× — it is what would
    have caught the free level. Also assert no crop sells before it harvests: for every
    `c`, the first non-zero `Σ_ch v[c,ch,w]` is at or after the first non-zero `H[c,w]`.
3c. **Shelf life actually binds (guards §3.0(b)):** harvest in one week, `shelf_life_weeks = 1`,
    the only buyer L+3 weeks later → **zero** sold, all wasted. Run it with the sale week both
    after and *before* the harvest week in calendar order; the second is the wrap case the
    doubled construction let through, and it must fail closed under any boundary.
4. **Annual demand:** 52k lbs/yr contract, 10-week harvest crop → full 52k sellable (B4 dead); with `max_weekly_lbs` set, weekly rows bind.
5. **Labor classes:** salary-only farm + hire → hire hours cost `hire_wage_per_hr` exactly (A3 dead: assert cost > 0); mixed crew where salaried capacity covers demand → labor variable cost == 0; OT only after `cap_hr` exhausted, priced at full multiplier.
6. **Water:** Mediterranean profile (wet winter/dry summer) + tank → summer irrigation served from stored winter catchment; tank ≤ cap binds; no tank → same inputs infeasible or city-water-priced (B7 dead). Well litres cost `well_cost_per_L` (A5 dead).
7. **Seasons:** the three dead templates (Winter Squash, Melon, Snow Peas) generate successions and plant (B5 dead); an overwintered garlic (plant W40, 30-week cycle) harvests ~W18 and sells (B6 dead); assert cyclic land occupancy in W1–5.
8. **B8:** two overlapping ranges → caps add.
9. **Money identity** (audit Part 7 item 3, extended to v3 terms): profit == revenue − Σ(every cost class exactly once), with labor/water now coming from `h_*`/`wtr_*` and revenue at true gross prices (§6.7); cash curve week 52 == opening_cash + operating_profit − overhead − fixed_selling·52 (reconciliation identity, now exact under §6.6's single week convention). Add: reported OT/hire cost == objective's labor-flex cost by construction (F1 dead — assert on a markup-above-premium fixture); C11/C12 squeeze at even-split boundary (F3: 12 acres fit a 4 ac/wk harvest cap with 3 harvest weeks).
10. **Physical magnitude pins** (the class that would have caught A1): rainfall zone sums, one hand-computed 2-crop fixture where expected profit is derived on paper to the dollar.

## 11. Rollout order (each lands green before the next)

**B.1 — DONE** (`0f56ce9`, `6338359`): C4's missing `/n_harv_weeks` divisor, harvest storage
right-sized 5,000 → 275 m³ with an honest rate, `harvest_weeks_of()` extracted, the
`succ_*_lbs` precomputes that stop the sell-through product being hand-typed at seven sites,
and three storage binding tests. Profit $494,134 → $580,359, plan unchanged. **Owes browser
QA.** Ordered first because the resize and the divisor fix are destructive apart.

1. §6.2 B8 one-liner + §7.2 validate wiring + §7.1 incumbent + §7.3 y-bounds (isolated, low-risk).
2. §4 labor classes (touches objective, C2, C13, result dict) + tests 5, 9.
3. **§3 inventory core** — `inv`/`waste`, the `inv[c,0]=0` balance, the §3.4 rolling shelf-life
   bound, C4/C5a/C5b/C7 deletion, `waste_by_crop` in the result + tests 1–3, 3b, 3c.
   *Split from the field work below: land the mechanism against migrated 1:1 shelf lives
   (`max(sales_spread_weeks, 1)`) so any profit move is attributable to the constraint rewrite
   alone. Two structural changes and a data change in one commit is not debuggable.*
3b. **§3.3 two-pool storage + `storage_type`** — per-crop field defaulted across all 30
   templates, ambient capacity + rate, the 8-week clamp raised, `sales_spread_weeks` renamed.
   Conservative shelf-life defaults only (§3.4); anything above ~4 weeks waits for a holding
   cost.
4. §6.1 annual demand + §1 season/cyclic semantics + tests 4, 7, 8. **§1 is what restores B6**
   — until it lands, §3's zero anchor means no crop sells stock it grew the previous autumn.
5. §5 water tank + A5 wiring + test 6.
6. §7.4 zero-acre explanations + §8 Python margin hurdle. ⚠️ **§6.1 collides with §8**: the
   hurdle works by zeroing `demand_table[c,ch,:]`, so if annual demand becomes a separate
   scalar row rather than a sum over that array, the hurdle silently stops excluding anything.
   Wire the annual RHS from `demand_table.sum(axis=2)`.
7. Blob re-sync (`scripts/sync_solver_blob.py`), payload-builder updates (`well_cost_per_L`, `hire_wage_per_hr`, `shelf_life_weeks`), rebaseline `test_regression.py` with provenance.

Each step re-runs the demo fixture; expected headline moves are recorded in the commit message (e.g. step 3: Garlic revenue ≈ +$165k at shipped defaults).

## 12. External review record & deferred scope

Reviewed 2026-07-24 by a non-Claude model (Gemini 2.5 Flash) with full spec + v2 source; verdict **IMPLEMENT WITH CHANGES**. Adopted: the two-variable guaranteed-hours construction (§4.4), the cyclic index-mapping clarification (§3.4), the inert-hire validation warning (§7.2). Confirmed sound: inventory balance, periodic boundary, doubled-week unrolling, labor-class pricing (no gaming path given the §7.2 validators), waste-variable free disposal ("realistic, not degenerate"), C7 deletion.

**Two of those "confirmed sound" items were wrong** — the periodic boundary and the doubled-week
unrolling, both refuted with running counterexamples on 2026-07-27 (§3.0). This is the concrete
answer to the question this section closed with. A model reading prose confirmed a construction
that a model *executing* it refuted in one fixture. The lesson is not "get a better reviewer";
it is that **for a constraint formulation, the reviewer must build it and solve it.** All four
of the 2026-07-27 agents were told to refute rather than assess, given the live solver, and
required to show a counterexample they had run — that is what the difference bought.

Second review, 2026-07-27 (four adversarial agents against the live code):
- **Formulation:** refuted §3.2's boundary, §3.4's construction, and the free-ambient proposal;
  confirmed no-new-binaries and that C7 deletion has no gaming path (checked that
  `net_water_rate` is `max(0,…)`-clipped, so nothing rewards growing for its own sake).
- **Numbers:** re-derived every measured claim independently. Corrected two: the "30× storage
  headroom" figure was the *display's* number, not the constraint's (6.1×), and Snap/Snow Peas
  does generate one succession — only Winter Squash and Melon are truly dead.
- **Sizing/domain:** established the 275 m³ / $500 / 20 yr basis and found the $463/m³ capital
  figure was back-fitted from a legacy constant (463/1300 exactly), with a citation to a
  Cornell "sizing guide" that does not exist.
- **Postharvest:** shelf life and storage type for all 30 templates from AH-66 and extension
  sources; found that a naive "perishable → refrigerated" default gets **basil** wrong (it
  blackens in 2–3 days at 38 °F) and that **potatoes** (38–40 °F, 90–95% RH) fit neither
  bucket — a third regime, escalated as a product decision. Also: the shipped demo set
  contains **no refrigerated storable at all**, so nothing in it will exercise §3.3 — swap in
  Carrots or Cabbage or the feature ships untested in QA.

Explicitly **deferred** (raised by review, out of Phase B scope):
- **Crop rotation constraints.** C8 acre-weeks is a weak rotation proxy, but real rotation logic needs a land-parcel dimension the model doesn't have (land is one fungible pool). A per-field model is a major extension — record as a possible v4 direction, do not bolt onto v3.
- **Explicit energy costs** (cold-storage kWh, pumping). Partially represented today inside overhead R&M/utilities and the storage $/m³ rates; splitting them out is a parameter-granularity decision for the benchmark library, not a constraint-matrix change.

Also deferred, added 2026-07-27:
- **A per-lb-week holding cost / `storage_loss_pct_per_week`.** Wanted for three independent
  reasons (prices holding, models real shrink, makes minimum-inventory strictly optimal), but
  not needed for §3 to be correct. It IS needed before shelf-life defaults go above ~4 weeks
  (§3.4).
- **A third storage regime** (cool-wet, 45–55 °F: tomatoes, cucumbers, peppers, melon, basil).
  The two-value enum collapses it into whichever bucket you pick. Tolerable only while every
  crop in that group has a ≤2-week shelf life — revisit if that stops being true.
- **`max_harvest_m3_per_week`** — v3 leaves no volumetric throughput cap at all (§3.3).

**Open product decisions** (not engineering calls — do these with the owner):
potatoes' storage type; conservative vs honest-realistic shelf-life defaults; whether the demo
crop set changes to exercise §3.3; and whether `shelf_life_weeks: 1` means the harvest week
only or harvest week + 1 (an off-by-one that doubles every perishable's flexibility).

A stronger *external* second opinion on §4–§5 is still desirable — those two sections have had
only the Flash pass, which §3.0 has now shown to be worth less than it appeared. §3 has been
adversarially reviewed against running code and no longer needs one.
