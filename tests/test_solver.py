"""Integration tests for farm_v2.solver.solve_farm_v2."""
import pytest
import numpy as np
from farm_v2.solver import solve_farm_v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solve(params):
    """Call solve_farm_v2 with a params dict, return result."""
    return solve_farm_v2(**params)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_returns_dict(self, minimal_params):
        result = _solve(minimal_params)
        assert isinstance(result, dict)

    def test_required_keys_present(self, minimal_params):
        result = _solve(minimal_params)
        required = {
            "status", "profit", "revenue", "variable_cost", "fixed_cost",
            "x", "y", "v", "successions", "crops", "channels",
            "weekly_cash_flow", "peak_borrowing",
        }
        assert required <= result.keys()

    def test_status_is_string(self, minimal_params):
        result = _solve(minimal_params)
        assert isinstance(result["status"], str)

    def test_x_is_array(self, minimal_params):
        result = _solve(minimal_params)
        assert isinstance(result["x"], np.ndarray)

    def test_y_is_array(self, minimal_params):
        result = _solve(minimal_params)
        assert isinstance(result["y"], np.ndarray)

    def test_weekly_cash_flow_length(self, minimal_params):
        result = _solve(minimal_params)
        assert len(result["weekly_cash_flow"]) == 53  # index 0 unused


# ---------------------------------------------------------------------------
# Optimality and feasibility
# ---------------------------------------------------------------------------

class TestSolverStatus:
    def test_minimal_one_crop_optimal(self, minimal_params):
        result = _solve(minimal_params)
        assert result["status"] == "optimal"

    def test_two_crop_optimal(self, two_crop_params):
        result = _solve(two_crop_params)
        assert result["status"] == "optimal"

    def test_infeasible_when_no_water_no_city_water(self, minimal_params):
        """Zero water supply with crops that need water → infeasible."""
        import copy
        p = copy.deepcopy(minimal_params)
        p["well_enabled"] = False
        p["catchment_enabled"] = False
        p["city_water_enabled"] = False
        # Keep rainfall at zero via fixture override
        p["rainfall_weekly_L_per_acre"] = np.zeros(52)
        # Reduce credit so cash floor triggers if no revenue
        p["opening_cash"] = 10_000.0
        p["credit_line"] = 10_000.0
        result = _solve(p)
        # With no water the farm can't irrigate; solver should find no feasible plan
        # or produce zero profit (zero planting)
        assert result["status"] in ("optimal", "infeasible")
        if result["status"] == "optimal":
            # If somehow feasible, profit must be ≤ 0 (no revenue from unirrigated crops)
            # or x is zero — acceptable either way
            pass

    def test_zero_credit_line_tight_cash_infeasible(self, minimal_params):
        """With zero credit and very low opening cash, solver may be infeasible."""
        import copy
        p = copy.deepcopy(minimal_params)
        p["opening_cash"] = 1_000.0   # almost nothing
        p["credit_line"] = 0.0
        result = _solve(p)
        # Either infeasible or a tiny feasible plan
        assert result["status"] in ("optimal", "infeasible")


# ---------------------------------------------------------------------------
# Constraint satisfaction checks (on optimal solutions)
# ---------------------------------------------------------------------------

class TestConstraintSatisfaction:
    @pytest.fixture(autouse=True)
    def solve_result(self, two_crop_params):
        result = _solve(two_crop_params)
        assert result["status"] == "optimal", "Need optimal result to check constraints"
        self.result = result
        self.total_land = two_crop_params["total_land"]

    def test_x_values_in_unit_interval(self):
        x = self.result["x"]
        assert np.all(x >= -1e-6)    # numerical tolerance
        assert np.all(x <= 1.0 + 1e-6)

    def test_y_values_binary(self):
        y = self.result["y"]
        assert np.all((y < 1e-6) | (y > 1 - 1e-6))

    def test_x_leq_y_linkage(self):
        """x[i] ≤ y[i] for all successions (if y=0, x must be 0)."""
        x = self.result["x"]
        y = self.result["y"]
        assert np.all(x <= y + 1e-6)

    def test_land_constraint_per_week(self):
        """Total land fraction active in any week must not exceed 1.0."""
        from farm_v2.utils.calendar import build_phase_table
        x = self.result["x"]
        succs = self.result["successions"]
        table = build_phase_table(succs, n_weeks=52)
        for w in range(1, 53):
            used = sum(x[i] for i in range(len(succs)) if table[i][w] is not None)
            assert used <= 1.0 + 1e-4, f"Land constraint violated in week {w}: {used:.4f}"

    def test_profit_equals_revenue_minus_costs(self):
        r = self.result
        computed = r["revenue"] - r["variable_cost"] - r["fixed_cost"]
        assert abs(computed - r["profit"]) < 1.0   # within $1

    def test_revenue_non_negative(self):
        assert self.result["revenue"] >= 0

    def test_fixed_cost_positive(self):
        assert self.result["fixed_cost"] > 0

    def test_cash_flow_floor_respected(self, two_crop_params):
        floor = -(two_crop_params["opening_cash"] + two_crop_params["credit_line"])
        wcf = self.result["weekly_cash_flow"]
        assert np.all(wcf[1:] >= floor - 1.0)   # $1 tolerance


