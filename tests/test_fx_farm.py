"""
THE FX GOLDEN FARM — the money regression for the fixed layer (SPEC_batchFX §3, FX.7).

The shipped golden farm (test_golden_farm.py) sends no zones, no variant, no perennial, no floor
and no contract — only garlic's carry-in. Across the five FX features it moved ONCE, by $45, when
FX.1 pinned that carry-in (test_golden_farm.py's history); it cannot see the rest: a mutant that charges no penalty, gives the tunnel rain, or
keys the market by name instead of identity leaves it green (the L4 trap, SPEC_batchFX). This
fixture is the shipped farm WITH every piece at once (tests/helpers.py `fx_farm`), pinned the same
way: five plan-determined lines to the cent, the two cash-timed ones to $50.

Every piece was MEASURED to bind or move money on this farm before it was pinned (2026-10-26),
and the liveness tests below keep it that way — a floor the plan clears anyway, a contract the
plan fills anyway or a zone with room to spare would leave the pin agreeing with the plain golden
farm on exactly the rows this file exists to watch. Removing each piece, measured:

    zones        tunnel spinach 6.8 ac -> 73.9 ac (the better spinach takes the field)   +$24,524
    variant      profit −$35,902; without it Spinach alone fills the market
    perennial    +$35,200 (4 ac of land all year, and the contract that needs the patch)
    floors       +$34,962 — the kale annual floor is $31,801 of it, the standing floor $512
    contracts    +$10,625 — the kale shortfall (weeks 36-37) and spinach's (32-36) are $6,500
                 of penalty; the asparagus must-deliver pulls 1,150 lb off the farmers market

WHEN THIS FAILS: as for the golden farm — find the line that moved, decide whether the new number
is the more honest one, and re-pin WITH a note. If the plain golden farm moved too, the cause is
not in the fixed layer; re-pin both in one commit. If only this one moved, it is.
"""
import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from tests.helpers import (ASPARAGUS, FX_COMMITMENTS, ROUNDING, TOL_LB,          # noqa: E402
                           assert_pnl_identities, assert_pnl_line, by_id, fx_farm, golden_crop,
                           golden_payload, load_toy_lp, planted, pnl_tolerance,
                           solve_payload_optimal as solve_optimal, spinach_fm_cap, standing,
                           weekly, weekly_identity)

# Pinned 2026-10-26 on the fixture's first build. Baseline history — re-pin ONLY with a reason:
#   2026-10-26 (first pin): profit 619,491.10 against the plain golden farm's 652,831.24 — the
#     fixed layer costs this farm $33,340, mostly the kale annual floor (45 ac of kale the plan
#     would not choose: $31,801) and the land the asparagus patches hold all year. Solves in
#     ~6 s against the golden farm's ~3 s: only kale is eligible in both zones, so only its slots
#     are doubled (SPEC_batchFX FX.4 deferral 5 — watch this if more crops go in both).
#     Bought capacity inside operating_profit: overtime $24,460.29 (the golden farm's ~$24,370 —
#     the floors keep the crew busy) + the $6,500.00 contract penalty. A ~$24k break here can be
#     the overtime price, not the fixed layer.
FX_GOLDEN = {
    "revenue":          2_497_869.57,
    "variable_cost":      482_363.32,
    "fixed_cost":         949_497.22,
    "overhead_cost":      399_659.13,
    "interest_cost":        2_898.51,
    "profit":             619_491.10,
    "operating_profit": 1_035_048.74,
}
HINT = "If the plain golden farm (test_golden_farm.py) is unchanged, the cause is in the fixed layer."

FX_PAYLOAD = fx_farm()
BY_ID = {e["id"]: e for e in FX_COMMITMENTS}
P1, K1, K2, C3 = BY_ID["p1"], BY_ID["k1"], BY_ID["k2"], BY_ID["c3"]
SPINACHES = ("Spinach", "Tunnel Spinach")
# What the fixture states, derived once: the bearing patch's pounds, what the must-deliver owes
# of them, and what is left for the dearer market (its cap, 300 lb × 8 weeks, is 2,400 — more).
SELLABLE = P1["acres"] * P1["yield_per_acre"]                          # 5,250 lb
OWED = C3["lb_per_week"] * (C3["to_week"] - C3["from_week"] + 1)       # 4,000 lb
TO_MARKET = SELLABLE - OWED                                            # 1,250 lb


@pytest.fixture(scope="module")
def fx():
    return solve_optimal(FX_PAYLOAD)


# ---------------------------------------------------------------------------
# The pin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line", sorted(FX_GOLDEN))
def test_pnl_line_is_pinned(fx, line):
    assert_pnl_line(fx, FX_GOLDEN, line, HINT)


def test_identities_hold_with_the_fixed_layer_in_the_mix(fx):
    """The golden farm's identities, now over a pinned perennial, a variant and a contract
    penalty (bought capacity inside operating profit)."""
    assert_pnl_identities(fx, FX_PAYLOAD["overhead_pct_of_revenue"])
    assert {"Asparagus", "Tunnel Spinach"} <= set(fx["crop_contribution"])
    assert fx["bought_capacity_split"]["overtime"] > 0      # the pin depends on its price too


