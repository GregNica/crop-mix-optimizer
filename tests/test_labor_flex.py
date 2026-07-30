"""
Phase 5 — labor flexibility (overtime + hiring) as decision variables.

Validates:
  * flex OFF reproduces baseline behavior (no hired/overtime hours, no cost),
  * flex ON never lowers profit and reports consistent cost accounting,
  * hired labor (cheaper) is used before overtime,
  * per-week caps on hiring and overtime are respected,
  * the payroll load flows through to all labor (incl. bought labor).
"""

import copy
import pytest

from farm_v2.solver import solve_farm_v2


def _labor_bound(two_crop_params, crew=2):
    """Lots of land + a scarce seasonal crew → labor is the binding constraint,
    so buying labor genuinely expands the plan (beyond TOTAL staff capacity)."""
    p = copy.deepcopy(two_crop_params)
    p["total_land"] = 200.0
    p["harvest_storage_cap"] = 100_000.0   # lift storage so labor is the real limiter
    # ...and water, for the same reason. The fixture's well is sized for its own 50 acres; at
    # 200 acres with honest FAO-56 water rates (2026-07-29) water binds first and these tests
    # stop being about labor at all. Isolate the constraint under test.
    p["well_weekly_cap_L"] = 1e12
    p["seasonal_employees"] = [{
        "position": "Field Hand", "count": crew, "type": "FT",
        "start_week": 8, "end_week": 46, "wage": 18.0, "hours_per_week": 40,
    }]
    return p


def test_flex_off_is_baseline(minimal_params):
    base = solve_farm_v2(**minimal_params)
    assert base["status"] == "optimal"
    assert base["labor_flex_enabled"] is False
    assert base["total_hired_hours"] == 0.0
    assert base["total_overtime_hours"] == 0.0
    assert base["hire_cost"] == 0.0
    assert base["overtime_cost"] == 0.0


def test_flex_never_lowers_profit_and_accounts_consistently(two_crop_params):
    p = _labor_bound(two_crop_params)
    base = solve_farm_v2(**p)
    flex = solve_farm_v2(
        **p,
        hire_enabled=True, max_hire_hrs_per_week=2000.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=1000.0,
    )
    assert flex["status"] == "optimal"
    assert flex["operating_profit"] >= base["operating_profit"] - 1.0
    # P&L identity holds with the new cost lines included.
    recomputed = flex["revenue"] - (
        flex["fixed_cost"] + flex["variable_cost"] + flex["city_water_cost"]
        + flex["overtime_cost"] + flex["hire_cost"]
    )
    assert recomputed == pytest.approx(flex["operating_profit"], abs=1.0)


def test_hired_labor_used_before_overtime(two_crop_params):
    # Labor genuinely binds; generous hire cap @ 0 markup → lean on hiring, not overtime.
    p = _labor_bound(two_crop_params)
    flex = solve_farm_v2(
        **p,
        hire_enabled=True, max_hire_hrs_per_week=5000.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=5000.0,
    )
    assert flex["status"] == "optimal"
    assert flex["total_hired_hours"] > 0.0
    assert flex["total_overtime_hours"] == pytest.approx(0.0, abs=1e-6)


def test_hire_cap_forces_overtime_overflow(two_crop_params):
    # Tight hire cap on a labor-bound farm → the overflow must spill into overtime.
    p = _labor_bound(two_crop_params)
    flex = solve_farm_v2(
        **p,
        hire_enabled=True, max_hire_hrs_per_week=20.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=5000.0,
    )
    assert flex["status"] == "optimal"
    assert max(flex["hired_hours_weekly"]) <= 20.0 + 1e-6
    assert flex["total_overtime_hours"] > 0.0


# ── Payroll load (employer burden on wages) ───────────────────────────────────

def _with_payroll_load(params, load):
    """Mirror run_from_js: stamp benefits_pct (the payroll load) onto every employee."""
    p = copy.deepcopy(params)
    for e in p["year_round_employees"] + p["seasonal_employees"]:
        e["benefits_pct"] = load
    return p


