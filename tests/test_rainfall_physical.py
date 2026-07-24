"""
Physical-magnitude tests for rainfall — the gap the A1 1000x bug slipped through.

test_water.py asserts shapes/monotonicity and builds its OWN rainfall arrays by
hand (rainfall_flat = 5000 L/acre/wk), so it NEVER calls get_rainfall_weekly() —
the function the app actually uses. The 1000x conversion error therefore changed
zero of 131 tests. These tests pin the PHYSICAL magnitude against first principles:

    1 mm of rain over 1 m2  = 1 liter
    1 acre                   = 4046.856 m2
    => 1 mm over 1 acre      = 4046.856 liters

so the annual total from get_rainfall_weekly(zone) must equal
sum(monthly_mm) * 4046.856 (within a few percent — the monthly->52-week mapping
is not exact). A 1000x unit error moves this by 1000x and fails loudly.
"""
import numpy as np
import pytest
from farm_v2.utils.water import get_rainfall_weekly, RAINFALL_BY_ZONE, _MONTHLY_MM

L_PER_MM_ACRE = 4046.856  # liters per (1 mm x 1 acre)


class TestRainfallPhysicalMagnitude:
    @pytest.mark.parametrize("zone", list(_MONTHLY_MM.keys()))
    def test_annual_total_matches_first_principles(self, zone):
        annual_mm = sum(_MONTHLY_MM[zone])
        expected_L = annual_mm * L_PER_MM_ACRE          # liters/acre/year
        actual_L = float(np.sum(get_rainfall_weekly(zone)))
        # 6% band absorbs the calendar-month -> equal-week redistribution; a 1000x
        # (or 1000-divided) error is ~5 orders of magnitude out and cannot pass.
        assert actual_L == pytest.approx(expected_L, rel=0.06), (
            f"{zone}: annual rainfall {actual_L:,.0f} L/acre vs first-principles "
            f"{expected_L:,.0f} L/acre ({annual_mm:.0f} mm x {L_PER_MM_ACRE}). "
            "A large miss usually means a unit-conversion regression in water.py."
        )

    def test_pacific_northwest_absolute_magnitude(self):
        """Anchor one zone to an absolute number so a magnitude regression is caught
        even if _MONTHLY_MM is edited. Portland ~ 933 mm/yr -> ~3.78M L/acre/yr."""
        total_L = float(np.sum(get_rainfall_weekly("pacific_northwest")))
        assert 3_000_000 < total_L < 4_500_000, (
            f"pacific_northwest annual rainfall {total_L:,.0f} L/acre is outside the "
            "plausible 3.0-4.5M L/acre band (~740-1110 mm/yr). Unit regression?"
        )

    def test_get_rainfall_weekly_shape_and_nonneg(self):
        arr = get_rainfall_weekly("california_central_valley")
        assert arr.shape == (52,)
        assert np.all(arr >= 0)

    def test_get_rainfall_weekly_matches_zone_table(self):
        """The function is the app's entry point; it must return the zone array."""
        for zone in _MONTHLY_MM:
            np.testing.assert_array_equal(get_rainfall_weekly(zone), RAINFALL_BY_ZONE[zone])

    def test_custom_weekly_passthrough(self):
        custom = np.full(52, 1234.0)
        np.testing.assert_array_equal(
            get_rainfall_weekly(custom_weekly_L_per_acre=custom), custom
        )
