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


def test_absent_mode_is_irrigated_to_the_cent():
    base = solve()
    absent = golden_payload()
    del absent["water_mode"]
    out = json.loads(run_from_js(json.dumps(absent)))
    assert out["status"] == base["status"] == "optimal"
    assert out["profit"] == base["profit"]


def test_unlimited_lifts_the_water_limit_where_it_binds():
    irrigated = solve(**DRY)
    unlimited = solve(**DRY, water_mode="unlimited")
    assert irrigated["status"] == unlimited["status"] == "optimal"
    assert unlimited["profit"] > irrigated["profit"] + 100_000, (irrigated["profit"], unlimited["profit"])
    assert unlimited["water_mode"] == "unlimited"
    assert any("Don't limit by water" in w for w in unlimited["warnings"])
    # No ceiling to report: every consumer reads cap 0 as "not a constraint".
    assert not any(unlimited["weekly_water_supply"])
    assert any(unlimited["weekly_water_used"]), "water USED must still be reported"


def test_unlimited_charges_no_city_water_even_with_city_ticked():
    out = solve(**DRY, water_mode="unlimited", city_water_enabled=True, city_water_cost_per_L=0.01)
    assert out["status"] == "optimal"
    assert out["bought_capacity_split"]["city_water"] == 0.0


def test_unlimited_keeps_the_owned_water_assets_depreciated():
    irrigated, unlimited = solve(**DRY), solve(**DRY, water_mode="unlimited")
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
    assert any("Rain-fed only" in w and "of 132" in w for w in out["warnings"]), out["warnings"]
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
