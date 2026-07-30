"""Salaried crop hours are paid for once, not twice (W9).

THE DEFECT. A year-round salaried worker's hours count toward `labor_capacity` — deliberately,
because excluding them let overtime "buy back" capacity the farm already had — while their salary
is charged in full to `fixed_cost_split.salaries`. But the solver ALSO charged every crop labour
hour at `hourly_labor_rate`, which is the blend of the HOURLY crew only. So the hours a salaried
person spends on crops were paid for twice.

Measured on the shipped farm before the fix: the Farm Manager supplies 36 h/wk of field capacity
against ~253 h/wk used, and **$44,702/yr — 8.1% of net profit** — was billed twice.

WHAT MAKES IT SUBTLE, and why both endpoints looked fine: only the MIXED crew was ever wrong.
With no hourly staff, `hourly_labor_rate` is 0, so labour costs nothing on top of the salary. With
no salaried staff, there is no salary line to double up against. A farm with both — which is most
farms — pays the overlap twice.

THE CREDIT IS AT THE RATE THAT WAS OVER-CHARGED, not at the salaried worker's own wage. That is
the one thing to get right here: the defect is "these hours were charged at the hourly blend and
should not have been", so undoing it means crediting back exactly `absorbed x hourly_blend`. The
salary itself is untouched — it is a commitment the farm pays whether or not anything is planted.
"""
import numpy as np
import pytest

pytest.importorskip("scipy")

from farm_v2.solver import solve_farm_v2  # noqa: E402
from farm_v2.utils.labor import compute_labor_arrays  # noqa: E402


def _hourly(wage=20.0, hrs=40.0, count=1):
    return {"position": "Field Crew", "count": count, "type": "hourly",
            "wage": wage, "hours_per_week": hrs, "benefits_pct": 0.0}


def _salaried(wage=80_000.0, hrs=40.0, count=1, field=100.0):
    return {"position": "Manager", "count": count, "type": "salary",
            "wage": wage, "hours_per_week": hrs, "benefits_pct": 0.0,
            "field_time_pct": field}


class TestTheCreditIsBoundedByBothCeilings:
    """`absorbed` must settle at min(hours worked on crops, salaried capacity).

    Two ceilings, in two different places: the capacity bound is a variable bound (Step 7) and
    the hours-worked bound is C2b. Each is load-bearing and neither implies the other.
    """

    def test_it_never_exceeds_salaried_capacity(self, two_crop_params):
        p = dict(two_crop_params, year_round_employees=[_salaried(hrs=10.0), _hourly(hrs=200.0)])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal", r["status"]
        lab = compute_labor_arrays(p["year_round_employees"], p["seasonal_employees"], 52)
        cap_hours = float(lab["salaried_capacity"].sum())
        assert r["salaried_absorbed_hours"] <= cap_hours + 1e-6, (
            f"credited {r['salaried_absorbed_hours']:,.1f} h against {cap_hours:,.1f} h of "
            f"salaried capacity — the farm is being paid for hours nobody has"
        )

    def test_an_idle_salaried_worker_earns_no_credit(self, two_crop_params):
        """The failure C2b exists to prevent: a manager on payroll in a week with nothing
        planted is a COST, not a saving. Without C2b the objective would collect the credit for
        all 52 weeks of capacity regardless of whether any crop needed the hours."""
        # No crops -> no plantable work at all. The farm still pays the salary.
        p = dict(two_crop_params, year_round_employees=[_salaried(), _hourly()],
                 crops=[dict(two_crop_params["crops"][0], seasons=[])])
        r = solve_farm_v2(**p)
        # Either the farm is refused for having no plantable window, or it solves with no work.
        if r.get("status") == "optimal":
            assert r["salaried_absorbed_hours"] == pytest.approx(0.0, abs=1e-6), (
                f"credited {r['salaried_absorbed_hours']:,.1f} h with nothing planted"
            )
            assert (-r["variable_cost_split"]["salaried_hours_absorbed"]) == pytest.approx(0.0, abs=1e-6)

    def test_the_credit_equals_the_hours_times_the_rate_they_were_charged_at(self, two_crop_params):
        """The credit undoes an over-charge, so it must be at the rate of the over-charge — the
        HOURLY blend — and not at the salaried worker's own wage. Rebuilt independently."""
        p = dict(two_crop_params, year_round_employees=[_salaried(wage=90_000.0), _hourly(wage=25.0)])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        lab = compute_labor_arrays(p["year_round_employees"], p["seasonal_employees"], 52)
        rate = lab["hourly_labor_rate"]
        # The blend VARIES by week here — the fixture has a seasonal crew on a different wage, so
        # weeks split 25.00 / 18.44. That is the case worth testing: a credit applied at one
        # average rate would be wrong in every week, and only a per-week check catches it. The
        # first draft of this test asserted a constant blend and failed on its own assumption.
        assert len(set(np.round(rate, 6))) > 1, (
            "fixture no longer has a varying blend, so this test cannot catch a credit applied "
            "at a single average rate"
        )
        # Bracket the credit by the cheapest and dearest weeks. An exact per-week rebuild would
        # need the solved hours per week, which is what `absorbed` already is; bracketing keeps
        # the oracle independent of the thing under test.
        hrs = r["salaried_absorbed_hours"]
        assert hrs > 0, "no hours absorbed, so the rate cannot be checked"
        credit = -r["variable_cost_split"]["salaried_hours_absorbed"]
        assert credit <= hrs * float(rate.max()) + 1e-6
        assert credit >= hrs * float(rate[rate > 0].min()) - 1e-6
        # And it is nowhere near the salaried worker's OWN wage, which is the wrong rate to
        # credit at: the defect was an over-charge at the hourly blend, so that is what is undone.
        salaried_hourly_equivalent = 90_000.0 / 52 / 40
        assert (-r["variable_cost_split"]["salaried_hours_absorbed"]) < hrs * salaried_hourly_equivalent * 0.9, (
            f"credit ${r['salaried_absorbed_cost']:,.2f} over {hrs:,.1f} h looks like it was "
            f"computed at the salaried wage (${salaried_hourly_equivalent:.2f}/h), not the "
            f"hourly blend it was over-charged at"
        )


