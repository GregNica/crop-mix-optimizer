"""FX.1 — must-plant: floors from the commitments table, and the carry-in pin (SPEC_batchFX §3, §5).

Two floor kinds on a crop's IDENTITY (the crop and its FX.5 variants), neither escapable by not
planting (`min_acreage_if_planted` is — measured: a 14-ac garlic "minimum" went to 0 ac):
  must_stand          at least A acres IN THE GROUND every week of a window
  must_plant_annual   at least A acres PLANTED over the year
and the overwintering carry-in, migrated from C15's week-1 floor to a PIN (grower ruling 1,
2026-10-25): the acres already in the ground, exactly — none entered means none overwintered.
The demo farm says 18 ac of garlic (it planted 18.04 when it was free to choose).
An infeasible plan names the commitments and WHICH limits they press on (elastic re-solve).
"""
import pytest

from tests.helpers import (KALE_ANNUAL, ROUNDING, commitments_farm, planted, set_carry_in,
                           solve_payload as solve, solve_payload_optimal as solve_optimal, standing)


def farm(*entries, garlic=None, **overrides):
    p = commitments_farm(*entries, **overrides)
    if garlic is not None:
        set_carry_in(p, garlic)
    return p


@pytest.fixture(scope="module")
def base():
    return solve_optimal(farm())


KALE_STAND = dict(id="k1", kind="must_stand", crop="Kale", acres=8, from_week=10, to_week=20)


# ---------------------------------------------------------------------------
# Carry-in: a pin at the acres in the ground (ruling 1)
# ---------------------------------------------------------------------------

def test_demo_garlic_is_pinned_at_its_carried_in_acres(base):
    assert standing(base, "Garlic", 1) == pytest.approx(18.0, abs=ROUNDING)


def test_carry_in_is_a_ceiling_not_only_a_floor():
    """Garlic pays: left free, the plan takes ~18 ac. At 10 entered it must stand at exactly 10 —
    a floor alone would let the plan go back up to 18."""
    r = solve_optimal(farm(garlic=10))
    assert standing(r, "Garlic", 1) == pytest.approx(10.0, abs=ROUNDING)


def test_carry_in_reserves_the_fall_replant(base):
    """The cyclic year: the same plantings stand in week 1 and go in again in weeks 46-48."""
    replant = sum(s["acres"] for s in base["succession_schedule"]
                  if s["crop"] == "Garlic" and s["start_week"] in (46, 47, 48))
    assert replant == pytest.approx(18.0, abs=ROUNDING)


def test_overwintering_crop_with_no_acres_is_not_grown():
    r = solve_optimal(farm(garlic=0))
    assert planted(r, "Garlic") == 0
    assert any("Garlic" in w and "no acres are entered" in w for w in r["warnings"])
    assert next(u for u in r["unplanted_crops"] if u["crop"] == "Garlic")["reason"] == "no_carry_in"


# ---------------------------------------------------------------------------
# The two floors
# ---------------------------------------------------------------------------

def test_standing_floor_holds_every_week_of_its_window(base):
    assert min(standing(base, "Kale", w) for w in range(10, 21)) < 8 - ROUNDING   # it binds
    r = solve_optimal(farm(KALE_STAND))
    for w in range(10, 21):
        assert standing(r, "Kale", w) >= 8 - ROUNDING, w
    assert r["profit"] < base["profit"]


def test_annual_floor_counts_plantings_over_the_year(base):
    assert planted(base, "Kale") < 45 - ROUNDING                                    # it binds
    r = solve_optimal(farm(KALE_ANNUAL))
    assert planted(r, "Kale") >= 45 - ROUNDING
    assert r["profit"] < base["profit"]


def test_unaccepted_suggestion_does_not_bind(base):
    r = solve_optimal(farm(dict(KALE_ANNUAL, source="suggested")))
    assert r["profit"] == pytest.approx(base["profit"], abs=0.01)
    accepted = solve_optimal(farm(dict(KALE_ANNUAL, source="accepted")))
    assert planted(accepted, "Kale") >= 45 - ROUNDING


# ---------------------------------------------------------------------------
# Refusals name their cause
# ---------------------------------------------------------------------------

def _refused(p, words):
    r = solve(p)
    assert r["status"] == "invalid_input", r.get("status")
    assert any(words in e for e in r["errors"]), r["errors"]


