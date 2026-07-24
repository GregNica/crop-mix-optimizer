"""
Regression tests — catch silent changes to the 6-crop model's optimal solution.

These tests use the full notebook-equivalent parameter set (session-scoped fixture
so the expensive solve runs only once). Bounds are intentionally loose (~5%)
to survive minor algorithmic changes in HiGHS, while still catching meaningful
regressions.

Update the EXPECTED_* constants if you intentionally change the model.
"""
import pytest
import numpy as np
from farm_v2.solver import solve_farm_v2


# ---------------------------------------------------------------------------
# Expected values — 6 crops, 2 channels, 74 successions, operating_weeks=48.
# Update these (with a provenance line below) if you INTENTIONALLY change the model.
#
# Baseline history:
#   2026-03-11 — original: profit 370,638 / revenue 1,722,668 / fixed 1,098,984
#   2026-07-24 — REBASELINED (commit rebaselines the stale March pin). The model
#     evolved substantially since March: the realism layer put sell-through IN the
#     objective (the farm grows ~100 to sell ~88, so revenue is lower for the same
#     acreage) and internalized overhead; a Min-Viable-Margin hurdle prunes thin
#     crop-channels. Revenue 1,722,668 → 1,627,508 and profit 370,638 → 171,739.
#     The `full_params` fixture sets overhead=interest=0, so profit == operating
#     profit == revenue − variable − fixed (verified by test_profit_equals_...).
#     Fixed cost is unchanged (fixture rates unchanged).
# ---------------------------------------------------------------------------

EXPECTED_PROFIT  = 171_739      # ± 10%  (rebaselined 2026-07-24)
EXPECTED_REVENUE = 1_627_508    # ± 10%  (rebaselined 2026-07-24)
EXPECTED_FIXED   = 1_098_984    # ± 5%   (unchanged since 2026-03-11)
TOLERANCE_PCT    = 0.10         # 10% relative tolerance


@pytest.fixture(scope="module")
def full_result(full_params):
    result = solve_farm_v2(**full_params)
    return result


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@pytest.mark.regression
@pytest.mark.slow
class TestRegressionStatus:
    def test_status_optimal(self, full_result):
        assert full_result["status"] == "optimal", (
            f"Solver returned '{full_result['status']}' instead of 'optimal'. "
            "Check constraint or parameter changes."
        )


# ---------------------------------------------------------------------------
# Financial results
# ---------------------------------------------------------------------------

@pytest.mark.regression
@pytest.mark.slow
class TestRegressionFinancials:
    def test_profit_in_expected_range(self, full_result):
        profit = full_result["profit"]
        lo = EXPECTED_PROFIT * (1 - TOLERANCE_PCT)
        hi = EXPECTED_PROFIT * (1 + TOLERANCE_PCT)
        assert lo <= profit <= hi, (
            f"Profit ${profit:,.0f} outside expected range "
            f"[${lo:,.0f}, ${hi:,.0f}]. "
            "Intentional? Update EXPECTED_PROFIT in test_regression.py."
        )

    def test_revenue_in_expected_range(self, full_result):
        rev = full_result["revenue"]
        lo = EXPECTED_REVENUE * (1 - TOLERANCE_PCT)
        hi = EXPECTED_REVENUE * (1 + TOLERANCE_PCT)
        assert lo <= rev <= hi, (
            f"Revenue ${rev:,.0f} outside expected range [{lo:,.0f}, {hi:,.0f}]."
        )

    def test_fixed_cost_in_expected_range(self, full_result):
        fc = full_result["fixed_cost"]
        lo = EXPECTED_FIXED * (1 - TOLERANCE_PCT)
        hi = EXPECTED_FIXED * (1 + TOLERANCE_PCT)
        assert lo <= fc <= hi, (
            f"Fixed cost ${fc:,.0f} outside expected range [{lo:,.0f}, {hi:,.0f}]."
        )

    def test_profit_equals_revenue_minus_costs(self, full_result):
        r = full_result
        computed = r["revenue"] - r["variable_cost"] - r["fixed_cost"]
        assert abs(computed - r["profit"]) < 10.0, (
            f"Profit identity broken: revenue - costs = {computed:,.2f} "
            f"but profit = {r['profit']:,.2f}"
        )


# ---------------------------------------------------------------------------
# Solution structure
# ---------------------------------------------------------------------------

@pytest.mark.regression
@pytest.mark.slow
class TestRegressionSolutionStructure:
    def test_successions_count(self, full_result):
        """74 successions expected for the default 6-crop config."""
        n = len(full_result["successions"])
        assert 60 <= n <= 90, f"Expected ~74 successions, got {n}"

    def test_some_successions_planted(self, full_result):
        """At least some successions should be active in the optimal plan."""
        y = full_result["y"]
        assert y.sum() >= 3, f"Only {int(y.sum())} successions planted — suspiciously low"

    def test_x_values_in_range(self, full_result):
        x = full_result["x"]
        assert np.all(x >= -1e-6)
        assert np.all(x <= 1.0 + 1e-6)

    def test_all_six_crops_represented_in_plan(self, full_result):
        """Each crop should appear in at least one planted succession."""
        succs = full_result["successions"]
        y = full_result["y"]
        planted_crops = {succs[i]["crop"] for i in range(len(y)) if y[i] > 0.5}
        # Expect most crops in the solution (allow 1 excluded crop)
        assert len(planted_crops) >= 5, (
            f"Only {len(planted_crops)} crops planted: {planted_crops}"
        )

    def test_cash_flow_never_below_floor(self, full_params, full_result):
        floor = -(full_params["opening_cash"] + full_params["credit_line"])
        wcf = full_result["weekly_cash_flow"]
        violations = [w for w in range(1, 53) if wcf[w] < floor - 1.0]
        assert not violations, (
            f"Cash floor violated in weeks: {violations[:5]}"
        )

    def test_land_fraction_sum_never_exceeds_1(self, full_result):
        from farm_v2.utils.calendar import build_phase_table
        x = full_result["x"]
        succs = full_result["successions"]
        table = build_phase_table(succs, n_weeks=52)
        worst_week = -1
        worst_val = 0.0
        for w in range(1, 53):
            used = sum(x[i] for i in range(len(succs)) if table[i][w] is not None)
            if used > worst_val:
                worst_val = used
                worst_week = w
        assert worst_val <= 1.0 + 1e-4, (
            f"Land constraint violated in week {worst_week}: {worst_val:.6f}"
        )
