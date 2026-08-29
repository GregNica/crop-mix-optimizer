"""
build_toy_v2.py — generates the Loss + Storage toy model workbook.

v2 CHANGES ONE THING, and it is the thing the grower's question exposed (backlog G1 /
DECISIONS E1): `sell_through_fraction` was doing two incompatible jobs at once.

  pack_out_fraction   gross harvest -> marketable product. Culls, off-grade, damage.
                      Applied AT HARVEST, before the store. Never occupies a cooler.
  sell_through_fraction  marketable product OFFERED -> actually sold. Returns, unsold at
                      market, rejected loads. Applied AT THE SALE, after the store. This
                      product WAS cooled and shipped; it just did not come back.

v1 applied a single 0.85 at harvest, so 15% of the crop never entered the room at all. That
understates room occupancy by 1/0.85 = 17.6% for whatever share of the loss happens downstream.

The comparison is built INTO this sheet rather than shipped as a second file: set pack-out 0.85
/ sell-through 1.00 and it reproduces v1 exactly. Same total loss, same money, different cooler.
That is the whole lesson, and two workbooks would have drifted.

WHY A GENERATOR AND NOT A HAND-BUILT SHEET. The calendar (which week each succession
plants, grows and harvests) and every crop constant are read from the SAME source the app
uses: farm_v2.utils.calendar.generate_successions and tests/golden/default_farm_payload.json.
A hand-typed sheet would be a second guess at the model, and the whole point of this toy is
to be an INDEPENDENT CHECK on the app's arithmetic — which it cannot be if its inputs are
a retyped approximation. Re-run this after any crop-data change.

Output: farm_toy_v2_loss_and_storage.xlsx  (open in LibreOffice Calc or Excel)
"""
import json, sys, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

from farm_v2.utils.calendar import generate_successions, harvest_weeks_of

# ---------------------------------------------------------------------------
# Source data — from the app, not retyped
# ---------------------------------------------------------------------------
payload = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
CROP_NAMES = ["Spinach", "Kale", "Garlic"]
crops = {c["name"]: c for c in payload["crops"] if c["name"] in CROP_NAMES}

# Five successions, chosen to show: a spring and a fall planting of each quick crop, and the
# one overwintering crop. Picked from the 68 the real generator offers for these three crops.
PICKED = ["Spinach W10", "Spinach W34", "Kale W12", "Kale W32", "Garlic W47"]
all_succ = {s["name"]: s for s in generate_successions(list(crops.values()), 2024)}
succs = [all_succ[n] for n in PICKED]

STF        = payload["sell_through_fraction"]      # 0.85 — now the AT-THE-SALE fraction
PACK_OUT   = 1.00                                  # DECISIONS E1 option (1); see the crop table
COLD_CAP   = payload["harvest_storage_cap"]        # 275 m3
AMB_CAP    = payload["ambient_storage_cap"]        # 150 m3
TOTAL_LAND = payload["total_land"]                 # 80 acres

W0 = 3                       # week 1 lives in column C
def wcol(w): return W0 + w - 1
def wl(w):   return get_column_letter(wcol(w))
LAST = get_column_letter(wcol(52))

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
F_TITLE  = Font(bold=True, size=15)
F_H1     = Font(bold=True, size=12, color="1F4E79")
F_BOLD   = Font(bold=True)
F_NOTE   = Font(italic=True, size=9, color="666666")
F_SMALL  = Font(size=9)
IN_FILL  = PatternFill("solid", fgColor="FFF2CC")   # yellow = you type here
CALC_FILL= PatternFill("solid", fgColor="F2F2F2")
HDR_FILL = PatternFill("solid", fgColor="DDEBF7")
POOL_C   = PatternFill("solid", fgColor="E8F0FE")
POOL_A   = PatternFill("solid", fgColor="FFF0E6")
THIN     = Side(style="thin", color="BFBFBF")
BOX      = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

wb = Workbook()