@pytest.mark.parametrize("entry, words", [
    (dict(KALE_STAND, crop="Rhubarb"), "not one of the farm's crops"),
    (dict(KALE_STAND, acres=0), "acres must be positive"),
    (dict(KALE_STAND, acres="8"), "acres must be positive"),
    (dict(KALE_STAND, acres=81), "on a 80-acre farm"),
    (dict(KALE_STAND, from_week=0), "from_week must be a whole week"),
    (dict(KALE_STAND, to_week=None), "to_week must be a whole week"),
    (dict(KALE_STAND, from_week=1, to_week=1), "no planting of it can be in the ground in week 1"),
    (dict(KALE_ANNUAL, kind="contract"), "not one of the farm's channels"),
])
def test_bad_floor_is_refused(entry, words):
    _refused(farm(entry), words)


def test_overlapping_standing_floors_beyond_the_farm_name_the_land_and_the_weeks():
    """Floors are left to the solve (validation checks only exact acres): 45 ac kale + 40 ac
    spinach standing in weeks 10-20 cannot fit 80 ac, and the elastic re-solve says so."""
    r = solve(farm(dict(KALE_STAND, acres=45), dict(KALE_STAND, id="s1", crop="Spinach", acres=40)))
    assert r["status"] == "infeasible"
    land = next(b for b in r["binding_limits"] if b["limit"] == "land")
    assert set(range(10, 21)) <= set(land["weeks"])
    assert "k1" in r["errors"][0] and "s1" in r["errors"][0]


def test_two_floors_on_one_crop_are_met_by_the_same_acres():
    """Not summed: 8 ac standing and 6 ac standing on the same kale in the same weeks need 8."""
    r = solve_optimal(farm(KALE_STAND, dict(KALE_STAND, id="k3", acres=6)))
    assert min(standing(r, "Kale", w) for w in range(10, 21)) >= 8 - ROUNDING


def test_commitments_beyond_the_crew_and_barn_name_both():
    """The toy's garlic finding, in the app: 45 ac overwintered needs the fall crew AND the barn
    together — relaxing one limit alone stays infeasible, so the diagnosis must be elastic."""
    r = solve(farm(garlic=45))
    assert r["status"] == "infeasible"
    named = {b["limit"] for b in r["binding_limits"]}
    assert named == {"labour", "ambient storage"}
    assert "Garlic: 45 ac already in the ground" in r["errors"][0]
    assert "labour" in r["errors"][0] and "ambient storage" in r["errors"][0]


def test_contradicting_commitments_are_named_as_such():
    """A standing floor above the overwintered acres cannot be met by any extra capacity: the
    carry-in is exact in week 1."""
    r = solve(farm(dict(id="g1", kind="must_stand", crop="Garlic", acres=30,
                        from_week=1, to_week=10)))
    assert r["status"] == "infeasible"
    assert r["binding_limits"] is None
    assert "contradict each other" in r["errors"][0]


# ---------------------------------------------------------------------------
# Guards that force the second condition (each was inert on the plain floor tests)
# ---------------------------------------------------------------------------

def test_a_floor_that_does_not_bind_costs_nothing(base):
    """A floor is not a pin: 2 ac of kale standing in weeks 10-20, where the plan already
    stands 4-8, changes nothing. (The binding 8-ac floor cannot tell a floor from a pin.)"""
    assert min(standing(base, "Kale", w) for w in range(10, 21)) > 2 + ROUNDING
    r = solve_optimal(farm(dict(KALE_STAND, acres=2)))
    assert r["profit"] == pytest.approx(base["profit"], abs=0.01)


def test_standing_means_in_the_ground_not_harvesting():
    """The floor binds EXACTLY in some week of the window: a row that counted only harvest
    weeks (or any narrower 'standing') would force more kale than 8 everywhere."""
    r = solve_optimal(farm(KALE_STAND))
    assert min(standing(r, "Kale", w) for w in range(10, 21)) == pytest.approx(8, abs=ROUNDING)


def test_a_standing_floor_counts_the_variant():
    """FX.5 identity: in weeks 3-4 only Tunnel Spinach (sold as Spinach, planted from week 2)
    can stand — open-field Spinach starts in week 5 — so a floor on Spinach is met by it."""
    from tests.test_variants import variant_farm
    p = variant_farm()
    p["commitments"] = [dict(id="s1", kind="must_stand", crop="Spinach", acres=1,
                             from_week=3, to_week=4)]
    r = solve_optimal(p)
    assert min(standing(r, "Tunnel Spinach", w) for w in (3, 4)) >= 1 - ROUNDING


def test_callers_that_read_only_the_status_skip_the_diagnosis():
    """One-more-head re-solves and Monte Carlo draws send diagnose_infeasible=False: the same
    refusal, without the two extra solves or the sentence they would throw away."""
    r = solve(farm(garlic=45, diagnose_infeasible=False))
    assert r["status"] == "infeasible"
    assert r["binding_limits"] is None and r["errors"] == []


