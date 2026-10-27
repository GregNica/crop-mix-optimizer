"""THE FX GOLDEN FARM AS THE FORM SENDS IT (Batch FX UI step).

test_fx_farm.py pins the fixed layer on a payload built in CODE (tests/helpers.py `fx_farm`),
because until the UI step the form could not express a zone, a variant, a perennial or a
commitment. scripts/capture_fx_payload.cjs now builds the SAME farm as a saved plan, loads it
through applyFormState like any plan and reads buildSolveParams off the real page; this file pins
what comes out — so what is pinned is what the form can send — and compares the two builds of
one farm like for like.

Measured 2026-10-26: the form's build solves to $619,446.39 against the code fixture's
$619,491.10, and the whole −$44.71 is ONE field — the crop card takes whole pounds per tote, so
the asparagus packs at 57 lb/tote (0.0011954 m³/lb) where the code fixture says 0.0012 m³/lb
exactly; with that one value swapped the form's payload solves to 619,491.10 to the cent.
Everything else the two payloads differ in was measured to move nothing: `shelf_life_weeks: 2`
vs the card's `sales_spread_weeks: 2` (the solver reads one through the other), a
`crop_diversity_max` on the perennial card (C8 skips pinned patches), and Kale's zones listed
against the form leaving them out (both mean every zone).
"""
import copy
import json

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import re

from tests.helpers import (REPO, ASPARAGUS, FX_COMMITMENTS, TUNNEL_AND_FIELD, assert_pnl_line,  # noqa: E402
                           fx_farm, index_src, pnl_tolerance)
from tests.test_fx_farm import FX_GOLDEN  # noqa: E402

FORM_PAYLOAD = REPO / "tests" / "golden" / "fx_farm_payload.json"
FORM_STATE = REPO / "tests" / "golden" / "fx_farm_form_state.json"

# The form's own pin (2026-10-26, first capture). Re-pin ONLY with a reason, as for the others.
#   2026-10-27 (X8): 619,446.39 → 619,523.26 (+$76.87) with the per-planting minimum — inside the
#   solver's 1e-4 gap, like the code pin's −$72.59 (its note in test_fx_farm.py); the tote-rounding
#   distance below moved −$44.71 → +$104.75 the same way. The payload the form builds is
#   byte-identical to the 2026-10-26 capture; only the solver moved.
FORM_GOLDEN = {**FX_GOLDEN,
               "revenue":          2_498_263.98,
               "variable_cost":      483_084.42,
               "overhead_cost":      399_722.24,
               "interest_cost":        2_871.75,
               "profit":             619_523.26,
               "operating_profit": 1_035_117.25}


def js_const(name):
    """A `const NAME = …;` literal from index.html, as the page defines it."""
    m = re.search(rf"^const {name} = (.+?);[ \t]*(?://.*)?$", index_src(), re.M | re.S)   # may span lines
    assert m, f"index.html defines no `const {name}`"
    return json.loads(m.group(1).replace("'", '"'))


TOTE_M3 = js_const("TOTE_M3")          # one 18-gallon harvest tote, m³


@pytest.fixture(scope="module")
def captured():
    return json.loads(FORM_PAYLOAD.read_text())


@pytest.fixture
def form_payload(captured):
    """A fresh copy per test — several tests edit it."""
    return copy.deepcopy(captured)


@pytest.fixture(scope="module")
def form_res():
    from farm_v2.adapter import run_from_js
    r = json.loads(run_from_js(json.dumps(json.loads(FORM_PAYLOAD.read_text()))))
    assert r["status"] == "optimal", r.get("error")
    return r


def test_the_capture_exists_and_is_the_saved_plan_shape():
    state = json.loads(FORM_STATE.read_text())
    assert state["zones"] and state["commitments"] and any(c.get("perennial") for c in state["crops"])
    assert {e["id"] for e in state["commitments"]} == {e["id"] for e in FX_COMMITMENTS}


def test_the_form_builds_the_code_fixtures_fixed_layer(form_payload):
    """Every fixed-layer piece the code fixture carries, the form's payload carries the same way
    — zones, each crop's kind and eligibility, and the commitments table (ids, kinds, figures)."""
    form, code = form_payload, fx_farm()
    assert form["zones"] == [dict(z, covered=z.get("covered", False)) for z in TUNNEL_AND_FIELD]
    assert [c["name"] for c in form["crops"]] == [c["name"] for c in code["crops"]]
    by_form = {c["name"]: c for c in form["crops"]}
    for c in code["crops"]:
        f = by_form[c["name"]]
        assert f.get("sells_as") == c.get("sells_as"), c["name"]
        assert bool(f.get("perennial")) == bool(c.get("perennial")), c["name"]
        # Eligibility: the form leaves zones out when every zone is ticked (Kale, both zones).
        if c.get("zones") and set(c["zones"]) != {z["name"] for z in TUNNEL_AND_FIELD}:
            assert f["zones"] == c["zones"], c["name"]
        else:
            assert "zones" not in f, c["name"]
    # Commitments: the form adds `source: "user"`, drops a deliver contract's null penalty and a
    # patch's absent harvest weeks; everything else is the fixture's figure.
    code_by_id = {e["id"]: {k: v for k, v in e.items() if v is not None} for e in FX_COMMITMENTS}
    for e in form["commitments"]:
        assert e.pop("source") == "user"
        want = dict(code_by_id[e["id"]])
        if want["kind"] == "perennial":
            want.setdefault("extra_cost_per_acre", 0)
        assert e == want, e["id"]


