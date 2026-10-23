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
  hire_hour_wage[w]          $/hour for a NEW hire (W15), LOAD-INCLUSIVE: an explicit wage
                              has hired_wage_load_pct applied here; an inferred one carries
                              each role's benefits_pct. Only the hire markup is applied
                              downstream. Regular hours are already paid by the committed
                              wage bill, so bought hours are charged in FULL
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
    hired_wage_per_hr: float | None = None,
    hired_wage_load_pct: float = 0.0,
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

    hired_wage_per_hr : float | None
        BASE $/hr for a hired hand on the local market. None (blank) = infer an
        hours-weighted mean over the farm's PAID hourly roles. 0 or negative is refused.

    hired_wage_load_pct : float
        Employer payroll load applied to an EXPLICIT hired wage, here, next to where every
        other wage gets its load via benefits_pct. The inferred branch needs none — each
        role's wage already carries its own load.
        ⚠️ `min_guaranteed_hours` is ACCEPTED AND IGNORED (W11/W14). It can never bind: committed
        wages already pay count x hours_per_week, which is >= count x min(min_guaranteed, hours)
        for every input. Wiring it back would put a floor underneath a floor and double-charge.

    n_weeks : int
        Planning horizon (52).

    Returns
    -------
    dict with keys:
        "labor_capacity"            np.ndarray shape (n_weeks,) — total hrs/week (0-indexed)
        "committed_weekly_wages"    np.ndarray shape (n_weeks,) — $/week owed to ALL listed staff
        "labor_by_role"             list[dict] — per-role weekly rows + overtime cap/rate (_role)
        "hire_hour_wage"            np.ndarray shape (n_weeks,) — LOAD-INCLUSIVE $/hr for a
                                    NEW hire: `hired_wage_per_hr` × (1+hired_wage_load_pct),
                                    else hours-weighted over paid roles (already loaded).
                                    Only the hire markup is applied downstream — treating
                                    this as a "base" rate double-applies the payroll load
        "piece_rate_workers"        list[dict] — seasonal workers with piece_rate_per_lb set
    """
    labor_capacity        = np.zeros(n_weeks, dtype=float)

    # Wages the farm has COMMITTED to, per week, across every listed worker (W12). A worker on
    # the payroll is paid for their stated hours over their stated weeks whether or not the crops
    # need them — the same basis the salaried line has always used, now applied to hourly and
    # seasonal staff too. Charged on FULL hours: `field_time_pct` limits how much of a worker's
    # time is available to crops, not how much of their wage the farm owes.
    committed_weekly_wages = np.zeros(n_weeks, dtype=float)
    # THE UNPAID-ROLES RULE, stated once (the accumulations below just point here): a role at
    # $0/hr — piece-rate picker, unpaid family, a blank wage box — provides CAPACITY but never
    # sets a PRICE. Unpaid hours are excluded from the paid-hours denominator below, from the
    # hire inference (the w > 0 filter), and from overtime (see _role); left in, they drag every
    # bought-labour price below any real wage (measured: a $20 hand + two unpaid family priced
    # overtime at $10.00/hr; an owner at $0 beside an $18 crew averaged $4.55/hr), which is the
    # UNSAFE direction — the optimizer buys help the grower cannot get.
    # Annual hours of roles the farm actually PAYS, not field-adjusted; feeds only
    # `average_paid_wage`.
    total_paid_hours = 0.0
    hourly_wages          = []          # (effective $/hr, weekly hours) per hourly role (W15)
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

        total_hrs_per_week = count * hrs * field
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

        if emp_type == "salary":
            if wage > 0:
                total_paid_hours += count * hrs * n_weeks

        elif emp_type == "hourly":
            effective_rate = wage * (1 + bene)
            hourly_wages.append((effective_rate, count * hrs))
            # Unpaid roles: capacity, never a price — see the rule at total_paid_hours.
            if wage > 0:
                total_paid_hours += count * hrs * n_weeks

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

        effective_rate = wage * (1 + bene)
        hourly_wages.append((effective_rate, count * hrs * (end_w - start_w + 1) / n_weeks))
        total_hrs_per_week = count * hrs * field
        labor_by_role.append(_role(emp, True, count, hrs, field, count * hrs * effective_rate,
                                   range(start_w - 1, end_w), n_weeks, overtime_rate_multiplier))

        # Unpaid roles: capacity, never a price — see the rule at total_paid_hours.
        if wage > 0:
            total_paid_hours += count * hrs * (end_w - start_w + 1)


    # The farm totals are the SUMS of the per-role rows (F3) — one derivation, not two.
    for role in labor_by_role:
        labor_capacity         += role["task_hours"]
        committed_weekly_wages += role["cost"]

    # THE PRICE OF A HIRED HOUR (overtime is priced per role, in _role — L.2).
    #
    # The fallback is the farm's own average paid wage — what it actually pays for an hour of
    # work, inferred from the crew it described. ⚠️ It is an AVERAGE standing in for a MARGINAL
    # price for a new person from the local market, where it is only a proxy. On a farm whose only
    # worker is a $95k manager it prices a hired field hand at $40.60/hr. The error direction is
    # SAFE — it over-prices bought labour, and the defect it replaced was free labour. The
    # explicit "what does a hand cost around here" input exists now (`hired_wage_per_hr`,
    # W15 closed); this fallback covers only the blank-box case, and which statistic should
    # stand here is the OPEN decision. See backlog W17.
    average_paid_wage = (float(committed_weekly_wages.sum()) / total_paid_hours
                         if total_paid_hours > 0 else 0.0)

    # Hire is a different transaction from overtime (W15):
    #   hire     — a NEW person from the local labour market. The existing crew's blend is only a
    #              proxy for that, and a poor one when the crew is unrepresentative: sharing one
    #              price meant a farm whose only worker is a $95k manager valued a hired field
    #              hand at $40.60/hr, and the demo crew priced one at $22.08 against a real
    #              harvest wage of $19 — so the optimizer refused hires it should have taken.
    #
    # `hired_wage_per_hr` is the honest answer and the caller supplies it. Without it the model
    # infers one from the hourly roles the farm lists — see the `else` branch below for what that
    # statistic is, why it has been wrong twice, and why no statistic over internal payroll is
    # really a market price.
    # An explicit wage must be a real wage. 0 is not "infer" — it is free labour, the defect
    # W12b closed — and a negative rate is a coefficient the optimizer drives to the hiring cap
    # for phantom profit. Blank reaches here as None, from the adapter; anything else is refused
    # HERE rather than trusted to a caller, because the caller is exactly who got it wrong before.
    if hired_wage_per_hr is not None:
        try:
            hire_base = float(hired_wage_per_hr)
        except (TypeError, ValueError):
            raise ValueError(
                f"hired_wage_per_hr must be a number or None (blank), got "
                f"{hired_wage_per_hr!r}."
            )
        if not hire_base > 0:
            raise ValueError(
                f"hired_wage_per_hr must be greater than 0, got {hire_base}. Leave it blank to "
                f"infer a rate from the crew; 0 would price hired labour at nothing."
            )
        # The typed value is a BASE wage — the same basis as every employee wage box — so it
        # carries the employer payroll load here, where every other wage gets its load (via
        # benefits_pct above). This used to live in the app's adapter, which made the solver
        # parameter secretly mean "all-in wage": a direct or server caller passing the grower's
        # typed base under-priced every hired hour by the load (25% at shipped defaults) — the
        # under-priced-bought-labour class, one layer down. The inferred branch below needs no
        # load: each role's wage already carries its own.
        hire_base *= 1.0 + max(0.0, hired_wage_load_pct)
    else:
        # Inferred from the roles the farm PAYS BY THE HOUR, weighted by their hours.
        #
        # ⚠️ THREE answers have stood here, and the first two were wrong in opposite
        # directions. The average over ALL paid hours dragged the price up toward salaried staff
        # who would never do the work ($40.60/hr for a field hand on a manager-only farm). An
        # unweighted `min` then dragged it down to the least representative role — a single
        # 2 h/wk helper at $12 priced all 20,800 potential hired hours — and that direction is the
        # UNSAFE one, because under-pricing makes the optimizer buy help the grower cannot get.
        #
        # This one is hours-weighted over PAID hourly roles: robust to both tails, with salaried
        # staff absent from the list entirely. Roles at $0/hr are EXCLUDED — piece-rate pickers,
        # unpaid family and a blank wage box all land there, and one of them set the price to zero
        # for every week, which was W12b reopened.
        #
        # ⚠️ It is still a statistic over INTERNAL PAYROLL standing in for a MARKET price, and no
        # reduction of internal payroll is a market price. A crew of two mechanics and one picker
        # prices its hires as mechanics. The honest answer is the explicit input above; this is
        # what the model can infer when the grower leaves it blank, not what a hire costs. See
        # backlog W17.
        # The weight is ANNUAL paid hours: a year-round role works all 52 weeks (factor 1) and a
        # seasonal role its window, so the 1/n_weeks cancels in the mean.
        paid = [(w, h) for w, h in hourly_wages if w > 0 and h > 0]
        if paid:
            hire_base = sum(w * h for w, h in paid) / sum(h for _w, h in paid)
        else:
            hire_base = average_paid_wage

    # Never zero while anyone is paid: validated (> 0) if explicit, else a weighted mean of
    # POSITIVE rates. A crew with NO paid role makes it 0, and the solver refuses to sell hired
    # hours at a non-positive price (its Step-2 gate).
    hire_hour_wage     = np.full(n_weeks, float(hire_base), dtype=float)


    return {
        "committed_weekly_wages": committed_weekly_wages,
        "hire_hour_wage":         hire_hour_wage,
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
        "position":   emp.get("position", ""),
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
