"""W8 — totals summed from their parts, and NET profit finished in the solver.

Measured before the fix (2026-10-19, golden farm): `solve_farm_v2` reported profit
$625,912.19 while the app showed $612,912.19 — the adapter, not the solver, deducted the
Farmers Market's $250/wk stall fee, so any caller of the solver itself (pytest, the planned
server) got a profit $13,000 too high. The browser's sweeps were never affected: they all go
through `run_from_js`. The other three parts are the W4 rule applied to the last totals that
were still written BESIDE their breakdowns: `total_cost` (never returned; the P&L re-derived
it from three hand-named keys), `revenue` (a second accumulation of the same product as
`channel_sales`), and per-channel fixed selling (re-derived in the P&L as rate x 52).
"""
import copy
import json

import pytest

import farm_v2.adapter as adapter
from farm_v2.solver import solve_farm_v2
from tests.helpers import GOLDEN_PAYLOAD

FEE_WK = 250.0


def _with_fee(params, fee=FEE_WK):
    p = copy.deepcopy(params)
    p["channels"] = [dict(ch, fixed_selling_cost_per_wk=fee) for ch in p["channels"]]
    return p


def test_solver_profit_is_net_of_channel_fixed_selling(two_crop_params):
    r = solve_farm_v2(**_with_fee(two_crop_params))
    assert r["status"] == "optimal", r["status"]
    ch = two_crop_params["channels"][0]["name"]
    assert r["fixed_selling_split"] == {ch: pytest.approx(FEE_WK * 52)}
    assert r["fixed_selling_cost"] == pytest.approx(FEE_WK * 52)
    # The identity, not a delta against a no-fee farm: the fee is also a cash outflow, so it
    # moves interest (and, where C13 binds, the plan) — a delta would be measuring those too.
    assert r["profit"] == pytest.approx(
        r["operating_profit"] - r["overhead_cost"] - r["fixed_selling_cost"] - r["interest_cost"],
        abs=1e-6), "net profit is no longer finished in the solver — the adapter-only deduction is back"


def test_a_channel_without_a_fee_has_no_split_entry(solved_two_crop):
    r, _ = solved_two_crop
    assert r["fixed_selling_split"] == {}
    assert r["fixed_selling_cost"] == 0.0


@pytest.fixture(scope="module")
def golden_both():
    """ONE golden-farm solve through the real adapter, keeping the solver's own result too."""
    seen, real = {}, adapter.solve_farm_v2

    def spy(**kw):
        seen["r"] = real(**kw)
        return seen["r"]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(adapter, "solve_farm_v2", spy)
        out = json.loads(adapter.run_from_js(GOLDEN_PAYLOAD.read_text()))
    assert out["status"] == "optimal", out.get("error", "")[:300]
    return seen["r"], out


def test_direct_caller_and_adapter_report_the_same_profit(golden_both):
    """The measured defect itself: $13,000 apart on the golden farm before W8."""
    r, out = golden_both
    assert out["fixed_selling_cost"] > 0, "the golden farm no longer charges a stall fee — this guard is inert"
    assert r["profit"] == out["profit"], (
        f"solver profit {r['profit']:,.2f} vs app {out['profit']:,.2f} — a caller that "
        f"skips the adapter gets a different number again")


def test_total_cost_is_summed_from_its_parts_and_closes_operating_profit(two_crop_params):
    from tests.test_labor_flex import _labor_bound
    r = solve_farm_v2(**_labor_bound(two_crop_params),
                      hire_enabled=True, max_hire_hrs_per_week=2000.0, hire_wage_markup=0.0,
                      overtime_enabled=True, overtime_rate_multiplier=1.5,
                      max_overtime_hrs_per_week=1000.0)
    assert r["status"] == "optimal"
    split = r["bought_capacity_split"]
    assert sum(split.values()) > 0, "fixture bought nothing — a dropped term would be invisible"
    assert set(split) == {"city_water", "overtime", "hire"}
    assert r["total_cost"] == pytest.approx(
        r["fixed_cost"] + r["variable_cost"] + sum(split.values()), abs=1e-6)
    assert r["revenue"] - r["total_cost"] == pytest.approx(r["operating_profit"], abs=1e-6)


def test_revenue_is_pounds_sold_times_the_typed_price(solved_two_crop):
    """Revenue is now summed FROM channel_sales by construction, so asserting that sum again
    would be a tautology. Check it against an INDEPENDENT derivation instead: the pounds the plan
    sold (read off `v` itself) times the price per lb as the CALLER typed it. A wrong factor in
    the solver's price array (sell-through, a unit) now fails here."""
    r, params = solved_two_crop
    v = r["v"]
    expect = sum(
        float(v[c, ch, 1:].sum()) * crop["channels"].get(chan["name"], {}).get("price_per_lb", 0.0)
        for c, crop in enumerate(params["crops"])
        for ch, chan in enumerate(params["channels"]))
    assert expect > 0
    assert r["revenue"] == pytest.approx(expect, rel=1e-12)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), None, "250"])
def test_a_bad_channel_fee_is_refused(two_crop_params, bad):
    r = solve_farm_v2(**_with_fee(two_crop_params, bad))
    assert r["status"] == "invalid_input", r["status"]


def test_the_adapter_forwards_every_new_money_key(golden_both):
    """Guardrail 10: a solver key the adapter does not forward is a feature with no path in.
    (Profit needs no identity here: the test above proves it equals the solver's, whose
    identity is pinned at the top of this file.)"""
    r, out = golden_both
    assert out["fixed_selling_split"] == {"Farmers Market": pytest.approx(FEE_WK * 52)}
    assert out["fixed_selling_split"] == r["fixed_selling_split"]
    assert out["bought_capacity_split"] == r["bought_capacity_split"]


def test_the_waterfall_draws_bought_capacity(golden_both, monkeypatch):
    """The waterfall's bars must add up to Net Profit. It had no bar for city water, overtime
    or hire, so on any farm buying them the chart was short by exactly that spend (W8 review).
    The golden farm buys none, so the figure is injected; the drawing itself is stubbed."""
    pytest.importorskip("matplotlib")
    import farm_v2.charts as charts
    _, out = golden_both
    seen = {}
    monkeypatch.setattr(charts, "make_waterfall_chart", lambda *a, **k: seen.update(args=a) or "")
    charts.waterfall_png(json.dumps(dict(out, bought_capacity_split={
        "city_water": 1_000.0, "overtime": 20_000.0, "hire": 4_000.0})))
    assert seen["args"][-1] == pytest.approx(25_000.0), "bought capacity never reaches the chart"