def test_the_variant_sends_no_inherited_key_and_the_perennial_no_calendar(form_payload):
    from farm_v2.utils.variants import INHERITED_KEYS
    form = {c["name"]: c for c in form_payload["crops"]}
    tunnel = form["Tunnel Spinach"]
    assert not set(INHERITED_KEYS) & set(tunnel), set(INHERITED_KEYS) & set(tunnel)
    assert tunnel["min_acreage_if_planted"] == 0.25 and len(tunnel["seasons"]) == 2
    asp = form["Asparagus"]
    for k in ("seasons", "days_to_maturity", "planting_weeks", "harvest_weeks", "min_acreage_if_planted",
              "committed_acres", "overwinters", "planting_type", "labor_plant", "water_plant"):
        assert k not in asp, k
    for k in ("labor_grow", "labor_harv", "water_grow", "water_harv", "fert_grow", "fert_harv", "fuel_grow",
              "fuel_harv", "crop_protection_cost_per_acre", "channels", "cold_storage"):
        assert asp[k] == ASPARAGUS[k], k
    # The one measured difference, stated: whole pounds per tote.
    assert asp["crop_size_m3_per_lb"] == pytest.approx(TOTE_M3 / 57, rel=1e-9)
    assert asp["sales_spread_weeks"] == ASPARAGUS["shelf_life_weeks"]


def test_the_form_payload_solves_to_its_pin(form_res):
    for line in FORM_GOLDEN:
        assert_pnl_line(form_res, FORM_GOLDEN, line,
                        "The FORM's build of the FX farm moved; if the code fixture (test_fx_farm.py) "
                        "is unchanged, the form now sends a different farm from the same saved plan.")


def test_the_only_distance_from_the_code_pin_is_the_tote_rounding(form_res, form_payload):
    """The two builds of one farm agree to the cent once the tote is the code fixture's exact
    m³/lb — so the form's pin is the code's pin plus one named, measured difference, not drift.
    The distance was −$44.71 under FX.4's per-zone minimum and is +$104.75 under X8 (2026-10-27):
    a 0.4% change in asparagus storage volume moves where HiGHS stops inside its 1e-4 gap, so the
    size and sign of the distance are tolerance; the identity (exact tote → the code pin to the
    cent) is the measurement."""
    from farm_v2.adapter import run_from_js
    assert form_res["profit"] == pytest.approx(FX_GOLDEN["profit"] + 104.75, abs=pnl_tolerance("profit"))
    p = form_payload
    next(c for c in p["crops"] if c["name"] == "Asparagus")["crop_size_m3_per_lb"] = ASPARAGUS["crop_size_m3_per_lb"]
    r = json.loads(run_from_js(json.dumps(p)))
    assert r["status"] == "optimal"
    assert r["profit"] == pytest.approx(FX_GOLDEN["profit"], abs=pnl_tolerance("profit"))


def test_every_piece_is_live_in_the_form_build(form_res):
    """The liveness the code fixture has (test_fx_farm.py), on the form's payload: the tunnel
    full, both spinaches in one market, the patches pinned, the contracts short where the toy
    said and the deliver one filled."""
    tunnel = next(z for z in form_res["zones"] if z["name"] == "High tunnel")
    assert max(tunnel["used_acres"]) == pytest.approx(tunnel["acres"], abs=1e-6)
    assert {s["commitment_id"] for s in form_res["succession_schedule"] if s["commitment_id"]} == {"p1", "p2"}
    by_id = {c["id"]: c for c in form_res["contracts"]}
    assert by_id["c3"]["short_lbs"] == 0 and by_id["c1"]["short_kind"] == "fact"
    assert {w["week"] for w in by_id["c1"]["by_week"] if w["short"] >= 1} == {36, 37}
    assert by_id["c2"]["short_lbs"] > 0
    sat = form_res["demand_saturation"]["Farmers Market"]["Spinach"]
    assert set(sat["sold_by"]) == {"Spinach", "Tunnel Spinach"}


# ---------------------------------------------------------------------------
# The two solver additions the UI step made
# ---------------------------------------------------------------------------

