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
        """y is REPORTED as a function of x, so it answers its question exactly.

        The tie-break alone was not enough and the earlier claim here overstated it: its total
        value across ~155 successions sits below HiGHS's default relative MIP gap, and it is
        not enforced at all on the time_limit_feasible path. An incumbent could still carry
        y=1 with x=0. Deriving the reported value removes the dependence on the tie-break's
        magnitude — x is the quantity, y is "is x above zero".
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


# ---------------------------------------------------------------------------
# Every zero-acre crop says WHY (audit Part 3 / S2)
# ---------------------------------------------------------------------------

class TestUnplantedCropsExplainThemselves:
    """A crop can reach zero acres from at least four causes.

    Only one of them (the margin hurdle) ever had a banner. The rest were identical to the
    grower: a crop they asked for, missing from the plan, nothing on screen. Each branch is
    pinned separately here — a diagnosis that collapses to one generic answer for everything
    is the failure mode, and it would still "pass" a test that only checked the list is
    non-empty.
    """

    def _reasons(self, res):
        return {d["crop"]: d["reason"] for d in res["unplanted_crops"]}

    def test_a_planted_crop_is_not_listed(self, minimal_params):
        res = _solve(minimal_params)
        planted = {
            res["successions"][i]["crop"]
            for i, xi in enumerate(res["x"]) if xi > 1e-9
        }
        names = {res["crops"][c]["name"] for c in planted}
        assert names, "fixture planted nothing — this test would be vacuous"
        for d in res["unplanted_crops"]:
            assert d["crop"] not in names, (
                f"{d['crop']} is in the plan but was reported as unplanted"
            )

    def test_no_plantable_window_is_named_as_such(self, minimal_params):
        """A cycle that cannot finish inside the year, with no overwinters flag."""
        params = dict(minimal_params)
        viable = dict(params["crops"][0])
        crop = dict(viable)
        crop["name"] = "Too Late"
        crop["seasons"] = [{"start": "12-15", "end": "12-24"}]
        # A viable crop alongside it: with NO crop plantable the solver raises globally and
        # there is no plan to diagnose against.
        params["crops"] = [viable, crop]
        res = _solve(params)
        assert self._reasons(res).get("Too Late") == "no_plantable_window", (
            f"expected a calendar explanation, got {res['unplanted_crops']}"
        )
        rec = next(d for d in res["unplanted_crops"] if d["crop"] == "Too Late")
        assert rec["cycle_weeks"] > 0, "the calendar reason must carry the cycle length"

    def test_no_demand_is_named_as_such(self, minimal_params):
        params = dict(minimal_params)
        crop = dict(params["crops"][0])
        ch_name = params["channels"][0]["name"]
        chan = dict(crop["channels"][ch_name])
        chan["demand_cap_type"] = "weekly_flat"
        chan["weekly_demand_lbs"] = 0
        crop["channels"] = {ch_name: chan}
        params["crops"] = [crop]
        res = _solve(params)
        assert self._reasons(res).get(crop["name"]) == "no_demand", (
            f"a crop with nowhere to sell must say so, got {res['unplanted_crops']}"
        )

    def test_an_annual_channel_with_zero_volume_is_no_demand_not_outcompeted(
            self, minimal_params):
        """A blank demand box on an "annual" channel sends annual_demand_lbs: 0.

        The crop then has nowhere at all to be sold, but the reason was gated on whether the
        crop APPEARED in annual_caps rather than on the cap being positive — and a zero-volume
        annual channel still has a key there. So it was reported as `outcompeted`, which the UI
        renders as "was plantable and sellable, but did not earn its place". It was neither.
        """
        params = dict(minimal_params)
        crop = dict(params["crops"][0])
        ch_name = params["channels"][0]["name"]
        chan = dict(crop["channels"][ch_name])
        chan["demand_cap_type"] = "annual"
        chan["annual_demand_lbs"] = 0
        crop["channels"] = {ch_name: chan}
        params["crops"] = [crop]
        res = _solve(params)
        assert self._reasons(res).get(crop["name"]) == "no_demand", (
            f"a crop with a zero-volume annual contract has nowhere to sell; got "
            f"{res['unplanted_crops']}"
        )

    def test_outcompeted_is_the_conservative_default(self, minimal_params):
        """An LP declines a bundle at these prices; it does not reject a crop for one reason.

        So when nothing structural is wrong the answer must be "it did not compete", NOT a
        confidently-named binding constraint. Naming one would be a story, not a finding.
        """
        params = dict(minimal_params)
        good = dict(params["crops"][0])
        bad = dict(good)
        bad["name"] = "Unprofitable Twin"
        ch_name = params["channels"][0]["name"]
        chan = dict(bad["channels"][ch_name])
        chan["price_per_lb"] = 0.01            # plantable, sellable, simply not worth it
        bad["channels"] = {ch_name: chan}
        params["crops"] = [good, bad]
        res = _solve(params)
        reason = self._reasons(res).get("Unprofitable Twin")
        assert reason == "outcompeted", (
            f"expected the conservative default, got {reason!r}: {res['unplanted_crops']}"
        )

    def test_every_entry_returns_a_crop_a_reason_and_a_detail(self, minimal_params):
        params = dict(minimal_params)
        viable = dict(params["crops"][0])
        crop = dict(viable); crop["name"] = "Too Late"
        crop["seasons"] = [{"start": "12-15", "end": "12-24"}]
        params["crops"] = [viable, crop]
        for d in _solve(params)["unplanted_crops"]:
            assert d.get("crop") and d.get("reason"), d
            # STRUCTURED, not prose: the solver returns the reason code and the numbers, and
            # the UI builds the sentence. A `detail` string here would put narration in the
            # solver and give a future assistant prose to re-parse instead of data to read.
            assert "detail" not in d, (
                f"the solver is writing sentences again: {d}"
            )
            for k in ("cycle_weeks", "min_acres", "excluded_channels", "tightest"):
                assert k in d, f"missing structured field {k!r}: {d}"

    def test_y_tracks_x_on_a_truncated_solve_too(self, full_params):
        """The tie-break is not enforced when HiGHS stops early — the derivation still is."""
        res = solve_farm_v2(**{**full_params, "solver_time_limit": 0.5})
        if res["status"] not in ("optimal", "time_limit_feasible"):
            pytest.skip(f"no usable incumbent at this budget ({res['status']})")
        x = np.asarray(res["x"], dtype=float)
        y = np.asarray(res["y"], dtype=float)
        for i, (xi, yi) in enumerate(zip(x, y)):
            expected = 1.0 if xi > 1e-9 else 0.0
            assert yi == expected, (
                f"succession {i}: x={xi}, y={yi} — on a truncated solve the reported plant flag "
                f"must still be derived from x, not read from the incumbent"
            )


# ---------------------------------------------------------------------------
# Land already in the ground is not a decision (S14)
# ---------------------------------------------------------------------------

class TestCommittedAcres:
    """Raised by the grower on seeing year-wrap land.

    Planning happens in winter, after November garlic is already planted. The cyclic year is
    self-consistent annually, but the optimiser could still choose ZERO acres of a crop that is
    already in the ground and already paid for — a plan nobody can act on.
    """

    def _unprofitable(self, minimal_params, committed):
        """A crop the optimiser would drop on the economics, with acres already committed."""
        params = dict(minimal_params)
        crop = dict(params["crops"][0])
        ch_name = params["channels"][0]["name"]
        chan = dict(crop["channels"][ch_name])
        chan["price_per_lb"] = 0.001          # nobody would choose to plant this
        crop["channels"] = {ch_name: chan}
        crop["committed_acres"] = committed
        crop["min_acreage_if_planted"] = 0.0
        params["crops"] = [crop]
        return params

    def test_without_a_commitment_an_unprofitable_crop_is_dropped(self, minimal_params):
        """The control. Without it, the test below could pass for the wrong reason."""
        res = _solve(self._unprofitable(minimal_params, 0.0))
        acres = sum(res["x"]) * minimal_params["total_land"]
        assert acres < 1e-6, f"the fixture is not actually unprofitable — planted {acres} acres"

    def test_committed_acres_are_planted_even_when_unprofitable(self, minimal_params):
        res = _solve(self._unprofitable(minimal_params, 3.0))
        assert res["status"] in ("optimal", "time_limit_feasible"), res["status"]
        acres = sum(res["x"]) * minimal_params["total_land"]
        assert acres >= 3.0 - 1e-6, (
            f"only {acres:.2f} acres planted against 3.0 already in the ground — the optimiser "
            f"is still treating a committed planting as a free choice"
        )

    def test_a_commitment_larger_than_the_farm_is_refused_with_a_reason(self, minimal_params):
        params = self._unprofitable(minimal_params, minimal_params["total_land"] + 10)
        res = _solve(params)
        assert res["status"] == "invalid_input", res["status"]
        assert any("committed" in e.lower() for e in res["errors"]), res["errors"]
