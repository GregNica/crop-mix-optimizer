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

# Module-level: every class here consumes the `result`/`run_from_js` fixtures, which read the
# payload. A class-level skip left the other four to ERROR instead of skip when it is absent.
pytestmark = pytest.mark.skipif(not PAYLOAD.exists(), reason="golden payload missing")

# The P&L of the shipped default farm. Captured 2026-07-27 from the app's own default payload.
GOLDEN = {
    "revenue":          1_815_018,
    "variable_cost":      718_088,
    "fixed_cost":         298_072,
    "overhead_cost":      290_403,
    "interest_cost":        1_321,
    "profit":             494_134,
    "operating_profit":   798_858,
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
#   2026-07-27 (re-captured): the previous fixture had been captured AFTER the JS margin hurdle
#     mutated the payload — Spinach/Wholesale went in with weekly_demand_lbs = 0, so the golden
#     farm was pinning a post-hurdle plan rather than the form's own defaults. With the hurdle
#     moved into Python and defaulted OFF (SPEC_v3 §8), the payload is now the untouched
#     defaults: that channel's 25,000 lb/wk cap is back, revenue 1,793,298 -> 1,815,018 and
#     profit 487,549 -> 494,134. Lesson worth keeping: capture the fixture from the FORM, not
#     from a payload something upstream has already rewritten.

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


class TestMarginKernel:
    """SPEC_v3 §8 — one margin kernel, computed from the objective's own arrays.

    Three JS copies used to recompute this with rates the model never charges ($20/hr labour,
    $0.002/L water), so the app ranked and signed crop-channels differently from its own
    optimizer — and used those wrong numbers to DROP channels before the solve. These pin the
    solver-side numbers the UI is now required to render rather than recompute.
    """

    def test_margins_are_returned_for_every_priced_crop_channel(self, result):
        cm = result.get("channel_margins")
        assert cm, "solver must return channel_margins for the UI to render"
        n = sum(len(v) for v in cm.values())
        assert n >= 14, f"expected a margin for every priced crop-channel, got {n}"
        for crop, chans in cm.items():
            for ch, m in chans.items():
                assert m["gross_price_per_lb"] > 0
                # the reported % must be the reported $/lb over gross price — not a second
                # computation that could drift from it
                assert m["margin_pct"] == pytest.approx(
                    m["margin_per_lb"] / m["gross_price_per_lb"] * 100.0, rel=1e-9), \
                    f"{crop}/{ch}: margin_pct disagrees with margin_per_lb"

    def test_wholesale_loss_makers_are_reported_negative(self, result):
        """The exec summary used to show Cucumbers/Wholesale at +$13,541/acre/yr. On the
        solver's own basis it is negative, and the kernel must say so."""
        cm = result["channel_margins"]
        assert cm["Cucumbers"]["Wholesale"]["margin_pct"] < 0
        assert cm["Spinach"]["Wholesale"]["margin_pct"] < 0
        assert cm["Garlic"]["Farmers Market"]["margin_pct"] > 40, "strong channels must stay clearly positive"

    def test_hurdle_is_off_by_default_and_excludes_nothing(self, result):
        assert result.get("excluded_channels") == [], (
            "the margin hurdle must default OFF: with honest margins any positive floor also "
            "excludes contribution-positive channels, which costs real profit (~$61k here)."
        )

    def test_hurdle_excludes_only_below_floor_when_enabled(self, run_from_js):
        params = json.loads(PAYLOAD.read_text())
        params["min_viable_margin_pct"] = 8.0
        r = json.loads(run_from_js(json.dumps(params)))
        excluded = {(e["crop"], e["channel"]) for e in r["excluded_channels"]}
        assert excluded, "an 8% floor must exclude the sub-8% channels"
        for crop, ch in excluded:
            assert r["channel_margins"][crop][ch]["margin_pct"] < 8.0
        # and it must cost profit — the measured price of applying a floor calibrated against
        # the OLD inflated margins to honest ones
        assert r["profit"] < GOLDEN["profit"]


class TestCropContribution:
    """Per-crop dollars, from the plan that was actually solved.

    Every other per-crop figure the app reports is a RATE (per lb, per acre, per acre-day).
    None of them answer "how much of my profit does garlic account for". These do, and because
    they come from the solved plan — pounds really sold, acres really planted — they involve no
    cycle-count or repeat assumption.
    """

    def test_contributions_reconcile_to_net_profit(self, result):
        """The strongest money assertion available: crop contributions minus the plan-level
        costs must equal the reported headline, to the cent. If a cost line is ever
        double-counted, dropped, or allocated to the wrong bucket, this is what catches it."""
        r = result
        total = sum(d["contribution"] for d in r["crop_contribution"].values())
        rebuilt = total - r["fixed_cost"] - r["fixed_selling_cost"] - r["interest_cost"]
        assert rebuilt == pytest.approx(r["profit"], abs=1.0), (
            f"per-crop contributions do not rebuild net profit: {rebuilt:,.2f} vs {r['profit']:,.2f}. "
            "A cost line is missing, doubled, or in the wrong bucket."
        )

    def test_every_planted_crop_is_accounted_for(self, result):
        planted = {s["crop"] for s in result["succession_schedule"] if s.get("acres", 0) > 0.01}
        reported = set(result["crop_contribution"])
        assert planted <= reported, f"planted but unaccounted: {sorted(planted - reported)}"

    def test_contribution_internals_are_consistent(self, result):
        for crop, d in result["crop_contribution"].items():
            assert d["contribution"] == pytest.approx(d["net_revenue"] - d["growing_cost"], abs=0.01), crop
            by_ch = sum(c["net_revenue"] for c in d["by_channel"].values())
            assert by_ch == pytest.approx(d["net_revenue"], abs=0.01), f"{crop}: channel split != total"
            lbs = sum(c["lbs_sold"] for c in d["by_channel"].values())
            assert lbs == pytest.approx(d["lbs_sold"], abs=0.01), f"{crop}: channel lbs != total"


class TestPerAcreDayMargin:
    """$/acre/day replaces a $/acre/YEAR figure the UI computed as 365/days_to_maturity — an
    assumption that a crop could be regrown all year (Basil got 10.43 cycles where its season
    allows 4). Because each crop's error differed, it REORDERED the ranking rather than just
    inflating it: the summary crowned Basil while the optimizer ranked it 6th of 7 by land."""

    def test_occupancy_is_the_full_succession_not_days_to_maturity(self, result):
        """Land is occupied from planting through the LAST harvest week. Charging only to
        maturity would overstate the earning rate of anything harvested over several weeks."""
        params = json.loads(PAYLOAD.read_text())
        dtm = {c["name"]: float(c.get("days_to_maturity", 0)) for c in params["crops"]}
        for crop, chans in result["channel_margins"].items():
            days = next(iter(chans.values()))["occupancy_days"]
            assert days > 0, crop
            assert days >= dtm[crop] * 0.8, (
                f"{crop}: occupancy {days}d is far below days-to-maturity {dtm[crop]}d")

    def test_rate_and_total_can_disagree_and_both_are_real(self, result):
        """Guards the insight the single fabricated metric was hiding: the best crop per
        acre-day need not be the biggest contributor. Basil earns the most per day of ground
        but occupies it briefly; Spinach contributes the most in total."""
        cm, cc = result["channel_margins"], result["crop_contribution"]
        best_rate = max(((c, m["margin_per_acre_day"])
                         for c, chans in cm.items() for m in chans.values()), key=lambda t: t[1])[0]
        biggest = max(cc.items(), key=lambda kv: kv[1]["contribution"])[0]
        assert best_rate != biggest, (
            "rate leader and contribution leader coincide — re-check the fixture; the point of "
            "reporting both is that they answer different questions")

    def test_per_acre_day_agrees_in_sign_with_per_lb(self, result):
        for crop, chans in result["channel_margins"].items():
            for ch, m in chans.items():
                if abs(m["margin_per_lb"]) > 1e-9:
                    assert (m["margin_per_acre_day"] >= 0) == (m["margin_per_lb"] >= 0), f"{crop}/{ch}"


class TestOneKernelNoDrift:
    """The contribution table used to recompute margins in JS and disagreed with the exec
    summary on the same screen — it showed Spinach/Wholesale at 0% and +$3/ac/wk while the
    solver had it at -20% and -$128/ac/wk. The divergence was structural, not just rates: the
    JS omitted overhead, used round(dtm/7) for occupancy, and re-multiplied hours by a scalar
    wage where the objective charges each week's own blend and a rainfall-adjusted water need.

    Both surfaces now render channel_margins. These pin the relationships they render, so a
    future surface can be checked against them instead of growing a fourth kernel.
    """

    def test_cycle_margin_is_the_day_rate_times_occupancy(self, result):
        for crop, chans in result["channel_margins"].items():
            for ch, m in chans.items():
                assert m["margin_per_acre_cycle"] == pytest.approx(
                    m["margin_per_acre_day"] * m["occupancy_days"], rel=1e-9), f"{crop}/{ch}"

    def test_cost_split_sums_to_the_total_it_reports(self, result):
        """The row tooltip renders the split and the cell renders the total; if they disagree
        the reader is being shown a breakdown that does not add up."""
        for crop, chans in result["channel_margins"].items():
            for ch, m in chans.items():
                c = m["cost_per_acre"]
                parts = (c["labor"] + c["water"] + c["fert"] + c["fuel"] + c["seed"]
                         + c["packaging"] + c["overhead"])
                assert parts == pytest.approx(c["total"], rel=1e-9), f"{crop}/{ch} split != total"

    def test_margin_reconciles_with_revenue_minus_cost(self, result):
        """Revenue - Cost must EQUAL the margin, exactly. The table shows Rev/acre, VC/acre and
        CM/acre side by side, so if they don't reconcile the reader is looking at three numbers
        that cannot all be true. This failed by exactly the overhead share until overhead was
        added to the cost split — the objective internalises it, so it is a real cost of the
        row and belongs in the row's cost column."""
        for crop, chans in result["channel_margins"].items():
            for ch, m in chans.items():
                implied = m["revenue_per_acre"] - m["cost_per_acre"]["total"]
                assert implied == pytest.approx(m["margin_per_acre_cycle"], abs=0.01), (
                    f"{crop}/{ch}: revenue {m['revenue_per_acre']:.2f} - cost "
                    f"{m['cost_per_acre']['total']:.2f} != margin {m['margin_per_acre_cycle']:.2f}")

    def test_loss_making_channels_stay_negative_in_every_derived_figure(self, result):
        """The bug's signature was a loss-maker rendering as break-even-or-better. If any
        derived figure can disagree in SIGN with the per-lb margin, that can happen again."""
        for crop, chans in result["channel_margins"].items():
            for ch, m in chans.items():
                if m["margin_per_lb"] < 0:
                    assert m["margin_pct"] < 0, f"{crop}/{ch}"
                    assert m["margin_per_acre_day"] < 0, f"{crop}/{ch}"
                    assert m["margin_per_acre_cycle"] < 0, f"{crop}/{ch}"
