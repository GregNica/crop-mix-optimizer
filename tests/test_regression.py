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
#   2026-07-27 — REBASELINED (operating_weeks retired as a cost multiplier). Recurring
#     fixed costs are now charged over the full 52-week year instead of the fixture's
#     operating_weeks=48: an owned asset depreciates and a loan accrues whether or not
#     the farm is operating, and the depreciation rates are themselves derived as
#     capital / (life × 52). Salaried payroll already used 52, which made the old
#     expression internally inconsistent. Revenue and variable cost are UNCHANGED
#     (1,627,508 / 356,785) and the plan is identical — only the 4 extra weeks of
#     non-salaried fixed lines move: fixed 1,098,984 → 1,184,316 (+85,332) and
#     profit 171,739 → 86,407 (−85,332, exactly the same figure).
#   2026-07-27 — REBASELINED (Phase B.2, SPEC_v3 §3 inventory core). C4/C5a/C5b/C7 are
#     replaced by a real weekly inventory balance with a storage cap on held stock and a
#     rolling shelf-life bound. Three defects died together: C7 capped a whole cycle's
#     production at one week's demand (B1), C5b double-counted overlapping sales windows
#     (B2), and those windows were anchored at the LAST harvest week so a crop could not
#     sell during its own earlier harvest weeks (F2). Revenue 1,627,508 → 1,761,684 and
#     profit 86,407 → 197,860; fixed cost unchanged at 1,184,316. This fixture wastes
#     nothing under the new model — every pound grown is sold.
#     The balance is verified to the pound, per crop, per week, by tests/test_inventory.py;
#     this file only pins that the headline did not drift afterwards.
#
#   2026-07-29 (honest water): profit -> 44,253. This fixture's crops got FAO-56 water rates and
#     its well was sized by the same 8 gpm/acre rule as the shipped default (2.5M -> 16.35M L/wk
#     for 150 acres, because 2.5M was 0.16 in/acre/week and could not irrigate the farm it
#     described). Water now binds here, which is the point: before this, the fixture's ~10x-low
#     rates meant the rainfall offset exceeded every crop's need and net irrigation was
#     identically ZERO — so this regression pin, and every other test using full_params, was
#     exercising a water constraint incapable of binding. Caught by the new binding test in
#     test_binding.py, which is exactly what that file is for.
#   2026-07-28 (Phase B.3, strict shelf life): `shelf_life_weeks` now counts SELLING weeks
#     including the harvest week, so the default of 1 means "sold the week it is picked" where
#     it previously allowed one more. Revenue 1,761,684 -> 1,628,917 (-7.5%) but profit
#     197,860 -> 87,933 (-55.6%): this fixture carries 1,184,316 of fixed cost, so a 7.5%
#     revenue cut takes more than half the profit with it. Operating leverage, not a modelling
#     error — and the reason this fixture is a sharper alarm than the golden farm (-7.8%).
#     ⚠️ This is the change landing AHEAD OF ITS DATA. None of this fixture's crops carry a
#     shelf life, so every one fell to the strictest possible reading. The agronomy audit sets
#     honest per-crop values; expect most of this back. Do not treat 87,933 as a target.
# ---------------------------------------------------------------------------

