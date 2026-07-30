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

  committed_weekly_wages[w]  $/week owed to EVERY listed worker (W12) — the wage bill, charged
                              on full hours regardless of how much the crops use
  labor_capacity[w]          total available hours in week w (salaried + hourly)
  hourly_labor_rate[w]       blended $/hour across all hourly employees available in w
                              (including benefits; weighted by count × hours_per_week). Prices
                              the OVERTIME and HIRE premiums only — regular hours are committed.
  piece_rate_per_lb[c][ch]   $/lb harvest cost per crop/channel — sourced from crop defs,
                              not computed here, but the module documents the pattern.

Overtime / hired labour (if enabled):
  Bought beyond TOTAL labor_capacity, not beyond the hourly-only part — measuring against
  hourly-only was the bug that removed C14, because it let flexibility buy back capacity the
  farm already had. Bought hours carry their FULL wage: the committed bill pays for the crew's
  stated hours, and these are extra (W12).
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
        and optionally: piece_rate_per_lb (float).
        ⚠️ `min_guaranteed_hours` is ACCEPTED AND IGNORED (W11/W14). It can never bind: committed
        wages already pay count x hours_per_week, which is >= count x min(min_guaranteed, hours)
        for every input. Wiring it back would put a floor underneath a floor and double-charge.

    n_weeks : int
        Planning horizon (52).

    Returns
    -------
    dict with keys:
        "labor_capacity"            np.ndarray shape (n_weeks,) — total hrs/week (1-indexed)
        "hourly_labor_rate"         np.ndarray shape (n_weeks,) — blended $/hr
        "labor_capacity_hourly"     np.ndarray shape (n_weeks,) — hourly-only hrs/week
        "committed_weekly_wages"    np.ndarray shape (n_weeks,) — $/week owed to ALL listed staff
        "committed_weekly_hours"    np.ndarray shape (n_weeks,) — PAID hrs/week (not field-adj)
        "fallback_hourly_wage"      float — $/hr for bought hours when a week has no blend
        "salaried_weekly_cost"      float — $/week for salaried staff.
                                    ⚠️ DEAD, and do NOT add it to fixed cost: this money
                                    is already inside `committed_weekly_wages` (W12/W14)
        "piece_rate_workers"        list[dict] — seasonal workers with piece_rate_per_lb set
    """
    labor_capacity        = np.zeros(n_weeks, dtype=float)
    labor_capacity_hourly = np.zeros(n_weeks, dtype=float)
    hourly_weighted_wages = np.zeros(n_weeks, dtype=float)   # sum(count × hrs × rate)
    hourly_weighted_hours = np.zeros(n_weeks, dtype=float)   # sum(count × hrs)

    salaried_weekly_cost  = 0.0
    # Wages the farm has COMMITTED to, per week, across every listed worker (W12). A worker on
    # the payroll is paid for their stated hours over their stated weeks whether or not the crops
    # need them — the same basis the salaried line has always used, now applied to hourly and
    # seasonal staff too. Charged on FULL hours: `field_time_pct` limits how much of a worker's
    # time is available to crops, not how much of their wage the farm owes.
    committed_weekly_wages = np.zeros(n_weeks, dtype=float)
    committed_weekly_hours = np.zeros(n_weeks, dtype=float)   # PAID hours, not field-adjusted
    piece_rate_workers    = []

    # --- Year-round employees (available every week) ---
    for emp in year_round_employees:
        count      = emp["count"]
        emp_type   = emp["type"].lower()
        wage       = emp["wage"]
        hrs        = emp["hours_per_week"]
        bene       = emp.get("benefits_pct", 0.0)
        # Max share of this worker's hours available for crop field work (cap, not average).
        # A farm manager might cap at ~80% in slow weeks; field crew ~100%. Default 100%.
        field      = max(0.0, min(1.0, emp.get("field_time_pct", 100.0) / 100.0))

        total_hrs_per_week = count * hrs * field
        labor_capacity += total_hrs_per_week

        if emp_type == "salary":
            # Annual wage → weekly cost
            weekly_cost = count * wage * (1 + bene) / 52
            salaried_weekly_cost += weekly_cost
            committed_weekly_wages += weekly_cost
            committed_weekly_hours += count * hrs

        elif emp_type == "hourly":
            effective_rate = wage * (1 + bene)
            committed_weekly_wages += count * hrs * effective_rate
            committed_weekly_hours += count * hrs
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
        piece_rate = emp.get("piece_rate_per_lb", None)
        field      = max(0.0, min(1.0, emp.get("field_time_pct", 100.0) / 100.0))

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
        # Order, not just range. `range(start-1, end)` is EMPTY when start > end, so a
        # wrap-around window (a winter crew entered as weeks 45-5) silently contributed no
        # capacity and — since W12 — no wages either, for a crew the farm is really paying.
        # validate_params catches this on the app path; this is a public util that tests and any
        # future caller reach directly, and losing a whole wage bill in silence is worse than the
        # capacity it used to lose.
        if start_w > end_w:
            raise ValueError(
                f"Seasonal employee '{emp.get('position', '?')}': start_week={start_w} is after "
                f"end_week={end_w}. A window that wraps the year is not supported — enter it as "
                f"two employees, one per side of week {n_weeks}."
            )

        if piece_rate is not None:
            piece_rate_workers.append(emp)

        effective_rate = wage * (1 + bene)
        total_hrs_per_week = count * hrs * field

        # Week indices are 0-based internally (week w → index w-1)
        for w_idx in range(start_w - 1, end_w):
            committed_weekly_wages[w_idx] += count * hrs * effective_rate
            committed_weekly_hours[w_idx] += count * hrs
            labor_capacity[w_idx]        += total_hrs_per_week
            labor_capacity_hourly[w_idx] += total_hrs_per_week
            hourly_weighted_wages[w_idx] += total_hrs_per_week * effective_rate
            hourly_weighted_hours[w_idx] += total_hrs_per_week


    # --- Blended hourly rate ---
    # Where no hourly employees are available, rate = 0 (no variable labor cost)
    with np.errstate(invalid="ignore", divide="ignore"):
        hourly_labor_rate = np.where(
            hourly_weighted_hours > 0,
            hourly_weighted_wages / hourly_weighted_hours,
            0.0,
        )

    # What one more hour costs when the week has no hourly crew to blend (W12 follow-up).
    #
    # `hourly_labor_rate` is the blend of the EXISTING hourly staff, so it is 0 in any week they
    # are not on — and once W12 stopped charging base wages through the crop coefficients, a zero
    # blend meant a bought hour was FREE. Measured: 80 hired hours at $0.00 on a fixture whose
    # only hourly crew is seasonal. The farm's own average paid wage is the honest fallback: it is
    # what this farm actually pays for an hour of work, inferred from the crew it described.
    total_paid_hours = float(committed_weekly_hours.sum())
    fallback_wage = (float(committed_weekly_wages.sum()) / total_paid_hours
                     if total_paid_hours > 0 else 0.0)

    return {
        "committed_weekly_wages": committed_weekly_wages,
        "committed_weekly_hours": committed_weekly_hours,
        "fallback_hourly_wage":   fallback_wage,
        "labor_capacity":         labor_capacity,
        "labor_capacity_hourly":  labor_capacity_hourly,
        "hourly_labor_rate":      hourly_labor_rate,
        "salaried_weekly_cost":   salaried_weekly_cost,
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

    Each rate is PER WEEK of its phase, charged once for every week the phase occupies —
    a crop with planting_weeks 2 costs 2 x labor_plant per acre to plant. Comparing the
    raw fields across crops is therefore only valid at equal phase length.
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
