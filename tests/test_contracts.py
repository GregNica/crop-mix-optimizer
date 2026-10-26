"""FX.3 — contracts: pounds owed to a buyer on a channel, week by week (SPEC_batchFX §3, §5 ruling 2).

A contract is a `commitments[]` entry of kind "contract" on a crop's IDENTITY (the crop and its FX.5
variants) and a channel. The grower MUST pick a mode: "deliver" is hard — a plan that cannot fill
every week is refused, naming the contract and the limit it presses on; "penalty" takes a $/lb and
the plan may come up short at that price. The penalty is in the objective and the P&L and NEVER in
the weekly cash floor (charged there, an unavoidable shortfall at a big penalty made the toy
infeasible). Each short week is reported as a FACT (no plan delivers it — kale has no harvest in
weeks 36-37, the toy's finding reproduced here) or a CHOICE (shorting was cheaper than growing).
§6.3: with `commitment_deltas` every commitment reports what it costs, on the OBJECTIVE.
"""
import pytest

from farm_v2.utils.commitments import describe, resolve_contracts
from tests.helpers import (commitments_farm as farm, solve_payload as solve,
                           solve_payload_optimal as solve_optimal, weekly)

TOL_LB = 0.5


def contract(**kw):
    base = dict(id="c1", kind="contract", crop="Kale", channel="Wholesale", lb_per_week=2000,
                from_week=20, to_week=35, mode="penalty", penalty_per_lb=0.50)
    base.update(kw)
    return base


def deliver(**kw):
    return contract(mode="deliver", penalty_per_lb=None, **kw)


def sold(r, channel, crop, w):
    return weekly(r, channel, crop)[w - 1]


@pytest.fixture(scope="module")
def penalty_8_40():
    """2,000 lb/wk of kale on Wholesale, weeks 8-40 at $0.50/lb short: no kale can be harvested
    before week 14 or in weeks 36-37, so those weeks are short whatever the price."""
    return solve_optimal(farm(contract(from_week=8, to_week=40)))


# ---------------------------------------------------------------------------
# Penalty mode
# ---------------------------------------------------------------------------

def test_penalty_contract_is_delivered_or_short_every_week(penalty_8_40):
    c = penalty_8_40["contracts"][0]
    assert c["mode"] == "penalty" and c["weeks"] == list(range(8, 41))
    for e in c["by_week"]:
        assert e["owed"] == 2000
        assert e["delivered"] + e["short"] >= 2000 - TOL_LB
        assert 0 <= e["short"] <= 2000 + TOL_LB
        assert e["delivered"] == pytest.approx(sold(penalty_8_40, "Wholesale", "Kale", e["week"]), abs=TOL_LB)
    assert c["owed_lbs"] == 2000 * 33
    assert c["short_lbs"] == pytest.approx(sum(e["short"] for e in c["by_week"]))
    assert c["penalty_cost"] == pytest.approx(c["short_lbs"] * 0.50)


def test_short_weeks_are_facts_where_no_kale_can_be_harvested(penalty_8_40):
    """Weeks 8-13 (no kale harvest before week 14) and 36-37 (the harvest gap) stay short at
    $1,000/lb: facts. The plan delivers the rest at $0.50."""
    c = penalty_8_40["contracts"][0]
    short = {e["week"]: e for e in c["by_week"] if e["short"] > TOL_LB}
    assert set(short) == {8, 9, 10, 11, 12, 13, 36, 37}
    assert all(e["kind"] == "fact" for e in short.values())
    assert c["short_kind"] == "fact"
    assert all(e["kind"] is None for e in c["by_week"] if e["short"] <= TOL_LB)


def test_a_cheap_penalty_makes_the_shortfall_a_choice():
    """4,000 lb/wk in weeks 14-35 at 1¢/lb: shorting is cheaper than growing, and the probe at
    $1,000/lb grows for those weeks — a CHOICE the grower could undo by raising the penalty."""
    r = solve_optimal(farm(contract(lb_per_week=4000, from_week=14, to_week=35, penalty_per_lb=0.01)))
    c = r["contracts"][0]
    assert c["short_lbs"] > 50_000
    assert c["short_kind"] == "choice"
    assert {e["kind"] for e in c["by_week"] if e["short"] > TOL_LB} == {"choice"}


