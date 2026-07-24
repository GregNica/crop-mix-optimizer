"""Unit tests for farm_v2.utils.water."""
import pytest
import numpy as np
from farm_v2.utils.water import (
    RAINFALL_BY_ZONE,
    compute_free_water,
    compute_net_water_rates,
)
from farm_v2.utils.calendar import generate_successions


# ---------------------------------------------------------------------------
# RAINFALL_BY_ZONE
# ---------------------------------------------------------------------------

class TestRainfallByZone:
    def test_six_zones_exist(self):
        expected = {
            "california_central_valley",
            "pacific_northwest",
            "southeast",
            "midwest",
            "northeast",
            "southwest_desert",
        }
        assert expected <= set(RAINFALL_BY_ZONE.keys())

    def test_each_zone_has_52_weeks(self):
        for zone, data in RAINFALL_BY_ZONE.items():
            arr = np.asarray(data)
            assert arr.shape == (52,), f"Zone {zone} has wrong shape: {arr.shape}"

    def test_no_negative_rainfall(self):
        for zone, data in RAINFALL_BY_ZONE.items():
            arr = np.asarray(data)
            assert (arr >= 0).all(), f"Zone {zone} has negative values"

    def test_zones_differ(self):
        """Different climate zones should have different rainfall profiles."""
        cv = np.asarray(RAINFALL_BY_ZONE["california_central_valley"])
        se = np.asarray(RAINFALL_BY_ZONE["southeast"])
        assert not np.allclose(cv, se)


# ---------------------------------------------------------------------------
# compute_free_water
# ---------------------------------------------------------------------------

class TestComputeFreeWater:
    def test_no_sources_returns_zeros(self, rainfall_flat):
        result = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_flat,
            catchment_enabled=False,
            well_enabled=False,
        )
        assert result.shape == (52,)
        assert np.all(result == 0)

    def test_well_only(self, rainfall_zero):
        cap = 500_000.0
        result = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_zero,
            well_enabled=True,
            well_weekly_cap_L=cap,
        )
        assert result.shape == (52,)
        assert np.all(result == cap)

    def test_catchment_proportional_to_rainfall(self, rainfall_flat):
        area = 1000.0  # m²
        result = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_flat,
            catchment_enabled=True,
            catchment_surface_area_m2=area,
        )
        assert result.shape == (52,)
        assert np.all(result > 0)

    def test_well_plus_catchment_additive(self, rainfall_flat):
        well_cap = 100_000.0
        well_only = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_flat,
            well_enabled=True,
            well_weekly_cap_L=well_cap,
        )
        combined = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_flat,
            well_enabled=True,
            well_weekly_cap_L=well_cap,
            catchment_enabled=True,
            catchment_surface_area_m2=500.0,
        )
        assert np.all(combined >= well_only)

    def test_zero_area_catchment_adds_nothing(self, rainfall_flat):
        no_catchment = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_flat,
            catchment_enabled=False,
        )
        zero_area = compute_free_water(
            rainfall_weekly_L_per_acre=rainfall_flat,
            catchment_enabled=True,
            catchment_surface_area_m2=0.0,
        )
        assert np.allclose(no_catchment, zero_area)


# ---------------------------------------------------------------------------
# compute_net_water_rates
# ---------------------------------------------------------------------------

class TestComputeNetWaterRates:
    def test_shape(self, spinach_crop, rainfall_flat):
        succs = generate_successions([spinach_crop])
        rates = compute_net_water_rates(succs, [spinach_crop], rainfall_flat)
        assert rates.shape == (len(succs), 53)  # index 0 unused → 53 columns

    def test_non_negative(self, spinach_crop, rainfall_flat):
        """Net irrigation need should never be negative (rainfall capped at 0 floor)."""
        succs = generate_successions([spinach_crop])
        rates = compute_net_water_rates(succs, [spinach_crop], rainfall_flat)
        assert np.all(rates >= 0)

    def test_inactive_weeks_are_zero(self, spinach_crop, rainfall_flat):
        succs = generate_successions([spinach_crop])
        rates = compute_net_water_rates(succs, [spinach_crop], rainfall_flat)
        for i, s in enumerate(succs):
            active = set(s["weeks"])
            for w in range(1, 53):
                if w not in active:
                    assert rates[i, w] == 0.0, f"Succession {i} week {w} should be 0"

    def test_high_rainfall_reduces_net_need(self, spinach_crop):
        """More rainfall → smaller net irrigation requirement."""
        succs = generate_successions([spinach_crop])
        low_rain = np.full(52, 1_000.0)
        high_rain = np.full(52, 50_000.0)
        rates_low = compute_net_water_rates(succs, [spinach_crop], low_rain)
        rates_high = compute_net_water_rates(succs, [spinach_crop], high_rain)
        # Sum of net need should be lower with more rainfall
        assert rates_high.sum() <= rates_low.sum()
