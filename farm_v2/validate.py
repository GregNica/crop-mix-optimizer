"""
validate.py — Input validation and infeasibility pre-checks for the v2 farm model.

Call ``validate_params(**params)`` before running the solver.  It raises
``ValueError`` with a descriptive message on the first problem found.

Checks performed:
  1. Farm infrastructure — positive land, opening_cash ≥ 0, credit_line ≥ 0
  2. Fixed cost rates — non-negative
  3. Water configuration — consistent source selection
  4. Labor configuration — valid employee dicts; hourly capacity > 0 in at least one week
  5. Equipment proxies — positive
  6. Crops — required keys, valid cycle math, ≥1 season, channel consistency
  7. Channels — at least one; unique names
  8. Succession feasibility — at least one succession generated per crop
  9. Demand — at least one non-zero demand entry exists
 10. Land tenure, ownership carrying and insurance (R7) — non-negative, rented ≤ total land,
     payment week 1–52, known asset classes, no carrying cost on a 'no constraint' capacity
"""

from __future__ import annotations

from farm_v2.utils.labor import SEASONAL_TYPES
from farm_v2.utils.water import WATER_MODES

import math
from farm_v2.utils.calendar import generate_successions, week_of_year
from farm_v2.utils.zones import crop_zone_names, resolve_zones
from farm_v2.utils.perennials import resolve_perennial_blocks
from farm_v2.utils.numbers import (check_nonneg as _check_nonneg, check_positive as _check_positive,
                                   is_number as _is_number)


# ---------------------------------------------------------------------------
# Top-level API
# ---------------------------------------------------------------------------

