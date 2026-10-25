"""FX.4 — zones: named land pools with crop eligibility (SPEC_batchFX §3).

Land (C1) is one row per zone per week, RHS acres_z / total_land. The shipped golden farm sends no
zones, so it cannot see any of this (the L4 trap) — the solves below use a 2-acre high tunnel
that BINDS, measured: tomatoes confined to it fall 5.0 → 2.0 acres and profit falls $42,593.
"""
import json

import pytest

from farm_v2.adapter import run_from_js
from farm_v2.utils.calendar import generate_successions
from farm_v2.utils.zones import WHOLE_FARM, resolve_zones
from tests.helpers import golden_payload

TUNNEL = [{"name": "High tunnel", "acres": 2}, {"name": "Open field"}]


# ---------------------------------------------------------------------------
# resolve_zones — the one definition validation and the solver share
# ---------------------------------------------------------------------------

class TestResolveZones:
    @pytest.mark.parametrize("zones", [None, []])
    def test_absent_is_the_whole_farm(self, zones):
        assert resolve_zones(zones, 80) == [{"name": WHOLE_FARM, "acres": 80.0}]

    def test_one_blank_zone_takes_the_rest(self):
        assert resolve_zones(TUNNEL, 80) == [{"name": "High tunnel", "acres": 2.0},
                                             {"name": "Open field", "acres": 78.0}]

    @pytest.mark.parametrize("zones, match", [
        ([{"name": "A", "acres": 30}, {"name": "B", "acres": 30}], "add up to 60"),
        ([{"name": "A", "acres": 50}, {"name": "B", "acres": 40}], "add up to 90"),
        ([{"name": "A", "acres": 80}, {"name": "B"}], "takes the rest"),
        ([{"name": "A"}, {"name": "B"}], "Only one zone"),
        ([{"name": "A", "acres": 2}, {"name": "A"}], "unique"),
        ([{"name": "", "acres": 80}], "needs a name"),
        ([{"name": "A", "acres": 0}, {"name": "B"}], "must be > 0"),
        ([{"name": "A", "acres": -2}, {"name": "B"}], "must be > 0"),
        ([{"name": "A", "acres": float("nan")}, {"name": "B"}], "must be > 0"),
        ([{"name": "A", "acres": "2"}, {"name": "B"}], "must be a number"),
        ([{"name": "A", "acres": True}, {"name": "B"}], "must be a number"),
    ])
    def test_malformed_zones_are_refused_by_name(self, zones, match):
        with pytest.raises(ValueError, match=match):
            resolve_zones(zones, 80)


# ---------------------------------------------------------------------------
# generate_successions — one slot per (start week, eligible zone)
# ---------------------------------------------------------------------------

class TestZonedSuccessions:
    def test_no_zones_is_the_old_calendar(self, spinach_crop):
        succs = generate_successions([spinach_crop])
        assert {s["zone"] for s in succs} == {0}
        assert all(s["name"] == f"Spinach W{s['start_week']:02d}" for s in succs)

    def test_a_crop_in_two_zones_gets_a_slot_in_each_with_unique_names(self, spinach_crop):
        one = generate_successions([spinach_crop])
        two = generate_successions([spinach_crop], 2024, ["High tunnel", "Open field"])
        assert len(two) == 2 * len(one)
        assert len({s["name"] for s in two}) == len(two)
        assert {s["zone"] for s in two} == {0, 1}
        assert two[0]["name"].endswith("· High tunnel")

    def test_names_follow_the_farm_not_the_crops_eligibility(self, spinach_crop):
        # Narrowing one crop's zones must not rename its plantings: the suffix is keyed on the
        # farm having zones, so "Spinach W11 · Open field" is the same slot either way.
        zones = ["High tunnel", "Open field"]
        both = generate_successions([spinach_crop], 2024, zones)
        field = generate_successions([dict(spinach_crop, zones=["Open field"])], 2024, zones)
        assert {s["zone"] for s in field} == {1}
        assert [s["name"] for s in field] == [s["name"] for s in both if s["zone"] == 1]

    @pytest.mark.parametrize("zones, match", [
        (["Shade house"], "does not have"),     # the toy's absent-zone leak: refused, not skipped
        ([], "at least one"),
        ("High tunnel", "at least one"),        # a bare string is not a list of names
    ])
    def test_eligibility_the_farm_cannot_honour_is_refused(self, spinach_crop, zones, match):
        with pytest.raises(ValueError, match=match):
            generate_successions([dict(spinach_crop, zones=zones)], 2024,
                                 ["High tunnel", "Open field"])


# ---------------------------------------------------------------------------
# Through run_from_js — the seam every new payload key must be tested at
# ---------------------------------------------------------------------------

def _solve(**overrides):
    tunnel_only = overrides.pop("tunnel_only", ())
    p = golden_payload(**overrides)
    for c in p["crops"]:
        if c["name"] in tunnel_only:
            c["zones"] = ["High tunnel"]
    return json.loads(run_from_js(json.dumps(p)))


def _refused(p, match):
    out = json.loads(run_from_js(json.dumps(p)))
    assert out["status"] == "invalid_input"
    assert match in " ".join(out["errors"])


