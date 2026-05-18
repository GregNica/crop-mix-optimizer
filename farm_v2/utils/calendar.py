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


def weeks_in_range(start_str: str, end_str: str, year: int = 2024) -> list[int]:
    """Return the list of week numbers covered by ["MM-DD", "MM-DD"]."""
    s = week_of_year(start_str, year)
    e = week_of_year(end_str, year)
    return list(range(s, e + 1))


# ---------------------------------------------------------------------------
# Succession auto-generation
# ---------------------------------------------------------------------------

def generate_successions(crops: list[dict], year: int = 2024) -> list[dict]:
    """
    Auto-generate all succession slots from crop definitions.

    For each crop, for each season window, one succession slot is created per
    valid start week (weekly spacing).  A start week is valid when the full
    crop cycle fits within the season window and within weeks 1–52.

    Returns a flat list of succession dicts:
        {
            "name":       str,       e.g. "Spinach W11"
            "crop":       int,       index into crops list
            "weeks":      list[int], e.g. [11, 12, 13]  (1-indexed)
            "phases":     list[int], 0=plant 1=grow 2=harvest (same length as weeks)
            "start_week": int,
        }

    Phase sequence: planting_weeks × [0]  +  grow_weeks × [1]  +  harvest_weeks × [2]
    grow_weeks is derived as  ceil(days_to_maturity / 7) − planting_weeks − harvest_weeks
    """
    successions = []

    for crop_idx, crop in enumerate(crops):
        total_weeks   = math.ceil(crop["days_to_maturity"] / 7)
        plant_w       = crop["planting_weeks"]
        harv_w        = crop["harvest_weeks"]
        grow_w        = total_weeks - plant_w - harv_w

        if grow_w < 0:
            raise ValueError(
                f"Crop '{crop['name']}': planting_weeks ({plant_w}) + "
                f"harvest_weeks ({harv_w}) exceed total cycle "
                f"({total_weeks} weeks from {crop['days_to_maturity']} days_to_maturity)."
            )

        phases = [0] * plant_w + [1] * grow_w + [2] * harv_w

        for season in crop["seasons"]:
            start_w = week_of_year(season["start"], year)
            end_w   = week_of_year(season["end"],   year)

            # Last valid start: slot must finish by end_w and by week 52
            last_start = min(end_w - total_weeks + 1, 52 - total_weeks + 1)

            for slot_start in range(start_w, last_start + 1):
                slot_end = slot_start + total_weeks - 1
                if slot_start < 1 or slot_end > 52:
                    continue

                weeks = list(range(slot_start, slot_start + total_weeks))
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


def successions_active_in_week(successions: list[dict], week: int) -> list[int]:
    """Return indices of successions that are active (any phase) in the given week."""
    return [i for i, s in enumerate(successions) if week in s["weeks"]]


def successions_in_phase_in_week(
    successions: list[dict], phase: int, week: int
) -> list[int]:
    """Return indices of successions that are in `phase` during `week`."""
    result = []
    for i, s in enumerate(successions):
        if week in s["weeks"]:
            idx = s["weeks"].index(week)
            if s["phases"][idx] == phase:
                result.append(i)
    return result


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