def test_the_shipped_golden_farm_carries_none_of_this():
    """The L4 trap, stated: the plain golden farm's pin is blind to the fixed layer BECAUSE its
    payload has none of it. If the demo ever gains a zone, a variant, a patch or a commitment,
    this fixture's claim changes and the two pins must be re-read together."""
    p = golden_payload()
    assert "zones" not in p and "commitments" not in p
    assert not any(c.get("sells_as") or c.get("perennial") or c.get("zones") for c in p["crops"])
    assert [c["name"] for c in p["crops"] if c.get("committed_acres")] == ["Garlic"]


# ---------------------------------------------------------------------------
# Liveness — each piece must bind or sell here, or the pin above proves nothing about it
# ---------------------------------------------------------------------------

def test_the_tunnel_is_full_and_holds_only_its_crops(fx):
    tunnel = next(z for z in fx["zones"] if z["name"] == "High tunnel")
    assert max(tunnel["used_acres"]) == pytest.approx(tunnel["acres"], abs=1e-6)
    in_tunnel = {s["crop"] for s in fx["succession_schedule"] if s["zone"] == "High tunnel"}
    assert in_tunnel and in_tunnel <= {"Tunnel Spinach", "Kale"}
    assert all(s["zone"] == "High tunnel" for s in fx["succession_schedule"]
               if s["crop"] == "Tunnel Spinach")


def test_both_spinaches_sell_into_one_market(fx):
    """FX.5: the identity shares Farmers Market's weekly cap — never over it together, at it in
    some week where BOTH names are selling (keyed by name, each would have the whole market)."""
    cap = spinach_fm_cap()
    field, tunnel = (weekly(fx, "Farmers Market", c) for c in SPINACHES)
    both = weekly_identity(fx, "Farmers Market", *SPINACHES)
    assert max(both) <= cap + TOL_LB
    assert planted(fx, "Tunnel Spinach") > 0 and sum(tunnel) > 0
    shared = [w + 1 for w, (b, f, t) in enumerate(zip(both, field, tunnel))
              if b >= cap - TOL_LB and f > TOL_LB and t > TOL_LB]
    assert shared, "no week has both names at the cap together — the shared row is untested here"


def test_the_patches_stand_pinned_all_year_and_the_harvest_is_sold(fx):
    """FX.2: 3 bearing acres + 1 establishing, weeks 1-52 in the open field; the bearing patch's
    pounds all sold — the contract's to Wholesale, the rest to the dearer market (the toy's
    split, to the pound); the establishing patch sells nothing and pays its extra."""
    rows = {s["commitment_id"]: s for s in fx["succession_schedule"] if s["commitment_id"]}
    assert set(rows) == {"p1", "p2"}
    for e in (P1, BY_ID["p2"]):
        row = rows[e["id"]]
        assert row["acres"] == e["acres"] and len(row["weeks"]) == 52
        assert row["zone"] == "Open field" and 0 not in row["phases"]
    p1, p2 = by_id(fx, "perennial_blocks", "p1"), by_id(fx, "perennial_blocks", "p2")
    assert (p1["stage"], p1["sellable_lbs"]) == ("bearing", SELLABLE)
    assert (p2["stage"], p2["sellable_lbs"]) == ("establishing", 0.0)
    assert sum(weekly(fx, "Wholesale", "Asparagus")) == pytest.approx(OWED, abs=TOL_LB)
    assert sum(weekly(fx, "Farmers Market", "Asparagus")) == pytest.approx(TO_MARKET, abs=TOL_LB)
    assert fx["variable_cost_split"]["perennial_extra"] == pytest.approx(
        BY_ID["p2"]["acres"] * BY_ID["p2"]["extra_cost_per_acre"])


def test_both_kale_floors_bind(fx):
    """FX.1: a floor that binds is met EXACTLY — the plan stands 6.0 ac in weeks 26-28 and
    plants 19 ac of kale without them (measured), so landing on 8.0 and 45 is the floor. The
    annual figure is the solver's own (unrounded); the standing one sums a few 0.1-ac rows."""
    window = [standing(fx, "Kale", w) for w in range(K1["from_week"], K1["to_week"] + 1)]
    assert min(window) == pytest.approx(K1["acres"], abs=ROUNDING)
    assert planted(fx, "Kale") == pytest.approx(K2["acres"], abs=1e-6)


def test_garlic_stands_at_its_carry_in(fx):
    assert standing(fx, "Garlic", 1) == pytest.approx(golden_crop("Garlic")["committed_acres"], abs=ROUNDING)


def short_weeks(c, kind):
    return {e["week"] for e in c["by_week"] if e["short"] > TOL_LB and e["kind"] == kind}


