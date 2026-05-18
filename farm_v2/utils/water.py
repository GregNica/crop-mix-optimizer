"""
water.py — Water supply and net irrigation-need utilities for the 52-week farm model.

Roles:
  1. Historical weekly rainfall data (built-in averages for common US climate zones;
     user can supply their own 52-element array in liters/acre/week).
  2. Derived weekly supply arrays: catchment_supply, well_supply, free_water.
  3. Net irrigation need per succession per week:
         net_water_rate[i][w] = max(0, crop_water_rate[i][w] - rainfall_offset[w])
     where rainfall_offset[w] = RAINFALL_WEEKLY[w] × RAINFALL_OFFSET_FRACTION
     This is computed before the solve as a fixed constant (keeps constraints linear).

Unit conventions (throughout this module):
  - Rainfall    : liters / acre / week
  - Water need  : liters / acre / week
  - Supply      : liters / week  (absolute, not per-acre)
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Hard-coded defaults
# ---------------------------------------------------------------------------

#: Fraction of field rainfall that offsets crop irrigation need.
#: e.g. 0.65 means 65 % of rainfall is usable in-field; the rest is runoff.
RAINFALL_OFFSET_FRACTION: float = 0.65

#: Fraction of catchment rainfall that actually reaches the storage tank
#: (accounting for evaporation and inefficiency).
CATCHMENT_EFFICIENCY: float = 0.85


# ---------------------------------------------------------------------------
# Built-in historical weekly rainfall data (liters / acre / week)
# ---------------------------------------------------------------------------
# Values represent average precipitation converted to liters per acre.
# 1 mm of rain over 1 acre = 4,046.86 liters.
# Sources: NOAA 30-year climate normals (1991–2020), representative cities.
#
# Available climate zones:
#   "california_central_valley"  — Fresno, CA  (hot dry summers)
#   "pacific_northwest"          — Portland, OR (wet winters, dry summers)
#   "southeast"                  — Atlanta, GA  (humid subtropical)
#   "midwest"                    — Des Moines, IA (continental)
#   "northeast"                  — Philadelphia, PA (humid continental)
#   "southwest_desert"           — Phoenix, AZ  (hot arid)
#
# Monthly mm → weekly liters/acre:
#   weekly_mm ≈ monthly_mm / 4.33
#   liters_per_acre = weekly_mm × 4046.86 / 1000  (since 1 mm = 4.046 L/m², 1 acre = 4046.86 m²)

def _monthly_mm_to_weekly_L_per_acre(monthly_mm: list[float]) -> np.ndarray:
    """
    Convert 12-element monthly rainfall (mm/month) to 52-element weekly
    (liters/acre/week) using simple equal-week distribution.
    """
    from farm_v2.utils.calendar import monthly_to_weekly
    monthly_L_per_acre = [mm * 4046.86 / 1000 for mm in monthly_mm]
    # Each month's L/acre/month → L/acre/week by dividing by weeks-in-month.
    # monthly_to_weekly assigns each week the value of its calendar month,
    # so we first need L/acre/week from L/acre/month.
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    monthly_L_per_acre_per_week = [
        L / (d / 7) for L, d in zip(monthly_L_per_acre, days_per_month)
    ]
    return monthly_to_weekly(monthly_L_per_acre_per_week)


# Monthly precipitation normals (mm/month) for each climate zone.
_MONTHLY_MM: dict[str, list[float]] = {
    # NOAA Fresno, CA
    "california_central_valley": [
        38.9, 36.3, 34.3, 14.2, 5.1, 1.5, 0.3, 0.5, 3.6, 14.5, 24.1, 35.6,
    ],
    # NOAA Portland, OR
    "pacific_northwest": [
        136.1, 100.3, 97.8, 68.6, 56.9, 36.8, 14.7, 17.3, 40.4, 87.9, 134.6, 141.5,
    ],
    # NOAA Atlanta, GA
    "southeast": [
        116.8, 111.3, 135.4, 89.4, 85.3, 104.4, 126.7, 97.5, 99.8, 75.7, 96.3, 102.6,
    ],
    # NOAA Des Moines, IA
    "midwest": [
        26.7, 28.4, 47.5, 75.4, 101.1, 108.5, 104.9, 107.4, 88.6, 60.5, 47.2, 32.3,
    ],
    # NOAA Philadelphia, PA
    "northeast": [
        85.9, 76.5, 99.1, 87.9, 96.3, 97.0, 107.4, 101.6, 91.9, 83.8, 87.1, 87.6,
    ],
    # NOAA Phoenix, AZ
    "southwest_desert": [
        18.8, 19.1, 24.6, 5.8, 3.8, 2.5, 32.5, 27.7, 22.4, 16.8, 13.0, 20.6,
    ],
}

#: Pre-computed 52-element arrays keyed by climate zone name.
RAINFALL_BY_ZONE: dict[str, np.ndarray] = {
    zone: _monthly_mm_to_weekly_L_per_acre(mm)
    for zone, mm in _MONTHLY_MM.items()
}


def get_rainfall_weekly(
    climate_zone: str | None = None,
    custom_weekly_L_per_acre: list[float] | np.ndarray | None = None,
) -> np.ndarray:
    """
    Return a 52-element array of rainfall in liters/acre/week.

    Supply exactly one of:
      - ``climate_zone``               — one of the built-in zone names
      - ``custom_weekly_L_per_acre``   — a 52-element array you provide

    Built-in zones: ``california_central_valley``, ``pacific_northwest``,
    ``southeast``, ``midwest``, ``northeast``, ``southwest_desert``.
    """
    if custom_weekly_L_per_acre is not None:
        arr = np.asarray(custom_weekly_L_per_acre, dtype=float)
        if arr.shape != (52,):
            raise ValueError(
                f"custom_weekly_L_per_acre must have 52 elements, got {arr.shape}."
            )
        return arr

    if climate_zone is not None:
        if climate_zone not in RAINFALL_BY_ZONE:
            raise ValueError(
                f"Unknown climate_zone '{climate_zone}'. "
                f"Choose from: {sorted(RAINFALL_BY_ZONE.keys())}."
            )
        return RAINFALL_BY_ZONE[climate_zone].copy()

    raise ValueError(
        "Supply either climate_zone or custom_weekly_L_per_acre."
    )


# ---------------------------------------------------------------------------
# Derived weekly supply arrays
# ---------------------------------------------------------------------------

def compute_catchment_supply(
    rainfall_weekly_L_per_acre: np.ndarray,
    catchment_surface_area_m2: float,
    catchment_efficiency: float = CATCHMENT_EFFICIENCY,
) -> np.ndarray:
    """
    Return 52-element catchment supply array in liters/week.

    ``catchment_surface_area_m2`` is the total impervious surface draining
    to the storage tank (roof area, packed-gravel pond berm, etc.).

    rainfall_weekly_L_per_acre is converted to mm and applied to m² surface area::

        supply[w] = rainfall_mm[w] × catchment_surface_area_m2 × efficiency / 1000
                  = (rainfall_L_per_acre[w] / 4046.86 × 1000)
                    × catchment_surface_area_m2 × efficiency / 1000
    """
    # L/acre → mm (1 L/acre = 1/4046.86 × 1000 mm = 0.24711 mm)
    rainfall_mm = rainfall_weekly_L_per_acre / 4046.86 * 1000
    supply = rainfall_mm * catchment_surface_area_m2 * catchment_efficiency / 1000
    return np.maximum(supply, 0.0)


def compute_well_supply(
    well_enabled: bool,
    well_weekly_cap_L: float,
) -> np.ndarray:
    """Return 52-element constant well supply array in liters/week."""
    if not well_enabled:
        return np.zeros(52)
    return np.full(52, well_weekly_cap_L, dtype=float)


def compute_free_water(
    rainfall_weekly_L_per_acre: np.ndarray,
    catchment_enabled: bool = False,
    catchment_surface_area_m2: float = 0.0,
    catchment_efficiency: float = CATCHMENT_EFFICIENCY,
    well_enabled: bool = False,
    well_weekly_cap_L: float = 0.0,
) -> np.ndarray:
    """
    Return 52-element free water supply array in liters/week.

    free_water[w] = catchment_supply[w] + well_supply[w]

    City water is NOT included here — it is a decision variable in the solver.
    """
    free = np.zeros(52)
    if catchment_enabled:
        free += compute_catchment_supply(
            rainfall_weekly_L_per_acre,
            catchment_surface_area_m2,
            catchment_efficiency,
        )
    if well_enabled:
        free += compute_well_supply(well_enabled, well_weekly_cap_L)
    return free


# ---------------------------------------------------------------------------
# Net irrigation need per succession per week
# ---------------------------------------------------------------------------

def compute_net_water_rates(
    successions: list[dict],
    crops: list[dict],
    rainfall_weekly_L_per_acre: np.ndarray,
    rainfall_offset_fraction: float = RAINFALL_OFFSET_FRACTION,
) -> np.ndarray:
    """
    Return a 2-D array ``net_water_rate[i][w]`` (shape: n_successions × 53,
    week-index 0 unused) in liters/acre/week.

    For succession ``i`` in week ``w``::

        phase = phase_in_week[i][w]
        if phase is None (not active):
            net_water_rate[i][w] = 0.0
        else:
            raw_rate = crop_water_rate_for_phase (liters/acre/week)
            offset   = rainfall_weekly[w-1] × rainfall_offset_fraction
            net_water_rate[i][w] = max(0, raw_rate - offset)

    Indices: weeks are 1-indexed (w = 1..52); index 0 is always 0.

    Phase keys in crop dict:
        "water_plant", "water_grow", "water_harv"
    """
    _WATER_KEY = ["water_plant", "water_grow", "water_harv"]
    n = len(successions)
    result = np.zeros((n, 53), dtype=float)  # col 0 unused (1-indexed weeks)

    for i, s in enumerate(successions):
        crop = crops[s["crop"]]
        for week, phase in zip(s["weeks"], s["phases"]):
            if not (1 <= week <= 52):
                continue
            raw_rate = crop[_WATER_KEY[phase]]
            offset = rainfall_weekly_L_per_acre[week - 1] * rainfall_offset_fraction
            result[i][week] = max(0.0, raw_rate - offset)

    return result
