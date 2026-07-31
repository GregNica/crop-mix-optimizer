"""C13 cash-floor guards — the suite's demonstrated blind spot, closed.

Mutation testing (2026-07-31 adversarial review) proved three C13 mutations survived all 363
tests: flattening the seasonal payroll rhs to `W * mean` (the exact defect that shipped once —
committed_weekly_wages built seasonal and collapsed flat), and zeroing the overtime / hire
coefficients (bought labor costing NOTHING in the solvency constraint). Root cause: every test
that enabled flex or committed wages ran with a $5M-$1e12 cash buffer, so C13's labor columns
were dead code under test.

These fixtures make the floor BIND — opening+credit is set $500 below the unconstrained plan's
cash need, so the solver must shape the plan against the floor. Two assertions per solve, and
both are load-bearing:

  * no-breach:  min(cum_cash) >= -credit_line - tol. Kills coefficient-zeroing (freeing
    bought-labor money in C13 lets the plan spend cash it does not have; the REPORTED curve
    still charges it, so it dives through the floor).
  * binding:    min(cum_cash) <= -credit_line + BIND_TOL. Kills rhs flattening (a flattened
    floor is ~$15k TIGHTER at this fixture's binding week 14, so the reported curve is pushed
    OFF the floor) — and guards this test's own relevance: a fixture whose floor stops binding
    reverts to exactly the dead-code-under-test hole this file exists to close.

Every mutation listed above was re-applied against these tests and confirmed CAUGHT before
this file was believed (the five-inert-guards lesson: run the mutation, not the reasoning).
"""
import copy

import numpy as np
import pytest

from farm_v2.solver import solve_farm_v2

BIND_TOL = 2_000.0   # slack is $500; flatten shifts the binding week by ~$15k (crew of 6)


def _cash_bound(two_crop_params, crew, opening_cash, credit_line, **flex):
    """Labor-heavy seasonal farm (weeks 8-46) with the cash floor set to bind (see module doc)."""
    p = copy.deepcopy(two_crop_params)
    p["total_land"] = 200.0
    p["harvest_storage_cap"] = 100_000.0
    p["well_weekly_cap_L"] = 1e12
    p["seasonal_employees"] = [{
        "position": "Field Hand", "count": crew, "type": "FT",
        "start_week": 8, "end_week": 46, "wage": 18.0, "hours_per_week": 40,
    }]
    p.update(opening_cash=opening_cash, credit_line=credit_line, **flex)
    return p


def _cum_net(r):
    """Reported cumulative cash relative to the floor's basis (includes opening_cash)."""
    return np.array(r["weekly_cash_flow"][1:], dtype=float)


def test_seasonal_payroll_shape_reaches_the_cash_floor(two_crop_params):
    """The C13 rhs must carry the SEASONAL cumulative wage bill, not a flat spread.

    Unconstrained, this farm's cash need is $762,896 (min at week 14 — crew on since week 8,
    revenue still ramping). opening+credit = $762,396 sits $500 below that, so the true floor
    binds at week 14. Flattening the wage rhs makes week 14's floor ~$15,120 TIGHTER (7 weeks
    of real crew < 14 weeks of annual mean), so the mutated solver holds the plan ~$15k off
    the true floor and the binding assertion fails; if it instead exploited the LOOSENED late
    weeks (wk 42: flat is $5k+ under true), the no-breach assertion fails. Both directions of
    the mutation are pinned by one solve.
    """
    p = _cash_bound(two_crop_params, crew=6, opening_cash=600_000.0, credit_line=162_396.0)
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", f"fixture must remain solvable: {r['status']} {r.get('errors')}"
    cum = _cum_net(r)
    floor = -p["credit_line"]
    assert float(cum.min()) >= floor - 1.0, (
        f"the plan breaches its own credit line by ${floor - cum.min():,.0f}: the cash floor "
        f"the solver enforced is looser than the cash curve it reports"
    )
    assert float(cum.min()) <= floor + BIND_TOL, (
        f"the cash floor no longer binds (min sits ${cum.min() - floor:,.0f} above it). Either "
        f"the C13 rhs lost the seasonal payroll shape, or this fixture drifted and C13 is "
        f"dead code under test again — re-derive opening+credit from the unconstrained need."
    )


def test_bought_labor_is_real_money_in_the_cash_floor(two_crop_params):
    """Overtime and hired hours must consume cash in C13, not only in the reported curve.

    Two fixture traps, each of which made an earlier version of this test INERT — both found
    by running the mutations, not by reasoning:

    * NO seasonal crew, deliberately: with a crew present, bought hours started at week 15
      while the floor bound at week 14, so zeroing a bought-labor coefficient freed money only
      in rows with slack and BOTH mutations survived. Without the crew the farm leans on flex
      from week 9 — inside the binding prefix.
    * The budget must make cash cost PROFIT, not just bind: at need-minus-$500 the MILP found
      an equal-profit plan $16.7k less cash-hungry (the floor only broke ties) and the
      mutations shuffled tie-breaking invisibly. The frontier here is steep only below
      ~$723k: at a $715,000 budget, profit is $133,691 vs $233,078 unconstrained (~$20 of
      profit per $1 of cash), the floor binds to the dollar, and every dollar a mutation
      frees from C13 gets spent — pushing the reported curve through the floor.

    The bought-hours asserts keep the fixture honest: no bought hours would mean the mutated
    coefficients multiply zeros and this test pins nothing.
    """
    p = _cash_bound(
        two_crop_params, crew=0, opening_cash=600_000.0, credit_line=115_000.0,
        hire_enabled=True, max_hire_hrs_per_week=20.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=5000.0,
    )
    p["seasonal_employees"] = []
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", f"fixture must remain solvable: {r['status']} {r.get('errors')}"
    assert r["total_hired_hours"] > 100.0, "fixture stopped hiring — the hire coefficient is untested"
    assert r["total_overtime_hours"] > 100.0, "fixture stopped buying overtime — the OT coefficient is untested"
    cum = _cum_net(r)
    floor = -p["credit_line"]
    assert float(cum.min()) >= floor - 1.0, (
        f"the plan breaches its own credit line by ${floor - cum.min():,.0f} — bought labor "
        f"is being planned with cash the farm does not have (its cost fell out of C13)"
    )
    assert float(cum.min()) <= floor + BIND_TOL, (
        f"the cash floor no longer binds (min sits ${cum.min() - floor:,.0f} above it) — "
        f"this fixture has drifted and C13's bought-labor columns are dead code under test"
    )