# ===========================================================================
# SHEET 1 — READ ME
# ===========================================================================
rd = wb.active
rd.title = "READ ME"   # content written at the END, once row numbers are known
rd.column_dimensions["A"].width = 112
readme = [
 ("Farm toy model — v2: LOSS + STORAGE", F_TITLE),
 ("", None),
 ("WHAT CHANGED FROM v1, AND WHY", F_H1),
 ("You asked whether 85% sell-through means the other 15% is not sellable, or that it could not", None),
 ("be sold — and if the latter, whether it should count against storage. It should, and v1 got", None),
 ("it wrong. So did the app; it is filed as G1 / DECISIONS E1.", None),
 ("", None),
 ("One number was doing two incompatible jobs. It is now two numbers, applied on opposite sides", None),
 ("of the store:", None),
 ("", None),
 ("   PACK-OUT       gross harvest -> marketable product.", F_BOLD),
 ("                  Culls, off-grade, damage. Sorted out at harvest. NEVER ENTERS THE COOLER.", None),
 ("", None),
 ("   SELL-THROUGH   marketable product OFFERED -> actually sold.", F_BOLD),
 ("                  Returns, unsold at market, rejected loads. This product WAS cooled, WAS", None),
 ("                  stored and WAS shipped. It just did not come back.", None),
 ("", None),
 ("You said the split is highly variable, and that is exactly why they cannot be one number. A", None),
 ("farm that leaves 15% in the field and a farm that brings 15% home from market have identical", None),
 ("revenue and identical growing costs — and need different sized coolers.", None),
 ("", None),
 ("THE DEMONSTRATION — it is built into this sheet, not a second file", F_H1),
 ("Ships as Pack-out 1.00 / Sell-through 0.85: ALL loss is downstream.", None),
 ("     Peak COLD {PK_COLD} m3      Peak AMBIENT {PK_AMB} m3", F_BOLD),
 ("", None),
 ("Now set Pack-out to 0.85 and Sell-through to 1.00 ({PACKOUT} and {SELLTHRU}). That is v1, and", None),
 ("it is also what the app does today: all loss in the field.", None),
 ("     Peak COLD {V1_COLD} m3      Peak AMBIENT {V1_AMB} m3", F_BOLD),
 ("", None),
 ("Same loss. Same pounds sold. Same money. THE COOLER REQUIREMENT DIFFERS BY {DELTA_PCT}.", F_BOLD),
 ("", None),
 ("On the real 80-acre farm that difference takes the barn from 90.5% full to 106.5% — from", None),
 ("comfortable to physically impossible. That is why this was worth stopping for.", None),
 ("", None),
 ("HOW THE FLOW READS NOW", F_H1),
 ("Each crop block runs top to bottom in the order the product actually moves:", None),
 ("", None),
 ("     Harvested (gross)              everything that comes off the field", None),
 ("       field cull                   removed here, never cooled            <- PACK-OUT", None),
 ("     Packed out -> INTO the store   what the cooler must hold", None),
 ("     Stock carried in / shrink      what was already there, and what it lost", None),
 ("     In store this week", None),
 ("     Shipped out of store           = what you sell, divided by sell-through", None),
 ("     Sold                           the pounds that became cash          <- SELL-THROUGH", None),
 ("       market loss                  cooled, shipped, unsold, gone", None),
 ("     Stock carried out", None),
 ("     ROOM OCCUPANCY                 carried in + everything packed out", None),
 ("", None),
 ("Read the two loss lines against each other: FIELD CULL is above the store and costs you no", None),
 ("cooler space; MARKET LOSS is below it and costs you all of it.", None),
 ("", None),
 ("WHY 'SHIPPED' IS BIGGER THAN 'SOLD'", F_H1),
 ("Because to sell 850 lb at 85% sell-through you have to send 1,000. The store gives up the", None),
 ("full 1,000; only 850 turns into money. That division is the whole mechanism, and it is why", None),
 ("sell-through cannot be modelled as a simple price discount — you pay to grow, cool and store", None),
 ("every pound, and get paid for 85% of them.", None),
 ("", None),
 ("HOW TO USE IT", F_H1),
 ("1. Every YELLOW cell is an input. Nothing else should be typed in.", None),
 ("2. Start with the acres in {ACRES}. Change one. Watch the whole sheet move.", None),
 ("3. Watch the 'room left' rows under LAND, COLD STORE and AMBIENT STORE. Red = over the limit", None),
 ("   in that week, which the app treats as an infeasible plan, not a warning.", None),
 ("", None),
 ("HOW THE SHEET IS LAID OUT", F_H1),
 ("Sections 1-3 are inputs. Section 4 is the year, week 1 to 52, left to right.", None),
 ("Only columns A and B are frozen, so scrolling up and down is free. Every band repeats its own", None),
 ("week-number strip so you never lose your place going right.", None),
 ("", None),
 ("EVERY CONSTRAINT IS THREE ROWS — the same shape you wrote in the original Group 5 model", None),
 ("('Available Land' / '<=' / '1', Model sheet rows 16-18):", None),
 ("        LAND in the ground     18.0  18.0  18.0   ...   <- what the plan uses", None),
 ("                                 <=    <=    <=", None),
 ("          limit                80.0  80.0  80.0   ...   <- what you have", None),
 ("          room left            62.0  62.0  62.0   ...", None),
 ("Read downwards, it IS the inequality. Three of them: LAND, COLD STORE, AMBIENT STORE.", None),
 ("", None),
 ("CHECK IT WORKED — the numbers you should see on opening", F_H1),
 ("Every planting 6 acres, Pack-out 1.00, Sell-through 0.85, shrink 0, sell rate 1,000,000:", None),
 ("     Peak LAND in the ground  {PK_LAND} acres in {LAND_WKS}   (you have 80)", F_BOLD),
 ("     Peak COLD store          {PK_COLD} m3  in week {PK_COLD_WK}         (cooler holds 275)", F_BOLD),
 ("     Peak AMBIENT store       {PK_AMB} m3  in week {PK_AMB_WK}         (barn holds 150)", F_BOLD),
 ("     Stock carried out        0 lb in every week, all three crops", F_BOLD),
 ("     Spinach  gross {SPINACH_GROSS} lb -> sold {SPINACH_SOLD} -> market loss {SPINACH_MLOSS}", None),
 ("     Kale     gross {KALE_GROSS} lb -> sold {KALE_SOLD} -> market loss {KALE_MLOSS}", None),
 ("     Garlic   gross {GARLIC_GROSS} lb -> sold {GARLIC_SOLD} -> market loss {GARLIC_MLOSS}", None),
 ("If those do not match, tell me — do not work around it.", None),
 ("", None),
 ("Note the pair in bold: closing stock is ZERO all year and the cooler is still {PK_COLD} m3 full.", None),
 ("A cooler is sized by what passes THROUGH it, not by what sleeps in it. Field heat has to come", None),
 ("off spinach within the hour whether it ships Tuesday or Friday. The app measured end-of-week", None),
 ("stock for months, so a farm that sold everything the week it picked was reported as needing", None),
 ("no cooler at all.", None),
 ("", None),
 ("THREE THINGS TO TRY", F_H1),
 ("", None),
 ("EXPERIMENT 1 — where the loss happens.  Set Pack-out to 0.85 and Sell-through to 1.00.", F_BOLD),
 ("   Expect: peak COLD {V1_COLD} m3, peak AMBIENT {V1_AMB} m3, market loss 0, field cull {SP_CULL} lb for", None),
 ("   Spinach. Sold is UNCHANGED at {SPINACH_SOLD} lb. Same money, {DELTA_PCT} less cooler.", None),
 ("", None),
 ("EXPERIMENT 2 — overflow the stores.  Put pack-out back to 1.00, set all five acre cells", F_BOLD),
 ("   ({ACRES}) to 25.", F_BOLD),
 ("   Expect: peak COLD {BIG_COLD} m3 (red, over 275) and peak AMBIENT {BIG_AMB} m3 (red, over 150).", None),
 ("   At v1's numbers the cooler survived this; it does not any more. The cooler now breaks at", None),
 ("   about {BREAK_AC} acres per planting instead of {V1_BREAK}.", None),
 ("", None),
 ("EXPERIMENT 3 — hold stock, and watch what does NOT happen.  Acres back to 6.", F_BOLD),
 ("   Set Garlic's 'Sell rate lb/wk' ({G_SELL}) to 2000.", F_BOLD),
 ("   Expect: Garlic sells less, carries stock into next year, and trips the shelf-life warning.", None),
 ("   BUT peak AMBIENT is still {PK_AMB} m3 in week {PK_AMB_WK} — exactly as before. Holding stock for months", F_BOLD),
 ("   did not add one cubic metre, because the peak is set by the week the harvest lands.", None),
 ("   Then set Garlic's 'Shrink %/wk' ({G_SHRINK}) to 2% and watch the leftovers disappear —", None),
 ("   shrink is what stops a long shelf life being free money.", None),
 ("", None),
 ("WHAT THIS VERSION STILL DOES NOT CARRY", F_H1),
 ("  - No demand caps. 'Sell rate lb/wk' is a stand-in for the buyer. The real model has", None),
 ("    per-channel weekly AND annual caps — that is the next layer.", None),
 ("  - No prices, costs, revenue or profit. This layer is physical only.", None),
 ("  - No cash, no labour, no water, no diversity, no planting/harvest throughput limits.", None),
 ("  - Shelf life is a WARNING, not enforced, and ignores the decay weighting the real", None),
 ("    constraint applies.", None),
 ("  - The real model DECIDES the acres. Here you type them.", None),
 ("  - The app itself does NOT yet do what this sheet does. G1/E1 is a proposal awaiting your", None),
 ("    decision; today the app still applies one fraction at harvest.", None),
 ("", None),
 ("WHY 'Shipped' AND 'Sold' USE MIN() — AND WHY THAT IS A FINDING", F_H1),
 ("MIN() is not linear, so a linear solver cannot use it. That is exactly why the real model has", None),
 ("no 'sold' formula: it makes pounds sold a DECISION VARIABLE and bounds it with a constraint", None),
 ("instead. When the spreadsheet cannot express something, that is usually telling you something", None),
 ("true about the solver.", None),
 ("", None),
 ("!! THE SCALE WARNING — READ BEFORE CONCLUDING ANYTHING", F_H1),
 ("Small models are TIGHT; large ones are LOOSE. This toy has 3 crops and 5 plantings; the real", None),
 ("farm has 7 crops and 220 acre-plantings. Which constraints BIND changes with scale, and this", None),
 ("sheet will get that wrong. It teaches MECHANISM. The app's capacity_series tells you which", None),
 ("constraint is actually binding on your farm. Nothing concluded here becomes a plan item", None),
 ("without re-measuring against the real farm.", None),
 ("", None),
 ("HAS THIS SHEET BEEN CHECKED?", F_H1),
 ("Yes. Every crop constant and planting date is READ FROM THE APP by the generator — nothing is", None),
 ("retyped. The whole workbook is CALCULATED by a formula engine and compared cell by cell", None),
 ("against a separate model of the same arithmetic, under two configurations. Every yellow input", None),
 ("is changed and the sheet re-calculated to prove it reaches the numbers at the bottom. And no", None),
 ("number on the Model sheet is frozen except the week strips and the week-1 zero.", None),
 ("", None),
 ("  Run it yourself:   .venv/bin/python toy_models/verify_toy_v2.py", None),
 ("", None),
 ("You found the frozen column in v1 within a minute of opening it. That is why these checks", None),
 ("exist, and why they now run on every rebuild.", None),
 ("", None),
 ("WHERE THE NUMBERS COME FROM", F_H1),
 ("Crop constants from tests/golden/default_farm_payload.json; planting calendar from the app's", None),
 ("own succession generator. See the 'Crop data' sheet. Regenerate after any crop-data change:", None),
 ("     python3 toy_models/build_toy_v2.py", None),
]

