"""
DEMAND SATURATION — how full each crop-channel's market is (W6).

WHAT THIS GUARDS. `demand_saturation` answers "how much of this buyer's appetite did the plan
fill, and is their cap what stops me selling more". It feeds the constraint-summary panel, the
What-If bottleneck ranking, and the constraint CSV.

WHY IT EXISTS. The client used to compute it as

    sat = min(1, gross annual harvest / this channel's annual cap)

with a numerator covering the crop's harvest across EVERY channel. Measured on the shipped demo
farm: 10 of 14 crop-channel rows overstated by more than 10 points, and three rows sold ZERO lb
while reporting 29%, 16% and 4% — printed beside a channel pie, built from `channel_sales`,
showing those channels selling nothing.

WHY THE OBVIOUS FIX IS ALSO WRONG, and the reason this module exists rather than a one-line
numerator swap. Reporting pounds SOLD on the annual basis alone reads Garlic/Farmers Market at
50% on the demo farm, and that row is at its weekly ceiling in every week it sells at all: the
cap is 2,000 lb/wk across W22-W35 and the garlic is not lifted until W29, so half the capped
weeks are unservable. The old formula said 100% and was right by accident; "50%" is a NEW wrong
answer, and it would have dropped the farm's tightest demand cap out of the What-If ranking.

So each figure is measured against the row the solver actually enforces:

  * `fill`           pounds sold / the year's total cap        (C6 summed, or C6b)
  * `peak_week_frac` max over weeks of sold / that week's cap  (C6; None when there is no
                     weekly row at all, i.e. an annual contract)
  * `binding`        the utilisation of whichever row exists — the ranking's basis

TestStorageCarry is the load-bearing class: it pins a crop-channel whose annual fill is low
while its weekly cap binds, which is the case that makes reporting one figure alone a defect.
"""
import copy

import pytest

from farm_v2.solver import solve_farm_v2
from tests.helpers import (
    SATURATION_KEYS,
    expand_weekly_caps,
    saturation_entries,
    solved_once,
)


# ---------------------------------------------------------------------------
# A farm shaped like the garlic case: a bulk channel that makes the crop worth
# planting, plus a small premium channel whose weekly cap opens long before the
# crop can be harvested.
# ---------------------------------------------------------------------------

# A channel that is never worth selling into: packaging costs more than the price, so every
# pound sold here loses money and the optimizer sells none. The cap is real and positive, which
# is exactly the row that used to report a saturation anyway. Shared by the crop that IS planted
# (its zero-sales row) and the crop that is not (the omission gate), so the two cannot drift.
_LOSS_LEADER = {
    "price_per_lb": 0.10,
    "packaging_cost_per_lb": 5.00,
    "demand_cap_type": "weekly_flat",
    "weekly_demand_lbs": 50_000,
}


@pytest.fixture
def carry_params(two_crop_params, spinach_crop):
    """The shared two-crop farm, re-channelled into the garlic case.

    DERIVED from `two_crop_params` rather than copied. 26 of its 29 keys were identical, and the
    conftest header records why that matters: those infrastructure rates were found wrong on
    2026-07-29 (water ~10x low, so the water constraint could not bind in any fixture) and fixed
    in conftest only. A hand-rolled copy does not receive the next such correction.
    """
    crop = copy.deepcopy(spinach_crop)
    crop["channels"] = {
        # Bulk: effectively uncapped, low price. Pays for the acreage.
        "Wholesale": {
            "price_per_lb": 1.00,
            "packaging_cost_per_lb": 0.05,
            "demand_cap_type": "weekly_flat",
            "weekly_demand_lbs": 1_000_000,
        },
        # Premium: pays triple, but takes only 200 lb/wk and its window (W1-W52) is open for
        # months before this crop is harvestable at all. This is the garlic shape.
        "Market": {
            "price_per_lb": 3.00,
            "packaging_cost_per_lb": 0.05,
            "demand_cap_type": "weekly_varying",
            "demand_ranges": [{"weeks": "W1-W52", "weekly_lbs": 200}],
        },
        "Loss Leader": dict(_LOSS_LEADER),
    }
    # A crop that will never be planted: its only outlet loses money on every pound. Present so
    # the "unplanted crops are omitted" gate is exercised — without it that test passes on a farm
    # where every crop IS planted, and the mutation deleting the gate survived exactly that way.
    never_planted = copy.deepcopy(spinach_crop)
    never_planted["name"] = "Radish"
    never_planted["channels"] = {"Loss Leader": dict(_LOSS_LEADER)}

    p = copy.deepcopy(two_crop_params)
    p.update(
        harvest_storage_cap=5_000.0,          # room to carry the premium channel's stock
        crops=[crop, never_planted],
        channels=[{"name": "Wholesale"}, {"name": "Market"}, {"name": "Loss Leader"}],
    )
    return p


