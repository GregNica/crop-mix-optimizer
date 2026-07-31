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
import pathlib

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
        assert weekly[19] == pytest.approx(salary_wk + hourly_wk), "week 20: crew gone"
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
        p = dict(minimal_params)
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


class TestBoughtHoursCarryTheirFullWage:
    """Hours bought beyond the committed crew — overtime and hired labour — cost the WHOLE wage.

    THE DEFECT W12 CREATED AND `/code-review` CAUGHT. Before W12 every crop hour was charged at
    the blended wage inside `var_cost_coeff`, so overtime and hire only had to add their premium
    on top: `rate x (multiplier - 1)` and `rate x markup`. W12 moved the crew's pay into the
    committed wage bill and deleted that per-hour charge — but bought hours are NOT in the
    committed bill, so the base wage ended up charged nowhere at all.

    Measured before the fix, on a 200-acre fixture: **2,080 hired hours at $0.00**, worth
    +$965,177 of phantom profit, and overtime at 1.5x charged $7.02/hr against an $18.00 blend.
    The shipped defaults are `max_hire_hrs_per_week=400` and `hire_wage_markup=0`, so the What-If
    "Plan optimal labor" tool was handing the optimizer 20,800 free hours a year and reporting the
    result as a gain. All nine labor-flex tests passed throughout.

    A SECOND HOLE UNDERNEATH IT: `hourly_labor_rate` is the blend of the EXISTING hourly crew, so
    it is 0 in any week they are not on. Even charging "the full rate" prices a bought hour at
    zero there. Hence `fallback_hourly_wage` — the farm's own average paid wage.
    """

    def _needs_help(self, minimal_params):
        """A farm whose crew cannot cover its own crops, so buying hours is the only way to grow."""
        return dict(minimal_params, opening_cash=5_000_000.0, credit_line=5_000_000.0,
                    year_round_employees=[
                        {"position": "Hand", "count": 1, "type": "hourly", "wage": 20.0,
                         "hours_per_week": 40.0, "benefits_pct": 0.0}],
                    seasonal_employees=[])

    def test_hired_hours_at_a_zero_markup_still_cost_the_base_wage(self, minimal_params):
        p = dict(self._needs_help(minimal_params),
                 hire_enabled=True, max_hire_hrs_per_week=2_000.0, hire_wage_markup=0.0)
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal", r["status"]
        assert r["total_hired_hours"] > 0, (
            "nothing was hired, so this test cannot tell a free hour from a paid one — the "
            "fixture's crew must be too small for its crops"
        )
        implied = r["hire_cost"] / r["total_hired_hours"]
        assert implied == pytest.approx(20.0, rel=1e-6), (
            f"hired labour costs ${implied:.2f}/hr at a 0% markup against a $20.00 wage. At $0.00 "
            f"the optimizer is being handed free hours and reporting the result as profit."
        )

    def test_overtime_costs_the_multiplier_on_the_whole_wage(self, minimal_params):
        p = dict(self._needs_help(minimal_params),
                 overtime_enabled=True, max_overtime_hrs_per_week=2_000.0,
                 overtime_rate_multiplier=1.5)
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert r["total_overtime_hours"] > 0, "no overtime bought; fixture cannot discriminate"
        implied = r["overtime_cost"] / r["total_overtime_hours"]
        assert implied == pytest.approx(30.0, rel=1e-6), (
            f"overtime costs ${implied:.2f}/hr against a $20.00 wage at 1.5x. ${20.0 * 0.5:.2f} "
            f"would mean only the premium is charged and the base wage has gone missing."
        )

    def test_a_week_with_no_hourly_crew_still_prices_a_bought_hour(self, minimal_params):
        """The second hole: an all-salaried farm has a blended rate of 0 in every week.

        Without a fallback, `rate x multiplier` is 0 x anything = free, so a farm with no hourly
        staff could buy unlimited labour for nothing.
        """
        p = dict(minimal_params, opening_cash=5_000_000.0, credit_line=5_000_000.0,
                 year_round_employees=[
                     {"position": "Mgr", "count": 1, "type": "salary", "wage": 52_000.0,
                      "hours_per_week": 40.0, "benefits_pct": 0.0}],
                 seasonal_employees=[],
                 hire_enabled=True, max_hire_hrs_per_week=2_000.0, hire_wage_markup=0.0)
        lab = compute_labor_arrays(p["year_round_employees"], [], 52)
        assert float(lab["hourly_labor_rate"].max()) == 0.0, "fixture has an hourly crew after all"
        # No hourly role exists at all, so there is no cheapest wage to infer a hire from and no
        # blend to price overtime with — both fall back to the farm's own average paid wage.
        assert float(lab["hire_hour_wage"][0]) == pytest.approx(1_000.0 / 40.0)
        assert float(lab["overtime_hour_wage"][0]) == pytest.approx(1_000.0 / 40.0), (
            "with no hourly crew, both bases must fall back to the average paid wage: "
            "$52,000/yr over 40 h/wk"
        )
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert r["total_hired_hours"] > 0, (
            "nothing was hired, so this cannot tell a $25 hour from a free one — the fixture's "
            "crew must be too small for its crops"
        )
        implied = r["hire_cost"] / r["total_hired_hours"]
        assert implied == pytest.approx(25.0, rel=1e-6), (
            f"bought hours cost ${implied:.2f}/hr on a farm with no hourly crew"
        )