# ---------------------------------------------------------------------------
# /code-review high on 11b731a
# ---------------------------------------------------------------------------

def test_one_more_head_re_solves_take_the_adapters_kwargs(monkeypatch):
    """#1: the adapter's solve_kwargs carry diagnose_infeasible, and next_head_deltas once passed
    it again at the call — a TypeError the per-row except turned into 'error' on every row, so
    the one-more-head figure vanished. The adapter path was stubbed in every test."""
    import farm_v2.solver as solver
    seen = []
    monkeypatch.setattr(solver, "solve_farm_v2",
                        lambda **kw: seen.append(kw) or {"status": "optimal", "profit": 90.0})
    out = solver.next_head_deltas({"diagnose_infeasible": True, "solver_time_limit": 80.0},
                                  {"status": "optimal", "profit": 100.0,
                                   "extra_hires": [{"extra": 1}]})
    assert out == [{"delta": -10.0, "status": "optimal"}]
    assert seen[0]["diagnose_infeasible"] is False and seen[0]["force_extra"] == {0: 2}


@pytest.mark.parametrize("limit, text", [
    (dict(limit="water", unit="L", weeks=[20, 21, 22, 24], max_over=15_320.4),
     "water (weeks 20–22, 24, up to 15,320 L over)"),
    (dict(limit="cold storage", unit="m³", weeks=[30], max_over=3.14159), "cold storage (week 30, 3.14 m³ over)"),
    (dict(limit="cash", unit="$", weeks=[5, 6], max_over=12_345.6), "cash (weeks 5–6, up to $12,346 over)"),
    (dict(limit="Kale's diversity ceiling", unit="acre-weeks", weeks=[], max_over=3.2),
     "Kale's diversity ceiling (3.2 acre-weeks over)"),
])
def test_limits_read_as_plain_numbers(limit, text):
    """#3 and #8: never '1.53e+04 L'; a weekless limit is one quantity, not 'up to'."""
    from farm_v2.solver import _limits_text
    assert _limits_text([limit]) == text


def test_an_unfinished_diagnosis_does_not_claim_a_contradiction(monkeypatch):
    """#4: a diagnosis that ran out of time is not 'they contradict each other'."""
    import farm_v2.solver as solver
    monkeypatch.setattr(solver, "DIAGNOSIS_TIME_LIMIT", 1e-4)
    r = solve(farm(garlic=45))
    assert r["status"] == "infeasible"
    assert r["binding_limits_verdict"] == "unfinished"
    assert "contradict" not in r["errors"][0] and "did not finish" in r["errors"][0]
    assert r["binding_limits"] is None


def test_the_crew_and_barn_diagnosis_is_proved():
    assert solve(farm(garlic=45))["binding_limits_verdict"] == "proved"


def test_a_floor_naming_a_variant_counts_only_the_variant():
    """#6: '3 ac of Tunnel Spinach standing in weeks 20-25' is not met by field Spinach — the
    tunnel holds 2 ac, so it cannot be met at all, and the diagnosis names the tunnel's land."""
    from tests.test_variants import variant_farm
    p = variant_farm()
    p["commitments"] = [dict(id="t1", kind="must_stand", crop="Tunnel Spinach", acres=3,
                             from_week=20, to_week=25)]
    r = solve(p)
    assert r["status"] == "infeasible", r["status"]
    assert "land in High tunnel" in {b["limit"] for b in r["binding_limits"]}


def test_a_commitment_cannot_take_a_carry_in_id():
    """#7: the app names each crop's carry-in 'carry-in:<crop>'; a typed id sharing it would merge
    with it in a refusal and in a per-entry with/without."""
    _refused(farm(dict(KALE_ANNUAL, id="carry-in:Garlic")), "are reserved")


@pytest.mark.parametrize("status, named_any, verdict", [
    (0, True, "proved"),
    (1, True, "unfinished"),        # stopped on the clock WITH an incumbent: not proved minimal
    (1, False, "unfinished"),
    (0, False, "unfinished"),       # nothing over tolerance on an infeasible model: no diagnosis
    (2, False, "contradiction"),
])
def test_the_elastic_verdict(status, named_any, verdict):
    """#4: an incumbent the time limit stopped is never reported as proved. A solve cannot be made
    to stop with an incumbent on demand, so the mapping is tested on its own."""
    from farm_v2.solver import _elastic_verdict
    assert _elastic_verdict(status, named_any) == verdict
