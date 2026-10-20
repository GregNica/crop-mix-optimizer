"""
calendar.py — Week/succession utilities for the 52-week farm optimization model.

Week numbering convention:
    Week 1  = days 1–7 of the year  (Jan 1–7)
    Week 2  = days 8–14             (Jan 8–14)
    ...
    Week 52 = days 358–365/366      (Dec 24–31)

This is a simple day-of-year / 7 convention, NOT ISO 8601, to avoid the
ISO 53-week-year edge case and to keep week numbers strictly in [1, 52].
"""

import math
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Week ↔ date helpers
# ---------------------------------------------------------------------------

def week_of_year(date_str: str, year: int = 2024) -> int:
    """
    Convert "MM-DD" to a week number 1–52 for the given year.

    Examples:
        week_of_year("01-01", 2024) → 1
        week_of_year("03-15", 2024) → 11
        week_of_year("12-31", 2024) → 52
    """
    month, day = int(date_str[:2]), int(date_str[3:])
    d = date(year, month, day)
    day_of_year = d.timetuple().tm_yday       # 1-indexed
    week = math.ceil(day_of_year / 7)
    return min(week, 52)                       # clamp — last few days stay in week 52


def week_start_date(week: int, year: int = 2024) -> date:
    """Return the calendar date of the first day of week `week` (1-indexed)."""
    day_of_year = (week - 1) * 7 + 1
    return date(year, 1, 1) + timedelta(days=day_of_year - 1)


def week_end_date(week: int, year: int = 2024) -> date:
    """Return the calendar date of the last day of week `week` (1-indexed)."""
    day_of_year = week * 7
    # Clamp to Dec 31
    year_end = date(year, 12, 31)
    d = date(year, 1, 1) + timedelta(days=day_of_year - 1)
    return min(d, year_end)


# ---------------------------------------------------------------------------
# Succession auto-generation
# ---------------------------------------------------------------------------

def generate_successions(crops: list[dict], year: int = 2024) -> list[dict]:
    """
    Auto-generate all succession slots from crop definitions.

    For each crop, for each season window, one succession slot is created per
    valid start week (weekly spacing).  Season windows are PLANTING windows: a
    start week is valid when it lies in the window.  The cycle runs from there
    and may wrap past week 52 into the next cyclic year.

    Returns a flat list of succession dicts:
        {
            "name":       str,       e.g. "Spinach W11"
            "crop":       int,       index into crops list
            "weeks":      list[int], e.g. [11, 12, 13]  (1-indexed)
            "phases":     list[int], 0=plant 1=grow 2=harvest (same length as weeks)
            "start_week": int,
        }

    Phase sequence: planting_weeks × [0]  +  grow_weeks × [1]  +  harvest_weeks × [2]

    days_to_maturity is PLANT TO FIRST HARVEST, so:
        grow_weeks  = ceil(days_to_maturity / 7) − planting_weeks
        field weeks = ceil(days_to_maturity / 7) + harvest_weeks
    """
    successions = []

    for crop_idx, crop in enumerate(crops):
        # days_to_maturity is PLANT TO FIRST HARVEST — the grower's definition, and what every
        # seed catalogue and extension budget publishes. It is NOT total field occupancy.
        #
        # This used to read `total_weeks = ceil(dtm/7)` and derive grow as
        # `total - plant - harvest`, so harvest_weeks ate the growing season: basil came out
        # with ONE week of growing (35 days, 1 plant, 3 harvest) and tomatoes with three. The
        # crop was in the ground for less time than it takes to grow it, and the model
        # under-charged land, labour, water and fertiliser for every crop with a long harvest.
        #
        # Occupancy is maturity PLUS the harvest window: you cannot pick for eight weeks and
        # still clear the bed on the day the first fruit ripens.
        plant_w       = crop["planting_weeks"]
        harv_w        = crop["harvest_weeks"]
        weeks_to_harvest = math.ceil(crop["days_to_maturity"] / 7)
        grow_w        = weeks_to_harvest - plant_w
        total_weeks   = weeks_to_harvest + harv_w

        if grow_w < 0:
            raise ValueError(
                f"Crop '{crop['name']}': planting_weeks ({plant_w}) exceeds the "
                f"{weeks_to_harvest} weeks to first harvest "
                f"({crop['days_to_maturity']} days_to_maturity). Planting cannot take longer "
                f"than the crop takes to mature."
            )

        phases = [0] * plant_w + [1] * grow_w + [2] * harv_w
        # Opt-in year-wrap. Default False, so an unflagged crop behaves as it always has.
        overwinters = bool(crop.get("overwinters", False))

        # A cycle longer than the planning year would wrap onto itself and occupy the same week
        # twice. That is a perennial, which the single cyclic year cannot represent — say so
        # rather than silently double-charging its land and labour.
        if total_weeks > 52:
            raise ValueError(
                f"Crop '{crop['name']}': cycle is {total_weeks} weeks "
                f"({crop['days_to_maturity']} days_to_maturity), which exceeds the 52-week "
                f"planning year. Perennial and multi-year crops cannot be modelled here."
            )

        for season in crop["seasons"]:
            start_w = week_of_year(season["start"], year)
            end_w   = week_of_year(season["end"],   year)

            # Seasons are PLANTING windows: any start week inside the window is valid, and the
            # cycle runs from there. Previously the whole cycle had to fit inside the window,
            # which silently produced ZERO successions for any crop whose harvest fell outside
            # it. The window itself may also wrap (start > end), e.g. a Nov-to-Feb planting.
            if end_w >= start_w:
                starts = list(range(start_w, end_w + 1))
            else:
                starts = list(range(start_w, 53)) + list(range(1, end_w + 1))

            for slot_start in starts:
                # Wrap is OPT-IN, via the crop's `overwinters` flag. Every window in the
                # library was authored under the old whole-cycle meaning, so making wrap
                # universal reinterprets all of them at once and lets frost-tender crops be
                # planted in autumn to "harvest" the following spring. Without the flag the
                # cycle must still finish inside the planning year.
                if not overwinters and slot_start + total_weeks - 1 > 52:
                    continue

                # 1-indexed weeks, wrapping 52 -> 1.
                weeks = [((slot_start - 1 + k) % 52) + 1 for k in range(total_weeks)]
                successions.append({
                    "name":       f"{crop['name']} W{slot_start:02d}",
                    "crop":       crop_idx,
                    "weeks":      weeks,
                    "phases":     phases.copy(),
                    "start_week": slot_start,
                })

    return successions


