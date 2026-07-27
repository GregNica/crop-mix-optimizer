"""
Binding-behavior tests — squeeze a constraint and assert the plan responds:
profit strictly drops and the constraint sits at its cap. The audit (Part 7)
flagged that constraint families lacked tests that make them BIND, so a cap
could silently go slack (e.g. wired to 1e9) unnoticed.

Two subtleties handled here:
  1. Several caps are BILLED (harvest storage is charged per m³ of capacity;
     irrigation scales with total_land), so "bigger cap -> more profit" is false —
     the cost confounds it. We zero the relevant cost RATE to isolate the CONSTRAINT.
  2. At the fixture's 150-acre scale the plan is DEMAND-limited, so labor sits slack
     (more of it doesn't change the plan). Land and harvest storage bind cleanly;
     the labor binding test needs a scaled-up, demand-rich scenario and is left as a
     follow-up rather than shipped flaky.
"""
import pytest
from farm_v2.solver import solve_farm_v2
from farm_v2.utils.calendar import build_phase_table, harvest_weeks_of

# Zeroing the BILLED rates is what makes a cap a pure constraint: harvest storage is charged
# per m³ of capacity and irrigation scales with total_land, so with the rates live "bigger cap
# -> more profit" is false and a squeeze test would pass for the wrong reason. That is exactly
# how a 5,000 m³ default sat inert and unnoticed for months.
_FREE_RATES = dict(rate_irrigation=0.0, rate_harvest_storage=0.0, well_weekly_cap_L=1e12)

# Land tests: storage freed too, so land is the only active constraint.
_FREE = {**_FREE_RATES, "harvest_storage_cap": 1e9}

# Storage tests: sell_through is set explicitly because the shared fixture omits it, so it
# defaults to 1.0 and the sell-through factor in C4's coefficient becomes INERT — a guard
# written against that fixture passes with the factor deleted from the solver. 0.85 is the
# shipped default. Found by mutation-testing this file, which is the only reason it is not
# still true. (Cannot spread _FREE here: the tests pass harvest_storage_cap explicitly.)
_STORAGE_FREE = {**_FREE_RATES, "sell_through_fraction": 0.85}


def _solve(full_params, **overrides):
    r = solve_farm_v2(**{**full_params, **overrides})
    assert r["status"] == "optimal", f"expected optimal, got {r['status']} for {overrides}"
    return r


def _peak_land_fraction(r):
    x, succs = r["x"], r["successions"]
    table = build_phase_table(succs, n_weeks=52)
    return max(
        sum(x[i] for i in range(len(succs)) if table[i][w] is not None)
        for w in range(1, 53)
    )


class TestLandBinds:
    def test_more_land_more_profit_when_constrained(self, full_params):
        tight  = _solve(full_params, total_land=40.0, **_FREE)
        looser = _solve(full_params, total_land=90.0, **_FREE)
        assert looser["profit"] > tight["profit"], (
            "in the land-constrained regime (irrigation free), more land must yield more "
            f"profit; got 40ac={tight['profit']:.0f} vs 90ac={looser['profit']:.0f}"
        )

    def test_land_sits_at_cap_when_squeezed(self, full_params):
        r = _solve(full_params, total_land=40.0, **_FREE)
        peak = _peak_land_fraction(r)
        assert peak > 0.9, (
            f"land squeezed to 40ac should be near-fully planted at peak, got fraction {peak:.3f}"
        )

    def test_relaxing_recovers(self, full_params):
        tight  = _solve(full_params, total_land=40.0, **_FREE)
        looser = _solve(full_params, total_land=90.0, **_FREE)
        assert _peak_land_fraction(looser) <= _peak_land_fraction(tight) + 1e-9, (
            "relaxing the land cap should leave peak utilization no higher (more slack)"
        )


