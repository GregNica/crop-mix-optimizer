"""R7 (Batch 2.2) — land rent, the rest of ownership cost, and insurance WITH its payment week.

Before R7 land read $0 and the six owned asset classes carried depreciation only — the D of the
standard D-I-R-T-I ownership cost — so owning was systematically under-costed. Each line is checked
against an independent derivation from the inputs, and the insurance payment week against the two
places timing lives: the reported cash curve, and the C13 cash floor the solver enforces (a lump
premium the floor did not see would let the plan overdraw its own credit line).
"""
import copy
import json

import numpy as np
import pytest

from farm_v2.adapter import run_from_js
from farm_v2.solver import OWNED_ASSET_CLASSES, solve_farm_v2
from tests.helpers import REPO, golden_payload
from tests.test_cash_floor_guards import _cash_bound

CAPITAL = {"harvest_storage": 500.0, "ambient_storage": 150.0, "water_storage": 0.5,
           "irrigation": 2000.0, "equipment_storage": 500.0, "fuel_storage": 13.0}


def _solve(params, **kw):
    p = copy.deepcopy(params)
    p.update(kw)
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", (r["status"], r.get("errors"))
    return p, r


def test_land_rent_is_rented_acres_times_rent(two_crop_params):
    _, r = _solve(two_crop_params, rented_acres=20.0, cash_rent_per_acre_yr=300.0)
    assert r["fixed_cost_split"]["land_rent"] == pytest.approx(6_000.0)


def test_ownership_carrying_is_the_rate_on_installed_cost(two_crop_params):
    p, r = _solve(two_crop_params, ownership_carrying_rate=0.06, capital_cost_per_unit=CAPITAL)
    capacity = {"harvest_storage": p["harvest_storage_cap"], "ambient_storage": p.get("ambient_storage_cap", 0.0),
                "water_storage": p.get("water_storage_capacity", 0.0), "irrigation": p["total_land"],
                "equipment_storage": p.get("equip_storage", 0.0), "fuel_storage": p.get("fuel_storage", 0.0)}
    assert set(capacity) == set(OWNED_ASSET_CLASSES)
    want = 0.06 * sum(CAPITAL[c] * capacity[c] for c in OWNED_ASSET_CLASSES)
    assert want > 0, "fixture owns nothing — the carrying charge would be invisible"
    assert r["fixed_cost_split"]["ownership_carrying"] == pytest.approx(want, rel=1e-12)


def test_every_line_is_zero_by_default(solved_two_crop):
    """The golden farm must not move until the Batch 2 re-pin switches the defaults on."""
    r, _ = solved_two_crop
    assert {k: r["fixed_cost_split"][k] for k in ("land_rent", "ownership_carrying", "insurance")} == \
        {"land_rent": 0.0, "ownership_carrying": 0.0, "insurance": 0.0}


def test_a_lump_premium_moves_cash_to_its_week_and_nowhere_else(two_crop_params):
    """Same premium, spread vs paid in week 20, on a farm that never borrows (so interest — which
    comes off the cash curve — cannot differ, and neither can the plan). The cash curves must
    differ by EXACTLY the premium's timing: ahead by premium x t/52 before week 20, and behind by
    premium x (1 - t/52) from it on."""
    rich = dict(opening_cash=1e9, credit_line=0.0)
    _, spread = _solve(two_crop_params, insurance_premium_per_yr=5_200.0, **rich)
    _, lump = _solve(two_crop_params, insurance_premium_per_yr=5_200.0, insurance_payment_week=20, **rich)
    assert spread["fixed_cost_split"]["insurance"] == lump["fixed_cost_split"]["insurance"] == 5_200.0
    assert lump["profit"] == pytest.approx(spread["profit"], abs=1e-6)
    t = np.arange(1, 53)
    want = np.where(t < 20, 5_200.0 * t / 52, 5_200.0 * t / 52 - 5_200.0)
    got = np.array(lump["weekly_cash_flow"][1:]) - np.array(spread["weekly_cash_flow"][1:])
    assert np.allclose(got, want, atol=1e-6), f"the premium landed in the wrong week(s): {np.round(got - want, 2)}"


def test_the_cash_floor_sees_a_lump_premium(two_crop_params):
    """The binding cash fixture (tests/test_cash_floor_guards.py), with a $30,000 premium paid in
    week 12 and the credit line raised by the same $30,000 so it stays solvable. If C13 did not
    carry the lump, the solver would plan as if the cash were still there and the curve it REPORTS
    (which does carry it) would sit up to $30,000 under the credit line."""
    p = _cash_bound(two_crop_params, crew=6, opening_cash=600_000.0, credit_line=170_000.0,
                    insurance_premium_per_yr=30_000.0, insurance_payment_week=12)
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", (r["status"], r.get("errors"))
    cum = np.array(r["weekly_cash_flow"][1:], dtype=float)
    assert cum.min() >= -p["credit_line"] - 1.0, (
        f"the plan overdraws its own credit line by ${-p['credit_line'] - cum.min():,.0f}: the cash "
        "floor did not see the premium the cash curve charges")