def validate_params(
    total_land: float,
    harvest_storage_cap: float,
    operating_weeks: int,
    crops: list,
    channels: list,
    rainfall_weekly_L_per_acre,
    opening_cash: float = 0.0,
    credit_line: float = 0.0,
    budget: float = None,   # deprecated — ignored if opening_cash/credit_line provided
    year_round_employees: list | None = None,
    seasonal_employees: list | None = None,
    city_water_enabled: bool = False,
    well_enabled: bool = False,
    catchment_enabled: bool = False,
    catchment_surface_area_m2: float = 0.0,
    well_weekly_cap_L: float = 0.0,
    water_mode: str = "irrigated",
    max_plant_acres_per_week: float = 1e9,
    max_harvest_acres_per_week: float = 1e9,
    year: int = 2024,
    rented_acres: float = 0.0,
    cash_rent_per_acre_yr: float = 0.0,
    ownership_carrying_rate: float = 0.0,
    capital_cost_per_unit: dict | None = None,
    insurance_premium_per_yr: float = 0.0,
    insurance_payment_week: int | None = None,
    utilities_cost_per_yr: float = 0.0,
    owned_capacity: dict | None = None,   # {asset class: capacity} — the solver's owned-asset table
    overtime_enabled: bool = False,
    overtime_rate_multiplier: float = 1.0,
    hire_enabled: bool = False,
    hire_productivity_pct: float = 70.0,
    hire_cost_per_head: float = 800.0,
    zones: list | None = None,            # FX.4 — [{name, acres}]; absent = one "Whole farm"
    commitments: list | None = None,      # FX.2 — [{id, kind, ...}]; perennial blocks so far
    **_kwargs,  # absorb unused kwargs for forward-compatibility
) -> list[str]:
    """
    Validate all model inputs.

    Returns a list of warning strings (non-fatal issues).
    Raises ``ValueError`` on any fatal problem.
    """
    warnings = []
    year_round_employees = year_round_employees or []
    seasonal_employees   = seasonal_employees or []

    # 1. Farm infrastructure
    _check_positive(total_land, "total_land")
    _check_positive(harvest_storage_cap, "harvest_storage_cap")
    if opening_cash < 0:
        raise ValueError(f"opening_cash must be ≥ 0, got {opening_cash}.")
    if credit_line < 0:
        raise ValueError(f"credit_line must be ≥ 0, got {credit_line}.")
    if not (1 <= operating_weeks <= 52):
        raise ValueError(f"operating_weeks must be in [1, 52], got {operating_weeks}.")
    # FX.4 — the same resolution the solver uses, so a zone it would refuse is refused here.
    zone_acres = {z["name"]: z["acres"] for z in resolve_zones(zones, total_land)}
    zone_names = list(zone_acres)

    # 2. Rainfall array
    import numpy as np
    rain = np.asarray(rainfall_weekly_L_per_acre)
    if rain.shape != (52,):
        raise ValueError(
            f"rainfall_weekly_L_per_acre must have 52 elements, got {rain.shape}."
        )
    if (rain < 0).any():
        raise ValueError("rainfall_weekly_L_per_acre contains negative values.")

    # 3. Water sources
    # Batch W: the farm says HOW it is watered. Only "irrigated" reads the sources; the other two
    # modes mean "no source", so a source left on with them is ambiguous and refused rather than
    # resolved either way (the adapter clears the form's remembered ticks before it gets here).
    any_source = city_water_enabled or well_enabled or catchment_enabled
    if water_mode not in WATER_MODES:
        raise ValueError(f"water_mode must be one of {list(WATER_MODES)}, got {water_mode!r}.")
    if water_mode != "irrigated" and any_source:
        raise ValueError(
            f"water_mode={water_mode!r} uses no water source, but a source is enabled — "
            f"turn the sources off or use water_mode='irrigated'."
        )
    # Refused, not warned (D11): with every source off the solve came back "optimal" by growing
    # nothing. Here, the one check every caller passes through — not only the app's form.
    if water_mode == "irrigated" and not any_source:
        raise ValueError(
            "No water source enabled (city_water, well, catchment are all disabled) — "
            "turn on at least one, or choose water_mode 'rainfed' or 'unlimited'."
        )
    if catchment_enabled and catchment_surface_area_m2 <= 0:
        raise ValueError(
            "catchment_enabled=True but catchment_surface_area_m2 is 0 or negative."
        )
    if well_enabled and well_weekly_cap_L <= 0:
        raise ValueError("well_enabled=True but well_weekly_cap_L is 0 or negative.")

    # 4. Labor
    _validate_year_round_employees(year_round_employees)
    _validate_seasonal_employees(seasonal_employees)

    # Check that at least some labor capacity exists
    has_capacity = bool(year_round_employees or seasonal_employees)
    if not has_capacity:
        warnings.append(
            "No employees configured. Labor constraints will be uncapped "
            "(capacity = 0), which will likely make the problem infeasible."
        )

    # 5. Equipment proxies
    if max_plant_acres_per_week <= 0:
        raise ValueError(
            f"max_plant_acres_per_week must be positive, got {max_plant_acres_per_week}."
        )
    if max_harvest_acres_per_week <= 0:
        raise ValueError(
            f"max_harvest_acres_per_week must be positive, got {max_harvest_acres_per_week}."
        )

    # R7 — every one of these is charged straight into fixed cost (and the premium into the cash
    # floor), so a bad value is refused, never coerced; a week outside 1-52 would index past the year.
    for v, what in ((rented_acres, "rented_acres"), (cash_rent_per_acre_yr, "cash_rent_per_acre_yr"),
                    (ownership_carrying_rate, "ownership_carrying_rate"),
                    (insurance_premium_per_yr, "insurance_premium_per_yr"),
                    (utilities_cost_per_yr, "utilities_cost_per_yr")):
        _check_nonneg(v, what)
    # A FRACTION, while every human-facing box is in percent — so 6 meaning 6% would bill 600% of
    # installed cost (/code-review max #10). 30% matches the form's max; real I-R-T is ~4-8%.
    if ownership_carrying_rate > 0.30:
        raise ValueError(f"ownership_carrying_rate is a fraction (0.06 = 6%) and at most 0.30, got {ownership_carrying_rate:g}.")
    if rented_acres > total_land:
        raise ValueError(f"rented_acres ({rented_acres:g}) cannot exceed total_land ({total_land:g}).")
    if insurance_payment_week is not None and not (
            _is_number(insurance_payment_week) and float(insurance_payment_week).is_integer()
            and 1 <= insurance_payment_week <= 52):
        raise ValueError(f"insurance_payment_week must be a whole week 1-52 or omitted, got {insurance_payment_week!r}.")
    # Keys are checked as well as values: an unknown class ('equip_storage', 'machinery') would be
    # silently ignored by the solver and charge nothing — the silent-drop class.
    if not isinstance(capital_cost_per_unit or {}, dict):
        raise ValueError(f"capital_cost_per_unit must be a mapping of asset class to $ per unit, got {capital_cost_per_unit!r}.")
    # Every owned capacity is a depreciation base and (R7) a carrying base: a negative one is a
    # building that pays the farm (/code-review max #2).
    for cls, cap in (owned_capacity or {}).items():
        _check_nonneg(cap, f"{cls} capacity")
    for cls, v in (capital_cost_per_unit or {}).items():
        if cls not in (owned_capacity or {}):
            raise ValueError(f"capital_cost_per_unit: unknown asset class {cls!r}; expected one of {sorted(owned_capacity or {})}.")
        _check_nonneg(v, f"capital_cost_per_unit[{cls!r}]")
        # A capacity at the 'no constraint' sentinel is not a building — carrying it would charge
        # on a billion cubic metres (the mechanism behind the earlier −$25.9B "optimal" plan).
        if v > 0 and ownership_carrying_rate > 0 and owned_capacity[cls] >= 1e8:
            raise ValueError(f"{cls}: an ownership carrying cost needs a real capacity, not the "
                             f"'no constraint' default ({owned_capacity[cls]:g}).")

    # 6. Channels
    if not channels:
        raise ValueError("At least one channel must be defined.")
    ch_names = [ch["name"] for ch in channels]
    if len(ch_names) != len(set(ch_names)):
        raise ValueError(f"Channel names must be unique. Got: {ch_names}.")
    # A channel's fixed selling fee is charged straight into net profit and the C13 cash floor
    # (W8). A None, NaN or negative fee must be refused, not coerced: NaN would turn the profit
    # NaN, and a negative fee is a stall that pays the farm.
    for ch in channels:
        _check_nonneg(ch.get("fixed_selling_cost_per_wk", 0.0),
                      f"Channel '{ch['name']}': fixed_selling_cost_per_wk")

    # 7. Crops
    if not crops:
        raise ValueError("At least one crop must be defined.")

    # Crop names must be unique for the same reason channel names must be, and the reason is
    # not cosmetic: every per-crop report the solver returns is a dict KEYED BY NAME —
    # `channel_sales[ch].by_crop`, `crop_contribution`, `waste_by_crop`. A duplicate name is
    # last-write-wins in those maps while the channel and farm totals still accumulate BOTH
    # crops, so the parts stop summing to the whole with nothing raised.
    #
    # Measured on the two-crop fixture with both crops renamed the same: the channel reported
    # 475,898 lb sold while its by_crop entries summed to 118,578 — 357,320 lb (75%) missing
    # from the pies and the sales CSV, with the P&L revenue line still correct. Silent, and
    # only on the reporting side, which is the worst shape this project keeps finding.
    crop_names = [c.get("name") for c in crops]
    if len(crop_names) != len(set(crop_names)):
        dupes = sorted({n for n in crop_names if crop_names.count(n) > 1})
        raise ValueError(
            f"Crop names must be unique — every per-crop result is keyed by name, so "
            f"duplicates silently drop pounds from the sales reports. Rename: {dupes}."
        )

    total_committed = 0.0
    standing = []                           # (crop, acres in the ground in week 1, zones it may stand in)
    for crop in crops:
        # R1: charged straight into the objective — a negative rate PAYS the farm (reproduced:
        # -$2,000/acre turned a -$99k farm into +$139k "optimal"), NaN crashes scipy.
        _check_nonneg(crop.get("crop_protection_cost_per_acre", 0.0),
                      f"Crop '{crop.get('name')}': crop_protection_cost_per_acre")
        warnings.extend(_validate_crop(crop, ch_names, year))
        # Acres already in the ground (S14). Checked here rather than in _validate_crop
        # because it is only meaningful against the farm's size.
        committed = float(crop.get("committed_acres", 0.0) or 0.0)
        if committed < 0:
            raise ValueError(
                f"Crop '{crop['name']}' committed_acres must be >= 0, got {committed:g}."
            )
        if committed > total_land:
            raise ValueError(
                f"Crop '{crop['name']}' has {committed:g} acres already committed, more than "
                f"the farm's {total_land:g} acres. No plan can be built around it."
            )
        # FX.4 — a crop's zones must be the farm's, and its commitment must fit in them.
        eligible = crop_zone_names(crop, zone_names)
        eligible_acres = sum(zone_acres[z] for z in eligible)
        if committed > eligible_acres + 1e-9:
            raise ValueError(
                f"Crop '{crop['name']}' has {committed:g} acres already committed, but the "
                f"zones it may stand in hold only {eligible_acres:g} acres."
            )
        # A minimum planting no eligible zone can hold makes the crop unplantable, and the
        # diagnosis would call it "outcompeted". C10 applies per zone slot (FX.4).
        # A perennial's patches are pinned with no minimum (C10 skips pins), so its card's
        # minimum is never applied — refusing a patch for it would refuse a valid farm (FX.2).
        min_acres = 0.0 if crop.get("perennial") else float(crop.get("min_acreage_if_planted", 0.0) or 0.0)
        too_small = [z for z in eligible if zone_acres[z] + 1e-9 < min_acres]
        if too_small and len(too_small) == len(eligible):
            raise ValueError(
                f"Crop '{crop['name']}' needs at least {min_acres:g} acres per planting, but "
                f"every zone it may stand in is smaller ({', '.join(too_small)}). Lower the "
                f"minimum or allow a larger zone."
            )
        if too_small:
            warnings.append(
                f"Crop '{crop['name']}' cannot be planted in {', '.join(too_small)}: its "
                f"{min_acres:g}-acre minimum planting is larger than the zone."
            )
        standing.append((crop["name"], committed, set(eligible)))
        if committed > 0:
            # NOT checked here any more: `committed_acres < min_acreage_if_planted`. That was
            # added on a mis-diagnosis and rejected farms that solve perfectly well — C15 is a
            # floor and C10 simply raises the planting to the lot size. Measured: 2 committed
            # acres against a 10-acre minimum solves optimal at 147 acres. The old message also
            # told the grower to raise their committed acreage to match, i.e. to misstate what
            # is actually in the ground.
            #
            # Still worth flagging: a commitment above the crop's diversity ceiling (C8) is
            # infeasible, and the infeasible path returns a bare HiGHS string with no diagnosis.
            div_max = float(crop.get("crop_diversity_max", 1.0) or 1.0)
            if committed > total_land * div_max + 1e-9:
                raise ValueError(
                    f"Crop '{crop['name']}' has {committed:g} acres already committed, but its "
                    f"diversity ceiling allows at most {total_land * div_max:g} acres "
                    f"({div_max:g} of {total_land:g}). Raise the ceiling or correct the "
                    f"committed acreage."
                )
            if not crop.get("overwinters", False):
                warnings.append(
                    f"Crop '{crop['name']}' has {committed:g} committed acres but is not marked "
                    f"as overwintering. Committed acres are ground standing at the START of the "
                    f"planning year, so only an overwintering crop can hold any."
                )
        total_committed += committed
    # FX.2 — a perennial block stands in its zone all year, so in week 1 it competes for ground
    # with the overwintered acres above: both join the land and zone checks that follow.
    blocks = resolve_perennial_blocks(commitments, crops, zone_names)
    for b in blocks:
        standing.append((f"{b['crop']} (block {b['id']})", b["acres"], {b["zone"]}))
        total_committed += b["acres"]
    # FX.5 — C8 is one row per identity, so a crop's commitments and its variants' share one
    # diversity ceiling: each can fit it alone and together not, which HiGHS reports as a bare
    # "infeasible". Measured: Garlic + a Hardneck variant at 33.6 ac each against a 48-ac ceiling.
    by_identity = {}
    for crop in crops:
        committed = float(crop.get("committed_acres", 0.0) or 0.0)
        if committed > 0:
            by_identity.setdefault(crop.get("sells_as") or crop["name"], []).append(
                (crop["name"], committed, float(crop.get("crop_diversity_max", 1.0) or 1.0)))
    for parent, held in by_identity.items():
        together = sum(c for _, c, _ in held)
        ceiling = total_land * held[0][2]
        if len(held) > 1 and together > ceiling + 1e-9:
            raise ValueError(
                f"{', '.join(n for n, _, _ in held)} sell as '{parent}' and share its diversity "
                f"ceiling of {ceiling:g} acres, but have {together:g} acres committed between "
                f"them. Raise the ceiling or correct the committed acreage."
            )
    if total_committed > total_land:
        raise ValueError(
            f"Committed plantings total {total_committed:g} acres against a {total_land:g}-acre "
            f"farm. Reduce them, or the plan is infeasible before it starts."
        )
    # FX.4 — the commitments must also fit zone by zone. A crop allowed in several zones can
    # split its acres, so a per-zone sum is not the test; Hall's condition is: for every group
    # of zones, the commitments that can ONLY stand inside it fit its acres. 2^zones groups,
    # fine at the 3-5 zones a farm has. Otherwise HiGHS returns a bare "infeasible".
    from itertools import combinations
    for k in range(1, len(zone_names)):
        for group in combinations(zone_names, k):
            inside = [(n, a) for n, a, el in standing if a > 0 and el <= set(group)]
            need = sum(a for _, a in inside)
            room = sum(zone_acres[z] for z in group)
            if need > room + 1e-9:
                raise ValueError(
                    f"Committed acres of {', '.join(n for n, _ in inside)} ({need:g} ac) can "
                    f"only stand in {', '.join(group)}, which hold{'s' if k == 1 else ''} "
                    f"{room:g} acres."
                )

    # 8. Global succession check
    try:
        succs = generate_successions(crops, year, zone_names)
    except ValueError as e:
        raise ValueError(f"Succession generation failed: {e}") from e

    if not succs and not blocks:
        raise ValueError(
            "No successions generated for any crop. Season windows are PLANTING windows, so "
            "check that each one holds at least one start week whose cycle finishes by week 52 "
            "— or tick 'overwinters' for a crop that is fall-planted and harvested the "
            "following year."
        )

    # Per-crop check
    for c_idx, crop in enumerate(crops):
        crop_succs = [s for s in succs if s["crop"] == c_idx]
        if not crop_succs and not crop.get("perennial"):
            warnings.append(
                f"Crop '{crop['name']}': no successions generated. "
                f"Season window(s) may be too narrow for the crop cycle length."
            )

    # 9. Demand
    has_any_demand = False
    for crop in crops:
        for ch_name in ch_names:
            ch_spec = crop.get("channels", {}).get(ch_name, {})
            cap_type = ch_spec.get("demand_cap_type", "")
            if cap_type == "annual" and ch_spec.get("annual_demand_lbs", 0) > 0:
                has_any_demand = True
            elif cap_type == "weekly_flat" and ch_spec.get("weekly_demand_lbs", 0) > 0:
                has_any_demand = True
            elif cap_type == "weekly_varying" and ch_spec.get("demand_ranges"):
                has_any_demand = True

    if not has_any_demand:
        warnings.append(
            "No positive demand caps found. "
            "The solver will produce zero revenue (no harvest scheduled)."
        )

    # Labour flex terms (L.2 / L.3), refused rather than clamped. Checked only when the lever is
    # on, so a caller that never hires is not rejected for a hiring default.
    if overtime_enabled and not (_is_number(overtime_rate_multiplier) and overtime_rate_multiplier >= 1.0):
        raise ValueError(f"Overtime pay multiplier must be at least 1.0 (straight time), got "
                         f"{overtime_rate_multiplier!r}. Use 1.5 where state law requires ag overtime.")
    if hire_enabled:
        if not (_is_number(hire_productivity_pct) and 0 < hire_productivity_pct <= 100):
            raise ValueError(f"New-hire productivity must be above 0% and at most 100% (a new hand "
                             f"is not faster than your crew), got {hire_productivity_pct!r}.")
        _check_nonneg(hire_cost_per_head, "One-off cost per new hire ($)")

    return warnings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_perennial_crop(crop: dict, name: str) -> None:
    """FX.2 — a perennial card describes the PRODUCT (channels, storage, and per-week labour,
    water, fertiliser and fuel rates for its grow and harvest phases — there is no planting phase);
    its blocks in the commitments table carry acres, this year's yield and harvest weeks.
    So it needs none of an annual's calendar keys, and the two carry-in fields have no meaning on
    it: the block IS the ground already standing. Refused rather than ignored."""
    if crop.get("perennial") is not True:
        raise ValueError(f"Crop '{name}': perennial must be true or false, got {crop['perennial']!r}.")
    missing = {"name", "crop_size_m3_per_lb", "labor_grow", "labor_harv", "water_grow",
               "water_harv", "fert_grow", "fert_harv", "fuel_grow", "fuel_harv"} - crop.keys()
    if missing:
        raise ValueError(f"Crop '{name}' missing required keys: {missing}.")
    if crop["crop_size_m3_per_lb"] < 0:
        raise ValueError(f"Crop '{name}' crop_size_m3_per_lb must be ≥ 0.")
    if float(crop.get("committed_acres", 0.0) or 0.0) > 0 or crop.get("overwinters"):
        raise ValueError(
            f"Crop '{name}' is perennial, so its ground is its blocks in the commitments table — "
            f"clear its committed acres and 'overwinters'."
        )


