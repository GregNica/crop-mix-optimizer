"""The P&L cost breakdowns (W4) — the solver's side.

WHAT WAS WRONG. The P&L exporter asked for thirteen flat cost keys (res.cost_seed,
res.cost_harvest_storage, ...). Twelve of them were never returned by anything, so `!= null`
filtered every row away and the statement printed two opaque totals with no detail under
either. The thirteenth, cost_property_mortgage_rent, was gated on `> 0` and is 0 on the shipped
farm — so in practice the breakdown was empty, and had been for the exporter's whole life.

WHY "just export vc_split" WOULD HAVE BEEN WRONG, twice. The backlog named the fix as exporting
the solver's internal `vc_split`. Measured before implementing:

  * vc_split carries the five per-acre growing categories and NOT packaging, which is charged
    per pound sold. Packaging is $119,633 on the shipped farm — 20.5% of variable cost. A
    five-row split would have sat under a total it missed by a fifth.
  * The fixed-cost side is not mentioned by the backlog at all, and it was worse: the exporter
    named eight components while Step 4 charged eleven. $750 of ambient-pool depreciation was
    unaccounted for on the shipped farm, and `other_debt_service_per_week` is a live form field,
    so the gap is unbounded on a farm that uses it.

So the guarded property is not "the keys exist" but THE PARTS SUM TO THE TOTAL — enforced in
the solver by summing each total from its own split, and asserted here on both.

The dict shape is load-bearing and is pinned too: consumers iterate it instead of naming keys,
which is what makes a newly added component appear in the P&L rather than vanish from it.
"""
import numpy as np
import pytest

pytest.importorskip("scipy")

from farm_v2.solver import solve_farm_v2  # noqa: E402


# Every component Step 4 charges. If a new one is added to fixed_cost_split it must be added
# here too — deliberately a hand-listed expectation, because the failure this file exists to
# stop was a hand-listed expectation drifting from the code SILENTLY. Here it drifts loudly.
FIXED_COMPONENTS = {
    "harvest_storage", "ambient_storage", "water_storage", "irrigation", "equipment_storage",
    "fuel_storage", "machinery", "property_mortgage_rent", "other_debt_service", "wages",
    # R7 (Batch 2.2): always present, $0 until entered — a configured-but-zero line is information.
    "land_rent", "ownership_carrying", "insurance", "utilities",
}
# No `labor` (W12): every listed worker is paid for their stated hours whether the crops need them
# or not, so wages are a committed weekly cost and live in fixed_cost_split["wages"].
VARIABLE_COMPONENTS = {"water", "fertilizer", "fuel", "seed", "packaging", "crop_protection"}   # R1


class TestTheTotalsAreSummedFromTheirParts:
    def test_variable_cost_split_sums_to_variable_cost(self, solved_two_crop):
        r, _ = solved_two_crop
        assert set(r["variable_cost_split"]) == VARIABLE_COMPONENTS
        assert sum(r["variable_cost_split"].values()) == pytest.approx(r["variable_cost"], abs=1e-6)

    def test_fixed_cost_split_sums_to_fixed_cost(self, solved_two_crop):
        r, _ = solved_two_crop
        assert set(r["fixed_cost_split"]) == FIXED_COMPONENTS
        assert sum(r["fixed_cost_split"].values()) == pytest.approx(r["fixed_cost"], abs=1e-6)

    def test_packaging_is_in_the_split_and_is_not_in_vc_split(self, solved_two_crop):
        """The trap that made the prescribed one-line fix wrong.

        Packaging is charged per pound SOLD, so it cannot be reached from the per-succession
        vc_split at all. If it ever stops being its own line, the five growing categories will
        silently sit under a total that is larger than they are.
        """
        r, _ = solved_two_crop
        pkg = r["variable_cost_split"]["packaging"]
        assert pkg > 0, "the two-crop fixture prices packaging, so this must be positive"
        # Recomputed from `v` and the crop-channel packaging rates — an INDEPENDENT oracle, not
        # an identity. Asserting `growing == variable_cost - packaging` would have been vacuous:
        # `growing` is defined as the sum of the other five, so it reduces to sum(x) == sum(x)
        # and would pass whatever the solver put in the packaging slot.
        expected = sum(
            float(np.asarray(r["v"])[c, ch, 1:].sum())
            * crop.get("channels", {}).get(ch_def["name"], {}).get("packaging_cost_per_lb", 0.0)
            for c, crop in enumerate(r["crops"])
            for ch, ch_def in enumerate(r["channels"])
        )
        assert pkg == pytest.approx(expected, abs=1e-6)


    def test_seed_carries_seed_and_not_some_other_category(self, solved_two_crop):
        """A category must hold ITS OWN money, not just contribute to a correct total.

        Found by mutation: reversing vc_split's columns after aggregation puts one category's
        dollars under another's label, and every reconciliation test still passed — the sum is
        unchanged, so nothing noticed. A grower would notice immediately ("$300k of seed on 12
        acres"), which is the definition of a number worth pinning.

        Seed is the category that can be rebuilt without reimplementing the solver: it is charged
        once per succession at planting, at total_land x the crop's per-acre seed cost, so it is
        a function of the plan and the crop library alone — no weekly wage or rainfall adjustment.
        """
        r, params = solved_two_crop
        expected = sum(
            float(r["x"][i]) * params["total_land"]
            * r["crops"][s["crop"]].get("seed_transplant_cost_per_acre", 0.0)
            for i, s in enumerate(r["successions"])
            if s["weeks"] and 1 <= s["weeks"][0] <= 52
        )
        assert expected > 0, "the two-crop fixture prices seed, so this must be positive"
        assert r["variable_cost_split"]["seed"] == pytest.approx(expected, abs=1e-6)
        # And the categories are distinct enough that a swap would be visible: if seed happened to
        # equal a neighbour, the assertion above would pass under the very mutation it exists to
        # catch. Compared against every other category rather than one named one, so this keeps
        # working as VC_CATEGORIES changes — it lost `labor` to W12 already.
        for other, value in r["variable_cost_split"].items():
            if other == "seed":
                continue
            assert r["variable_cost_split"]["seed"] != pytest.approx(value, abs=1.0), (
                f"seed and {other} are near-equal on this fixture, so a column swap would be "
                f"invisible here — change the fixture rather than trusting this test"
            )


