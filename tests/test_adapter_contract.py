"""The adapter's forwarding contract — solver keys that must reach the browser.

The recurring false-green mechanism in this repo is a field that exists in the solver and dies
in the adapter: W6's demand_at_cap_threshold, then city_water_cost, then gap_note. Each looked
live (solver computed it, a UI site read it, a test passed) while every browser solve got the
default. These tests EXECUTE the real adapter — a regex over its source cannot catch a key
that is simply absent from a dict literal.
"""
import base64
import json
import re
import subprocess
import sys

import pytest

import farm_v2.adapter
from farm_v2.adapter import run_from_js
from tests.helpers import REPO, golden_payload, index_src


@pytest.fixture(scope="module")
def golden_out():
    """One solve of the unmodified golden payload, shared by every read-only assertion —
    three tests solved the identical payload independently at ~2.7s each."""
    return json.loads(run_from_js(json.dumps(golden_payload())))


def test_gap_note_survives_the_adapter(monkeypatch):
    """A time-limited solve must carry its own health warning to the browser.

    solver.py attaches gap_note ("...best plan found within the budget, not a proven optimum")
    on status time_limit_feasible, and the browser has always read res.gap_note — but the
    adapter never forwarded it, so the falsy check went quiet and a truncated plan rendered
    exactly like a proven-optimal one. Substituting the solver isolates the contract: whatever
    the solver returns as gap_note must land in the adapter's JSON verbatim.
    """
    real_solve = farm_v2.adapter.solve_farm_v2
    note = "Stopped at the time limit — this is the best plan found within the budget, " \
           "not a proven optimum."

    def truncated_solve(**kwargs):
        r = real_solve(**kwargs)
        r["status"] = "time_limit_feasible"
        r["gap_note"] = note
        return r

    monkeypatch.setattr(farm_v2.adapter, "solve_farm_v2", truncated_solve)
    out = json.loads(run_from_js(json.dumps(golden_payload())))
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
    assert min(golden_out["hire_rate_full_weekly"]) > 0, (
        "a published hire rate of $0 is the free-labour defect showing through the display"
    )


def test_labor_by_role_survives_the_adapter_and_sums_to_the_farm(golden_out):
    """F3 (L.1): the roster as named weekly rows, one per employee row, 52 entries, 0-indexed.

    The farm's capacity is DERIVED from these rows, so their task hours must sum to the weekly
    supply the page charts (flex is off on the golden farm, so supply = capacity). A key added
    to the solver but not the adapter is the W6 failure; this executes the adapter."""
    rows = golden_out.get("labor_by_role")
    assert rows and len(rows) == len(golden_payload()["employees"])
    for r in rows:
        assert r["position"]
        for k in ("heads", "paid_hours", "task_hours", "cost"):
            assert len(r[k]) == 52, (r["position"], k)
    # supply = crew capacity + the overtime bought that week (L.2 puts overtime in the plan).
    supply, ot = golden_out["weekly_labor_supply"], golden_out["overtime_hours_weekly"]
    for i in range(52):
        assert abs(sum(r["task_hours"][i] for r in rows) + ot[i] - supply[i]) < 0.05 * len(rows), i
    # A seasonal role is OFF outside its window (week indices 0-based), on inside it.
    assert any(min(r["heads"]) == 0 < max(r["heads"]) for r in rows), "no windowed role"
    # One basis for every weekly labour series (the 52/53 split produced a false finding).
    assert len(golden_out["overtime_hours_weekly"]) == 52
    assert len(golden_out["hired_hours_weekly"]) == 52


def test_fractional_headcount_survives_the_adapter(golden_out):
    """The What-If labor lever scales counts fractionally (+10% of 2 workers = 2.2).

    The adapter used int(), which truncated 2.2 back to 2 — reintroducing the rounding no-op
    one layer below the fix. A fractional count must change the wage bill it produces."""
    p = golden_payload()
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
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    assert out["fixed_cost_split"]["wages"] > golden_out["fixed_cost_split"]["wages"] + 1.0, (
        "scaling one row's count by 1.2 did not move the committed wage bill — the adapter "
        "is truncating fractional headcounts again"
    )