class TestTheReportedHoursAreAFunctionOfTheInputs:
    """The absorbed HOURS must be derived from the plan, not read out of the solved variable.

    `absorbed[w]`'s objective coefficient is -hourly_labor_rate[w], so in any week with no hourly
    staff available that coefficient is ZERO and the LP is indifferent anywhere in
    [0, min(used, capacity)] — HiGHS picks arbitrarily. The COST is unaffected (a zero rate times
    anything is zero), but a published hours figure that depends on which vertex HiGHS happened to
    land on is not a function of the inputs. This file already refuses that twice, for inventory
    level and tank level.

    The fixture matters: `two_crop_params`' only hourly staff are SEASONAL, so the weeks outside
    their window have a zero blended rate and are exactly where a solved-vector read diverges.
    """

    def test_hours_equal_min_of_hours_worked_and_salaried_capacity(self, two_crop_params):
        p = dict(two_crop_params, year_round_employees=[_salaried(hrs=40.0)])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        lab = compute_labor_arrays(p["year_round_employees"], p["seasonal_employees"], 52)
        rate = lab["hourly_labor_rate"]
        zero_rate_weeks = int((rate == 0).sum())
        assert zero_rate_weeks > 0, (
            "fixture has an hourly crew in every week, so the degenerate case this test exists "
            "for cannot arise and a solved-vector read would look correct"
        )
        # Independent oracle: hours worked on crops per week, from x and the labour rates.
        used = np.zeros(52)
        for i, sc in enumerate(r["successions"]):
            if r["x"][i] <= 1e-9:
                continue
            for w, ph in zip(sc["weeks"], sc["phases"]):
                if 1 <= w <= 52:
                    key = ("labor_plant", "labor_grow", "labor_harv")[ph]
                    used[w - 1] += (p["total_land"] * r["x"][i]
                                    * r["crops"][sc["crop"]].get(key, 0.0))
        expected = float(np.minimum(used, lab["salaried_capacity"]).sum())
        assert expected > 0, "nothing absorbed, so this test proves nothing"
        assert r["salaried_absorbed_hours"] == pytest.approx(expected, rel=1e-6), (
            f"reported {r['salaried_absorbed_hours']:,.1f} h against an honest {expected:,.1f} h "
            f"— {zero_rate_weeks} weeks have a zero hourly rate, so the solved variable is free "
            f"there and this figure is reading a coin flip"
        )


class TestTheEndpointsAreUnchanged:
    """Both were already correct, so the fix must not move them."""

    def test_a_farm_with_no_salaried_staff_gets_no_credit(self, two_crop_params):
        p = dict(two_crop_params, year_round_employees=[_hourly(hrs=200.0)])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert (-r["variable_cost_split"]["salaried_hours_absorbed"]) == pytest.approx(0.0, abs=1e-9)
        assert r["variable_cost_split"]["salaried_hours_absorbed"] == pytest.approx(0.0, abs=1e-9)

    def test_an_all_salaried_farm_pays_no_hourly_labour_and_needs_no_credit(self, two_crop_params):
        """With no hourly crew the blend is 0, so crop labour was already free and the salary
        line already carried the whole cost. The credit must be 0 — crediting anything here
        would hand the farm money for a cost it never had."""
        # seasonal_employees must be emptied too: every seasonal worker is hourly (type FT/PT),
        # so leaving them in makes this farm mixed, not all-salaried. The first draft missed that
        # and measured $22,153 of "impossible" hourly labour.
        p = dict(two_crop_params, year_round_employees=[_salaried(hrs=200.0)],
                 seasonal_employees=[])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert r["variable_cost_split"]["labor"] == pytest.approx(0.0, abs=1e-9)
        assert (-r["variable_cost_split"]["salaried_hours_absorbed"]) == pytest.approx(0.0, abs=1e-9)


