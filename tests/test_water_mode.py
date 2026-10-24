"""
Batch W — water mode: Irrigated / Rain-fed only / Don't limit by water (BACKLOG BC4, SPEC_batchW).

Through run_from_js on the golden farm, because the adapter is where the form's remembered source
ticks are cleared outside Irrigated — a solver-only test would skip the boundary the mode lives on.
"""
import copy
import json
from functools import lru_cache

import pytest

from farm_v2.adapter import run_from_js
from farm_v2.utils.calendar import generate_successions
from farm_v2.utils.water import compute_net_water_rates, get_rainfall_weekly
from farm_v2.validate import validate_params
from tests.helpers import golden_payload

pytest.importorskip("scipy")


@lru_cache(maxsize=None)
def _solve(overrides_json: str) -> dict:
    return json.loads(run_from_js(json.dumps(golden_payload(**json.loads(overrides_json)))))


def solve(**overrides) -> dict:
    return _solve(json.dumps(overrides, sort_keys=True))


# The golden farm's water never binds (the 8.7M L/wk well is ample), so "unlimited" equals
# "irrigated" there and a guard on the default fixture could not tell them apart. A desert farm on
# a 2M L/wk well is water-bound: irrigated it loses money, unlimited it does not.
DRY = dict(climate_zone="southwest_desert", well_weekly_cap_L=2_000_000)
# City water ticked and priced: the form remembers ticks outside Irrigated, so every unlimited test
# shares a solve that also proves the adapter cleared them.
UNLIMITED = dict(DRY, water_mode="unlimited", city_water_enabled=True, city_water_cost_per_L=0.01)


def test_absent_mode_is_irrigated_to_the_cent(golden_out):
    absent = golden_payload()
    del absent["water_mode"]
    out = json.loads(run_from_js(json.dumps(absent)))
    assert out["status"] == golden_out["status"] == "optimal"
    assert out["profit"] == golden_out["profit"]
    # Profit alone cannot tell: water never binds on the golden farm, so "unlimited" solves to
    # within float noise of it. The echo and D11 can — an absent mode must still refuse no source.
    assert out["water_mode"] == "irrigated"
    absent["well_enabled"] = False
    refused = json.loads(run_from_js(json.dumps(absent)))
    assert refused["status"] == "invalid_input" and "No water source" in " ".join(refused["errors"])


def test_unlimited_lifts_the_water_limit_where_it_binds():
    irrigated = solve(**DRY)
    unlimited = solve(**UNLIMITED)
    assert irrigated["status"] == unlimited["status"] == "optimal"
    assert unlimited["profit"] > irrigated["profit"] + 100_000, (irrigated["profit"], unlimited["profit"])
    assert unlimited["water_mode"] == "unlimited"
    assert any("Don't limit by water" in w for w in unlimited["warnings"])
    # No ceiling to report: every consumer reads cap 0 as "not a constraint".
    assert not any(unlimited["weekly_water_supply"])
    assert any(unlimited["weekly_water_used"]), "water USED must still be reported"


def test_unlimited_charges_no_city_water_even_with_city_ticked():
    out = solve(**UNLIMITED)
    assert out["status"] == "optimal"
    assert out["bought_capacity_split"]["city_water"] == 0.0


def test_unlimited_keeps_the_owned_water_assets_depreciated():
    irrigated, unlimited = solve(**DRY), solve(**UNLIMITED)
    for cls in ("water_storage", "irrigation"):
        assert unlimited["fixed_cost_split"][cls] == irrigated["fixed_cost_split"][cls] > 0, cls


def test_rainfed_golden_farm_is_refused_with_the_reason():
    """Measured: no shipped crop is rain-plantable on any built-in climate — the solve would be
    'optimal' growing nothing (−$997k), D11's hole. Refused, naming how close rain gets."""
    out = solve(water_mode="rainfed")
    assert out["status"] == "invalid_input"
    msg = " ".join(out["errors"])
    assert "Rain-fed only" in msg and "Basil" in msg and "44%" in msg, msg


