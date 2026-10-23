"""
conftest.py — Shared pytest fixtures for farm_v2 tests.

Fixtures are organized in tiers:
  - Primitives: single crop/channel dicts for unit tests
  - Minimal:    smallest possible valid parameter set (1 crop, 1 channel)
  - Full:       6-crop 2-channel demo model (matches notebook defaults)
"""

# Water rates follow the same FAO-56 rule as the shipped crop templates (Kc x 141,640 L/acre/wk).
# They used to be ~10x lower, which put net irrigation at identically ZERO for every fixture that
# uses them — so every test here exercised a water constraint that could not bind, including the
# regression pin. Found 2026-07-29 by the binding test in test_binding.py, which is the point of
# having one. These are synthetic values with no provenance claim; they only have to be the right
# ORDER so the constraint they feed is real.

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Rainfall
# ---------------------------------------------------------------------------

@pytest.fixture
def rainfall_flat():
    """52-week flat rainfall — 5,000 L/acre/week."""
    return np.full(52, 5_000.0)


@pytest.fixture
def rainfall_zero():
    """52-week zero rainfall (forces reliance on well/catchment)."""
    return np.zeros(52)


# ---------------------------------------------------------------------------
# Minimal crop / channel for unit-test level fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spinach_crop():
    """Minimal valid Spinach crop dict."""
    return {
        "name": "Spinach",
        "days_to_maturity": 42,       # 6 weeks: 1 plant + 3 grow + 2 harvest
        "planting_weeks": 1,
        "harvest_weeks": 2,
        "seasons": [{"start": "03-01", "end": "06-30"}],
        "min_acreage_if_planted": 1.0,
        "crop_diversity_max": 0.50,
        "yield_per_acre": 3_000,
        "crop_size_m3_per_lb": 0.002,
        "planting_type": "seed",
        "seed_transplant_cost_per_acre": 200,
        "labor_plant": 0.7,  "labor_grow": 0.5,  "labor_harv": 1.9,
        "water_plant": 99148, "water_grow": 141640, "water_harv": 134558,
        "fert_plant": 0.4,  "fert_grow": 0.3,  "fert_harv": 0.2,
        "fuel_plant": 3.5,  "fuel_grow": 1.8,  "fuel_harv": 4.6,
        "channels": {
            "Direct": {
                "price_per_lb": 2.00,
                "packaging_cost_per_lb": 0.15,
                "demand_cap_type": "weekly_flat",
                "weekly_demand_lbs": 5_000,
            },
        },
    }


@pytest.fixture
def cucumber_crop():
    """Minimal valid Cucumber crop dict."""
    return {
        "name": "Cucumbers",
        "days_to_maturity": 70,       # 10 weeks: 1 plant + 6 grow + 3 harvest
        "planting_weeks": 1,
        "harvest_weeks": 3,
        "seasons": [{"start": "05-01", "end": "09-01"}],
        "min_acreage_if_planted": 1.0,
        "crop_diversity_max": 0.40,
        "yield_per_acre": 3_000,
        "crop_size_m3_per_lb": 0.003,
        "planting_type": "seed",
        "seed_transplant_cost_per_acre": 150,
        "labor_plant": 0.9,  "labor_grow": 0.7,  "labor_harv": 2.3,
        "water_plant": 84984, "water_grow": 141640, "water_harv": 106230,
        "fert_plant": 0.7,  "fert_grow": 0.5,  "fert_harv": 0.2,
        "fuel_plant": 4.2,  "fuel_grow": 2.3,  "fuel_harv": 5.1,
        "channels": {
            "Direct": {
                "price_per_lb": 1.00,
                "packaging_cost_per_lb": 0.10,
                "demand_cap_type": "annual",
                "annual_demand_lbs": 500_000,
            },
        },
    }


@pytest.fixture
def direct_channel():
    return {"name": "Direct"}


@pytest.fixture
def wholesale_channel():
    return {"name": "Wholesale"}


