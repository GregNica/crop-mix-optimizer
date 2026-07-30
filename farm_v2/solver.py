"""
solver.py — Core MILP solver for the 52-week farm optimization model v2.

Entry point: ``solve_farm_v2(**params)``

Variable layout (all collected into one flat vector ``z`` for scipy.milp):
  0 .. N_S-1               x[i]           — succession land fraction (continuous)
  N_S .. 2*N_S-1           y[i]           — binary plant/no-plant
  2*N_S .. 2*N_S+V_off-1   v[c,ch,w]      — channel sales in lbs (continuous)
  next n_crops*52          inv[c,w]       — lbs held at END of week w (continuous)
  next n_crops*52          waste[c,w]     — lbs discarded in week w (continuous)
  then, when enabled:      city_water[w], overtime[w], hire[w]  — 52 each

Constraint order (rows of A):
  C1   land (52)
  C2   labor (52)
  C3   water (52)
  C4a  inventory balance — EQUALITY, inv[c,0]=0 (n_crops × 52)
  C4b  storage capacity on room occupancy — cold pool then ambient pool (2 × 52)
  C4c  shelf life — rolling bound on inv (n_crops × 52)
  C6   sales ≤ WEEKLY sales-capacity cap (skipped for annual-cap channels)
  C6b  sales ≤ ANNUAL cap — one row per crop-channel that has one
  C8   crop diversity — annual acre-weeks per crop (n_crops)
  C9   binary linkage upper x[i] ≤ y[i]  (N_S)
  C15  committed acres — floor on ground STANDING in week 1 (one row per committed crop)
  C10  min acreage lower   x[i] ≥ y[i]×min_frac  (N_S)
  C11  max plant acres/week (52)
  C12  max harvest acres/week (52)
  C13  weekly cash floor — cumulative cash ≥ -(opening_cash + credit_line) (52)
  C14  overtime lower bound (52, optional)

C4 (harvest-week storage), C5a/C5b (per-week supply + spread window) and C7 (production ≤
one week's demand) were deleted in Phase B.2; the inventory core above replaces all four.
See SPEC_v3.md §3.
"""

from __future__ import annotations

import math
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import csr_matrix

from farm_v2.utils.calendar import (
    generate_successions,
    build_phase_table,
    harvest_weeks_of,
)
from farm_v2.utils.water import (
    compute_free_water,
    compute_net_water_rates,
    RAINFALL_OFFSET_FRACTION,
    CATCHMENT_EFFICIENCY,
)
from farm_v2.utils.labor import compute_labor_arrays, compute_labor_rates
from farm_v2.utils.demand import build_demand_table, build_annual_caps
from farm_v2.validate import validate_params


# How full a resource or a demand cap has to be before the reports call it "at its limit".
# One constant because it is one concept: `_diagnose_unplanted_crops` uses it to decide whether
# a resource was tight enough to name as context, and `demand_saturation` uses it to decide
# which weeks a channel sold its cap out in. It is published as `demand_at_cap_threshold` so a
# reader can label the column it draws rather than assume a value.
AT_CAP_FRACTION = 0.95


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _vcw_index(c: int, ch: int, w: int, n_channels: int, n_weeks: int) -> int:
    """Flat index into v[c, ch, w] block (0-based within the block)."""
    return c * n_channels * n_weeks + ch * n_weeks + (w - 1)


# Holding tie-break, $/lb/week. Module-level so tests can assert on the ACTUAL value —
# a test that re-types the number cannot detect the number changing. See its use in the
# objective for why it exists and why it must stay negligible.
INVENTORY_TIE_BREAK_PER_LB_WEEK = 1e-6

# Plant-flag tie-break, $ per planted succession. Same discipline as the holding tie-break
# above: module-level so a test can assert on the ACTUAL value rather than re-typing it.
PLANT_FLAG_TIE_BREAK = 1e-6

# Water-level tie-break, $/litre/week. Tiny because a tank holds millions of litres:
# 5e-12 x 500,000 L x 52 wk is well under a ten-thousandth of a cent.
WATER_LEVEL_TIE_BREAK_PER_L_WEEK = 5e-12


def _cw_index(c: int, w: int, n_weeks: int) -> int:
    """Flat index into a per-crop-per-week block (inv, waste), 0-based within the block."""
    return c * n_weeks + (w - 1)


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def _diagnose_unplanted_crops(
    crops, successions, crop_contribution, annual_caps, demand_table, excluded_channels,
    capacity_series, phase_table, n_weeks,
):
    """Say WHY each crop got zero acres — as DATA, not as sentences.

    A crop can reach zero from at least four causes and only one (the margin hurdle) had any
    banner; the rest were indistinguishable to the grower. This returns a structured record per
    unplanted crop and leaves the wording to the presentation layer, which is where the locked
    rule puts it — the solver owns the numbers, the UI renders them — and which a future
    assistant needs, since it cannot narrate from prose it would have to re-parse.

    `outcompeted` is deliberately the weakest claim available. An LP declines a whole bundle at
    these prices; it does not reject a crop for one reason. `tightest` is therefore reported as
    context, never as the cause, and only when a resource is genuinely near its limit.
    """
    out = []
    # Gate on a POSITIVE cap, not on key presence: a channel of type "annual" with a volume
    # of 0 — which is what a blank demand box sends — still has a key here. Keying on
    # presence made `no_demand` unreachable for such a crop and reported it as
    # `outcompeted`, i.e. "plantable and sellable, but did not earn its place", when in
    # fact it had nowhere at all to be sold.
    annual_crops = {c for (c, _ch), cap in (annual_caps or {}).items() if cap > 0}
    excluded_by_crop = {}
    for e in (excluded_channels or []):
        # Entries are always keyed by crop NAME where they are built.
        excluded_by_crop.setdefault(e.get("crop"), []).append(e.get("channel"))

    for c_idx, crop in enumerate(crops):
        name = crop.get("name", f"Crop {c_idx + 1}")
        if float((crop_contribution.get(name) or {}).get("acres_planted", 0.0)) > 1e-6:
            continue

        succ_idx = [i for i, s in enumerate(successions) if s["crop"] == c_idx]
        cycle_weeks = int(round(float(crop.get("days_to_maturity", 0)) / 7.0))
        rec = {
            "crop": name,
            "cycle_weeks": cycle_weeks,
            "min_acres": float(crop.get("min_acreage_if_planted", 0.0) or 0.0),
            "excluded_channels": excluded_by_crop.get(name) or [],
            "tightest": None,
        }

        if not succ_idx:
            rec["reason"] = "no_plantable_window"
            out.append(rec)
            continue

        sellable = float(np.sum(np.where(np.isfinite(demand_table[c_idx]),
                                         demand_table[c_idx], 0.0)))
        if sellable <= 0.0 and c_idx not in annual_crops:
            rec["reason"] = ("all_channels_excluded" if rec["excluded_channels"]
                             else "no_demand")
            out.append(rec)
            continue

        if capacity_series:
            weeks = sorted({w for i in succ_idx for w in range(1, n_weeks + 1)
                            if phase_table[i][w] is not None})
            best = -1.0
            for res_name, series in capacity_series.items():
                used, cap = series.get("used") or [], series.get("cap") or []
                for w in weeks:
                    if w - 1 < len(used) and w - 1 < len(cap) and cap[w - 1] > 0:
                        ratio = used[w - 1] / cap[w - 1]
                        if ratio > best:
                            best = ratio
                            if ratio >= AT_CAP_FRACTION:
                                rec["tightest"] = {"resource": res_name, "week": w,
                                                   "utilization": float(ratio)}
        rec["reason"] = "outcompeted"
        out.append(rec)

    return out


