"""
demand.py — Expand demand cap specifications to 52-week arrays for the v2 solver.

Three demand cap types (per SPEC_v2.md §5G):

  "annual"          → total lbs/year; spread uniformly across all 52 weeks
                      (the optimizer can front/back-load freely within that total)

  "weekly_flat"     → constant lbs/week for all 52 weeks

  "weekly_varying"  → list of week ranges, each with a per-week lbs cap;
                      weeks NOT covered by any range → 0 demand
                      (optimizer won't schedule harvest for those weeks)

Returns a 3-D array: demand_cap[crop_idx][channel_idx][week_1indexed]
  shape: (n_crops, n_channels, 53)  — index 0 unused (weeks are 1-based)
  units: lbs/week

Channel ordering must match the CHANNELS list passed to the solver so that
index ch lines up with crop["channels"][channel_name].
"""

from __future__ import annotations

import re
import numpy as np


# ---------------------------------------------------------------------------
# Week-range parser
# ---------------------------------------------------------------------------

def _parse_week_range(range_str: str) -> tuple[int, int]:
    """
    Parse a week range string like "W1-W12" or "1-12" into (start, end) ints.

    Both endpoints are inclusive, 1-indexed.
    """
    s = range_str.strip().upper().replace("W", "")
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError(
            f"Cannot parse week range '{range_str}'. "
            f"Expected format 'W1-W12' or '1-12'."
        )
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(
            f"Cannot parse week range '{range_str}'. "
            f"Expected integer week numbers."
        )
    if not (1 <= start <= 52 and 1 <= end <= 52):
        raise ValueError(
            f"Week range '{range_str}' out of bounds. Weeks must be in [1, 52]."
        )
    if start > end:
        raise ValueError(
            f"Week range '{range_str}': start ({start}) > end ({end})."
        )
    return start, end


# ---------------------------------------------------------------------------
# Single channel demand cap → 52-element array
# ---------------------------------------------------------------------------

def expand_channel_demand(channel_spec: dict) -> np.ndarray:
    """
    Convert a single channel demand spec to a 52-element array of lbs/week.

    Parameters
    ----------
    channel_spec : dict
        One channel entry from crop["channels"][ch_name], containing at minimum:
        - "demand_cap_type": "annual" | "weekly_flat" | "weekly_varying"
        - type-specific keys (see below)

    Returns
    -------
    np.ndarray of shape (52,), dtype float, representing demand_cap for weeks 1..52.
    Index 0 corresponds to week 1.
    """
    cap_type = channel_spec.get("demand_cap_type", "").lower()

    if cap_type == "annual":
        annual = float(channel_spec["annual_demand_lbs"])
        weekly = annual / 52.0
        return np.full(52, weekly, dtype=float)

    elif cap_type == "weekly_flat":
        weekly = float(channel_spec["weekly_demand_lbs"])
        return np.full(52, weekly, dtype=float)

    elif cap_type == "weekly_varying":
        arr = np.zeros(52, dtype=float)
        ranges = channel_spec.get("demand_ranges", [])
        for r in ranges:
            start, end = _parse_week_range(r["weeks"])
            arr[start - 1 : end] = float(r["weekly_lbs"])
        return arr

    else:
        raise ValueError(
            f"Unknown demand_cap_type '{cap_type}'. "
            f"Expected 'annual', 'weekly_flat', or 'weekly_varying'."
        )


# ---------------------------------------------------------------------------
# Full demand cap table for all crops × channels
# ---------------------------------------------------------------------------

def build_demand_table(
    crops: list[dict],
    channels: list[dict],
    n_weeks: int = 52,
) -> np.ndarray:
    """
    Build the full demand cap array for the solver.

    Parameters
    ----------
    crops : list[dict]
        Full crop definitions.  Each crop must have a "channels" sub-dict
        keyed by channel name.

    channels : list[dict]
        Ordered list of channel defs (each has at least "name").
        The order determines channel index in the returned array.

    n_weeks : int
        Planning horizon (52).

    Returns
    -------
    np.ndarray of shape (n_crops, n_channels, n_weeks + 1), dtype float.
    demand_cap[c][ch][w] = max lbs crop c can be sold to channel ch in week w.
    Index w=0 is unused (weeks are 1-indexed); valid range w=1..n_weeks.
    """
    n_crops    = len(crops)
    n_channels = len(channels)

    # Shape: (n_crops, n_channels, n_weeks+1) — w=0 unused
    table = np.zeros((n_crops, n_channels, n_weeks + 1), dtype=float)

    ch_names = [ch["name"] for ch in channels]

    for c_idx, crop in enumerate(crops):
        crop_channels = crop.get("channels", {})
        for ch_idx, ch_name in enumerate(ch_names):
            if ch_name not in crop_channels:
                # No demand for this crop × channel combination → all zeros
                continue
            weekly_arr = expand_channel_demand(crop_channels[ch_name])
            # weekly_arr[0] = week 1, ..., weekly_arr[51] = week 52
            table[c_idx, ch_idx, 1 : n_weeks + 1] = weekly_arr

    return table


# ---------------------------------------------------------------------------
# Total market capacity per crop per week (used for C7)
# ---------------------------------------------------------------------------

