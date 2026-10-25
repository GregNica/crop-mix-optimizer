"""FX.5 — variants: a crop grown a second way and sold as the first (SPEC_batchFX §3, §5 ruling 3).

"Tunnel Spinach" has its own windows, yield, zone and minimum, and sells AS Spinach: the same
buyers, prices, caps, labour and diversity allowance. Measured in the app before the fix, keyed
by crop name: the two sold 12,000 lb/wk into Farmers Market's 6,000 lb in 10 weeks and profit
read $757,459; with one market per identity it is $705,841 (the golden farm, $652,876, is
untouched — it has no variants, the L4 trap, hence this fixture).
"""
import copy

import pytest

from farm_v2.solver import DEMAND_AT_CAP_FRACTION
from farm_v2.utils.variants import INHERITED_KEYS, identity_groups, resolve_variants
from tests.helpers import (expand_weekly_caps, golden_payload, saturation_entries,
                           solve_payload as solve, solve_payload_optimal as solve_optimal)

SPINACHES = ("Spinach", "Tunnel Spinach")


def golden_crop(name):
    return next(c for c in golden_payload()["crops"] if c["name"] == name)


# Spinach's Farmers Market weekly ceiling (6,000 lb/wk, W10–W48), read from the payload through
# the independent oracle so a re-pinned golden demand cannot leave this guard measuring a stale number.
FM_CAP = max(c for _, c in expand_weekly_caps(golden_crop("Spinach")["channels"]["Farmers Market"]))


def variant_of(parent, **own):
    """`parent` with every inherited field left out (the variant takes them) and `own` applied."""
    return {**{k: v for k, v in copy.deepcopy(parent).items() if k not in INHERITED_KEYS}, **own}


def variant_farm(**spinach):
    """Golden farm + a covered 2-ac tunnel growing a year-round Tunnel Spinach sold as Spinach.

    `spinach` overrides the PARENT, which the variant then inherits."""
    p = golden_payload(zones=[{"name": "High tunnel", "acres": 2, "covered": True},
                              {"name": "Open field"}])
    parent = next(c for c in p["crops"] if c["name"] == "Spinach")
    parent.update(spinach)
    p["crops"].append(variant_of(
        parent, name="Tunnel Spinach", sells_as="Spinach", zones=["High tunnel"],
        yield_per_acre=6500, min_acreage_if_planted=0.25,
        seasons=[{"start": "01-10", "end": "12-10"}]))
    return p


@pytest.fixture(scope="module")
def base():
    return solve_optimal(variant_farm())


def weekly(r, channel, crop):
    return (r["channel_sales"].get(channel, {}).get("by_crop", {}).get(crop, {})
            .get("weekly_lbs") or [0.0] * 52)


def acre_weeks(r, crops):
    return sum(s["acres"] * len(s["weeks"]) for s in r["succession_schedule"] if s["crop"] in crops)


# ---------------------------------------------------------------------------
# resolve_variants — the one place a variant takes its parent's fields
# ---------------------------------------------------------------------------

PARENT = {"name": "Spinach", "channels": {"FM": {"price_per_lb": 2.75}}, "crop_diversity_max": 0.5,
          "labor_harv": 50, "cold_storage": True, "yield_per_acre": 5000}


class TestResolveVariants:
    def test_omitted_inherited_fields_are_the_parents(self):
        _, v = resolve_variants([PARENT, {"name": "T", "sells_as": "Spinach", "yield_per_acre": 6500}])
        assert v["channels"] == PARENT["channels"] and v["labor_harv"] == 50
        assert v["crop_diversity_max"] == 0.5 and v["cold_storage"] is True
        assert v["yield_per_acre"] == 6500                 # growing fields stay the variant's

    def test_the_parents_value_sent_again_is_fine_and_resolving_twice_is_a_no_op(self):
        once = resolve_variants([PARENT, {**PARENT, "name": "T", "sells_as": "Spinach"}])
        assert resolve_variants(once) == once

    def test_the_inherited_copy_is_not_shared_with_the_parent(self):
        _, v = resolve_variants([PARENT, {"name": "T", "sells_as": "Spinach"}])
        assert v["channels"] is not PARENT["channels"]

    def test_inputs_are_not_mutated(self):
        variant = {"name": "T", "sells_as": "Spinach"}
        resolve_variants([PARENT, variant])
        assert variant == {"name": "T", "sells_as": "Spinach"}

    @pytest.mark.parametrize("key, value", [
        ("channels", {"FM": {"price_per_lb": 3.0}}),       # a second price is a second product
        ("crop_diversity_max", 0.9),
        ("labor_harv", 20),
        ("cold_storage", False),
        ("shelf_life_weeks", 4),                           # the parent leaves it out: still a 2nd value
    ])
    def test_a_different_inherited_value_is_refused_by_name(self, key, value):
        with pytest.raises(ValueError, match=f"takes Spinach's {key}"):
            resolve_variants([PARENT, {"name": "T", "sells_as": "Spinach", key: value}])

    @pytest.mark.parametrize("sells_as, match", [
        ("Kale", "not one of the farm's crops"),
        ("T", "sells as itself"),
        ("", "must name a crop"),
        (["Spinach"], "must name a crop"),
    ])
    def test_a_bad_parent_is_refused(self, sells_as, match):
        with pytest.raises(ValueError, match=match):
            resolve_variants([PARENT, {"name": "T", "sells_as": sells_as}])

    def test_no_chains(self):
        with pytest.raises(ValueError, match="Point it at 'Spinach' directly"):
            resolve_variants([PARENT, {"name": "T", "sells_as": "Spinach"},
                              {"name": "U", "sells_as": "T"}])

    def test_identity_groups_put_a_variant_with_its_parent(self):
        crops = resolve_variants([{"name": "K"}, {"name": "T", "sells_as": "Spinach"}, PARENT])
        assert identity_groups(crops) == {0: [0], 2: [1, 2]}


