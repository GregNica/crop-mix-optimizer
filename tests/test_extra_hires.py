"""Extra hires per roster row (Batch L.3 — GROUP F1, the grower's design).

An extra head INHERITS its row — wage, hours, field %, window, overtime allowance — and is an
integer: a person, not a spot market of 2-hour weeks. It works at the farm-wide new-hire
productivity, is paid the row's full weekly pay in every window week (committed, W12) and costs
the one-off per-head amount once. What-If only (Q3): the main plan never hires.

The shipped golden farm hires ZERO (F1 measured every role losing money), so the "it hires"
side needs this forced fixture: a 2-person seasonal crew ($18/h, 40 h, weeks 8-46) on 200 acres.
"""
import copy
import json

import pytest

from farm_v2.adapter import run_from_js
from farm_v2.solver import solve_farm_v2
from tests.test_golden_farm import PAYLOAD
from tests.test_labor_flex import _labor_bound

WEEKS = 46 - 8 + 1                     # 39-week window
PAY_PER_HEAD = WEEKS * 40 * 18.0       # $28,080 — the row's full pay for its window
FEE = 800.0
PROD = 0.70


def _fixture(two_crop_params, max_more=20, **row):
    p = _labor_bound(two_crop_params, crew=2)
    p["seasonal_employees"][0].update(hire_more=True, max_more=max_more, **row)
    return p


@pytest.fixture
def hired(two_crop_params):
    p = _fixture(two_crop_params)
    return p, solve_farm_v2(**p, hire_enabled=True)


def test_the_main_plan_never_hires(two_crop_params):
    r = solve_farm_v2(**_fixture(two_crop_params))
    assert r["status"] == "optimal"
    assert r["extra_hires"] == [] and r["hire_cost"] == 0.0 and r["total_hired_hours"] == 0.0


def test_extra_heads_are_whole_people_within_the_row_limit(two_crop_params, hired):
    p, r = hired
    assert r["status"] == "optimal"
    (row,) = r["extra_hires"]
    assert row["extra"] >= 1, "fixture stopped hiring — every guard below is inert"
    assert row["extra"] == int(row["extra"]) and row["extra"] <= row["max_more"]
    capped = solve_farm_v2(**_fixture(two_crop_params, max_more=1), hire_enabled=True)
    assert capped["extra_hires"][0]["extra"] == 1, "max_more is not the limit"
    base = solve_farm_v2(**p)
    assert r["profit"] >= base["profit"] - 0.01, "an option the optimizer can decline cost money"


def test_a_head_is_paid_the_rows_full_window_plus_the_one_off_cost_once(hired):
    """Catches: billed one week instead of the window; the one-off cost charged every week
    ($800 × 39); the one-off cost dropped; pay at a different wage than the row's."""
    _p, r = hired
    (row,) = r["extra_hires"]
    assert row["cost_per_head"] == pytest.approx(PAY_PER_HEAD + FEE)
    assert r["hire_cost"] == pytest.approx(row["extra"] * (PAY_PER_HEAD + FEE))
    assert r["bought_capacity_split"]["hire"] == pytest.approx(r["hire_cost"])


def test_a_head_adds_its_rows_hours_at_new_hire_pace_in_its_window_only(hired):
    _p, r = hired
    (row,) = r["extra_hires"]
    assert row["hours_per_head"] == pytest.approx(WEEKS * 40 * PROD)
    for w, h in enumerate(r["hired_hours_weekly"], start=1):
        want = row["extra"] * 40 * PROD if 8 <= w <= 46 else 0.0
        assert h == pytest.approx(want, abs=1e-6), (w, h, want)


def test_productivity_decides_how_many_heads(two_crop_params):
    """At 100% pace each head does more, so the plan needs no more heads than at 70%."""
    p = _fixture(two_crop_params)
    slow = solve_farm_v2(**p, hire_enabled=True, hire_productivity_pct=40.0)
    fast = solve_farm_v2(**p, hire_enabled=True, hire_productivity_pct=100.0)
    assert slow["extra_hires"][0]["extra"] > fast["extra_hires"][0]["extra"]