def _require_employee_numbers(emp: dict, keys: tuple, kind: str, i: int) -> None:
    # A non-numeric value (None from a blanked field, a string from a hand-edited file) must be
    # refused as ValueError HERE: a bare `emp["wage"] < 0` raises TypeError instead, and Step 0
    # only converts ValueError into `invalid_input` — everything else fails OPEN with a warning,
    # which for a wage means the number is invented downstream.
    for key in keys:
        v = emp.get(key)
        if not _is_number(v):   # NaN/inf too: the bounds checks below are False for NaN (#8)
            raise ValueError(
                f"{kind} employee '{emp.get('position', i)}' {key} must be a number, got {v!r}."
            )
    # Optional keys labor.py does arithmetic on the moment they are present — a None or
    # string there raises TypeError in Step 2, OUTSIDE the Step-0 try, handing a caller a
    # traceback where every other bad input gets invalid_input.
    for key in ("benefits_pct", "fica_pct", "field_time_pct", "admin_pct", "max_ot_hrs", "max_more"):
        if key in emp:
            v = emp[key]
            if not _is_number(v):
                raise ValueError(
                    f"{kind} employee '{emp.get('position', i)}' {key} must be a number, "
                    f"got {v!r}."
                )
    # Batch L roster columns: refused out of range, never clamped downstream.
    who = f"{kind} employee '{emp.get('position', i)}'"
    for key in ("admin_pct", "field_time_pct"):
        if key in emp and not 0 <= emp[key] <= 100:
            raise ValueError(f"{who} {key} must be between 0 and 100, got {emp[key]!r}.")
    if "max_ot_hrs" in emp and not 0 <= emp["max_ot_hrs"] <= emp.get("hours_per_week", 0):
        raise ValueError(f"{who} 'Max OT hrs/wk' must be between 0 (no overtime) and its regular "
                         f"Hrs/Wk ({emp.get('hours_per_week')!r}), got {emp['max_ot_hrs']!r}.")
    # FICA is the all-pay PART of the load (benefits_pct = fica + straight-time); more FICA than
    # load would make the straight-time part negative and under-price every overtime hour.
    if "fica_pct" in emp and not 0 <= emp["fica_pct"] <= emp.get("benefits_pct", 0.0):
        raise ValueError(f"{who} fica_pct ({emp['fica_pct']!r}) must be between 0 and its total "
                         f"payroll load benefits_pct ({emp.get('benefits_pct', 0.0)!r}).")
    if "max_more" in emp and not (emp["max_more"] >= 0 and float(emp["max_more"]).is_integer()):
        raise ValueError(f"{who} 'Max more' must be a whole number ≥ 0, got {emp['max_more']!r}.")