def test_a_wrap_around_seasonal_window_is_refused_not_silently_free():
    """`range(start-1, end)` is EMPTY when start > end, so a winter crew entered as weeks 45-5
    used to contribute no capacity — and after W12, no WAGES either, for people the farm really
    pays. Losing a whole wage bill in silence is worse than the capacity it used to lose."""
    with pytest.raises(ValueError, match="wraps the year"):
        compute_labor_arrays([], [{"position": "Winter Crew", "count": 2, "type": "FT",
                                   "wage": 20.0, "hours_per_week": 40.0, "benefits_pct": 0.0,
                                   "start_week": 45, "end_week": 5}], 52)


def test_overtime_does_not_double_charge_the_base_wage(minimal_params):
    """The arithmetic behind "charge bought hours their FULL rate", made executable.

    This is the step that looks wrong and is not, so it earns a test rather than a comment. The
    invariant is that `labor_capacity` IS the crew's stated hours — exactly what the committed
    bill already paid for — and C2 measures bought hours against it. So an overtime hour is
    genuinely a 41st hour, and charging `wage x multiplier` on it adds no second base.

    One worker, 40 h/wk at $20, no benefits, 100% field time, asked for more than 40 hours:

        committed  40 x $20                 =   $800
        overtime   N x $20 x 1.5            =   $30 per extra hour
        total                                  $800 + $30N

    Pinning the TOTAL, not just the rate. A rate check alone passes if the base is charged twice
    somewhere else; this is the assertion that would catch a regression in either direction —
    back to "increment only" (the defect W12 created) or forward into double-counting.
    """
    p = dict(minimal_params, opening_cash=5_000_000.0, credit_line=5_000_000.0,
             year_round_employees=[{"position": "Hand", "count": 1, "type": "hourly",
                                    "wage": 20.0, "hours_per_week": 40.0,
                                    "benefits_pct": 0.0, "field_time_pct": 100}],
             seasonal_employees=[],
             overtime_enabled=True, max_overtime_hrs_per_week=100.0,
             overtime_rate_multiplier=1.5)
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", r["status"]
    ot_hours = r["total_overtime_hours"]
    assert ot_hours > 0, "no overtime bought, so the double-charge question is not exercised"

    committed = r["fixed_cost_split"]["wages"]
    assert committed == pytest.approx(40.0 * 20.0 * 52), (
        f"the committed bill is ${committed:,.2f}; it must be the stated 40 h/wk at $20 for 52 "
        f"weeks and nothing else, or the baseline for this arithmetic is wrong"
    )
    assert r["overtime_cost"] == pytest.approx(ot_hours * 30.0, rel=1e-6), (
        f"overtime cost ${r['overtime_cost']:,.2f} for {ot_hours:,.1f} h. At $10/hr the base has "
        f"gone missing again; at $50/hr it is being charged twice."
    )
    # And the two together are the whole labour bill — nothing else charges an hour anywhere.
    assert committed + r["overtime_cost"] == pytest.approx(
        40.0 * 20.0 * 52 + ot_hours * 30.0, rel=1e-9)


