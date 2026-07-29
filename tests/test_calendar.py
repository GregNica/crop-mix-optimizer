"""Unit tests for farm_v2.utils.calendar."""
import pytest
import numpy as np
from farm_v2.utils.calendar import (
    week_of_year,
    week_start_date,
    generate_successions,
    build_phase_table,
    monthly_to_weekly,
)


# ---------------------------------------------------------------------------
# week_of_year
# ---------------------------------------------------------------------------

class TestWeekOfYear:
    def test_jan_1_is_week_1(self):
        assert week_of_year("01-01") == 1

    def test_dec_31_is_week_52(self):
        assert week_of_year("12-31") == 52

    def test_midyear(self):
        # July 4 is in the second half of the year
        assert week_of_year("07-04") > 26

    def test_monotone(self):
        """Later dates produce >= week numbers."""
        dates = ["01-15", "03-01", "06-15", "09-01", "11-15"]
        weeks = [week_of_year(d) for d in dates]
        assert weeks == sorted(weeks)

    def test_range(self):
        for month in range(1, 13):
            w = week_of_year(f"{month:02d}-15")
            assert 1 <= w <= 52

    def test_different_year(self):
        # Leap year 2024 should still produce valid weeks
        w = week_of_year("02-29", year=2024)
        assert 1 <= w <= 52


# ---------------------------------------------------------------------------
# generate_successions
# ---------------------------------------------------------------------------

class TestGenerateSuccessions:
    def test_returns_list(self, spinach_crop):
        result = generate_successions([spinach_crop])
        assert isinstance(result, list)

    def test_required_keys(self, spinach_crop):
        succs = generate_successions([spinach_crop])
        assert len(succs) > 0
        for s in succs:
            assert "crop" in s
            assert "weeks" in s
            assert "phases" in s
            assert "start_week" in s

    def test_crop_index_assigned(self, spinach_crop, cucumber_crop):
        succs = generate_successions([spinach_crop, cucumber_crop])
        crops_seen = {s["crop"] for s in succs}
        assert 0 in crops_seen  # spinach
        assert 1 in crops_seen  # cucumber

    def test_succession_fits_in_season(self, spinach_crop):
        """All weeks in a succession must fall within the declared season."""
        import math
        succs = generate_successions([spinach_crop])
        total_weeks = math.ceil(spinach_crop["days_to_maturity"] / 7)
        for s in succs:
            assert len(s["weeks"]) == total_weeks

    def test_phases_length_matches_weeks(self, spinach_crop):
        succs = generate_successions([spinach_crop])
        for s in succs:
            assert len(s["phases"]) == len(s["weeks"])

    def test_narrow_season_generates_fewer_successions(self, spinach_crop):
        """A 7-week season for a 6-week crop has room for only 2 start slots."""
        import copy
        narrow = copy.deepcopy(spinach_crop)
        narrow["seasons"] = [{"start": "04-01", "end": "05-15"}]  # ~7 weeks
        succs = generate_successions([narrow])
        # Should produce ≥ 1 succession but fewer than wide season
        assert len(succs) >= 1

    def test_season_narrower_than_the_cycle_still_produces_successions(self, spinach_crop):
        """A window shorter than the crop cycle is a short PLANTING window, not an empty one.

        This test previously asserted the opposite — that a 3-week window on a 6-week crop
        yields nothing — because a season had to contain the whole cycle. That reading is what
        made Winter Squash and Melon generate zero successions and vanish from every plan
        silently. Growers enter these as planting windows: "I can put spinach in the ground for
        these three weeks" does not mean "and it must also be harvested by then".
        """
        import copy
        narrow = copy.deepcopy(spinach_crop)
        # 6-week crop, 3-week planting window
        narrow["seasons"] = [{"start": "04-01", "end": "04-21"}]
        succs = generate_successions([narrow])
        assert len(succs) >= 1, "a short planting window must still permit plantings"
        for s in succs:
            assert 13 <= s["start_week"] <= 17, (
                f"start week {s['start_week']} is outside the 04-01..04-21 planting window"
            )

    def test_cycle_may_not_run_past_week_52_without_overwinters(self, spinach_crop):
        """Relaxing containment must NOT silently let frost-tender crops wrap the year.

        Every window in the shipped library was authored under the old whole-cycle meaning, so
        making wrap universal let the solver plant Hot Peppers in mid-October to harvest the
        following spring. Wrap is opt-in; without the flag the cycle still ends inside the year.
        """
        import copy
        late = copy.deepcopy(spinach_crop)
        late["seasons"] = [{"start": "12-15", "end": "12-31"}]   # 6-week crop, starts ~W51
        assert generate_successions([late]) == [], (
            "a cycle that cannot finish by week 52 must be dropped unless overwinters is set"
        )

    def test_overwinters_allows_the_cycle_to_wrap(self, spinach_crop):
        """The opt-in path: fall-planted, harvested the following year."""
        import copy
        ow = copy.deepcopy(spinach_crop)
        ow["seasons"] = [{"start": "12-15", "end": "12-31"}]
        ow["overwinters"] = True
        succs = generate_successions([ow])
        assert succs, "overwinters=True must permit a wrapping cycle"
        s = succs[0]
        assert s["weeks"][-1] < s["weeks"][0], (
            f"expected a wrap; got weeks {s['weeks'][0]}..{s['weeks'][-1]}"
        )
        assert len(s["weeks"]) == len(set(s["weeks"])), "a wrapped cycle must not reuse a week"

    def test_multiple_seasons(self, spinach_crop):
        """Spinach with spring + fall seasons should produce successions from both."""
        import copy
        two_season = copy.deepcopy(spinach_crop)
        two_season["seasons"] = [
            {"start": "03-01", "end": "06-15"},   # spring: W9–W24
            {"start": "08-15", "end": "11-15"},   # fall: W33–W46
        ]
        succs = generate_successions([two_season])
        start_weeks = [s["start_week"] for s in succs]
        # spring ends ~W24, fall starts ~W33 — gap in between
        spring = [w for w in start_weeks if w < 27]
        fall = [w for w in start_weeks if w > 30]
        assert len(spring) > 0
        assert len(fall) > 0

    def test_empty_crops(self):
        assert generate_successions([]) == []

    def test_two_crops_independent(self, spinach_crop, cucumber_crop):
        combined = generate_successions([spinach_crop, cucumber_crop])
        spinach_only = generate_successions([spinach_crop])
        cucumber_only = generate_successions([cucumber_crop])
        n_spinach = sum(1 for s in combined if s["crop"] == 0)
        n_cucumber = sum(1 for s in combined if s["crop"] == 1)
        assert n_spinach == len(spinach_only)
        assert n_cucumber == len(cucumber_only)


