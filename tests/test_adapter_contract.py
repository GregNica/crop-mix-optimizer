"""The adapter's forwarding contract — solver keys that must reach the browser.

The recurring false-green mechanism in this repo is a field that exists in the solver and dies
in the adapter: W6's demand_at_cap_threshold, then city_water_cost, then gap_note. Each looked
live (solver computed it, a UI site read it, a test passed) while every browser solve got the
default. These tests EXECUTE the real adapter — a regex over its source cannot catch a key
that is simply absent from a dict literal.
"""
import json
import pathlib

import pytest

from tests.test_committed_wages import _run_from_js

GOLDEN = pathlib.Path(__file__).resolve().parent / "golden" / "default_farm_payload.json"


def _payload(**overrides):
    p = json.loads(GOLDEN.read_text())
    p.update(overrides)
    return p


def test_gap_note_survives_the_adapter():
    """A time-limited solve must carry its own health warning to the browser.

    solver.py attaches gap_note ("...best plan found within the budget, not a proven optimum")
    on status time_limit_feasible, and the browser has always read res.gap_note — but the
    adapter never forwarded it, so the falsy check went quiet and a truncated plan rendered
    exactly like a proven-optimal one. Substituting the solver isolates the contract: whatever
    the solver returns as gap_note must land in the adapter's JSON verbatim.
    """
    run, ns = _run_from_js(return_ns=True)
    real_solve = ns["solve_farm_v2"]
    note = "Stopped at the time limit — this is the best plan found within the budget, " \
           "not a proven optimum."

    def truncated_solve(**kwargs):
        r = real_solve(**kwargs)
        r["status"] = "time_limit_feasible"
        r["gap_note"] = note
        return r

    ns["solve_farm_v2"] = truncated_solve
    out = json.loads(run(json.dumps(_payload())))
    assert out.get("status") == "time_limit_feasible", (
        f"the adapter no longer passes a time-limited solve through its success path: "
        f"{out.get('status')} {out.get('error', '')[:200]}"
    )
    assert out.get("gap_note") == note, (
        "gap_note did not survive the adapter — a truncated solve renders as proven-optimal"
    )


def test_an_untruncated_solve_carries_no_gap_note():
    run = _run_from_js()
    out = json.loads(run(json.dumps(_payload())))
    assert out.get("status") == "optimal"
    assert not out.get("gap_note"), "an optimal solve must not warn about a time limit"


def test_city_water_fixed_fee_reaches_the_solver_through_the_adapter():
    """The standing charge was a solver feature + P&L label + green pytest with NO path in.

    run_from_js never read the key, so the feature was silently $0 on every browser solve while
    tests/cost_splits_client.cjs fed it through a fixture the adapter could never emit. This
    runs the fee through the real adapter and requires the solver to charge it.
    """
    run = _run_from_js()
    out = json.loads(run(json.dumps(_payload(
        city_water_enabled=True,
        city_water_cost_per_L=0.003,
        city_water_fixed_fee_per_week=400.0,
    ))))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    assert out["fixed_cost_split"].get("city_water_fixed_fee") == pytest.approx(400.0 * 52), (
        "city_water_fixed_fee_per_week was sent in the payload and did not reach the "
        "fixed-cost split — the adapter dropped it again"
    )