def _require_employee_bounds(emp: dict, kind: str, i: int) -> None:
    """The checks both employee kinds share: count ≥ 1, wage ≥ 0, hours ≥ 1.

    ONE implementation on purpose. These lived as per-kind copies, and the seasonal copy
    shipped without the wage/hours lines — a wage of -18 then booked payroll as INCOME
    (fixed_cost_split['wages'] = -$220,800, a $561,600 phantom profit swing) and turned the
    inferred hire price negative, so the optimizer was PAID per hired hour. Zero warnings.
    A rule spelled once cannot be forgotten in one of its copies.
    """
    who = f"{kind} employee '{emp.get('position', i)}'"
    if emp["count"] < 1:
        raise ValueError(f"{who} count must be ≥ 1.")
    if emp["wage"] < 0:
        raise ValueError(f"{who} wage must be ≥ 0.")
    if emp["hours_per_week"] < 1:
        raise ValueError(f"{who} hours_per_week must be ≥ 1.")


def _validate_year_round_employees(employees: list) -> None:
    required = {"position", "count", "type", "wage", "hours_per_week"}
    for i, emp in enumerate(employees):
        missing = required - emp.keys()
        if missing:
            raise ValueError(
                f"Year-round employee #{i} missing required keys: {missing}."
            )
        if emp["type"].lower() not in ("salary", "hourly"):
            raise ValueError(
                f"Year-round employee '{emp.get('position', i)}' type must be "
                f"'salary' or 'hourly', got '{emp['type']}'."
            )
        _require_employee_numbers(emp, ("count", "wage", "hours_per_week"), "Year-round", i)
        _require_employee_bounds(emp, "Year-round", i)