def test_rainfed_grows_only_what_rain_waters():
    """Two conditions at once: rain high enough for SOME successions, not all (×2.6 the
    Northeast normals) — otherwise the filter is either everything or a refusal."""
    out = solve(water_mode="rainfed", rainfall_weekly_multipliers=[2.6] * 52)
    assert out["status"] == "optimal"
    # The count, derived the OTHER way — zero net need in every week, which is what C3 solves
    # against — so the refusal's coverage walk cannot drift from the constraint.
    p = golden_payload()
    succ = generate_successions(p["crops"], 2024)
    rain = get_rainfall_weekly(p["climate_zone"]) * 2.6
    n_ok = int((~compute_net_water_rates(succ, p["crops"], rain).any(axis=1)).sum())
    assert 0 < n_ok < len(succ)
    assert any(f"{n_ok} of {len(succ)} possible" in w for w in out["warnings"]), (n_ok, out["warnings"])
    planted = {s["crop"] for s in out["succession_schedule"] if s["acres"] > 0.01}
    assert planted and not planted & {"Tomatoes", "Hot Peppers", "Garlic"}, planted


def test_rainfed_ignores_ticked_sources_from_the_form():
    """The form's ticks are remembered state outside Irrigated; the adapter clears them — a well
    must not water a 'rain-fed' plan."""
    out = solve(water_mode="rainfed", well_enabled=True)
    assert out["status"] == "invalid_input" and "Rain-fed only" in " ".join(out["errors"])


def test_an_unknown_mode_is_refused():
    out = solve(water_mode="drip")
    assert out["status"] == "invalid_input" and "water_mode" in " ".join(out["errors"])


def test_irrigated_with_no_source_is_still_refused():
    """D11 kept: an accidental untick in Irrigated, the default, is refused."""
    out = solve(well_enabled=False)
    assert out["status"] == "invalid_input" and "No water source" in " ".join(out["errors"])


class TestValidateDirectCallers:
    """validate_params refuses ambiguity instead of resolving it — only the adapter clears ticks."""

    def test_a_source_with_a_non_irrigated_mode_is_refused(self, minimal_params):
        for mode in ("rainfed", "unlimited"):
            p = {**copy.deepcopy(minimal_params), "water_mode": mode, "well_enabled": True,
                 "well_weekly_cap_L": 1e6}
            with pytest.raises(ValueError, match="uses no water source"):
                validate_params(**p)

    def test_no_source_is_accepted_outside_irrigated(self, minimal_params):
        for mode in ("rainfed", "unlimited"):
            p = {**copy.deepcopy(minimal_params), "water_mode": mode, "well_enabled": False,
                 "catchment_enabled": False, "city_water_enabled": False}
            validate_params(**p)


def test_one_list_of_modes_in_python_the_registry_and_the_form():
    """The mode list is written in water.py, fields.js (the assistant's enum, which the page reads)
    and the <select>. A mode added in one place would read as 'irrigated' on the client."""
    import re
    from farm_v2.utils.water import WATER_MODES
    from tests.helpers import REPO, index_src
    reg = (REPO / "public" / "fields.js").read_text()
    enum = re.search(r'water_mode: \{\s*chat: \{[^}]*?enum: \[([^\]]*)\]', reg)
    assert enum and re.findall(r'"([a-z]+)"', enum.group(1)) == list(WATER_MODES)
    select = re.search(r'<select id="water_mode">(.*?)</select>', index_src(), re.S)
    assert select and re.findall(r'value="([a-z]+)"', select.group(1)) == list(WATER_MODES)


def test_a_crop_rain_cannot_water_says_so_not_outcompeted():
    """/code-review: with C3's supply at zero the cause is physical; 'outcompeted' told the grower
    the crop lost on economics."""
    out = solve(water_mode="rainfed", rainfall_weekly_multipliers=[2.6] * 52)
    why = {r["crop"]: r for r in out["unplanted_crops"]}
    for crop in ("Tomatoes", "Hot Peppers", "Garlic"):
        assert why[crop]["reason"] == "rain_short", why[crop]
        assert 0 < why[crop]["rain_coverage"] < 1


def test_a_monte_carlo_draw_too_dry_for_any_crop_is_a_real_loss_not_a_dropped_draw():
    """/code-review: refused draws were skipped, so the dry tail vanished from the distribution.
    A draw (refuse_rain_short=False) solves the year it is: nothing planted, fixed costs carried."""
    out = solve(water_mode="rainfed", refuse_rain_short=False)
    assert out["status"] == "optimal", out.get("errors")
    assert out["profit"] < -900_000 and out["revenue"] == 0
    assert {r["reason"] for r in out["unplanted_crops"]} == {"rain_short"}
    assert any("0 of 132" in w for w in out["warnings"]), out["warnings"]
