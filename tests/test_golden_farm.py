"""
GOLDEN FARM — the money regression.

Fixed inputs to a fixed P&L, asserted to the dollar. If a change moves the farmer's numbers,
this fails and someone has to say why. That is the whole point: the rest of the suite pins
STRUCTURE (test_accounting) and the solver in isolation (test_solver), but nothing pinned the
number a user actually sees, so every money defect found so far was caught by review or by
hand rather than by CI.

Two properties make this different from test_regression.py:

  1. It runs the app's REAL default payload, captured from the browser
     (tests/golden/default_farm_payload.json) — the ~80-acre demo farm, not a synthetic
     fixture. What it pins is what the landing screen claims.

  2. It runs through run_from_js, the Python adapter embedded in public/index.html, not
     solve_farm_v2 directly. The adapter is money-path code in its own right: it nets
     variable selling cost into price, derives cash_constraint_enabled, and deducts channel
     fixed selling from the reported profit. Calling the solver directly would skip all of
     that and pin a number no user ever sees.

WHEN THIS FAILS: do not just re-pin it. Work out which line moved and whether the new number
is more honest than the old one. Several known-open defects (water priced at zero, labor
double-counted, the margin hurdle running on phantom rates) will each move these figures when
fixed — that is expected, and the new values should be recorded here with a note saying why.
"""
import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INDEX = REPO / "public" / "index.html"
PAYLOAD = REPO / "tests" / "golden" / "default_farm_payload.json"

pytest.importorskip("numpy")
pytest.importorskip("scipy")

# The P&L of the shipped default farm. Captured 2026-07-27 from the app's own default payload.
GOLDEN = {
    "revenue":          1_793_298,
    "variable_cost":      706_305,
    "fixed_cost":         298_072,
    "overhead_cost":      286_928,
    "interest_cost":        1_444,
    "profit":             487_549,
    "operating_profit":   788_920,
}
# Baseline history — re-pin ONLY with a reason, and record it here.
#   2026-07-27 (first pin): fixed 341,812 / profit 443,458.
#   2026-07-27 (re-pinned): the water-tank capital benchmark was $3.74/L, which made the
#     stock 270,000 L tank a $1,009,800 asset and 15% of ALL fixed cost on an 80-acre farm.
#     Re-benchmarked to $0.50/L installed: a 10,000-gal poly tank lists around $13,940
#     ($0.37/L) before freight, and per-litre cost falls with capacity. Fixed cost
#     341,812 -> 298,072 (-43,740) and profit 443,458 -> 487,549. Revenue, variable cost and
#     overhead are UNCHANGED — the plan did not move, only the cost of a tank did.
#     (Retiring operating_weeks as a cost multiplier in the same commit changed nothing here,
#     because the shipped default was already 52.)

# $50 is the solver noise floor, not a comfort margin. The MILP is solved by HiGHS via scipy,
# and different builds (notably Pyodide's vs a local venv) settle on solutions that differ by
# a couple of dollars on a $443k plan — the browser reports $443,460 where this path reports
# $443,458. Pinning to the literal dollar would make the test fail on a scipy upgrade and
# teach everyone to re-pin reflexively, which is exactly the habit that makes a money guard
# worthless. $50 is 0.011% of profit, while every real defect found in this codebase moved
# $10k-$171k, so nothing that matters can hide under it.
DOLLAR = 50.0


def _extract_python_code() -> str:
    """Pull the PYTHON_CODE template literal out of index.html.

    It is a JS backtick string, so `${...}` interpolations would be a problem — there are
    none today, and this asserts that stays true rather than silently mangling the source.
    """
    src = INDEX.read_text()
    start = src.index("const PYTHON_CODE = `") + len("const PYTHON_CODE = `")
    end = src.index("`;", start)
    code = src[start:end]
    assert "${" not in code, (
        "PYTHON_CODE now contains a JS interpolation; this extractor would inline it "
        "verbatim and the golden test would be running something other than the app's code."
    )
    # matplotlib is only needed for the chart PNGs, which this test does not exercise.
    return code


@pytest.fixture(scope="module")
def run_from_js():
    """The app's real adapter, with the chart calls stubbed out (no matplotlib needed)."""
    code = _extract_python_code()
    ns: dict = {}
    # Drop the matplotlib import/use lines and stub the two chart builders.
    code = re.sub(r"^import matplotlib.*$", "", code, flags=re.M)
    code = re.sub(r"^matplotlib\.use\(.*$", "", code, flags=re.M)
    code = re.sub(r"^from matplotlib.*$", "", code, flags=re.M)
    exec(compile(code, "index.html:PYTHON_CODE", "exec"), ns)   # noqa: S102
    ns["make_waterfall_chart"] = lambda *a, **k: ""
    ns["make_heatmap_chart"] = lambda *a, **k: ""
    ns["_fig_to_b64"] = lambda *a, **k: ""
    return ns["run_from_js"]


@pytest.fixture(scope="module")
def result(run_from_js):
    params = json.loads(PAYLOAD.read_text())
    out = json.loads(run_from_js(json.dumps(params)))
    assert out.get("status") == "optimal", f"golden farm did not solve: {out.get('status')} {out.get('error', '')}"
    return out


@pytest.mark.skipif(not PAYLOAD.exists(), reason="golden payload missing")
class TestGoldenFarm:
    @pytest.mark.parametrize("line", sorted(GOLDEN))
    def test_pnl_line_to_the_dollar(self, result, line):
        got, want = result[line], GOLDEN[line]
        assert got == pytest.approx(want, abs=DOLLAR), (
            f"{line} moved: ${got:,.0f} vs the pinned ${want:,.0f} "
            f"(delta ${got - want:+,.0f}). Money changed — identify the cause and, if the new "
            f"number is the more honest one, re-pin it here with a note."
        )

    def test_identities_hold_on_the_golden_farm(self, result):
        """The pinned numbers must also be internally consistent, so a re-pin can't paper
        over a broken P&L by adjusting one line."""
        r = result
        enumerated = (r["fixed_cost"] + r["variable_cost"] + r.get("city_water_cost", 0.0)
                      + r.get("overtime_cost", 0.0) + r.get("hire_cost", 0.0))
        assert r["operating_profit"] == pytest.approx(r["revenue"] - enumerated, abs=DOLLAR)
        assert r["overhead_cost"] == pytest.approx(
            r["revenue"] * json.loads(PAYLOAD.read_text())["overhead_pct_of_revenue"], rel=1e-6)

    def test_plan_is_nonempty_and_within_land(self, result):
        """A degenerate all-zero plan would satisfy the dollar assertions if they were ever
        re-pinned to zero; make that impossible to do quietly."""
        acres = sum(s.get("acres", 0.0) for s in result.get("succession_schedule", []))
        assert acres > 0, "golden farm planted nothing"
        assert result["revenue"] > 0 and result["profit"] > 0
