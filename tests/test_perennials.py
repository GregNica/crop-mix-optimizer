"""FX.2 — perennials: committed ground standing all year (SPEC_batchFX §3, §5 ruling 6).

A perennial is a crop card flagged `perennial` plus one BLOCK per planting ("patch") in the
farm-level `commitments` table — acres, this year's yield (0 while establishing), harvest weeks,
and an optional extra cost for that patch alone. Its fertiliser, fuel and crop protection come from
the card like any crop's (grower, 2026-10-25). Each block enters the solver as a PINNED planting
standing weeks 1-52. Before this, the app refused any perennial outright (`calendar.py`: "cycle
exceeds the 52-week planning year"). Yield 1,750 lb/ac from the toy (UKY 2016); the input rates and
the establishing patch's $800 extra are round placeholders.
"""
import copy

import pytest

from tests.helpers import golden_payload, solve_payload as solve, solve_payload_optimal as solve_optimal

ASPARAGUS = dict(
    name="Asparagus", perennial=True, cold_storage=True, crop_size_m3_per_lb=0.0012,
    shelf_life_weeks=2, labor_grow=0.5, labor_harv=5.5, water_grow=100000, water_harv=100000,
    fert_grow=2.0, fert_harv=2.0, fuel_grow=1.0, fuel_harv=3.0, crop_protection_cost_per_acre=150,
    seed_transplant_cost_per_acre=500,      # on the card, and NEVER charged to a block (sunk)
    channels={"Wholesale": {"price_per_lb": 1.75, "packaging_cost_per_lb": 0.15,
                            "demand_cap_type": "weekly_flat", "weekly_demand_lbs": 1500},
              "Farmers Market": {"price_per_lb": 4.00, "packaging_cost_per_lb": 0.30,
                                 "demand_cap_type": "weekly_varying",
                                 "demand_ranges": [{"weeks": "W18-W25", "weekly_lbs": 300}]}})
BEARING = dict(id="c1", kind="perennial", crop="Asparagus", acres=3, planted_year=2019,
               yield_per_acre=1750, harvest_from_week=18, harvest_to_week=25)
ESTABLISHING = dict(id="c2", kind="perennial", crop="Asparagus", acres=1, planted_year=2025,
                    yield_per_acre=0, extra_cost_per_acre=800)
HARVEST = range(18, 26)


def perennial_farm(*blocks, **overrides):
    p = golden_payload(**overrides)
    p["crops"].append(copy.deepcopy(ASPARAGUS))
    p["commitments"] = copy.deepcopy(list(blocks or (BEARING, ESTABLISHING)))
    return p


@pytest.fixture(scope="module")
def base():
    return solve_optimal(perennial_farm())


def block(r, cid):
    return next(b for b in r["perennial_blocks"] if b["id"] == cid)


def block_row(r, cid):
    return next(s for s in r["succession_schedule"] if s["commitment_id"] == cid)


# ---------------------------------------------------------------------------
# The pin: acres are an input, standing every week
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cid, acres", [("c1", 3.0), ("c2", 1.0)])
def test_block_stands_all_year_at_its_acres(base, cid, acres):
    row = block_row(base, cid)
    assert row["acres"] == acres
    assert row["weeks"] == list(range(1, 53))
    assert 0 not in row["phases"]                       # already in the ground: no planting phase


def test_bearing_block_harvests_only_in_its_weeks(base):
    row = block_row(base, "c1")
    assert [w for w, ph in zip(row["weeks"], row["phases"]) if ph == 2] == list(HARVEST)
    assert block(base, "c1")["stage"] == "bearing"


def test_establishing_block_never_harvests(base):
    assert set(block_row(base, "c2")["phases"]) == {1}
    b = block(base, "c2")
    assert (b["stage"], b["sellable_lbs"], b["harvest_weeks"]) == ("establishing", 0.0, [])


def test_blocks_hold_their_land_every_week(base):
    """C1 sees the pin: at least the blocks' 4 acres are standing in every week."""
    assert min(sum(z["used_acres"][w] for z in base["zones"]) for w in range(52)) >= 4.0 - 1e-6


# ---------------------------------------------------------------------------
# Money: this year's cost, never seed; the harvest sold through the channels
# ---------------------------------------------------------------------------

