"""FX.4 — zones: named land pools with crop eligibility (SPEC_batchFX §3).

Land (C1) is one row per zone per week, RHS acres_z / total_land. The shipped golden farm sends no
zones, so it cannot see any of this (the L4 trap) — the solves below use a 2-acre high tunnel
that BINDS, measured: tomatoes confined to it fall 5.0 → 2.0 acres and profit falls $42,593.
"""
import json

import numpy as np
import pytest

from farm_v2.adapter import run_from_js
from farm_v2.utils.calendar import generate_successions
from farm_v2.utils.water import (
    RAINFALL_OFFSET_FRACTION, WATER_PHASE_KEYS, compute_net_water_rates, get_rainfall_weekly,
    rain_coverage,
)
from farm_v2.utils.zones import WHOLE_FARM, resolve_zones
from tests.helpers import golden_payload, planted

TUNNEL = [{"name": "High tunnel", "acres": 2}, {"name": "Open field"}]


# ---------------------------------------------------------------------------
# resolve_zones — the one definition validation and the solver share
# ---------------------------------------------------------------------------

class TestResolveZones:
    @pytest.mark.parametrize("zones", [None, []])
    def test_absent_is_the_whole_farm(self, zones):
        assert resolve_zones(zones, 80) == [{"name": WHOLE_FARM, "acres": 80.0, "covered": False}]

    def test_one_blank_zone_takes_the_rest(self):
        assert resolve_zones(TUNNEL, 80) == [
            {"name": "High tunnel", "acres": 2.0, "covered": False},
            {"name": "Open field", "acres": 78.0, "covered": False}]

    def test_plots_typed_to_the_farm_in_hectares_are_accepted(self):
        # 80 ac shows as 32.37 ha; plots typed to add up to THAT are 79.988 ac — 0.012 short, which
        # 1e-6 refused (grower, 2026-10-27). Within 0.1 ac / 0.1% the plots stand as typed.
        z = resolve_zones([{"name": "High tunnel", "acres": 2.0}, {"name": "Open field", "acres": 77.988}], 80)
        assert [x["acres"] for x in z] == [2.0, 77.988]
        with pytest.raises(ValueError, match="add up to 79.5"):
            resolve_zones([{"name": "A", "acres": 2.0}, {"name": "B", "acres": 77.5}], 80)

    def test_covered_is_kept(self):
        z = resolve_zones([{"name": "High tunnel", "acres": 2, "covered": True}, {"name": "F"}], 80)
        assert [x["covered"] for x in z] == [True, False]

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
        ("High tunnel", "list of"),                        # shapes that used to raise
        (["High tunnel"], "list of"),                      # AttributeError → a traceback,
        ({"name": "A", "acres": 80}, "list of"),           # not a refusal (/code-review)
        ([{"name": "A", "acres": 2, "covered": "yes"}, {"name": "B"}], "true or false"),
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
        assert planted(baseline, "Tomatoes") > 2.0 + 1e-6
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

    @pytest.mark.parametrize("zones", ["High tunnel", ["High tunnel"]])
    def test_a_malformed_zones_payload_is_refused_not_a_traceback(self, zones):
        _refused(golden_payload(zones=zones), "list of")

    def test_the_schedule_carries_its_start_week(self, tunnel_tomatoes):
        # The Gantt labels by this field: parsing the name read "2" off "Kale W10 · Tunnel 2".
        for s in tunnel_tomatoes["succession_schedule"]:
            assert s["start_week"] == s["weeks"][0]
            assert f"W{s['start_week']:02d} · " in s["name"]

    def test_a_minimum_planting_the_eligible_plots_cannot_hold_together_is_refused(self):
        p = golden_payload(zones=TUNNEL)
        tom = next(c for c in p["crops"] if c["name"] == "Tomatoes")
        tom["zones"], tom["min_acreage_if_planted"] = ["High tunnel"], 3
        _refused(p, "hold only 2 acres together")

    def test_a_minimum_larger_than_every_eligible_plot_is_met_by_straddling_them(self):
        # X8 (2026-10-27): the minimum is on the PLANTING, summed over its plots. Tomatoes may
        # stand in two 2-ac plots only, with a 3-ac minimum and a 3-ac floor: no single plot can
        # hold a planting, so the floor is met ONLY by a planting straddling both — under FX.4's
        # per-slot minimum this farm is refused outright (/code-review: the earlier form of this
        # test passed under both rules).
        p = golden_payload(zones=[{"name": "High tunnel", "acres": 2}, {"name": "Small field", "acres": 2},
                                  {"name": "Open field"}])
        tom = next(c for c in p["crops"] if c["name"] == "Tomatoes")
        tom.update(zones=["High tunnel", "Small field"], min_acreage_if_planted=3)
        p["commitments"] = [{"id": "t1", "kind": "must_plant_annual", "crop": "Tomatoes", "acres": 3, "source": "user"}]
        out = json.loads(run_from_js(json.dumps(p)))
        assert out["status"] == "optimal", out.get("errors") or out.get("error")
        assert not any("cannot be planted in" in w for w in out["warnings"])
        by_planting = {}
        for s in out["succession_schedule"]:
            if s["crop"] == "Tomatoes" and s["acres"] > 1e-6:
                by_planting.setdefault(s["start_week"], {})[s["zone"]] = s["acres"]
        assert by_planting, "the floor was met by nothing"
        for start, plots in by_planting.items():
            assert sum(plots.values()) >= 3 - 1e-6, (start, plots)          # the planting as a whole
            assert len(plots) == 2 and all(a < 3 for a in plots.values()), (start, plots)   # straddling

    def test_an_unplanted_crop_confined_to_a_full_plot_names_the_plot(self):
        # The diagnosis scanned farm-wide series only: a crop that lost on land it could not leave
        # read "outcompeted" with no tightest resource while its plot sat at 100% (landing review).
        import copy
        from tests.helpers import ASPARAGUS
        p = golden_payload(zones=TUNNEL)
        p["crops"].append(dict(copy.deepcopy(ASPARAGUS), zones=["High tunnel"]))
        p["commitments"] = [{"id": "p1", "kind": "perennial", "crop": "Asparagus", "zone": "High tunnel", "acres": 2,
                             "planted_year": 2019, "yield_per_acre": 1750, "harvest_from_week": 18, "harvest_to_week": 25,
                             "source": "user"}]
        tom = next(c for c in p["crops"] if c["name"] == "Tomatoes")
        tom["zones"] = ["High tunnel"]                          # the patch fills its only plot all year
        out = json.loads(run_from_js(json.dumps(p)))
        assert out["status"] == "optimal", out.get("errors") or out.get("error")
        rec = next(r for r in out["unplanted_crops"] if r["crop"] == "Tomatoes")
        assert rec["reason"] == "outcompeted"
        assert rec["tightest"] and rec["tightest"]["resource"] == "land in High tunnel", rec
        assert rec["tightest"]["utilization"] >= 0.95

    def test_commitments_that_overfill_one_zone_together_are_refused(self):
        # Each fits the 2-ac tunnel alone; together they need 3. Was a bare HiGHS "infeasible".
        p = golden_payload(zones=TUNNEL)
        for name, acres in (("Garlic", 2), ("Kale", 1)):
            c = next(c for c in p["crops"] if c["name"] == name)
            c.update(zones=["High tunnel"], committed_acres=acres, overwinters=True)
        _refused(p, "can only stand in High tunnel")

    def test_a_commitment_that_may_spill_into_another_zone_is_not_refused(self):
        # Hall's condition, not a per-zone sum: Kale may also use the field, so 2 + 1 fits.
        p = golden_payload(zones=TUNNEL)
        g = next(c for c in p["crops"] if c["name"] == "Garlic")
        g.update(zones=["High tunnel"], committed_acres=2)
        k = next(c for c in p["crops"] if c["name"] == "Kale")
        k.update(committed_acres=1, overwinters=True)
        out = json.loads(run_from_js(json.dumps(p)))
        assert out["status"] == "optimal", out.get("errors")
        tunnel, field = out["zones"]
        assert tunnel["used_acres"][0] == pytest.approx(2.0, abs=1e-3)   # garlic fills it
        assert field["used_acres"][0] >= 1.0 - 1e-3                      # kale stands outside

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


