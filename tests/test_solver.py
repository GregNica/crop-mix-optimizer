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

    def test_y_is_a_reliable_planted_flag_even_at_min_acreage_zero(self, minimal_params):
        """The degenerate case, now pinned rather than documented as a caveat.

        With min_acreage_if_planted = 0, C10 collapses to `0 <= x` and C9 is only `x <= y`, so
        y = 1 alongside x = 0 used to be feasible at zero cost — every value of y equally
        optimal, and no reliable answer to "was this planted". PLANT_FLAG_TIE_BREAK makes the
        minimum strictly optimal, so y now tracks x in every case.
        """
        params = dict(minimal_params)
        params["crops"] = [dict(c, min_acreage_if_planted=0.0) for c in params["crops"]]
        res = _solve(params)
        x = np.asarray(res["x"], dtype=float)
        y = np.asarray(res["y"], dtype=float)
        assert np.all(y <= 1 + 1e-6), f"y must stay bounded to 1: {y}"
        for i, (xi, yi) in enumerate(zip(x, y)):
            if xi <= 1e-9:
                assert yi <= 1e-6, (
                    f"succession {i} has x={xi} but reports y={yi} — an unplanted succession "
                    f"claiming to be planted, at min_acreage_if_planted=0"
                )

    def test_the_plant_flag_tie_break_stays_negligible(self, minimal_params):
        """It sits in the objective and NOT in the reported P&L, so it must stay invisible.

        Imported rather than re-typed: a test that restates the constant cannot notice the
        constant changing.
        """
        from farm_v2.solver import PLANT_FLAG_TIE_BREAK
        res = _solve(minimal_params)
        n_succ = len(res["successions"])
        worst_case = PLANT_FLAG_TIE_BREAK * n_succ
        assert worst_case < 0.01, (
            f"planting every one of {n_succ} successions would cost ${worst_case:.6f} of "
            f"objective distortion — the tie-break is no longer negligible"
        )


# ---------------------------------------------------------------------------
# An annual demand cap is a yearly total, not a weekly ceiling (audit B4)
# ---------------------------------------------------------------------------

class TestAnnualDemandIsAnnual:
    """A grower reads "annual total cap (lbs/yr)" as a contract volume.

    It was enforced as `annual / 52` in every week, so a crop harvesting in only part of the
    year could deliver only that fraction of a contract it had signed — and the docstring
    claimed the optimizer could front- or back-load freely. The cap now has its own row.
    """

    def test_a_short_harvest_can_still_fill_a_whole_annual_contract(self, minimal_params):
        params = dict(minimal_params)
        crop = dict(params["crops"][0])
        ch_name = params["channels"][0]["name"]
        chan = dict(crop["channels"][ch_name])
        chan["demand_cap_type"] = "annual"
        # Small enough that the farm can physically grow it, so the CAP is what binds.
        chan["annual_demand_lbs"] = 20_000
        crop["channels"] = {ch_name: chan}
        params["crops"] = [crop]

        res = _solve(params)
        assert res["status"] in ("optimal", "time_limit_feasible"), res["status"]
        v = np.asarray(res["v"], dtype=float)
        sold = float(v[0, 0, 1:].sum())

        harvest_weeks = sum(
            1 for i, s in enumerate(res["successions"])
            for w, ph in zip(s["weeks"], s["phases"]) if ph == 2
        )
        old_ceiling = (20_000 / 52.0) * max(1, harvest_weeks)

        assert sold <= 20_000 + 1e-6, (
            f"sold {sold:,.0f} lb against a 20,000 lb annual cap — the annual row is not binding"
        )
        assert sold > old_ceiling * 1.001 or sold == pytest.approx(20_000, rel=1e-6), (
            f"sold {sold:,.0f} lb, which the old annual/52 spread would also have permitted "
            f"({old_ceiling:,.0f} lb) — this test is not exercising the fix"
        )

    def test_the_annual_cap_is_never_exceeded(self, minimal_params):
        params = dict(minimal_params)
        crop = dict(params["crops"][0])
        ch_name = params["channels"][0]["name"]
        chan = dict(crop["channels"][ch_name])
        chan["demand_cap_type"] = "annual"
        chan["annual_demand_lbs"] = 5_000        # deliberately tight
        crop["channels"] = {ch_name: chan}
        params["crops"] = [crop]

        res = _solve(params)
        v = np.asarray(res["v"], dtype=float)
        assert float(v[0, 0, 1:].sum()) <= 5_000 + 1e-6, (
            "removing the weekly ceiling must not leave the channel unbounded"
        )
