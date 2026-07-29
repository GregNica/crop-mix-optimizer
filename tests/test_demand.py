"""Unit tests for farm_v2.utils.demand."""
import pytest
import numpy as np
from farm_v2.utils.demand import expand_channel_demand, build_demand_table


class TestExpandChannelDemand:
    def test_annual_spreads_evenly(self):
        spec = {"demand_cap_type": "annual", "annual_demand_lbs": 52_000}
        arr = expand_channel_demand(spec)
        assert arr.shape == (52,)
        assert np.allclose(arr, 1_000.0)   # 52_000 / 52

    def test_annual_zero(self):
        spec = {"demand_cap_type": "annual", "annual_demand_lbs": 0}
        arr = expand_channel_demand(spec)
        assert np.all(arr == 0)

    def test_weekly_flat_constant(self):
        spec = {"demand_cap_type": "weekly_flat", "weekly_demand_lbs": 500}
        arr = expand_channel_demand(spec)
        assert arr.shape == (52,)
        assert np.allclose(arr, 500.0)

    def test_weekly_varying_range_inside(self):
        spec = {
            "demand_cap_type": "weekly_varying",
            "demand_ranges": [{"weeks": "W10-W20", "weekly_lbs": 300}],
        }
        arr = expand_channel_demand(spec)
        assert arr.shape == (52,)
        # Weeks 10–20 should be 300
        for w_idx in range(9, 20):   # 0-indexed: w10=index9 .. w20=index19
            assert arr[w_idx] == 300.0
        # Outside range → 0
        assert arr[0] == 0.0
        assert arr[51] == 0.0

    def test_weekly_varying_multiple_ranges(self):
        spec = {
            "demand_cap_type": "weekly_varying",
            "demand_ranges": [
                {"weeks": "W5-W10", "weekly_lbs": 100},
                {"weeks": "W30-W40", "weekly_lbs": 200},
            ],
        }
        arr = expand_channel_demand(spec)
        assert arr[4] == 100.0    # W5 (0-indexed: 4)
        assert arr[29] == 200.0   # W30 (0-indexed: 29)
        assert arr[1] == 0.0      # W2 — outside both ranges

    def test_weekly_varying_overlapping_ranges_accumulate(self):
        """Overlapping ranges are two buyers, not one restated.

        This was `arr[...] = value`, so the LAST range listed silently replaced the earlier one
        over the overlap — order-dependent, and usually resolving to the lower cap, so the model
        under-planned with nothing on screen to explain it. A standing W1-W20 contract plus a
        W10-W15 seasonal top-up must be the SUM in the overlap.
        """
        spec = {
            "demand_cap_type": "weekly_varying",
            "demand_ranges": [
                {"weeks": "W1-W20", "weekly_lbs": 1000},
                {"weeks": "W10-W15", "weekly_lbs": 400},
            ],
        }
        arr = expand_channel_demand(spec)
        assert arr[0] == 1000.0     # W1  — contract only
        assert arr[9] == 1400.0     # W10 — contract + top-up
        assert arr[14] == 1400.0    # W15 — last overlapping week
        assert arr[15] == 1000.0    # W16 — top-up has ended
        assert arr[20] == 0.0       # W21 — outside both

    def test_weekly_varying_overlap_is_order_independent(self):
        """Same two ranges, listed in the other order, must give the identical array."""
        a = expand_channel_demand({
            "demand_cap_type": "weekly_varying",
            "demand_ranges": [
                {"weeks": "W1-W20", "weekly_lbs": 1000},
                {"weeks": "W10-W15", "weekly_lbs": 400},
            ],
        })
        b = expand_channel_demand({
            "demand_cap_type": "weekly_varying",
            "demand_ranges": [
                {"weeks": "W10-W15", "weekly_lbs": 400},
                {"weeks": "W1-W20", "weekly_lbs": 1000},
            ],
        })
        np.testing.assert_array_equal(a, b)

    def test_weekly_varying_no_ranges_all_zeros(self):
        spec = {"demand_cap_type": "weekly_varying", "demand_ranges": []}
        arr = expand_channel_demand(spec)
        assert np.all(arr == 0)

    def test_non_negative_output(self):
        for spec in [
            {"demand_cap_type": "annual", "annual_demand_lbs": 100_000},
            {"demand_cap_type": "weekly_flat", "weekly_demand_lbs": 1_000},
            {
                "demand_cap_type": "weekly_varying",
                "demand_ranges": [{"weeks": "W1-W52", "weekly_lbs": 500}],
            },
        ]:
            arr = expand_channel_demand(spec)
            assert np.all(arr >= 0)


class TestBuildDemandTable:
    def test_shape(self, spinach_crop, cucumber_crop, direct_channel):
        crops = [spinach_crop, cucumber_crop]
        channels = [direct_channel]
        table = build_demand_table(crops, channels)
        assert table.shape == (2, 1, 53)   # (n_crops, n_ch, 53) — index 0 unused

    def test_two_channels(self, spinach_crop):
        channels = [{"name": "Wholesale"}, {"name": "Farmers Market"}]
        # spinach_crop fixture only has "Direct" — give it two channels
        import copy
        crop = copy.deepcopy(spinach_crop)
        crop["channels"] = {
            "Wholesale": {
                "price_per_lb": 1.00,
                "packaging_cost_per_lb": 0.08,
                "demand_cap_type": "annual",
                "annual_demand_lbs": 100_000,
            },
            "Farmers Market": {
                "price_per_lb": 2.00,
                "packaging_cost_per_lb": 0.15,
                "demand_cap_type": "weekly_flat",
                "weekly_demand_lbs": 500,
            },
        }
        table = build_demand_table([crop], channels)
        assert table.shape == (1, 2, 53)
        # Wholesale: ~1923 lbs/week (100k/52)
        assert table[0, 0, 1] == pytest.approx(100_000 / 52, rel=1e-3)
        # Farmers Market: 500 flat
        assert table[0, 1, 1] == pytest.approx(500.0, rel=1e-3)

    def test_crop_without_channel_is_zero(self, spinach_crop, direct_channel):
        """Crop not listed in a channel gets zero demand for that channel."""
        import copy
        crop = copy.deepcopy(spinach_crop)
        crop["channels"] = {}   # no channels specified
        table = build_demand_table([crop], [direct_channel])
        assert np.all(table[0, :, 1:] == 0)

    def test_values_non_negative(self, spinach_crop, direct_channel):
        table = build_demand_table([spinach_crop], [direct_channel])
        assert np.all(table >= 0)