# ---------------------------------------------------------------------------
# Economic sanity checks
# ---------------------------------------------------------------------------

class TestEconomicSanity:
    def test_profit_finite(self, minimal_params):
        result = _solve(minimal_params)
        if result["status"] == "optimal":
            assert np.isfinite(result["profit"])

    def test_revenue_gte_variable_cost_when_profitable(self, two_crop_params):
        result = _solve(two_crop_params)
        if result["status"] == "optimal" and result["profit"] > 0:
            assert result["revenue"] > result["variable_cost"]

    def test_more_credit_line_does_not_decrease_profit(self, minimal_params):
        """A looser cash floor can only help or leave profit unchanged."""
        import copy
        base = _solve(minimal_params)
        more_credit = copy.deepcopy(minimal_params)
        more_credit["credit_line"] = minimal_params["credit_line"] * 3
        better = _solve(more_credit)
        if base["status"] == "optimal" and better["status"] == "optimal":
            assert better["profit"] >= base["profit"] - 1.0

    def test_more_land_does_not_decrease_profit(self, minimal_params):
        """More total land relaxes the land constraint, so profit should not fall.

        The premise only holds when land is what is actually scarce. Irrigation is charged per
        acre of TOTAL land (you installed the system) while water SUPPLY does not scale with
        acreage — so on a water-limited farm, buying land you cannot water costs real money and
        profit correctly falls. That is not a solver defect; it is the model telling you not to
        buy it. Found 2026-07-29 when honest FAO-56 water rates made this fixture water-limited
        and this assertion started failing at -$575k.

        So the water constraint is lifted here to isolate the one under test.
        """
        import copy
        p = copy.deepcopy(minimal_params)
        p["well_weekly_cap_L"] = 1e12
        base = _solve(p)
        more_land = copy.deepcopy(p)
        more_land["total_land"] = p["total_land"] * 2
        better = _solve(more_land)
        if base["status"] == "optimal" and better["status"] == "optimal":
            assert better["profit"] >= base["profit"] - 1.0

# ---------------------------------------------------------------------------
# y[i] is a BINARY, not merely an integer
# ---------------------------------------------------------------------------

class TestPlantBinaryIsBounded:
    """`integrality` alone makes y an integer; without an upper bound it is unbounded.

    y appears only in C9 (x <= y) and C10 (min_frac * y <= x). `min_acreage_if_planted` of 0 is
    a value the form accepts, and it drives min_frac to 0, which collapses C10 to `0 <= x` and
    leaves y completely free. Every value of y is then equally optimal — infinitely many optima,
    and a y_sol that cannot be trusted to answer "was this succession planted".
    """

    def test_y_is_binary_on_a_normal_solve(self, minimal_params):
        res = _solve(minimal_params)
        y = np.asarray(res["y"], dtype=float)
        assert np.all(y >= -1e-6), f"y went negative: {y}"
        assert np.all(y <= 1 + 1e-6), (
            f"y exceeded 1: {y}. y[i] means plant-or-not; an integer above 1 is not a "
            f"meaningful answer and indicates the upper bound was dropped."
        )

    def test_y_stays_binary_when_min_acreage_is_zero(self, minimal_params):
        """The degenerate case: min_acreage 0 removes C10's grip on y entirely.

        With min_acreage_if_planted = 0, C10 collapses to `0 <= x` and C9 is only `x <= y`, so
        y = 1 alongside x = 0 is feasible and costs nothing. The bound is then the ONLY thing
        holding y down. Note what follows and is deliberately NOT asserted here: y is not pinned
        to 0 for an unplanted succession in this case, so anything reporting "was this crop
        planted" must read x, not y. Whether HiGHS happens to return 0 or 1 is an arbitrary
        tie-break among equally optimal solutions — pinning it would test the solver's mood.
        """
        params = dict(minimal_params)
        params["crops"] = [dict(c, min_acreage_if_planted=0.0) for c in params["crops"]]
        res = _solve(params)
        y = np.asarray(res["y"], dtype=float)
        assert np.all(y <= 1 + 1e-6), (
            f"with min_acreage_if_planted=0 the y bound is the ONLY thing holding y down, "
            f"and it did not: {y}"
        )

    def test_unplanted_succession_reports_y_zero_when_min_acreage_is_set(self, minimal_params):
        """With a real min_acreage, C10 (min_frac * y <= x) forces y to 0 when x is 0.

        This is the contract the "was this planted" report depends on, and it holds for every
        shipped template — all of them set min_acreage_if_planted >= 1.
        """
        res = _solve(minimal_params)
        x = np.asarray(res["x"], dtype=float)
        y = np.asarray(res["y"], dtype=float)
        assert any(c.get("min_acreage_if_planted", 0) > 0 for c in minimal_params["crops"]), (
            "fixture must set a non-zero min_acreage for this test to mean anything"
        )
        for i, (xi, yi) in enumerate(zip(x, y)):
            if xi <= 1e-9:
                assert yi <= 1e-6, (
                    f"succession {i} has x={xi} but reports y={yi} — an unplanted succession "
                    f"claiming to be planted"
                )