def test_the_result_does_not_echo_cash_inputs_back():
    """E2b: `opening_cash` / `credit_line` used to be echoed into the result dict. Their last
    reader (renderConstraintSummary) died with W7 and every live site reads `params.*`, so the
    echo was a second copy of an input that could drift from the first — the shape this repo
    keeps paying for. Held out of E2 only because removing keys would have forfeited its
    byte-equivalence proof. The solver's own result still carries `opening_cash` (the cash
    curve's basis); this pins the ADAPTER's dict only."""
    p = golden_payload()
    p.update(opening_cash=300_000.0, credit_line=800_000.0)
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    echoed = {"opening_cash", "credit_line"} & out.keys()
    assert not echoed, f"the adapter echoes cash inputs back into its result again: {echoed}"


@pytest.mark.parametrize("key", ["credit_line", "other_debt_service_per_week",
                                 "overhead_pct_of_revenue"])
def test_a_blanked_numeric_field_is_a_status_not_a_traceback(key):
    """parseFloat('') is NaN, JSON.stringify(NaN) is 'null', so a blanked box arrives as a
    PRESENT None — p.get's default never applies — and float(None) used to hand the grower a
    raw TypeError traceback instead of a plan. For genuinely optional/rate fields the adapter
    treats present-None as absent (the documented default). Whatever the solve concludes, it
    must be a status dict, never the blanket-except 'error' path."""
    p = golden_payload()
    p[key] = None
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") != "error", (
        f"a null {key} still crashes the adapter: {out.get('error', '')[:200]}"
    )


@pytest.mark.parametrize("key", ["harvest_storage_cap", "water_storage_capacity",
                                 # /code-review max #4: My Farm Data mode blanks these three, and a
                                 # blank solved "optimal" with the cost gone — $88k on this farm.
                                 "cost_fert_per_lb", "cost_fuel_per_L", "rate_machinery"])
def test_a_blanked_capacity_field_is_refused_not_invented(key):
    """The first version of the present-None fix defaulted these too — and a blanked storage
    box then solved 'optimal' while charging depreciation on the 1e9 no-constraint default
    (profit −$25.9B rendered as a plan), and a blanked tank box invented $5.8k/yr. Capacity
    and price boxes that are always sent must be REFUSED when blanked, loudly, same contract
    as well_weekly_cap_L ('the value would be invented'). Absent stays the documented default
    for toggle-off/server callers — only present-None is refused."""
    p = golden_payload()
    p[key] = None
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") == "error" and key in out.get("error", ""), (
        f"a blanked {key} was not refused — the solve ran on an invented value "
        f"(status={out.get('status')}, profit={out.get('profit')})"
    )


def test_a_blank_box_for_a_water_source_that_is_OFF_does_not_block_the_solve():
    """/code-review max #8. With a source off the solver never reads its size, but the adapter
    refused the blank anyway — so a farm with no well (My Farm Data blanks the benchmark well cap)
    could not get a plan without typing a number into a box that does nothing. One solve covers
    all three: the well and catchment are off and blank, city water carries the farm."""
    p = golden_payload(well_enabled=False, well_weekly_cap_L=None,
                 catchment_enabled=False, catchment_surface_area_m2=None,
                 city_water_enabled=True, city_water_cost_per_L=0.003)
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") == "optimal", out.get("error", "")[:300]


@pytest.mark.parametrize("on,key", [("well_enabled", "well_weekly_cap_L"),
                                    ("catchment_enabled", "catchment_surface_area_m2"),
                                    ("city_water_enabled", "city_water_cost_per_L")])
def test_a_blank_box_for_a_water_source_that_is_ON_is_still_refused(on, key):
    """The other half, so #8's fix cannot be 'stop refusing water blanks altogether'."""
    out = json.loads(run_from_js(json.dumps(golden_payload(**{on: True, key: None}))))
    assert out.get("status") == "error" and key in out.get("error", ""), (
        f"a blank {key} with the source ON was not refused (status={out.get('status')})")


def test_the_payroll_load_reaches_a_hired_hour_through_the_adapter():
    """Kills deleting the hired_wage_load_pct kwarg from the adapter's solve call.

    The /simplify pass moved the load multiplication from the adapter into labor.py; the only
    tests asserting the load called compute_labor_arrays directly, so removing the kwarg
    would silently resurrect the 25% hire under-pricing for every browser caller with the
    whole suite green. This runs the REAL adapter with flex on and pins the published rate."""
    p = golden_payload(labor_flex_enabled=True, hire_enabled=True, max_hire_hrs_per_week=400.0,
                 hire_wage_markup=0.0, hired_wage_per_hr=19.0, payroll_load_pct=0.25)
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    assert out["hire_rate_full_weekly"][0] == pytest.approx(19.0 * 1.25), (
        f"typed $19.00 at 25% payroll load published as "
        f"${out['hire_rate_full_weekly'][0]}/hr — the load fell out of the adapter→labor.py "
        f"hand-off (19.00 = zero-applied, 29.6875 = double-applied)"
    )