def solve_farm_v2(
    # --- Farm infrastructure ---
    total_land: float,
    opening_cash: float,             # cash on hand at start of year
    credit_line: float,              # maximum operating credit (line of credit)
    harvest_storage_cap: float,      # m³
    # --- Fixed cost rates ---
    operating_weeks: int,            # DEPRECATED: accepted, but no longer scales any cost (Step 4)
    rate_harvest_storage: float,     # $/m³/week
    rate_water_storage: float,       # $/liter/week (for any on-farm water tank)
    rate_irrigation: float,          # $/acre/week
    rate_equip_storage: float,       # $/m³/week
    rate_fuel_storage: float,        # $/liter/week
    rate_machinery: float,           # $/week
    equip_storage: float,            # m³
    fuel_storage: float,             # liters
    water_storage_capacity: float,   # liters (for fixed cost; 0 if no tank)
    # --- Water ---
    rainfall_weekly_L_per_acre: np.ndarray,   # shape (52,)
    catchment_enabled: bool = False,
    catchment_surface_area_m2: float = 0.0,
    catchment_efficiency: float = CATCHMENT_EFFICIENCY,
    well_enabled: bool = False,
    well_weekly_cap_L: float = 0.0,
    well_cost_per_L: float = 0.0,
    city_water_enabled: bool = False,
    city_water_cost_per_L: float = 0.0,
    city_water_fixed_fee_per_week: float = 0.0,
    rainfall_offset_fraction: float = RAINFALL_OFFSET_FRACTION,
    # --- Labor ---
    year_round_employees: list | None = None,
    seasonal_employees: list | None = None,
    overtime_enabled: bool = False,
    overtime_rate_multiplier: float = 1.5,
    max_overtime_hrs_per_week: float | None = None,
    hire_enabled: bool = False,
    max_hire_hrs_per_week: float = 0.0,
    hire_wage_markup: float = 0.0,
    # --- Equipment proxy ---
    max_plant_acres_per_week: float = 1e9,
    max_harvest_acres_per_week: float = 1e9,
    # --- Additional fixed costs ---
    rate_property_mortgage_rent: float = 0.0,  # $/week — land lease or mortgage payment
    other_debt_service_per_week: float = 0.0,  # $/week — P&I on other long-term loans (buildings, land improvements, carried debt) not already in the machinery/property lines
    fixed_selling_per_week: float = 0.0,       # $/week — channel fixed selling (stall fees, retainers); in cash flow only, P&L handles it below the line
    # --- Storage shrink ---
    # Weight lost per week in store: respiration, moisture loss, trimming, sorting out rots.
    # SPEC_v3 §3.4. This is what makes holding COST something — without it a long shelf life is
    # pure upside in the objective, so honest shelf lives cannot be entered before it exists
    # (the reason it is a hard prerequisite of the crop-data audit's Phase B). Per-crop override
    # via crop["storage_loss_frac_per_week"]; garlic and onions are a few tenths of a percent a
    # week, leafy greens several percent.
    # A FRACTION, not a percent — 0.05 means 5%/week. Named explicitly because `_pct` means
    # 0-100 everywhere else here, and the 0-0.99 clamp would silently turn a "5" into 99%/wk.
    # Ships at 0.0 = no shrink = today's behaviour exactly. Values arrive with their sources.
    storage_loss_frac_per_week: float = 0.0,
    # --- Ambient (non-refrigerated) produce storage ---
    # A second pool for crops whose `cold_storage` flag is False: cured alliums, winter squash
    # (chilling-injured below 50°F), potatoes. It is CAPPED and PRICED, never free — an
    # uncapped ambient pool was measured as a $91,274/yr exploit, since marking every crop
    # ambient then removes storage cost from the plan without changing it. Barn space is
    # cheap (~$120/m³ against ~$500/m³ refrigerated), not free.
    ambient_storage_cap: float = 0.0,      # m³
    rate_ambient_storage: float = 0.0,     # $/m³/week
    # --- Cash flow constraint ---
    cash_constraint_enabled: bool = True,  # if False, skip C13 weekly cash floor entirely
    # --- Realism factors (sell-through in-objective; overhead & interest below the line) ---
    min_viable_margin_pct: float = 0.0,   # 0 = off; see Step 3b
    sell_through_fraction: float = 1.0,    # FARM-WIDE DEFAULT fraction of harvest that converts to sellable product (shrink/grade-out/spoilage). Per-crop override via crop["sell_through_fraction"]. Scales C5/C7 production→sales link, so the farm grows more to deliver the cap.
    overhead_pct_of_revenue: float = 0.0,  # indirect overhead (insurance, tax, admin, utilities, R&M, vehicle/office) as a share of revenue; deducted post-solve
    interest_rate_apr: float = 0.0,        # APR charged on the solved weekly operating borrowing; deducted post-solve
    # --- Variable cost rates ---
    cost_fert_per_lb: float = 0.0,
    cost_fuel_per_L: float = 0.0,
    # --- Crops and channels ---
    crops: list | None = None,
    channels: list | None = None,
    # --- Year ---
    year: int = 2024,
    # --- Solver options ---
    solver_time_limit: float = 80.0,
) -> dict:
    """
    Solve the 52-week farm MILP and return a results dict.

    Returns
    -------
    dict with keys:
        "status"            : str  ("optimal", "infeasible", "unbounded", ...)
        "profit"            : float
        "revenue"           : float
        "variable_cost"     : float
        "fixed_cost"        : float
        "weekly_cash_flow"  : np.ndarray (53,) — cumulative cash by week (index 0 unused)
        "peak_borrowing"    : float — maximum credit drawn at any week
        "x"                 : np.ndarray — succession land fractions
        "y"                 : np.ndarray — succession binary (plant/no-plant)
        "v"                 : np.ndarray — channel sales (n_crops, n_channels, 53)
        "channel_sales"     : dict — the reportable form of `v`:
                              {channel: {"lbs_sold", "revenue",
                                         "by_crop": {crop: {"lbs_sold", "revenue",
                                                            "weekly_lbs": [52]}}}}
                              Channel revenues sum to "revenue"; weekly_lbs sums to lbs_sold.
        "demand_saturation" : dict — how full each crop-channel's demand is, measured against
                              the row the solver enforces (C6 weekly, or C6b annual):
                              {channel: {crop: {"basis", "cap_lbs", "sold_lbs", "fill",
                                                "peak_week_frac", "peak_week_cap_lbs",
                                                "weeks_at_cap", "binding"}}}
                              `binding` is the utilisation of the enforced row and is the
                              What-If ranking's basis. See the note where it is built for why
                              an annual figure alone is not enough.
        "demand_at_cap_threshold" : float — the utilisation at which a week counts as "at cap"
                              in `weeks_at_cap`. Published so a reader can LABEL the column it
                              renders instead of assuming; the constraint CSV wrote these counts
                              under a ">=100%" heading while they were measured at >=95%.
        "successions"       : list[dict]
        "crops"             : list[dict]
        "channels"          : list[dict]
    """
    # Missing collections are normalised to empty and left to validate_params below, so there
    # is ONE contract for bad input: solve_farm_v2 returns `invalid_input` with a reason and
    # never raises for it. Raising here meant `crops=None` threw while `crops=[]` returned a
    # status dict — same category of mistake, two different things for a caller to handle.
    crops = crops or []
    channels = channels or []
    if year_round_employees is None:
        year_round_employees = []
    if seasonal_employees is None:
        seasonal_employees = []

    N_WEEKS = 52
    n_crops    = len(crops)
    n_channels = len(channels)

    # -----------------------------------------------------------------------
    # Step 0 — Pre-flight validation (audit 1.4 / S1)
    # -----------------------------------------------------------------------
    # This is the point every caller converges on: the Optimize button, the What-If sweep,
    # the sensitivity runs, Monte Carlo, the tests, and the server path that does not exist yet.
    #
    # Errors are RETURNED, not raised: callers already branch on `status`, and a traceback is
    # not an error message. A crash in the guard itself fails OPEN but LOUD — it costs the
    # check, not the plan, and says so in the warnings.
    validation_warnings: list[str] = []
    try:
        validation_warnings = validate_params(
            total_land=total_land,
            harvest_storage_cap=harvest_storage_cap,
            operating_weeks=operating_weeks,
            crops=crops,
            channels=channels,
            rainfall_weekly_L_per_acre=rainfall_weekly_L_per_acre,
            opening_cash=opening_cash,
            credit_line=credit_line,
            year_round_employees=year_round_employees,
            seasonal_employees=seasonal_employees,
            city_water_enabled=city_water_enabled,
            well_enabled=well_enabled,
            catchment_enabled=catchment_enabled,
            catchment_surface_area_m2=catchment_surface_area_m2,
            well_weekly_cap_L=well_weekly_cap_L,
            year=year,
        ) or []
    except ValueError as ve:
        return {
            "status": "invalid_input",
            "profit": None,
            "errors": [str(ve)],
            "warnings": [],
            "crops": crops,
            "channels": channels,
            "successions": [],
        }
    except Exception as ge:
        # A guard that crashes must not cost a computable plan — but it must not go quiet
        # either. Silently continuing is how this branch has shipped inert guards before, and
        # this exact path swallowed a NameError of mine while the guard lived in the adapter.
        validation_warnings = [
            f"Pre-flight checks could not run ({type(ge).__name__}: {ge}). The plan was still "
            f"computed, but it was NOT checked for bad inputs."
        ]

    # -----------------------------------------------------------------------
    # Step 1 — Generate successions and lookup tables
    # -----------------------------------------------------------------------
    successions = generate_successions(crops, year)
    N_S = len(successions)
    if N_S == 0:
        # Normally unreachable — validate_params raises first and Step 0 turns it into
        # `invalid_input`. It is reached only when the guard itself crashed and Step 0 failed
        # open, so RETURN rather than raise: failing open must not cost a caller its contract.
        return {
            "status": "invalid_input",
            "profit": None,
            "errors": [
                "No successions generated for ANY crop. Season windows are PLANTING windows, "
                "so each needs at least one start week whose cycle finishes by week 52 — or the "
                "crop must be marked as overwintering."
            ],
            "warnings": validation_warnings,
            "crops": crops,
            "channels": channels,
            "successions": [],
        }

    phase_table = build_phase_table(successions, N_WEEKS)  # [i][w] = 0/1/2/None

    # -----------------------------------------------------------------------
    # Step 2 — Pre-compute derived arrays
    # -----------------------------------------------------------------------

    # Water
    free_water = compute_free_water(
        rainfall_weekly_L_per_acre,
        catchment_enabled, catchment_surface_area_m2, catchment_efficiency,
        well_enabled, well_weekly_cap_L,
    )  # shape (52,)

    net_water_rate = compute_net_water_rates(
        successions, crops, rainfall_weekly_L_per_acre, rainfall_offset_fraction,
    )  # shape (N_S, 53)

    # Labor
    labor_result = compute_labor_arrays(
        year_round_employees, seasonal_employees, N_WEEKS,
    )
    labor_capacity         = labor_result["labor_capacity"]          # (52,)
    hourly_labor_rate      = labor_result["hourly_labor_rate"]       # (52,)
    salaried_weekly_cost   = labor_result["salaried_weekly_cost"]

    labor_rate = compute_labor_rates(successions, crops, N_WEEKS)  # (N_S, 53)

    # Demand
    demand_table = build_demand_table(crops, channels, N_WEEKS)  # (n_crops, n_ch, 53)
    annual_caps  = build_annual_caps(crops, channels)            # {(c, ch): lbs/yr}

    # Fert and fuel rate arrays per succession per week
    _FERT_KEY = ["fert_plant", "fert_grow", "fert_harv"]
    _FUEL_KEY = ["fuel_plant", "fuel_grow", "fuel_harv"]

    fert_rate = np.zeros((N_S, N_WEEKS + 1), dtype=float)
    fuel_rate  = np.zeros((N_S, N_WEEKS + 1), dtype=float)
    for i, s in enumerate(successions):
        crop = crops[s["crop"]]
        for week, phase in zip(s["weeks"], s["phases"]):
            if 1 <= week <= N_WEEKS:
                fert_rate[i][week] = crop.get(_FERT_KEY[phase], 0.0)
                fuel_rate[i][week]  = crop.get(_FUEL_KEY[phase], 0.0)

    # -----------------------------------------------------------------------
    # Step 3 — Variable cost: total annual coefficient + weekly breakdown
    #
    # var_cost_coeff[i]     = total $/land-fraction  (annual, for objective)
    # var_cost_weekly[i][w] = $/land-fraction in week w (for cash flow constraints)
    # -----------------------------------------------------------------------
    var_cost_coeff  = np.zeros(N_S, dtype=float)
    var_cost_weekly = np.zeros((N_S, N_WEEKS + 1), dtype=float)
    vc_split        = np.zeros((N_S, 5), dtype=float)   # labor, water, fert, fuel, seed

    for i, s in enumerate(successions):
        crop = crops[s["crop"]]
        seed_cost = crop.get("seed_transplant_cost_per_acre", 0.0)

        # Seed cost charged in the first week of the succession
        first_week = s["weeks"][0] if s["weeks"] else None
        if first_week and 1 <= first_week <= N_WEEKS:
            seed_total = total_land * seed_cost
            var_cost_weekly[i][first_week] += seed_total
            var_cost_coeff[i] += seed_total
            vc_split[i, 4] += seed_total

        for w in range(1, N_WEEKS + 1):
            if phase_table[i][w] is None:
                continue
            water_c = total_land * net_water_rate[i][w] * well_cost_per_L
            fert_c  = total_land * fert_rate[i][w] * cost_fert_per_lb
            fuel_c  = total_land * fuel_rate[i][w] * cost_fuel_per_L
            labor_c = total_land * labor_rate[i][w] * hourly_labor_rate[w - 1]
            week_c  = water_c + fert_c + fuel_c + labor_c
            var_cost_weekly[i][w] += week_c
            var_cost_coeff[i]     += week_c
            # Keep the split. The UI used to re-multiply hours x a scalar rate to show a cost
            # breakdown, which could never reproduce these numbers: labour is priced at the
            # week's own blended wage and water at the RAINFALL-ADJUSTED requirement. Returning
            # the products the objective actually charged is the only way the displayed
            # breakdown can agree with the plan.
            vc_split[i, 0] += labor_c
            vc_split[i, 1] += water_c
            vc_split[i, 2] += fert_c
            vc_split[i, 3] += fuel_c

    # Cumulative variable cost per succession up to week W: cum_var[i, W]
    # cum_var[i, W] = Σ_{w=1}^{W} var_cost_weekly[i][w]
    cum_var = np.zeros((N_S, N_WEEKS + 1), dtype=float)
    for i in range(N_S):
        running = 0.0
        for w in range(1, N_WEEKS + 1):
            running += var_cost_weekly[i][w]
            cum_var[i, w] = running

    # Net price per crop-channel (for cash flow constraint coefficients)
    net_price = np.zeros((n_crops, n_channels), dtype=float)
    for c_idx, crop in enumerate(crops):
        for ch_idx, ch in enumerate(channels):
            ch_spec = crop.get("channels", {}).get(ch["name"], {})
            net_price[c_idx, ch_idx] = (
                ch_spec.get("price_per_lb", 0.0)
                - ch_spec.get("packaging_cost_per_lb", 0.0)
            )

    # Overhead is overhead_pct × gross revenue, so each lb sold carries this overhead share.
    # net_after_price = revenue net of packaging AND overhead — used in the objective and the
    # cash-flow floor (C13) so the optimizer and the solvency check both see overhead.
    gross_price = np.zeros((n_crops, n_channels), dtype=float)
    for c_idx, crop in enumerate(crops):
        for ch_idx, ch in enumerate(channels):
            gross_price[c_idx, ch_idx] = crop.get("channels", {}).get(
                ch["name"], {}).get("price_per_lb", 0.0)
    overhead_price  = overhead_pct_of_revenue * gross_price
    net_after_price = net_price - overhead_price

    # -----------------------------------------------------------------------
    # Step 3b — Contribution margin per crop x channel (audit 1.3 / SPEC_v3 §8)
    # -----------------------------------------------------------------------
    # ONE margin kernel, built from the arrays the objective itself uses, and returned in the
    # result so the UI renders these numbers instead of recomputing them. Three JS copies used
    # to each recompute this with hard-coded rates the model never charges ($20/hr labour,
    # $0.002/L water), so the app disagreed with its own optimizer about which channels made
    # money — while the same wrong numbers were used to DROP channels before the solve.
    #
    # Per pound sold, the objective credits net_after_price (price - packaging - overhead
    # share) and pays the growing cost. Only sell_through of what is grown can be sold, so the
    # full growing cost is carried by the sold pounds.
    var_cost_per_lb = np.zeros(n_crops, dtype=float)
    for c_idx, crop in enumerate(crops):
        ypa = float(crop.get("yield_per_acre", 0.0) or 0.0)
        stf = float(crop.get("sell_through_fraction", sell_through_fraction) or 0.0)
        sold_lbs_per_unit_x = total_land * ypa * stf          # lbs sold when x[i] = 1
        costs = [
            var_cost_coeff[i] / sold_lbs_per_unit_x
            for i, s in enumerate(successions)
            if s["crop"] == c_idx and sold_lbs_per_unit_x > 0
        ]
        var_cost_per_lb[c_idx] = float(np.mean(costs)) if costs else 0.0

    # Land-occupancy days per crop: planting through the LAST harvest week, not days-to-maturity
    # — a crop harvested over several weeks occupies the ground for all of them, and charging it
    # only to maturity would overstate its earning rate.
    occupancy_days = np.zeros(n_crops, dtype=float)
    for c_idx in range(n_crops):
        lens = [len(s["weeks"]) * 7.0 for s in successions if s["crop"] == c_idx and s["weeks"]]
        occupancy_days[c_idx] = float(np.mean(lens)) if lens else 0.0

    # Per-acre variable cost split for each crop, from the products the objective charged.
    # var_cost_coeff/vc_split are "cost when x=1", i.e. for total_land acres, so divide out.
    cost_split_per_acre = {}
    for c_idx, crop in enumerate(crops):
        rows = [vc_split[i] for i, sc in enumerate(successions) if sc["crop"] == c_idx]
        if rows and total_land > 0:
            mean = np.mean(np.vstack(rows), axis=0) / total_land
        else:
            mean = np.zeros(5, dtype=float)
        cost_split_per_acre[crop["name"]] = {
            "labor": float(mean[0]), "water": float(mean[1]), "fert": float(mean[2]),
            "fuel":  float(mean[3]), "seed":  float(mean[4]),
            "total": float(mean.sum()),
        }

    channel_margins = {}
    for c_idx, crop in enumerate(crops):
        ypa = float(crop.get("yield_per_acre", 0.0) or 0.0)
        stf = float(crop.get("sell_through_fraction", sell_through_fraction) or 0.0)
        sold_lbs_per_acre = ypa * stf
        for ch_idx, ch in enumerate(channels):
            gross = gross_price[c_idx, ch_idx]
            if gross <= 0:
                continue
            per_lb = net_after_price[c_idx, ch_idx] - var_cost_per_lb[c_idx]
            # $/acre/DAY: what an acre earns for each day this crop occupies it. Acre-days are
            # the farm's scarce resource, so this is the honest way to rank what to put in a
            # slot. It replaces a "$/acre/year" figure the UI computed as 365/days_to_maturity,
            # which assumed a crop could be regrown all year — Basil got 10.43 cycles where its
            # season allows 4 — and which reordered the rankings, not just inflated them.
            # Whether the rest of the year can be refilled is the OPTIMIZER's question, and it
            # is answered by the plan itself, not by a formula in a summary.
            days = occupancy_days[c_idx]
            per_acre_day = (per_lb * sold_lbs_per_acre / days) if days > 0 else 0.0
            split = dict(cost_split_per_acre[crop["name"]])
            split["packaging"] = float(
                crop.get("channels", {}).get(ch["name"], {}).get("packaging_cost_per_lb", 0.0)
                * sold_lbs_per_acre)
            # Overhead is INTERNALISED in the objective (net_after_price subtracts
            # overhead_pct x gross), so it must appear in the cost split too — otherwise the
            # displayed row does not reconcile: Revenue - Cost came out ABOVE Margin by exactly
            # the overhead share, with no line to explain the gap.
            split["overhead"] = float(overhead_pct_of_revenue * gross * sold_lbs_per_acre)
            split["total"] = float(split["total"] + split["packaging"] + split["overhead"])
            channel_margins.setdefault(crop["name"], {})[ch["name"]] = {
                "margin_per_lb": float(per_lb),
                "margin_pct": float(per_lb / gross * 100.0),
                "margin_per_acre_day": float(per_acre_day),
                "margin_per_acre_cycle": float(per_acre_day * days),
                "occupancy_days": float(days),
                "gross_price_per_lb": float(gross),
                "revenue_per_acre": float(gross * sold_lbs_per_acre),
                "sold_lbs_per_acre": float(sold_lbs_per_acre),
                "var_cost_per_lb": float(var_cost_per_lb[c_idx]),
                # The breakdown the row tooltip renders — the objective's own products, so the
                # displayed split always sums to the cost that produced the plan.
                "cost_per_acre": split,
            }

    # Margin hurdle: zero the demand of any crop-channel below the floor, BEFORE the solve.
    # Default 0 disables it. Deliberately opt-in: with honest margins any positive floor also
    # excludes channels that are contribution-POSITIVE per pound but thin on a standalone
    # per-acre basis, which costs real profit in a shared-acreage model.
    excluded_channels = []
    if min_viable_margin_pct > 0:
        for c_idx, crop in enumerate(crops):
            for ch_idx, ch in enumerate(channels):
                m = channel_margins.get(crop["name"], {}).get(ch["name"])
                if m is not None and m["margin_pct"] < min_viable_margin_pct:
                    demand_table[c_idx, ch_idx, :] = 0.0
                    excluded_channels.append({
                        "crop": crop["name"], "channel": ch["name"],
                        "margin_pct": m["margin_pct"], "floor_pct": float(min_viable_margin_pct),
                    })

    # -----------------------------------------------------------------------
    # Step 4 — Fixed cost
    # -----------------------------------------------------------------------
    # Every recurring fixed line is charged over the FULL year (N_WEEKS = 52), never over
    # `operating_weeks`. Ownership does not pause off-season: a barn keeps depreciating and a
    # loan keeps accruing whether or not anything is planted, and the depreciation rates are
    # themselves derived as capital / (life_years * 52). Charging them over a shorter season
    # understated an owned-asset farm by ~$17k/yr at 48 weeks and ~$52k at 36. Salaried payroll
    # was already correct here (* N_WEEKS), which made the expression internally inconsistent.
    # Costs that genuinely stop when nothing is planted already scale on their own: metered
    # consumables are charged per unit of usage, overhead is a share of revenue, and interest
    # comes off the cash curve. `operating_weeks` is therefore accepted for backwards
    # compatibility but no longer multiplies anything (SPEC_v3 N2/N3).
    irrigation_fixed = total_land * rate_irrigation * N_WEEKS
    fixed_cost = (
        harvest_storage_cap * rate_harvest_storage * N_WEEKS
        + ambient_storage_cap * rate_ambient_storage * N_WEEKS
        + water_storage_capacity * rate_water_storage * N_WEEKS
        + irrigation_fixed
        + equip_storage * rate_equip_storage * N_WEEKS
        + fuel_storage * rate_fuel_storage * N_WEEKS
        + rate_machinery * N_WEEKS
        + rate_property_mortgage_rent * N_WEEKS
        + other_debt_service_per_week * N_WEEKS
        + salaried_weekly_cost * N_WEEKS
    )
    if city_water_enabled and city_water_fixed_fee_per_week > 0:
        fixed_cost += city_water_fixed_fee_per_week * N_WEEKS

    fixed_weekly = fixed_cost / N_WEEKS  # fixed cost spread evenly per week

    # -----------------------------------------------------------------------
    # Step 5 — Decision variable layout
    # -----------------------------------------------------------------------
    V_off = n_crops * n_channels * N_WEEKS  # v block size
    INV_off = n_crops * N_WEEKS             # inv[] and waste[] block size
    idx_x_start   = 0
    idx_y_start   = N_S
    idx_v_start   = 2 * N_S
    # inv[c,w] — lbs of crop c held in storage at the END of week w.
    # waste[c,w] — lbs discarded in week w (free disposal: earns nothing, costs nothing more).
    # Both always present: the inventory balance (C4′) is an equality, so `waste` is what keeps
    # a shelf-life bound from forcing sales that demand cannot absorb — turning a modelling
    # limit into an infeasibility is the B1 failure this rewrite exists to remove.
    idx_inv_start   = idx_v_start + V_off
    idx_waste_start = idx_inv_start + INV_off
    # Sequentially lay out the optional weekly variable blocks after the fixed ones.
    _next = idx_waste_start + INV_off
    # Two allocation conventions live here, on purpose. city water / overtime / hire are gated
    # on an explicit *_enabled flag because each carries its own cost rate and cap that would be
    # wrong to allocate at zero. wstore below is gated on its CAPACITY instead: its off state is
    # a single scalar collapse with no separate wiring, so allocating it unconditionally avoids
    # forking one flow-balance row. Pick deliberately when adding the next optional resource.
    idx_cw_start = None
    if city_water_enabled:
        idx_cw_start = _next; _next += N_WEEKS
    idx_ot_start = None
    if overtime_enabled:
        idx_ot_start = _next; _next += N_WEEKS
    idx_hire_start = None
    if hire_enabled:
        idx_hire_start = _next; _next += N_WEEKS
    # wstore[w] — litres held in the on-farm tank at the END of week w. Always allocated: when
    # water_storage_capacity is 0 the whole block is bounded to 0 and presolve removes it,
    # which keeps ONE water balance in the code instead of a tank path and a no-tank path.
    idx_ws_start = _next; _next += N_WEEKS
    n_vars = _next

    # -----------------------------------------------------------------------
    # Step 6 — Objective (scipy.milp minimises, so negate profit)
    # -----------------------------------------------------------------------
    c_obj = np.zeros(n_vars)

    # Succession variable costs (add to -profit)
    c_obj[idx_x_start : idx_x_start + N_S] = var_cost_coeff

    # Channel sales revenue minus packaging cost, minus INTERNALIZED overhead.
    # Overhead = overhead_pct × gross revenue, so each lb sold carries an overhead share of
    # overhead_pct × price. Subtracting it here makes the optimizer maximize AFTER-overhead
    # profit — it won't chase production whose margin doesn't clear its overhead bar. (Interest
    # stays below-the-line; post-solve accounting/reporting is unchanged.)
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            net_after = net_after_price[c_idx, ch_idx]
            for w in range(1, N_WEEKS + 1):
                flat_idx = idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                c_obj[flat_idx] -= net_after

    # City water cost
    if city_water_enabled and idx_cw_start is not None:
        c_obj[idx_cw_start : idx_cw_start + N_WEEKS] = city_water_cost_per_L

    # Holding tie-break — a numerical device, NOT economics.
    #
    # The balance pins inventory GIVEN a sales schedule, but the schedule itself is degenerate
    # whenever a pound can be sold this week or next at the same price with demand to spare.
    # Both plans earn identically, so HiGHS picks arbitrarily and the returned `inventory`
    # series moves on a 1e-9 nudge — measured at 29,077 lb on the six-crop fixture. That is
    # the same defect the periodic boundary had (SPEC_v3 §3.0a): a reported series that is not
    # a function of the inputs. Refusing it there and tolerating it here would be incoherent.
    #
    # An arbitrarily small positive cost on held stock makes "sell sooner, hold less" strictly
    # optimal and the series unique, without changing which plan wins: at 1e-6 $/lb/week the
    # whole tie-break is worth about $2 against a ~$900k objective, four orders below the
    # golden farm's $50 noise floor, and it is ~6 orders below any real per-lb margin so it can
    # never make discarding a sellable pound look better than selling it.
    #
    # It is deliberately NOT in the reported P&L, so the objective and `profit` differ by its
    # value. That is the same reported-vs-optimized gap the audit killed in the labor-flex
    # reconstruction (F1/N1), and it is tolerated here only because it is bounded at well
    # under a dollar and pinned there by a test. The clean alternative is a lexicographic
    # two-stage solve (maximize profit, then minimize inventory subject to that profit), which
    # doubles solve time to buy nothing a grower can see.
    #
    # SPEC_v3 §3.4 supersedes this with a real per-crop `storage_loss_frac_per_week`, which is
    # wanted anyway to model shrink and to stop long shelf lives being free money. When that
    # lands, delete this.
    c_obj[idx_inv_start : idx_inv_start + INV_off] = INVENTORY_TIE_BREAK_PER_LB_WEEK

    # Plant-flag tie-break — makes y[i] mean what its name says. See the y upper-bound note
    # below for why y is otherwise free when min_acreage_if_planted is 0.
    #
    # A vanishing cost makes the minimum strictly optimal, exactly as the holding tie-break
    # above does for inventory. Bounded by a test: at 1e-6 per succession, a farm planting all
    # ~155 of them pays under a fifth of a cent.
    c_obj[idx_y_start : idx_y_start + N_S] += PLANT_FLAG_TIE_BREAK

    # Water-level tie-break — the tank level is PUBLISHED, so it has to be a function of the
    # inputs rather than of a solver tie-break. wstore carries no cost of its own, so in any
    # week where water is slack the level is degenerate: measured on the 29-crop fixture, weeks
    # 1-3 left the tank empty against 16.35 M L of slack while week 3 filled it to exactly
    # capacity. `capacity_series["water"]["cap"]` is built from these values and the client
    # divides `used` by it for utilisation and bottleneck ranking, so two runs of the same plan
    # could report different water pressure. This is the same defect
    # INVENTORY_TIE_BREAK_PER_LB_WEEK exists to prevent; refusing it there and tolerating it
    # here would be incoherent. Minimum-storage is now strictly optimal.
    c_obj[idx_ws_start : idx_ws_start + N_WEEKS] += WATER_LEVEL_TIE_BREAK_PER_L_WEEK

    # Overtime cost (incremental rate above regular pay)
    if overtime_enabled and idx_ot_start is not None:
        ot_extra_rate = hourly_labor_rate * (overtime_rate_multiplier - 1.0)
        c_obj[idx_ot_start : idx_ot_start + N_WEEKS] = ot_extra_rate

    # Hired-labor cost: only the wage markup above base wage (base wage on every used
    # hour is already in var_cost_coeff). Default markup 0 → hired labor costs base wage.
    if hire_enabled and idx_hire_start is not None:
        c_obj[idx_hire_start : idx_hire_start + N_WEEKS] = hourly_labor_rate * hire_wage_markup

    # -----------------------------------------------------------------------
    # Step 7 — Bounds
    # -----------------------------------------------------------------------
    lb = np.zeros(n_vars)
    ub = np.full(n_vars, np.inf)
    ub[idx_x_start : idx_x_start + N_S] = 1.0  # x[i] ∈ [0, 1]
    # y[i] ∈ {0, 1}. Integrality alone (Step 8) only makes y an INTEGER — without this it is an
    # unbounded non-negative integer, which is not what "plant this succession or not" means and
    # is not what the rest of the model assumes. y appears only in C9 (x ≤ y) and C10
    # (min_frac·y ≤ x), so when min_acreage_if_planted is 0 — a value the form accepts — min_frac
    # is 0, C10 collapses to 0 ≤ x, and y becomes entirely free. Every value of y is then equally
    # optimal: infinitely many optima for branch-and-bound to wander through, and a meaningless
    # y_sol for the "was this planted" report read below. Bounding it costs nothing and restores
    # the documented semantics.
    ub[idx_y_start : idx_y_start + N_S] = 1.0
    # The tank holds at most its capacity. At 0 this pins the block and presolve drops it.
    ub[idx_ws_start : idx_ws_start + N_WEEKS] = float(water_storage_capacity)

    # Per-week caps on the labor-flex levers (the "max additional capacity by period").
    if overtime_enabled and idx_ot_start is not None and max_overtime_hrs_per_week is not None:
        ub[idx_ot_start : idx_ot_start + N_WEEKS] = max_overtime_hrs_per_week
    if hire_enabled and idx_hire_start is not None:
        ub[idx_hire_start : idx_hire_start + N_WEEKS] = max_hire_hrs_per_week

    # -----------------------------------------------------------------------
    # Step 8 — Integrality
    # -----------------------------------------------------------------------
    integrality = np.zeros(n_vars, dtype=int)
    integrality[idx_y_start : idx_y_start + N_S] = 1  # y[i] binary

    # -----------------------------------------------------------------------
    # Step 9 — Constraints
    # -----------------------------------------------------------------------
    rows_A, cols_A, vals_A = [], [], []
    lbs_con, ubs_con = [], []
    row = 0

    def add_row(col_vals, lo, hi):
        nonlocal row
        for c_col, v_val in col_vals:
            rows_A.append(row)
            cols_A.append(c_col)
            vals_A.append(v_val)
        lbs_con.append(lo)
        ubs_con.append(hi)
        row += 1

    # Per-crop shelf life, in weeks. `sales_spread_weeks` is deprecated: it named a sales
    # WINDOW anchored at the LAST harvest week, which double-counted overlapping plantings
    # (B2) and locked a crop out of its own early harvest weeks (F2). Same grower question,
    # honest semantics. Migrated 1:1 here so this commit changes the MECHANISM and not the
    # data, and any profit move is attributable to the rewrite alone.
    # The 8-week ceiling was lifted to N_WEEKS in B.3, and the holding cost that had to precede
    # honest long shelf lives (storage_loss_frac_per_week, above) landed with it — without one,
    # a long shelf life is pure upside in the objective.
    storage_loss = [
        max(0.0, min(0.99, float(c.get("storage_loss_frac_per_week", storage_loss_frac_per_week) or 0.0)))
        for c in crops
    ]
    shelf_life_weeks = [
        max(1, min(N_WEEKS, int(c.get("shelf_life_weeks", c.get("sales_spread_weeks", 1)) or 1)))
        for c in crops
    ]

    # One week's SELLABLE harvest per succession, at x[i] = 1 — the even-split convention.
    # Written once because it used to be hand-typed at every row, sell-through fallback and
    # all, and the copy in C4 forgot both the fallback and the divisor. `harvest_weeks_of`
    # gives the one clamped definition of the denominator.
    succ_weekly_sellable_lbs = []
    succ_n_harv = []
    for i in range(N_S):
        crop_i = crops[successions[i]["crop"]]
        n_harv = max(1, len(harvest_weeks_of(successions[i], N_WEEKS)))  # max(1,…): no div-by-0
        succ_n_harv.append(n_harv)
        st_i = crop_i.get("sell_through_fraction", sell_through_fraction)
        succ_weekly_sellable_lbs.append(st_i * total_land * crop_i["yield_per_acre"] / n_harv)

    # C1 — Land: Σ x[i] ≤ 1 for each week w
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i, 1.0)
            for i in range(N_S)
            if phase_table[i][w] is not None
        ]
        add_row(cols, -np.inf, 1.0)

    # C2 — Labor: Σ x[i]×land×labor_rate ≤ capacity[w] (+ overtime if enabled)
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i, total_land * labor_rate[i][w])
            for i in range(N_S)
            if phase_table[i][w] is not None
        ]
        rhs = labor_capacity[w - 1]
        if overtime_enabled and idx_ot_start is not None:
            cols.append((idx_ot_start + w - 1, -1.0))
        if hire_enabled and idx_hire_start is not None:
            cols.append((idx_hire_start + w - 1, -1.0))
        add_row(cols, -np.inf, rhs)

    # C3 — Water, with the tank actually storing something (audit B7)
    #
    #     wstore[w] ≤ wstore[w-1] + free_water[w] + city_water[w] − use[w]
    #
    # The inequality rather than an equality is what lets surplus be dumped, so no spill
    # variable is needed; with wstore ≥ 0 it also enforces that a week cannot spend water it
    # does not have. At capacity 0 every level pins to 0 and the row collapses to the pure
    # flow balance this replaced — one water constraint, not a tank path and a no-tank path.
    #
    # wstore[0] = 0 — the tank starts the year empty, the same anchoring choice as the
    # inventory balance below and for the same reason: a periodic boundary leaves the level
    # free, so the reported series would not be a physical quantity.
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i, total_land * net_water_rate[i][w])
            for i in range(N_S)
            if phase_table[i][w] is not None and net_water_rate[i][w] > 0
        ]
        if city_water_enabled and idx_cw_start is not None:
            cols.append((idx_cw_start + w - 1, -1.0))
        cols.append((idx_ws_start + w - 1, 1.0))            # +wstore[w]
        if w > 1:
            cols.append((idx_ws_start + w - 2, -1.0))       # −wstore[w-1]
        add_row(cols, -np.inf, free_water[w - 1])

    # C4a — Inventory balance (equality rows, n_crops × 52)
    #
    # Replaces v2's C4 (harvest-week storage), C5a (per-week supply), C5b (cumulative spread
    # window) and C7 (production ≤ one week's demand). SPEC_v3 §3.
    #
    #     inv[c,w] = (1 − loss[c])·inv[c,w-1] + st[c]·H[c,w] − Σ_ch v[c,ch,w] − waste[c,w]
    #     inv[c,0] = 0
    #
    # ⚠️ The boundary is ZERO, not periodic. SPEC_v3 §3.0(a): summing a periodic balance over
    # the year cancels the level, leaving these rows one short of full rank and the inventory
    # LEVEL free — same plan, same profit, peak stock anywhere across a 6× band on a solver
    # tie-break, so the reported series would not be a physical quantity. A periodic boundary
    # also lets a W52 harvest sell in W5 of the same calendar year while C13, interest and
    # peak borrowing are all calendar-anchored. The cost of anchoring at zero is audit item
    # B6 — nothing sells stock grown the previous autumn until §1's cyclic year lands. No
    # shipped template overwinters, so nothing regresses today.
    #
    # Only SELLABLE product enters inventory (st[c] factor): culls are assumed graded out at
    # harvest rather than stored. B.1's C4 took the opposite, conservative reading because it
    # had no way to price holding; this row can, so it takes the more precise one. Expect the
    # reported storage figure to drop by 1/st when this lands — SPEC_v3 §3.3.
    for c_idx in range(n_crops):
        for w in range(1, N_WEEKS + 1):
            cols = [
                (idx_inv_start + _cw_index(c_idx, w, N_WEEKS), 1.0),
                (idx_waste_start + _cw_index(c_idx, w, N_WEEKS), 1.0),
            ]
            if w > 1:
                # -(1 - loss), not -1: a pound carried from last week arrives as (1-loss) pounds.
                # Still linear — the coefficient is a constant, not a variable.
                cols.append((idx_inv_start + _cw_index(c_idx, w - 1, N_WEEKS),
                             -(1.0 - storage_loss[c_idx])))
            cols += [
                (idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS), 1.0)
                for ch_idx in range(n_channels)
            ]
            cols += [
                (idx_x_start + i, -succ_weekly_sellable_lbs[i])
                for i in range(N_S)
                if successions[i]["crop"] == c_idx and phase_table[i][w] == 2
            ]
            add_row(cols, 0.0, 0.0)   # equality

    # C4b — Storage capacity: everything that is IN THE ROOM during the week (2 x 52 rows)
    #
    #     Σ_c m3/lb · ( inv[c,w-1] + st·H[c,w] )  ≤  capacity
    #
    # Opening stock plus this week's harvest — NOT end-of-week stock. A cooler is sized by what
    # passes THROUGH it, not by what sleeps in it: field heat has to come off greens within the
    # hour whether they ship Tuesday or Friday, so produce sold in its own harvest week occupies
    # the room all the same. Measuring end-of-week `inv` reported ZERO storage for a farm that
    # sells everything the week it picks, which is why that number could only ever be published
    # as a lower bound. This form can size a building.
    #
    # Conservative on purpose: the whole week's harvest is counted as being in the room before
    # any of it ships. You size a cooler for the worst Tuesday, not for the weekly average.
    #
    # TWO POOLS, split by the per-crop `cold_storage` flag. Cured storables (garlic, onions,
    # winter squash — chilling-injured below 50°F, so the cooler actively damages it) belong in
    # a barn and must not crowd out the perishables that need refrigeration. Ambient is capped
    # and priced like any other owned building; see the note on `ambient_storage_cap`.
    def _room_cols(w, want_cold):
        cols = []
        for c_idx in range(n_crops):
            if bool(crops[c_idx].get("cold_storage", True)) != want_cold:
                continue
            m3 = crops[c_idx]["crop_size_m3_per_lb"]
            if w > 1:   # inv[c,0] is anchored at zero, so week 1 has no opening stock
                cols.append((idx_inv_start + _cw_index(c_idx, w - 1, N_WEEKS), m3))
            cols += [
                (idx_x_start + i, m3 * succ_weekly_sellable_lbs[i])
                for i in range(N_S)
                if successions[i]["crop"] == c_idx and phase_table[i][w] == 2
            ]
        return cols

    # Kept, not discarded: the reported series is these very columns evaluated against the
    # solution, so "what we publish" and "what we enforce" are the same arithmetic object
    # rather than two derivations a test has to keep in agreement. This branch has shipped a
    # report-vs-enforce divergence twice (B.1's 5x overstatement, and the pre-B.2
    # inflow-vs-held mismatch); this makes the third one unrepresentable.
    cold_room_cols = [_room_cols(w, True) for w in range(1, N_WEEKS + 1)]
    ambient_room_cols = [_room_cols(w, False) for w in range(1, N_WEEKS + 1)]
    for cols in cold_room_cols:
        add_row(cols, -np.inf, harvest_storage_cap)
    for cols in ambient_room_cols:
        # Emitted unconditionally even when no crop is ambient: an all-empty row is 0 <= cap,
        # which presolve drops, and branching on crop data would add a case to reason about
        # for no gain.
        add_row(cols, -np.inf, ambient_storage_cap)

    # C4c — Shelf life: nothing in store is older than L weeks (n_crops × 52 rows)
    #
    #     inv[c,w] ≤ st[c] · Σ_{k=0..L−2} H[c, w−k]
    #
    # L is the number of weeks the crop can be SOLD IN, counting its harvest week. So L=1 means
    # "sold the week it is picked" and bounds held stock to zero — the sum is empty. Decided
    # 2026-07-28: the field previously read L=1 as "harvest week plus one more", which was
    # measured (a W14-15 harvest sold to a W16-only buyer at L=1) and judged not to match what
    # the label promises. Anything relying on the old reading needs its value raised by one.
    #
    # "Inventory cannot exceed what arrived in the last L weeks." A rolling bound, NOT the
    # cumulative construction SPEC_v3 originally specified: §3.0(b) showed those doubled
    # 104-week rows collapse to tautologies in every wrap case (harvest W52, shelf life 1,
    # sold W5 — permitted, bit-identical to no constraint at all). This form is anchor-free,
    # stays correct if §1 later makes the year cyclic (w−k becomes ((w−k−1) mod 52)+1), and
    # runs ~L nonzeros per row against the cumulative form's ~170.
    #
    # `waste` is what makes it satisfiable: product that cannot be sold inside its shelf life
    # is discarded rather than the row forcing a sale demand cannot absorb.
    for c_idx in range(n_crops):
        L = shelf_life_weeks[c_idx]
        if L > N_WEEKS:
            # Unreachable BY CONSTRUCTION: L is clamped to min(N_WEEKS, ...) above. Kept as the
            # attachment point for a future non-perishable sentinel (a crop that genuinely never
            # expires), which is the only way it becomes live. Do not read the row count as if it
            # were.
            continue
        for w in range(1, N_WEEKS + 1):
            # L-1, not L: the harvest week is a SELLING week, not a storage week.
            window = range(max(1, w - L + 2), w + 1)
            cols = [(idx_inv_start + _cw_index(c_idx, w, N_WEEKS), 1.0)]
            for i in range(N_S):
                if successions[i]["crop"] != c_idx:
                    continue
                # A succession can harvest in several of the window's weeks; each contributes
                # one week's inflow, DECAYED by the weeks it has been sitting. Without the
                # (1-loss)^age factor the row bounds shrunken stock against undecayed arrivals,
                # and the slack can only be filled by product older than the shelf life — which
                # is the one thing this row exists to forbid. Measured before the fix: 7.4% of
                # held stock overheld at 5%/wk, 21% at 15%/wk, and the error books revenue on
                # pounds that should have been written off.
                weight = sum((1.0 - storage_loss[c_idx]) ** (w - t)
                             for t in window if phase_table[i][t] == 2)
                if weight:
                    cols.append((idx_x_start + i,
                                 -succ_weekly_sellable_lbs[i] * weight))
            add_row(cols, -np.inf, 0.0)

    # C6 — Channel sales ≤ WEEKLY demand cap
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            for w in range(1, N_WEEKS + 1):
                cap_w = demand_table[c_idx, ch_idx, w]
                # +inf means "no weekly ceiling" — an annual-cap channel, bounded by C6b
                # instead. Emitting the row anyway would be a vacuous `v <= inf`.
                if not np.isfinite(cap_w):
                    continue
                flat_idx = idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                add_row([(flat_idx, 1.0)], -np.inf, cap_w)

    # C6b — Channel sales ≤ ANNUAL demand cap (one row per crop-channel that has one).
    # A yearly total is a sum across weeks, which no per-week row can express; see
    # expand_channel_demand and build_annual_caps in demand.py for the rest.
    #
    # `annual_rows` records WHICH crop-channels this loop actually gave an annual row to, so the
    # reporting side can look it up instead of re-deriving it (W6). `demand_saturation` used to
    # ask the same question a few hundred lines below in a different shape — `annual_caps` plus
    # `not isfinite(weekly_cap).any()` — and the two agreed only because expand_channel_demand
    # happens to return uniformly +inf per channel and the hurdle happens to zero the slice.
    # Reporting against "the row the solver actually enforces" is the whole point of W6, so which
    # row exists should be recorded where the row is created, not inferred twice. This mirrors
    # cold_room_cols / ambient_room_cols, which are captured at construction and evaluated later.
    annual_rows = set()
    for (c_idx, ch_idx), annual_lbs in annual_caps.items():
        # A channel dropped by the margin hurdle has its weekly caps zeroed above, which
        # already forces v to 0; the annual row would be slack. Skip it rather than carry a row
        # that can never bind.
        if float(demand_table[c_idx, ch_idx, 1:].max()) == 0.0:
            continue
        annual_rows.add((c_idx, ch_idx))
        cols = [
            (idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS), 1.0)
            for w in range(1, N_WEEKS + 1)
        ]
        add_row(cols, -np.inf, float(annual_lbs))

    # C7 — DELETED (audit B1). It capped a succession's whole-cycle production at ONE week's
    # demand, which pinned any crop whose harvest is concentrated to `demand / yield` acres and
    # collided with `min_acreage_if_planted` to zero others out silently. Overproduction is now
    # simply `waste` that cost money to grow and earns nothing, so the optimizer prices it out
    # instead of the model forbidding it. Measured on the shipped farm: +$84,857, Garlic
    # 11.6 → 23.5 acres.
    #
    # Two consequences SPEC_v3 §3.5 flags, neither automatic:
    #   • free disposal turns modelling bugs into invisible waste, which is why `waste_by_crop`
    #     is now in the result dict — a number nobody can see is a number nobody can audit;
    #   • `overhead_pct_of_revenue` proxies costs that scale with the SIZE of the operation,
    #     and C7 was accidentally holding production ≈ sales. A farm that grows 2× and sells 1×
    #     now pays overhead as if it were half its real size. Not fixed here.

    # C8 — Crop diversity: annual acre-weeks per crop
    # Σ_{i: crop c} x[i] × len(weeks(i)) ≤ diversity_max[c] × N_WEEKS
    # Semantic: crop c may occupy at most (diversity_max × 100)% of the farm's
    # total annual planting capacity (acres × weeks), capturing rotation intent.
    for c_idx in range(n_crops):
        div_max = crops[c_idx].get("crop_diversity_max", 1.0)
        rhs = div_max * N_WEEKS
        cols = [
            (idx_x_start + i, float(len(successions[i]["weeks"])))
            for i in range(N_S)
            if successions[i]["crop"] == c_idx
        ]
        if cols:
            add_row(cols, -np.inf, rhs)

    # C9 — Binary linkage upper: x[i] ≤ y[i]
    for i in range(N_S):
        add_row(
            [(idx_x_start + i, 1.0), (idx_y_start + i, -1.0)],
            -np.inf, 0.0,
        )

    # C15 — Committed acres: land already in the ground is not a decision (S14)
    #
    # "Already planted" means STANDING IN THE GROUND when the plan is made. The planning year is
    # anchored at 1 January, so that is week 1 — which is exactly the set of successions an
    # overwintering crop occupies at the start of the year (garlic goes in around week 46 and
    # runs through to July).
    #
    # ⚠️ The floor is on ACREAGE ACTIVE IN WEEK 1, not on the annual sum of plantings. Flooring
    # the sum was wrong and measured so: with a 3-acre commitment and a 1-acre/week planting
    # cap, the solver satisfied it with eighteen separate 1-acre plantings spread from week 9 to
    # week 26 — annual sum 18, peak standing acreage 6, and not one acre of the commitment
    # actually reserved. A commitment is a quantity of ground, not a quantity of activity.
    #
    # ⚠️ COSTS ARE STILL CHARGED, and this CAN change the plan, not only the P&L. The seed,
    # labour and fuel are sunk, but charging them consumes cash (C13) and labour (C2) in those
    # weeks, so when either binds the forced planting crowds out other crops and the returned
    # plan differs from the honest one. See BACKLOG S14.
    for c_idx, crop in enumerate(crops):
        committed = float(crop.get("committed_acres", 0.0) or 0.0)
        if committed <= 0:
            continue
        cols = [(idx_x_start + i, -total_land)
                for i, s in enumerate(successions)
                if s["crop"] == c_idx and phase_table[i][1] is not None]
        if not cols:
            # Nothing this crop can grow is in the ground in week 1, so the commitment cannot
            # be honoured by any plan. Silently dropping it is the failure mode this whole
            # sweep exists to remove.
            return {
                "status": "invalid_input",
                "profit": None,
                "errors": [
                    f"Crop '{crop.get('name', c_idx)}' has {committed:g} acres recorded as "
                    f"already planted, but none of its plantings are in the ground at the start "
                    f"of the planning year. Mark it as overwintering, or set its committed "
                    f"acres to 0."
                ],
                "warnings": validation_warnings,
                "crops": crops,
                "channels": channels,
                "successions": successions,
            }
        add_row(cols, -np.inf, -committed)

    # C10 — Min acreage lower: x[i] ≥ y[i] × min_frac
    for i in range(N_S):
        crop = crops[successions[i]["crop"]]
        min_acres = crop.get("min_acreage_if_planted", 0.0)
        min_frac = min_acres / total_land
        add_row(
            [(idx_x_start + i, -1.0), (idx_y_start + i, min_frac)],
            -np.inf, 0.0,
        )

    # C11 — Max plant acres per week
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i, total_land)
            for i in range(N_S)
            if phase_table[i][w] == 0
        ]
        add_row(cols, -np.inf, max_plant_acres_per_week)

    # C12 — Max harvest acres per week
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i, total_land)
            for i in range(N_S)
            if phase_table[i][w] == 2
        ]
        add_row(cols, -np.inf, max_harvest_acres_per_week)

    # C13 — Weekly cash floor (cumulative):
    # Σ_{t≤W} net_rev[t] - Σ_i x[i]×cum_var[i,W] ≥ -(opening_cash+credit_line) + W×fixed_weekly
    #
    # For each W=1..52, the row involves:
    #   v[c,ch,w] for all w ≤ W  (coefficient: +net_price[c,ch])
    #   x[i]                     (coefficient: -cum_var[i,W])
    #   city_water[w] for w ≤ W  (coefficient: -city_water_cost_per_L)
    #   overtime[w]   for w ≤ W  (coefficient: -ot_extra_rate[w-1])
    ot_extra_rate_arr = (hourly_labor_rate * (overtime_rate_multiplier - 1.0)
                         if overtime_enabled else np.zeros(N_WEEKS))
    hire_extra_rate_arr = (hourly_labor_rate * hire_wage_markup
                           if hire_enabled else np.zeros(N_WEEKS))
    floor = -(opening_cash + credit_line)

    # Skip the cash floor entirely when disabled (UI "cash off" → optimize
    # purely for profit). Applying it with a zero buffer would force revenue ≥
    # cost from week 1, which is infeasible given week-1 salaried/fixed costs.
    c13_weeks = range(1, N_WEEKS + 1) if cash_constraint_enabled else range(0)
    for W in c13_weeks:
        cols = []
        # Revenue from sales up to week W, net of overhead (overhead is a real cash outflow
        # ∝ revenue, so the solvency check must see it).
        for c_idx in range(n_crops):
            for ch_idx in range(n_channels):
                np_val = net_after_price[c_idx, ch_idx]
                if np_val == 0.0:
                    continue
                for w in range(1, W + 1):
                    flat = idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                    cols.append((flat, np_val))
        # Variable costs from x[i] (cumulative up to W)
        for i in range(N_S):
            cv = cum_var[i, W]
            if cv != 0.0:
                cols.append((idx_x_start + i, -cv))
        # City water cost up to W
        if city_water_enabled and idx_cw_start is not None:
            for w in range(W):
                cols.append((idx_cw_start + w, -city_water_cost_per_L))
        # Overtime cost up to W
        if overtime_enabled and idx_ot_start is not None:
            for w in range(W):
                cols.append((idx_ot_start + w, -ot_extra_rate_arr[w]))
        # Hired-labor markup cost up to W
        if hire_enabled and idx_hire_start is not None:
            for w in range(W):
                cols.append((idx_hire_start + w, -hire_extra_rate_arr[w]))

        # Fixed selling (stall fees/retainers) is a steady weekly cash outflow → in the floor.
        rhs_lo = floor + W * (fixed_weekly + fixed_selling_per_week)
        add_row(cols, rhs_lo, np.inf)

    # (Former C14 removed.) Overtime/hire are needed only beyond TOTAL labor capacity
    # (salaried + hourly + seasonal); C2 already enforces that ceiling and forces
    # overtime+hire ≥ used − labor_capacity. The previous version measured against the
    # hourly-only capacity, which wrongly excluded salaried staff and made flexibility
    # "buy back" capacity the farm already had.

    # -----------------------------------------------------------------------
    # Step 10 — Assemble and solve
    # -----------------------------------------------------------------------
    n_rows = row
    A_sparse = csr_matrix(
        (vals_A, (rows_A, cols_A)),
        shape=(n_rows, n_vars),
    )
    constraints = LinearConstraint(A_sparse, lbs_con, ubs_con)
    bounds = Bounds(lb, ub)

    result = milp(
        c=c_obj,
        constraints=constraints,
        integrality=integrality,
        bounds=bounds,
        options={"disp": False, "time_limit": solver_time_limit},
    )

    # -----------------------------------------------------------------------
    # Step 11 — Extract results
    # -----------------------------------------------------------------------
    status_map = {0: "optimal", 1: "iteration_limit", 2: "infeasible",
                  3: "unbounded", 4: "other"}
    status = status_map.get(result.status, f"unknown({result.status})")

    # SPEC_v3 §7.1 — a time-limited solve usually HAS a plan; don't throw it away.
    #
    # scipy reports status 1 when HiGHS hits `time_limit`, and in that case `result.x` is
    # normally a feasible incumbent, often within a fraction of a percent of optimal. Bailing
    # out with profit=None hands the grower "no solution found" while a perfectly usable plan
    # sits in the result object. B.2 made this materially more likely: the golden farm went
    # from closing at the root in 1 branch-and-bound node to needing 41, so a farm larger than
    # the demo can plausibly reach the 75s budget the client sets.
    #
    # Fall through to normal extraction and flag it, rather than inventing a second reporting
    # path that could drift from the first.
    time_limited_incumbent = (result.status == 1 and getattr(result, "x", None) is not None)
    if result.status != 0 and not time_limited_incumbent:
        return {
            "status": status,
            "profit": None,
            "message": result.message,
            # Present on EVERY branch. The adapter had to write result.get('errors', []) purely
            # because this path omitted them — a caller band-aiding a schema the solver should
            # simply keep consistent.
            "errors": [],
            "warnings": validation_warnings,
            "channel_margins": channel_margins,
            "excluded_channels": excluded_channels,
            "successions": successions,
            "crops": crops,
            "channels": channels,
        }
    if time_limited_incumbent:
        status = "time_limit_feasible"

    z = result.x
    x_sol = z[idx_x_start : idx_x_start + N_S]
    # y is REPORTED as a function of x, not read raw from the solution.
    #
    # PLANT_FLAG_TIE_BREAK makes minimum-y strictly optimal, but its total value across ~155
    # successions (~1.6e-4) sits below HiGHS's default relative MIP gap, and it is not enforced
    # at all on the `time_limit_feasible` path this solver deliberately supports. So a returned
    # incumbent can still carry y=1 with x=0, and anything reading y as "was this planted"
    # would list a zero-acre succession as planted. Deriving it removes the dependence on the
    # tie-break's magnitude entirely: x is the quantity, y is the question "is x above zero".
    y_raw = z[idx_y_start : idx_y_start + N_S]
    y_sol = np.where(z[idx_x_start : idx_x_start + N_S] > 1e-9, 1.0, 0.0)

    v_flat = z[idx_v_start : idx_v_start + V_off]
    v_sol = np.zeros((n_crops, n_channels, N_WEEKS + 1), dtype=float)
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            for w in range(1, N_WEEKS + 1):
                flat = _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                v_sol[c_idx, ch_idx, w] = v_flat[flat]

    inv_sol   = np.zeros((n_crops, N_WEEKS + 1), dtype=float)
    waste_sol = np.zeros((n_crops, N_WEEKS + 1), dtype=float)
    for c_idx in range(n_crops):
        for w in range(1, N_WEEKS + 1):
            flat = _cw_index(c_idx, w, N_WEEKS)
            inv_sol[c_idx, w]   = z[idx_inv_start + flat]
            waste_sol[c_idx, w] = z[idx_waste_start + flat]

    # Waste per crop, and what share of sellable output it represents.
    #
    # NOT optional reporting. Deleting C7 (B1) means overproduction is no longer infeasible,
    # it is discarded — which is correct economics, but it also means a MODELLING bug now
    # expresses itself as a plan that looks legitimate while quietly dumping product, where
    # before it expressed itself as suppressed acreage that at least looked wrong. The shipped
    # plan already discards 45.2% of its garlic to the F2 window defect with nothing anywhere
    # saying so. A number nobody can see is a number nobody can audit. SPEC_v3 §3.5.
    waste_by_crop = {}
    for c_idx, crop in enumerate(crops):
        discarded = float(waste_sol[c_idx, 1:].sum())
        sellable = sum(
            succ_weekly_sellable_lbs[i] * float(x_sol[i]) * succ_n_harv[i]
            for i in range(N_S) if successions[i]["crop"] == c_idx
        )
        # Shrink leaves the balance through the (1-loss) coefficient without ever becoming
        # `waste`, so before this was reported a farm could lose half its harvest in store and
        # the results still said "0% waste" with no banner — the exact blindness this block
        # exists to prevent, reintroduced by the mechanism that destroys the product. Measured
        # at 15%/wk: 424,529 lb unaccounted, waste_by_crop reporting 0.0000.
        shrunk = float(storage_loss[c_idx] * inv_sol[c_idx, :-1].sum())
        lost = discarded + shrunk
        waste_by_crop[crop["name"]] = {
            "lbs": discarded,
            "shrink_lbs": shrunk,
            "lost_lbs": lost,
            "sellable_lbs": sellable,
            "fraction": (discarded / sellable) if sellable > 1e-9 else 0.0,
            "lost_fraction": (lost / sellable) if sellable > 1e-9 else 0.0,
        }

    m3_per_lb = np.array([c["crop_size_m3_per_lb"] for c in crops], dtype=float)
    # C4b's own rows, evaluated against the solution — see the note where they are built.
    def _row_value(cols):
        return float(sum(coeff * z[col] for col, coeff in cols))

    storage_m3_weekly = [_row_value(cols) for cols in cold_room_cols]
    ambient_m3_weekly = [_row_value(cols) for cols in ambient_room_cols]

    # Pounds sold per crop-channel over the year. Four separate reporting blocks below want this
    # same slice-sum (revenue, crop_contribution, channel_sales, demand_saturation); computing it
    # once means they cannot drift, and it is the quantity the whole money path is built on.
    sold_by_pair = v_sol[:, :, 1:].sum(axis=2)

    # Revenue and costs
    revenue = 0.0
    packaging_cost = 0.0
    for c_idx, crop in enumerate(crops):
        for ch_idx, ch in enumerate(channels):
            ch_spec = crop.get("channels", {}).get(ch["name"], {})
            price = ch_spec.get("price_per_lb", 0.0)
            pkg   = ch_spec.get("packaging_cost_per_lb", 0.0)
            sold  = sold_by_pair[c_idx, ch_idx]
            revenue       += sold * price
            packaging_cost += sold * pkg

    variable_cost = float(np.dot(x_sol, var_cost_coeff)) + packaging_cost

    # What each crop actually contributes to THIS plan, in dollars. Every other per-crop figure
    # the app reports is a rate (per lb, per acre, per acre-day); none of them answer "how much
    # of my profit does garlic account for". These come from the solved plan — the pounds really
    # sold and the acres really planted — so no cycle-count or repeat assumption is involved.
    crop_contribution = {}
    for c_idx, crop in enumerate(crops):
        grow_cost = float(sum(x_sol[i] * var_cost_coeff[i]
                              for i, sc in enumerate(successions) if sc["crop"] == c_idx))
        acres = float(sum(x_sol[i] * total_land
                          for i, sc in enumerate(successions) if sc["crop"] == c_idx))
        by_channel, net_rev_total, lbs_total = {}, 0.0, 0.0
        for ch_idx, ch in enumerate(channels):
            sold = float(sold_by_pair[c_idx, ch_idx])
            if sold <= 0:
                continue
            net_rev = sold * float(net_after_price[c_idx, ch_idx])   # net of packaging + overhead
            by_channel[ch["name"]] = {"lbs_sold": sold, "net_revenue": net_rev}
            net_rev_total += net_rev
            lbs_total     += sold
        if lbs_total <= 0 and acres <= 0:
            continue
        crop_contribution[crop["name"]] = {
            "acres_planted":  acres,
            "lbs_sold":       lbs_total,
            "net_revenue":    net_rev_total,      # after packaging and overhead
            "growing_cost":   grow_cost,
            "contribution":   net_rev_total - grow_cost,
            "by_channel":     by_channel,
        }

    # The per-channel WEEKLY sales schedule, read straight off the solver's own `v` (W1 / D4).
    #
    # `v` has always been returned and nothing read it. The client rebuilt this instead, by
    # splitting each week's GROSS harvest in proportion to demand x price — a formula that
    # knows nothing about sell-through (~18% overstatement on its own), storage carry, the
    # annual caps, the margin hurdle, or what the LP actually chose to sell. So the pies, the
    # sales CSV and the P&L's channel revenue lines could not reconcile to the headline
    # revenue printed on the same page.
    #
    # Two properties this structure is built to have, both pinned by tests:
    #   * `revenue` per channel uses gross_price — the SAME product the headline `revenue`
    #     total above is summed from — so the channel lines add up to it exactly.
    #   * `weekly_lbs` sums to `lbs_sold`, so a weekly view and an annual view of the same
    #     channel cannot disagree.
    #
    # Only non-zero series are emitted. A dense crops x channels x 52 grid is almost entirely
    # zeros on any real farm, and this crosses the Pyodide boundary as JSON on every solve.
    channel_sales = {}
    for ch_idx, ch in enumerate(channels):
        by_crop, ch_lbs, ch_rev = {}, 0.0, 0.0
        for c_idx, crop in enumerate(crops):
            weekly = v_sol[c_idx, ch_idx, 1:]            # index 0 = week 1
            sold   = float(sold_by_pair[c_idx, ch_idx])
            if sold <= 0.0:
                continue
            rev = sold * float(gross_price[c_idx, ch_idx])
            by_crop[crop["name"]] = {
                "lbs_sold":   sold,
                "revenue":    rev,
                "weekly_lbs": [float(t) for t in weekly],
            }
            ch_lbs += sold
            ch_rev += rev
        if not by_crop:
            continue
        channel_sales[ch["name"]] = {
            "lbs_sold": ch_lbs,
            "revenue":  ch_rev,
            "by_crop":  by_crop,
        }

    # Demand saturation per crop-channel, measured against the row the solver ACTUALLY
    # ENFORCES (W6).
    #
    # The client used to compute this itself as `gross annual harvest / this channel's cap`,
    # where the numerator was the crop's ENTIRE harvest across every channel. So a crop selling
    # nothing at all into Wholesale still printed a Wholesale saturation, beside a channel pie
    # built from `channel_sales` showing it selling nothing there. Measured on the shipped farm:
    # 10 of 14 crop-channel rows overstated by more than 10 points, and three rows sold ZERO lb
    # while reporting 29%, 16% and 4%.
    #
    # WHY THE OBVIOUS FIX IS ALSO WRONG — this is what makes the calculation worth owning here
    # rather than patching the numerator in JS. Simply swapping in pounds sold on the ANNUAL
    # basis reads Garlic/Farmers Market at 50%, and that row sits at its weekly ceiling in every
    # week it sells at all: the cap is 2,000 lb/wk across W22-W35, the garlic is not out of the
    # ground until W29, so seven of the fourteen capped weeks are unservable and the annual
    # figure halves. The old formula said 100% and was right by accident. "50%" would be a NEW
    # wrong number, and it would have dropped the farm's tightest demand constraint out of the
    # What-If ranking altogether.
    #
    # So each statement is reported against the row that exists, and never against one that
    # does not:
    #   fill            pounds sold / the year's total cap. "How much of this buyer's appetite
    #                   did I fill." Garlic/FM = 50%, which is true and worth knowing — there
    #                   are 14,000 lb of market appetite here that this plan cannot serve.
    #   peak_week_frac  max over weeks of sold / THAT week's cap, for channels with weekly caps
    #                   (C6). Garlic/FM = 100%. None for annual-cap channels, where no weekly
    #                   ceiling exists at all — C6b is the only row, and reporting one anyway is
    #                   the `annual/52` fiction the panel used to print.
    #   binding         utilisation of whichever row the solver enforces. This is the What-If
    #                   ranking's basis, and it puts demand on the same footing as every other
    #                   entry in that list, all of which are peak-weekly.
    #
    # Emitted only for crops with acreage in the plan. "0% of Wholesale filled" for a crop that
    # was never planted is noise, and `unplanted_crops` already explains why it is absent.
    # Keying by crop name is safe because validate.py refuses duplicate crop names — see the
    # W1 follow-up, where last-write-wins on this exact pattern silently dropped 75% of a
    # channel's pounds.
    # Whether a crop is in the plan is a question about the CROP, so it is answered once per
    # crop rather than once per crop-channel. Same predicate `_diagnose_unplanted_crops` uses —
    # these two must agree, because an absent row here is explained by `unplanted_crops` there.
    planted = {crop["name"] for crop in crops
               if float((crop_contribution.get(crop["name"]) or {}).get("acres_planted", 0.0)) > 1e-6}
    demand_saturation = {}
    for ch_idx, ch in enumerate(channels):
        per_crop = {}
        for c_idx, crop in enumerate(crops):
            name = crop["name"]
            if name not in planted:
                continue
            weekly_cap  = demand_table[c_idx, ch_idx, 1:]
            sold        = float(sold_by_pair[c_idx, ch_idx])
            finite      = np.isfinite(weekly_cap)

            if (c_idx, ch_idx) in annual_rows:
                # C6b is the only row the solver emitted for this pair: a yearly total, and no
                # weekly ceiling anywhere. Read off `annual_rows` rather than re-deriving it —
                # see the note at C6b.
                basis, cap, fracs = "annual", float(annual_caps[(c_idx, ch_idx)]), None
            else:
                basis, cap = "weekly", float(np.where(finite, weekly_cap, 0.0).sum())
                # Weeks with no cap divide by +inf, which is 0.0 — no branch, no warning.
                fracs = np.minimum(1.0, v_sol[c_idx, ch_idx, 1:]
                                   / np.where(finite & (weekly_cap > 0), weekly_cap, np.inf))
            if cap <= 0:
                continue

            # Only what differs between the two bases is branched on. Writing the shared four
            # fields twice is how a fifth one comes to disagree with itself.
            fill = min(1.0, sold / cap)
            entry = {
                "basis":    basis,
                "cap_lbs":  cap,
                "sold_lbs": sold,
                "fill":     fill,
            }
            if fracs is None:
                entry["peak_week_frac"]    = None
                entry["weeks_at_cap"]      = []
                entry["peak_week_cap_lbs"] = None
            else:
                entry["peak_week_frac"] = float(fracs.max())
                entry["weeks_at_cap"]   = [int(w) + 1 for w in np.flatnonzero(fracs >= AT_CAP_FRACTION)]
                # The ceiling the plan is actually up against, so a "+10% demand" lever can be
                # labelled without the client parsing week-range strings out of the form — the
                # last place it rebuilt a cap for itself. Falls back to the largest weekly cap
                # when nothing sells, since then no week is the tightest.
                entry["peak_week_cap_lbs"] = float(
                    weekly_cap[int(fracs.argmax())] if entry["peak_week_frac"] > 0
                    else weekly_cap[finite].max()
                )
            entry["binding"] = fill if fracs is None else entry["peak_week_frac"]
            per_crop[name] = entry
        if per_crop:
            demand_saturation[ch["name"]] = per_crop

    city_water_cost = 0.0
    if city_water_enabled and idx_cw_start is not None:
        cw_sol = z[idx_cw_start : idx_cw_start + N_WEEKS]
        city_water_cost = cw_sol.sum() * city_water_cost_per_L

    # Labor-flex reporting (hired + overtime). The hire/overtime split is recomputed
    # deterministically from the labor actually used, rather than read from the raw
    # decision variables, because when hire is cheaper than overtime the LP split is
    # degenerate (many equal-cost splits). The cost-optimal split is: fill hired labor
    # up to its cap first, then overtime — which is exactly what we reconstruct here, so
    # the recomputed costs equal the objective's labor-flex cost.
    labor_used_weekly = np.zeros(N_WEEKS + 1)
    for i in range(N_S):
        if x_sol[i] <= 1e-9:
            continue
        for w in range(1, N_WEEKS + 1):
            labor_used_weekly[w] += total_land * labor_rate[i][w] * x_sol[i]

    hired_hours_weekly    = np.zeros(N_WEEKS + 1)
    overtime_hours_weekly = np.zeros(N_WEEKS + 1)
    if overtime_enabled or hire_enabled:
        # Hours beyond TOTAL labor capacity (salaried + hourly + seasonal) must be bought —
        # filled by cheaper hired labor up to its cap, then overtime. Matches C2.
        for w in range(1, N_WEEKS + 1):
            extra = max(0.0, labor_used_weekly[w] - labor_capacity[w - 1])
            hired = min(extra, max_hire_hrs_per_week) if hire_enabled else 0.0
            hired_hours_weekly[w]    = hired
            overtime_hours_weekly[w] = (extra - hired) if overtime_enabled else 0.0

    overtime_cost = float(np.dot(overtime_hours_weekly[1:],
                                 hourly_labor_rate * (overtime_rate_multiplier - 1.0))) \
                    if overtime_enabled else 0.0
    hire_cost     = float(np.dot(hired_hours_weekly[1:],
                                 hourly_labor_rate * hire_wage_markup)) \
                    if hire_enabled else 0.0

    total_cost = fixed_cost + variable_cost + city_water_cost + overtime_cost + hire_cost
    operating_profit = revenue - total_cost  # what the solver maximized (before overhead + interest)

    # Weekly cash flow for reporting
    # weekly_rev[w]      = net revenue received in week w
    # weekly_vcost[w]    = variable costs paid in week w
    # weekly_fixed_cost  = fixed costs spread evenly
    # cum_cash[w]        = opening_cash + Σ_{t=1}^{w} (weekly_rev[t] - weekly_vcost[t] - fixed_weekly)
    weekly_rev   = np.zeros(N_WEEKS + 1)
    weekly_vcost = np.zeros(N_WEEKS + 1)

    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            np_val = net_price[c_idx, ch_idx]
            pkg_val = crops[c_idx].get("channels", {}).get(
                channels[ch_idx]["name"], {}).get("packaging_cost_per_lb", 0.0)
            for w in range(1, N_WEEKS + 1):
                sold = v_sol[c_idx, ch_idx, w]
                price_full = np_val + pkg_val
                weekly_rev[w] += sold * price_full - sold * pkg_val  # = sold × net_price

    for i in range(N_S):
        for w in range(1, N_WEEKS + 1):
            weekly_vcost[w] += x_sol[i] * var_cost_weekly[i][w]

    # Other weekly cash outflows the cumulative position must reflect so peak borrowing and
    # interest are honest: city water, overtime/hire premiums, overhead (∝ revenue), and fixed
    # selling. Packaging is already inside weekly_rev (net_price). (var costs + fixed are above.)
    cw_weekly = z[idx_cw_start : idx_cw_start + N_WEEKS] if (city_water_enabled and idx_cw_start is not None) else None
    ot_rate_w = hourly_labor_rate * (overtime_rate_multiplier - 1.0)
    hr_rate_w = hourly_labor_rate * hire_wage_markup
    weekly_gross_rev = np.zeros(N_WEEKS + 1)
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            gp = gross_price[c_idx, ch_idx]
            if gp == 0.0:
                continue
            for w in range(1, N_WEEKS + 1):
                weekly_gross_rev[w] += v_sol[c_idx, ch_idx, w] * gp

    weekly_other = np.zeros(N_WEEKS + 1)
    for w in range(1, N_WEEKS + 1):
        weekly_other[w] = (
            (cw_weekly[w - 1] * city_water_cost_per_L if cw_weekly is not None else 0.0)
            + overtime_hours_weekly[w] * ot_rate_w[w - 1]
            + hired_hours_weekly[w]    * hr_rate_w[w - 1]
            + overhead_pct_of_revenue  * weekly_gross_rev[w]
            + fixed_selling_per_week
        )

    weekly_cash_flow = np.zeros(N_WEEKS + 1)
    cum = opening_cash
    for w in range(1, N_WEEKS + 1):
        cum += weekly_rev[w] - weekly_vcost[w] - fixed_weekly - weekly_other[w]
        weekly_cash_flow[w] = cum

    peak_borrowing = max(0.0, -float(weekly_cash_flow[1:].min()))

    # Below-the-line realism deductions — applied to the optimized plan, do NOT reshape it:
    #   overhead — indirect business costs as a share of revenue (insurance, tax, admin, etc.)
    #   interest — APR on the average weekly operating borrowing the plan implies
    overhead_cost = overhead_pct_of_revenue * revenue
    borrowed_weekly = np.maximum(0.0, -weekly_cash_flow[1:])
    avg_borrowing = float(borrowed_weekly.mean()) if borrowed_weekly.size else 0.0
    interest_cost = interest_rate_apr * avg_borrowing
    profit = operating_profit - overhead_cost - interest_cost  # net profit (honest headline)

    # capacity_series — the used-vs-capacity pairs the CONSTRAINTS actually used, so the
    # client can render them instead of rebuilding the physics with different assumptions
    # (SPEC_v3 §9, audit N5/N6). Every series here has a matching constraint:
    #   labor   -> C2   water -> C3   storage -> C4b
    #
    # This is not cosmetic. The client's own versions disagreed with the model: it counted
    # rain falling on fields as water SUPPLY, where C3 treats rain as a reduction in demand
    # via net_water_rate, and it summed raw crew hours without field_time_pct. On the shipped
    # farm that inflated the water denominator by 1.5x on average and 2.2x at peak, and labor
    # by up to 16%. Since the bottleneck ranking picks the max utilisation ACROSS these
    # series, one honest ratio among inflated ones does not just mislead, it mis-ranks.
    #
    # Shape is {name: {used, cap}} rather than flat arrays because SPEC_v3 §3.3 splits
    # storage into refrigerated + ambient, and a scalar cap wedged into a dict of series
    # would have to be reshaped once consumers exist.

    # wstore[w] is the END-of-week level; the water available TO week w is its opening level,
    # i.e. the previous week's close. Week 1 opens empty (wstore[0] = 0, anchored like inv).
    wstore_sol = z[idx_ws_start : idx_ws_start + N_WEEKS]
    wstore_opening = [0.0] + [float(wstore_sol[w - 1]) for w in range(1, N_WEEKS)]

    water_used_weekly = [
        float(sum(total_land * net_water_rate[i][w] * x_sol[i]
                  for i in range(N_S) if phase_table[i][w] is not None))
        for w in range(1, N_WEEKS + 1)
    ]
    # `cap` is each row's RHS AS SOLVED, not its standing capacity — because several rows buy
    # extra headroom with a decision variable and the constraint is only satisfied against the
    # total:
    #     C2:  used - overtime[w] - hire[w]  <= labor_capacity[w]
    #     C3:  used - city_water[w]          <= free_water[w]
    # Reporting the bare RHS understates the ceiling and breaks two real configurations. With
    # a well switched off and city water on, free_water is all zeros: every consumer guards
    # `cap > 0 ? used/cap : 0`, so water silently reports 0% and summaryRow drops the row
    # entirely — water can never be ranked the bottleneck even when it is the binding
    # resource. With both on, used legitimately exceeds free_water and the unclamped
    # peakRatio goes past 100%, which makes rankBottlenecks call water #1 wrongly. The labor
    # equivalent fires in the What-If "Plan optimal labor" scenario, which reports labor
    # over-subscribed in exactly the run where the grower just bought the extra hours.
    ot_weekly   = (z[idx_ot_start   : idx_ot_start   + N_WEEKS]
                   if (overtime_enabled and idx_ot_start is not None) else np.zeros(N_WEEKS))
    hire_weekly = (z[idx_hire_start : idx_hire_start + N_WEEKS]
                   if (hire_enabled and idx_hire_start is not None) else np.zeros(N_WEEKS))
    city_weekly = (z[idx_cw_start   : idx_cw_start   + N_WEEKS]
                   if (city_water_enabled and idx_cw_start is not None) else np.zeros(N_WEEKS))

    capacity_series = {
        "labor":   {"used": [float(v) for v in labor_used_weekly[1:]],
                    "cap":  [float(labor_capacity[w] + ot_weekly[w] + hire_weekly[w])
                             for w in range(N_WEEKS)]},
        # The tank's OPENING level is part of the week's supply (B7): a week may legitimately
        # draw more than that week's inflow by emptying stored water. Leaving it out made the
        # published cap smaller than the row actually solved against, so `used` exceeded `cap`
        # and the bottleneck ranking would have called water saturated when it was not.
        "water":   {"used": water_used_weekly,
                    "cap":  [float(free_water[w] + city_weekly[w] + wstore_opening[w])
                             for w in range(N_WEEKS)]},
        "storage_ambient": {"used": ambient_m3_weekly,
                            "cap":  [float(ambient_storage_cap)] * N_WEEKS},
        "storage": {"used": storage_m3_weekly,
                    "cap":  [float(harvest_storage_cap)] * N_WEEKS},
    }

    return {
        "status":           status,
        # Present only when the solve stopped on its time budget: the plan below is the best
        # HiGHS found, not a proven optimum. SPEC_v3 §7.1.
        "gap_note":         ("Stopped at the time limit — this is the best plan found within "
                             "the budget, not a proven optimum."
                             if status == "time_limit_feasible" else None),
        # SPEC_v3 §8: the ONE margin kernel, computed from the objective's own arrays. The UI
        # renders these numbers rather than recomputing them, so it can never disagree with
        # the optimizer about which crop-channels make money.
        "channel_margins":   channel_margins,
        "excluded_channels": excluded_channels,
        "crop_contribution": crop_contribution,
        # The weekly per-channel sales schedule the client renders (W1 / D4). Built here rather
        # than in the adapter so every entry point gets it — the What-If sweep, the sensitivity
        # runs and Monte Carlo never touch the browser's reporting code.
        "channel_sales":     channel_sales,
        "demand_saturation": demand_saturation,
        "demand_at_cap_threshold": AT_CAP_FRACTION,
        "profit":           profit,
        "operating_profit": operating_profit,
        "overhead_cost":    overhead_cost,
        "interest_cost":    interest_cost,
        "sell_through_fraction": sell_through_fraction,
        "revenue":          revenue,
        "variable_cost":    variable_cost,
        "fixed_cost":       fixed_cost,
        "city_water_cost":  city_water_cost,
        "overtime_cost":    overtime_cost,
        "hire_cost":        hire_cost,
        "labor_flex_enabled": bool(overtime_enabled or hire_enabled),
        "total_hired_hours":    float(hired_hours_weekly.sum()),
        "total_overtime_hours": float(overtime_hours_weekly.sum()),
        "hired_hours_weekly":    hired_hours_weekly,
        "overtime_hours_weekly": overtime_hours_weekly,
        "weekly_cash_flow": weekly_cash_flow,
        "peak_borrowing":   peak_borrowing,
        "opening_cash":     opening_cash,
        "credit_line":      credit_line,
        "x":                x_sol,
        "y":                y_sol,
        "v":                v_sol,
        "inventory":        inv_sol,
        "waste":            waste_sol,
        "waste_by_crop":    waste_by_crop,
        # The storage series the CONSTRAINT used. The client must render this rather than
        # rebuild it — B.1 left the adapter recomputing harvest inflow because there was no
        # key to read, and that copy understates any plan that holds stock. SPEC_v3 §9.
        "warnings":         validation_warnings,
        "errors":           [],
        "capacity_series":  capacity_series,
        # WHY each requested crop is absent from the plan (audit Part 3 / S2). Computed here
        # rather than in the client so every entry point gets it — the What-If sweep and Monte
        # Carlo never touch the browser's reporting code.
        "unplanted_crops":  _diagnose_unplanted_crops(
            crops, successions, crop_contribution, annual_caps, demand_table,
            excluded_channels, capacity_series, phase_table, N_WEEKS,
        ),
        "storage_peak_m3":  max(storage_m3_weekly) if storage_m3_weekly else 0.0,
        "ambient_peak_m3":  max(ambient_m3_weekly) if ambient_m3_weekly else 0.0,
        "successions":      successions,
        "crops":            crops,
        "channels":         channels,
    }