# ---------------------------------------------------------------------------
# Minimal 1-crop solve params (fast — used in unit/integration tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def spinach_crop_high_demand(spinach_crop):
    """Spinach with a high demand cap so it isn't revenue-constrained in solver tests."""
    import copy
    c = copy.deepcopy(spinach_crop)
    c["channels"]["Direct"]["demand_cap_type"] = "weekly_flat"
    c["channels"]["Direct"]["weekly_demand_lbs"] = 100_000   # effectively uncapped
    return c


@pytest.fixture
def minimal_params(spinach_crop_high_demand, rainfall_flat):
    """
    Smallest feasible parameter set for solver integration tests.

    Designed for a 50-acre farm with:
      - Modest infrastructure (small cooler, fuel tank, equip shed)
      - Generous opening cash + credit to survive early-season cash burn. Raised 500k -> 1.5M on
        2026-07-31 with W12: wages became a COMMITTED weekly cost, so payroll now has to clear the
        C13 cash floor like any other bill. Several variants of this fixture went `infeasible` at
        the old level — which is the model telling the truth (a farm must be able to make payroll),
        not a regression.
      - High demand cap so revenue can scale with planted area
    Fixed cost breakdown (~$738k):
      irrigation (50ac×$175/wk×52)=$455k, machinery=$135k, salaried=$60k,
      storage infrastructure=$88k
    Revenue potential (50ac × Spinach × ~8 successions) >> fixed cost.
    """
    return dict(
        total_land=50.0,
        harvest_storage_cap=500.0,           # m³ — small on-farm cooler
        opening_cash=1_500_000.0,
        credit_line=1_500_000.0,
        operating_weeks=48,
        crops=[spinach_crop_high_demand],
        channels=[{"name": "Direct"}],
        rainfall_weekly_L_per_acre=rainfall_flat,
        year_round_employees=[
            {
                "position": "Manager",
                "count": 1,
                "type": "salary",
                "wage": 60_000,
                "hours_per_week": 40,
            }
        ],
        seasonal_employees=[
            {
                "position": "Field Hand",
                "count": 10,
                "type": "FT",
                "start_week": 8,
                "end_week": 46,
                "wage": 18.0,
                "hours_per_week": 40,
            }
        ],
        city_water_enabled=False,
        well_enabled=True,
        well_weekly_cap_L=5_450_000.0,   # 8 gpm/ac x 50 ac x 60 h/wk
        catchment_enabled=False,
        catchment_surface_area_m2=0.0,
        max_plant_acres_per_week=1e9,
        max_harvest_acres_per_week=1e9,
        year=2024,
        rate_harvest_storage=2.0,
        rate_water_storage=0.0036,
        rate_irrigation=175.0,
        rate_equip_storage=1.042,
        rate_fuel_storage=0.0208,
        rate_machinery=2_600.0,
        water_storage_capacity=100_000.0,    # L — small tank
        equip_storage=200.0,                 # m³
        fuel_storage=5_000.0,                # L
        cost_fert_per_lb=0.82,
        cost_fuel_per_L=1.25,
    )


# ---------------------------------------------------------------------------
# 2-crop params (integration tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def two_crop_params(spinach_crop, cucumber_crop, rainfall_flat):
    """
    2-crop, 1-channel parameter set for integration tests.

    Crops have generous demand caps (both use annual or weekly_flat in their
    fixtures) and the farm has enough cash/credit to cover fixed costs while
    waiting for first harvest revenue.
    """
    import copy
    # Boost demand caps so revenue can scale with planted area
    spinach = copy.deepcopy(spinach_crop)
    spinach["channels"]["Direct"]["weekly_demand_lbs"] = 100_000

    cucumber = copy.deepcopy(cucumber_crop)
    cucumber["channels"]["Direct"]["annual_demand_lbs"] = 2_000_000

    return dict(
        total_land=50.0,
        harvest_storage_cap=500.0,
        opening_cash=600_000.0,
        credit_line=600_000.0,
        operating_weeks=48,
        crops=[spinach, cucumber],
        channels=[{"name": "Direct"}],
        rainfall_weekly_L_per_acre=rainfall_flat,
        year_round_employees=[
            {
                "position": "Manager",
                "count": 1,
                "type": "salary",
                "wage": 60_000,
                "hours_per_week": 40,
            }
        ],
        seasonal_employees=[
            {
                "position": "Field Hand",
                "count": 15,
                "type": "FT",
                "start_week": 8,
                "end_week": 45,
                "wage": 18.0,
                "hours_per_week": 40,
            }
        ],
        city_water_enabled=False,
        well_enabled=True,
        well_weekly_cap_L=5_450_000.0,   # 8 gpm/ac x 50 ac x 60 h/wk
        catchment_enabled=False,
        catchment_surface_area_m2=0.0,
        max_plant_acres_per_week=1e9,
        max_harvest_acres_per_week=1e9,
        year=2024,
        rate_harvest_storage=0.356,
        rate_water_storage=0.00360,
        rate_irrigation=38.54,
        rate_equip_storage=1.042,
        rate_fuel_storage=0.0208,
        rate_machinery=4_167.0,
        water_storage_capacity=100_000.0,
        equip_storage=200.0,
        fuel_storage=5_000.0,
        cost_fert_per_lb=0.82,
        cost_fuel_per_L=1.25,
    )