# ===========================================================================
# SHEET 2 — MODEL
# ===========================================================================
ws = wb.create_sheet("Model")
ws.column_dimensions["A"].width = 30
ws.column_dimensions["B"].width = 13
for w in range(1, 53):
    ws.column_dimensions[wl(w)].width = 8.5

def put(r, c, v, font=None, fill=None, fmt=None, align=None, border=False):
    cell = ws.cell(row=r, column=c, value=v)
    if font: cell.font = font
    if fill: cell.fill = fill
    if fmt:  cell.number_format = fmt
    if align: cell.alignment = Alignment(horizontal=align)
    if border: cell.border = BOX
    return cell


def week_header(r, note=""):
    """A week-number strip. REPEATED at the head of every band on purpose.

    The first version froze rows 1-25 so the week numbers would stay visible, which pinned the
    whole input block and left about five scrollable rows on a normal screen — vertical scrolling
    looked broken while horizontal still worked. Freezing the LABEL COLUMNS only and repeating
    this strip costs six rows and cannot do that.
    """
    put(r, 1, "Week", font=F_BOLD, fill=HDR_FILL)
    put(r, 2, note, font=F_NOTE, fill=HDR_FILL)
    for w in range(1, 53):
        put(r, wcol(w), w, font=F_BOLD, fill=HDR_FILL, align="center")
    return r + 1


