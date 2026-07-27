"""
solver.py — Core MILP solver for the 52-week farm optimization model v2.

Entry point: ``solve_farm_v2(**params)``

Variable layout (all collected into one flat vector ``z`` for scipy.milp):
  0 .. N_S-1               x[i]           — succession land fraction (continuous)
  N_S .. 2*N_S-1           y[i]           — binary plant/no-plant
  2*N_S .. 2*N_S+V_off-1   v[c,ch,w]      — channel sales in lbs (continuous)
  next V_off               city_water[w]  — liters (continuous, optional)
  next 52                  overtime[w]    — hours (continuous, optional)

Constraint order (rows of A):
  C1   land (52)
  C2   labor (52)
  C3   water (52)
  C4   harvest storage (52)
  C5   sales ≤ sell_through × production (n_crops × 52)   [production = harvest = x×land×yield]
  C6   sales ≤ sales-capacity cap (n_crops × n_channels × 52)
  C7   sell_through × production ≤ sales-capacity (n_crops × 52)
  C8   crop diversity — annual acre-weeks per crop (n_crops)
  C9   binary linkage upper x[i] ≤ y[i]  (N_S)
  C10  min acreage lower   x[i] ≥ y[i]×min_frac  (N_S)
  C11  max plant acres/week (52)
  C12  max harvest acres/week (52)
  C13  weekly cash floor — cumulative cash ≥ -(opening_cash + credit_line) (52)
  C14  overtime lower bound (52, optional)
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
from farm_v2.utils.demand import build_demand_table, total_demand_per_crop_week


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _vcw_index(c: int, ch: int, w: int, n_channels: int, n_weeks: int) -> int:
    """Flat index into v[c, ch, w] block (0-based within the block)."""
    return c * n_channels * n_weeks + ch * n_weeks + (w - 1)


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

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
        "successions"       : list[dict]
        "crops"             : list[dict]
        "channels"          : list[dict]
    """
    if crops is None:
        raise ValueError("crops must be provided.")
    if channels is None:
        raise ValueError("channels must be provided.")
    if year_round_employees is None:
        year_round_employees = []
    if seasonal_employees is None:
        seasonal_employees = []

    N_WEEKS = 52
    n_crops    = len(crops)
    n_channels = len(channels)

    # -----------------------------------------------------------------------
    # Step 1 — Generate successions and lookup tables
    # -----------------------------------------------------------------------
    successions = generate_successions(crops, year)
    N_S = len(successions)
    if N_S == 0:
        raise ValueError("No successions generated. Check crop season windows.")

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
    total_demand = total_demand_per_crop_week(demand_table)       # (n_crops, 53)

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
        if excluded_channels:
            total_demand = total_demand_per_crop_week(demand_table)

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
    idx_x_start   = 0
    idx_y_start   = N_S
    idx_v_start   = 2 * N_S
    # Sequentially lay out the optional weekly variable blocks after the v[] block.
    _next = idx_v_start + V_off
    idx_cw_start = None
    if city_water_enabled:
        idx_cw_start = _next; _next += N_WEEKS
    idx_ot_start = None
    if overtime_enabled:
        idx_ot_start = _next; _next += N_WEEKS
    idx_hire_start = None
    if hire_enabled:
        idx_hire_start = _next; _next += N_WEEKS
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

    # Per-succession precomputes shared by C4, C5 and C7.
    #
    # `succ_sellable_lbs` / `succ_weekly_sellable_lbs` exist so the "sellable pounds off
    # this succession" product is written ONCE. It was previously hand-typed at each row,
    # sell-through fallback and all, and C4 was the copy that forgot both the fallback and
    # the divisor — a drift no reader could see, because each site looked self-consistent.
    # Which of the two arrays a row wants is a real semantic distinction, so it is in the
    # name: whole-season for the rows that cap a window's total, one-week for the rows that
    # cap a single week.
    succ_spread              = []  # int S ∈ [1,8]
    succ_last_harv           = []  # last harvest week (or None if no harvest phase)
    succ_n_harv_weeks        = []  # number of harvest-phase weeks per succession
    succ_sellable_lbs        = []  # sellable lbs over the whole season, at x[i] = 1
    succ_weekly_sellable_lbs = []  # ... spread evenly across the harvest weeks
    for i in range(N_S):
        crop_i = crops[successions[i]["crop"]]
        succ_spread.append(max(1, min(8, int(crop_i.get("sales_spread_weeks", 1) or 1))))
        harv_wks = harvest_weeks_of(successions[i], N_WEEKS)
        n_harv = max(1, len(harv_wks))  # max(1,...) avoids div-by-zero
        succ_last_harv.append(harv_wks[-1] if harv_wks else None)
        succ_n_harv_weeks.append(n_harv)
        st_i = crop_i.get("sell_through_fraction", sell_through_fraction)
        succ_sellable_lbs.append(st_i * total_land * crop_i["yield_per_acre"])
        succ_weekly_sellable_lbs.append(succ_sellable_lbs[-1] / n_harv)

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

    # C3 — Water
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i, total_land * net_water_rate[i][w])
            for i in range(N_S)
            if phase_table[i][w] is not None and net_water_rate[i][w] > 0
        ]
        if city_water_enabled and idx_cw_start is not None:
            cols.append((idx_cw_start + w - 1, -1.0))
        add_row(cols, -np.inf, free_water[w - 1])

    # C4 — Harvest storage (weekly throughput)
    #
    # Coefficient is the volume of ONE WEEK's sellable harvest. C5, C7 and the client's
    # `weekly_harvest_vol` reporter apply the same sell-through factor and the same
    # per-harvest-week divisor to this quantity, so keep this row in step with them —
    # that is what `succ_weekly_sellable_lbs` exists for. `yield_per_acre` is a
    # WHOLE-SEASON figure; charging it in every harvest week is not a conservative reading
    # of the cap, it is a different quantity. History of the 2026-07-27 correction and the
    # money it moved: the baseline log in tests/test_golden_farm.py.
    #
    # NOTE: this is a throughput cap, not an inventory cap — it sees produce in its harvest
    # week only and models no carryover, so a crop with sales_spread_weeks > 1 occupies no
    # modelled space while it waits to be sold. Set harvest_storage_cap to hold peak weekly
    # throughput. SPEC_v3 §3 replaces this row with a real inventory balance.
    for w in range(1, N_WEEKS + 1):
        cols = [
            (idx_x_start + i,
             succ_weekly_sellable_lbs[i] * crops[successions[i]["crop"]]["crop_size_m3_per_lb"])
            for i in range(N_S)
            if phase_table[i][w] == 2
        ]
        add_row(cols, -np.inf, harvest_storage_cap)

    # C5 — Channel sales ≤ sell_through × production (Phase 3.5.1: sales_spread_weeks)
    #   "production" = "harvest" = x[i]×total_land×yield_per_acre (physical lbs off the field).
    #   Only sell_through_fraction of it is sellable; the supply coefficient below carries that factor.
    #
    # spread=1 (default, backward-compatible):
    #   Per-week:  Σ_ch v[c,ch,w] ≤ Σ_{i: harvest phase in w} x[i]×land×yield
    #   Successions not in harvest phase contribute zero supply → v forced to 0.
    #
    # spread=S > 1 (per succession i with last harvest week H):
    #   Two constraint sets work together:
    #   (a) Per-week:   Σ_ch v[c,ch,w] ≤ Σ_{spread=1, harvest in w} supply
    #                                    + Σ_{spread>1, window covers w} supply
    #       Allows selling in spread weeks; does NOT increase total allowed.
    #   (b) Cumulative: Σ_ch Σ_{w=H}^{H+S-1} v[c,ch,w] ≤ x[i]×land×yield
    #       Caps the total across the window to the actual harvest volume.
    #   C1 (land/field occupancy) is unchanged — spread window is post-harvest.

    # Build spread_window[i] = set of weeks where succession i can sell (post-harvest window)
    # For spread=1 this equals the harvest weeks.  For spread>1 it is [H .. H+S-1].
    spread_window: list[set[int]] = []
    for i in range(N_S):
        H = succ_last_harv[i]
        if H is None:
            spread_window.append(set())
            continue
        S = succ_spread[i]
        if S == 1:
            # Standard: only the actual harvest weeks
            spread_window.append(set(harvest_weeks_of(successions[i], N_WEEKS)))
        else:
            # Spread: window starts at last harvest week, extends S weeks
            spread_window.append(set(range(H, min(H + S, N_WEEKS + 1))))

    # (a) Per-week rows — one per crop × week
    for c_idx in range(n_crops):
        for w in range(1, N_WEEKS + 1):
            col_v = [
                (idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS), 1.0)
                for ch_idx in range(n_channels)
            ]
            for i in range(N_S):
                if successions[i]["crop"] != c_idx:
                    continue
                if w in spread_window[i]:
                    if succ_spread[i] <= 1:
                        # Spread evenly across harvest weeks so total supply = yield_per_acre.
                        # Without this division each harvest week independently allows the full
                        # yield, letting the optimizer sell n_harv_weeks × yield_per_acre total.
                        supply = succ_weekly_sellable_lbs[i]
                    else:
                        # spread>1: cumulative constraint (C5b) caps the total; per-week
                        # supply stays at full yield so any week in the window can clear it.
                        supply = succ_sellable_lbs[i]
                    col_v.append((idx_x_start + i, -supply))
            add_row(col_v, -np.inf, 0.0)

    # (b) Cumulative window rows — one per spread>1 succession
    # Ensures total sales across the window ≤ actual harvest volume.
    for i in range(N_S):
        if succ_spread[i] <= 1:
            continue
        if succ_last_harv[i] is None:
            continue
        c_idx = successions[i]["crop"]
        col_w = [
            (idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS), 1.0)
            for w in sorted(spread_window[i])
            for ch_idx in range(n_channels)
        ]
        col_w.append((idx_x_start + i, -succ_sellable_lbs[i]))
        add_row(col_w, -np.inf, 0.0)

    # C6 — Channel sales ≤ demand cap
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            for w in range(1, N_WEEKS + 1):
                cap_w = demand_table[c_idx, ch_idx, w]
                flat_idx = idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                add_row([(flat_idx, 1.0)], -np.inf, cap_w)

    # C7 — sell_through × production ≤ total sales-capacity  (i.e. production ≤ capacity / sell_through)
    #   Lets the farm grow more than the cap so the SELLABLE share still fits the market.
    for c_idx in range(n_crops):
        for w in range(1, N_WEEKS + 1):
            cols = [
                (idx_x_start + i, succ_weekly_sellable_lbs[i])
                for i in range(N_S)
                if successions[i]["crop"] == c_idx and phase_table[i][w] == 2
            ]
            add_row(cols, -np.inf, total_demand[c_idx, w])

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

    if result.status != 0:
        return {
            "status": status,
            "profit": None,
            "message": result.message,
            "channel_margins": channel_margins,
            "excluded_channels": excluded_channels,
            "successions": successions,
            "crops": crops,
            "channels": channels,
        }

    z = result.x
    x_sol = z[idx_x_start : idx_x_start + N_S]
    y_sol = z[idx_y_start : idx_y_start + N_S]

    v_flat = z[idx_v_start : idx_v_start + V_off]
    v_sol = np.zeros((n_crops, n_channels, N_WEEKS + 1), dtype=float)
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            for w in range(1, N_WEEKS + 1):
                flat = _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                v_sol[c_idx, ch_idx, w] = v_flat[flat]

    # Revenue and costs
    revenue = 0.0
    packaging_cost = 0.0
    for c_idx, crop in enumerate(crops):
        for ch_idx, ch in enumerate(channels):
            ch_spec = crop.get("channels", {}).get(ch["name"], {})
            price = ch_spec.get("price_per_lb", 0.0)
            pkg   = ch_spec.get("packaging_cost_per_lb", 0.0)
            sold  = v_sol[c_idx, ch_idx, 1:].sum()
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
            sold = float(v_sol[c_idx, ch_idx, 1:].sum())
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

    return {
        "status":           status,
        # SPEC_v3 §8: the ONE margin kernel, computed from the objective's own arrays. The UI
        # renders these numbers rather than recomputing them, so it can never disagree with
        # the optimizer about which crop-channels make money.
        "channel_margins":   channel_margins,
        "excluded_channels": excluded_channels,
        "crop_contribution": crop_contribution,
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
        "successions":      successions,
        "crops":            crops,
        "channels":         channels,
    }