class TestHireIsPricedForTheMarketNotTheCrew:
    """A hired hand is bought from the local labour market; overtime is your own crew staying late.

    W15: sharing one price between them meant the existing crew's blend stood in for a market
    wage, and it is a poor proxy whenever the crew is unrepresentative — measured, a farm whose
    only worker is a $95,000 manager valued a hired field hand at $40.60/hr, and the demo crew
    priced one at $22.08 against a real harvest wage of $19, so the optimizer refused hires it
    should have taken. The error direction was safe (over-pricing, where the defect it replaced
    was FREE labour), which is why this was a decision rather than a bug.
    """

    def _crew(self):
        return [{"position": "Mgr", "count": 1, "type": "salary", "wage": 104_000.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0},
                {"position": "Operator", "count": 1, "type": "hourly", "wage": 40.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0}]

    def test_an_explicit_hired_wage_is_used_verbatim(self):
        lab = compute_labor_arrays(self._crew(), [], 52, hired_wage_per_hr=17.5)
        assert float(lab["hire_hour_wage"][0]) == pytest.approx(17.5), (
            "the grower said what a hand costs; nothing should be inferred over the top of it"
        )
        # ...and it must NOT bleed into overtime, which is the existing crew's own rate.
        assert float(lab["overtime_hour_wage"][0]) == pytest.approx(40.0)

    def test_without_one_the_proxy_is_an_hours_weighted_average_of_PAID_hourly_roles(self):
        """Third answer to "what does a hired hand cost", and the first that is robust both ways.

        The average over ALL paid hours dragged the price up toward salaried staff who would never
        do the work ($40.60/hr for a field hand on a manager-only farm). An unweighted `min` over
        roles then dragged it down to the least representative one, and that direction is the
        UNSAFE one — under-pricing makes the optimizer buy help the grower cannot get. Weighting
        by hours is robust to both tails, and salaried staff are not in the list at all.
        """
        crew = self._crew() + [{"position": "Hand", "count": 2, "type": "hourly", "wage": 18.0,
                                "hours_per_week": 40.0, "benefits_pct": 0.0}]
        lab = compute_labor_arrays(crew, [], 52)
        expected = (40.0 * 40.0 + 18.0 * 80.0) / (40.0 + 80.0)     # $25.33
        assert float(lab["hire_hour_wage"][0]) == pytest.approx(expected, rel=1e-9)
        # The $104k manager must not be in it — that was the original defect.
        assert float(lab["hire_hour_wage"][0]) < 30.0

    def test_a_tiny_cheap_role_does_not_set_the_price_for_every_bought_hour(self):
        """The failure mode `min` had: one 2 h/wk helper priced all 20,800 potential hired hours.

        Hours-weighting is what contains it — the helper moves the rate by cents, not to $12.
        """
        base = [{"position": "Crew", "count": 4, "type": "hourly", "wage": 22.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0}]
        helper = {"position": "Helper", "count": 1, "type": "hourly", "wage": 12.0,
                  "hours_per_week": 2.0, "benefits_pct": 0.0}
        without = float(compute_labor_arrays(base, [], 52)["hire_hour_wage"][0])
        with_helper = float(compute_labor_arrays(base + [helper], [], 52)["hire_hour_wage"][0])
        assert without == pytest.approx(22.0)
        assert with_helper > 21.8, (
            f"a 2 h/wk helper at $12 moved the hired rate to ${with_helper:.2f}. An unweighted "
            f"minimum would give $12.00 and price every bought hour off the least representative "
            f"role on the farm."
        )

    def test_an_unpaid_role_does_not_make_hired_labour_free(self):
        """W12b, reopened and closed again.

        Piece-rate pickers, unpaid family and a blank wage box all arrive as wage 0. An unfiltered
        minimum over the wage list returned 0, and 0 x (1 + markup) is still 0 — so the markup
        could not rescue it and hired hours cost nothing. Measured before the fix:
        hire_hour_wage = $0.00 for all 52 weeks.
        """
        crew = [{"position": "Hand", "count": 1, "type": "hourly", "wage": 20.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0},
                {"position": "Picker (piece rate)", "count": 4, "type": "hourly", "wage": 0.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0}]
        lab = compute_labor_arrays(crew, [], 52)
        assert float(lab["hire_hour_wage"][0]) == pytest.approx(20.0), (
            f"a $0/hr role set the hired rate to ${float(lab['hire_hour_wage'][0]):.2f}"
        )
        assert float(lab["hire_hour_wage"].min()) > 0.0, "hired labour is free in some week"
        assert float(lab["overtime_hour_wage"].min()) > 0.0, "overtime is free in some week"

    @pytest.mark.parametrize("bad", [0, 0.0, -5, "", "abc", "0"])
    def test_an_unusable_explicit_wage_is_refused_not_silently_accepted(self, bad):
        """0 is not "infer" — it is free labour. Negative is worse: a negative objective
        coefficient the optimizer drives to the hiring cap for phantom profit. Refused HERE
        rather than trusted to a caller, because the caller is who got it wrong before."""
        crew = [{"position": "Hand", "count": 1, "type": "hourly", "wage": 20.0,
                 "hours_per_week": 40.0, "benefits_pct": 0.0}]
        with pytest.raises(ValueError):
            compute_labor_arrays(crew, [], 52, hired_wage_per_hr=bad)

    def test_seasonal_wages_count_as_hourly_for_the_proxy(self):
        lab = compute_labor_arrays(
            [{"position": "Mgr", "count": 1, "type": "salary", "wage": 104_000.0,
              "hours_per_week": 40.0, "benefits_pct": 0.0}],
            [{"position": "Crew", "count": 6, "type": "FT", "wage": 15.0, "hours_per_week": 40.0,
              "benefits_pct": 0.0, "start_week": 10, "end_week": 30}], 52)
        assert float(lab["hire_hour_wage"][0]) == pytest.approx(15.0), (
            "seasonal staff are hourly by construction, so their wage is a market signal too"
        )

    def test_the_explicit_wage_reaches_the_solver(self, minimal_params):
        p = dict(minimal_params, opening_cash=5_000_000.0, credit_line=5_000_000.0,
                 year_round_employees=[{"position": "Hand", "count": 1, "type": "hourly",
                                        "wage": 40.0, "hours_per_week": 40.0,
                                        "benefits_pct": 0.0}],
                 seasonal_employees=[],
                 hire_enabled=True, max_hire_hrs_per_week=2_000.0, hire_wage_markup=0.0,
                 hired_wage_per_hr=12.0)
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert r["total_hired_hours"] > 0, "nothing hired, so the price cannot be checked"
        implied = r["hire_cost"] / r["total_hired_hours"]
        assert implied == pytest.approx(12.0, rel=1e-6), (
            f"hired hours cost ${implied:.2f}/hr against an explicit $12.00 input. At $40.00 the "
            f"solver is still pricing hires from the existing crew's wage."
        )


