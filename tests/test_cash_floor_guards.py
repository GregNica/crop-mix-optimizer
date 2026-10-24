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

    The budget must make cash cost PROFIT, not just bind — the same trap the flex test below
    documents. At need-minus-$500 ($762,396) this fixture sat on an equal-profit plateau
    (measured: profit $249,982 from $760k up), so the "binding" min was HiGHS tie-breaking
    and a solver upgrade could park it $11k off the floor spuriously. Measured frontier:
    infeasible ≤ ~$730k; $740,000 → profit $36,182 with the floor binding TO THE DOLLAR at
    week 18; $750,000 → $249,982. So $740k prices cash at ~$21 of profit per $1.

    Flattening the wage rhs makes week 18's floor ~$10,800 TIGHTER (11 weeks of real crew
    < 18 weeks of annual mean) — only ~$10k above the infeasibility edge, so the mutated
    solve goes infeasible (status assert) or re-plans ~$10.8k off the true floor (binding
    assert). If it instead exploited the LOOSENED late weeks, the no-breach assert fails.
    All directions covered by one solve.
    """
    p = _cash_bound(two_crop_params, crew=6, opening_cash=600_000.0, credit_line=140_000.0)
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

    ⚠️ W17 coupling: with no seasonal crew and a blank hired wage, this fixture's flex prices
    are inferred from the two_crop year-round roster (the paid-roles fallback). If W17
    replaces blank-box inference with something that refuses salary-heavy crews, this test's
    status=="optimal" precondition fails LOUDLY — fix by giving the fixture an explicit
    hired_wage_per_hr and re-deriving the budget from the then-current frontier (the probe
    recipe is in this docstring's history).
    """
    p = _cash_bound(
        two_crop_params, crew=0, opening_cash=600_000.0, credit_line=140_000.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5,
    )
    p["seasonal_employees"] = []
    # L.2: overtime is per role, so the fixture needs an hourly role that may work it (up to
    # 40 OT h/wk each). Re-derived frontier: cash binds below ~$149k credit; at
    # $140k profit $300,894 vs $302,588 unconstrained — cash costs profit, so the floor binds.
    p["year_round_employees"] = p["year_round_employees"] + [
        {"position": "Hand", "count": 2, "type": "hourly", "wage": 18.0, "hours_per_week": 40,
         "max_ot_hrs": 40}]
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", f"fixture must remain solvable: {r['status']} {r.get('errors')}"
    # Extra hires' C13 column is guarded in test_extra_hires.py (L.3 retired the spot market).
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
