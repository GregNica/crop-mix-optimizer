"""Wages are a COMMITMENT, and they have a SHAPE (W12).

The model used to charge hourly and seasonal staff only for the hours the crops happened to use,
while salaried staff were already a fixed cost. Measured on the shipped farm: a stated crew with a
$736,400 wage bill was costed at $293,356 — 60.2% of payroll invisible. Every listed worker is now
paid for their stated hours over their stated weeks.

Two rules carry the whole change, and neither had a test until this file:

  1. WAGES ARE CHARGED ON FULL HOURS. `field_time_pct` says how much of a worker's time is
     available for crop work; it does not reduce what the farm owes them. Charging the
     field-adjusted figure instead is a plausible-looking mistake that passed 27 tests when
     mutated in, and only showed up as a dollar mismatch in the golden farm.
  2. PAYROLL IS NOT FLAT. It is the first fixed line with a weekly profile, so it must reach the
     cash floor as the profile rather than as an annual total divided by 52.
"""
import numpy as np
import pytest

pytest.importorskip("scipy")

from farm_v2.solver import solve_farm_v2            # noqa: E402
from farm_v2.utils.labor import compute_labor_arrays  # noqa: E402


class TestWagesAreChargedOnFullHours:
    def test_field_time_pct_cuts_capacity_and_not_the_wage(self):
        """The rule, stated on its own: half the field time, half the capacity, same wage.

        A worker on 50% field time is paid for a whole week and can only be pointed at crops for
        half of it. Tying the wage to `field_time_pct` would quietly make part-time-on-crops staff
        free, which is the understatement W12 exists to remove.
        """
        full = [{"position": "Hand", "count": 1, "type": "hourly", "wage": 20.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0, "field_time_pct": 100}]
        half = [dict(full[0], field_time_pct=50)]
        a = compute_labor_arrays(full, [], 52)
        b = compute_labor_arrays(half, [], 52)

        assert float(b["committed_weekly_wages"].sum()) == pytest.approx(
            float(a["committed_weekly_wages"].sum())), (
            "halving field time changed the wage bill — the farm owes the whole shift regardless "
            "of how much of it the crops can use"
        )
        assert float(b["labor_capacity"].sum()) == pytest.approx(
            float(a["labor_capacity"].sum()) / 2.0), "field time must halve crop-available hours"
        # And the absolute figure, so a proportional error in both cannot hide here.
        assert float(a["committed_weekly_wages"].sum()) == pytest.approx(40.0 * 20.0 * 52)

    def test_benefits_are_owed_too(self):
        lab = compute_labor_arrays(
            [{"position": "Hand", "count": 2, "type": "hourly", "wage": 20.0,
              "hours_per_week": 40.0, "benefits_pct": 0.25}], [], 52)
        assert float(lab["committed_weekly_wages"].sum()) == pytest.approx(2 * 40 * 25.0 * 52)

    def test_every_kind_of_worker_is_committed(self):
        """Salaried, year-round hourly and seasonal all land in one bill.

        The defect was an inconsistency — salaried staff were committed and the others were not —
        so the guard is that all three now agree, and that seasonal staff are charged for their
        window and not the year.
        """
        lab = compute_labor_arrays(
            [{"position": "Mgr", "count": 1, "type": "salary", "wage": 52_000.0,
              "hours_per_week": 40.0, "benefits_pct": 0.0},
             {"position": "Op", "count": 1, "type": "hourly", "wage": 10.0,
              "hours_per_week": 40.0, "benefits_pct": 0.0}],
            [{"position": "Crew", "count": 3, "type": "FT", "wage": 20.0, "hours_per_week": 40.0,
              "benefits_pct": 0.0, "start_week": 10, "end_week": 19}], 52)
        weekly = lab["committed_weekly_wages"]
        salary_wk, hourly_wk, seasonal_wk = 1_000.0, 400.0, 3 * 40 * 20.0
        assert weekly[0] == pytest.approx(salary_wk + hourly_wk), "week 1: no seasonal crew yet"
        assert weekly[9] == pytest.approx(salary_wk + hourly_wk + seasonal_wk), "week 10: crew on"
        assert weekly[19] == pytest.approx(salary_wk + hourly_wk), "week 21: crew gone"
        assert float(weekly.sum()) == pytest.approx(
            (salary_wk + hourly_wk) * 52 + seasonal_wk * 10)

    def test_the_wage_bill_reaches_the_solver_as_a_fixed_cost(self, two_crop_params):
        r = solve_farm_v2(**two_crop_params)
        assert r["status"] == "optimal"
        lab = compute_labor_arrays(two_crop_params["year_round_employees"],
                                   two_crop_params["seasonal_employees"], 52)
        assert r["fixed_cost_split"]["wages"] == pytest.approx(
            float(lab["committed_weekly_wages"].sum()), abs=0.01)
        assert "labor" not in r["variable_cost_split"], (
            "labour is a committed cost now; a per-acre labour charge would bill it twice"
        )