# ---------------------------------------------------------------------------
# Covered zones — no rain reaches a high tunnel (grower, 2026-10-25)
# ---------------------------------------------------------------------------

class TestCoveredZones:
    def test_a_covered_planting_gets_no_rain_credit(self, spinach_crop):
        # A covered slot carries rain fraction 0 (the solver's wiring is tested end to end below).
        succs = generate_successions([spinach_crop])[:1]
        rain = np.full(52, 50_000.0)                          # rain in every week
        open_, shut = (compute_net_water_rates(succs, [spinach_crop], rain, [f])
                       for f in (0.65, 0.0))
        weeks = succs[0]["weeks"]
        assert (open_[0, weeks] < shut[0, weeks]).all()       # rain helped in the open
        assert list(shut[0, weeks]) == [spinach_crop[WATER_PHASE_KEYS[p]]
                                         for p in succs[0]["phases"]]
        assert rain_coverage(succs, [spinach_crop], rain, [0.0])[0] == 0.0
        assert rain_coverage(succs, [spinach_crop], rain, [0.65])[0] > 0.0

    def test_covering_the_tunnel_adds_exactly_its_lost_rain(self, tunnel_tomatoes):
        # Same plan, measured; the delta is rebuilt by hand from the crop's phase needs and the
        # climate's rain, independently of the solver's water rows.
        covered = _solve(zones=[dict(TUNNEL[0], covered=True), TUNNEL[1]],
                         tunnel_only=("Tomatoes",))
        assert covered["status"] == "optimal"
        assert covered["zones"][0]["covered"] is True
        plan = lambda o: [(s["name"], s["acres"]) for s in o["succession_schedule"]]
        assert plan(covered) == plan(tunnel_tomatoes)
        p = golden_payload()
        tom = next(c for c in p["crops"] if c["name"] == "Tomatoes")
        rain = get_rainfall_weekly(p["climate_zone"])
        offset = rain * RAINFALL_OFFSET_FRACTION
        lost = sum(s["acres"] * min(tom[WATER_PHASE_KEYS[ph]], offset[w - 1])
                   for s in covered["succession_schedule"] if s["zone"] == "High tunnel"
                   for w, ph in zip(s["weeks"], s["phases"]))
        assert lost > 1_000_000                               # the effect is not negligible
        delta = sum(covered["weekly_water_used"]) - sum(tunnel_tomatoes["weekly_water_used"])
        assert delta == pytest.approx(lost, rel=1e-4)

    def test_rain_fed_wording_knows_the_tunnel_is_dry(self):
        # rain_coverage only WORDS the Rain-fed refusal, so nothing else pins its wiring: with
        # every crop in a covered tunnel, the closest crop must read 0%, not the open-field 44%.
        p = golden_payload(water_mode="rainfed",
                           zones=[dict(TUNNEL[0], covered=True), TUNNEL[1]])
        for c in p["crops"]:
            c["zones"] = ["High tunnel"]
            c["committed_acres"] = 0       # FX.1: 18 ac of carried-in garlic cannot fit 2 ac
        _refused(p, "rain covers 0%")