def test_the_hired_wage_input_crosses_the_adapter():
    """End to end: the form's value must reach the solver, and BLANK must not mean free.

    A solver parameter with no form field is W11's defect facing the other way. And blank is the
    trap: `parseFloat("") || 0` is $0.00/hr, i.e. free hired labour, which is the bug W12b closed.

    ⚠️ The first version of this test guarded two string literals that no plausible regression
    writes (`"|| 0 : null"`, and a two-line pattern that checked the line AFTER the assignment).
    Both were inert. This asserts on the ACTUAL assignment instead — extracted and checked for the
    `|| 0` idiom that would reintroduce the defect.
    """
    import re
    src = (pathlib.Path(__file__).resolve().parent.parent / "public" / "index.html").read_text()
    assert 'id="hired_wage_per_hr"' in src, "no form field — the parameter is unreachable"
    assert "hired_wage_per_hr=hired_wage_per_hr" in src, "run_from_js never forwards it"

    m = re.search(r"sp\.hired_wage_per_hr\s*=\s*([^;]+);", src)
    assert m, "the payload builder never assigns sp.hired_wage_per_hr"
    assignment = m.group(1)
    assert "|| 0" not in assignment, (
        f"the payload builder assigns `{assignment.strip()}` — a `|| 0` fallback turns a blank "
        f"field into $0.00/hr, which is free hired labour"
    )
    assert "null" in assignment, (
        f"blank must travel as null so the solver infers a rate; got `{assignment.strip()}`"
    )


def test_blank_means_infer_not_free():
    """Blank means infer. Empty string and 0 are REFUSED, not reinterpreted — see below."""
    crew = [{"position": "Hand", "count": 1, "type": "hourly", "wage": 21.0,
             "hours_per_week": 40.0, "benefits_pct": 0.0}]
    inferred = compute_labor_arrays(crew, [], 52)
    assert float(inferred["hire_hour_wage"][0]) == pytest.approx(21.0)
    got = compute_labor_arrays(crew, [], 52, hired_wage_per_hr=None)
    assert float(got["hire_hour_wage"][0]) == pytest.approx(21.0), (
        "hired_wage_per_hr=None (blank) must mean INFER, never $0.00/hr"
    )
    # The docstring used to claim empty-string and 0 were covered here while the loop tested only
    # None — and those two were exactly the inputs that failed. They are refused now, and that is
    # asserted where refusal lives, in test_an_unusable_explicit_wage_is_refused_not_silently_accepted.