@pytest.mark.parametrize("bad", [
    dict(rented_acres=-1.0), dict(rented_acres=10_000.0), dict(cash_rent_per_acre_yr=float("nan")),
    dict(ownership_carrying_rate=-0.01), dict(insurance_premium_per_yr=-5.0),
    dict(utilities_cost_per_yr=-1.0), dict(utilities_cost_per_yr=float("nan")), dict(utilities_cost_per_yr="7800"),
    dict(insurance_payment_week=0), dict(insurance_payment_week=53), dict(insurance_payment_week=12.5),
    dict(capital_cost_per_unit={"harvest_storage": -1.0}),
    # Unknown classes are refused, not ignored: the solver only reads known ones, so a typo
    # ('equip_storage') or a non-class ('machinery') would charge nothing, silently.
    dict(capital_cost_per_unit={"equip_storage": 500.0}),
    dict(capital_cost_per_unit={"machinery": 80_000.0}),
    dict(capital_cost_per_unit="500"),
    # Carrying on the 'no constraint' capacity sentinel would bill a billion cubic metres.
    dict(harvest_storage_cap=1e9, ownership_carrying_rate=0.05, capital_cost_per_unit={"harvest_storage": 500.0}),
])
def test_bad_inputs_are_refused(two_crop_params, bad):
    p = copy.deepcopy(two_crop_params)
    p.update(bad)
    assert solve_farm_v2(**p)["status"] == "invalid_input"


def test_the_adapter_carries_every_r7_key_to_the_solver():
    """Guardrail 10: a payload key the adapter does not forward is a feature with no path in."""
    p = golden_payload(rented_acres=10.0, cash_rent_per_acre_yr=250.0, ownership_carrying_rate=0.05,
                       capital_cost_per_unit=CAPITAL, insurance_premium_per_yr=4_000.0, insurance_payment_week=10)
    out = json.loads(run_from_js(json.dumps(p)))
    assert out["status"] == "optimal", out.get("error", "")[:300]
    split = out["fixed_cost_split"]
    assert split["land_rent"] == pytest.approx(2_500.0)
    assert split["ownership_carrying"] > 0
    assert split["insurance"] == pytest.approx(4_000.0)
    # The payment WEEK changes no total, only timing — so it is checked on the cash curve: the same
    # premium spread evenly must leave a different week-10 position than one paid in week 10.
    p.pop("insurance_payment_week")
    spread = json.loads(run_from_js(json.dumps(p)))
    assert spread["weekly_cash_flow"][10] - out["weekly_cash_flow"][10] == pytest.approx(
        4_000.0 - 4_000.0 * 10 / 52, abs=2.0), "the adapter did not carry the insurance payment week"


@pytest.mark.parametrize("key", ["rented_acres", "cash_rent_per_acre_yr", "ownership_carrying_rate",
                                 "insurance_premium_per_yr", "utilities_cost_per_yr"])
def test_a_present_null_is_refused_not_read_as_zero(key):
    """The form always sends a number, so a null means a blanked box or NaN crossing the boundary —
    charging $0 for it would invent the value (the _num_no_invent contract)."""
    p = golden_payload(**{key: None})
    out = json.loads(run_from_js(json.dumps(p)))
    # The refusal itself — naming the key — not merely "not optimal", which a crash would also be.
    assert out.get("status") == "error" and key in out.get("error", ""), (
        f"a null {key} was not refused by name (status={out.get('status')}, error={out.get('error','')[:120]!r})")


def test_the_page_and_the_solver_name_the_same_owned_asset_classes():
    """The page's OWNED_CAPITAL table supplies capital_cost_per_unit; validate.py refuses an unknown
    class. A class added on one side only would break every solve (or charge nothing)."""
    import re
    from tests.helpers import index_src
    block = re.search(r"const OWNED_CAPITAL = \{(.*?)\n\};", index_src(), re.S).group(1)
    assert tuple(re.findall(r"^\s+(\w+):", block, re.M)) == OWNED_ASSET_CLASSES
    # ...and the registry's payload entry names the same installed-cost fields, in the same order
    # (a third hand-kept copy of the list, which nothing else checks).
    cost_fields = re.findall(r"^\s+\w+:\s+\['(\w+)'", block, re.M)
    fields_js = (REPO / "public" / "fields.js").read_text()
    from_list = re.search(r"capital_cost_per_unit:\s*\{ from: \[(.*?)\]", fields_js, re.S).group(1)
    assert re.findall(r"'(\w+)'", from_list) == cost_fields