# ---------------------------------------------------------------------------
# Full 6-crop 2-channel params (regression tests — matches notebook defaults)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def full_crops():
    return [
        {
            "name": "Spinach",
            "days_to_maturity": 42,
            "planting_weeks": 1, "harvest_weeks": 2,
            "seasons": [
                {"start": "02-01", "end": "06-15"},
                {"start": "08-01", "end": "11-15"},
            ],
            "min_acreage_if_planted": 2.0,
            "crop_diversity_max": 0.50,
            "yield_per_acre": 3_250,
            "crop_size_m3_per_lb": 0.0022,
            "planting_type": "seed",
            "seed_transplant_cost_per_acre": 280,
            "labor_plant": 0.7, "labor_grow": 0.5, "labor_harv": 1.9,
            "water_plant": 99148, "water_grow": 141640, "water_harv": 134558,
            "fert_plant": 0.46, "fert_grow": 0.35, "fert_harv": 0.23,
            "fuel_plant": 3.5, "fuel_grow": 1.8, "fuel_harv": 4.6,
            "channels": {
                "Wholesale": {
                    "price_per_lb": 1.10, "packaging_cost_per_lb": 0.09,
                    "demand_cap_type": "annual", "annual_demand_lbs": 1_200_000,
                },
                "Farmers Market": {
                    "price_per_lb": 2.10, "packaging_cost_per_lb": 0.18,
                    "demand_cap_type": "weekly_flat", "weekly_demand_lbs": 6_000,
                },
            },
        },
        {
            "name": "Cucumbers",
            "days_to_maturity": 70,
            "planting_weeks": 1, "harvest_weeks": 3,
            "seasons": [{"start": "05-01", "end": "09-01"}],
            "min_acreage_if_planted": 2.0,
            "crop_diversity_max": 0.40,
            "yield_per_acre": 3_000,
            "crop_size_m3_per_lb": 0.0030,
            "planting_type": "seed",
            "seed_transplant_cost_per_acre": 190,
            "labor_plant": 0.9, "labor_grow": 0.7, "labor_harv": 2.3,
            "water_plant": 84984, "water_grow": 141640, "water_harv": 106230,
            "fert_plant": 0.69, "fert_grow": 0.46, "fert_harv": 0.23,
            "fuel_plant": 4.2, "fuel_grow": 2.3, "fuel_harv": 5.1,
            "channels": {
                "Wholesale": {
                    "price_per_lb": 0.55, "packaging_cost_per_lb": 0.06,
                    "demand_cap_type": "annual", "annual_demand_lbs": 900_000,
                },
                "Farmers Market": {
                    "price_per_lb": 1.05, "packaging_cost_per_lb": 0.12,
                    "demand_cap_type": "weekly_varying",
                    "demand_ranges": [{"weeks": "W18-W40", "weekly_lbs": 4_000}],
                },
            },
        },
        {
            "name": "Sweet Corn",
            "days_to_maturity": 84,
            "planting_weeks": 1, "harvest_weeks": 2,
            "seasons": [{"start": "04-15", "end": "09-01"}],
            "min_acreage_if_planted": 3.0,
            "crop_diversity_max": 0.35,
            "yield_per_acre": 6_000,
            "crop_size_m3_per_lb": 0.0015,
            "planting_type": "seed",
            "seed_transplant_cost_per_acre": 120,
            "labor_plant": 0.9, "labor_grow": 0.5, "labor_harv": 2.3,
            "water_plant": 42492, "water_grow": 162886, "water_harv": 148722,
            "fert_plant": 0.58, "fert_grow": 0.46, "fert_harv": 0.35,
            "fuel_plant": 4.6, "fuel_grow": 2.3, "fuel_harv": 5.8,
            "channels": {
                "Wholesale": {
                    "price_per_lb": 0.38, "packaging_cost_per_lb": 0.04,
                    "demand_cap_type": "annual", "annual_demand_lbs": 600_000,
                },
                "Farmers Market": {
                    "price_per_lb": 0.82, "packaging_cost_per_lb": 0.10,
                    "demand_cap_type": "weekly_varying",
                    "demand_ranges": [{"weeks": "W25-W38", "weekly_lbs": 3_000}],
                },
            },
        },
        {
            "name": "Napa Cabbage",
            "days_to_maturity": 70,
            "planting_weeks": 1, "harvest_weeks": 2,
            "seasons": [
                {"start": "03-01", "end": "07-01"},
                {"start": "07-15", "end": "11-01"},
            ],
            "min_acreage_if_planted": 2.0,
            "crop_diversity_max": 0.40,
            "yield_per_acre": 3_500,
            "crop_size_m3_per_lb": 0.0025,
            "planting_type": "seed",
            "seed_transplant_cost_per_acre": 160,
            "labor_plant": 0.7, "labor_grow": 0.5, "labor_harv": 2.1,
            "water_plant": 99148, "water_grow": 148722, "water_harv": 134558,
            "fert_plant": 0.46, "fert_grow": 0.35, "fert_harv": 0.23,
            "fuel_plant": 3.5, "fuel_grow": 1.8, "fuel_harv": 4.6,
            "channels": {
                "Wholesale": {
                    "price_per_lb": 0.65, "packaging_cost_per_lb": 0.07,
                    "demand_cap_type": "annual", "annual_demand_lbs": 700_000,
                },
                "Farmers Market": {
                    "price_per_lb": 1.25, "packaging_cost_per_lb": 0.14,
                    "demand_cap_type": "weekly_flat", "weekly_demand_lbs": 3_600,
                },
            },
        },
        {
            "name": "Hot Peppers",
            "days_to_maturity": 147,
            "planting_weeks": 2, "harvest_weeks": 6,
            "seasons": [{"start": "04-01", "end": "10-15"}],
            "min_acreage_if_planted": 2.0,
            "crop_diversity_max": 0.55,
            "yield_per_acre": 834,
            "crop_size_m3_per_lb": 0.0018,
            "planting_type": "transplant",
            "seed_transplant_cost_per_acre": 420,
            "labor_plant": 1.2, "labor_grow": 0.7, "labor_harv": 2.8,
            "water_plant": 84984, "water_grow": 148722, "water_harv": 127476,
            "fert_plant": 0.69, "fert_grow": 0.46, "fert_harv": 0.35,
            "fuel_plant": 4.2, "fuel_grow": 2.8, "fuel_harv": 5.8,
            "channels": {
                "Wholesale": {
                    "price_per_lb": 1.80, "packaging_cost_per_lb": 0.14,
                    "demand_cap_type": "annual", "annual_demand_lbs": 300_000,
                },
                "Farmers Market": {
                    "price_per_lb": 3.20, "packaging_cost_per_lb": 0.25,
                    "demand_cap_type": "weekly_varying",
                    "demand_ranges": [{"weeks": "W22-W44", "weekly_lbs": 1_600}],
                },
            },
        },
        {
            "name": "Garlic",
            "days_to_maturity": 196,
            "planting_weeks": 3, "harvest_weeks": 3,
            "seasons": [{"start": "01-01", "end": "08-01"}],
            "min_acreage_if_planted": 5.0,
            "crop_diversity_max": 0.60,
            "yield_per_acre": 834,
            "crop_size_m3_per_lb": 0.0012,
            "planting_type": "seed",
            "seed_transplant_cost_per_acre": 380,
            "labor_plant": 0.9, "labor_grow": 0.5, "labor_harv": 1.4,
            "water_plant": 99148, "water_grow": 141640, "water_harv": 99148,
            "fert_plant": 0.46, "fert_grow": 0.23, "fert_harv": 0.12,
            "fuel_plant": 4.6, "fuel_grow": 1.8, "fuel_harv": 3.5,
            "channels": {
                "Wholesale": {
                    "price_per_lb": 3.00, "packaging_cost_per_lb": 0.20,
                    "demand_cap_type": "annual", "annual_demand_lbs": 200_000,
                },
                "Farmers Market": {
                    "price_per_lb": 5.20, "packaging_cost_per_lb": 0.40,
                    "demand_cap_type": "weekly_varying",
                    "demand_ranges": [{"weeks": "W22-W35", "weekly_lbs": 1_000}],
                },
            },
        },
    ]