@pytest.fixture
def carry(carry_params):
    return solved_once("carry", carry_params)


@pytest.fixture
def two(solved_two_crop):
    return solved_two_crop


# The flatten helper and the entry key set live in conftest — both are asserted from more than
# one module, and a second copy is how one of them comes to lag the contract.
_entries = saturation_entries


class TestStructure:
    def test_returned_and_non_empty(self, carry):
        res, _ = carry
        assert res["demand_saturation"], "no saturation reported — the fixture cannot pin anything"

    def test_channels_and_crops_are_real(self, carry):
        res, params = carry
        names = {c["name"] for c in params["channels"]}
        crops = {c["name"] for c in params["crops"]}
        for ch, cp, _e in _entries(res):
            assert ch in names, f"unknown channel {ch!r}"
            assert cp in crops, f"unknown crop {cp!r}"

    def test_every_entry_is_complete(self, carry):
        res, _ = carry
        for ch, cp, e in _entries(res):
            assert set(e) == SATURATION_KEYS, f"{ch}/{cp} keys: {sorted(set(e) ^ SATURATION_KEYS)}"
            assert e["basis"] in ("weekly", "annual")

    def test_fractions_are_in_range(self, carry):
        res, _ = carry
        for ch, cp, e in _entries(res):
            assert 0.0 <= e["fill"] <= 1.0, f"{ch}/{cp} fill={e['fill']}"
            assert 0.0 <= e["binding"] <= 1.0, f"{ch}/{cp} binding={e['binding']}"
            if e["peak_week_frac"] is not None:
                assert 0.0 <= e["peak_week_frac"] <= 1.0
            assert all(1 <= w <= 52 for w in e["weeks_at_cap"]), e["weeks_at_cap"]
            assert e["weeks_at_cap"] == sorted(set(e["weeks_at_cap"]))


class TestAgreesWithChannelSales:
    """The two reports come off the same `v`, so they must not be able to disagree.

    `channel_sales` drives the pies, the sales CSV and the P&L channel lines; this drives the
    saturation panel. The whole point of W1 and W6 is that those are one number.
    """

    def test_sold_lbs_matches_channel_sales(self, carry):
        res, _ = carry
        cs = res["channel_sales"]
        for ch, cp, e in _entries(res):
            sold = cs.get(ch, {}).get("by_crop", {}).get(cp, {}).get("lbs_sold", 0.0)
            assert sold == pytest.approx(e["sold_lbs"], abs=1e-6), f"{ch}/{cp}"

    def test_a_channel_absent_from_channel_sales_sold_nothing(self, carry):
        res, _ = carry
        cs = res["channel_sales"]
        for ch, cp, e in _entries(res):
            if cp not in cs.get(ch, {}).get("by_crop", {}):
                assert e["sold_lbs"] == 0.0, (
                    f"{ch}/{cp} reports {e['sold_lbs']} lb sold but does not appear in "
                    f"channel_sales — the pies would show nothing beside it"
                )


