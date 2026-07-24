"""
Accounting-identity tests — pin the money so a cost line can't silently double-count,
vanish, or land in the wrong bucket (audit Part 7 item 3). Complements test_regression
(which pins magnitudes) by pinning the STRUCTURE of the P&L:

    operating_profit = revenue - (fixed + variable + city_water + overtime + hire)
    overhead_cost    = overhead_pct * revenue          (overhead appears exactly once)
    profit (net)     = operating_profit - overhead_cost - interest_cost

Run with non-zero overhead + interest so those terms are actually exercised (the
default full_params fixture zeroes them).
"""
import pytest
from farm_v2.solver import solve_farm_v2

OVERHEAD_PCT = 0.15
INTEREST_APR = 0.07


@pytest.fixture(scope="module")
def result_with_realism(full_params):
    params = {**full_params,
              "overhead_pct_of_revenue": OVERHEAD_PCT,
              "interest_rate_apr": INTEREST_APR}
    r = solve_farm_v2(**params)
    assert r["status"] == "optimal"
    return r


class TestAccountingIdentities:
    def test_operating_profit_equals_revenue_minus_enumerated_costs(self, result_with_realism):
        r = result_with_realism
        enumerated = (r["fixed_cost"] + r["variable_cost"] + r["city_water_cost"]
                      + r["overtime_cost"] + r["hire_cost"])
        assert r["operating_profit"] == pytest.approx(r["revenue"] - enumerated, abs=1.0), (
            "operating_profit must equal revenue minus exactly the enumerated cost lines "
            "(fixed + variable + city_water + overtime + hire) — a mismatch means a cost "
            "line is missing, doubled, or unbucketed."
        )

    def test_overhead_appears_exactly_once_and_proportional(self, result_with_realism):
        r = result_with_realism
        assert r["overhead_cost"] == pytest.approx(OVERHEAD_PCT * r["revenue"], rel=1e-6), (
            "overhead_cost must be exactly overhead_pct x revenue (charged once, in one place)."
        )

    def test_net_profit_is_operating_minus_overhead_and_interest(self, result_with_realism):
        r = result_with_realism
        expected = r["operating_profit"] - r["overhead_cost"] - r["interest_cost"]
        assert r["profit"] == pytest.approx(expected, abs=1.0), (
            "net profit must be operating_profit - overhead - interest (the honest headline)."
        )

    def test_interest_nonnegative(self, result_with_realism):
        assert result_with_realism["interest_cost"] >= 0.0

    def test_all_cost_lines_nonnegative(self, result_with_realism):
        r = result_with_realism
        for k in ("fixed_cost", "variable_cost", "city_water_cost",
                  "overtime_cost", "hire_cost", "overhead_cost"):
            assert r[k] >= -1e-6, f"{k} is negative ({r[k]}) — costs should never be negative"


class TestOverheadInterestOffToggle:
    def test_zero_overhead_and_interest_collapse_to_operating(self, full_params):
        """With overhead=interest=0, net profit == operating profit (no phantom deductions)."""
        r = solve_farm_v2(**{**full_params,
                             "overhead_pct_of_revenue": 0.0,
                             "interest_rate_apr": 0.0})
        assert r["overhead_cost"] == pytest.approx(0.0, abs=1e-9)
        assert r["interest_cost"] == pytest.approx(0.0, abs=1e-9)
        assert r["profit"] == pytest.approx(r["operating_profit"], abs=1.0)

    def test_higher_overhead_reduces_net_profit(self, full_params):
        """Sanity: raising overhead strictly lowers net profit (monotone, exercised end-to-end)."""
        lo = solve_farm_v2(**{**full_params, "overhead_pct_of_revenue": 0.05})["profit"]
        hi = solve_farm_v2(**{**full_params, "overhead_pct_of_revenue": 0.20})["profit"]
        assert hi < lo, "more overhead should mean less net profit"