def test_an_extra_way_to_buy_labour_can_never_make_the_plan_worse(minimal_params):
    """A free option is worth >= 0. The reported P&L has to agree.

    The hire/overtime split used to be RECONSTRUCTED — fill hired labour to its cap, give the
    rest to overtime — on the reasoning that hire is cheaper. W15 decoupled the two prices, so
    that stopped being a fact. Measured with a $20/hr crew, 1.5x overtime and a $60/hr hired
    wage: the same 105.52 bought hours were all reported as hire, so ENABLING an extra and more
    expensive option made reported profit $3,165.71 WORSE than not having it.

    The objective never made that mistake — it priced both and chose. Only the REPORT was wrong,
    which is the harder kind to notice: every downstream figure (hire_cost, overtime_cost,
    total_cost, operating_profit, the cash curve, the P&L rows) inherited it, and the P&L's
    UNRECONCILED tripwire could not fire because both sides came from the same guess.
    """
    crew = [{"position": "Hand", "count": 1, "type": "hourly", "wage": 20.0,
             "hours_per_week": 40.0, "benefits_pct": 0.0}]
    base = dict(minimal_params, opening_cash=5_000_000.0, credit_line=5_000_000.0,
                year_round_employees=crew, seasonal_employees=[],
                overtime_enabled=True, max_overtime_hrs_per_week=2_000.0,
                overtime_rate_multiplier=1.5)
    ot_only = solve_farm_v2(**base)
    with_costly_hire = solve_farm_v2(**dict(
        base, hire_enabled=True, max_hire_hrs_per_week=2_000.0,
        hire_wage_markup=0.0, hired_wage_per_hr=60.0))
    assert ot_only["status"] == "optimal" and with_costly_hire["status"] == "optimal"
    assert with_costly_hire["profit"] >= ot_only["profit"] - 0.01, (
        f"adding a $60/hr hiring option to a farm with $30/hr overtime made reported profit "
        f"${ot_only['profit'] - with_costly_hire['profit']:,.2f} WORSE. An option the optimizer "
        f"can decline cannot cost anything — the reported split is not the solved one."
    )
    # And it must actually decline it, or the fixture is not exercising the choice.
    assert with_costly_hire["total_hired_hours"] == pytest.approx(0.0, abs=1e-6), (
        "the dearer option was taken anyway; this fixture cannot tell a solved split from a "
        "reconstructed one"
    )
    assert with_costly_hire["total_overtime_hours"] > 0


def test_the_double_charge_identity_is_the_100_percent_field_time_case(minimal_params):
    """The identity above is exact only when field_time_pct is 100, and the shipped farm is not.

    Its manager is 80% and both operators 90%, so 17 h/wk are paid by the committed bill and
    invisible to C2 — overtime can be bought while those paid hours are unspent. That is the
    DELIBERATE reading (`field_time_pct` is a cap on crop-available time, not an average: the
    unspent hours are admin and maintenance), but it means the clean $1,100 identity is a special
    case. Pinned so nobody generalises the comment: at 50% field time the committed bill is
    unchanged while capacity halves, so overtime starts at half the hours.
    """
    from farm_v2.utils.labor import compute_labor_arrays
    full = [{"position": "Hand", "count": 1, "type": "hourly", "wage": 20.0,
             "hours_per_week": 40.0, "benefits_pct": 0.0, "field_time_pct": 100}]
    half = [dict(full[0], field_time_pct=50)]
    a, b = compute_labor_arrays(full, [], 52), compute_labor_arrays(half, [], 52)
    assert float(a["committed_weekly_wages"][0]) == pytest.approx(
        float(b["committed_weekly_wages"][0])), "the wage bill must not move with field time"
    assert float(b["labor_capacity"][0]) == pytest.approx(float(a["labor_capacity"][0]) / 2)
    # So paid-but-uncroppable hours exist, and C2 cannot see them. That is the gap the comment
    # in solver.py now names instead of claiming the identity holds generally.
    paid_hours = 40.0
    assert float(b["labor_capacity"][0]) < paid_hours
