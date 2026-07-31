"""Unit tests for farm_v2.validate."""
import copy
import pytest
import numpy as np
from farm_v2.validate import validate_params


# ---------------------------------------------------------------------------
# Helper: call validate with minimal valid params easily overridden
# ---------------------------------------------------------------------------

def _call(params, **overrides):
    """Merge overrides into params and call validate_params."""
    p = {**params, **overrides}
    return validate_params(**p)


# ---------------------------------------------------------------------------
# Valid params — should pass without error
# ---------------------------------------------------------------------------

class TestValidParamsPass:
    def test_minimal_params_passes(self, minimal_params):
        warnings = validate_params(**minimal_params)
        assert isinstance(warnings, list)

    def test_two_crop_passes(self, two_crop_params):
        warnings = validate_params(**two_crop_params)
        assert isinstance(warnings, list)

    def test_returns_list(self, minimal_params):
        result = validate_params(**minimal_params)
        assert isinstance(result, list)

    def test_no_employees_produces_warning_not_error(self, minimal_params):
        p = copy.deepcopy(minimal_params)
        p["year_round_employees"] = []
        p["seasonal_employees"] = []
        warnings = validate_params(**p)
        assert any("employee" in w.lower() or "labor" in w.lower() for w in warnings)

    def test_no_water_source_produces_warning(self, minimal_params):
        p = copy.deepcopy(minimal_params)
        p["well_enabled"] = False
        p["catchment_enabled"] = False
        p["city_water_enabled"] = False
        warnings = validate_params(**p)
        assert any("water" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Farm infrastructure — fatal errors
# ---------------------------------------------------------------------------

class TestFarmInfrastructure:
    def test_negative_land_raises(self, minimal_params):
        with pytest.raises(ValueError, match="total_land"):
            _call(minimal_params, total_land=-1.0)

    def test_zero_land_raises(self, minimal_params):
        with pytest.raises(ValueError, match="total_land"):
            _call(minimal_params, total_land=0.0)

    def test_zero_harvest_storage_raises(self, minimal_params):
        with pytest.raises(ValueError, match="harvest_storage_cap"):
            _call(minimal_params, harvest_storage_cap=0.0)

    def test_negative_opening_cash_raises(self, minimal_params):
        with pytest.raises(ValueError, match="opening_cash"):
            _call(minimal_params, opening_cash=-1.0)

    def test_negative_credit_line_raises(self, minimal_params):
        with pytest.raises(ValueError, match="credit_line"):
            _call(minimal_params, credit_line=-100.0)

    def test_operating_weeks_zero_raises(self, minimal_params):
        with pytest.raises(ValueError, match="operating_weeks"):
            _call(minimal_params, operating_weeks=0)

    def test_operating_weeks_53_raises(self, minimal_params):
        with pytest.raises(ValueError, match="operating_weeks"):
            _call(minimal_params, operating_weeks=53)


# ---------------------------------------------------------------------------
# Rainfall array
# ---------------------------------------------------------------------------

class TestRainfallValidation:
    def test_wrong_length_raises(self, minimal_params):
        with pytest.raises(ValueError, match="52"):
            _call(minimal_params, rainfall_weekly_L_per_acre=np.zeros(51))

    def test_negative_value_raises(self, minimal_params):
        rain = np.full(52, 100.0)
        rain[10] = -1.0
        with pytest.raises(ValueError, match="negative"):
            _call(minimal_params, rainfall_weekly_L_per_acre=rain)

    def test_all_zeros_passes(self, minimal_params):
        _call(minimal_params, rainfall_weekly_L_per_acre=np.zeros(52))


# ---------------------------------------------------------------------------
# Water sources
# ---------------------------------------------------------------------------

class TestWaterValidation:
    def test_catchment_enabled_zero_area_raises(self, minimal_params):
        with pytest.raises(ValueError, match="catchment_surface_area_m2"):
            _call(minimal_params, catchment_enabled=True, catchment_surface_area_m2=0.0)

    def test_well_enabled_zero_cap_raises(self, minimal_params):
        with pytest.raises(ValueError, match="well_weekly_cap_L"):
            _call(minimal_params, well_enabled=True, well_weekly_cap_L=0.0)


# ---------------------------------------------------------------------------
# Crops
# ---------------------------------------------------------------------------

class TestCropValidation:
    def test_no_crops_raises(self, minimal_params):
        with pytest.raises(ValueError, match="[Cc]rop"):
            _call(minimal_params, crops=[])

    def test_missing_required_key_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        del bad["yield_per_acre"]
        with pytest.raises(ValueError, match="yield_per_acre"):
            _call(minimal_params, crops=[bad])

    def test_days_to_maturity_too_short_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["days_to_maturity"] = 3  # < 7
        with pytest.raises(ValueError, match="days_to_maturity"):
            _call(minimal_params, crops=[bad])

    def test_planting_plus_harvest_exceeds_cycle_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["planting_weeks"] = 5
        bad["harvest_weeks"] = 5
        # days_to_maturity=42 → 6 total weeks; 5+5=10 > 6
        with pytest.raises(ValueError, match="planting_weeks|harvest_weeks"):
            _call(minimal_params, crops=[bad])

    def test_zero_yield_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["yield_per_acre"] = 0
        with pytest.raises(ValueError, match="yield_per_acre"):
            _call(minimal_params, crops=[bad])

    def test_no_seasons_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["seasons"] = []
        with pytest.raises(ValueError, match="season"):
            _call(minimal_params, crops=[bad])

    def test_season_end_before_start_is_a_wrapping_window_not_an_error(
            self, minimal_params, spinach_crop):
        """A window that ends before it starts WRAPS the year — Sept-to-March planting.

        This used to raise. generate_successions handles it explicitly (B6), so rejecting it
        here contradicted the generator and would have failed exactly the fall-planted crops
        the wrap exists to support.
        """
        wrapping = copy.deepcopy(spinach_crop)
        wrapping["seasons"] = [{"start": "09-01", "end": "03-01"}]
        _call(minimal_params, crops=[wrapping])   # must not raise

    def test_diversity_max_out_of_range_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["crop_diversity_max"] = 0.0   # must be > 0
        with pytest.raises(ValueError, match="crop_diversity_max"):
            _call(minimal_params, crops=[bad])

    def test_diversity_max_above_1_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["crop_diversity_max"] = 1.5
        with pytest.raises(ValueError, match="crop_diversity_max"):
            _call(minimal_params, crops=[bad])

    def test_narrow_season_window_no_longer_warns(self, minimal_params, spinach_crop):
        """A window shorter than the cycle is a short PLANTING window, not an empty one.

        The old warning said "No successions will be generated for this window" — which was the
        B5 defect stated as if it were intended behaviour. A grower acting on it would widen a
        window for no reason and change their plan.
        """
        narrow = copy.deepcopy(spinach_crop)
        narrow["seasons"] = [{"start": "04-01", "end": "04-28"}]   # 4 weeks, 6-week crop
        warnings = _call(minimal_params, crops=[narrow])
        assert not any("no successions" in w.lower() for w in warnings), (
            f"validator still claims a narrow window yields nothing: {warnings}"
        )

    def test_late_window_without_overwinters_warns(self, minimal_params, spinach_crop):
        """The replacement warning: start weeks whose cycle would run past week 52 are skipped."""
        late = copy.deepcopy(spinach_crop)
        # A workable window alongside the late one, so the crop still generates successions —
        # otherwise the "no successions at all" error fires first and there are no warnings.
        late["seasons"] = [{"start": "04-01", "end": "06-15"},
                           {"start": "12-01", "end": "12-24"}]
        warnings = _call(minimal_params, crops=[late])
        assert any("past week 52" in w for w in warnings), (
            f"expected a skipped-start-weeks warning, got {warnings}"
        )

    def test_late_window_with_overwinters_does_not_warn(self, minimal_params, spinach_crop):
        """...and it must go quiet once the crop declares it overwinters."""
        ow = copy.deepcopy(spinach_crop)
        ow["seasons"] = [{"start": "04-01", "end": "06-15"},
                         {"start": "12-01", "end": "12-24"}]
        ow["overwinters"] = True
        warnings = _call(minimal_params, crops=[ow])
        assert not any("past week 52" in w for w in warnings), (
            f"an overwintering crop must not be warned about wrapping: {warnings}"
        )

    def test_missing_price_per_lb_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        del bad["channels"]["Direct"]["price_per_lb"]
        with pytest.raises(ValueError, match="price_per_lb"):
            _call(minimal_params, crops=[bad])

    def test_invalid_demand_cap_type_raises(self, minimal_params, spinach_crop):
        bad = copy.deepcopy(spinach_crop)
        bad["channels"]["Direct"]["demand_cap_type"] = "monthly"  # invalid
        with pytest.raises(ValueError, match="demand_cap_type"):
            _call(minimal_params, crops=[bad])


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------

class TestChannelValidation:
    def test_no_channels_raises(self, minimal_params):
        with pytest.raises(ValueError, match="channel"):
            _call(minimal_params, channels=[])

    def test_duplicate_channel_names_raises(self, minimal_params):
        with pytest.raises(ValueError, match="unique"):
            _call(minimal_params, channels=[{"name": "A"}, {"name": "A"}])


# ---------------------------------------------------------------------------
# Demand warnings
# ---------------------------------------------------------------------------

class TestDemandWarnings:
    def test_no_demand_produces_warning(self, minimal_params, spinach_crop):
        p = copy.deepcopy(minimal_params)
        bad_crop = copy.deepcopy(spinach_crop)
        bad_crop["channels"]["Direct"]["weekly_demand_lbs"] = 0
        p["crops"] = [bad_crop]
        warnings = validate_params(**p)
        assert any("demand" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Employees — the seasonal path must be as strict as the year-round one
# (W-review 2026-07-31: a seasonal wage of -18 passed every check and booked
# payroll as INCOME — fixed_cost_split['wages'] = -$220,800, a $561,600 phantom
# profit swing — while also turning the inferred hire price negative, so the
# optimizer was PAID per hired hour.)
# ---------------------------------------------------------------------------

def _seasonal(**overrides):
    emp = {"position": "Crew", "count": 2, "type": "FT", "wage": 18.0,
           "hours_per_week": 40, "start_week": 10, "end_week": 40}
    emp.update(overrides)
    return emp


class TestEmployeeValidation:
    def test_negative_seasonal_wage_raises(self, minimal_params):
        with pytest.raises(ValueError, match="wage"):
            _call(minimal_params, seasonal_employees=[_seasonal(wage=-18.0)])

    def test_zero_seasonal_wage_is_allowed(self, minimal_params):
        # Unpaid family / piece-rate roles are legitimate; the solver refuses to
        # SELL flex hours at that price, but the roster itself is valid.
        _call(minimal_params, seasonal_employees=[_seasonal(wage=0.0)])

    def test_nonpositive_seasonal_hours_raise(self, minimal_params):
        with pytest.raises(ValueError, match="hours_per_week"):
            _call(minimal_params, seasonal_employees=[_seasonal(hours_per_week=-40)])
        with pytest.raises(ValueError, match="hours_per_week"):
            _call(minimal_params, seasonal_employees=[_seasonal(hours_per_week=0)])

    @pytest.mark.parametrize("key,val", [
        ("wage", None), ("wage", "18"), ("hours_per_week", None),
        ("count", None), ("start_week", None), ("end_week", "40"),
    ])
    def test_non_numeric_seasonal_fields_raise_value_error(self, minimal_params, key, val):
        # ValueError specifically: Step 0 converts it to `invalid_input`, while a
        # TypeError from `None < 0` would fail OPEN with only a warning.
        with pytest.raises(ValueError, match=key):
            _call(minimal_params, seasonal_employees=[_seasonal(**{key: val})])

    @pytest.mark.parametrize("key,val", [
        ("wage", None), ("wage", "18"), ("hours_per_week", None), ("count", None),
    ])
    def test_non_numeric_year_round_fields_raise_value_error(self, minimal_params, key, val):
        emp = {"position": "Hand", "count": 1, "type": "hourly",
               "wage": 20.0, "hours_per_week": 40}
        emp[key] = val
        with pytest.raises(ValueError, match=key):
            _call(minimal_params, year_round_employees=[emp])