def test_penalty_is_in_the_pl_and_operating_profit(penalty_8_40):
    r = penalty_8_40
    pen = r["contracts"][0]["penalty_cost"]
    assert pen > 0
    assert r["bought_capacity_split"]["contract_shortfall"] == pytest.approx(pen)
    # operating profit is what the objective maximised, so the penalty it charged sits inside it
    assert r["operating_profit"] == pytest.approx(
        r["revenue"] - r["fixed_cost"] - r["variable_cost"] - sum(r["bought_capacity_split"].values()),
        abs=0.01)


def test_penalty_is_never_in_the_weekly_cash_floor(golden_out):
    """The toy's guard: an unavoidable shortfall at $200/lb (6 weeks × 2,000 lb = $2.4M, more
    than the credit line) must still SOLVE, with the same plan and the same cash curve, and the
    penalty taken off profit after the season. ⚠️ The golden farm has no opening cash or credit
    line, so its cash floor is OFF and this guard was inert there (the mutant charging the
    penalty in C13 survived): the floor is switched on here, with a line just above the plan's
    own peak borrowing, so a penalty charged in it would make the plan infeasible."""
    cash = dict(opening_cash=0, credit_line=golden_out["peak_borrowing"] + 100_000)
    base = solve_optimal(farm(**cash))
    r = solve_optimal(farm(contract(from_week=5, to_week=10, penalty_per_lb=200), **cash))
    c = r["contracts"][0]
    assert c["short_lbs"] == pytest.approx(12_000, abs=TOL_LB)
    assert c["short_kind"] == "fact"
    assert r["bought_capacity_split"]["contract_shortfall"] == pytest.approx(2_400_000, abs=1)
    assert r["profit"] == pytest.approx(base["profit"] - 2_400_000, abs=1)
    assert r["weekly_cash_flow"] == base["weekly_cash_flow"]


def test_callers_that_read_only_the_status_skip_the_probe():
    """Without the probe a short week that SOMETHING could have sold in is 'unknown'; a week
    nothing can sell in needs no probe and is a fact either way."""
    r = solve_optimal(farm(contract(lb_per_week=4000, from_week=12, to_week=35, penalty_per_lb=0.01),
                           diagnose_infeasible=False))
    kinds = {e["week"]: e["kind"] for e in r["contracts"][0]["by_week"] if e["short"] > TOL_LB}
    assert kinds[12] == "fact" and kinds[13] == "fact"        # no kale harvest before week 14
    assert {k for w, k in kinds.items() if w >= 14} == {"unknown"}
    assert r["contracts"][0]["short_kind"] == "mixed"


# ---------------------------------------------------------------------------
# Deliver mode
# ---------------------------------------------------------------------------

def test_deliver_contract_is_filled_every_week():
    r = solve_optimal(farm(deliver(from_week=38, to_week=50)))
    c = r["contracts"][0]
    assert c["mode"] == "deliver" and c["short_lbs"] == 0 and c["penalty_cost"] == 0
    assert c["short_kind"] is None
    for e in c["by_week"]:
        assert e["delivered"] >= 2000 - TOL_LB
    assert min(e["delivered"] for e in c["by_week"]) == pytest.approx(2000, abs=TOL_LB)  # binds


def test_deliver_contract_beyond_the_crew_is_refused_naming_it_and_the_limit():
    r = solve(farm(deliver(lb_per_week=20_000, from_week=38, to_week=50)))
    assert r["status"] == "infeasible"
    assert "Kale on Wholesale: 20,000 lb/wk weeks 38–50, must deliver (c1)" in r["errors"][0]
    assert {b["limit"] for b in r["binding_limits"]} == {"labour"}
    assert r["binding_limits_verdict"] == "proved"


def test_deliver_contract_in_a_week_nothing_can_be_sold_is_refused_by_name():
    r = solve(farm(deliver(from_week=20, to_week=40)))
    assert r["status"] == "invalid_input"
    assert "weeks 36–37" in r["errors"][0] and "no planting of it can be harvested and sold" in r["errors"][0]


