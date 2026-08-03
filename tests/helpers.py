"""Shared test helpers.

Pure functions only — fixtures live in conftest.py. These are imported by more than one test
module, which is the whole point: a second copy of an oracle or a contract's key set is how one
of them comes to lag the thing it is meant to pin.
"""
from __future__ import annotations

import pathlib

# ---------------------------------------------------------------------------
# Where the app lives
# ---------------------------------------------------------------------------
# Six modules had each re-derived this with their own `parent.parent` walk. They are all correct
# today and all break one at a time the day `public/` or `tests/` moves, which is the same reason
# this module exists at all.
REPO = pathlib.Path(__file__).resolve().parent.parent
INDEX = REPO / "public" / "index.html"
# The shipped farm's payload, as the browser sends it. Four modules had each re-derived this
# path with their own `parent` walk — same reason as REPO above.
GOLDEN_PAYLOAD = REPO / "tests" / "golden" / "default_farm_payload.json"


def index_src() -> str:
    """The app's single HTML file, as text."""
    return INDEX.read_text()


# ---------------------------------------------------------------------------
# Shared solve cache
# ---------------------------------------------------------------------------
# The MILP is the slow part of these suites and the fixtures are deterministic, so a solve is
# reused across every test that wants it.
_SOLVE_CACHE: dict = {}


def solved_once(key: str, params: dict):
    """Solve `params` once per session and return (result, params)."""
    from farm_v2.solver import solve_farm_v2
    if key not in _SOLVE_CACHE:
        res = solve_farm_v2(**params)
        assert res["status"] == "optimal", f"{key} did not solve: {res.get('status')}"
        _SOLVE_CACHE[key] = (res, params)
    return _SOLVE_CACHE[key]


# ---------------------------------------------------------------------------
# demand_saturation helpers (W6)
# ---------------------------------------------------------------------------
# The full key set of one `demand_saturation` entry. Asserted in more than one module, so it is
# defined once — otherwise adding a field makes one test fail for the wrong reason.
SATURATION_KEYS = {
    "basis", "cap_lbs", "sold_lbs", "fill",
    "peak_week_frac", "peak_week_cap_lbs", "weeks_at_cap", "binding",
}


def saturation_entries(res: dict):
    """Flatten res["demand_saturation"] to [(channel, crop, entry), ...]."""
    return [(ch, cp, e)
            for ch, by_crop in (res.get("demand_saturation") or {}).items()
            for cp, e in by_crop.items()]


def expand_weekly_caps(spec: dict) -> list[tuple[int, float]]:
    """[(week, cap)] for weeks this channel spec caps; empty for an annual contract.

    A DELIBERATE reimplementation of demand.py's expansion. Calling the production helper would
    make the at-cap assertions circular — they would be checking the solver against itself. It
    lives here so there is ONE independent oracle rather than a copy per test module, and unlike
    the copies it replaced it accepts the bare `1-12` range form that `_parse_week_range` allows.
    """
    kind = str(spec["demand_cap_type"]).lower()
    if kind == "annual":
        return []
    if kind == "weekly_flat":
        return [(w, float(spec["weekly_demand_lbs"])) for w in range(1, 53)]
    caps: dict[int, float] = {}
    for r in spec["demand_ranges"]:
        start, end = (r["weeks"].strip().upper().replace("W", "")).split("-")
        for w in range(int(start), int(end) + 1):
            caps[w] = caps.get(w, 0.0) + float(r["weekly_lbs"])   # accumulate, like S7
    return sorted((w, c) for w, c in caps.items() if c > 0)


def annual_equivalent_cap(spec: dict) -> float:
    """The whole year's cap for a channel spec, on whichever basis it uses."""
    if str(spec["demand_cap_type"]).lower() == "annual":
        return float(spec["annual_demand_lbs"])
    return sum(cap for _w, cap in expand_weekly_caps(spec))