def test_a_legacy_single_payroll_load_solves_exactly_like_its_split():
    """L.5: a pre-split caller's payroll_load_pct = 0.25 is FICA 7.65% + 17.35% straight-time,
    so the solve is identical to the split payload — regular pay unchanged to the cent."""
    split = golden_payload()
    legacy = golden_payload()
    legacy.pop("fica_pct"); legacy.pop("straight_time_load_pct")
    legacy["payroll_load_pct"] = split["fica_pct"] + split["straight_time_load_pct"]
    a = json.loads(run_from_js(json.dumps(split)))
    b = json.loads(run_from_js(json.dumps(legacy)))
    assert a["status"] == b["status"] == "optimal"
    assert a["fixed_cost_split"]["wages"] == pytest.approx(b["fixed_cost_split"]["wages"], abs=1e-6)
    assert a["profit"] == pytest.approx(b["profit"], abs=1e-6)


def test_city_water_fixed_fee_reaches_the_solver_through_the_adapter():
    """The standing charge was a solver feature + P&L label + green pytest with NO path in.

    run_from_js never read the key, so the feature was silently $0 on every browser solve while
    tests/cost_splits_client.cjs fed it through a fixture the adapter could never emit. This
    runs the fee through the real adapter and requires the solver to charge it.
    """
    out = json.loads(run_from_js(json.dumps(golden_payload(
        city_water_enabled=True,
        city_water_cost_per_L=0.003,
        city_water_fixed_fee_per_week=400.0,
    ))))
    assert out.get("status") == "optimal", out.get("error", "")[:300]
    assert out["fixed_cost_split"].get("city_water_fixed_fee") == pytest.approx(400.0 * 52), (
        "city_water_fixed_fee_per_week was sent in the payload and did not reach the "
        "fixed-cost split — the adapter dropped it again"
    )


def test_the_adapter_does_not_import_matplotlib():
    """The money path must run without a plotting stack. That is the whole reason E2 split the
    chart into farm_v2/charts.py rather than moving it along with the adapter.

    Checked in a SUBPROCESS on purpose. By the time this test runs, another test — or pytest's
    own plugins — may already have imported matplotlib, so `'matplotlib' in sys.modules` inside
    this process would pass no matter what the adapter does: a guard that cannot fail. A source
    grep is the other easy version and is weaker still, because it cannot see a transitive
    import arriving through farm_v2.solver.
    """
    probe = ("import sys, farm_v2.adapter; "
             "print(any(m == 'matplotlib' or m.startswith('matplotlib.') for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", probe], cwd=REPO,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "False", (
        "importing farm_v2.adapter pulled matplotlib in. The chart lives in farm_v2/charts.py so "
        "a server caller can run the solve and the accounting without shipping a plotting stack."
    )


def test_the_adapter_returns_no_chart(golden_out):
    """E8's saving, made structural by E2.

    E8 bought it with a `skip_charts` payload flag that five sweep paths had to remember to
    stamp; the flag is deleted and the drawing moved out, so a solve now costs no figure unless
    its caller separately asks for one. A sixth sweep path cannot forget a flag that is gone.

    THE MEASUREMENT E8 took, kept here because this is the test that would notice a regression:
    the waterfall was built on every solve, including all 100 Monte Carlo draws, for ONE
    consumer — the main render. ~49 ms median in CPython over 20 warm calls (47-72 ms), on a
    2.9 s solve whose entire Python-level adapter work profiles at ~27 ms; the chart alone cost
    more than twice everything else combined. A second chart, `make_heatmap_chart` (~119 ms),
    ran on every solve and was never put in the result dict at all — deleted. Pyodide is slower
    than CPython, so the browser saves more; that browser figure is NOT measured and is claimed
    nowhere.
    """
    assert "waterfall_png" not in golden_out, (
        "the adapter is emitting a chart again — drawing belongs to farm_v2/charts.py, called "
        "only by the one path that renders an image"
    )