def test_a_penalty_contract_is_never_blamed_for_an_infeasible_plan():
    """45 ac of overwintered garlic cannot fit (FX.1); the penalty contract beside it can absorb
    any shortfall, so the refusal names the garlic and not the contract."""
    p = farm(contract())
    next(c for c in p["crops"] if c["name"] == "Garlic")["committed_acres"] = 45
    r = solve(p)
    assert r["status"] == "infeasible"
    assert "Garlic: 45 ac already in the ground" in r["errors"][0]
    assert "Kale on Wholesale" not in r["errors"][0]


# ---------------------------------------------------------------------------
# Identity (FX.5), suggestions, the hurdle
# ---------------------------------------------------------------------------

def test_contract_on_the_parent_is_delivered_by_the_variant_too():
    from tests.test_variants import variant_farm
    p = variant_farm()
    p["commitments"] = [contract(crop="Spinach", lb_per_week=25_000, from_week=11, to_week=20)]
    r = solve_optimal(p)
    c = r["contracts"][0]
    for e in c["by_week"]:
        both = sold(r, "Wholesale", "Spinach", e["week"]) + sold(r, "Wholesale", "Tunnel Spinach", e["week"])
        assert e["delivered"] == pytest.approx(both, abs=TOL_LB)
    assert any(sold(r, "Wholesale", "Tunnel Spinach", w) > TOL_LB for w in range(11, 21))


def test_contract_naming_the_variant_counts_the_variant_only():
    """Open-field Spinach sells 25,000 lb/wk on Wholesale in these weeks; none of it counts
    toward a contract for TUNNEL spinach, which must deliver its 500 lb itself."""
    from tests.test_variants import variant_farm
    p = variant_farm()
    p["commitments"] = [deliver(crop="Tunnel Spinach", lb_per_week=500, from_week=20, to_week=27)]
    r = solve_optimal(p)
    c = r["contracts"][0]
    for e in c["by_week"]:
        assert e["delivered"] == pytest.approx(sold(r, "Wholesale", "Tunnel Spinach", e["week"]), abs=TOL_LB)
        assert e["delivered"] >= 500 - TOL_LB
        assert sold(r, "Wholesale", "Spinach", e["week"]) > 1_000        # and is not what counted


def test_unaccepted_suggestion_does_not_bind(golden_out):
    r = solve_optimal(farm(contract(source="suggested")))
    assert r["contracts"] == []
    assert r["profit"] == pytest.approx(golden_out["profit"], abs=0.01)


def test_contract_on_a_channel_the_hurdle_dropped_is_refused_by_name():
    r = solve(farm(contract(), min_viable_margin_pct=90))
    assert r["status"] == "invalid_input"
    assert "minimum viable margin (90%) dropped that channel" in r["errors"][0]


# ---------------------------------------------------------------------------
# Refusals, by name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("change,words", [
    (dict(crop="Okra"), "not one of the farm's crops"),
    (dict(channel="CSA"), "not one of the farm's channels"),
    (dict(lb_per_week=0), "lb_per_week"),
    (dict(lb_per_week="2000"), "lb_per_week"),
    (dict(from_week=0), "from_week"),
    (dict(to_week=53), "to_week"),
    (dict(mode=None), "mode must be 'deliver'"),
    (dict(mode="hard"), "mode must be 'deliver'"),
    (dict(penalty_per_lb=None), "penalty_per_lb"),
    (dict(penalty_per_lb=0), "penalty_per_lb"),
    (dict(mode="deliver", penalty_per_lb=0.5), "has no penalty per pound"),
    # above the market: a weekly cap, an annual cap, and a week the channel takes nothing
    (dict(crop="Spinach", lb_per_week=26_000), "takes 25000 lb in week 20"),
    (dict(lb_per_week=20_000, from_week=20, to_week=45), "takes 500,000 lb a year"),
    (dict(channel="Farmers Market", lb_per_week=1000, from_week=5, to_week=12), "takes nothing from it that week"),
])
def test_bad_contract_is_refused(change, words):
    r = solve(farm(contract(**change)))
    assert r["status"] == "invalid_input", r
    assert words in r["errors"][0], r["errors"][0]


def test_contract_on_a_channel_the_crop_does_not_sell_on_is_refused():
    p = farm(contract(crop="Hot Peppers", lb_per_week=1000, from_week=30, to_week=35))
    del next(c for c in p["crops"] if c["name"] == "Hot Peppers")["channels"]["Wholesale"]
    r = solve(p)
    assert r["status"] == "invalid_input"
    assert "'Hot Peppers' does not sell on Wholesale" in r["errors"][0]


