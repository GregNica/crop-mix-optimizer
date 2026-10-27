"""Shared test helpers.

Pure functions only — fixtures live in conftest.py. These are imported by more than one test
module, which is the whole point: a second copy of an oracle or a contract's key set is how one
of them comes to lag the thing it is meant to pin.
"""
from __future__ import annotations

import copy
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


def golden_payload(**overrides) -> dict:
    """The shipped farm's payload with `overrides` applied — a fresh dict each call.

    A MISSING file skips the calling module instead of erroring at collection: five modules read
    this at import (fx_farm, variants, perennials, toy), and a collection error aborts the whole
    pytest session, not just those tests (/code-review G22). A corrupt file still fails loudly."""
    import json
    import pytest
    if not GOLDEN_PAYLOAD.exists():
        pytest.skip("golden payload missing", allow_module_level=True)
    p = json.loads(GOLDEN_PAYLOAD.read_text())
    p.update(overrides)
    return p


# FX.1 (ruling 1): the demo's garlic is 18 ac ALREADY IN THE GROUND, pinned exactly. A fixture
# that cuts the crew, the water or the zones can make that pin unmeetable — a real refusal — so a
# test about something else sets the carry-in it can hold, here, with the reason beside it.
def set_carry_in(p: dict, acres: float, crop: str = "Garlic") -> dict:
    """`p` with `crop`'s acres already in the ground set to `acres` (0 = none overwintered)."""
    next(c for c in p["crops"] if c["name"] == crop)["committed_acres"] = acres
    return p


def commitments_farm(*entries, **overrides) -> dict:
    """The golden farm with `entries` as its commitments table (Batch FX fixtures)."""
    p = golden_payload(**overrides)
    p["commitments"] = copy.deepcopy(list(entries))
    return p


def weekly(r: dict, channel: str, crop: str) -> list:
    """A crop's weekly pounds into a channel off the solver's own `channel_sales` (52, week 1
    first); zeros when it sold nothing there."""
    return (r["channel_sales"].get(channel, {}).get("by_crop", {}).get(crop, {})
            .get("weekly_lbs") or [0.0] * 52)


def weekly_identity(r: dict, channel: str, *crops: str) -> list:
    """An IDENTITY's weekly pounds into a channel: the named crops' series summed (FX.5)."""
    return [sum(v) for v in zip(*(weekly(r, channel, c) for c in crops))]


# Schedule acres are reported to 0.1 ac, so sums of them carry that rounding.
ROUNDING = 0.15
TOL_LB = 0.5


def standing(r: dict, crop: str, w: int) -> float:
    """Acres of `crop` in the ground in week `w` of the solved plan."""
    return sum(s["acres"] for s in r["succession_schedule"] if s["crop"] == crop and w in s["weeks"])


def planted(r: dict, crop: str) -> float:
    """Acres of `crop` planted over the year, from the solver's own per-crop figure — NOT a sum
    of schedule rows, which the adapter rounds to 0.1 ac each (nine kale rows carry ±0.45 of
    rounding, and a sum that lands on the floor exactly is luck). 0 when it grew none."""
    return float((r["crop_contribution"].get(crop) or {}).get("acres_planted", 0.0))


def by_id(r: dict, key: str, cid: str) -> dict:
    """The entry with id `cid` in the result list `r[key]` (perennial_blocks, contracts, ...)."""
    return next(e for e in r[key] if e["id"] == cid)


def golden_crop(name: str) -> dict:
    return next(c for c in golden_payload()["crops"] if c["name"] == name)


def load_toy_lp():
    """toy_models/toy_v12_lp.py as a module — the toy's oracle, loaded by path (it is not a
    package), fresh each call so a test that mutates its tables cannot leak into another."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("toy_v12_lp", REPO / "toy_models" / "toy_v12_lp.py")
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    return lp


def index_src() -> str:
    """The app's single HTML file, as text."""
    return INDEX.read_text()


def solve_payload(p: dict) -> dict:
    """`p` solved through the app's adapter, as the browser would — the decoded result."""
    import json
    from farm_v2.adapter import run_from_js
    return json.loads(run_from_js(json.dumps(p)))


def solve_payload_optimal(p: dict) -> dict:
    """solve_payload, asserting a plan came back (with the refusal's reasons if not)."""
    r = solve_payload(p)
    assert r["status"] == "optimal", r.get("errors") or r.get("error")
    return r


# ---------------------------------------------------------------------------
# Money-pin tolerances (test_golden_farm.py, test_fx_farm.py)
# ---------------------------------------------------------------------------
# $50 is the solver noise floor, not a comfort margin. The MILP is solved by HiGHS via scipy,
# and different builds (notably Pyodide's vs a local venv) settle on solutions that differ by
# a couple of dollars on a $443k plan — the browser reports $443,460 where this path reports
# $443,458. Pinning to the literal dollar would make the test fail on a scipy upgrade and
# teach everyone to re-pin reflexively, which is exactly the habit that makes a money guard
# worthless. $50 is 0.011% of profit, while every real defect found in this codebase moved
# $10k-$171k, so nothing that matters can hide under it.
DOLLAR = 50.0