class TestGrossHarvestIsNotTheNumerator:
    """The specific defect W6 names.

    Gross harvest is derived here from planted acreage x yield, independently of anything the
    saturation code touches — the W1 lesson about tests that are true by algebra.
    """

    def test_a_channel_with_no_sales_reads_zero(self, carry):
        res, params = carry
        e = res["demand_saturation"]["Loss Leader"]["Spinach"]
        acres = res["crop_contribution"]["Spinach"]["acres_planted"]
        gross = acres * params["crops"][0]["yield_per_acre"]
        assert acres > 0 and gross > 0, "the crop must be planted for this to mean anything"
        assert e["sold_lbs"] == 0.0
        assert e["fill"] == 0.0 and e["binding"] == 0.0, (
            f"a channel the plan sells nothing into reads {e['fill']:.0%}. The old formula "
            f"divided the crop's whole {gross:,.0f} lb harvest by this channel's cap and "
            f"printed a saturation for a channel with no sales in it"
        )
        assert e["cap_lbs"] > 0, "the row is only interesting because the cap is real"

    def test_gross_harvest_would_have_overstated_it(self, carry):
        res, params = carry
        acres = res["crop_contribution"]["Spinach"]["acres_planted"]
        gross = acres * params["crops"][0]["yield_per_acre"]
        e = res["demand_saturation"]["Market"]["Spinach"]
        old = min(1.0, gross / e["cap_lbs"])
        assert old > e["fill"], (
            f"the fixture no longer distinguishes the two bases (gross {gross:,.0f} lb vs sold "
            f"{e['sold_lbs']:,.0f} lb against a {e['cap_lbs']:,.0f} lb cap) — it cannot pin W6"
        )

    def test_sold_never_exceeds_gross_harvest(self, carry):
        res, params = carry
        acres = res["crop_contribution"]["Spinach"]["acres_planted"]
        gross = acres * params["crops"][0]["yield_per_acre"]
        total_sold = sum(e["sold_lbs"] for _ch, _cp, e in _entries(res))
        assert total_sold <= gross + 1e-6, f"sold {total_sold:,.0f} > grown {gross:,.0f}"


class TestStorageCarry:
    """A low annual fill and a binding weekly cap are not a contradiction.

    This is the garlic case. The premium channel's window is open all year at 200 lb/wk, but
    this crop cannot be harvested until well into the season, so most of those capped weeks are
    unservable and the annual fill is low — while in every week it CAN supply, it sells the cap
    out exactly. Reporting only the annual figure would call this slack.
    """

    def test_weekly_cap_binds_while_annual_fill_is_low(self, carry):
        res, _ = carry
        e = res["demand_saturation"]["Market"]["Spinach"]
        assert e["basis"] == "weekly"
        assert e["peak_week_frac"] == pytest.approx(1.0, abs=1e-6), (
            "the premium channel should sell out its weekly cap when product is available"
        )
        assert e["fill"] < 0.9, (
            f"fill is {e['fill']:.2f} — the fixture no longer has unservable capped weeks, so "
            f"it cannot pin the case where the two figures diverge"
        )
        assert e["weeks_at_cap"], "weeks at cap is the evidence that makes a low fill readable"
        assert e["binding"] == pytest.approx(e["peak_week_frac"]), (
            "the ranking must use the WEEKLY row for a weekly cap, or it drops a binding "
            "constraint whose annual figure looks slack"
        )

    def test_weeks_at_cap_are_exactly_the_weeks_that_sell_the_cap(self, carry):
        """Checked for EVERY weekly channel, against caps expanded independently.

        Pinning only the premium channel was a false green: it sells either its full 200 lb or
        nothing, so no threshold between 0 and 100% can be distinguished on that data alone.
        The bulk channel runs at a few percent, which is what makes the threshold observable.
        """
        res, params = carry
        crop = params["crops"][0]
        checked = 0
        for ch, cp, e in _entries(res):
            if e["basis"] != "weekly" or cp != crop["name"]:
                continue
            caps = dict(expand_weekly_caps(crop["channels"][ch]))
            weekly = (res["channel_sales"].get(ch, {}).get("by_crop", {})
                      .get(cp, {}).get("weekly_lbs") or [0.0] * 52)
            want = sorted(w for w, cap in caps.items() if weekly[w - 1] >= 0.95 * cap)
            assert e["weeks_at_cap"] == want, (
                f"{ch}/{cp}: flagged {e['weeks_at_cap']} but the weeks selling >=95% of their "
                f"own cap are {want}"
            )
            checked += 1
        assert checked >= 2, f"only {checked} weekly channels checked — need a saturated one and a slack one"