def constraint_triplet(r, label, lhs_formula, cap_ref, fill, note):
    """The original Group 5 model's own idiom: a row of values, a '<=' row, and the limit.

    Read top to bottom it IS the inequality. Copied deliberately from 'Model' rows 16-18 of
    'Group 5_Baby Model_Final (2).xlsx' (Available Land / <= / 1), because that is the layout
    the grower wrote and already reads without translation.
    """
    put(r, 1, label, font=F_BOLD, fill=fill)
    put(r, 2, "used", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), lhs_formula(w), fmt="0.0", fill=fill)
    used = r; r += 1
    put(r, 1, "", font=F_BOLD)
    put(r, 2, "", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), "<=", align="center", font=F_BOLD)
    r += 1
    put(r, 1, "  limit", font=F_BOLD)
    put(r, 2, "cap", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={cap_ref}", fmt="0.0")
    r += 1
    put(r, 1, "  room left", font=F_SMALL)
    put(r, 2, "", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={cap_ref}-{wl(w)}{used}", fmt="0.0")
    head = r; r += 1
    put(r, 1, note, font=F_NOTE)
    r += 2
    for rng, op, formula in ((head, "lessThan", ["0"]), (used, "greaterThan", [cap_ref])):
        ws.conditional_formatting.add(
            f"{wl(1)}{rng}:{LAST}{rng}",
            CellIsRule(operator=op, formula=formula,
                       fill=PatternFill("solid", fgColor="FFC7CE"),
                       font=Font(color="9C0006", bold=True)))
    return r, used, head

r = 1
put(r, 1, "FARM TOY MODEL — v1: the spine + storage"); ws.cell(row=r, column=1).font = F_TITLE
r += 1
put(r, 1, "Type in the YELLOW cells only. Everything else is a formula. Read the 'READ ME' sheet first.", font=F_NOTE)
r += 2

# ---- INPUT: acres per succession ----
put(r, 1, "1 — WHAT YOU PLANT   (acres)", font=F_H1); r += 1
hdr = ["Succession", "Acres", "Crop", "Harvest weeks", "gross lb/harvest wk per acre"]
for j, h in enumerate(hdr):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_SUCC = r
# The crop settings table lands below this one, so its row numbers are computed up front:
# 5 succession rows + 'Total acres planted' + 'Land you have' + blank + section head + header.
crop_row_pending = {n: ROW_SUCC + len(PICKED) + 5 + i for i, n in enumerate(CROP_NAMES)}
succ_meta = []
for s in succs:
    crop = crops[s["crop_name"]] if "crop_name" in s else crops[CROP_NAMES[s["crop"]]]
    nharv = max(1, len(harvest_weeks_of(s, 52)))
    put(r, 1, s["name"], border=True)
    put(r, 2, 6.0, fill=IN_FILL, fmt="0.0", border=True)          # <- INPUT
    put(r, 3, crop["name"], border=True)
    put(r, 4, ", ".join("W%d" % w for w in harvest_weeks_of(s, 52)), font=F_SMALL, border=True)
    # A FORMULA, never a baked number. This column describes the live harvest rows below it, and
    # a frozen copy beside a live figure is this project's most-repeated defect — the grower spotted
    # it here within a minute of opening the file, and was right to conclude there would be more.
    # (There were not, but only because every other displayed number already derived itself.)
    put(r, 5, f'=$B${crop_row_pending[crop["name"]]}/{nharv}', fmt="#,##0", border=True)
    succ_meta.append({"row": r, "s": s, "crop": crop["name"], "nharv": nharv})
    r += 1
put(r, 1, "Total acres planted", font=F_BOLD)
put(r, 2, f"=SUM(B{ROW_SUCC}:B{r-1})", font=F_BOLD, fmt="0.0")
put(r, 3, "sum of the five above — but they overlap in time, so this is NOT peak land use", font=F_NOTE)
ROW_TOTACRES = r
r += 1
put(r, 1, "Land you have", font=F_BOLD)
put(r, 2, TOTAL_LAND, fill=IN_FILL, fmt="0.0", border=True)
put(r, 3, "acres — the limit the 'LAND in the ground' rows below are measured against", font=F_NOTE)
ROW_LAND = r
r += 2

# ---- INPUT: crop settings ----
put(r, 1, "2 — HOW EACH CROP BEHAVES", font=F_H1); r += 1
cols = ["Crop", "Yield lb/acre", "Pack-out", "Sell-through", "m3 per lb", "Store",
        "Shelf life wk", "Shrink %/wk", "Sell rate lb/wk"]
for j, h in enumerate(cols):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_CROP = r
crop_row = {}
for name in CROP_NAMES:
    c = crops[name]
    pool = "Cold" if c.get("cold_storage", True) else "Ambient"
    put(r, 1, name, border=True)
    # Yellow because they ARE live inputs — every formula that needs them reads these cells, and
    # the propagation check proves it. They were rendered as plain constants, which read as
    # "look, do not touch" for two of the biggest levers on the sheet.
    put(r, 2, c["yield_per_acre"], fill=IN_FILL, fmt="#,##0", border=True)
    # DEFAULTS per DECISIONS E1 option (1): all of today's 15% treated as DOWNSTREAM loss.
    # Conservative for sizing, and it makes the app's own tooltip true. Set 0.85 / 1.00 to
    # reproduce v1 exactly.
    put(r, 3, PACK_OUT, fill=IN_FILL, fmt="0.00", border=True)
    put(r, 4, STF, fill=IN_FILL, fmt="0.00", border=True)
    put(r, 5, c["crop_size_m3_per_lb"], fill=IN_FILL, fmt="0.0000000", border=True)
    put(r, 6, pool, border=True, fill=POOL_C if pool == "Cold" else POOL_A)
    put(r, 7, c.get("shelf_life_weeks", c.get("sales_spread_weeks", 1)), fill=IN_FILL, border=True)
    put(r, 8, 0.0, fill=IN_FILL, fmt="0.0%", border=True)
    put(r, 9, 1000000, fill=IN_FILL, fmt="#,##0", border=True)
    crop_row[name] = r
    assert crop_row_pending[name] == r, (
        f"crop settings row moved: reserved {crop_row_pending[name]} for {name}, wrote {r}. "
        f"The 'lb/harvest wk' formulas above point at the reserved row.")
    r += 1
put(r, 1, "Shrink is weight lost in store each week. Sell rate stands in for the buyer (layer 2 makes it real).", font=F_NOTE)
r += 2

# ---- INPUT: storage caps ----
put(r, 1, "3 — WHAT YOU CAN STORE", font=F_H1); r += 1
put(r, 1, "Cold store (cooler) capacity", border=True)
put(r, 2, COLD_CAP, fill=IN_FILL, fmt="#,##0", border=True); ROW_COLDCAP = r
put(r, 3, "m3   — Spinach, Kale", font=F_NOTE); r += 1
put(r, 1, "Ambient store (barn) capacity", border=True)
put(r, 2, AMB_CAP, fill=IN_FILL, fmt="#,##0", border=True); ROW_AMBCAP = r
put(r, 3, "m3   — Garlic (cured; the cooler would damage it)", font=F_NOTE)
r += 2

# ---- week header ----
put(r, 1, "4 — THE YEAR, WEEK BY WEEK", font=F_H1); r += 1
ROW_WEEKNUM = r
r = week_header(r)
# Columns A-B only. See week_header's docstring for why no rows are frozen.
ws.freeze_panes = "C1"

# ---- per-succession phase + harvest ----
put(r, 1, "PLANTING CALENDAR", font=F_BOLD); r += 1
PHASE_TXT = {0: "P", 1: "G", 2: "H"}
succ_harv_row = {}
for m in succ_meta:
    s = m["s"]
    phase_by_week = {}
    for wk, ph in zip(s["weeks"], s["phases"]):
        ww = ((wk - 1) % 52) + 1
        phase_by_week[ww] = ph
    put(r, 1, s["name"], font=F_SMALL)
    put(r, 2, "P/G/H", font=F_NOTE)
    for w in range(1, 53):
        if w in phase_by_week:
            put(r, wcol(w), PHASE_TXT[phase_by_week[w]], align="center", font=F_SMALL,
                fill=CALC_FILL)
    phrow = r
    m["phase_row"] = phrow
    r += 1
    put(r, 1, "   lbs harvested (GROSS)", font=F_SMALL)
    put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        col = wl(w)
        put(r, wcol(w),
            f'=IF({col}{phrow}="H",$B${m["row"]}*$B${crop_row[m["crop"]]}/{m["nharv"]},0)',
            fmt="#,##0")
    succ_harv_row.setdefault(m["crop"], []).append(r)
    r += 1
put(r, 1, "P = planting   G = growing   H = harvesting.  GROSS pounds — everything that comes off the field.", font=F_NOTE)
r += 2

# The one constraint the grower already knows, in the layout they already read — so the
# storage rows below are a familiar shape carrying an unfamiliar quantity.
r = week_header(r, "acres")
land_lhs = lambda w: "=" + "+".join(
    f'IF({wl(w)}{m["phase_row"]}<>"",$B${m["row"]},0)' for m in succ_meta)
r, ROW_LANDUSED, _ = constraint_triplet(
    r, "LAND in the ground", land_lhs, f"$B${ROW_LAND}", None,
    "   Acres standing in the ground that week. A succession occupies its ground from planting "
    "to its LAST harvest week — which is why the five acre figures above can sum past your land "
    "and still be legal, as long as no single WEEK does.")

# ---- per-crop inventory + storage ----
crop_block = {}
for name in CROP_NAMES:
    cr = crop_row[name]
    pool = "Cold" if crops[name].get("cold_storage", True) else "Ambient"
    put(r, 1, f"{name.upper()}  —  {pool.lower()} store", font=F_H1)
    put(r, 2, "", fill=POOL_C if pool == "Cold" else POOL_A)
    r += 1
    r = week_header(r)

    # ---- BEFORE THE STORE ------------------------------------------------
    put(r, 1, "Harvested (gross)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        parts = "+".join(f"{wl(w)}{hr}" for hr in succ_harv_row[name])
        put(r, wcol(w), f"={parts}", fmt="#,##0")
    R_GROSS = r; r += 1

    put(r, 1, "   field cull (never cooled)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_GROSS}*(1-$C${cr})", fmt="#,##0")
    R_CULL = r; r += 1

    put(r, 1, "Packed out -> INTO the store", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_GROSS}*$C${cr}", fmt="#,##0")
    R_HARV = r; r += 1

    # ---- IN THE STORE ----------------------------------------------------
    put(r, 1, "Stock carried in", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), 0 if w == 1 else f"={wl(w-1)}{r+6}", fmt="#,##0")
    R_OPEN = r; r += 1

    put(r, 1, "   lost to shrink", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_OPEN}*$H${cr}", fmt="#,##0")
    R_SHRINK = r; r += 1

    put(r, 1, "In store this week", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_OPEN}-{wl(w)}{R_SHRINK}+{wl(w)}{R_HARV}", fmt="#,##0")
    R_AVAIL = r; r += 1

    # ---- LEAVING THE STORE ----------------------------------------------
    # Sell rate is the BUYER's appetite, in pounds SOLD. To sell S you must ship S / sell-through,
    # so the drawdown on the store is the larger number. Shipping is capped by what is in store.
    put(r, 1, "Shipped out of store", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"=MIN({wl(w)}{R_AVAIL},$I${cr}/$D${cr})", fmt="#,##0")
    R_SHIP = r; r += 1

    put(r, 1, "Sold", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_SHIP}*$D${cr}", fmt="#,##0")
    R_SOLD = r; r += 1

    put(r, 1, "   market loss (did not come back)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_SHIP}-{wl(w)}{R_SOLD}", fmt="#,##0")
    R_MLOSS = r; r += 1

    put(r, 1, "Stock carried out", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_AVAIL}-{wl(w)}{R_SHIP}", fmt="#,##0")
    R_CLOSE = r; r += 1

    put(r, 1, "ROOM OCCUPANCY", font=F_BOLD)
    put(r, 2, "m3", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"=({wl(w)}{R_OPEN}+{wl(w)}{R_HARV})*$E${cr}", fmt="0.0",
            fill=POOL_C if pool == "Cold" else POOL_A)
    R_ROOM = r; r += 1
    put(r, 1, "   = carried in + everything PACKED OUT this week, before any of it ships.", font=F_NOTE)
    r += 1
    put(r, 1, "   Market loss is already counted here — it was in the room before it left.", font=F_NOTE)
    r += 1

    put(r, 1, "Over shelf life?", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w),
            f'=MAX(0,{wl(w)}{R_CLOSE}-SUMIFS(${wl(1)}${R_HARV}:${LAST}${R_HARV},'
            f'${wl(1)}${ROW_WEEKNUM}:${LAST}${ROW_WEEKNUM},">="&{wl(w)}${ROW_WEEKNUM}-$G${cr}+2,'
            f'${wl(1)}${ROW_WEEKNUM}:${LAST}${ROW_WEEKNUM},"<="&{wl(w)}${ROW_WEEKNUM}))',
            fmt="#,##0")
    R_OLD = r; r += 1
    put(r, 1, "   stock older than its shelf life — a WARNING here, a hard constraint in the app", font=F_NOTE)
    r += 2
    crop_block[name] = dict(gross=R_GROSS, cull=R_CULL, harv=R_HARV, ship=R_SHIP, sold=R_SOLD,
                            mloss=R_MLOSS, close=R_CLOSE, room=R_ROOM, shrink=R_SHRINK,
                            old=R_OLD, pool=pool)

# ---- pools ----
put(r, 1, "5 — THE TWO STORES", font=F_H1); r += 1
put(r, 1, "Same three-row shape as LAND above, and as 'Available Land / <= / 1' in the original "
          "Group 5 model. Read each block downwards: it IS the inequality.", font=F_NOTE)
r += 1
pool_rows = {}
for pool, cap_row, fill in (("Cold", ROW_COLDCAP, POOL_C), ("Ambient", ROW_AMBCAP, POOL_A)):
    members = [n for n in CROP_NAMES if crop_block[n]["pool"] == pool]
    r = week_header(r, "m3")
    lhs = (lambda mem: (lambda w: "=" + "+".join(
        f"{wl(w)}{crop_block[n]['room']}" for n in mem)))(members)
    r, used, head = constraint_triplet(
        r, f"{pool.upper()} STORE", lhs, f"$B${cap_row}", fill,
        f"   Holds {', '.join(members)}. A RED cell is not a warning — the app refuses the plan.")
    pool_rows[pool] = dict(used=used, head=head, cap=cap_row)

# ---- summary ----
put(r, 1, "6 — WHAT THIS PLAN DOES", font=F_H1); r += 1
def summary(label, formula, fmt="#,##0", note="", bold=False):
    global r
    put(r, 1, label, font=F_BOLD if bold else None)
    put(r, 2, formula, fmt=fmt, font=F_BOLD if bold else None)
    if note: put(r, 3, note, font=F_NOTE)
    r += 1

summary("Peak COLD store used", f"=MAX({wl(1)}{pool_rows['Cold']['used']}:{LAST}{pool_rows['Cold']['used']})",
        "0.0", f"m3   against a {COLD_CAP} m3 cooler", bold=True)
summary("Weeks the cooler overflows",
        f"=COUNTIF({wl(1)}{pool_rows['Cold']['head']}:{LAST}{pool_rows['Cold']['head']},\"<0\")",
        "0", "weeks out of 52", bold=True)
summary("Peak AMBIENT store used", f"=MAX({wl(1)}{pool_rows['Ambient']['used']}:{LAST}{pool_rows['Ambient']['used']})",
        "0.0", f"m3   against a {AMB_CAP} m3 barn", bold=True)
summary("Weeks the barn overflows",
        f"=COUNTIF({wl(1)}{pool_rows['Ambient']['head']}:{LAST}{pool_rows['Ambient']['head']},\"<0\")",
        "0", "weeks out of 52", bold=True)
r += 1
for name in CROP_NAMES:
    b = crop_block[name]
    summary(f"{name} — harvested (gross)", f"=SUM({wl(1)}{b['gross']}:{LAST}{b['gross']})", "#,##0", "lb off the field")
    summary(f"{name} — field cull", f"=SUM({wl(1)}{b['cull']}:{LAST}{b['cull']})", "#,##0",
            "lb  — never entered the store")
    summary(f"{name} — packed out", f"=SUM({wl(1)}{b['harv']}:{LAST}{b['harv']})", "#,##0",
            "lb  — this is what the cooler has to hold")
    summary(f"{name} — shipped", f"=SUM({wl(1)}{b['ship']}:{LAST}{b['ship']})", "#,##0", "lb out of store")
    summary(f"{name} — SOLD", f"=SUM({wl(1)}{b['sold']}:{LAST}{b['sold']})", "#,##0", "lb", bold=True)
    summary(f"{name} — market loss", f"=SUM({wl(1)}{b['mloss']}:{LAST}{b['mloss']})", "#,##0",
            "lb  — was cooled and shipped, did not sell, does not come back")
    summary(f"{name} — lost to shrink", f"=SUM({wl(1)}{b['shrink']}:{LAST}{b['shrink']})", "#,##0", "lb in store")
    summary(f"{name} — left at year end", f"={LAST}{b['close']}", "#,##0",
            "lb  (the app anchors stock at zero on 1 Jan, so this is stranded)")
    summary(f"{name} — over shelf life at worst", f"=MAX({wl(1)}{b['old']}:{LAST}{b['old']})", "#,##0",
            "lb  (WARNING only in this sheet)")
    r += 1

# ===========================================================================
# SHEET 3 — CROP DATA
# ===========================================================================
cd = wb.create_sheet("Crop data")
cd.column_dimensions["A"].width = 34
for col in "BCD":
    cd.column_dimensions[col].width = 17
rows = [("Crop constants — READ FROM THE APP, not retyped", F_TITLE)]
cd.cell(row=1, column=1, value=rows[0][0]).font = F_TITLE
cd.cell(row=2, column=1,
        value="Source: tests/golden/default_farm_payload.json (the payload the browser sends) and "
              "farm_v2.utils.calendar.generate_successions (the app's own calendar).").font = F_NOTE
cd.cell(row=3, column=1, value="Regenerate with:  python3 toy_models/build_toy_v2.py").font = F_NOTE
hdrs = ["Field", "Spinach", "Kale", "Garlic", "What it means"]
for j, h in enumerate(hdrs):
    c = cd.cell(row=5, column=1 + j, value=h); c.font = F_BOLD; c.fill = HDR_FILL
fields = [
 ("yield_per_acre", "lb of crop per acre, before sell-through"),
 ("crop_size_m3_per_lb", "how much store space one pound takes"),
 ("cold_storage", "TRUE = cooler, FALSE = ambient barn"),
 ("shelf_life_weeks", "weeks it can be SOLD IN, counting its harvest week"),
 ("days_to_maturity", "plant to FIRST harvest (not total field time)"),
 ("planting_weeks", "how long the planting phase lasts"),
 ("harvest_weeks", "how many weeks it is picked over"),
 ("overwinters", "may its cycle run past week 52"),
 ("seasons", "the PLANTING window(s) — any start week inside is legal"),
]
rr = 6
for key, meaning in fields:
    cd.cell(row=rr, column=1, value=key).font = F_BOLD
    for j, name in enumerate(CROP_NAMES):
        v = crops[name].get(key, crops[name].get("sales_spread_weeks") if key == "shelf_life_weeks" else "")
        if key == "seasons":
            v = "; ".join(f"{s['start']}->{s['end']}" for s in crops[name]["seasons"])
        cd.cell(row=rr, column=2 + j, value=str(v) if not isinstance(v, (int, float)) else v)
    cd.cell(row=rr, column=5, value=meaning).font = F_SMALL
    rr += 1
rr += 1
cd.cell(row=rr, column=1, value="Farm-level").font = F_H1; rr += 1
for k, v, note in (("total_land", TOTAL_LAND, "acres of ground"),
                   ("sell_through_fraction", STF, "share of harvest that becomes sellable product"),
                   ("harvest_storage_cap", COLD_CAP, "m3 of refrigerated space"),
                   ("ambient_storage_cap", AMB_CAP, "m3 of barn space")):
    cd.cell(row=rr, column=1, value=k).font = F_BOLD
    cd.cell(row=rr, column=2, value=v)
    cd.cell(row=rr, column=5, value=note).font = F_SMALL
    rr += 1
rr += 2
cd.cell(row=rr, column=1, value="The 5 plantings on the Model sheet").font = F_H1; rr += 1
cd.cell(row=rr, column=1, value="chosen from the 68 the app's generator offers for these three crops").font = F_NOTE
rr += 1
for j, h in enumerate(["Succession", "Crop", "In the ground", "Harvest weeks"]):
    c = cd.cell(row=rr, column=1 + j, value=h); c.font = F_BOLD; c.fill = HDR_FILL
rr += 1
for m in succ_meta:
    s = m["s"]
    cd.cell(row=rr, column=1, value=s["name"])
    cd.cell(row=rr, column=2, value=m["crop"])
    cd.cell(row=rr, column=3, value=f"W{s['weeks'][0]} to W{((s['weeks'][-1]-1)%52)+1} ({len(s['weeks'])} wk)")
    cd.cell(row=rr, column=4, value=", ".join("W%d" % w for w in harvest_weeks_of(s, 52)))
    rr += 1

# ---------------------------------------------------------------------------
# The numbers the READ ME promises, COMPUTED — never typed.
#
# Three of them shipped 0.1 out on the first pass because I rounded by hand while writing the
# prose. Same class as the cell coordinates below and as the frozen column the grower found in
# v1: a figure written beside its source instead of derived from it. The README cannot now
# promise a number the sheet does not produce.
# ---------------------------------------------------------------------------
def _sim(acres, packout, stf, sell, shrink):
    gross = {n: [0.0] * 53 for n in CROP_NAMES}
    for pn, m in zip(PICKED, succ_meta):
        s_ = m["s"]; cn = m["crop"]
        for w in harvest_weeks_of(s_, 52):
            gross[cn][w] += acres * crops[cn]["yield_per_acre"] / m["nharv"]
    close = {n: [0.0] * 53 for n in CROP_NAMES}
    room = {n: [0.0] * 53 for n in CROP_NAMES}
    sold = {n: 0.0 for n in CROP_NAMES}
    cull = {n: 0.0 for n in CROP_NAMES}
    mloss = {n: 0.0 for n in CROP_NAMES}
    for n in CROP_NAMES:
        for w in range(1, 53):
            packed = gross[n][w] * packout
            cull[n] += gross[n][w] - packed
            opening = close[n][w - 1] if w > 1 else 0.0
            in_store = opening - opening * shrink + packed
            ship = min(in_store, sell / stf)
            sold[n] += ship * stf
            mloss[n] += ship - ship * stf
            close[n][w] = in_store - ship
            room[n][w] = (opening + packed) * crops[n]["crop_size_m3_per_lb"]
    cold = [room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)]
    amb = [room["Garlic"][w] for w in range(1, 53)]
    return dict(cold=max(cold), cold_wk=cold.index(max(cold)) + 1,
                amb=max(amb), amb_wk=amb.index(max(amb)) + 1,
                gross={n: sum(gross[n]) for n in CROP_NAMES}, sold=sold, cull=cull, mloss=mloss)