class TestPayrollIsNotFlat:
    """Wages are the first fixed line with a weekly shape, which makes flat-spreading wrong.

    Every other fixed line (irrigation, machinery, mortgage, debt service, storage) genuinely is
    the same every week, so `fixed_cost / 52` was exact and nothing had to care. Payroll is
    $4,884/wk in the shipped farm's winter and $24,484/wk once the seasonal crews start.
    """

    def _seasonal_farm(self, params, **over):
        return dict(params,
                    year_round_employees=[
                        {"position": "Mgr", "count": 1, "type": "salary", "wage": 52_000.0,
                         "hours_per_week": 40.0, "benefits_pct": 0.0}],
                    seasonal_employees=[
                        {"position": "Crew", "count": 10, "type": "FT", "wage": 20.0,
                         "hours_per_week": 40.0, "benefits_pct": 0.0,
                         "start_week": 20, "end_week": 40}],
                    **over)

    def test_the_cash_curve_charges_payroll_in_the_weeks_it_is_owed(self, minimal_params):
        """The property, on a farm where the curve is fully predictable.

        Both of the first attempts at this test were INERT — they asserted the fixture had a
        seasonal shape and that the totals reconciled, and a flat spread satisfies both (same
        annual bill, same total). Mutation-testing caught them: re-flattening payroll left all six
        tests green, and only the golden farm's pinned interest noticed.

        The fix is to remove everything else from the curve. With every price at zero the
        optimizer plants nothing, so weekly revenue and variable cost are both zero and each
        week's cash movement is exactly the flat fixed lines plus THAT WEEK's payroll. A flat
        spread then reports the same number every week; the true profile reports the salary alone
        until the crew arrives and a step up afterwards.
        """
        p = dict(minimal_params, opening_cash=5_000_000.0, credit_line=0.0)
        crop = dict(p["crops"][0])
        ch = p["channels"][0]["name"]
        crop["channels"] = {ch: dict(crop["channels"][ch], price_per_lb=0.0)}
        p["crops"] = [crop]
        p = self._seasonal_farm(p, opening_cash=5_000_000.0, credit_line=0.0)

        r = solve_farm_v2(**p)
        assert r["status"] == "optimal", r["status"]
        assert float(np.asarray(r["x"]).sum()) == pytest.approx(0.0, abs=1e-6), (
            "something was planted at a zero price, so the curve is not payroll-only any more"
        )

        weekly = compute_labor_arrays(p["year_round_employees"],
                                      p["seasonal_employees"], 52)["committed_weekly_wages"]
        cash = np.asarray(r["weekly_cash_flow"])[1:]
        drops = -np.diff(np.concatenate(([r["opening_cash"]], cash)))   # outflow per week

        quiet, busy = 0, 25          # week 1 (no crew) and week 26 (crew on)
        assert weekly[busy] > weekly[quiet], "fixture's crew does not start mid-year"
        step = float(weekly[busy] - weekly[quiet])
        assert float(drops[busy] - drops[quiet]) == pytest.approx(step, abs=0.01), (
            f"cash outflow rose by ${drops[busy] - drops[quiet]:,.2f} when payroll rose by "
            f"${step:,.2f}. A flat spread charges the same every week and would give $0.00 here — "
            f"the cash curve is not seeing payroll in the weeks it is actually owed."
        )