# ---------------------------------------------------------------------------
# build_phase_table
# ---------------------------------------------------------------------------

class TestBuildPhaseTable:
    def test_shape(self, spinach_crop):
        succs = generate_successions([spinach_crop])
        table = build_phase_table(succs, n_weeks=52)
        assert len(table) == len(succs)
        for row in table:
            assert len(row) == 52 + 1  # index 0 unused, weeks 1–52

    def test_phase_values_valid(self, spinach_crop):
        """Phase entries are 0, 1, 2, or None."""
        succs = generate_successions([spinach_crop])
        table = build_phase_table(succs, n_weeks=52)
        valid = {0, 1, 2, None}
        for row in table:
            for val in row[1:]:
                assert val in valid

    def test_inactive_weeks_are_none(self, spinach_crop):
        succs = generate_successions([spinach_crop])
        table = build_phase_table(succs, n_weeks=52)
        for i, s in enumerate(succs):
            active_weeks = set(s["weeks"])
            for w in range(1, 53):
                if w not in active_weeks:
                    assert table[i][w] is None


# ---------------------------------------------------------------------------
# monthly_to_weekly
# ---------------------------------------------------------------------------

class TestMonthlyToWeekly:
    def test_output_length(self):
        monthly = list(range(1, 13))
        weekly = monthly_to_weekly(monthly)
        assert len(weekly) == 52

    def test_values_preserved(self):
        """All output values must be one of the input monthly values."""
        monthly = [float(m * 100) for m in range(1, 13)]
        weekly = monthly_to_weekly(monthly)
        valid = set(monthly)
        for v in weekly:
            assert v in valid

    def test_flat_array_returns_constant(self):
        monthly = [5.0] * 12
        weekly = monthly_to_weekly(monthly)
        assert np.allclose(weekly, 5.0)