# ---------------------------------------------------------------------------
# The solve — one market, one diversity allowance, one saturation row per identity
# ---------------------------------------------------------------------------

class TestOneMarketPerIdentity:
    def test_the_variant_is_planted_in_its_zone_and_sells_into_the_shared_channel(self, base):
        """Else every guard below is inert: a variant selling nothing cannot overfill a cap."""
        rows = [s for s in base["succession_schedule"] if s["crop"] == "Tunnel Spinach"]
        assert rows and {s["zone"] for s in rows} == {"High tunnel"}
        assert sum(weekly(base, "Farmers Market", "Tunnel Spinach")) > 1000

    def test_both_names_together_fit_the_weekly_cap_and_it_binds(self, base):
        both = [a + b for a, b in zip(weekly(base, "Farmers Market", "Spinach"),
                                      weekly(base, "Farmers Market", "Tunnel Spinach"))]
        assert max(both) <= FM_CAP + 1e-6
        assert max(both) >= FM_CAP - 1e-6          # binds — so the row is what holds it

    def test_both_names_together_fit_an_annual_cap_and_it_binds(self):
        # Measured: at 60,000 lb the parent fills it alone and the variant sells none there —
        # an inert fixture. At 300,000 both sell into it (279,272 + 20,728).
        cap = 300000
        channels = golden_crop("Spinach")["channels"]
        fm = {**channels["Farmers Market"], "demand_cap_type": "annual", "annual_demand_lbs": cap}
        r = solve_optimal(variant_farm(channels={**channels, "Farmers Market": fm}))
        lbs = {c: sum(weekly(r, "Farmers Market", c)) for c in SPINACHES}
        assert lbs["Tunnel Spinach"] > 1000
        assert sum(lbs.values()) == pytest.approx(cap, abs=1.0)
        sat = r["demand_saturation"]["Farmers Market"]["Spinach"]
        assert sat["basis"] == "annual" and sat["sold_lbs"] == pytest.approx(cap, abs=1.0)

    def test_the_diversity_allowance_is_shared(self):
        """At 0.1 each NAME alone could take 10% of the farm's acre-weeks; together they get 10%."""
        r = solve_optimal(variant_farm(crop_diversity_max=0.1))
        both = acre_weeks(r, SPINACHES) / (80 * 52)
        assert both <= 0.1 + 1e-3
        assert acre_weeks(r, {"Tunnel Spinach"}) > 0 and both >= 0.1 - 1e-3

    def test_saturation_is_reported_once_under_the_parent_with_both_names_pounds(self, base):
        entries = saturation_entries(base)
        assert all(crop != "Tunnel Spinach" for _, crop, _ in entries)
        for ch, crop, e in entries:
            if crop == "Spinach":
                by_crop = base["channel_sales"][ch]["by_crop"]
                sold = sum(by_crop.get(c, {}).get("lbs_sold", 0.0) for c in SPINACHES)
                assert e["sold_lbs"] == pytest.approx(sold)
        fm = base["demand_saturation"]["Farmers Market"]["Spinach"]
        assert fm["peak_week_frac"] == pytest.approx(1.0)

    def test_weeks_at_cap_count_both_names(self, base):
        """Rebuilt from the sales and the payload's caps, not from the solver's table. Mutant M7
        (the weekly series read off the parent alone) passed every check above, because Spinach
        alone reaches 6,000 lb in some week, so the peak is 1.0 either way. Measured: 31 weeks
        at cap together, 24 for Spinach alone — this is the check that tells them apart."""
        caps = expand_weekly_caps(golden_crop("Spinach")["channels"]["Farmers Market"])
        both = [a + b for a, b in zip(*(weekly(base, "Farmers Market", c) for c in SPINACHES))]
        parent = weekly(base, "Farmers Market", "Spinach")
        at_cap = [w for w, cap in caps if both[w - 1] >= DEMAND_AT_CAP_FRACTION * cap]
        assert at_cap != [w for w, cap in caps if parent[w - 1] >= DEMAND_AT_CAP_FRACTION * cap]
        assert base["demand_saturation"]["Farmers Market"]["Spinach"]["weeks_at_cap"] == at_cap

    def test_the_hurdle_drops_a_name_not_the_market(self):
        """The margin hurdle is per NAME (a variant's costs, so margin, differ). Measured: at a
        66% floor Spinach/Wholesale (65.5%) is dropped and Tunnel Spinach/Wholesale (67.5%) is
        not — the shared row must still offer the variant the market's 25,000 lb, not the
        parent's zeroed copy of it."""
        r = solve_optimal({**variant_farm(), "min_viable_margin_pct": 66})
        dropped = {(e["crop"], e["channel"]) for e in r["excluded_channels"]}
        assert ("Spinach", "Wholesale") in dropped and ("Tunnel Spinach", "Wholesale") not in dropped
        assert sum(weekly(r, "Wholesale", "Spinach")) == 0.0
        assert sum(weekly(r, "Wholesale", "Tunnel Spinach")) > 1000
        assert r["demand_saturation"]["Wholesale"]["Spinach"]["cap_lbs"] > 0

    def test_sales_and_contribution_stay_per_name_and_reconcile(self, base):
        assert "Tunnel Spinach" in base["crop_contribution"]
        lines = sum(cs["revenue"] for cs in base["channel_sales"].values())
        assert lines == pytest.approx(base["revenue"])


