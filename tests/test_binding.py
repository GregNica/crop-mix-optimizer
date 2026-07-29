"""
Binding-behavior tests — squeeze a constraint and assert the plan responds: profit strictly
drops and the constraint sits at its cap. The audit (Part 7) flagged that constraint families
lacked tests that make them BIND, so a cap could silently go slack (e.g. wired to 1e9)
unnoticed.

COVERAGE, so completeness stays auditable (SPEC_v3 §10 wants a squeeze/relax pair per family):
    land ............ here
    harvest storage . tests/test_inventory.py::TestStorageBindsOnHeldStock
    shelf life ...... tests/test_inventory.py::TestShelfLife
    water ........... here (TestWaterBinds)
    labor ........... NOT COVERED — needs a demand-rich fixture, see below
    cash / diversity  NOT COVERED

Storage moved out when SPEC_v3 §3 replaced C4 with an inventory balance: the quantity changed
from harvest inflow to stock actually held, so those tests were replaced rather than
relocated, and they need helpers that live with the inventory core.

The subtlety that keeps biting: several caps are BILLED (harvest storage is charged per m³ of
capacity, irrigation scales with total_land), so "bigger cap -> more profit" is false and a
squeeze test passes for the wrong reason. Zero the RATE to isolate the CONSTRAINT. Likewise
set sell_through_fraction explicitly — the shared fixture omits it, so it defaults to 1.0 and
any guard on that factor is inert. Both were found by mutation testing, not by reading.

At the fixture's 150-acre scale the plan is DEMAND-limited, so labor sits slack; a labor
binding test needs a scaled-up, demand-rich scenario and is left as a follow-up rather than
shipped flaky.
"""
import pytest
from farm_v2.solver import solve_farm_v2
from farm_v2.utils.calendar import build_phase_table

# Zeroing the BILLED rates is what makes a cap a pure constraint: harvest storage is charged
# per m³ of capacity and irrigation scales with total_land, so with the rates live "bigger cap
# -> more profit" is false and a squeeze test would pass for the wrong reason. That is exactly
# how a 5,000 m³ default sat inert and unnoticed for months.
_FREE_RATES = dict(rate_irrigation=0.0, rate_harvest_storage=0.0, well_weekly_cap_L=1e12)

# Land tests: storage freed too, so land is the only active constraint.
_FREE = {**_FREE_RATES, "harvest_storage_cap": 1e9}



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


class TestWaterBinds:
    """C3. Until 2026-07-29 this family had NO binding test anywhere, and the constraint was
    mathematically incapable of binding: crop water rates were ~10x below evapotranspiration, so
    the 65% rainfall offset exceeded every crop's need and net irrigation was identically zero.
    A whole constraint family sat present, costed, and decorative for the life of the app.

    That is the failure this class exists to make impossible to repeat: squeeze the well and the
    plan must respond. It does NOT assert that water binds on the shipped farm — it should not,
    a well is sized with headroom — only that the row is capable of biting when supply is short,
    which is exactly what was untrue before.
    """

    # NOTE: capacity_series, not weekly_water_used — the latter is the JS adapter's key and
    # reading it here returns [] silently, which made this test "detect" a vacuous constraint
    # that was not there. A guard that fails for the wrong reason is still a broken guard.
    def _params(self, full_params, well_L):
        p = dict(full_params)
        p["well_weekly_cap_L"] = well_L
        p["city_water_enabled"] = False        # no second tap to escape through
        return p

    def test_squeezing_the_well_squeezes_the_plan(self, full_params):
        roomy = solve_farm_v2(**self._params(full_params, 1e12))
        assert roomy["status"] == "optimal"
        peak_need = max(roomy["capacity_series"]["water"]["used"] or [0])
        assert peak_need > 0, (
            "the plan uses NO water at any point — net irrigation is zero, which is the "
            "vacuous-constraint state this test exists to detect"
        )

        tight = solve_farm_v2(**self._params(full_params, peak_need * 0.5))
        assert tight["status"] == "optimal"
        # A single week may legitimately draw MORE than that week's inflow by emptying the
        # tank (B7) — that is what a tank is for. What must hold is the row as solved: draw
        # never exceeds the week's supply, which is inflow plus the tank's opening level.
        # Comparing against the well cap alone was only correct while storage banked nothing.
        used = tight["capacity_series"]["water"]["used"] or [0]
        cap  = tight["capacity_series"]["water"]["cap"] or [0]
        over = [w for w, (u, c) in enumerate(zip(used, cap), start=1) if u > c * (1 + 1e-6) + 1e-6]
        assert not over, (
            f"weeks {over} drew more water than they had available (inflow + opening tank) — "
            f"C3 is not enforced"
        )
        assert tight["profit"] < roomy["profit"], (
            f"halving the well changed nothing (profit {tight['profit']:,.0f} vs "
            f"{roomy['profit']:,.0f}) — the water constraint is slack at any supply, so it "
            f"cannot be steering the plan"
        )
