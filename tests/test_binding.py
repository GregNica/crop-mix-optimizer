"""
Binding-behavior tests — squeeze a constraint and assert the plan responds:
profit strictly drops and the constraint sits at its cap. The audit (Part 7)
flagged that constraint families lacked tests that make them BIND, so a cap
could silently go slack (e.g. wired to 1e9) unnoticed.

Two subtleties handled here:
  1. Several caps are BILLED (harvest storage is charged per m³ of capacity;
     irrigation scales with total_land), so "bigger cap -> more profit" is false —
     the cost confounds it. We zero the relevant cost RATE to isolate the CONSTRAINT.
  2. At the fixture's 150-acre scale the plan is DEMAND-limited, so storage/labor
     sit slack (more of them doesn't change the plan). Land is the constraint that
     cleanly binds here; storage/labor binding tests need a scaled-up, demand-rich
     scenario and are left as a follow-up rather than shipped flaky.
"""
import pytest
from farm_v2.solver import solve_farm_v2
from farm_v2.utils.calendar import build_phase_table

# rate_irrigation=0 removes the land-scaled fixed cost; the other caps are freed so land
# is the only active constraint. Then land purely affects the CONSTRAINT, not cost.
_FREE = dict(rate_irrigation=0.0, harvest_storage_cap=1e9, rate_harvest_storage=0.0,
             well_weekly_cap_L=1e12)


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
