"""
labor.py — Labor capacity and cost utilities for the 52-week farm model.

Two employee categories (per SPEC_v2.md §5D):

  Year-round employees
  ├── type = "salary"  → fixed weekly cost; contributes to capacity
  └── type = "hourly"  → variable weekly cost; contributes to regular capacity

  Seasonal employees
  ├── type = "FT" or "PT"  (both are hourly)
  └── available only during [start_week, end_week]
  └── optional piece_rate_per_lb → treated as additional $/lb packaging cost
                                    (NOT a labor cost in the solver; tracked separately)

Derived arrays (all 52-element, 0-indexed for weeks 1..52):

  labor_capacity[w]          total available hours in week w (salaried + hourly)
  hourly_labor_rate[w]       blended $/hour across all hourly employees available in w
                              (including benefits; weighted by count × hours_per_week)
  salaried_weekly_fixed_cost total $/week for salaried staff (constant, added to fixed cost)
  piece_rate_per_lb[c][ch]   $/lb harvest cost per crop/channel — sourced from crop defs,
                              not computed here, but the module documents the pattern.

Overtime (if enabled):
  The solver receives labor_capacity_hourly_only[w] as the threshold above which
  overtime kicks in. The overtime variable covers hours beyond regular hourly capacity
  (salaried hours are NOT subject to overtime rules).
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def compute_labor_arrays(
    year_round_employees: list[dict],
    seasonal_employees: list[dict],
    n_weeks: int = 52,
) -> dict:
    """
    Compute all derived labor arrays from employee configuration.

    Parameters
    ----------
    year_round_employees : list[dict]
        Each dict with keys: position, count, type ("salary"|"hourly"),
        wage ($/year if salary; $/hour if hourly), hours_per_week, benefits_pct.

    seasonal_employees : list[dict]
        Each dict with keys: position, count, type ("FT"|"PT"),
        start_week, end_week, wage ($/hour), hours_per_week, benefits_pct,
        and optionally: min_guaranteed_hours (int), piece_rate_per_lb (float).

    n_weeks : int
        Planning horizon (52).

    Returns
    -------
    dict with keys:
        "labor_capacity"            np.ndarray shape (n_weeks,) — total hrs/week (1-indexed)
        "hourly_labor_rate"         np.ndarray shape (n_weeks,) — blended $/hr
        "labor_capacity_hourly"     np.ndarray shape (n_weeks,) — hourly-only hrs/week
        "salaried_weekly_cost"      float — $/week, constant fixed cost
        "guaranteed_hourly_cost"    np.ndarray shape (n_weeks,) — $/week for guaranteed mins
        "piece_rate_workers"        list[dict] — seasonal workers with piece_rate_per_lb set
    """
    labor_capacity        = np.zeros(n_weeks, dtype=float)
    labor_capacity_hourly = np.zeros(n_weeks, dtype=float)
    hourly_weighted_wages = np.zeros(n_weeks, dtype=float)   # sum(count × hrs × rate)
    hourly_weighted_hours = np.zeros(n_weeks, dtype=float)   # sum(count × hrs)
    guaranteed_cost       = np.zeros(n_weeks, dtype=float)

    salaried_weekly_cost  = 0.0
    piece_rate_workers    = []

    # --- Year-round employees (available every week) ---
    for emp in year_round_employees:
        count      = emp["count"]
        emp_type   = emp["type"].lower()
        wage       = emp["wage"]
        hrs        = emp["hours_per_week"]
        bene       = emp.get("benefits_pct", 0.0)

        total_hrs_per_week = count * hrs
        labor_capacity += total_hrs_per_week

        if emp_type == "salary":
            # Annual wage → weekly cost
            weekly_cost = count * wage * (1 + bene) / 52
            salaried_weekly_cost += weekly_cost

        elif emp_type == "hourly":
            effective_rate = wage * (1 + bene)
            labor_capacity_hourly += total_hrs_per_week
            hourly_weighted_wages += total_hrs_per_week * effective_rate
            hourly_weighted_hours += total_hrs_per_week

        else:
            raise ValueError(
                f"Year-round employee '{emp.get('position', '?')}' has unknown type "
                f"'{emp_type}'. Expected 'salary' or 'hourly'."
            )

    # --- Seasonal employees ---
    for emp in seasonal_employees:
        count      = emp["count"]
        emp_type   = emp["type"].upper()   # "FT" or "PT" — both hourly
        start_w    = emp["start_week"]     # 1-indexed
        end_w      = emp["end_week"]       # 1-indexed, inclusive
        wage       = emp["wage"]           # $/hour
        hrs        = emp["hours_per_week"]
        bene       = emp.get("benefits_pct", 0.0)
        min_hrs    = emp.get("min_guaranteed_hours", 0)
        piece_rate = emp.get("piece_rate_per_lb", None)

        if emp_type not in ("FT", "PT"):
            raise ValueError(
                f"Seasonal employee '{emp.get('position', '?')}' has unknown type "
                f"'{emp_type}'. Expected 'FT' or 'PT'."
            )

        if not (1 <= start_w <= n_weeks and 1 <= end_w <= n_weeks):
            raise ValueError(
                f"Seasonal employee '{emp.get('position', '?')}': "
                f"start_week={start_w}, end_week={end_w} must be in [1, {n_weeks}]."
            )

        if piece_rate is not None:
            piece_rate_workers.append(emp)

        effective_rate = wage * (1 + bene)
        total_hrs_per_week = count * hrs

        # Week indices are 0-based internally (week w → index w-1)
        for w_idx in range(start_w - 1, end_w):
            labor_capacity[w_idx]        += total_hrs_per_week
            labor_capacity_hourly[w_idx] += total_hrs_per_week
            hourly_weighted_wages[w_idx] += total_hrs_per_week * effective_rate
            hourly_weighted_hours[w_idx] += total_hrs_per_week

            # Guaranteed minimum hours: must pay even if less work available
            if min_hrs > 0:
                guaranteed_hrs   = count * min(min_hrs, hrs)
                guaranteed_cost[w_idx] += guaranteed_hrs * effective_rate

    # --- Blended hourly rate ---
    # Where no hourly employees are available, rate = 0 (no variable labor cost)
    with np.errstate(invalid="ignore", divide="ignore"):
        hourly_labor_rate = np.where(
            hourly_weighted_hours > 0,
            hourly_weighted_wages / hourly_weighted_hours,
            0.0,
        )

    return {
        "labor_capacity":         labor_capacity,
        "labor_capacity_hourly":  labor_capacity_hourly,
        "hourly_labor_rate":      hourly_labor_rate,
        "salaried_weekly_cost":   salaried_weekly_cost,
        "guaranteed_hourly_cost": guaranteed_cost,
        "piece_rate_workers":     piece_rate_workers,
    }


# ---------------------------------------------------------------------------
# Labor rate per succession per week (lookup table for solver)
# ---------------------------------------------------------------------------

def compute_labor_rates(
    successions: list[dict],
    crops: list[dict],
    n_weeks: int = 52,
) -> np.ndarray:
    """
    Return labor_rate[i][w] in hrs/acre/week (shape: n_successions × 53,
    week-index 0 unused).

    Phase keys expected in crop dict: "labor_plant", "labor_grow", "labor_harv".
    """
    _LABOR_KEY = ["labor_plant", "labor_grow", "labor_harv"]
    n = len(successions)
    result = np.zeros((n, n_weeks + 1), dtype=float)

    for i, s in enumerate(successions):
        crop = crops[s["crop"]]
        for week, phase in zip(s["weeks"], s["phases"]):
            if 1 <= week <= n_weeks:
                result[i][week] = crop[_LABOR_KEY[phase]]

    return result