def test_new_heads_may_work_overtime_too(two_crop_params):
    """The row's overtime cap grows with its heads: (allowance − 1) × (count + extra × pace) ×
    hours × field. The fixture must buy MORE overtime in some week than the original two could
    give (0.25 × 2 × 40 = 20 h), or a cap frozen at the original crew would pass unseen."""
    p = _fixture(two_crop_params)
    r = solve_farm_v2(**p, hire_enabled=True, overtime_enabled=True)
    assert r["status"] == "optimal"
    n = r["extra_hires"][0]["extra"]
    (ot,) = r["overtime_by_role"]
    assert max(ot["hours"]) > 20.0 + 1e-6, "OT never exceeds the original crew's cap — inert"
    for h in ot["hours"]:
        assert h <= 0.25 * 40 * (2 + n * PROD) + 1e-6


def test_hire_more_on_an_unpaid_row_is_refused_not_free(two_crop_params):
    p = _fixture(two_crop_params, wage=0.0)
    r = solve_farm_v2(**p, hire_enabled=True)
    assert r["status"] == "invalid_input"
    assert any("Hire more" in e for e in r["errors"])


@pytest.mark.parametrize("kw", [dict(hire_productivity_pct=0.0), dict(hire_cost_per_head=-1.0),
                                dict(hire_productivity_pct=float("nan"))])
def test_nonsense_hire_terms_are_refused(two_crop_params, kw):
    r = solve_farm_v2(**_fixture(two_crop_params), hire_enabled=True, **kw)
    assert r["status"] == "invalid_input"


def test_extra_hires_are_real_money_in_the_cash_floor(two_crop_params):
    """C13 must pay each head's wages week by week and the one-off cost in the first week."""
    # Measured: unconstrained it hires 3 and needs $760,084 of credit; at 97% it binds to the
    # dollar and hires 2 — cash costs a head, so the floor is live.
    p = dict(_fixture(two_crop_params), opening_cash=0.0)
    free = solve_farm_v2(**dict(p, credit_line=1e9), hire_enabled=True)
    need = -min(free["weekly_cash_flow"][1:])
    tight = solve_farm_v2(**dict(p, credit_line=need * 0.97), hire_enabled=True)
    assert tight["status"] == "optimal"
    assert tight["extra_hires"][0]["extra"] >= 1, "the tight fixture hires nobody — inert"
    assert min(tight["weekly_cash_flow"][1:]) == pytest.approx(-need * 0.97, abs=50.0), (
        "the floor no longer binds — fixture drifted")
    assert min(tight["weekly_cash_flow"][1:]) >= -need * 0.97 - 1.0, (
        "the plan breaches its credit line — extra hires' pay fell out of the cash floor"
    )


def test_the_adapter_carries_the_row_through_and_back(two_crop_params):
    """hire_more / max_more ride on the roster row; the result names the FORM row index so
    'Add to roster' adds the heads to the right line."""
    p = json.loads(PAYLOAD.read_text())
    p["labor_flex_enabled"] = True
    for e in p["employees"]:
        e["max_week_pct"] = 100                           # no overtime: make hiring the lever
    rows = {e["position"]: i for i, e in enumerate(p["employees"])}
    for name in ("Seasonal Field Crew", "Harvest Crew"):          # both crews cut to one person
        p["employees"][rows[name]].update(count=1, hire_more=True, max_more=10)
    out = json.loads(run_from_js(json.dumps(p)))
    assert out["status"] == "optimal", out.get("error", "")[:300]
    got = {r["position"]: r for r in out["extra_hires"]}
    assert set(got) == {"Seasonal Field Crew", "Harvest Crew"}
    for name, r in got.items():
        assert r["row"] == rows[name], "the result points at the wrong roster line"
        assert r["extra"] >= 1, f"{name} cut to one person hired nobody — fixture inert"
