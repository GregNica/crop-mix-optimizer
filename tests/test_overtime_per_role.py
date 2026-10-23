"""Overtime per role (Batch L.2 — GROUP F2 + F4), guarded on the SHIPPED golden farm.

Overtime is in the main plan (grower ruling Q1(a)), so the golden farm is the flex-ON fixture: it
buys 979 h across three roles, binds caps in several weeks, and has two hourly roles with
DIFFERENT wages on in the same short weeks — the two conditions the cap and the price tests need
(the shelf-life lesson: a guard needs every condition its effect depends on, not one).

  cap[r][w]  = (max_week_pct/100 − 1) × count × hours × field%    in r's window, else 0
  rate[r]    = wage × (multiplier × (1 + fica) + straight-time load)
  salaried and unpaid roles: no overtime at all
"""
import copy
import json

import pytest

from farm_v2.adapter import run_from_js
from farm_v2.utils.labor import compute_labor_arrays
from tests.helpers import golden_payload

# Shipped roster at 125% (40 + 10 OT): cap = 0.25 × count × 40 × field%.
EXPECTED_CAP = {"Equipment Operator": 0.25 * 2 * 40 * 0.90,   # 18 h/wk, weeks 1-52
                "Seasonal Field Crew": 0.25 * 12 * 40,         # 120 h/wk, weeks 10-42
                "Harvest Crew": 0.25 * 8 * 40}                 # 80 h/wk, weeks 14-40
WINDOW = {"Equipment Operator": (1, 52), "Seasonal Field Crew": (10, 42), "Harvest Crew": (14, 40)}
WAGE = {"Equipment Operator": 26.0, "Seasonal Field Crew": 20.0, "Harvest Crew": 19.0}
FICA, STRAIGHT = 0.0765, 0.1735   # shipped split of the old 25% (L.5)
# Pinned from the 2026-10-23 re-pin (test_golden_farm GOLDEN history).
EXPECTED_HOURS = {"Equipment Operator": 70.2, "Seasonal Field Crew": 407.9, "Harvest Crew": 500.6}


def _solve(**over):
    out = json.loads(run_from_js(json.dumps(golden_payload(**over))))
    assert out["status"] == "optimal", out.get("error", "")[:300]
    return out


@pytest.fixture
def golden(golden_out):
    return golden_out


def _roles(out):
    return {r["position"]: r for r in out["overtime_by_role"]}


def test_only_paid_hourly_roles_can_work_overtime(golden):
    assert set(_roles(golden)) == set(EXPECTED_CAP), (
        "the salaried Farm Manager must get no overtime, and every hourly role must"
    )


def test_each_cap_is_derived_from_its_own_row_and_window(golden):
    """Catches `allowance` for `allowance − 1` (a 125% week would allow 50 OT hours, not 10),
    a dropped field %, and a cap leaking outside the role's window."""
    for name, r in _roles(golden).items():
        lo, hi = WINDOW[name]
        for w, cap in enumerate(r["cap"], start=1):
            want = EXPECTED_CAP[name] if lo <= w <= hi else 0.0
            assert cap == pytest.approx(want, abs=0.05), (name, w, cap, want)


def test_overtime_never_exceeds_a_cap_and_the_caps_bind(golden):
    binding = 0
    for name, r in _roles(golden).items():
        for h, cap in zip(r["hours"], r["cap"]):
            assert h <= cap + 0.05, (name, h, cap)
            binding += cap > 0 and h >= cap - 0.05
    assert binding >= 5, "no cap binds — this fixture can no longer catch a wrong cap"


def test_each_role_is_priced_at_its_own_wage(golden):
    """At the shipped 1.0× an overtime hour costs exactly a regular loaded hour, per role.
    A blended rate would print one number for all three."""
    for name, r in _roles(golden).items():
        assert r["rate"] == pytest.approx(WAGE[name] * (1 + FICA + STRAIGHT), abs=0.01), name


def test_the_cheaper_role_works_overtime_first(golden):
    """Harvest Crew ($23.75) and Seasonal Field Crew ($25.00) are both on in weeks 14-40: the
    dearer crew may stay late only once the cheaper one is at its cap."""
    R = _roles(golden)
    sfc, hc = R["Seasonal Field Crew"], R["Harvest Crew"]
    both = [w for w in range(52) if sfc["hours"][w] > 0.05 and hc["cap"][w] > 0]
    assert both, "no week uses the dearer crew while the cheaper one is on — fixture inert"
    for w in both:
        assert hc["hours"][w] >= hc["cap"][w] - 0.05, (
            f"week {w + 1}: the $25.00 crew worked overtime while the $23.75 crew had room"
        )


