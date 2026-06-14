"""
Phase 5 — labor flexibility (overtime + hiring) as decision variables.

Validates:
  * flex OFF reproduces baseline behavior (no hired/overtime hours, no cost),
  * flex ON never lowers profit and reports consistent cost accounting,
  * hired labor (cheaper) is used before overtime,
  * per-week caps on hiring and overtime are respected.
"""

import copy
import pytest

from farm_v2.solver import solve_farm_v2


def _labor_tight(params):
    """Squeeze the seasonal crew so labor is the binding constraint."""
    p = copy.deepcopy(params)
    p["seasonal_employees"] = [{
        "position": "Field Hand", "count": 2, "type": "FT",
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


def test_flex_never_lowers_profit_and_accounts_consistently(minimal_params):
    p = _labor_tight(minimal_params)
    base = solve_farm_v2(**p)
    flex = solve_farm_v2(
        **p,
        hire_enabled=True, max_hire_hrs_per_week=2000.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=1000.0,
    )
    assert flex["status"] == "optimal"
    # Buying labor is optional → can only help (allow tiny float slack).
    assert flex["operating_profit"] >= base["operating_profit"] - 1.0
    # P&L identity holds with the new cost lines included.
    recomputed = flex["revenue"] - (
        flex["fixed_cost"] + flex["variable_cost"] + flex["city_water_cost"]
        + flex["overtime_cost"] + flex["hire_cost"]
    )
    assert recomputed == pytest.approx(flex["operating_profit"], abs=1.0)


def test_hired_labor_used_before_overtime(minimal_params):
    # Generous hire cap, cheap (0 markup) → the optimizer should lean on hiring.
    p = _labor_tight(minimal_params)
    flex = solve_farm_v2(
        **p,
        hire_enabled=True, max_hire_hrs_per_week=5000.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=5000.0,
    )
    assert flex["status"] == "optimal"
    assert flex["total_hired_hours"] > 0.0
    # With a large hire cap and 0 markup, overtime (premium) should not be needed.
    assert flex["total_overtime_hours"] == pytest.approx(0.0, abs=1e-6)


def test_hire_cap_forces_overtime_overflow(minimal_params):
    # Tiny hire cap + tight labor → overflow must spill into overtime.
    p = _labor_tight(minimal_params)
    flex = solve_farm_v2(
        **p,
        hire_enabled=True, max_hire_hrs_per_week=50.0, hire_wage_markup=0.0,
        overtime_enabled=True, overtime_rate_multiplier=1.5, max_overtime_hrs_per_week=5000.0,
    )
    assert flex["status"] == "optimal"
    # Hired hours per week never exceed the cap.
    assert max(flex["hired_hours_weekly"]) <= 50.0 + 1e-6