def _validate_seasonal_employees(employees: list) -> None:
    required = {"position", "count", "type", "start_week", "end_week",
                "wage", "hours_per_week"}
    for i, emp in enumerate(employees):
        missing = required - emp.keys()
        if missing:
            raise ValueError(
                f"Seasonal employee #{i} missing required keys: {missing}."
            )
        if emp["type"].upper() not in SEASONAL_TYPES:
            raise ValueError(
                f"Seasonal employee '{emp.get('position', i)}' type must be "
                f"'FT' or 'PT', got '{emp['type']}'."
            )
        _require_employee_numbers(
            emp, ("count", "wage", "hours_per_week", "start_week", "end_week"), "Seasonal", i,
        )
        _require_employee_bounds(emp, "Seasonal", i)
        if not (1 <= emp["start_week"] <= 52 and 1 <= emp["end_week"] <= 52):
            raise ValueError(
                f"Seasonal employee '{emp.get('position', i)}' "
                f"start_week/end_week must be in [1, 52]."
            )
        if emp["start_week"] > emp["end_week"]:
            raise ValueError(
                f"Seasonal employee '{emp.get('position', i)}' "
                f"start_week ({emp['start_week']}) > end_week ({emp['end_week']})."
            )


def _validate_crop(crop: dict, ch_names: list[str], year: int) -> list[str]:
    """Validate a single crop dict. Returns list of warnings."""
    warnings = []
    name = crop.get("name", "<unnamed>")
    if crop.get("perennial"):
        _validate_perennial_crop(crop, name)
        _validate_crop_channels(crop, ch_names, name)
        return warnings

    required_keys = {
        "name", "days_to_maturity", "planting_weeks", "harvest_weeks",
        "seasons", "min_acreage_if_planted", "crop_diversity_max",
        "yield_per_acre", "crop_size_m3_per_lb",
        "labor_plant", "labor_grow", "labor_harv",
        "water_plant", "water_grow", "water_harv",
        "fert_plant", "fert_grow", "fert_harv",
        "fuel_plant", "fuel_grow", "fuel_harv",
    }
    missing = required_keys - crop.keys()
    if missing:
        raise ValueError(f"Crop '{name}' missing required keys: {missing}.")

    dtm = crop["days_to_maturity"]
    if dtm < 7:
        raise ValueError(f"Crop '{name}' days_to_maturity must be ≥ 7, got {dtm}.")

    total_weeks = math.ceil(dtm / 7)
    plant_w = crop["planting_weeks"]
    harv_w  = crop["harvest_weeks"]
    grow_w  = total_weeks - plant_w - harv_w

    if plant_w < 1:
        raise ValueError(f"Crop '{name}' planting_weeks must be ≥ 1, got {plant_w}.")
    if harv_w < 1:
        raise ValueError(f"Crop '{name}' harvest_weeks must be ≥ 1, got {harv_w}.")
    if grow_w < 0:
        raise ValueError(
            f"Crop '{name}': planting_weeks ({plant_w}) + harvest_weeks ({harv_w}) "
            f"exceed total cycle ({total_weeks} weeks from {dtm} days_to_maturity). "
            f"Increase days_to_maturity or reduce phase weeks."
        )

    if crop["yield_per_acre"] <= 0:
        raise ValueError(f"Crop '{name}' yield_per_acre must be positive.")
    if crop["crop_size_m3_per_lb"] < 0:
        raise ValueError(f"Crop '{name}' crop_size_m3_per_lb must be ≥ 0.")
    if not (0 < crop["crop_diversity_max"] <= 1):
        raise ValueError(
            f"Crop '{name}' crop_diversity_max must be in (0, 1], "
            f"got {crop['crop_diversity_max']}."
        )
    if crop["min_acreage_if_planted"] < 0:
        raise ValueError(f"Crop '{name}' min_acreage_if_planted must be ≥ 0.")

    seasons = crop.get("seasons", [])
    if not seasons:
        raise ValueError(f"Crop '{name}' must have at least one season window.")
    for s in seasons:
        if "start" not in s or "end" not in s:
            raise ValueError(f"Crop '{name}' season entry missing 'start' or 'end'.")
        sw = week_of_year(s["start"], year)
        ew = week_of_year(s["end"],   year)
        # A window that ends before it starts WRAPS the year (e.g. Nov-to-Feb planting) and is
        # generated correctly by generate_successions. Rejecting it here contradicted the
        # generator and would have failed exactly the fall-planted crops B6 exists to support.
        window_size = (ew - sw + 1) if ew >= sw else (52 - sw + 1) + ew

        # NOT a warning any more: seasons are PLANTING windows, so a window narrower than the
        # cycle is an ordinary short planting window, not an empty one. The old text asserted
        # "No successions will be generated for this window", which was the B5 defect stated as
        # if it were intended behaviour — a grower acting on it would widen a window for no
        # reason and change their plan.
        if not crop.get("overwinters", False) and sw + total_weeks - 1 > 52:
            warnings.append(
                f"Crop '{name}' season window {s['start']}–{s['end']}: a cycle started at the "
                f"beginning of this window ({total_weeks} weeks) would run past week 52. Those "
                f"start weeks are skipped. Tick 'overwinters' if this crop is meant to be "
                f"fall-planted and harvested the following year."
            )

    _validate_crop_channels(crop, ch_names, name)
    return warnings


def _validate_crop_channels(crop: dict, ch_names: list[str], name: str) -> None:
    crop_channels = crop.get("channels", {})
    for ch_name in ch_names:
        if ch_name not in crop_channels:
            continue
        ch_spec = crop_channels[ch_name]
        if "price_per_lb" not in ch_spec:
            raise ValueError(
                f"Crop '{name}', channel '{ch_name}': missing 'price_per_lb'."
            )
        if ch_spec.get("price_per_lb", 0) < 0:
            raise ValueError(
                f"Crop '{name}', channel '{ch_name}': price_per_lb must be ≥ 0."
            )
        cap_type = ch_spec.get("demand_cap_type", "")
        if cap_type not in ("annual", "weekly_flat", "weekly_varying"):
            raise ValueError(
                f"Crop '{name}', channel '{ch_name}': demand_cap_type must be "
                f"'annual', 'weekly_flat', or 'weekly_varying', got '{cap_type}'."
            )
