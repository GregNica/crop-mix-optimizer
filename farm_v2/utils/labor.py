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
  overtime_hour_wage[w]      $/hour base for your own crew staying late
  hire_hour_wage[w]          $/hour base for a NEW hire (W15) — regular hours are already
                              paid by the committed wage bill, so both are charged in FULL
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
        "committed_weekly_wages"    np.ndarray shape (n_weeks,) — $/week owed to ALL listed staff
        "overtime_hour_wage"        np.ndarray shape (n_weeks,) — $/hr base for YOUR crew
                                    staying late; never zero while anyone is paid
        "hire_hour_wage"            np.ndarray shape (n_weeks,) — $/hr base for a NEW hire,
                                    from `hired_wage_per_hr`, else hours-weighted over paid roles
        "piece_rate_workers"        list[dict] — seasonal workers with piece_rate_per_lb set
    """
    labor_capacity        = np.zeros(n_weeks, dtype=float)
    hourly_weighted_wages = np.zeros(n_weeks, dtype=float)   # sum(count × hrs × rate)
    hourly_weighted_hours = np.zeros(n_weeks, dtype=float)   # sum(count × hrs)

    # Wages the farm has COMMITTED to, per week, across every listed worker (W12). A worker on
    # the payroll is paid for their stated hours over their stated weeks whether or not the crops
    # need them — the same basis the salaried line has always used, now applied to hourly and
    # seasonal staff too. Charged on FULL hours: `field_time_pct` limits how much of a worker's
    # time is available to crops, not how much of their wage the farm owes.
    committed_weekly_wages = np.zeros(n_weeks, dtype=float)
    # THE UNPAID-ROLES RULE, stated once (the accumulations below just point here): a role at
    # $0/hr — piece-rate picker, unpaid family, a blank wage box — provides CAPACITY but never
    # sets a PRICE. Unpaid hours are excluded from the blend, from the paid-hours denominator
    # below, and (via the w > 0 filter) from the hire inference; left in, they drag every
    # bought-labour price below any real wage (measured: a $20 hand + two unpaid family priced
    # overtime at $10.00/hr; an owner at $0 beside an $18 crew averaged $4.55/hr), which is the
    # UNSAFE direction — the optimizer buys help the grower cannot get.
    # Annual hours of roles the farm actually PAYS, not field-adjusted; feeds only
    # `average_paid_wage`.
    total_paid_hours = 0.0
    hourly_wages          = []          # (effective $/hr, weekly hours) per hourly role (W15)
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
            committed_weekly_wages += weekly_cost
            if wage > 0:
                total_paid_hours += count * hrs * n_weeks

        elif emp_type == "hourly":
            effective_rate = wage * (1 + bene)
            hourly_wages.append((effective_rate, count * hrs))
            committed_weekly_wages += count * hrs * effective_rate
            # Unpaid roles: capacity, never a price — see the rule at total_paid_hours.
            if wage > 0:
                total_paid_hours += count * hrs * n_weeks
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

        # Unpaid roles: capacity, never a price — see the rule at total_paid_hours.
        if wage > 0:
            total_paid_hours += count * hrs * (end_w - start_w + 1)

        # Week indices are 0-based internally (week w → index w-1)
        for w_idx in range(start_w - 1, end_w):
            committed_weekly_wages[w_idx] += count * hrs * effective_rate
            labor_capacity[w_idx]        += total_hrs_per_week
            if wage > 0:
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

    # THE PRICE OF AN HOUR BOUGHT BEYOND THE COMMITTED CREW — published as one array, so no
    # caller has to reason about wage semantics to get it right.
    #
    # `hourly_labor_rate` is the blend of the EXISTING hourly staff, so it is 0 in any week they
    # are not on. Once W12 stopped charging base wages through the crop coefficients, a zero blend
    # meant a bought hour was FREE — measured at 80 hired hours for $0.00 on a farm whose only
    # hourly crew is seasonal. That trap belongs here, next to the code that CREATES the zero,
    # rather than in the solver: a future caller reading `hourly_labor_rate` directly would
    # re-create the defect with nothing to warn them.
    #
    # The fallback is the farm's own average paid wage — what it actually pays for an hour of
    # work, inferred from the crew it described. ⚠️ It is an AVERAGE standing in for a MARGINAL
    # price, and it is shared by overtime (existing crew, where the blend is genuinely right) and
    # hire (a new person from the local market, where it is only a proxy). On a farm whose only
    # worker is a $95k manager it prices a hired field hand at $40.60/hr. The error direction is
    # SAFE — it over-prices bought labour, and the defect it replaced was free labour — but the
    # honest fix is an explicit "what does a hand cost around here" input. See backlog W15.
    average_paid_wage = (float(committed_weekly_wages.sum()) / total_paid_hours
                         if total_paid_hours > 0 else 0.0)

    # TWO prices, because overtime and hire are different transactions (W15).
    #
    #   overtime — your OWN crew, staying late. The blend of the hourly staff actually present
    #              that week is exactly right.
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

    # Never zero while anyone is paid: a zero blend means "no hourly crew this week", not "labour
    # is free". Getting that wrong is what let 2,080 hired hours cost $0.00.
    #   overtime — the weekly blend of PAID roles, or the average paid wage where none are on
    #   hire     — validated (> 0) if explicit, else a weighted mean of POSITIVE rates
    # ⚠️ "While anyone is paid" is load-bearing: a crew with NO paid role at all (every wage $0 —
    # blank boxes, unpaid family) makes average_paid_wage 0 and BOTH prices 0. No statistic over
    # an unpaid crew can price a bought hour, so no floor here can fix that case honestly — the
    # solver refuses to sell flex hours at a non-positive price instead (its Step-2 gate), which
    # is the point of consumption and holds for every inference past and future.
    # A separate "floor" block used to sit here re-applying np.where to its own output. It was
    # inert on every reachable path — deleting it failed no behavioural test — and where it could
    # have fired (this all-unpaid case) it floored with zero and its promise of "never free" was
    # false anyway.
    overtime_hour_wage = np.where(hourly_labor_rate > 0, hourly_labor_rate, average_paid_wage)
    hire_hour_wage     = np.full(n_weeks, float(hire_base), dtype=float)


    return {
        "committed_weekly_wages": committed_weekly_wages,
        "overtime_hour_wage":     overtime_hour_wage,
        "hire_hour_wage":         hire_hour_wage,
        "labor_capacity":         labor_capacity,
        "hourly_labor_rate":      hourly_labor_rate,
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