def test_sold_by_names_only_the_members_that_sold(form_res, form_payload):
    """FX.5 (3)/(6): `sold_by` is the client's label — "Spinach market (Tunnel Spinach)" when only
    the variant sold. A crop with no variant lists itself; an identity lists the members with
    pounds on that channel and no other."""
    for ch, by_crop in form_res["demand_saturation"].items():
        for crop, e in by_crop.items():
            # A planted crop that sold NOTHING on this channel has a row (fill 0) and nobody in it.
            assert bool(e["sold_by"]) == (e["sold_lbs"] > 1e-6), (ch, crop, e["sold_by"], e["sold_lbs"])
            for name in e["sold_by"]:
                sold = sum(form_res["channel_sales"][ch]["by_crop"].get(name, {}).get("weekly_lbs") or [0])
                assert sold > 1e-6, (ch, crop, name, "listed as selling but sold nothing")
    kale = form_res["demand_saturation"]["Wholesale"]["Kale"]
    assert kale["sold_by"] == ["Kale"]
    # A member that sold nothing on a channel is NOT listed, even though it is in the identity.
    p = form_payload
    tunnel = next(c for c in p["crops"] if c["name"] == "Tunnel Spinach")
    tunnel["seasons"] = [{"start": "01-02", "end": "01-16"}]      # a planting window nothing sells from
    tunnel["min_acreage_if_planted"] = 1.9                         # the tunnel cannot hold a lot: not planted
    from farm_v2.adapter import run_from_js
    r = json.loads(run_from_js(json.dumps(p)))
    assert r["status"] == "optimal"
    for ch in ("Farmers Market", "Wholesale"):
        e = r["demand_saturation"].get(ch, {}).get("Spinach")
        if e:
            assert e["sold_by"] == ["Spinach"], (ch, e["sold_by"])


def test_the_pricing_loop_has_one_wall_clock_budget(monkeypatch):
    """X13: ONE budget for the LOOP — the first entries are priced, the rest come back `time_limit`
    unsolved — never a hung tab. Two held entries (the carry-in and a contract) on a FAKE clock that
    advances 400 s per read against a 500 s budget: the first is priced, the second is not. A
    per-entry budget (the clock reset inside the loop — the unbounded loop back) prices both; a
    one-entry fixture could not tell the two apart (/code-review G24, mutation-verified)."""
    import farm_v2.solver as solver
    from tests.helpers import commitments_farm
    from farm_v2.adapter import run_from_js
    p = commitments_farm(dict(id="c1", kind="contract", crop="Kale", channel="Wholesale", lb_per_week=1000,
                              from_week=20, to_week=30, mode="penalty", penalty_per_lb=0.5))
    p["commitment_deltas"] = True

    class FakeClock:
        now = 0.0

        @classmethod
        def monotonic(cls):
            cls.now += 400.0
            return cls.now
    monkeypatch.setattr(solver, "time", FakeClock)
    monkeypatch.setattr(solver, "COMMITMENT_DELTAS_BUDGET_S", 500.0)
    calls = []
    orig = solver.milp

    def counting_milp(*a, **kw):
        calls.append(1)
        return orig(*a, **kw)
    monkeypatch.setattr(solver, "milp", counting_milp)
    r = json.loads(run_from_js(json.dumps(p)))
    assert r["status"] == "optimal"
    by_id = {d["id"]: d for d in r["commitment_deltas"]}
    assert set(by_id) == {"carry-in:Garlic", "c1"}
    statuses = [d["status"] for d in r["commitment_deltas"]]
    assert statuses == ["optimal", "time_limit"], statuses
    assert by_id["c1"]["delta"] is None and by_id["carry-in:Garlic"]["delta"] is not None
    # The unpriced entry cost no solve: the base solve and the one priced entry only.
    assert len(calls) == 2, calls


def test_the_clients_inherited_and_carry_in_spellings_are_the_solvers():
    """The client deletes a variant's inherited keys from a NAMED list and joins carry-in deltas on
    a NAMED id prefix; both are spellings of something the solver owns (variants.INHERITED_KEYS,
    commitments.CARRY_IN). Pinned together, or a key added on one side passes silently: the solver
    refuses only a DIFFERENT value, so an inherited key the client forgot to drop goes through as
    a copy, and a renamed prefix blanks the carry-in's cost column with no error."""
    from farm_v2.utils.commitments import CARRY_IN
    from farm_v2.utils.variants import INHERITED_KEYS
    from tests.helpers import golden_payload
    client = set(js_const("CROP_INHERITED_KEYS"))
    sent_by_the_form = set(golden_payload()["crops"][0])
    assert client == set(INHERITED_KEYS) & sent_by_the_form, (
        f"client drops {sorted(client)}; the solver inherits {sorted(set(INHERITED_KEYS) & sent_by_the_form)} "
        "of the keys the form sends")
    assert js_const("CARRY_IN_ID_PREFIX") == CARRY_IN
