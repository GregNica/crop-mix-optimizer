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

from tests.helpers import (
    SATURATION_KEYS,
    annual_equivalent_cap,
    saturation_entries,
)

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
    "revenue":          1_621_122,
    "variable_cost":      584_030,
    "fixed_cost":         213_097,
    "overhead_cost":      259_379,
    "interest_cost":        1_091,
    "profit":             550_524,
    "operating_profit":   823_994,
}
# Baseline history — re-pin ONLY with a reason, and record it here.
#   2026-07-30 (W4, NOT a re-pin — recorded because the observed number now differs from the pin):
#     profit reads 550,529.36 against the 550,524 pinned above, and interest 1,085.48 against
#     1,090.78. Everything else is identical TO THE CENT: revenue, variable_cost, fixed_cost,
#     operating_profit and peak_borrowing all unchanged, and 38 successions planted before and
#     after. The difference is a TIE being broken differently. Spinach's plantings moved from
#     W15/W17/W18/W20/W22 to W15/W17/W19/W21/W22 — same total acreage, same profit — because W4
#     charges each variable cost once into one array and sums it, so the float addition ORDER of
#     the cash-flow coefficients changed in the last bits and HiGHS picked a different equally
#     optimal vertex. A different planting week means a different cash curve, hence average
#     borrowing, hence interest.
#     DELIBERATELY NOT RE-PINNED: 550,524 is no more or less correct than 550,529, and re-pinning
#     to today's tie would suggest the number moved when the plan's economics did not. This is the
#     case the $50 tolerance was reasoned for. If a future change moves profit and leaves
#     operating_profit identical, suspect degeneracy before suspecting a defect.
#   2026-07-29 (days_to_maturity is PLANT TO FIRST HARVEST, not total field occupancy):
#     revenue 2,163,463 -> 1,621,122 (-25%), profit 747,002 -> 550,524 (-26%).
#
#     The grower corrected the definition: DTM is how long before you can harvest, which is
#     what every seed catalogue and extension budget publishes. The model read it as
#     plant-to-bed-clear and derived grow = total - plant - harvest, so harvest_weeks ate the
#     growing season — basil had ONE week of growing (35 days, 1 plant, 3 harvest) and tomatoes
#     three. The crop was in the ground for less time than it takes to grow it.
#
#     Occupancy is now maturity PLUS the harvest window. Field weeks: Spinach 6->8,
#     Cucumbers 10->13, Kale 9->13, Tomatoes 13->21, Hot Peppers 21->31, Basil 5->8,
#     Garlic 35->36. Land is genuinely scarcer, which is why everything falls.
#
#     This is a correction of a real under-charge, not a loss: every crop with a harvest window
#     was paying for less land, labour, water and fertiliser than it actually uses.
#
#     Net margin 34.5% -> 34.0% — essentially unmoved, so the standing margin problem is NOT
#     explained by this and remains open.
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

    def test_rate_and_total_are_independent_measures(self, result):
        """Guards the insight the single fabricated metric was hiding: the best crop per
        acre-day need not be the biggest contributor.

        This used to assert the two leaders are DIFFERENT crops. That is a property of the
        fixture, not of the model — once field occupancy was corrected (DTM is plant-to-first-
        harvest) Garlic led both, and the test failed while nothing was wrong. Pinning it would
        have pinned an accident. What must hold is that both measures exist, are well-formed,
        and are computed from different quantities: a RATE per day of ground occupied, and a
        TOTAL over the season.
        """
        cm, cc = result["channel_margins"], result["crop_contribution"]
        rates = [(c, m["margin_per_acre_day"], m["occupancy_days"])
                 for c, chans in cm.items() for m in chans.values()]
        assert rates, "no per-acre-day rates were reported"
        for c, rate, days in rates:
            assert days > 0, f"{c}: occupancy_days is {days}, so the rate has no denominator"
        planted = {k: v for k, v in cc.items() if (v.get("acres_planted") or 0) > 0}
        assert planted, "no crop was planted — this test would be vacuous"
        for k, v in planted.items():
            assert "contribution" in v, f"{k}: no seasonal contribution reported"
        # The two answer different questions, so a crop leading one must not be ASSUMED to lead
        # the other. Assert only that both rankings are computable and non-degenerate.
        assert len({r for _, r, _ in rates}) > 1, (
            "every crop-channel reports the same per-acre-day rate — the metric is not "
            "discriminating between crops at all"
        )

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
                parts = (c["labor"] + c["water"] + c["fertilizer"] + c["fuel"] + c["seed"]
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

    def test_a_valid_payload_still_solves_and_carries_warnings(self, run_from_js, golden_payload,
                                                              result):
        # Reuses the module-scoped `result` fixture rather than re-solving the golden farm: the
        # assertion is about the warnings CHANNEL existing, not about the plan, and a fresh
        # 7-crop solve cost ~3.7s to prove a key is present.
        out = result
        assert out["status"] in ("optimal", "time_limit_feasible"), out["status"]
        assert "warnings" in out, (
            "the solve path must carry validate.py's warnings back — they are the only "
            "pre-flight signal the grower gets"
        )
        assert isinstance(out["warnings"], list)

    def test_the_guard_never_takes_the_solve_down_with_it(self, run_from_js, golden_payload):
        """A crashing guard must degrade to no-guard, not to no-plan.

        Trimmed to ONE crop: this asserts the guard does not abort the run, which needs a solve
        but not the whole 7-crop farm. The full-farm version cost ~2.7s to prove `status !=
        error`.
        """
        import copy, json as _json
        odd = copy.deepcopy(golden_payload)
        odd["crops"] = odd["crops"][:1]
        odd["crops"][0]["seasons"] = [{"start": "03-01", "end": "06-15"}]
        out = _json.loads(run_from_js(_json.dumps(odd)))
        assert out["status"] != "error", out.get("errors") or out.get("message")


# The per-channel sales lines as the app prints them (W1 / D4). Captured 2026-07-29, the day
# the client stopped reconstructing them from demand x price and started reading the solver's
# own `v`. These are the numbers under the Revenue line in the exported P&L.
GOLDEN_CHANNEL_REVENUE = {
    "Farmers Market": 1_278_660,
    "Wholesale":        342_462,
}


class TestChannelSalesReachTheClient(object):
    """W1 / D4 — the sales schedule crosses the adapter intact and adds up.

    tests/test_channel_sales.py pins the same identities inside the solver. This class exists
    because the adapter is a second place they can break: it re-serializes the whole structure
    into JSON for Pyodide, rounding pounds for size. Nothing tested that forwarding, and the
    golden farm is the only fixture here with more than one channel — so it is the only place
    "the channel lines sum to the headline revenue" is a non-trivial statement.
    """

    def test_every_channel_is_present(self, result):
        cs = result["channel_sales"]
        assert set(cs) == set(GOLDEN_CHANNEL_REVENUE), (
            f"expected {sorted(GOLDEN_CHANNEL_REVENUE)}, got {sorted(cs)}"
        )

    @pytest.mark.parametrize("ch", sorted(GOLDEN_CHANNEL_REVENUE))
    def test_channel_revenue_line(self, result, ch):
        got, want = result["channel_sales"][ch]["revenue"], GOLDEN_CHANNEL_REVENUE[ch]
        assert abs(got - want) < 50, f"{ch} revenue {got:,.2f}, expected ~{want:,}"

    def test_the_lines_sum_to_the_headline_revenue(self, result):
        """The property the reconstruction could never have. Tolerance is a cent, not the $50
        used for the P&L lines above: this is one arithmetic identity over one set of numbers,
        not a re-solve, so there is no solver drift for it to absorb."""
        total = sum(d["revenue"] for d in result["channel_sales"].values())
        assert abs(total - result["revenue"]) < 0.01, (
            f"channel lines sum to {total:,.2f} but the headline revenue on the same page is "
            f"{result['revenue']:,.2f}"
        )

    def test_weekly_series_survives_serialization(self, result):
        """The adapter rounds pounds to 2dp for payload size. That must not break the weekly
        identity the pies and the CSV both depend on — 52 roundings of <=0.005 lb each."""
        for ch, data in result["channel_sales"].items():
            for crop, cp in data["by_crop"].items():
                assert len(cp["weekly_lbs"]) == 52, f"{ch}/{crop}"
                assert abs(sum(cp["weekly_lbs"]) - cp["lbs_sold"]) < 1.0, f"{ch}/{crop}"

    def test_sales_are_below_gross_harvest(self, result, golden_payload):
        """Sell-through — the single largest error in the reconstruction this replaced.

        That code split GROSS harvest across channels, so it reported pounds the farm never
        had to sell. Measured on this farm the day it was removed: 809,200 lb claimed against
        686,415 lb actually sold, a **17.9% overstatement**, on the same screen as a revenue
        figure computed from the honest number.

        `grown` is derived from the planted acreage and the crops' yields — NOT from the sold
        figure. Dividing sales back out by sell-through would make this test true by algebra
        and prove nothing; the first version of it did exactly that.
        """
        st = golden_payload.get("sell_through_fraction", 1.0)
        assert st < 1.0, "the golden farm has no shrink — this test would prove nothing"
        ypa = {c["name"]: c["yield_per_acre"] for c in golden_payload["crops"]}
        grown = sum(s["acres"] * ypa[s["crop"]] for s in result["succession_schedule"])
        sold = sum(d["lbs_sold"] for d in result["channel_sales"].values())
        assert grown > 0
        assert sold <= grown * st + 1.0, (
            f"sold {sold:,.0f} lb but only {grown * st:,.0f} lb of the {grown:,.0f} lb grown "
            f"is sellable at sell-through {st}"
        )
        assert sold < grown * 0.95, (
            f"sold {sold:,.0f} lb against {grown:,.0f} lb grown — that is too close to gross "
            f"for shrink to be modelled at all, which is the defect this guards"
        )


# The three crop-channel rows on this farm that sell NOTHING, with what the old gross-harvest
# formula printed for each. Measured 2026-07-30, before W6 was fixed.
GOLDEN_PHANTOM_DEMAND = {
    ("Wholesale", "Basil"):       0.29,
    ("Wholesale", "Spinach"):     0.16,
    ("Wholesale", "Hot Peppers"): 0.04,
}


class TestDemandSaturationReachesTheClient(object):
    """W6 — the saturation panel's numbers cross the adapter, and say what is enforced.

    tests/test_demand_saturation.py pins the identities inside the solver on purpose-built
    fixtures. This class exists because the golden farm is the SHIPPED farm: it is the only
    place the measured defect can be shown against the numbers a grower actually sees, and the
    adapter is a second place forwarding can break.
    """

    def test_it_survives_the_adapter(self, result):
        ds = result.get("demand_saturation")
        assert ds, "demand_saturation did not cross the adapter — the panel has nothing to read"
        for ch, cp, e in saturation_entries(result):
            assert set(e) == SATURATION_KEYS, f"{ch}/{cp}: {sorted(set(e) ^ SATURATION_KEYS)}"

    def test_the_at_cap_threshold_crosses_too(self, result):
        """The number `weeks_at_cap` was measured at has to travel with it.

        The CSV heads a column with it. This was missed on the first pass — the field was added
        to the solver's return and not to the adapter's, so it was `undefined` in the browser
        while the jsdom fixture supplied it and every test stayed green. Caught by reading the
        real value out of a real page, which is why that step is not optional.
        """
        got = result.get("demand_at_cap_threshold")
        assert got is not None, "demand_at_cap_threshold did not cross the adapter"
        assert 0.0 < got <= 1.0, got
        # And it must be the threshold the data was actually built with.
        for ch, cp, e in saturation_entries(result):
            if e["basis"] != "weekly" or e["peak_week_frac"] is None:
                continue
            if e["weeks_at_cap"]:
                assert e["peak_week_frac"] >= got, (
                    f"{ch}/{cp} flags {len(e['weeks_at_cap'])} weeks at cap but its peak week is "
                    f"only {e['peak_week_frac']:.2f}, below the published threshold {got}"
                )

    def test_it_agrees_with_the_channel_pies(self, result):
        """One `v`, two reports. A pie showing nothing beside a row claiming saturation is the
        contradiction W6 names, and it is only impossible if these two cannot disagree."""
        cs = result["channel_sales"]
        for ch, cp, e in saturation_entries(result):
            sold = cs.get(ch, {}).get("by_crop", {}).get(cp, {}).get("lbs_sold", 0.0)
            assert abs(sold - e["sold_lbs"]) < 0.5, (
                f"{ch}/{cp}: the panel says {e['sold_lbs']:,.1f} lb, the pies say {sold:,.1f}"
            )

    @pytest.mark.parametrize("ch,cp", sorted(GOLDEN_PHANTOM_DEMAND))
    def test_a_channel_with_no_sales_reads_zero(self, result, ch, cp):
        """The defect, on the shipped farm. Each of these sells zero pounds into the channel and
        printed a saturation anyway, because the numerator was the crop's harvest across ALL
        channels."""
        e = result["demand_saturation"][ch][cp]
        was = GOLDEN_PHANTOM_DEMAND[(ch, cp)]
        assert e["sold_lbs"] == 0.0, f"{ch}/{cp} now sells {e['sold_lbs']:,.0f} lb — re-measure"
        assert e["fill"] == 0.0 and e["binding"] == 0.0, (
            f"{ch}/{cp} sells nothing but reads {e['fill']:.0%}; it read {was:.0%} before W6"
        )

    def test_garlic_farmers_market_is_binding_despite_a_low_annual_fill(self, result):
        """The case that makes reporting one figure a defect.

        Garlic/Farmers Market has a 2,000 lb/wk cap across W22-W35, and the garlic is not lifted
        until W29 — so half the capped weeks are unservable and the annual fill is ~50%, while
        every week it CAN supply sells the cap out exactly. Reporting only the annual figure
        calls this slack and drops the farm's tightest demand cap out of the What-If ranking.
        """
        e = result["demand_saturation"]["Farmers Market"]["Garlic"]
        assert e["basis"] == "weekly"
        assert 0.40 < e["fill"] < 0.60, f"annual fill drifted to {e['fill']:.2f} — re-measure"
        assert e["peak_week_frac"] == pytest.approx(1.0, abs=1e-6), (
            "the weekly cap must read as fully binding"
        )
        assert e["binding"] == pytest.approx(e["peak_week_frac"]), (
            "the ranking basis must be the weekly row for a weekly cap"
        )
        assert len(e["weeks_at_cap"]) >= 5, f"only {len(e['weeks_at_cap'])} weeks at cap"
        assert min(e["weeks_at_cap"]) >= 22, "flagged a week before the buyer's window opens"
        assert max(e["weeks_at_cap"]) <= 35, "flagged a week after the buyer's window closes"

    def test_annual_contracts_report_no_weekly_ceiling(self, result, golden_payload):
        """`annual/52` is a limit the solver stopped imposing at B4; the panel kept printing it."""
        annual = {(ch, cp) for cp_ in golden_payload["crops"]
                  for ch, spec in (cp_.get("channels") or {}).items()
                  for cp in [cp_["name"]]
                  if str(spec.get("demand_cap_type", "")).lower() == "annual"}
        seen = 0
        for ch, cp, e in saturation_entries(result):
            if (ch, cp) not in annual:
                continue
            seen += 1
            assert e["basis"] == "annual", f"{ch}/{cp}"
            assert e["peak_week_frac"] is None, f"{ch}/{cp} invented a weekly ceiling"
            assert e["peak_week_cap_lbs"] is None, f"{ch}/{cp} invented a weekly cap figure"
            assert e["weeks_at_cap"] == [], f"{ch}/{cp} flagged weeks against no row"
        assert seen >= 3, f"only {seen} annual-contract rows found — re-check the payload"

    def test_the_old_formula_really_did_overstate_this_farm(self, result, golden_payload):
        """The measurement, pinned so it cannot quietly stop being true.

        The old saturation is recomputed here from the payload — planted acreage x yield over
        each channel's annual cap — entirely independently of anything the solver publishes, so
        this is a comparison of two bases rather than a restatement of one.
        """
        acres = {}
        for s in result["succession_schedule"]:
            acres[s["crop"]] = acres.get(s["crop"], 0.0) + s["acres"]

        overstated, phantom = 0, 0
        for crop in golden_payload["crops"]:
            gross = acres.get(crop["name"], 0.0) * float(crop["yield_per_acre"])
            for ch, spec in (crop.get("channels") or {}).items():
                cap = annual_equivalent_cap(spec)
                e = result["demand_saturation"].get(ch, {}).get(crop["name"])
                if cap <= 0 or e is None:
                    continue
                old = min(1.0, gross / cap)
                if old - e["fill"] > 0.10:
                    overstated += 1
                if e["sold_lbs"] == 0.0 and old > 0.0:
                    phantom += 1
        assert overstated >= 8, (
            f"only {overstated} rows differ by >10 points between the gross-harvest basis and "
            f"the sold basis (10 when measured) — this farm no longer demonstrates W6"
        )
        assert phantom >= 3, (
            f"only {phantom} rows sold zero pounds while the old formula reported a saturation "
            f"(3 when measured)"
        )


class TestCostSplitsReachTheClient(object):
    """W4 — the P&L's cost breakdowns cross the adapter, and still add up when they get there.

    tests/test_cost_splits.py pins the identities inside the solver. This class exists because
    forwarding is a SECOND place they break, and it is the break with no symptoms: the P&L simply
    prints fewer rows, which looks exactly like a P&L. That is how twelve of thirteen detail rows
    came to be missing for the whole life of the exporter, and how W6's `demand_at_cap_threshold`
    reached the browser as `undefined` while every test stayed green.

    Both mutations — the adapter dropping either split — survived the solver-side suite. This is
    what kills them.
    """

    def test_every_key_the_pl_reads_actually_arrives(self, result):
        """Structural: no P&L line may read a key the adapter does not send.

        This is the defect's whole mechanism, generalised. The exporter asked for thirteen keys
        that were never sent and printed nothing, silently — and while fixing exactly that, the
        new "City Water (metered purchase)" row was written against `res.city_water_cost`, which
        the adapter ALSO did not forward. That one was worse than a blank row: the solver charges
        city water into operating_profit, so the missing key would have pushed the difference into
        the new UNRECONCILED tripwire on every farm buying metered water. Nothing caught it — the
        golden farm has city water off, and the jsdom fixture supplied the key itself.

        So the guard is not a list of keys, which is what failed twice. It reads the exporter's
        OWN source for `res.<name>` and requires the payload to carry each one.
        """
        src = INDEX.read_text()
        start = src.index("function exportPLCSV()")
        body = src[start:src.index("\n}", start)]
        # Comments out first, or the prose naming the OLD dead keys reads as live code — this
        # guard's first run flagged `cost_seed` and `cost_harvest_storage` out of the comment
        # that explains why they are gone.
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
        body = re.sub(r"//[^\n]*", "", body)
        read = sorted(set(re.findall(r"\bres\.([a-z_][a-z0-9_]*)\b", body)))
        assert read, "found no res.* reads in exportPLCSV — the extractor is broken, not the app"
        missing = [k for k in read if k not in result]
        assert missing == [], (
            f"exportPLCSV reads {missing} and the adapter does not send them. Every one prints as "
            f"a blank or zero row, and any cost among them also silently unbalances the "
            f"statement. Forward them, or stop reading them."
        )

    def test_both_splits_survive_the_adapter(self, result):
        for key in ("variable_cost_split", "fixed_cost_split"):
            split = result.get(key)
            assert split, f"{key} did not cross the adapter — the P&L has no detail to print"

    def test_the_forwarded_splits_still_sum_to_the_forwarded_totals(self, result):
        """The property the whole fix rests on, checked on the numbers the browser receives.

        Not the same assertion as the solver-side one: the adapter re-floats every value and
        could round, drop or reorder them on the way through. A breakdown that reconciles in
        Python and not in the payload is still a P&L whose parts do not sum to its total.
        """
        for split_key, total_key in (("variable_cost_split", "variable_cost"),
                                     ("fixed_cost_split", "fixed_cost")):
            got = sum(result[split_key].values())
            assert got == pytest.approx(result[total_key], abs=0.01), (
                f"{split_key} sums to {got:,.2f} under a {total_key} of "
                f"{result[total_key]:,.2f} — the P&L would print a breakdown "
                f"{abs(got - result[total_key]):,.2f} short of its own total"
            )

    def test_packaging_is_a_fifth_of_variable_cost_on_this_farm(self, result):
        """The measurement that proved the prescribed one-line fix wrong.

        Exporting the solver's internal `vc_split` — the fix as the backlog described it — would
        have printed five rows under a total that excludes packaging entirely. Pinned as a
        share, not a dollar figure, so it survives a re-pin of the baseline but still fails if
        packaging stops being carried.
        """
        pkg = result["variable_cost_split"]["packaging"]
        share = pkg / result["variable_cost"]
        assert 0.15 < share < 0.30, (
            f"packaging is {share:.1%} of variable cost (20.5% when measured); if it has become "
            f"negligible this farm no longer demonstrates why vc_split alone was not the fix"
        )

    def test_no_flat_cost_key_comes_back_from_the_dead(self, result):
        """The thirteen keys the exporter used to ask for are gone, and must stay gone.

        Two of them were real and were REMOVED with this fix, because each was a second
        derivation of a number the solver already had: `cost_property_mortgage_rent` re-did the
        solver's annualisation, and `cost_ambient_storage` was emitted with a comment saying the
        fixed-cost breakdown needed it while nothing read it at all. Deriving one number twice is
        how the two copies come to disagree (see C6b in W6).
        """
        # The thirteen are named, rather than banning the `cost_` prefix: the property wanted is
        # "no cost is derived twice", and a prefix ban would also reject a legitimate future
        # `cost_of_capital` for no reason.
        DEAD = {
            "cost_seed", "cost_water", "cost_fert", "cost_labor", "cost_fuel",
            "cost_harvest_storage", "cost_water_storage", "cost_irrigation",
            "cost_equip_storage", "cost_fuel_storage", "cost_machinery", "cost_salaries",
            "cost_property_mortgage_rent", "cost_ambient_storage",
        }
        revived = sorted(DEAD & set(result))
        assert revived == [], (
            f"flat per-component cost keys are back: {revived}. Cost detail belongs in "
            f"variable_cost_split / fixed_cost_split, where it is summed to its total — a flat "
            f"key is a second derivation of a number that already has one."
        )