@pytest.fixture(scope="session")
def full_channels():
    return [{"name": "Wholesale"}, {"name": "Farmers Market"}]


@pytest.fixture(scope="session")
def full_rainfall():
    """California Central Valley rainfall (matches notebook default zone)."""
    from farm_v2.utils.water import RAINFALL_BY_ZONE
    return RAINFALL_BY_ZONE["california_central_valley"]


@pytest.fixture(scope="session")
def full_params(full_crops, full_channels, full_rainfall):
    """Complete 6-crop notebook-equivalent parameter set."""
    return dict(
        total_land=150.0,
        harvest_storage_cap=24_000.0,
        opening_cash=150_000.0,
        credit_line=600_000.0,
        operating_weeks=48,
        crops=full_crops,
        channels=full_channels,
        rainfall_weekly_L_per_acre=full_rainfall,
        year_round_employees=[
            {
                "position": "Farm Manager",
                "count": 1,
                "type": "salary",
                "wage": 75_000,
                "hours_per_week": 50,
            }
        ],
        seasonal_employees=[
            {
                "position": "Seasonal Crew",
                "count": 25,
                "type": "FT",
                "start_week": 8,
                "end_week": 45,
                "wage": 18.0,
                "hours_per_week": 40,
            }
        ],
        city_water_enabled=False,
        well_enabled=True,
        well_weekly_cap_L=16_350_000.0,  # 8 gpm/ac x 150 ac x 60 h/wk
        catchment_enabled=False,
        catchment_surface_area_m2=0.0,
        max_plant_acres_per_week=1e9,
        max_harvest_acres_per_week=1e9,
        year=2024,
        # Exact notebook values (Section 3A–3B)
        rate_harvest_storage=0.356,
        rate_water_storage=0.00360,
        rate_irrigation=38.54,
        rate_equip_storage=1.042,
        rate_fuel_storage=0.0208,
        rate_machinery=4_167.0,
        water_storage_capacity=500_000.0,
        equip_storage=500.0,
        fuel_storage=25_000.0,
        cost_fert_per_lb=0.82,
        cost_fuel_per_L=1.25,
    )


# ---------------------------------------------------------------------------
# Shared solve cache (fixtures; the helpers live in tests/helpers.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def solved_two_crop(two_crop_params):
    """The two-crop fixture, solved once per session.

    Shared by test_channel_sales and test_demand_saturation. Both had grown their own
    module-level `_SOLVED` dict guarding the SAME solve of `two_crop_params` — same idiom, same
    assert, same docstring, twice, and one extra MILP per run.
    """
    from tests.helpers import solved_once
    return solved_once("two_crop", two_crop_params)


@pytest.fixture(scope="session")
def golden_out():
    """ONE solve of the unmodified golden payload through the app's adapter, shared read-only by
    every module that needs it (each private copy cost ~3 s)."""
    import json
    from farm_v2.adapter import run_from_js
    from tests.helpers import golden_payload
    return json.loads(run_from_js(json.dumps(golden_payload())))