def test_other_debt_service_is_a_fixed_cost(minimal_params):
    base = solve_farm_v2(**minimal_params)
    with_debt = solve_farm_v2(**minimal_params, other_debt_service_per_week=1000.0)
    assert base["status"] == "optimal" and with_debt["status"] == "optimal"
    # A flat fixed cost charged over the FULL year, not over operating_weeks — debt service
    # does not pause off-season (see solver.py Step 4). Nothing else shifts the plan.
    wk = 52
    assert with_debt["fixed_cost"] == pytest.approx(base["fixed_cost"] + 1000.0 * wk, abs=1.0)
    assert with_debt["operating_profit"] == pytest.approx(base["operating_profit"] - 1000.0 * wk, abs=1.0)


def test_payroll_load_reduces_profit(minimal_params):
    no_load = solve_farm_v2(**_with_payroll_load(minimal_params, 0.0))
    loaded  = solve_farm_v2(**_with_payroll_load(minimal_params, 0.25))
    assert no_load["status"] == "optimal" and loaded["status"] == "optimal"
    assert loaded["operating_profit"] <= no_load["operating_profit"] + 1.0


def test_payroll_load_flows_into_bought_labor(two_crop_params):
    p = _labor_bound(two_crop_params)
    flex_kwargs = dict(
        hire_enabled=True, max_hire_hrs_per_week=2000.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=2000.0,
    )
    no_load = solve_farm_v2(**_with_payroll_load(p, 0.0),  **flex_kwargs)
    loaded  = solve_farm_v2(**_with_payroll_load(p, 0.30), **flex_kwargs)
    assert no_load["status"] == "optimal" and loaded["status"] == "optimal"
    assert loaded["operating_profit"] <= no_load["operating_profit"] + 1.0


# ── Field-time cap + overhead internalization ─────────────────────────────────

def test_field_time_cap_reduces_capacity(two_crop_params):
    # Halving field-time on the crew halves their effective field capacity, so a
    # labor-bound plan can't do as much → operating profit is lower (or equal).
    full = _labor_bound(two_crop_params, crew=6)
    half = copy.deepcopy(full)
    for e in half["seasonal_employees"]:
        e["field_time_pct"] = 50.0
    rf = solve_farm_v2(**full)
    rh = solve_farm_v2(**half)
    assert rf["status"] == "optimal" and rh["status"] == "optimal"
    assert rh["operating_profit"] <= rf["operating_profit"] + 1.0


def test_hiring_more_crew_than_the_plan_needs_costs_money(two_crop_params):
    """W12 INVERTED this test, and the inversion is the point.

    It used to assert that adding crew can never lower the maximized quantity, because more
    labour enlarged the feasible set and cost nothing unless the crops used it. Under W12 a
    listed worker is paid for their stated hours whether the crops need them or not, so adding
    crew buys capacity AND a wage bill. Hiring is now a real trade-off, and over-hiring is
    strictly worse — which is the behaviour a grower needs the tool to show.

    The bound is what makes this more than a sign check: the loss cannot exceed the extra wages,
    because the extra crew is free to sit idle and change nothing else. If it ever did, the
    committed bill would be charging more than the farm agreed to pay.
    """
    def cfg(crew):
        p = _labor_bound(two_crop_params, crew=crew)
        p.update(overhead_pct_of_revenue=0.16, sell_through_fraction=0.85,
                 opening_cash=1e12, credit_line=1e12)
        return p
    r_few  = solve_farm_v2(**cfg(4))
    r_many = solve_farm_v2(**cfg(16))
    assert r_few["status"] == "optimal" and r_many["status"] == "optimal"
    after_oh = lambda r: r["operating_profit"] - r["overhead_cost"]
    extra_wages = r_many["fixed_cost_split"]["wages"] - r_few["fixed_cost_split"]["wages"]
    assert extra_wages > 0, "the fixture did not actually add any committed crew"
    drop = after_oh(r_few) - after_oh(r_many)
    assert drop > 0, (
        f"adding {12} crew changed the maximized quantity by {-drop:+,.0f} — under W12 idle crew "
        f"is paid for, so over-hiring must cost something"
    )
    assert drop <= extra_wages + 1.0, (
        f"over-hiring cost ${drop:,.0f} against ${extra_wages:,.0f} of extra wages. The extra "
        f"crew can always sit idle, so the loss cannot exceed what they are paid."
    )