class TestRefusalsThroughThePayload:
    def test_a_variant_with_its_own_price_is_refused_not_solved(self):
        p = variant_farm()
        p["crops"][-1]["channels"] = copy.deepcopy(p["crops"][0]["channels"])
        p["crops"][-1]["channels"]["Wholesale"]["price_per_lb"] = 1.5
        r = solve(p)
        assert r["status"] == "invalid_input"
        assert any("takes Spinach's channels" in e for e in r["errors"])

    def test_a_variant_of_an_ambient_crop_that_omits_cold_storage_solves(self):
        """The adapter defaults cold_storage to True; on a variant it must leave it to the parent,
        or a Garlic variant (parent False) is refused for a box the grower never typed."""
        p = golden_payload()
        garlic = next(c for c in p["crops"] if c["name"] == "Garlic")
        assert garlic["cold_storage"] is False
        hardneck = variant_of(garlic, name="Hardneck Garlic", sells_as="Garlic")
        hardneck["committed_acres"] = 0    # its own carry-in (FX.5); 18 + 18 would not fit the crew
        p["crops"].append(hardneck)
        assert solve(p)["status"] == "optimal"

    def test_a_variant_sending_the_parents_raw_spread_is_normalised_alike(self):
        """Sent on both, a raw value is normalised on both (0 → 1), so they still agree."""
        p = variant_farm()
        p["crops"][0]["sales_spread_weeks"] = 0
        p["crops"][-1]["sales_spread_weeks"] = 0
        assert solve(p)["status"] == "optimal"

    def test_a_crop_without_a_name_is_still_refused_not_raised(self):
        """/code-review: identity grouping ran before validation and indexed c["name"], so an
        unnamed crop became a KeyError traceback instead of validation's own refusal."""
        p = golden_payload()
        del p["crops"][0]["name"]
        r = solve(p)
        assert r["status"] == "invalid_input"
        assert any("missing required keys" in e for e in r["errors"])

    def test_duplicate_names_are_refused_before_a_variant_finds_the_wrong_parent(self):
        p = variant_farm()
        # A second "Spinach" card that itself sells as Kale: found by name last-write-wins, it
        # made the variant's refusal "Point it at 'Kale' directly" instead of the real problem.
        p["crops"].append({**p["crops"][1], "name": "Spinach", "sells_as": "Kale"})
        r = solve(p)
        assert r["status"] == "invalid_input"
        assert any("unique" in e for e in r["errors"])

    def test_commitments_sharing_one_diversity_ceiling_are_refused_by_name(self):
        """/code-review, measured: Garlic (0.6 of 80 = 48 ac) and a Hardneck variant at 33.6 ac
        each pass the per-name check and gave a bare HiGHS 'infeasible' against the shared C8."""
        p = golden_payload()
        garlic = next(c for c in p["crops"] if c["name"] == "Garlic")
        garlic["committed_acres"] = 33.6
        p["crops"].append(variant_of(garlic, name="Hardneck Garlic", sells_as="Garlic"))
        r = solve(p)
        assert r["status"] == "invalid_input"
        assert any("share its diversity ceiling of 48 acres" in e for e in r["errors"])