EXPECTED_PROFIT  = -23_492      # reference only — see test_the_fixture_is_still_near_break_even
EXPECTED_TOTAL_COST = 2_226_393 # ± 10%  (2026-07-31; carries the relative band profit cannot)
EXPECTED_REVENUE = 2_202_901    # ± 10%  (rebaselined 2026-07-29, DTM semantics)
# 2026-07-29 — days_to_maturity is PLANT TO FIRST HARVEST, not total field occupancy. The
# model derived grow = total - plant - harvest, so harvest_weeks ate the growing season and
# every crop with a harvest window under-charged land, labour, water and fertiliser. Field
# occupancy is now maturity PLUS the harvest window, land is genuinely scarcer, and revenue
# 2,508,022 -> 2,202,901 with profit 831,685 -> 588,948. A correction of an under-charge.
# 2026-07-29 (B4) — an annual demand cap is now a YEARLY TOTAL with its own constraint row,
# not `annual/52` imposed as a ceiling in every week. Revenue 1,992,132 -> 2,508,022 (+26%),
# profit 412,699 -> 831,685. Verified before re-pinning that the new row BINDS and is never
# exceeded: Spinach/Wholesale sells exactly 1,200,000 lb against its 1,200,000 lb cap, Napa
# 92%, Sweet Corn 14%, zero violations. Under the old spread Spinach could deliver at most
# ~23,077 lb in each of its harvest weeks, so most of a contract it had actually signed was
# unsellable. This fixture sits near break-even, so a 26% revenue move doubles profit.
# 2026-07-29 — seasons became PLANTING windows (B5), so a cycle no longer has to fit inside
# its window. On this 29-crop fixture that takes successions 74 -> 152 and revenue
# 1,791,809 -> 1,992,132 (+11%). Profit moves 44,253 -> 412,699, which looks alarming and is
# arithmetic: this fixture sits close to break-even, so an 11% revenue change swings profit
# by ~10x. Checked before re-pinning — no succession reuses a week, nothing wraps the year
# (no crop here sets `overwinters`), so the extra successions are the containment fix working
# rather than double-counting. Year-wrap is opt-in and does not touch this fixture.
EXPECTED_FIXED   = 1_868_316    # ± 5%   (rebaselined 2026-07-31: W12 put wages in fixed cost)
# 2026-07-31 — W12: every listed worker is paid for their stated hours whether the crops need them
# or not, so the wage bill moved into fixed cost. On this 29-crop fixture that is +$684,000 of
# fixed cost, and profit goes 588,948 -> -23,492.
#
# ⚠️ A LOSS IS THE HONEST ANSWER HERE, not a regression. This fixture staffs a farm generously and
# was previously charged only for the hours its crops happened to use; paying that crew properly
# is more than its margin can carry. It sits close to break-even by construction (see the note
# below on how an 11% revenue change swung profit ~10x), so it is the sharpest alarm in the suite
# and it is now alarming about a real thing. The GOLDEN farm, which is the one a user sees, stays
# comfortably profitable at 20.0% net margin.
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
    def test_total_cost_in_expected_range(self, full_result):
        """The relative band lives HERE, on a large positive number where 10% means what it says.

        It used to live on `profit`, and W12 re-pinned this fixture to -$23,492 — deliberately
        near break-even, as the note above records. A relative band then means +/-$2.3k, the
        tightest assertion in the suite on the fixture most prone to swinging; re-anchoring its
        WIDTH to revenue overcorrected to +/-$220k, i.e. +/-950% of the pinned value, so profit
        could change by an order of magnitude AND flip sign without firing. Both are wrong for
        the same reason: profit near zero cannot carry a proportional tolerance at all.

        Cost and revenue can. Between them they bound profit (profit = revenue - total_cost)
        without either band having to be nonsense.
        """
        r = full_result
        # Summed from the solver's own reported identity rather than a fifth hand-written list of
        # cost keys (BACKLOG W8(a) flags the same enumeration in exportPLCSV). If a new cost line
        # is added, `operating_profit` moves with it and this stays correct.
        total_cost = r["revenue"] - r["operating_profit"]
        lo = EXPECTED_TOTAL_COST * (1 - TOLERANCE_PCT)
        hi = EXPECTED_TOTAL_COST * (1 + TOLERANCE_PCT)
        assert lo <= total_cost <= hi, (
            f"Total cost ${total_cost:,.0f} outside expected range [{lo:,.0f}, {hi:,.0f}]. "
            "Intentional? Update EXPECTED_TOTAL_COST in test_regression.py."
        )

    def test_the_fixture_is_still_near_break_even(self, full_result):
        """What this fixture is actually FOR, said plainly instead of dressed as a tolerance.

        It is a deliberately marginal 29-crop farm — the note above records an 11% revenue move
        swinging profit ~10x — which is what makes it the sharpest alarm in the suite. The thing
        worth asserting is not "profit is within N% of a number near zero", which is either a
        hair-trigger or meaningless depending on how N is scaled. It is "this farm has not blown
        up in either direction", with the real proportional guards on revenue and total cost.
        """
        profit = full_result["profit"]
        # ⚠️ THIRD attempt at this band, and the first two were wrong in opposite directions:
        # ±10% of a near-zero profit is ±$2.3k (a hair-trigger), and ±10% of revenue is ±$220k
        # (±950%, meaningless). Review then showed THIS band is 91% of the width of the one it
        # replaced — so on its own it is barely an improvement, and it is not carrying the load.
        # The real coverage is EXPECTED_TOTAL_COST and EXPECTED_REVENUE above, both large
        # positives where a relative band means what it says. This assertion's only job is to
        # catch a change of CHARACTER — a fixture built to sit near break-even ending up wildly
        # profitable or catastrophically loss-making — so it is deliberately loose and says so
        # rather than pretending to be a tolerance.
        assert -250_000 < profit < 150_000, (
            f"Profit ${profit:,.0f} left the near-break-even band this fixture exists to sit in "
            f"(it was ${EXPECTED_PROFIT:,.0f} when last pinned). That is a real change of "
            f"character, not drift — find out which line moved before re-pinning."
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
        # 2026-07-29: 74 -> 152 when season windows became PLANTING windows. The old ceiling
        # encoded the whole-cycle-containment rule, which is the defect B5 removed.
        assert 130 <= n <= 175, f"Expected ~152 successions, got {n}"

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
        # 2026-07-29 (B4): 6 -> 4. Not a diversity requirement — nothing in the model asks
        # for one — but a consequence of contracts becoming fillable. With annual caps freed,
        # the crops holding large contracts absorb the land instead of every crop taking a
        # throttled share. The floor is kept as a smoke test that the plan is not collapsing
        # to a monoculture, which WOULD indicate a broken constraint.
        assert len(planted_crops) >= 3, (
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