def test_contracts_are_short_where_the_toy_said_and_bind_where_they_can(fx):
    """FX.3: kale's weeks 36-37 and spinach's 35-36 are FACTS (no harvest can reach them — the
    toy's finding, reproduced), spinach also shorts by CHOICE at $0.50, and the asparagus
    must-deliver is filled to the pound in every week. Every penalty dollar is in the P&L."""
    c1, c2, c3 = (by_id(fx, "contracts", c) for c in ("c1", "c2", "c3"))
    assert short_weeks(c1, "fact") == {36, 37} and c1["short_kind"] == "fact"
    assert short_weeks(c2, "fact") == {35, 36} and c2["short_kind"] == "mixed"
    assert short_weeks(c2, "choice")
    assert c3["mode"] == "deliver" and c3["short_lbs"] == 0
    assert all(e["delivered"] == pytest.approx(e["owed"], abs=TOL_LB) for e in c3["by_week"])
    penalties = c1["penalty_cost"] + c2["penalty_cost"]
    assert penalties > 0
    assert fx["bought_capacity_split"]["contract_shortfall"] == pytest.approx(penalties)


# ---------------------------------------------------------------------------
# What each entry costs (§6.3), and the toy-vs-app cross-check the shapes allow
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def deltas(fx):
    """One with/without re-solve per entry (~5 s each): the co-pilot's 'why' primitive. This
    re-solves the base plan too (~5 s the `fx` fixture already spent) — the price of keeping the
    pin and liveness tests fast under `-m "not slow"`."""
    r = solve_optimal(fx_farm(commitment_deltas=True))
    assert r["profit"] == pytest.approx(fx["profit"], abs=pnl_tolerance("profit"))
    return {d["id"]: d for d in r["commitment_deltas"]}


@pytest.mark.slow
def test_every_entry_is_priced_and_the_floors_cost_more_than_the_noise(deltas):
    """A patch the must-deliver contract depends on cannot be removed: its 'without' solve is
    infeasible, and the table says so instead of inventing a number (UI wording: BACKLOG X15)."""
    assert set(deltas) == set(BY_ID) | {"carry-in:Garlic"}
    assert deltas["p1"]["status"] == "infeasible" and deltas["p1"]["delta"] is None
    for cid in set(deltas) - {"p1"}:
        assert deltas[cid]["status"] == "optimal" and deltas[cid]["tolerance"] > 0, cid
    for cid in ("k1", "k2", "c3", "carry-in:Garlic"):
        assert deltas[cid]["delta"] > deltas[cid]["tolerance"], (
            f"{cid} costs ${deltas[cid]['delta']:,.0f}, inside ${deltas[cid]['tolerance']:,.0f} of "
            f"solver noise — it is not binding here and the pin says nothing about it")


@pytest.mark.slow
def test_the_toys_asparagus_contract_costs_the_same_in_the_app(deltas):
    """The one with/without figure both models can state for the SAME object: the 3-ac patch,
    its two channels and the 500 lb/wk must-deliver are identical in toy_v12_lp.py and here, and
    nothing else on either farm touches asparagus. So the contract's cost is self-contained and
    derivable by hand — the pounds pulled off the farmers market at the price gap, less the
    packaging saved, less the overhead that revenue would have carried — and the toy's exact
    figure, the hand figure and the app's delta must agree. ⚠️ Two models agreeing proves only
    that they agree (FX.2's lesson); the hand derivation is the third leg."""
    lp = load_toy_lp()
    toy_card, toy_c3 = lp.CROPS["Asparagus"], next(c for c in lp.CONTRACTS if c.mode == "deliver")
    assert toy_card["channels"] == ASPARAGUS["channels"]
    assert toy_card["yield_per_acre"] == P1["yield_per_acre"]
    assert (toy_c3.gid, toy_c3.channel, toy_c3.lb, toy_c3.first, toy_c3.last) == (
        C3["crop"], C3["channel"], C3["lb_per_week"], C3["from_week"], C3["to_week"])
    assert [b["acres"] for b in lp.PERENNIAL_BLOCKS if b["bearing"]] == [P1["acres"]]

    with_c3 = lp.solve()
    without = lp.solve(contracts=[c for c in lp.CONTRACTS if c.mode != "deliver"])
    toy_delta = without["obj_value"] - with_c3["obj_value"]

    ch, weeks = ASPARAGUS["channels"], C3["to_week"] - C3["from_week"] + 1
    market_cap = ch["Farmers Market"]["demand_ranges"][0]["weekly_lbs"] * weeks        # 2,400 lb
    diverted = market_cap - TO_MARKET                                                  # 1,150 lb
    assert diverted > 0
    price_gap = ch["Farmers Market"]["price_per_lb"] - ch["Wholesale"]["price_per_lb"]
    packaging_saved = ch["Farmers Market"]["packaging_cost_per_lb"] - ch["Wholesale"]["packaging_cost_per_lb"]
    hand = diverted * (price_gap * (1 - FX_PAYLOAD["overhead_pct_of_revenue"]) - packaging_saved)
    assert toy_delta == pytest.approx(hand, abs=0.01), f"toy ${toy_delta:,.2f} vs hand ${hand:,.2f}"

    app = deltas["c3"]
    assert app["tolerance"] < hand / 2, "the app's noise is too large for this comparison to mean anything"
    assert app["delta"] == pytest.approx(hand, abs=app["tolerance"]), (
        f"app ${app['delta']:,.0f} ± {app['tolerance']:,.0f} vs toy/hand ${hand:,.2f}")
