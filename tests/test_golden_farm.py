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
    "revenue":          2_163_463,
    "variable_cost":      843_522,
    "fixed_cost":         213_097,
    "overhead_cost":      346_154,
    "interest_cost":          688,
    "profit":             747_002,
    "operating_profit": 1_106_844,
}
# Baseline history — re-pin ONLY with a reason, and record it here.
#   2026-07-29 (B5/B6: seasons became PLANTING windows, and garlic's calendar became real):
#     profit 739,767 -> 747,002 (+7,235, +1.0%), revenue 2,084,368 -> 2,163,463 (+3.8%).
#     Two changes, one commit, because shipping either alone would strand the other.
#
#     (a) A season window used to have to contain the WHOLE crop cycle. Growers enter these as
#     PLANTING windows, so the old reading silently deleted any succession whose harvest fell
#     outside the window — Winter Squash and Melon generated zero successions and never appeared
#     in a plan at all. Windows are now planting windows.
#
#     (b) Garlic's 01-01 to 08-01 window was fabricated: it existed only because the calendar
#     could not express fall planting. The grower's actual practice (zone 6) is saved cloves in
#     late November before the ground freezes, straw-mulched, harvested the following July. Now
#     11-15 to 12-01, overwinters=true, days_to_maturity 196 -> 240.
#
#     WHY 196 WAS NOT SIMPLY WRONG, which took the grower to see: 196 days from Jan 1 lands on
#     July 14. It was measuring garlic's visible TAIL inside a planning year that starts on
#     Jan 1 — real occupancy from an assumed Jan 1 start, not the crop's actual cycle. 240 days
#     from Nov 15 lands on July 11: the same harvest, honestly measured. The old figure never
#     charged garlic for November and December ground.
#
#     WRAPPING IS OPT-IN (`overwinters`), and that is the load-bearing decision. Making it
#     universal was measured first and moved profit +63% to $1,208,966 — because every window in
#     the library was authored under the old meaning, so read as planting windows they let the
#     solver plant Hot Peppers in mid-October and Tomatoes in early October, both frost-tender,
#     harvesting into the following spring. Opt-in keeps every other template behaving exactly as
#     its window was written for. Successions 101 -> 155 (universal wrap would have been 199).
#
#     Note against the standing pattern: this is the first honest fix that did NOT raise net
#     margin. 35.5% -> 34.5%.
#   2026-07-29 (review: the audit had STILL not reached the farm): profit 766,074 -> 739,767.
#     Twelve more override keys deleted. The shadow guard added the day before covered only
#     water_* and fert_* — and the previous commit had deleted every water/fert override, so the
#     list matched NOTHING while three overrides quietly shadowed the fields this same audit had
#     just sourced: Cucumbers.labor_plant 12 (template 3), Hot Peppers.labor_plant 8 (template
#     4.6), Kale.seed_transplant_cost_per_acre 220 (template 1,089). Two of five "fixed" labour
#     outliers and one of four transplanted demo crops had never reached the shipped farm.
#     The guard no longer keeps a hand-written list of what counts as sourced — it reads
#     CROP_PROVENANCE, so its reach grows automatically as citations are added. A list maintained
#     alongside the work it guards will always lag it; that is how this happened twice.
#     Net margin 35.5%.
#   2026-07-29 (transplant costs, purchased-plug basis): profit 834,155 -> 766,074 (-68,081).
#     Ten transplanted crops re-costed as plants/acre (published spacing, 43,560 sq ft/acre) x a
#     published flat price: 72-cell @ $15 for solanaceae and cucurbits, 128-cell @ $12 for
#     brassicas, lettuce and basil. Every one was 2-8x low — Basil 280 -> 2,722 at 29,040
#     plants/acre, Bell Peppers 400 -> 2,017, Kale 300 -> 1,089.
#     BASIS IS EXPLICIT NOW, because the grower's answer was that there is no single right one
#     and the real question is INFRASTRUCTURE: raising your own means midwinter seeding, which
#     means a heated GREENHOUSE, not a high tunnel. This model has no propagation greenhouse, so
#     "raise your own" would read as nearly free — the ambient-barn error again. Purchased plugs
#     is therefore the honest shipped basis, and it is also the grower's own recommendation
#     (skips early-seedling loss and midwinter seeding while keeping control of field timing).
#     ⚠️ Commercial bulk plugs are quoted custom, not published, so these are the published-price
#     UPPER bound. Onions and Strawberries were deliberately NOT touched — they are bare-root
#     (bunched plants, crowns), plug pricing does not apply, and no price source was found.
#     Net margin 34.5%, from 36.5%. Still outside 5-15%, and now most of the remaining gap is in
#     labour season totals, which is the one family still entirely unaudited.
#   2026-07-29 (two more sourced values): profit 834,760 -> 834,155 (-605). Small because
#     neither crop is a large block here, but both were wrong and both are now citable.
#     Bell pepper HARVEST labour 111 -> 200 h/acre (UC Davis Rural Migration labor data). Garlic
#     nitrogen 90 -> 125 lb/acre (Rutgers NJAES FS1289, which also gives 150 P and 150 K) — Penn
#     State's three-tier table had put garlic in the 90 bracket and the crop-specific source is
#     better evidence than the tier.
#   2026-07-29 (garlic seed cost + planting-labour consistency): profit 868,594 -> 834,760
#     (-33,834). Variable cost +64,760; revenue +38,277 as the plan shifted away from garlic.
#     GARLIC SEED 380 -> 2,500/acre. Garlic is planted from CLOVES at 800-1,200 lb/acre, not from
#     seed by the packet. Seed stock runs $10-25/lb premium and $2-4/lb wholesale-grade with
#     20-30% bulk discounts over 1,000 lb (Basaltic Farms / Grey Duck planting guides, 2025), so
#     even the CHEAPEST defensible basis — own saved seed or bulk stock valued at wholesale — is
#     $1,600-4,800/acre. 1,000 lb x $2.50 is the conservative end of that. The shipped $380 was
#     4-25x low on the crop that dominates the plan. Purchased premium seed would be $8,000-30,000.
#     PLANTING LABOUR: five outliers aligned to the library's OWN value for the same operation —
#     Spinach 15 -> 2 (Baby Spinach is 2, identical direct-seeding), Cucumbers 15 -> 3 (Zucchini
#     is 3), Napa 8 -> 2.5, Sweet Corn 10 -> 3, Hot Peppers 10 -> 4.6 (Bell Peppers is 4.6). Napa
#     was the inversion: direct-seeded at 8.0 against TRANSPLANTED Cabbage at 3.5, and
#     transplanting an acre cannot cost less than seeding it. Tagged `estimate` — this is a
#     coherence fix, not a re-benchmark.
#     ⚠️ NOT DONE, and not silently: the season TOTALS for labour, and transplant costs for the
#     other 11 transplanted crops, are still unaudited. Every extension budget that publishes
#     them was unreachable (403s, a corrupted PDF, a certificate failure), and the locked rule is
#     that model-generated values are never entered as data. Known-suspect and left alone: garlic
#     planting at 20 h/ac total against a real 40-100, garlic harvest at 75 h/ac in a single week,
#     and strawberry harvest at 400 h/ac against 600-1,000 for hand-picking 25,000 lb.
#     Net margin 36.5%, from 38.9%. First movement on the margin thesis; still outside 5-15%.
#   2026-07-29 (review of the water/fert/well work): profit 875,354 -> 868,594 (-6,760).
#     The -6,760 is the audit finally REACHING the demo farm. DEMO_OVERRIDES — the map built in
#     Phase A to capture drift — had faithfully captured the demo's PRE-audit water and fertiliser
#     and was shadowing the corrected templates ever since: Cucumbers and Hot Peppers were still
#     charged ~1/8 of their evapotranspiration, Kale and Basil still carried old fertiliser. So
#     three of seven demo crops had the fix and four did not, and every measurement in the two
#     entries below was taken on that hybrid. 19 override keys deleted; they were pure drift with
#     no adjudication behind them, which is what Ruling 0 says burns to empty.
#     Also in this pass: the shipped climate_zone was CALIFORNIA CENTRAL VALLEY (Fresno) while the
#     water rates were benchmarked for humid temperate and the well from a Wisconsin design
#     standard — three regions in one farm. Now northeast/Philadelphia, zone 7a, which is what
#     decision D2 locked and what every one of those numbers already assumed.
#     Water peaks at 60.5% of supply with the coherent pairing (Fresno's near-zero summer rain
#     against humid-temperate ET was the incoherence, not the well). Beets took the small-vegetable
#     Kc where FAO-56 lists it under Roots & Tubers; Melon took the Sweet Melons row where the
#     table has a Cantaloupe one; mesclun had grow_weeks = 0, so 45% of its nitrogen and all of
#     its grow-phase water were never read by the solver at all.
#   2026-07-29 (audit Phase B, well capacity): profit 635,305 -> 875,354 (+240,049). Revenue
#     returns to 2,248,859 — the EXACT figure from before the water fix.
#     That coincidence is the finding: crop water was ~10x too low and the well was ~3.5x too
#     low, so the two errors cancelled and the plan looked reasonable while neither number was.
#     With both corrected the plan is nearly identical, but the model can now reason about water:
#     peak utilisation 80%, nine weeks above 70%, none binding — a live constraint with realistic
#     headroom, where before it was mathematically incapable of binding at all.
#     The well default was 2,500,000 L/wk sourced from a CALIFORNIA WATER BOARD PERMIT — a
#     regulatory cap in a water-scarce state — while this app's reference region is zone 7 humid
#     temperate, where a well is sized to peak demand and irrigation supplements rain. A category
#     error, and its own record already said confidence: low. Re-benchmarked to 8,700,000 L/wk =
#     UW-Madison Extension's design minimum of 8 gpm per irrigated acre x 80 acres x 60 h/week,
#     which is 1.06 in/acre/week and cross-checks against the independent 1-1.5 in/wk peak need.
#     NET EFFECT OF THE WHOLE WATER/FERT/WELL AUDIT: -5,180 against the pre-audit 880,534, which
#     is the honest fertiliser cost and nothing else. Three order-of-magnitude errors, and the
#     money barely moved — because they were offsetting. Net margin 38.9%, still outside the real
#     5-15% band, so the margin thesis remains unresolved and is NOT explained by these inputs.
#   2026-07-28 (audit Phase B, water + fertiliser): profit 880,534 -> 635,305 (-245,229, -27.8%),
#     revenue -468,005. Variable cost also FELL 147,582 — the farm grows less, it is not paying
#     more. Water is essentially all of it; fertiliser adds only ~3,600 on top because the plan
#     has already shrunk by then.
#     Water: rates rebuilt from FAO-56 Table 12 Kc x a 5 mm/day mid-season ETo. They were ~10x
#     below crop ET, so the 65% rainfall offset exceeded every crop's need and net irrigation was
#     identically ZERO — C3 has never bound in this app's history. It binds now.
#     Fertiliser: Penn State's three-tier N recommendation, split 40/45/15 across the phases.
#     Was ~6 lb N/acre/season for tomatoes against a real 130.
#     ⚠️ THE NEXT SUSPECT IS THE WELL, NOT THE CROPS. The demo's well_weekly_cap_L of 2,500,000
#     is 0.30 in/acre/week across 80 acres; irrigated vegetables need 1-1.5. It covers about 24
#     of the 80 acres at peak ET, so the model is now correctly reporting a farm that cannot
#     irrigate itself. That default was never audited BECAUSE crop water was 10x too low and the
#     constraint never bound. It is deliberately NOT adjusted here: tuning an input to restore a
#     profit figure is the exact move this project forbids, and changing it in the same commit
#     would confound the measurement above. Audit it next, with a source.
#     Note the net margin is 35.7% — still far above the 5-15% real range, so these two fixes did
#     NOT resolve the margin thesis; the plan shrank roughly in proportion to the revenue.
#   2026-07-28 (audit Phase B, shelf lives): sourced values entered for all 29 templates from
#     USDA AH-66 via UMaine Ext. Bulletin 4135 and SDSU Extension, by one stated rule (low end of
#     the published range for the regime the crop is actually stored in on a diversified farm,
#     rounded down, counting the harvest week). Provenance per value in CROP_PROVENANCE.
#     Profit 831,046 -> 880,534 (+49,488); revenue 2,114,051 -> 2,248,859. Recovers ~70% of the
#     strict-semantics loss below. Fixed cost +750 is the new 150 m3 ambient barn's depreciation,
#     which had to exist or garlic (now ambient) would be un-plantable.
#     ⚠️ PREDICTION PARTLY FALSIFIED. SPEC_agronomy predicted recovery would concentrate in the 8
#     storables. On THIS farm it came entirely from perishables moving 1 -> 2 weeks (spinach,
#     cucumbers, kale, peppers); garlic — the only storable here — contributed ZERO, because its
#     shelf life stops binding around 6 weeks (measured separately: 8, 16 and 24 give bit-identical
#     plans). The prediction was about the LIBRARY and is untestable on a farm with no storables.
#     Do not read this as confirmation.
#     Residual: still ~20,700 below the pre-B.3 901,236, and that gap is honest — tomatoes and
#     basil are genuinely 1-week crops where the old blank default gave them two.
#   2026-07-28 (re-pinned, B.3): shelf life became STRICT — `shelf_life_weeks` is now the
#     number of weeks a crop can be SOLD IN counting its harvest week, so 1 means "sold the
#     week it is picked" and holds nothing. It previously meant "harvest week plus one more",
#     measured directly (a W14-15 harvest reaching a W16-only buyer at L=1). Every crop
#     therefore loses one selling week: revenue 2,304,930 -> 2,114,051 and profit 901,236 ->
#     831,046 (-70,190, -7.8%).
#     This is the change landing ahead of its data, and the loss is expected to be mostly
#     recovered: 27 of the 29 crop templates carry NO shelf life at all, so they all fell to
#     the strictest possible reading. Honest per-crop values are the agronomy audit's job, and
#     five of the seven demo crops were separately measured as worth +$48,970 together. Do not
#     read this baseline as the model getting worse.
#     Storage also changed in the same pass (C4b now counts everything in the room during the
#     week, not end-of-week stock) but that alone did NOT move the P&L — cold storage does not
#     bind. Reported peak 95.6 -> 181.4 m3, i.e. 66% of the 275 m3 cap.
#     (An earlier draft of this note said 200.7 m3 / 73%. That was measured after the storage
#     change but BEFORE the strict shelf life below, which reduces what is held. Caught in
#     review. Re-measure before quoting a figure from a half-applied change.)
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
#   2026-07-27 (Phase B.1 — harvest storage right-sized, C4 divisor fixed):
#     TWO changes, and only ONE of them moves money.
#       (a) C4's coefficient was missing both the /n_harv_weeks divisor and the sell-through
#           factor that C5, C7 and the client's weekly_harvest_vol reporter all apply, so the
#           enforced storage row was ~5x the physical quantity (peak 825 m3 enforced against a
#           real 139 m3). At the OLD 5,000 m3 cap that row was slack either way, so this fix
#           moves profit by +$5 — under the tolerance. It deliberately lands WITH the resize
#           because the two are destructive apart: at 275 m3 with the old coefficient, revenue
#           collapses 1.82M -> 1.42M against a constraint that is counting the wrong quantity.
#       (b) harvest_storage_cap 5,000 -> 275 m3, and the rate rebased from $463/m3 over 25yr
#           to $500/m3 over 20yr (0.35615 -> 0.48077 $/m3/wk = 500/(20*52)). Why those numbers,
#           and why the old ones had no provenance to preserve, is documented next to the
#           default itself: BENCHMARK_DEFAULTS.harvest_storage_cap in public/index.html.
#     Effect: fixed_cost 298,072 -> 212,347 (-85,725/yr), interest 1,321 -> 821 (less borrowing
#     against a smaller fixed base), profit 494,134 -> 580,359. Revenue, variable cost and
#     overhead are UNCHANGED to the dollar — the plan did not move at all. This was a wrong
#     number on the balance sheet, not a wrong plan.
#     The two payload keys were edited directly rather than re-captured from a browser, because
#     both are deterministic functions of form defaults changed in the same commit
#     (harvest_storage_cap = the input itself; rate = 500/(20*52)).
#   2026-07-27 (Phase B.2 — inventory core, SPEC_v3 §3):
#     The largest single move this baseline has seen, and it is three fixes compounding:
#       B1  C7 deleted. It capped a whole cycle's production at ONE week's demand, pinning
#           Garlic to demand/yield acres. Alone: +$84,857.
#       B2  C5b's per-succession sales windows double-counted overlapping plantings.
#       F2  those windows were anchored at the LAST harvest week, so a crop could not sell
#           during its own earlier harvest weeks.
#     Together B2+F2 were discarding 44,600 lb of Garlic — 45.2% of its sellable output —
#     silently. Under the balance, waste on this plan is now ZERO: every pound grown is sold.
#     revenue 1,815,018 -> 2,304,930, profit 580,359 -> 901,236.
#
#     ⚠️ THE RESULTING NET MARGIN IS 39.1%, WHICH IS NOT BELIEVABLE FOR DIVERSIFIED VEG
#     (real farms net 5-15%). Do not read this re-pin as "the model got better". The
#     constraint arithmetic is verified correct to the pound by tests/test_inventory.py; what
#     it exposes is that the shipped DEMAND defaults are far more generous than the broken
#     constraints ever let the optimizer reach. Garlic wholesale alone is defaulted to
#     30,000 lb/week = 1.56M lb/yr of standing demand. The old C7/C5b defects were masking
#     that, so the demo looked plausible for the wrong reason. Re-calibrating those defaults
#     is a separate, deliberate piece of work and must not be done by quietly re-tightening a
#     constraint until the number looks nice.
#
#     Also new here: `inventory`, `waste`, `waste_by_crop`, `storage_peak_m3` and
#     `capacity_series.storage`. The adapter now RENDERS the storage series the constraint
#     used instead of recomputing harvest inflow client-side (SPEC_v3 §9), which is why the
#     reported storage utilisation changes meaning: it is held stock now, not weekly inflow.

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
    # A backtick ENDS the template literal in the browser, so the page breaks while this
    # extractor — which slices to the first "`;" — happily keeps returning valid Python and
    # every test here stays green. That happened once: a backtick inside a comment in the
    # result dict. Only the node harnesses caught it. Fail here too.
    assert "`" not in code, (
        "PYTHON_CODE contains a backtick, which closes the JS template literal early and "
        "breaks the page. Python-side tests cannot see this; use quotes in comments."
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
def golden_payload():
    return json.loads(PAYLOAD.read_text())


class TestNoPhantomFarm:
    """A payload that omits a farm's essentials is refused, not quietly invented.

    All three fallbacks were unreachable from the app (every caller sends the real thing) and
    all three were live on the planned server path, where a confident plan for a farm nobody
    described is the worst failure this tool can have. The labor one was the worst: it staffed
    28 people, which moves the capacity constraint AND the payroll line.
    """

    @pytest.mark.parametrize("drop,expect", [("crops", "no crops"), ("channels", "no channels")])
    def test_missing_collection_is_refused(self, run_from_js, golden_payload, drop, expect):
        p = dict(golden_payload)
        p.pop(drop, None)
        out = json.loads(run_from_js(json.dumps(p)))
        assert out["status"] == "error", (
            f"a payload with no {drop} returned {out['status']!r} — it used to solve a stale "
            f"built-in default silently"
        )
        assert expect in out.get("error", "").lower(), out.get("error")

    def test_missing_labor_is_refused(self, run_from_js, golden_payload):
        # The payload carries one `employees` list; the adapter splits it into year-round and
        # seasonal. Emptying that list is what an unstaffed farm looks like on the wire.
        p = dict(golden_payload)
        p["employees"] = []
        out = json.loads(run_from_js(json.dumps(p)))
        assert out["status"] == "error", "an unstaffed farm must not be silently given a crew"
        assert "labor" in out.get("error", "").lower(), out.get("error")


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


class TestValidationRunsOnTheSolverPath:
    """audit 1.4 / S1 + S8 — validate.py used to be imported only by pytest.

    A broken crop produced 0 acres and no explanation. It is wired into the ADAPTER rather
    than into validateParams() in the browser, because only the Optimize button goes through
    the JS guard: the What-If sweep, the sensitivity runs and Monte Carlo all call the solver
    directly and were unguarded. Validating where every path converges covers all of them.
    """

    def test_a_broken_crop_is_refused_with_a_reason(self, run_from_js, golden_payload):
        import copy, json as _json
        bad = copy.deepcopy(golden_payload)
        bad["crops"][0]["yield_per_acre"] = 0          # validate.py rejects non-positive yield
        out = _json.loads(run_from_js(_json.dumps(bad)))
        assert out["status"] == "invalid_input", (
            f"a zero-yield crop solved anyway with status {out['status']!r} — it would have "
            f"produced 0 acres and no explanation"
        )
        assert out.get("errors"), "refused the solve without saying why"
        assert any("yield" in e.lower() for e in out["errors"]), out["errors"]
        assert out["profit"] is None

    def test_a_valid_payload_still_solves_and_carries_warnings(self, run_from_js, golden_payload):
        import json as _json
        out = _json.loads(run_from_js(_json.dumps(golden_payload)))
        assert out["status"] in ("optimal", "time_limit_feasible"), out["status"]
        assert "warnings" in out, (
            "the solve path must carry validate.py's warnings back — they are the only "
            "pre-flight signal the grower gets"
        )
        assert isinstance(out["warnings"], list)

    def test_the_guard_never_takes_the_solve_down_with_it(self, run_from_js, golden_payload):
        """A crashing guard must degrade to no-guard, not to no-plan."""
        import copy, json as _json
        odd = copy.deepcopy(golden_payload)
        odd["crops"][0]["seasons"] = [{"start": "03-01", "end": "06-15"}]
        out = _json.loads(run_from_js(_json.dumps(odd)))
        assert out["status"] != "error", out.get("errors") or out.get("message")