FERT, FUEL = golden_payload()["cost_fert_per_lb"], golden_payload()["cost_fuel_per_L"]
# Per acre per year: 2 lb fert every week; fuel 1 L/wk growing, 3 L/wk harvesting; $150 spray.
BEARING_INPUTS = 52 * 2.0 * FERT + (44 * 1.0 + 8 * 3.0) * FUEL + 150
ESTABLISHING_INPUTS = 52 * 2.0 * FERT + 52 * 1.0 * FUEL + 150


def test_block_cost_is_the_cards_inputs_plus_its_extra(base):
    """Hand-derived from the rates: the block pays the card's fertiliser, fuel and crop
    protection like any crop, plus its own extra — and no seed (water is metered at $0 here)."""
    assert block(base, "c1")["cost"] == pytest.approx(3 * BEARING_INPUTS)
    assert block(base, "c2")["cost"] == pytest.approx(1 * (ESTABLISHING_INPUTS + 800))
    assert base["variable_cost_split"]["perennial_extra"] == pytest.approx(800)


def test_block_inputs_land_in_their_own_columns():
    """Zeroing the card's input rates moves fertiliser, fuel and crop protection by exactly the
    blocks' share — the annual plan is free to move, so the check is on the totals the blocks
    alone account for, read off the two solves' per-block costs."""
    p = perennial_farm()
    p["crops"][-1].update(fert_grow=0, fert_harv=0, fuel_grow=0, fuel_harv=0,
                          crop_protection_cost_per_acre=0)
    bare = solve_optimal(p)
    assert block(bare, "c1")["cost"] == pytest.approx(0.0, abs=1e-9)
    assert block(bare, "c2")["cost"] == pytest.approx(800)


def test_harvest_is_this_years_yield_and_sells(base):
    sold = sum(base["channel_sales"][ch]["by_crop"].get("Asparagus", {}).get("lbs_sold", 0.0)
               for ch in base["channel_sales"])
    assert block(base, "c1")["sellable_lbs"] == pytest.approx(3 * 1750)
    assert sold == pytest.approx(3 * 1750, rel=1e-6)    # the market (1,800 lb/wk) takes it all
    fm = base["channel_sales"]["Farmers Market"]["by_crop"]["Asparagus"]["weekly_lbs"]
    assert all(fm[w - 1] == 0 for w in range(1, 53) if w not in HARVEST)


def test_block_labour_is_its_phases(base):
    assert block(base, "c1")["labor_hours"] == pytest.approx(3 * (44 * 0.5 + 8 * 5.5))
    assert block(base, "c2")["labor_hours"] == pytest.approx(1 * 52 * 0.5)


def test_block_labour_override_beats_the_card():
    r = solve_optimal(perennial_farm(dict(BEARING, labor_grow=1.0), ESTABLISHING))
    assert block(r, "c1")["labor_hours"] == pytest.approx(3 * (44 * 1.0 + 8 * 5.5))


def test_no_commitments_is_the_golden_farm(golden_out):
    """Absent (the golden payload has no key) and an empty table are the same farm."""
    assert golden_out["variable_cost_split"]["perennial_extra"] == 0.0
    assert golden_out["perennial_blocks"] == []
    r = solve_optimal(golden_payload(commitments=[]))
    assert r["profit"] == pytest.approx(golden_out["profit"], abs=0.01)
    assert r["perennial_blocks"] == []


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

TWO_ZONES = [{"name": "High tunnel", "acres": 4, "covered": True}, {"name": "Open field"}]


def test_zone_required_when_the_crop_may_stand_in_several():
    r = solve(perennial_farm(zones=TWO_ZONES))
    assert r["status"] == "invalid_input"
    assert "say which zone" in r["errors"][0]


def test_block_fills_its_zone():
    r = solve_optimal(perennial_farm(dict(BEARING, zone="High tunnel"),
                                     dict(ESTABLISHING, zone="High tunnel"), zones=TWO_ZONES))
    tunnel = next(z for z in r["zones"] if z["name"] == "High tunnel")
    assert min(tunnel["used_acres"]) == pytest.approx(4.0)
    assert block_row(r, "c1")["zone"] == "High tunnel"


# ---------------------------------------------------------------------------
# Refusals — each by name, never a bare "infeasible" or a skipped entry
# ---------------------------------------------------------------------------

def _refused(p, words):
    r = solve(p)
    assert r["status"] == "invalid_input", r.get("status")
    assert any(words in e for e in r["errors"]), r["errors"]