def _peak_storage_m3(r, land):
    """Peak weekly harvest volume, recomputed independently of the solver's own arrays.

    The volume formula is deliberately NOT read off a result key. A binding guard has to
    assert that the constraint the solver enforced agrees with a physical quantity derived
    some other way; reading a series the solver built from the same coefficients would
    assert a == a. This repo has shipped exactly that test before — one that compared two
    parses of the same value, both zero, and certified a bug as correct.

    `sell_through` is the one input echoed back off the result rather than re-supplied by
    the caller: it is a scalar the solver was handed, not a number it derived, so quoting
    it twice creates a way for helper and solve to disagree without creating independence.
    """
    x, succs, crops = r["x"], r["successions"], r["crops"]
    sell_through = r["sell_through_fraction"]
    weekly = [0.0] * 53
    for i, s in enumerate(succs):
        if x[i] <= 1e-9:
            continue
        crop = crops[s["crop"]]
        harv = harvest_weeks_of(s)
        if not harv:
            continue
        st_c = crop.get("sell_through_fraction", sell_through)
        per_week = (st_c * x[i] * land * crop["yield_per_acre"]
                    * crop["crop_size_m3_per_lb"] / len(harv))
        for w in harv:
            weekly[w] += per_week
    return max(weekly)


@pytest.fixture(scope="module")
def loose_storage(full_params):
    """The unconstrained plan and its own peak weekly volume — the yardstick every
    squeeze in this class is measured against. Module-scoped over the session-scoped
    `full_params` because the squeezed solve costs ~0.46s (a binding C4 forces real
    branch-and-bound where the slack case relaxes at the root) and three tests want it."""
    r = _solve(full_params, harvest_storage_cap=1e9, **_STORAGE_FREE)
    return r, _peak_storage_m3(r, full_params["total_land"])


@pytest.fixture(scope="module")
def squeezed_storage(full_params, loose_storage):
    """The same plan with the cap halved below its own peak. Shared by the two tests
    that assert on it."""
    _, peak = loose_storage
    cap = peak * 0.5
    return cap, _solve(full_params, harvest_storage_cap=cap, **_STORAGE_FREE)


class TestHarvestStorageBinds:
    """C4 — the harvest-storage cap.

    Guards the 2026-07-27 correction: the coefficient must be ONE WEEK's SELLABLE harvest
    volume, not the whole season's physical yield charged in every harvest week. Two details
    below were each found by mutation-testing and each silently disarmed the whole class
    before that — the explicit sell_through in _STORAGE_FREE, and the 2% margin. Preserve
    both through any rewrite of this file.
    """

    def test_squeezing_storage_costs_profit(self, loose_storage, squeezed_storage):
        loose, peak = loose_storage
        cap, tight  = squeezed_storage
        assert tight["profit"] < loose["profit"], (
            f"halving the storage cap below the plan's own {peak:,.0f} m³ peak must cost "
            f"profit; got tight={tight['profit']:,.0f} vs loose={loose['profit']:,.0f}. "
            "If these are equal the cap is not reaching the constraint matrix at all."
        )

    def test_squeezed_storage_sits_at_its_cap(self, full_params, squeezed_storage):
        cap, tight = squeezed_storage
        used = _peak_storage_m3(tight, full_params["total_land"])
        assert used <= cap * 1.0001, (
            f"storage use {used:,.1f} m³ exceeds the {cap:,.1f} m³ cap — the row is not enforced"
        )
        assert used > cap * 0.95, (
            f"storage squeezed to {cap:,.1f} m³ should sit near its cap, got {used:,.1f} m³"
        )

    def test_coefficient_is_one_week_not_the_whole_season(self, full_params, loose_storage):
        """The regression guard proper.

        A crop harvested over N weeks must fit a cap sized for one week's volume. Under the
        pre-fix coefficient (whole-season yield charged in every harvest week, sell-through
        omitted) the same plan needed N/sell_through times the space, so this solve came back
        with less acreage or a lower profit.
        """
        loose, peak = loose_storage
        # 2%, not 20%. The margin must be TIGHTER than the smallest error it has to catch, and
        # the smaller of the two factors is sell-through: dropping it inflates the row by
        # 1/0.85 = 1.176x. A 20% margin swallowed that exactly — mutation-testing caught this
        # guard passing with the sell-through factor deleted from the solver.
        sized = _solve(full_params, harvest_storage_cap=peak * 1.02, **_STORAGE_FREE)
        assert sized["profit"] == pytest.approx(loose["profit"], rel=1e-6), (
            f"a cap 2% above the plan's {peak:,.0f} m³ peak must be slack, but profit moved "
            f"{loose['profit']:,.0f} -> {sized['profit']:,.0f}. That means C4 is charging more "
            "than one week's sellable harvest — check the /n_harv_weeks divisor and the "
            "sell-through factor."
        )
