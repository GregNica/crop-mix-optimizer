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
  labor_by_role[r]           the roster as named weekly rows, incl. each role's overtime
                              cap and rate (L.2) — see _role
  piece_rate_per_lb[c][ch]   $/lb harvest cost per crop/channel — sourced from crop defs,
                              not computed here, but the module documents the pattern.

Overtime and extra hires (L.2 / L.3), both per role — see _role:
  Bought beyond TOTAL labor_capacity, not beyond the hourly-only part — measuring against
  hourly-only was the bug that removed C14, because it let flexibility buy back capacity the
  farm already had. Bought hours carry their FULL wage: the committed bill pays for the crew's
  stated hours, and these are extra (W12). An extra head INHERITS its row — wage, hours,
  field %, window, overtime allowance — so no hired-wage statistic is inferred any more (the
  three that stood here were each a statistic over internal payroll posing as a market price;
  W15/W17 retired with them).
"""

from __future__ import annotations

import numpy as np

# The two accepted seasonal type spellings. PT is a legacy alias — the two take identical
# code paths (wage, capacity, committed-wage treatment all the same); the app's adapter maps
# its own 'seasonal' type to 'FT'. One definition, imported by validate.py, so the accepted
# set cannot drift between the two files.
SEASONAL_TYPES = frozenset({"FT", "PT"})


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def compute_labor_arrays(
    year_round_employees: list[dict],
    seasonal_employees: list[dict],
    n_weeks: int = 52,
    overtime_rate_multiplier: float = 1.0,
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

    overtime_rate_multiplier : float
        Overtime pay as a multiple of each role's own wage (1.0 = straight time, FLSA).

    Note: `min_guaranteed_hours` is ACCEPTED AND IGNORED (W11/W14).
It can never bind: committed
        wages already pay count x hours_per_week, which is >= count x min(min_guaranteed, hours)
        for every input. Wiring it back would put a floor underneath a floor and double-charge.

    n_weeks : int
        Planning horizon (52).

    Returns
    -------
    dict with keys:
        "labor_capacity"            np.ndarray shape (n_weeks,) — total hrs/week (0-indexed)
        "committed_weekly_wages"    np.ndarray shape (n_weeks,) — $/week owed to ALL listed staff
        "labor_by_role"             list[dict] — per-role weekly rows, overtime cap/rate and
                                    extra-head terms (_role)
        "piece_rate_workers"        list[dict] — seasonal workers with piece_rate_per_lb set
    """
    labor_capacity        = np.zeros(n_weeks, dtype=float)

    # Wages the farm has COMMITTED to, per week, across every listed worker (W12). A worker on
    # the payroll is paid for their stated hours over their stated weeks whether or not the crops
    # need them — the same basis the salaried line has always used, now applied to hourly and
    # seasonal staff too. Charged on FULL hours: `field_time_pct` limits how much of a worker's
    # time is available to crops, not how much of their wage the farm owes.
    committed_weekly_wages = np.zeros(n_weeks, dtype=float)
    # THE UNPAID-ROLES RULE: a role at $0/hr — piece-rate picker, unpaid family, a blank wage
    # box — provides CAPACITY but can never be BOUGHT: no overtime, no extra heads (see _role).
    # At $0 either would be free labour (W12b).
    piece_rate_workers    = []
    labor_by_role         = []          # F3: one named row per roster line, see _role

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

        if emp_type not in ("salary", "hourly"):
            raise ValueError(
                f"Year-round employee '{emp.get('position', '?')}' has unknown type "
                f"'{emp_type}'. Expected 'salary' or 'hourly'."
            )
        # Annual wage → weekly cost (salary); count × hours × loaded rate (hourly).
        weekly_cost = (count * wage * (1 + bene) / 52 if emp_type == "salary"
                       else count * hrs * (wage * (1 + bene)))
        labor_by_role.append(_role(emp, emp_type == "hourly", count, hrs, field, weekly_cost,
                                   range(n_weeks), n_weeks, overtime_rate_multiplier))

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

        if emp_type not in SEASONAL_TYPES:
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

        labor_by_role.append(_role(emp, True, count, hrs, field, count * hrs * (wage * (1 + bene)),
                                   range(start_w - 1, end_w), n_weeks, overtime_rate_multiplier))

    # The farm totals are the SUMS of the per-role rows (F3) — one derivation, not two.
    for role in labor_by_role:
        labor_capacity         += role["task_hours"]
        committed_weekly_wages += role["cost"]

    return {
        "committed_weekly_wages": committed_weekly_wages,
        "labor_capacity":         labor_capacity,
        "piece_rate_workers":     piece_rate_workers,
        "labor_by_role":          labor_by_role,
    }


def _role(emp: dict, is_hourly: bool, count: float, hrs: float, field: float,
          weekly_cost: float, weeks: range, n_weeks: int,
          overtime_rate_multiplier: float = 1.0) -> dict:
    """One roster line as named weekly arrays (F3), all n_weeks long and 0-indexed.

    paid_hours is what the wage bill pays for; task_hours is the share available to crop work
    (field %). The farm totals in compute_labor_arrays are the sums of these rows.

    Overtime (F2/F4, L.2), per role:
      ot_cap[w] = (max_week_pct/100 − 1) × count × hours × field   — the cap is DERIVED from the
                  roster; a flat farm-wide cap once let 15 of 52 weeks buy more overtime than the
                  whole crew's regular hours. max_week_pct is the TOTAL week incl. overtime
                  (125 = 40 regular + 10 OT), never an amount on top.
      ot_rate   = wage × (multiplier × (1 + fica) + straight-time load) — the premium carries
                  FICA only (I2b). straight-time load = benefits_pct − fica_pct.
    Salaried roles get none (cannot be paid overtime), and nor does an UNPAID role: an hour
    nobody pays for cannot be bought, and at $0 it would be free labour (W12b).

    Extra heads (F1, L.3) — one more person on THIS row, inheriting everything:
      head_task[w] = hours × field in the window (× new-hire productivity, applied by the solver)
      head_cost[w] = the row's weekly cost ÷ count — full pay every window week (committed, W12)
      hire_more / max_more — whether the What-If may add heads here, and at most how many.
    """
    on = np.zeros(n_weeks, dtype=float)
    on[list(weeks)] = 1.0
    wage = float(emp.get("wage", 0.0))
    ot_ok = is_hourly and wage > 0
    allowance = max(0.0, float(emp.get("max_week_pct", 125.0 if is_hourly else 100.0)) / 100.0 - 1.0)
    fica = float(emp.get("fica_pct", 0.0))
    straight = float(emp.get("benefits_pct", 0.0)) - fica
    return {
        "ot_cap":     on * (allowance * count * hrs * field) if ot_ok else np.zeros(n_weeks),
        "ot_rate":    wage * (overtime_rate_multiplier * (1.0 + fica) + straight) if ot_ok else 0.0,
        "allowance":  allowance if ot_ok else 0.0,
        "head_task":  on * (hrs * field),
        "head_cost":  on * (weekly_cost / count) if count > 0 else np.zeros(n_weeks),
        "start":      weeks.start,
        "paid":       wage > 0,
        "hire_more":  bool(emp.get("hire_more", False)),
        "max_more":   max(0, int(emp.get("max_more", 0) or 0)),
        "position":   emp.get("position", ""),
        "row":        emp.get("row"),   # the caller's roster index, so a result can point back
        "is_hourly":  bool(is_hourly),
        "heads":      on * count,
        "paid_hours": on * (count * hrs),
        "task_hours": on * (count * hrs * field),
        "cost":       on * weekly_cost,
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