@pytest.mark.parametrize("change, words", [
    (dict(crop="Rhubarb"), "not one of the farm's crops"),
    (dict(crop="Spinach"), "not marked perennial"),
    (dict(acres=0), "acres must be positive"),
    (dict(acres=True), "acres must be positive, got True"),
    (dict(yield_per_acre=None), "yield_per_acre"),
    (dict(extra_cost_per_acre=-5), "extra_cost_per_acre must be a number ≥ 0"),
    (dict(harvest_to_week=None), "harvest_to_week must be a whole week"),
    (dict(harvest_from_week=53), "harvest_from_week must be a whole week"),
    (dict(kind="contract"), "not one of the farm's channels"),
    (dict(kind="orchard"), "unknown kind"),
    (dict(id=""), "needs an id"),
    (dict(source="robot"), "source must be one of"),
    (dict(zone="High tunnel"), "which the farm does not have"),
    (dict(acres=200), "Committed plantings total"),
])
def test_bad_block_is_refused(change, words):
    _refused(perennial_farm(dict(BEARING, **change), ESTABLISHING), words)


def test_unaccepted_suggestion_does_not_bind(base):
    """A co-pilot suggestion is priced by a 'try it' solve that sends it as accepted; until then
    the plan ignores it (grower, 2026-10-25). Accepted binds exactly like typed."""
    plain = solve_optimal(perennial_farm(BEARING))
    suggested = solve_optimal(perennial_farm(BEARING, dict(ESTABLISHING, source="suggested")))
    accepted = solve_optimal(perennial_farm(BEARING, dict(ESTABLISHING, source="accepted")))
    assert [b["id"] for b in suggested["perennial_blocks"]] == ["c1"]
    assert suggested["profit"] == pytest.approx(plain["profit"], abs=0.01)
    assert [b["id"] for b in accepted["perennial_blocks"]] == ["c1", "c2"]
    assert accepted["profit"] == pytest.approx(base["profit"], abs=0.01)     # = typed (`user`)
    assert accepted["profit"] < plain["profit"] - 100


def test_patch_that_cannot_fit_is_named_not_bare_infeasible():
    """A 10-ac patch needing 200 h/ac/wk at harvest exceeds the crew alone; the refusal names the
    committed plantings instead of returning HiGHS's bare 'infeasible'."""
    r = solve(perennial_farm(dict(BEARING, acres=10, labor_harv=200), ESTABLISHING))
    assert r["status"] == "infeasible"
    assert any("Asparagus · planted 2019 (10 ac)" in e and "cannot all be met" in e for e in r["errors"]), r
    assert [b["limit"] for b in r["binding_limits"]] == ["labour"]      # FX.1: and WHICH limit


def test_perennial_card_minimum_is_not_applied_to_its_patches():
    """A card keeping a 5-ac minimum, allowed only in a 3-ac tunnel: its 2-ac patch is valid,
    because a pinned patch has no minimum (C10 skips pins)."""
    p = perennial_farm(dict(BEARING, acres=2, zone="High tunnel"), dict(ESTABLISHING, zone="High tunnel"),
                       zones=[{"name": "High tunnel", "acres": 3, "covered": True}, {"name": "Open field"}])
    p["crops"][-1].update(min_acreage_if_planted=5, zones=["High tunnel"])
    assert sorted(b["acres"] for b in solve_optimal(p)["perennial_blocks"]) == [1.0, 2.0]


def test_perennial_with_only_a_suggested_patch_is_not_committed():
    r = solve_optimal(perennial_farm(dict(BEARING, source="suggested")))
    rec = next(u for u in r["unplanted_crops"] if u["crop"] == "Asparagus")
    assert rec["reason"] == "no_committed_block"


def test_duplicate_id_refused():
    _refused(perennial_farm(BEARING, dict(ESTABLISHING, id="c1")), "used twice")


def test_perennial_crop_without_a_block_refused():
    p = perennial_farm()
    p["commitments"] = []
    _refused(p, "has no block in the commitments table")


@pytest.mark.parametrize("change", [dict(committed_acres=2), dict(overwinters=True)])
def test_perennial_crop_cannot_carry_in(change):
    p = perennial_farm()
    p["crops"][-1].update(change)
    _refused(p, "is perennial, so its ground is its blocks")


