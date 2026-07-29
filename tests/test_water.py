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

# ---------------------------------------------------------------------------
# The tank stores water (audit B7)
# ---------------------------------------------------------------------------

class TestWaterStorageActuallyStores:
    """`water_storage_capacity` used to appear ONLY as a fixed-cost multiplier.

    C3 was a pure per-week flow balance, so a tank was billed every week of the year and banked
    nothing — catchment arriving in a wet week was lost. That makes rainwater harvesting
    unmodellable in any climate where the rain and the demand fall in different months.
    """

    # rate_water_storage is zeroed on purpose: capacity is billed per litre per week, so a
    # tank big enough to matter costs more than the farm has and the solve goes infeasible on
    # CASH, not on water. These tests are about whether the tank stores, not what it costs.
    def _solve(self, full_params, capacity):
        from farm_v2.solver import solve_farm_v2
        # city_water OFF as well: with it on, a week can already exceed its inflow by BUYING
        # water, so "used more than arrived" stops distinguishing a tank from a tap. Turning it
        # off makes storage the only possible source of the excess — which is what these tests
        # are actually about.
        return solve_farm_v2(**{**full_params,
                                "water_storage_capacity": capacity,
                                "rate_water_storage": 0.0,
                                "city_water_enabled": False})

    def test_a_tank_lets_a_week_draw_more_than_its_own_inflow(self, full_params):
        """Assert on USE, not on the reported cap.

        An earlier version of this test compared the published capacity against inflow. That
        passed even with the carry term deleted, because the published cap reads wstore — and
        with no row constraining it, wstore is unconstrained garbage anywhere in [0, capacity].
        The test was checking the report rather than the behaviour. What actually distinguishes
        a tank is that a week can SPEND more than arrives that week, which the flow-only row
        makes impossible.
        """
        from farm_v2.utils.water import compute_free_water, CATCHMENT_EFFICIENCY
        r = self._solve(full_params, 5_000_000)
        assert r["status"] in ("optimal", "time_limit_feasible"), r["status"]
        inflow = compute_free_water(
            full_params["rainfall_weekly_L_per_acre"],
            full_params.get("catchment_enabled", False),
            full_params.get("catchment_surface_area_m2", 0.0),
            full_params.get("catchment_efficiency", CATCHMENT_EFFICIENCY),
            full_params.get("well_enabled", False),
            full_params.get("well_weekly_cap_L", 0.0),
        )
        used = r["capacity_series"]["water"]["used"]
        drawn_down = [w for w, (u, f) in enumerate(zip(used, inflow), start=1)
                      if u > float(f) + 1.0]
        assert drawn_down, (
            "no week spent more water than arrived in it, so nothing was ever drawn out of "
            "storage — the tank is banking nothing, which is the B7 defect"
        )

    def test_water_is_conserved_across_the_year(self, full_params):
        """A tank moves water between weeks; it must not create any.

        Total draw over the year cannot exceed total inflow (the tank starts empty), which is
        the check that stops the carry term from becoming a source of free water.
        """
        from farm_v2.utils.water import compute_free_water, CATCHMENT_EFFICIENCY
        r = self._solve(full_params, 5_000_000)
        inflow = compute_free_water(
            full_params["rainfall_weekly_L_per_acre"],
            full_params.get("catchment_enabled", False),
            full_params.get("catchment_surface_area_m2", 0.0),
            full_params.get("catchment_efficiency", CATCHMENT_EFFICIENCY),
            full_params.get("well_enabled", False),
            full_params.get("well_weekly_cap_L", 0.0),
        )
        total_used = sum(r["capacity_series"]["water"]["used"])
        total_in = float(sum(inflow)) + float(r.get("city_water_cost", 0.0) and 0.0)
        assert total_used <= total_in + 1.0, (
            f"the farm used {total_used:,.0f} L against {total_in:,.0f} L of inflow — storage "
            f"is creating water, not moving it"
        )

    def test_no_tank_means_no_banking(self, full_params):
        from farm_v2.utils.water import compute_free_water, CATCHMENT_EFFICIENCY
        r = self._solve(full_params, 0.0)
        inflow = compute_free_water(
            full_params["rainfall_weekly_L_per_acre"],
            full_params.get("catchment_enabled", False),
            full_params.get("catchment_surface_area_m2", 0.0),
            full_params.get("catchment_efficiency", CATCHMENT_EFFICIENCY),
            full_params.get("well_enabled", False),
            full_params.get("well_weekly_cap_L", 0.0),
        )
        caps = r["capacity_series"]["water"]["cap"]
        for w, (c, f) in enumerate(zip(caps, inflow), start=1):
            assert c <= float(f) + 1e-6, (
                f"week {w}: capacity 0 but the reported supply {c:,.0f} exceeds inflow "
                f"{float(f):,.0f} — water is being conjured"
            )

    def test_a_tank_never_makes_the_farm_worse_off(self, full_params):
        """Storage is optional: the optimizer may ignore it, so profit must not fall."""
        none = self._solve(full_params, 0.0)
        tank = self._solve(full_params, 5_000_000)
        assert tank["profit"] >= none["profit"] - 1.0, (
            f"adding storage capacity REDUCED profit ({tank['profit']:,.0f} vs "
            f"{none['profit']:,.0f}) — a tank cannot remove an option"
        )