class TestAComponentCannotGoMissing:
    """A cost charged to a total must appear in that total's split.

    This is the shape of the original defect: money in the total, no row in the breakdown, and
    nothing anywhere that noticed the difference.
    """

    # Each case: the kwargs that switch a component on, the key it must appear under, and the
    # annual cost it must add to BOTH the total and the split. The two cases had identical
    # bodies; the baseline comes from the session-cached solve rather than a third and fourth
    # re-solve of the same unmodified fixture (tests/conftest.py::solved_two_crop exists for
    # exactly that).
    @pytest.mark.parametrize("kwargs,key,delta", [
        ({"other_debt_service_per_week": 1_000.0}, "other_debt_service", 52_000.0),
        # The $750 that the old eight-row breakdown dropped on the shipped farm.
        ({"ambient_storage_cap": 100.0, "rate_ambient_storage": 0.5}, "ambient_storage", 2_600.0),
    ], ids=["other_debt_service", "ambient_pool"])
    def test_a_switched_on_component_lands_in_both(self, solved_two_crop, kwargs, key, delta):
        base, params = solved_two_crop
        r = solve_farm_v2(**dict(params, **kwargs))
        assert r["fixed_cost_split"][key] == pytest.approx(delta)
        assert r["fixed_cost"] == pytest.approx(base["fixed_cost"] + delta)
        assert sum(r["fixed_cost_split"].values()) == pytest.approx(r["fixed_cost"], abs=1e-6)

    def test_a_metered_water_standing_charge_appears_only_when_it_is_charged(self, solved_two_crop):
        """The one conditional component: a key that appears mid-dict is exactly why consumers
        must iterate the split rather than hold a fixed list of keys."""
        off, params = solved_two_crop
        assert "city_water_fixed_fee" not in off["fixed_cost_split"]
        on = solve_farm_v2(**dict(params, city_water_enabled=True,
                                  city_water_cost_per_L=0.001,
                                  city_water_fixed_fee_per_week=25.0))
        assert on["fixed_cost_split"]["city_water_fixed_fee"] == pytest.approx(1_300.0)
        assert sum(on["fixed_cost_split"].values()) == pytest.approx(on["fixed_cost"], abs=1e-6)


# NOT TESTED HERE: "the REPORTED variable cost still equals what the OBJECTIVE charged."
#
# Worth recording why, because the first version of this note gave a wrong reason. It argued the
# test would be `sum(all but packaging) + packaging == sum(all)` and therefore vacuous — but that
# only holds if `var_cost_coeff` (the objective's coefficient) is derived from `vc_split` (the
# reported breakdown). At the time it was NOT: they were parallel hand-maintained accumulators,
# so the identity was real, untested, and exactly what this change had put at risk. A review
# caught the false premise.
#
# The answer was to remove the risk rather than test for it: Step 3 now charges each cost ONCE
# into `vc_weekly_split`, and the objective coefficient, the cash-flow rows and this breakdown
# are three sums of that one array. The two cannot disagree, so the test is circular NOW — for
# the reason the old note only assumed. If they are ever split apart again, this becomes the
# first test to write.
#
# The plan itself not moving is pinned by tests/test_golden_farm.py, against a captured baseline.