class TestAnnualContracts:
    """An annual cap has no weekly row, so no weekly ceiling may be reported.

    Filling `annual/52` into a weekly array is the fiction B4 removed from the solver and the
    panel kept printing: a 100,000 lb contract harvested over 10 weeks showed 100% peak-weekly
    with ten weeks flagged red, against a limit the solver does not impose.
    """

    def test_annual_basis_reports_no_peak_week(self, two):
        res, _ = two
        annual = [(ch, cp, e) for ch, cp, e in _entries(res) if e["basis"] == "annual"]
        assert annual, "the two-crop fixture should have an annual-cap channel (Cucumbers/Direct)"
        for ch, cp, e in annual:
            assert e["peak_week_frac"] is None, f"{ch}/{cp} invented a weekly ceiling"
            assert e["weeks_at_cap"] == [], f"{ch}/{cp} flagged weeks against a nonexistent row"
            assert e["binding"] == pytest.approx(e["fill"]), (
                f"{ch}/{cp}: with only C6b to enforce, the yearly fill IS the binding figure"
            )

    def test_annual_cap_is_the_contract_volume(self, two):
        res, params = two
        cucumber = next(c for c in params["crops"] if c["name"] == "Cucumbers")
        want = float(cucumber["channels"]["Direct"]["annual_demand_lbs"])
        e = res["demand_saturation"]["Direct"]["Cucumbers"]
        assert e["cap_lbs"] == pytest.approx(want)


class TestWhatIsOmitted:
    def test_unplanted_crops_are_absent(self, carry):
        """`unplanted_crops` explains an absent crop; 0% rows for it are noise.

        Asserts the fixture actually HAS an unplanted crop first. Without that this passed on a
        farm where every crop was planted, and the mutation that deletes the gate survived.
        """
        res, params = carry
        planted = {n for n, c in res["crop_contribution"].items()
                   if c["acres_planted"] > 1e-6}
        absent = [c["name"] for c in params["crops"] if c["name"] not in planted]
        assert absent, "no crop went unplanted — this test cannot detect a missing gate"
        # ...and it would have produced a row: the cap is real, only the sales are zero.
        assert any(float(sp.get("weekly_demand_lbs") or sp.get("annual_demand_lbs") or 0) > 0
                   for name in absent
                   for sp in next(c for c in params["crops"] if c["name"] == name)["channels"].values())
        for ch, cp, _e in _entries(res):
            assert cp in planted, f"{ch}/{cp}: crop is not in the plan"

    def test_hurdle_excluded_channels_are_absent(self, carry_params):
        """A channel the margin hurdle dropped can sell nothing, so it has no saturation.

        Its weekly caps are zeroed before the solve, which is what makes it drop out here.
        """
        p = copy.deepcopy(carry_params)
        p["min_viable_margin_pct"] = 50.0
        res = solve_farm_v2(**p)
        assert res["status"] == "optimal", res.get("status")
        excluded = {(e["crop"], e["channel"]) for e in res["excluded_channels"]}
        assert excluded, "the hurdle excluded nothing — this test would be vacuous"
        for ch, cp, _e in _entries(res):
            assert (cp, ch) not in excluded, f"{cp}/{ch} was excluded but still has a saturation"

    def test_a_hurdle_excluded_ANNUAL_contract_is_absent(self, carry_params):
        """The one case where "is there an annual row?" and "is there an annual cap?" differ.

        The hurdle zeroes a channel's weekly caps before the solve, and C6b then SKIPS its annual
        row because it could never bind. So a hurdle-excluded annual channel has an entry in
        `annual_caps` and no enforced row anywhere — and reporting it on the annual basis would
        publish a fat contract volume for a channel that can sell nothing.

        This is why the basis is read off `annual_rows`, recorded where C6b builds the rows,
        rather than re-derived from `annual_caps`. Every other fixture here is weekly-capped, so
        without an annual channel in the excluded set the two predicates are indistinguishable
        and the refactor is unguarded — a mutation back to the old form passed 19 tests.
        """
        p = copy.deepcopy(carry_params)
        p["crops"][0]["channels"]["Contract"] = {
            "price_per_lb": 0.20,          # below any sane margin floor
            "packaging_cost_per_lb": 0.05,
            "demand_cap_type": "annual",
            "annual_demand_lbs": 400_000,
        }
        p["channels"] = list(p["channels"]) + [{"name": "Contract"}]
        p["min_viable_margin_pct"] = 50.0
        res = solve_farm_v2(**p)
        assert res["status"] == "optimal", res.get("status")
        excluded = {(e["crop"], e["channel"]) for e in res["excluded_channels"]}
        assert ("Spinach", "Contract") in excluded, (
            "the hurdle did not exclude the annual contract — this test would be vacuous"
        )
        assert "Spinach" not in res["demand_saturation"].get("Contract", {}), (
            "a hurdle-excluded ANNUAL contract still reports a saturation; it has no enforced "
            "row at all, so any figure for it is invented"
        )

    def test_a_crop_channel_with_no_cap_is_absent(self, carry_params):
        """A zero cap is not a market; reporting 0/0 as a percentage is worse than silence."""
        p = copy.deepcopy(carry_params)
        p["crops"][0]["channels"]["Market"]["demand_ranges"] = [
            {"weeks": "W1-W52", "weekly_lbs": 0}
        ]
        res = solve_farm_v2(**p)
        assert res["status"] == "optimal", res.get("status")
        assert "Spinach" not in res["demand_saturation"].get("Market", {})


