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


@pytest.fixture(scope="module")
def golden_out():
    """One solve of the unmodified golden payload, shared by every read-only assertion —
    three tests solved the identical payload independently at ~2.7s each."""
    return json.loads(_run_from_js()(json.dumps(_payload())))


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


def test_an_untruncated_solve_carries_no_gap_note(golden_out):
    assert golden_out.get("status") == "optimal"
    assert not golden_out.get("gap_note"), "an optimal solve must not warn about a time limit"


def test_bought_hour_rate_arrays_survive_the_adapter(golden_out):
    """52 entries each, so renderLaborPlan can print the price a bought hour carries."""
    assert golden_out.get("status") == "optimal"
    assert len(golden_out.get("hire_rate_full_weekly", [])) == 52
    assert len(golden_out.get("overtime_rate_full_weekly", [])) == 52
    assert min(golden_out["hire_rate_full_weekly"]) > 0, (
        "a published hire rate of $0 is the free-labour defect showing through the display"
    )


def test_fractional_headcount_survives_the_adapter(golden_out):
    """The What-If labor lever scales counts fractionally (+10% of 2 workers = 2.2).

    The adapter used int(), which truncated 2.2 back to 2 — reintroducing the rounding no-op
    one layer below the fix. A fractional count must change the wage bill it produces."""
    p = _payload()
    emp = next(e for e in p["employees"] if e["type"] != "salary")
    # Precondition, so roster drift cannot make this guard silently inert: the int()
    # truncation is only distinguishable from correct behavior when the truncated scaled
    # count equals the ORIGINAL count (int(2×1.2)=2 → wages flat under the mutation). If a
    # golden re-capture ever changes this row's count so that stops holding, fail loudly
    # here instead of letting the mutation slip through a still-green assertion.
    assert int(emp["count"] * 1.2) == int(emp["count"]), (
        f"golden roster drifted (first non-salary count={emp['count']}): pick a row where "
        f"int(count*1.2) == count, or the truncation mutation becomes undetectable"
    )
    emp["count"] = emp["count"] * 1.2
    out = json.loads(_run_from_js()(json.dumps(p)))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    assert out["fixed_cost_split"]["wages"] > golden_out["fixed_cost_split"]["wages"] + 1.0, (
        "scaling one row's count by 1.2 did not move the committed wage bill — the adapter "
        "is truncating fractional headcounts again"
    )


@pytest.mark.parametrize("key", ["credit_line", "cost_fert_per_lb",
                                 "overhead_pct_of_revenue"])
def test_a_blanked_numeric_field_is_a_status_not_a_traceback(key):
    """parseFloat('') is NaN, JSON.stringify(NaN) is 'null', so a blanked box arrives as a
    PRESENT None — p.get's default never applies — and float(None) used to hand the grower a
    raw TypeError traceback instead of a plan. For genuinely optional/rate fields the adapter
    treats present-None as absent (the documented default). Whatever the solve concludes, it
    must be a status dict, never the blanket-except 'error' path."""
    p = _payload()
    p[key] = None
    out = json.loads(_run_from_js()(json.dumps(p)))
    assert out.get("status") != "error", (
        f"a null {key} still crashes the adapter: {out.get('error', '')[:200]}"
    )


@pytest.mark.parametrize("key", ["harvest_storage_cap", "water_storage_capacity"])
def test_a_blanked_capacity_field_is_refused_not_invented(key):
    """The first version of the present-None fix defaulted these too — and a blanked storage
    box then solved 'optimal' while charging depreciation on the 1e9 no-constraint default
    (profit −$25.9B rendered as a plan), and a blanked tank box invented $5.8k/yr. Capacity
    and price boxes that are always sent must be REFUSED when blanked, loudly, same contract
    as well_weekly_cap_L ('the value would be invented'). Absent stays the documented default
    for toggle-off/server callers — only present-None is refused."""
    p = _payload()
    p[key] = None
    out = json.loads(_run_from_js()(json.dumps(p)))
    assert out.get("status") == "error" and key in out.get("error", ""), (
        f"a blanked {key} was not refused — the solve ran on an invented value "
        f"(status={out.get('status')}, profit={out.get('profit')})"
    )


def test_the_payroll_load_reaches_a_hired_hour_through_the_adapter():
    """Kills deleting the hired_wage_load_pct kwarg from the adapter's solve call.

    The /simplify pass moved the load multiplication from the adapter into labor.py; the only
    tests asserting the load called compute_labor_arrays directly, so removing the kwarg
    would silently resurrect the 25% hire under-pricing for every browser caller with the
    whole suite green. This runs the REAL adapter with flex on and pins the published rate."""
    p = _payload(labor_flex_enabled=True, hire_enabled=True, max_hire_hrs_per_week=400.0,
                 hire_wage_markup=0.0, hired_wage_per_hr=19.0, payroll_load_pct=0.25)
    out = json.loads(_run_from_js()(json.dumps(p)))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    assert out["hire_rate_full_weekly"][0] == pytest.approx(19.0 * 1.25), (
        f"typed $19.00 at 25% payroll load published as "
        f"${out['hire_rate_full_weekly'][0]}/hr — the load fell out of the adapter→labor.py "
        f"hand-off (19.00 = zero-applied, 29.6875 = double-applied)"
    )


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
