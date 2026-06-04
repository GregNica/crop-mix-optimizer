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
  C5   sales ≤ harvest (n_crops × 52)
  C6   sales ≤ demand cap (n_crops × n_channels × 52)
  C7   production ≤ market (n_crops × 52)
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

from farm_v2.utils.calendar import generate_successions, build_phase_table
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
    operating_weeks: int,
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
    overtime_threshold_hrs: float = 40.0,
    overtime_rate_multiplier: float = 1.5,
    # --- Equipment proxy ---
    max_plant_acres_per_week: float = 1e9,
    max_harvest_acres_per_week: float = 1e9,
    # --- Additional fixed costs ---
    rate_property_mortgage_rent: float = 0.0,  # $/week — land lease or mortgage payment
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
    labor_capacity_hourly  = labor_result["labor_capacity_hourly"]   # (52,)
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

    for i, s in enumerate(successions):
        crop = crops[s["crop"]]
        seed_cost = crop.get("seed_transplant_cost_per_acre", 0.0)

        # Seed cost charged in the first week of the succession
        first_week = s["weeks"][0] if s["weeks"] else None
        if first_week and 1 <= first_week <= N_WEEKS:
            seed_total = total_land * seed_cost
            var_cost_weekly[i][first_week] += seed_total
            var_cost_coeff[i] += seed_total

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

    # -----------------------------------------------------------------------
    # Step 4 — Fixed cost
    # -----------------------------------------------------------------------
    irrigation_fixed = total_land * rate_irrigation * operating_weeks
    fixed_cost = (
        harvest_storage_cap * rate_harvest_storage * operating_weeks
        + water_storage_capacity * rate_water_storage * operating_weeks
        + irrigation_fixed
        + equip_storage * rate_equip_storage * operating_weeks
        + fuel_storage * rate_fuel_storage * operating_weeks
        + rate_machinery * operating_weeks
        + rate_property_mortgage_rent * operating_weeks
        + salaried_weekly_cost * N_WEEKS
    )
    if city_water_enabled and city_water_fixed_fee_per_week > 0:
        fixed_cost += city_water_fixed_fee_per_week * operating_weeks

    fixed_weekly = fixed_cost / N_WEEKS  # fixed cost spread evenly per week

    # -----------------------------------------------------------------------
    # Step 5 — Decision variable layout
    # -----------------------------------------------------------------------
    V_off = n_crops * n_channels * N_WEEKS  # v block size
    idx_x_start   = 0
    idx_y_start   = N_S
    idx_v_start   = 2 * N_S
    idx_cw_start  = idx_v_start + V_off  if city_water_enabled else None
    idx_ot_start  = (idx_cw_start + N_WEEKS if city_water_enabled else idx_v_start + V_off) \
                    if overtime_enabled else None

    n_vars = 2 * N_S + V_off
    if city_water_enabled:
        n_vars += N_WEEKS
    if overtime_enabled:
        n_vars += N_WEEKS

    # -----------------------------------------------------------------------
    # Step 6 — Objective (scipy.milp minimises, so negate profit)
    # -----------------------------------------------------------------------
    c_obj = np.zeros(n_vars)

    # Succession variable costs (add to -profit)
    c_obj[idx_x_start : idx_x_start + N_S] = var_cost_coeff

    # Channel sales revenue minus packaging cost (subtract from -profit)
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            net = net_price[c_idx, ch_idx]
            for w in range(1, N_WEEKS + 1):
                flat_idx = idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                c_obj[flat_idx] -= net

    # City water cost
    if city_water_enabled and idx_cw_start is not None:
        c_obj[idx_cw_start : idx_cw_start + N_WEEKS] = city_water_cost_per_L

    # Overtime cost (incremental rate above regular pay)
    if overtime_enabled and idx_ot_start is not None:
        ot_extra_rate = hourly_labor_rate * (overtime_rate_multiplier - 1.0)
        c_obj[idx_ot_start : idx_ot_start + N_WEEKS] = ot_extra_rate

    # -----------------------------------------------------------------------
    # Step 7 — Bounds
    # -----------------------------------------------------------------------
    lb = np.zeros(n_vars)
    ub = np.full(n_vars, np.inf)
    ub[idx_x_start : idx_x_start + N_S] = 1.0  # x[i] ∈ [0, 1]

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

    # C4 — Harvest storage
    # NOTE: With sales_spread_weeks > 1 (Phase 3.5.1), this constraint is checked
    # at the harvest week only and does not track post-harvest inventory carryover.
    # Users must set harvest_storage_cap large enough to hold the full harvest
    # volume for any spread crop. Full inventory balance is out of scope here.
    for w in range(1, N_WEEKS + 1):
        cols = []
        for i in range(N_S):
            if phase_table[i][w] == 2:
                crop = crops[successions[i]["crop"]]
                coeff = total_land * crop["yield_per_acre"] * crop["crop_size_m3_per_lb"]
                cols.append((idx_x_start + i, coeff))
        add_row(cols, -np.inf, harvest_storage_cap)

    # C5 — Channel sales ≤ harvest production (Phase 3.5.1: sales_spread_weeks)
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
    #
    # Pre-compute per-succession spread, last harvest week, and harvest week count.
    succ_spread       = []  # int S ∈ [1,8]
    succ_last_harv    = []  # last harvest week (or None if no harvest phase)
    succ_n_harv_weeks = []  # number of harvest-phase weeks per succession
    for i in range(N_S):
        crop_i = crops[successions[i]["crop"]]
        S = max(1, min(8, int(crop_i.get("sales_spread_weeks", 1) or 1)))
        succ_spread.append(S)
        harv_wks = [w for w in successions[i]["weeks"] if phase_table[i][w] == 2]
        succ_last_harv.append(harv_wks[-1] if harv_wks else None)
        succ_n_harv_weeks.append(max(1, len(harv_wks)))  # max(1,...) avoids div-by-zero

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
            spread_window.append({w for w in successions[i]["weeks"] if phase_table[i][w] == 2})
        else:
            # Spread: window starts at last harvest week, extends S weeks
            spread_window.append(set(range(H, min(H + S, N_WEEKS + 1))))

    # (a) Per-week rows — one per crop × week
    for c_idx in range(n_crops):
        crop = crops[c_idx]
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
                        supply = total_land * crop["yield_per_acre"] / succ_n_harv_weeks[i]
                    else:
                        # spread>1: cumulative constraint (C5b) caps the total; per-week
                        # supply stays at full yield so any week in the window can clear it.
                        supply = total_land * crop["yield_per_acre"]
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
        crop  = crops[c_idx]
        col_w = [
            (idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS), 1.0)
            for w in sorted(spread_window[i])
            for ch_idx in range(n_channels)
        ]
        col_w.append((idx_x_start + i, -total_land * crop["yield_per_acre"]))
        add_row(col_w, -np.inf, 0.0)

    # C6 — Channel sales ≤ demand cap
    for c_idx in range(n_crops):
        for ch_idx in range(n_channels):
            for w in range(1, N_WEEKS + 1):
                cap_w = demand_table[c_idx, ch_idx, w]
                flat_idx = idx_v_start + _vcw_index(c_idx, ch_idx, w, n_channels, N_WEEKS)
                add_row([(flat_idx, 1.0)], -np.inf, cap_w)

    # C7 — Production ≤ total market (consistent with C5 even-spread fix)
    for c_idx in range(n_crops):
        crop = crops[c_idx]
        for w in range(1, N_WEEKS + 1):
            cols = [
                (idx_x_start + i, total_land * crop["yield_per_acre"] / succ_n_harv_weeks[i])
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
    floor = -(opening_cash + credit_line)

    for W in range(1, N_WEEKS + 1):
        cols = []
        # Revenue from sales up to week W
        for c_idx in range(n_crops):
            for ch_idx in range(n_channels):
                np_val = net_price[c_idx, ch_idx]
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

        rhs_lo = floor + W * fixed_weekly
        add_row(cols, rhs_lo, np.inf)

    # C14 — Overtime lower bound (if enabled)
    if overtime_enabled and idx_ot_start is not None:
        for w in range(1, N_WEEKS + 1):
            cols = [
                (idx_x_start + i, total_land * labor_rate[i][w])
                for i in range(N_S)
                if phase_table[i][w] is not None
            ]
            cols.append((idx_ot_start + w - 1, -1.0))
            add_row(cols, -np.inf, labor_capacity_hourly[w - 1])

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

    city_water_cost = 0.0
    if city_water_enabled and idx_cw_start is not None:
        cw_sol = z[idx_cw_start : idx_cw_start + N_WEEKS]
        city_water_cost = cw_sol.sum() * city_water_cost_per_L

    overtime_cost = 0.0
    if overtime_enabled and idx_ot_start is not None:
        ot_sol = z[idx_ot_start : idx_ot_start + N_WEEKS]
        ot_extra = hourly_labor_rate * (overtime_rate_multiplier - 1.0)
        overtime_cost = float(np.dot(ot_sol, ot_extra))

    total_cost = fixed_cost + variable_cost + city_water_cost + overtime_cost
    profit = revenue - total_cost

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

    weekly_cash_flow = np.zeros(N_WEEKS + 1)
    cum = opening_cash
    for w in range(1, N_WEEKS + 1):
        cum += weekly_rev[w] - weekly_vcost[w] - fixed_weekly
        weekly_cash_flow[w] = cum

    peak_borrowing = max(0.0, -float(weekly_cash_flow[1:].min()))

    return {
        "status":           status,
        "profit":           profit,
        "revenue":          revenue,
        "variable_cost":    variable_cost,
        "fixed_cost":       fixed_cost,
        "city_water_cost":  city_water_cost,
        "overtime_cost":    overtime_cost,
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