def test_describe_reads_as_the_grower_would():
    p = farm(contract(), deliver(id="c2", from_week=38, to_week=50))
    c1, c2 = resolve_contracts(p["commitments"], p["crops"], p["channels"])
    assert describe(c1) == "Kale on Wholesale: 2,000 lb/wk weeks 20–35, $0.50/lb short (c1)"
    assert describe(c2) == "Kale on Wholesale: 2,000 lb/wk weeks 38–50, must deliver (c2)"


# ---------------------------------------------------------------------------
# §6.3 — what each commitment costs
# ---------------------------------------------------------------------------

def test_commitment_deltas_are_off_by_default(penalty_8_40):
    assert penalty_8_40["commitment_deltas"] is None


def test_commitment_deltas_price_every_entry_on_the_objective():
    r = solve_optimal(farm(contract(), commitment_deltas=True))
    by_id = {d["id"]: d for d in r["commitment_deltas"]}
    assert set(by_id) == {"carry-in:Garlic", "c1"}
    assert all(d["status"] == "optimal" for d in by_id.values())
    c = by_id["c1"]
    assert c["label"].startswith("Kale on Wholesale")
    # the contract's penalty is part of what it costs; the plan it forces is the rest
    assert c["delta"] > r["bought_capacity_split"]["contract_shortfall"] + c["tolerance"]
    assert abs(by_id["carry-in:Garlic"]["delta"]) < 1_000     # the demo pin is near-free (FX.1)


# ---------------------------------------------------------------------------
# Guards that force the second condition (each inert on the tests above)
# ---------------------------------------------------------------------------

def test_a_contract_only_the_variant_can_fill_is_filled_by_it():
    """Field spinach's first harvest is week 11; the tunnel's is week 8. A contract on SPINACH
    for weeks 8-10 is met — by Tunnel Spinach, the identity's other member. A row that counted
    the parent alone could not fill it."""
    from tests.test_variants import variant_farm
    p = variant_farm()
    p["commitments"] = [deliver(crop="Spinach", lb_per_week=500, from_week=8, to_week=10)]
    r = solve_optimal(p)
    for e in r["contracts"][0]["by_week"]:
        assert e["delivered"] >= 500 - TOL_LB
        assert sold(r, "Wholesale", "Tunnel Spinach", e["week"]) >= 500 - TOL_LB
        assert sold(r, "Wholesale", "Spinach", e["week"]) == 0


def test_a_week_sold_from_held_stock_is_not_a_dead_week():
    """Kale's last summer harvest is week 34 and its shelf life 2 weeks, so week 35 sells only
    what was picked in 34 — a deliver contract through week 35 is met, and the dead weeks of a
    longer one are exactly 36-37 (asserted above). The sell window is h … h+L−1, not h+L−2."""
    r = solve_optimal(farm(deliver(from_week=30, to_week=35)))
    assert sold(r, "Wholesale", "Kale", 35) >= 2000 - TOL_LB


def test_without_a_carry_in_means_the_crop_is_free_not_capped():
    """Garlic pays and would take ~18 ac free. Pinned at 10, 'without the pin' must release the
    CEILING too: the delta is the cost of being held to 10 ac, far above the noise."""
    from tests.helpers import set_carry_in
    r = solve_optimal(set_carry_in(farm(commitment_deltas=True), 10))
    d = r["commitment_deltas"][0]
    assert d["id"] == "carry-in:Garlic" and d["status"] == "optimal"
    assert d["delta"] > 50_000 and d["delta"] > 10 * d["tolerance"]


def test_without_a_paying_patch_is_the_patch_removed_not_optional():
    """A bearing patch at 6,000 lb/ac earns its keep, so 'without it' is a LOSS (negative delta).
    If the release only freed its lower bound the optimiser would keep it and read ~$0."""
    from tests.test_perennials import perennial_farm, BEARING, ESTABLISHING
    r = solve_optimal(perennial_farm(dict(BEARING, yield_per_acre=6000), ESTABLISHING,
                                     commitment_deltas=True))
    d = next(x for x in r["commitment_deltas"] if x["id"] == "c1")
    assert d["status"] == "optimal"
    assert d["delta"] < -1_000 and -d["delta"] > 3 * d["tolerance"]