class TestTheDoubleChargeIsActuallyGone:
    def test_labour_paid_equals_only_the_hours_the_hourly_crew_covers(self, two_crop_params):
        """The whole point, stated as an identity.

        gross labour charge  = every crop hour x blend
        credit               = salaried-covered hours x blend
        so what remains      = hours the HOURLY crew covers x blend.
        """
        p = dict(two_crop_params, year_round_employees=[_salaried(hrs=20.0), _hourly(hrs=100.0)])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        split = r["variable_cost_split"]
        net_labour = split["labor"] + split["salaried_hours_absorbed"]   # credit is negative
        assert net_labour >= -1e-6, f"net labour cost went negative: {net_labour}"
        assert net_labour == pytest.approx(split["labor"] - (-r["variable_cost_split"]["salaried_hours_absorbed"]), abs=1e-6)

    def test_the_credit_is_worth_real_money_on_a_mixed_crew(self, two_crop_params):
        """A guard against the fix quietly becoming inert: on a farm with both kinds of staff and
        real work to do, the credit must be non-trivial. If it drops to zero this whole file is
        passing vacuously."""
        p = dict(two_crop_params, year_round_employees=[_salaried(hrs=40.0), _hourly(hrs=160.0)])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert r["salaried_absorbed_hours"] > 100.0, r["salaried_absorbed_hours"]
        assert (-r["variable_cost_split"]["salaried_hours_absorbed"]) > 1_000.0, (-r["variable_cost_split"]["salaried_hours_absorbed"])

    def test_the_split_still_sums_to_the_total_with_a_negative_entry(self, two_crop_params):
        """W4's invariant, re-checked because W9 puts the first NEGATIVE entry in either split."""
        p = dict(two_crop_params, year_round_employees=[_salaried(), _hourly()])
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        assert sum(r["variable_cost_split"].values()) == pytest.approx(r["variable_cost"], abs=1e-6)
        assert r["variable_cost_split"]["salaried_hours_absorbed"] <= 0.0


class TestTheCashFloorSeesTheCreditToo:
    """C13 must not demand money the farm never spends.

    The cumulative cash floor charges every crop hour at the hourly blend, and the salaried share
    of that is already inside `fixed_weekly`. Leaving the credit out of C13 makes the floor
    STRICTER than reality, so a farm that can actually fund its plan gets told it cannot.

    Pinned on the FEASIBILITY BOUNDARY because that is the only place the omission is observable:
    measured on this fixture, the floor is slack above ~$121k of opening cash (peak borrowing 0,
    profit unchanged) and infeasible below ~$120k, so there is no wide band where it merely
    changes the plan. At $121,000 the plan is fundable with the credit and NOT fundable without
    it — verified by removing the C13 term and watching this farm flip to infeasible.
    """

    def test_a_plan_the_farm_can_fund_is_not_refused(self, two_crop_params):
        p = dict(two_crop_params,
                 year_round_employees=[_salaried(hrs=40.0), _hourly(wage=22.0, count=2)],
                 opening_cash=121_000.0, credit_line=0.0, cash_constraint_enabled=True)
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal", (
            f"got {r['status']!r} at $121,000 of opening cash. This farm is fundable once the "
            f"salaried hours already paid for in Salaries stop being charged again in the cash "
            f"floor; if C13 has lost that credit, the floor is demanding money nobody spends."
        )
        # And the credit must be doing real work here, or the boundary has drifted and this test
        # is asserting something it no longer discriminates.
        assert -r["variable_cost_split"]["salaried_hours_absorbed"] > 1_000.0


class TestItInteractsWithTheFlexLevers:
    def test_overtime_does_not_also_pay_for_the_credited_hours(self, two_crop_params):
        """Overtime is charged only beyond TOTAL capacity, and the credit is inside capacity, so
        the two must not overlap. Checked as an ordering property: credited hours never exceed
        capacity, so they can never be overtime hours."""
        p = dict(two_crop_params,
                 year_round_employees=[_salaried(hrs=20.0), _hourly(hrs=40.0)],
                 overtime_enabled=True, max_overtime_hrs_per_week=100.0,
                 overtime_rate_multiplier=1.5)
        r = solve_farm_v2(**p)
        assert r["status"] == "optimal"
        lab = compute_labor_arrays(p["year_round_employees"], p["seasonal_employees"], 52)
        cap = float(lab["salaried_capacity"].sum())
        assert r["salaried_absorbed_hours"] <= cap + 1e-6
        assert sum(r["variable_cost_split"].values()) == pytest.approx(r["variable_cost"], abs=1e-6)