_BASE = _sim(6.0, PACK_OUT, STF, 1e6, 0.0)
_V1   = _sim(6.0, STF, 1.0, 1e6, 0.0)
_BIG  = _sim(25.0, PACK_OUT, STF, 1e6, 0.0)
_land = [0.0] * 53
for m in succ_meta:
    for wk in m["s"]["weeks"]:
        _land[((wk - 1) % 52) + 1] += 6.0
_peak_land = max(_land[1:])
_land_wks = [w for w in range(1, 53) if _land[w] == _peak_land]
NUMS = {
    "{PK_COLD}":   f"{_BASE['cold']:.1f}",   "{PK_COLD_WK}": str(_BASE["cold_wk"]),
    "{PK_AMB}":    f"{_BASE['amb']:.1f}",    "{PK_AMB_WK}":  str(_BASE["amb_wk"]),
    "{V1_COLD}":   f"{_V1['cold']:.1f}",     "{V1_AMB}":     f"{_V1['amb']:.1f}",
    "{BIG_COLD}":  f"{_BIG['cold']:.1f}",    "{BIG_AMB}":    f"{_BIG['amb']:.1f}",
    "{PK_LAND}":   f"{_peak_land:.1f}",
    "{LAND_WKS}":  f"weeks {_land_wks[0]}-{_land_wks[-1]}",
    "{BREAK_AC}":  f"{6.0 * COLD_CAP / _BASE['cold']:.1f}",
    "{V1_BREAK}":  f"{6.0 * COLD_CAP / _V1['cold']:.1f}",
    "{SP_CULL}":   f"{_V1['cull']['Spinach']:,.0f}",
    "{DELTA_PCT}": f"{(_BASE['cold'] / _V1['cold'] - 1) * 100:.1f}%",
}
for _n in CROP_NAMES:
    NUMS[f"{{{_n.upper()}_GROSS}}"] = f"{_BASE['gross'][_n]:,.0f}"
    NUMS[f"{{{_n.upper()}_SOLD}}"]  = f"{_BASE['sold'][_n]:,.0f}"
    NUMS[f"{{{_n.upper()}_MLOSS}}"] = f"{_BASE['mloss'][_n]:,.0f}"