class TestCapMatchesWhatIsEnforced:
    def test_overlapping_ranges_accumulate(self, carry_params):
        """Two buyers wanting the same weeks are two caps, not one (S7).

        The client's own cap builder ASSIGNED here, so a W1-W20 contract with a W10-W15 top-up
        silently lost the contract's volume for those six weeks. That builder is deleted; this
        pins the surviving one.
        """
        p = copy.deepcopy(carry_params)
        p["crops"][0]["channels"]["Market"]["demand_ranges"] = [
            {"weeks": "W1-W20", "weekly_lbs": 1_000},
            {"weeks": "W10-W15", "weekly_lbs": 500},
        ]
        res = solve_farm_v2(**p)
        assert res["status"] == "optimal", res.get("status")
        e = res["demand_saturation"]["Market"]["Spinach"]
        assert e["cap_lbs"] == pytest.approx(20 * 1_000 + 6 * 500)

    def test_weekly_flat_cap_is_the_year(self, carry):
        res, params = carry
        want = float(params["crops"][0]["channels"]["Wholesale"]["weekly_demand_lbs"]) * 52
        assert res["demand_saturation"]["Wholesale"]["Spinach"]["cap_lbs"] == pytest.approx(want)

    def test_peak_week_cap_is_one_week_not_the_year(self, carry):
        """`peak_week_cap_lbs` labels the What-If lever, so it must be a WEEK's ceiling.

        Reporting `cap_lbs` here would put the year's total behind a "/wk cap" label — the same
        shape of untrue label as the `annual/52` figure this field exists to replace.
        """
        res, params = carry
        e = res["demand_saturation"]["Market"]["Spinach"]
        one_week = dict(expand_weekly_caps(params["crops"][0]["channels"]["Market"]))
        assert e["peak_week_cap_lbs"] == pytest.approx(200.0)
        assert e["peak_week_cap_lbs"] == pytest.approx(one_week[e["weeks_at_cap"][0]])
        assert e["peak_week_cap_lbs"] < e["cap_lbs"], (
            f"a single week's cap ({e['peak_week_cap_lbs']:,.0f}) cannot equal the year's "
            f"({e['cap_lbs']:,.0f}) — the fixture must span more than one capped week"
        )

    def test_the_reported_cap_matches_the_week_that_binds(self, carry):
        """Whichever week is tightest, that week's cap is the one published."""
        res, params = carry
        caps = dict(expand_weekly_caps(params["crops"][0]["channels"]["Wholesale"]))
        e = res["demand_saturation"]["Wholesale"]["Spinach"]
        weekly = (res["channel_sales"].get("Wholesale", {}).get("by_crop", {})
                  .get("Spinach", {}).get("weekly_lbs") or [0.0] * 52)
        tightest = max(range(1, 53), key=lambda w: weekly[w - 1] / caps[w])
        assert e["peak_week_cap_lbs"] == pytest.approx(caps[tightest])

    def test_sales_never_exceed_the_reported_cap(self, carry):
        res, _ = carry
        for ch, cp, e in _entries(res):
            assert e["sold_lbs"] <= e["cap_lbs"] + 1e-6, (
                f"{ch}/{cp} sold {e['sold_lbs']:,.1f} against a reported cap of "
                f"{e['cap_lbs']:,.1f} — the cap published is not the cap enforced"
            )