def test_block_bigger_than_its_zone_refused():
    _refused(perennial_farm(dict(BEARING, zone="High tunnel", acres=5), dict(ESTABLISHING, zone="Open field"),
                            zones=TWO_ZONES), "can only stand in High tunnel")


def test_annual_with_a_multi_year_cycle_still_refused_with_the_way_out():
    p = golden_payload()
    p["crops"][0]["days_to_maturity"] = 730
    _refused(p, "tick 'perennial' on its card")


# ---------------------------------------------------------------------------
# Guards that need a second condition to bite (the inert-guard lesson): each fixture below is
# built so the mechanism it pins would CHANGE THE ANSWER if it broke, which the default farm
# alone cannot show — the blocks lose money, the card has no diversity cap or minimum, and the
# extra cost is 0 on the bearing block.
# ---------------------------------------------------------------------------

def test_pin_is_a_ceiling_not_just_a_floor():
    """At a premium price more asparagus would pay; the pin must still hold 3 acres (a floor-only
    pin passes every test on the default farm, where the blocks lose money)."""
    p = perennial_farm(BEARING)
    for ch in p["crops"][-1]["channels"].values():
        ch["price_per_lb"] *= 20
        ch.update(demand_cap_type="weekly_flat", weekly_demand_lbs=50_000)
        ch.pop("demand_ranges", None)
    assert block_row(solve_optimal(p), "c1")["acres"] == 3.0


@pytest.mark.parametrize("card, why", [
    (dict(crop_diversity_max=0.01), "diversity cap of 0.8 ac"),
    (dict(min_acreage_if_planted=5), "5-ac minimum planting"),
])
def test_pin_is_exempt_from_rotation_and_lot_size(card, why):
    """Committed ground is neither a rotation choice (C8) nor a lot-size choice (C10): either row
    applied to the 3 + 1 ac blocks would make the plan infeasible."""
    p = perennial_farm()
    p["crops"][-1].update(card)
    r = solve_optimal(p)
    assert sorted(b["acres"] for b in r["perennial_blocks"]) == [1.0, 3.0], why


def test_margin_kernel_weights_bearing_blocks_by_acres():
    """Hand-derived: 3 ac at 1,750 lb and 1 ac at 1,000 lb sell (5,250 + 1,000) / 4 = 1,562.5 lb
    per acre — not the unweighted 1,375. Per-pound cost is what the bearing patches cost over what
    they sell: 4 × inputs / 6,250 lb. (This guard first pinned the plain mean of per-patch ratios,
    which /code-review showed reads $1.69/lb for a true $0.19 with a small young patch.) The
    establishing patch is in neither figure."""
    young = dict(BEARING, id="c3", acres=1, yield_per_acre=1000)
    r = solve_optimal(perennial_farm(BEARING, young, ESTABLISHING))
    m = r["channel_margins"]["Asparagus"]["Wholesale"]
    assert m["sold_lbs_per_acre"] == pytest.approx(1562.5)
    assert m["var_cost_per_lb"] == pytest.approx(4 * BEARING_INPUTS / 6250)


def test_small_young_patch_does_not_inflate_per_pound_cost():
    """The /code-review scenario: a 0.2-ac patch at 100 lb/ac beside the 3-ac bearing one. The
    per-pound cost is the bearing patches' total cost over their sellable pounds, read off the
    solver's own per-patch report."""
    r = solve_optimal(perennial_farm(BEARING, dict(BEARING, id="c3", acres=0.2, yield_per_acre=100),
                                     ESTABLISHING))
    bearing = [b for b in r["perennial_blocks"] if b["stage"] == "bearing"]
    true = sum(b["cost"] for b in bearing) / sum(b["sellable_lbs"] for b in bearing)
    assert r["channel_margins"]["Asparagus"]["Wholesale"]["var_cost_per_lb"] == pytest.approx(true)


def test_margin_tooltip_reconciles_for_a_perennial(base):
    """revenue/acre − cost/acre = margin/acre, as it does for every annual: the split must describe
    the same (bearing) patches the per-pound cost does — establishing extra cost included, it was
    $390/ac apart."""
    for ch, m in base["channel_margins"]["Asparagus"].items():
        assert m["revenue_per_acre"] - m["cost_per_acre"]["total"] == pytest.approx(
            m["margin_per_acre_cycle"]), ch