# ...but only TWO of the pinned lines actually need that much room, and giving it to the other five
# is what let a real $5.30 movement sit inside the guard while the pin stayed stale.
#
# Measured 2026-07-30 across the W4 refactor, which broke an LP tie differently: revenue,
# variable_cost, fixed_cost and operating_profit came out IDENTICAL TO THE CENT, while `profit` and
# `interest_cost` moved $5.30 — because interest is charged on the *cash curve*, so it depends on
# WHICH of several equally-optimal planting weeks HiGHS picks, not just on the plan's economics.
#
# So the two cash-timed lines keep the $50, and the rest are pinned to the cent. That is strictly
# stronger than one loose tolerance everywhere: a $44 regression in fixed_cost can no longer hide,
# and the two lines that legitimately drift no longer force everyone else to tolerate drift too.
# It also makes the failure diagnostic — a break in the tight set means the PLAN moved, a break in
# the loose set alone means its cash timing did.
CASH_TIMED_LINES = {"profit", "interest_cost"}
CENT = 0.01


def pnl_tolerance(line: str) -> float:
    return DOLLAR if line in CASH_TIMED_LINES else CENT


def assert_pnl_line(result: dict, pinned: dict, line: str, hint: str = "") -> None:
    """One P&L line of a solved result against its pin, at that line's tolerance."""
    import pytest
    got, want, tol = result[line], pinned[line], pnl_tolerance(line)
    assert got == pytest.approx(want, abs=tol), (
        f"{line} moved: ${got:,.2f} vs the pinned ${want:,.2f} (delta ${got - want:+,.2f}, "
        f"tolerance ${tol}). Money changed — identify the cause and, if the new number is the "
        f"more honest one, re-pin it with a note. {hint}".rstrip())


def assert_pnl_identities(r: dict, overhead_pct: float) -> None:
    """The pinned numbers must also be internally consistent, so a re-pin cannot paper over a
    broken P&L by adjusting one line. The contributions identity is the strongest money
    assertion available: per-crop contributions minus the plan-level costs must rebuild the
    headline to the cent — a cost line double-counted, dropped or in the wrong bucket breaks it.
    No labour term of any kind (W12: wages are a committed weekly cost inside `fixed_cost`), and
    bought capacity (city water, overtime, hire, a contract penalty) is plan-level too."""
    import pytest
    bought = sum(r["bought_capacity_split"].values())      # strict: every key, no `.get(…, 0)`
    assert r["operating_profit"] == pytest.approx(
        r["revenue"] - r["fixed_cost"] - r["variable_cost"] - bought, abs=CENT)
    assert r["overhead_cost"] == pytest.approx(r["revenue"] * overhead_pct, rel=1e-6)
    contributions = sum(d["contribution"] for d in r["crop_contribution"].values())
    rebuilt = contributions - r["fixed_cost"] - r["fixed_selling_cost"] - r["interest_cost"] - bought
    assert rebuilt == pytest.approx(r["profit"], abs=CENT), (
        f"per-crop contributions do not rebuild net profit: {rebuilt:,.2f} vs {r['profit']:,.2f}. "
        "A cost line is missing, doubled, or in the wrong bucket.")


# ---------------------------------------------------------------------------
# Batch FX fixture data (test_perennials.py, test_variants.py, test_fx_farm.py)
# ---------------------------------------------------------------------------
# The toy's asparagus (toy_v12_lp.py): yield 1,750 lb/ac from UKY 2016; the channel prices and
# caps, the input rates and the establishing patch's $800 extra are round placeholders.
ASPARAGUS = dict(
    name="Asparagus", perennial=True, cold_storage=True, crop_size_m3_per_lb=0.0012,
    shelf_life_weeks=2, labor_grow=0.5, labor_harv=5.5, water_grow=100000, water_harv=100000,
    fert_grow=2.0, fert_harv=2.0, fuel_grow=1.0, fuel_harv=3.0, crop_protection_cost_per_acre=150,
    seed_transplant_cost_per_acre=500,      # on the card, and NEVER charged to a block (sunk)
    channels={"Wholesale": {"price_per_lb": 1.75, "packaging_cost_per_lb": 0.15,
                            "demand_cap_type": "weekly_flat", "weekly_demand_lbs": 1500},
              "Farmers Market": {"price_per_lb": 4.00, "packaging_cost_per_lb": 0.30,
                                 "demand_cap_type": "weekly_varying",
                                 "demand_ranges": [{"weeks": "W18-W25", "weekly_lbs": 300}]}})


# The toy's two asparagus blocks (test_perennials.py addresses them as c1/c2; the FX farm re-ids them).
BEARING = dict(id="c1", kind="perennial", crop="Asparagus", acres=3, planted_year=2019,
               yield_per_acre=1750, harvest_from_week=18, harvest_to_week=25)