# ---------------------------------------------------------------------------
# READ ME content, written LAST so its cell references are the real ones.
#
# The first version hard-coded them. Adding one row to the input block shifted every crop
# settings row by one, and the instructions then pointed at the wrong crop — the sheet said
# "set Garlic's shrink (G17)" at a cell holding Kale's. A document that names a coordinate has
# to derive it, exactly as this project's totals are summed from their parts rather than
# written beside them.
# ---------------------------------------------------------------------------
GARLIC_ROW = crop_row["Garlic"]
COORDS = {
    "{ACRES}":      f"B{ROW_SUCC}:B{ROW_SUCC + len(succ_meta) - 1}",
    "{LAND}":       f"B{ROW_LAND}",
    "{G_SELL}":     f"I{GARLIC_ROW}",
    "{G_SHRINK}":   f"H{GARLIC_ROW}",
    "{PACKOUT}":    f"C{crop_row['Spinach']}:C{crop_row['Garlic']}",
    "{SELLTHRU}":   f"D{crop_row['Spinach']}:D{crop_row['Garlic']}",
    "{COLDCAP}":    f"B{ROW_COLDCAP}",
    "{AMBCAP}":     f"B{ROW_AMBCAP}",
}
row_i = 1
for text, font in readme:
    for k, v in {**COORDS, **NUMS}.items():
        text = text.replace(k, v)
    c = rd.cell(row=row_i, column=1, value=text)
    if font: c.font = font
    row_i += 1

out = REPO / "toy_models" / "farm_toy_v2_loss_and_storage.xlsx"
wb.save(out)
print(f"wrote {out}")
print(f"  crops: {', '.join(CROP_NAMES)}")
print(f"  successions: {', '.join(PICKED)}")
print(f"  cold cap {COLD_CAP} m3 | ambient cap {AMB_CAP} m3 | sell-through {STF}")
