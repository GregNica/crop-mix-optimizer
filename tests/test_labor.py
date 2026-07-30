"""Unit tests for farm_v2.utils.labor."""
import pytest
import numpy as np
from farm_v2.utils.labor import compute_labor_arrays, compute_labor_rates
from farm_v2.utils.calendar import generate_successions


SALARIED_MANAGER = {
    "position": "Manager",
    "count": 1,
    "type": "salary",
    "wage": 60_000,
    "hours_per_week": 40,
}

HOURLY_WORKER = {
    "position": "Field Hand",
    "count": 5,
    "type": "salary",   # year-round hourly treated as salary here
    "wage": 37_440,     # $18/hr × 40hr × 52wk
    "hours_per_week": 40,
}

SEASONAL_FT = {
    "position": "Seasonal Crew",
    "count": 10,
    "type": "FT",
    "start_week": 10,
    "end_week": 40,
    "wage": 18.0,
    "hours_per_week": 40,
}

SEASONAL_PT = {
    "position": "Harvest Help",
    "count": 4,
    "type": "PT",
    "start_week": 20,
    "end_week": 35,
    "wage": 18.0,
    "hours_per_week": 20,
}


class TestComputeLaborArrays:
    def test_returns_dict_with_required_keys(self):
        result = compute_labor_arrays([SALARIED_MANAGER], [])
        assert "labor_capacity" in result
        assert "committed_weekly_wages" in result

    def test_no_employees_zero_capacity(self):
        result = compute_labor_arrays([], [])
        assert np.all(result["labor_capacity"] == 0)
        assert np.all(result["committed_weekly_wages"] == 0.0)

    def test_salaried_contributes_to_capacity_all_weeks(self):
        result = compute_labor_arrays([SALARIED_MANAGER], [])
        cap = result["labor_capacity"]
        assert cap.shape == (52,)
        # Salaried manager works all 52 weeks
        assert np.all(cap > 0)

    def test_seasonal_only_active_in_window(self):
        result = compute_labor_arrays([], [SEASONAL_FT])
        cap = result["labor_capacity"]
        # Weeks before start and after end should be 0
        assert np.all(cap[:9] == 0)   # weeks 0–8 (0-indexed)
        assert np.all(cap[10:40] > 0)  # weeks 10–39 active
        assert np.all(cap[40:] == 0)  # weeks 40–51

    def test_more_workers_more_capacity(self):
        fewer = compute_labor_arrays([], [SEASONAL_FT])
        more_emp = {**SEASONAL_FT, "count": 20}
        more = compute_labor_arrays([], [more_emp])
        assert np.all(more["labor_capacity"] >= fewer["labor_capacity"])

    def test_a_salary_is_charged_as_an_annual_wage_over_52_weeks(self):
        """Was `salaried_weekly_cost`, deleted with W14 — that output had no consumer left once
        W12 folded every worker's pay into one committed bill. The property it pinned is real and
        still worth pinning, so it moved to the key that carries it."""
        result = compute_labor_arrays([SALARIED_MANAGER], [])
        expected = SALARIED_MANAGER["wage"] / 52
        assert abs(result["committed_weekly_wages"][0] - expected) < 0.01
        assert abs(float(result["committed_weekly_wages"].sum())
                   - SALARIED_MANAGER["wage"]) < 0.01

    def test_seasonal_pt_half_capacity_of_ft(self):
        ft = compute_labor_arrays([], [SEASONAL_FT])
        pt_equiv = {**SEASONAL_PT, "count": 20, "start_week": 10, "end_week": 40}
        pt = compute_labor_arrays([], [pt_equiv])
        # PT at 20hrs vs FT at 40hrs with same count → half capacity
        active_w = 25  # a week inside both windows (0-indexed: w10..w40 → index 15)
        assert abs(pt["labor_capacity"][15] - ft["labor_capacity"][15]) < 1.0

    def test_multiple_seasonal_employees_additive(self):
        single = compute_labor_arrays([], [SEASONAL_FT])
        double = compute_labor_arrays([], [SEASONAL_FT, SEASONAL_FT])
        # In active weeks capacity should roughly double
        active_idx = 20  # index inside window
        assert abs(double["labor_capacity"][active_idx] / single["labor_capacity"][active_idx] - 2.0) < 0.01


class TestComputeLaborRates:
    def test_shape(self, spinach_crop, cucumber_crop):
        succs = generate_successions([spinach_crop, cucumber_crop])
        rates = compute_labor_rates(succs, [spinach_crop, cucumber_crop])
        assert rates.shape == (len(succs), 53)

    def test_inactive_weeks_are_zero(self, spinach_crop):
        succs = generate_successions([spinach_crop])
        rates = compute_labor_rates(succs, [spinach_crop])
        for i, s in enumerate(succs):
            active = set(s["weeks"])
            for w in range(1, 53):
                if w not in active:
                    assert rates[i, w] == 0.0

    def test_harvest_phase_higher_labor(self, spinach_crop):
        """Harvest labor > grow labor for spinach."""
        assert spinach_crop["labor_harv"] > spinach_crop["labor_grow"]