ESTABLISHING = dict(id="c2", kind="perennial", crop="Asparagus", acres=1, planted_year=2025,
                    yield_per_acre=0, extra_cost_per_acre=800)
KALE_ANNUAL = dict(id="k2", kind="must_plant_annual", crop="Kale", acres=45)


def variant_of(parent: dict, **own) -> dict:
    """`parent` with every inherited field left out (the variant takes them) and `own` applied."""
    from farm_v2.utils.variants import INHERITED_KEYS
    return {**{k: v for k, v in copy.deepcopy(parent).items() if k not in INHERITED_KEYS}, **own}


# The FX golden farm (SPEC_batchFX §3 FX.7): the shipped farm plus every fixed-layer piece at once,
# each one MEASURED to bind or move money on this farm (2026-10-26), because the shipped golden
# carries none of it and is blind to all of it (the L4 trap). The toy's fixed layer (toy_v12_lp.py)
# where its numbers bind here too; where they did not, the measured reason is beside the entry.
# A covered 2-ac high tunnel and the open field — the two-zone farm the variant and FX tests share.
TUNNEL_AND_FIELD = [{"name": "High tunnel", "acres": 2, "covered": True}, {"name": "Open field"}]
FX_COMMITMENTS = [
    # FX.2 — a bearing patch and an establishing one (the toy's two blocks)
    dict(BEARING, id="p1"), dict(ESTABLISHING, id="p2"),
    # FX.1 — both floor kinds, on kale. The toy's spring window (weeks 10-20) is INERT here: the
    # 45-ac annual floor already stands 19-24 ac of kale there (own delta $44, inside $318 of
    # solver noise). A fall window (42-46 or 40-44) is REFUSED — kale's harvest crew collides
    # with garlic's replant in week 48, the FX.1 fall-crew check. Weeks 24-30 stand 6.0 ac
    # without the floor and exactly 8.0 with it.
    dict(id="k1", kind="must_stand", crop="Kale", acres=8, from_week=24, to_week=30),
    KALE_ANNUAL,
    # FX.3 — the toy's three contracts: two penalty ones that are PARTLY unmeetable (kale has no
    # harvest in weeks 36-37, spinach's 35-36 sit in the summer gap) and a deliver one that binds.
    dict(id="c1", kind="contract", crop="Kale", channel="Wholesale", lb_per_week=1500,
         from_week=20, to_week=40, mode="penalty", penalty_per_lb=0.50),
    dict(id="c2", kind="contract", crop="Spinach", channel="Wholesale", lb_per_week=2000,
         from_week=28, to_week=36, mode="penalty", penalty_per_lb=0.50),
    dict(id="c3", kind="contract", crop="Asparagus", channel="Wholesale", lb_per_week=500,
         from_week=18, to_week=25, mode="deliver", penalty_per_lb=None),
]


def fx_farm(**overrides) -> dict:
    """The FX golden farm's payload; `overrides` apply before the fixed layer is added.

    Built in code rather than captured from the form because the form cannot express any of it
    yet — the UI step should re-capture it from the browser (tests/golden/) the way the shipped
    farm's payload was, so that what is pinned is what the form can send; it lives here, not in
    test_fx_farm.py, because that step's client guards will solve the same farm.
    """
    p = commitments_farm(*FX_COMMITMENTS, **overrides)
    # FX.4 — a covered 2-ac tunnel and the open field. Every open-field crop is confined to it
    # (a crop eligible everywhere gets a copy of each slot per zone — X8 ties them to one planting); kale is
    # the one crop allowed in both, as in the toy; the variant is the tunnel's.
    p["zones"] = copy.deepcopy(TUNNEL_AND_FIELD)
    for c in p["crops"]:
        c["zones"] = ["Open field", "High tunnel"] if c["name"] == "Kale" else ["Open field"]
    # FX.5 — the toy's variant: the same spinach with the tunnel's longer windows and a
    # tunnel-sized minimum block, sold AS Spinach.
    spinach = next(c for c in p["crops"] if c["name"] == "Spinach")
    p["crops"].append(variant_of(
        spinach, name="Tunnel Spinach", sells_as="Spinach", zones=["High tunnel"],
        min_acreage_if_planted=0.25,
        seasons=[{"start": "01-02", "end": "06-30"}, {"start": "08-01", "end": "12-15"}]))
    p["crops"].append(dict(copy.deepcopy(ASPARAGUS), zones=["Open field"]))
    return p


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
    "sold_by",      # FX.5: the names whose pounds these are (the key is the identity's)
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


def spinach_fm_cap() -> float:
    """Spinach's Farmers Market weekly ceiling, read from the payload through the independent
    oracle so a re-pinned golden demand cannot leave a guard measuring a stale number. A function,
    not a constant: a missing payload must SKIP the tests that need it, not break every module
    that imports helpers at collection."""
    return max(c for _, c in expand_weekly_caps(golden_crop("Spinach")["channels"]["Farmers Market"]))
