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

            # SEASONS ARE PLANTING WINDOWS (B5), AND CYCLES MAY WRAP THE YEAR (B6).
            #
            # This used to require the WHOLE cycle to fit inside the window and inside weeks
            # 1-52. Growers enter these as planting windows — "I can put spinach in the ground
            # from February to mid-June" — so the old reading silently deleted any succession
            # whose harvest fell outside the window. Three shipped templates generated ZERO
            # successions and simply never appeared in a plan: Winter Squash, Melon and
            # Snap/Snow Peas.
            #
            # It also made the year a wall. Nothing could be planted after about week 45, land
            # sat structurally idle in November and December, and no crop could overwinter —
            # which is why garlic, whose real planting is September to November, carried a
            # fabricated January-to-August window just to produce any successions at all.
            #
            # A start week is now valid if it lies in the window, full stop. The cycle runs from
            # there and wraps into the next cyclic year if it must. The model is a steady state:
            # the weeks a wrapped succession occupies at the start of the year are the same
            # weeks last year's planting occupies, so charging them here is correct.
            #
            # The window itself may also wrap (start > end), e.g. a November-to-February
            # planting window, which was previously an empty range and therefore silent.
            if end_w >= start_w:
                starts = list(range(start_w, end_w + 1))
            else:
                starts = list(range(start_w, 53)) + list(range(1, end_w + 1))

            for slot_start in starts:
                if not (1 <= slot_start <= 52):
                    continue

                # WRAPPING IS OPT-IN, via the crop's `overwinters` flag.
                #
                # Relaxing containment (B5) and allowing wrap (B6) are separate changes, and
                # making wrap universal would silently re-interpret every window in the library.
                # Those windows were authored under the OLD meaning — "the whole cycle fits in
                # here" — so read as planting windows they permit absurdities: Hot Peppers
                # planted in mid-October and Tomatoes in early October, both frost-tender,
                # harvesting into the following spring. Measured: universal wrap moved the
                # golden farm's profit +63%, and that is where a good part of it came from.
                #
                # So a cycle must still finish inside the planning year unless the crop says it
                # overwinters. Garlic is the one that does, and its window is grower-sourced.
                # Every other template keeps exactly the behaviour its window was written for.
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
    return [w for w, p in zip(s["weeks"], s["phases"]) if p == 2 and 1 <= w <= n_weeks]


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
