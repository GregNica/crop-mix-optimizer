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
        # An ANNUAL cap is a yearly total, not a weekly one. It used to be spread as
        # `annual / 52` in every week, which quietly turned a 52,000 lb contract into a flat
        # 1,000 lb/wk ceiling — so a crop harvesting in only 10 weeks could deliver 10,000 lb
        # of it and the rest was unsellable. A grower reads this field as a contract volume,
        # and the docstring claimed front/back-loading was allowed.
        #
        # There is no weekly bound now. The yearly total is enforced by its own row in the
        # solver (see `build_annual_caps` and C6b), which is the only place a sum over weeks
        # can be expressed.
        return np.full(52, np.inf, dtype=float)

    elif cap_type == "weekly_flat":
        weekly = float(channel_spec["weekly_demand_lbs"])
        return np.full(52, weekly, dtype=float)

    elif cap_type == "weekly_varying":
        arr = np.zeros(52, dtype=float)
        ranges = channel_spec.get("demand_ranges", [])
        for r in ranges:
            start, end = _parse_week_range(r["weeks"])
            # ACCUMULATE, do not assign. Two buyers wanting 1,000 lb/wk in overlapping weeks
            # are 2,000 lb of capacity that week, not 1,000. Assignment also made the result
            # ORDER-DEPENDENT: whichever range was listed last silently won, so a farm with a
            # W1-W20 contract and a W10-W15 top-up saw the top-up REPLACE the contract for
            # those six weeks. The lower figure usually won, so the model under-planned and
            # nothing indicated why.
            arr[start - 1 : end] += float(r["weekly_lbs"])
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


def build_annual_caps(
    crops: list[dict],
    channels: list[dict],
) -> dict[tuple[int, int], float]:
    """Yearly total caps, keyed by (crop_index, channel_index).

    Only channels whose `demand_cap_type` is "annual" appear. These cannot be expressed in the
    weekly demand table at all — a yearly total is a sum across weeks, so it needs its own
    constraint row. `expand_channel_demand` returns +inf for these weeks precisely so the
    weekly rows impose nothing and this is the single binding statement.
    """
    caps: dict[tuple[int, int], float] = {}
    for c_idx, crop in enumerate(crops):
        crop_channels = crop.get("channels", {})
        for ch_idx, ch in enumerate(channels):
            spec = crop_channels.get(ch["name"]) if crop_channels else None
            if not spec:
                continue
            if str(spec.get("demand_cap_type", "")).lower() == "annual":
                caps[(c_idx, ch_idx)] = float(spec["annual_demand_lbs"])
    return caps