def test_waterfall_png_draws_from_the_result_alone(golden_out):
    """The split is only complete if the RESULT carries everything the chart needed.

    `make_waterfall_chart` took seven positional figures the adapter happened to have in local
    scope (revenue, variable/fixed cost, overhead, interest, fixed selling, and the post-selling
    net profit). Had any one of them not also been a result key, moving the chart out would have
    silently drawn a different picture — a lossy split that the import test above cannot see,
    because a module boundary can be clean and still drop data across it.
    """
    pytest.importorskip("matplotlib")
    from farm_v2.charts import waterfall_png
    png = waterfall_png(json.dumps(golden_out))
    assert base64.b64decode(png)[:8] == b"\x89PNG\r\n\x1a\n", (
        "waterfall_png did not return a base64 PNG built from the result dict alone"
    )


def test_waterfall_png_declines_to_draw_a_farm_that_did_not_solve():
    """No plan, no picture — and no exception either.

    The chart used to be built INSIDE run_from_js, behind the early return for a non-optimal
    status, so an infeasible farm never reached it. Now that drawing is a second call the
    browser makes on its own, that guard has to live here or a failed solve throws a KeyError on
    'revenue' where it used to show an error message.
    """
    pytest.importorskip("matplotlib")
    from farm_v2.charts import waterfall_png
    assert waterfall_png(json.dumps({"status": "infeasible", "profit": None})) == ""


def test_the_browser_draws_on_exactly_one_path():
    """E2/E8, the structural half: the Python contract above cannot prove what the browser does.

    Five call sites (What-If labour, What-If scaling, the diagnostic replay, sensitivity, Monte
    Carlo) were each an independent copy of the same solve+parse block, which is how they came
    to differ. They go through `solveForNumbers`; `runOptimizer` is the one path that renders an
    image and owns its own timeout race. So: exactly TWO sites name `run_from_js`, and exactly
    ONE names `waterfall_png`. A second chart site is a sweep path that started drawing again.

    This is a source-level check, which this repo distrusts on its own — it is here as the cheap
    complement to the executing tests above, not as a substitute. It is limited to COUNTING JS
    call sites, which is the one thing a Python test genuinely cannot get any other way. It
    deliberately does not also assert that the string "skip_charts" is absent: that would pin a
    spelling rather than a mechanism (`draw_chart: false` reintroduces the flag and passes), and
    the invariant it was reaching for — the adapter emits no image, and cannot even import
    matplotlib — is already pinned by two executing tests above.
    """
    src = index_src()
    direct = re.findall(r"runPythonAsync\(\s*[`\"\']run_from_js", src)
    assert len(direct) == 2, (
        f"{len(direct)} call sites invoke run_from_js directly; exactly two may — runOptimizer "
        "(which then draws) and solveForNumbers (which does not). Route any new solve through "
        "solveForNumbers() so it stays chart-free."
    )
    charts = re.findall(r"runPythonAsync\(\s*[`\"\']waterfall_png", src)
    assert len(charts) == 1, (
        f"{len(charts)} call sites draw the waterfall; exactly one may — runOptimizer. Every "
        "other path reads figures off the result and decodes no image."
    )


def test_the_overhead_ledger_reaches_the_page(golden_out):
    """R8: the P&L overhead row is labelled from this list, so it must arrive — short labels only."""
    from farm_v2.solver import OVERHEAD_COVERS
    assert golden_out["overhead_covers"] == [short for short, _ in OVERHEAD_COVERS.values()]
    assert "overhead_excludes" not in golden_out, "nothing in the page reads it — do not send it"


@pytest.mark.parametrize("where", ["wage", "hours_per_week", "count", "total_land"])
def test_nan_is_refused_not_solved(where):
    """/code-review max #8/#9: NaN compares False to every bound, so a wage of NaN solved 'optimal'
    with profit NaN, and NaN hours or land reached HiGHS as a model error. A server caller can send
    the NaN literal (Python's json accepts it), so Step 0 must refuse it."""
    p = golden_payload()
    if where == "total_land":
        p["total_land"] = float("nan")
    else:
        p["employees"][0][where] = float("nan")
    out = json.loads(run_from_js(json.dumps(p)))
    assert out.get("status") == "invalid_input", (out.get("status"), out.get("error", "")[:200])