def test_overtime_hours_and_cost_are_pinned_and_reconcile(golden):
    R = _roles(golden)
    for name, want in EXPECTED_HOURS.items():
        assert sum(R[name]["hours"]) == pytest.approx(want, abs=0.5), name
    cost = sum(sum(r["hours"]) * r["rate"] for r in R.values())
    assert golden["bought_capacity_split"]["overtime"] == pytest.approx(cost, abs=5.0)
    assert golden["total_overtime_hours"] == pytest.approx(sum(EXPECTED_HOURS.values()), abs=1.0)
    weekly = golden["overtime_hours_weekly"]
    assert len(weekly) == 52
    for w in range(52):
        assert weekly[w] == pytest.approx(sum(r["hours"][w] for r in R.values()), abs=0.2)


def test_the_premium_carries_fica_only(golden):
    """At 1.5× the premium half-hour carries FICA but not the straight-time load (I2b):
    rate = wage × (1.5 × 1.0765 + 0.1735). Untestable at the shipped 1.0×, where there is no
    premium — hence this second solve."""
    R = _roles(_solve(overtime_rate_multiplier=1.5))
    for name, r in R.items():
        assert r["rate"] == pytest.approx(WAGE[name] * (1.5 * (1 + FICA) + STRAIGHT), abs=0.01), name


def test_a_100pct_week_means_no_overtime_and_restores_the_pre_L2_farm():
    """The grower's off-switch: every row at 100%. Byte-equal to the pre-L.2 baseline profit."""
    p = golden_payload()
    for e in p["employees"]:
        e["max_week_pct"] = 100
    out = json.loads(run_from_js(json.dumps(p)))
    assert out["status"] == "optimal"
    assert out["total_overtime_hours"] == 0.0 and out["overtime_by_role"] == []
    assert out["profit"] == pytest.approx(612_912.19, abs=0.01)


# Which roles may work overtime is decided in labor._role before any solve (the solver's ot_roles
# is exactly the rows with ot_cap > 0), so these two are checked there — no 3 s solve each.
_SHIPPED_ROLES = [dict(position="Farm Manager", count=1, type="salary", wage=95_000.0,
                       hours_per_week=45, admin_pct=20),
                  dict(position="Harvest Crew", count=8, type="hourly", wage=19.0,
                       hours_per_week=40, admin_pct=0)]


def test_an_unpaid_hourly_role_gets_no_overtime():
    roles = [dict(r) for r in _SHIPPED_ROLES]
    roles[1]["wage"] = 0.0
    hc = compute_labor_arrays(roles, [])["labor_by_role"][1]
    assert float(hc["ot_cap"].max()) == 0.0 and hc["ot_rate"] == 0.0, (
        "an hour nobody pays for was made buyable (free labour)")


def test_a_salaried_row_typed_above_100pct_still_gets_no_overtime():
    """Salaried staff cannot be paid overtime. A salaried row TYPED at 125% would otherwise be
    priced per hour at its annual salary."""
    roles = [dict(r, max_week_pct=125) for r in _SHIPPED_ROLES]
    mgr, hc = compute_labor_arrays(roles, [])["labor_by_role"]
    assert float(mgr["ot_cap"].max()) == 0.0 and mgr["ot_rate"] == 0.0
    assert float(hc["ot_cap"].max()) > 0, "fixture inert: the hourly row got no overtime either"


def test_overtime_is_real_money_in_the_cash_floor():
    """C13 must charge overtime in the week it is paid. Two conditions: the floor must BIND, and
    overtime must be bought on or before the binding week — the two-crop cash fixture binds in
    week 14 with its overtime from week 15, so it cannot see this. The golden farm at a $95k
    credit line binds in week 10, after week-9 overtime (measured: profit $633,396 vs $652,876
    unconstrained, so cash costs profit)."""
    out = _solve(credit_line=95_000.0)
    cash = out["weekly_cash_flow"][1:]
    bind_wk = min(range(52), key=lambda w: cash[w])
    assert min(cash) == pytest.approx(-95_000.0, abs=50.0), "the floor no longer binds — fixture drifted"
    assert sum(out["overtime_hours_weekly"][: bind_wk + 1]) > 1.0, (
        "no overtime on or before the binding week — this guard is inert"
    )
    assert min(cash) >= -95_000.0 - 1.0, (
        f"the plan breaches its credit line by ${-95_000.0 - min(cash):,.2f} — overtime is being "
        f"bought with cash the farm does not have (its cost fell out of C13)"
    )