@pytest.fixture(scope="module")
def baseline(golden_out):
    assert golden_out["status"] == "optimal"
    return golden_out


@pytest.fixture(scope="module")
def tunnel_tomatoes():
    out = _solve(zones=TUNNEL, tunnel_only=("Tomatoes",))
    assert out["status"] == "optimal", out.get("errors") or out.get("error")
    return out


def _acres(out, crop):
    return sum(s["acres"] for s in out["succession_schedule"] if s["crop"] == crop)


class TestZonesThroughTheAdapter:
    def test_no_zones_reports_one_whole_farm_zone(self, baseline):
        (z,) = baseline["zones"]
        assert (z["name"], z["acres"]) == (WHOLE_FARM, 80.0)
        assert {s["zone"] for s in baseline["succession_schedule"]} == {WHOLE_FARM}

    def test_naming_the_whole_farm_explicitly_changes_nothing(self, spinach_crop):
        # Pure: the same zone list yields the same successions, so the same LP — no solve needed.
        assert resolve_zones([{"name": WHOLE_FARM, "acres": 80}], 80) == resolve_zones(None, 80)
        assert (generate_successions([spinach_crop], 2024, [WHOLE_FARM])
                == generate_successions([spinach_crop]))

    def test_splitting_land_every_crop_may_use_changes_nothing(self, baseline):
        # Identical objective at mip_rel_gap 1e-9 (measured 1,617,655.27 both). At the shipped
        # 1e-4 gap a tied optimum lands ~$20 away, so allow the gap, not the cent.
        out = _solve(zones=TUNNEL)
        assert out["profit"] == pytest.approx(baseline["profit"], abs=100)

    def test_a_crop_confined_to_a_zone_stays_inside_it(self, tunnel_tomatoes):
        tom = [s for s in tunnel_tomatoes["succession_schedule"] if s["crop"] == "Tomatoes"]
        assert tom and {s["zone"] for s in tom} == {"High tunnel"}
        for z in tunnel_tomatoes["zones"]:
            assert max(z["used_acres"]) <= z["acres"] + 1e-6, z["name"]

    @pytest.mark.parametrize("which", ["baseline", "tunnel_tomatoes"])
    def test_land_series_are_the_schedule_standing_each_week(self, which, request):
        # Rebuilt from the planting schedule — each planting's own zone and acres — independently
        # of the solver's per-zone table, which C1 and the zone report SHARE: binning every
        # planting into one zone moved both together and passed every other test here (mutant
        # M2). Schedule acres are rounded to 0.1 ac, hence the tolerance.
        out = request.getfixturevalue(which)
        standing = {z["name"]: [0.0] * 52 for z in out["zones"]}
        for s in out["succession_schedule"]:
            for w in s["weeks"]:
                standing[s["zone"]][w - 1] += s["acres"]
        for z in out["zones"]:
            assert z["used_acres"] == pytest.approx(standing[z["name"]], abs=0.5), z["name"]
        farm = [sum(col) / 80 for col in zip(*standing.values())]
        assert out["weekly_land_frac"] == pytest.approx(farm, abs=0.01)
        assert max(out["weekly_land_frac"]) > 0.5     # a plan is standing, not an empty series

    def test_the_tunnel_binds_so_these_guards_can_fail(self, baseline, tunnel_tomatoes):
        # Without this the tests above pass on a zone the plan never presses against.
        tunnel = tunnel_tomatoes["zones"][0]
        assert tunnel["name"] == "High tunnel"
        assert max(tunnel["used_acres"]) == pytest.approx(2.0, abs=1e-3)
        assert _acres(baseline, "Tomatoes") > 2.0 + 1e-6
        assert baseline["profit"] - tunnel_tomatoes["profit"] > 10_000

    @pytest.mark.parametrize("zones, crop_zones, match", [
        (TUNNEL, ["Shade house"], "does not have"),
        (None, ["High tunnel"], "does not have"),       # a crop zoned on a farm with no zones
        ([{"name": "A", "acres": 30}], None, "add up to 30"),
    ])
    def test_zones_the_farm_cannot_honour_are_refused(self, zones, crop_zones, match):
        p = golden_payload()
        if zones is not None:
            p["zones"] = zones
        if crop_zones is not None:
            p["crops"][0]["zones"] = crop_zones
        _refused(p, match)

    def test_a_commitment_bigger_than_its_zones_is_refused(self):
        p = golden_payload(zones=TUNNEL)
        garlic = next(c for c in p["crops"] if c["name"] == "Garlic")
        garlic["zones"] = ["High tunnel"]
        garlic["committed_acres"] = 3
        _refused(p, "hold only 2")

    def test_zones_are_refused_even_when_validation_fails_open(self, monkeypatch):
        # Step 0 swallows a CRASHED guard and solves anyway; the solver resolves zones itself
        # so an unknown zone still cannot reach C1 without a land row.
        import farm_v2.solver as solver

        def crash(**_):
            raise RuntimeError("guard crashed")
        monkeypatch.setattr(solver, "validate_params", crash)
        p = golden_payload(zones=TUNNEL)
        p["crops"][0]["zones"] = ["Shade house"]
        _refused(p, "does not have")