# ---------------------------------------------------------------------------
# Succession lookup tables (pre-computed for solver performance)
# ---------------------------------------------------------------------------

def build_phase_table(successions: list[dict], n_weeks: int = 52) -> list[list]:
    """
    Return phase_table[i][w] = phase (0/1/2) if succession i is active in
    week w (1-indexed), else None.

    Rows = successions (0-indexed), columns = weeks 1..52.
    """
    n = len(successions)
    table = [[None] * (n_weeks + 1) for _ in range(n)]   # index 0 unused (weeks are 1-based)

    for i, s in enumerate(successions):
        for week, phase in zip(s["weeks"], s["phases"]):
            if 1 <= week <= n_weeks:
                table[i][week] = phase

    return table


def phase_weeks_of(s: dict, phase: int | None, n_weeks: int = 52) -> list[int]:
    """Weeks (1-indexed, clamped to 1..n_weeks) in which succession `s` is in `phase`
    (0 plant, 1 grow, 2 harvest), or in ANY phase when `phase` is None. The one clamp every
    per-phase divisor in the money path uses — see harvest_weeks_of for why that matters."""
    return [w for w, p in zip(s["weeks"], s["phases"])
            if (phase is None or p == phase) and 1 <= w <= n_weeks]


def harvest_weeks_of(s: dict, n_weeks: int = 52) -> list[int]:
    """Weeks (1-indexed, clamped to 1..n_weeks) in which succession `s` is harvesting.

    One definition, because the count is a DIVISOR in money-path math: the even-split
    convention charges a succession's season yield as `yield / len(harvest_weeks)` per
    harvest week, in the storage cap, the sales-supply rows, and the client's reported
    volume series. Those three had drifted — C4 omitted the divisor entirely — and the
    fix would have left three differently-clamped reimplementations behind it.

    The clamp matches build_phase_table, which is what the constraint rows index through,
    so a caller supplying successions directly (rather than via generate_successions,
    which never emits an out-of-range slot) still gets the count the solver will use.
    """
    return phase_weeks_of(s, 2, n_weeks)


# ---------------------------------------------------------------------------
# Monthly → weekly conversion
# ---------------------------------------------------------------------------

def monthly_to_weekly(monthly_array, year: int = 2024):
    """
    Convert a 12-element monthly array to a 52-element weekly array.

    Each week is assigned the value of its calendar month, determined by the
    midpoint day of the week (day 4 of the 7-day block).

    Works for any monthly quantity (water, labor, etc.).
    """
    import numpy as np

    if len(monthly_array) != 12:
        raise ValueError(f"Expected 12-element monthly array, got {len(monthly_array)}.")

    weekly = []
    for w in range(1, 53):
        mid_day    = (w - 1) * 7 + 4                                    # day of year, 1-indexed
        mid_day    = min(mid_day, 365 + (1 if _is_leap(year) else 0))   # clamp to year end
        mid_date   = date(year, 1, 1) + timedelta(days=mid_day - 1)
        month_idx  = mid_date.month - 1                                  # 0-indexed
        weekly.append(monthly_array[month_idx])

    return np.array(weekly, dtype=float)


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


# ---------------------------------------------------------------------------
# Utility: summarise succession calendar as a readable dict
# ---------------------------------------------------------------------------

PHASE_LABEL = {0: "P", 1: "G", 2: "H", None: "-"}


def succession_summary(successions: list[dict], crops: list[dict]) -> str:
    """Return a compact text calendar of all generated successions."""
    header = f"{'Succession':<30} {'Crop':<20} {'Wks':>4}  {'Calendar'}"
    lines  = [header, "-" * 90]
    for s in successions:
        crop_name = crops[s["crop"]]["name"]
        cal = " ".join(PHASE_LABEL[p] for p in s["phases"])
        lines.append(
            f"{s['name']:<30} {crop_name:<20} {len(s['weeks']):>4}  W{s['start_week']:02d}: {cal}"
        )
    return "\n".join(lines)