def test_extra_cost_is_spread_flat_over_the_year():
    """The extra is a constant (pinned acres), so it moves no decision; the cash curve must shift
    by the same 1/52 every week — charged in one week, the yearly totals would still agree."""
    with_extra = solve_optimal(perennial_farm(dict(BEARING, extra_cost_per_acre=520)))
    without = solve_optimal(perennial_farm(BEARING))
    shift = [a - b for a, b in zip(without["weekly_cash_flow"], with_extra["weekly_cash_flow"])]
    assert shift == pytest.approx([3 * 520 / 52 * w for w in range(53)], abs=2)   # [0] = opening


# ---------------------------------------------------------------------------
# Growing season — dormant weeks hold land and use nothing (grower, 2026-10-25)
# ---------------------------------------------------------------------------

SEASON = dict(growing_from_week=14, growing_to_week=40)       # 27 active weeks, harvest 18-25 inside


def season_farm(*blocks, **season):
    p = perennial_farm(*blocks)
    p["crops"][-1].update(season or SEASON)
    return p


@pytest.fixture(scope="module")
def seasonal():
    return solve_optimal(season_farm())


def test_outside_the_season_a_patch_is_dormant(seasonal):
    for cid in ("c1", "c2"):
        row = block_row(seasonal, cid)
        assert [w for w, ph in zip(row["weeks"], row["phases"]) if ph == 3] == \
            list(range(1, 14)) + list(range(41, 53)), cid
    assert [w for w, ph in zip(block_row(seasonal, "c1")["weeks"], block_row(seasonal, "c1")["phases"])
            if ph == 2] == list(HARVEST)


def test_dormant_patch_still_holds_its_land(seasonal):
    assert min(sum(z["used_acres"][w] for z in seasonal["zones"]) for w in range(52)) >= 4.0 - 1e-6


def test_dormant_weeks_use_no_labour(seasonal):
    # bearing: 27 active weeks = 19 grow + 8 harvest; establishing: 27 grow.
    assert block(seasonal, "c1")["labor_hours"] == pytest.approx(3 * (19 * 0.5 + 8 * 5.5))
    assert block(seasonal, "c2")["labor_hours"] == pytest.approx(1 * 27 * 0.5)


def test_dormant_weeks_carry_no_inputs(seasonal):
    """Fertiliser every active week, fuel by phase, the spray over the 19 (or 27) grow weeks — and
    nothing in the 25 dormant ones. The establishing patch's flat extra is a patch cost, not an
    input, so it stays whole."""
    bearing = 27 * 2.0 * FERT + (19 * 1.0 + 8 * 3.0) * FUEL + 150
    establishing = 27 * 2.0 * FERT + 27 * 1.0 * FUEL + 150
    assert block(seasonal, "c1")["cost"] == pytest.approx(3 * bearing)
    assert block(seasonal, "c2")["cost"] == pytest.approx(establishing + 800)


def test_water_readers_skip_dormant_weeks():
    """Direct, because a solve hides it: the app meters water at $0, so only C3 reads it."""
    import numpy as np
    from farm_v2.utils.calendar import DORMANT, GROW
    from farm_v2.utils.water import compute_net_water_rates, rain_coverage
    succ = [{"crop": 0, "weeks": [1, 2], "phases": [DORMANT, GROW]}]
    crop = [{"water_plant": 0, "water_grow": 100.0, "water_harv": 0}]
    rain = np.zeros(52)
    rate = compute_net_water_rates(succ, crop, rain, 0.65)
    assert (rate[0][1], rate[0][2]) == (0.0, 100.0)
    # A DRY dormant week must not count: the growing week is fully rain-watered, so coverage is
    # 1.0 — counted, the dormant week's zero would drag it to 0 and bar the patch rain-fed.
    # (A WET dormant week was this guard's first form, and it was inert: it can only raise a min.)
    rain[1] = 1e6
    assert rain_coverage(succ, crop, rain, 0.65)[0] == 1.0


@pytest.mark.parametrize("season, words", [
    (dict(growing_from_week=14), "give both growing_from_week and growing_to_week"),
    (dict(growing_from_week=20, growing_to_week=40), "outside 'Asparagus's growing season"),
    (dict(growing_from_week=0, growing_to_week=40), "growing_from_week must be a whole week"),
])
def test_bad_season_is_refused(season, words):
    _refused(season_farm(**season), words)
