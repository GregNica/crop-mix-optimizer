"""
build_toy_v10.py — generates the LABOUR-BY-POSITION toy model workbook (a MILP).

v5 closes the two gaps the grower found in v4, both of which were DECISION VARIABLES rather
than cost lines:

  1. IT CHOOSES WHEN TO PLANT. Every succession the app's calendar generator offers is on the
     sheet — 68 for these three crops, one per legal start week — and the solver allocates
     acres across all of them. Zero acres IS the decision not to plant that week. v4 offered
     five, hand-picked, and that single restriction was worth 128% of profit.
  2. IT CHOOSES WHETHER TO PLANT AT ALL. A binary per succession, tied to acres by the app's
     own C9 and C10, so anything planted meets its minimum acreage. That makes this a MILP,
     which is what `farm_v2/solver.py` is — its `integrality` array marks the same y block.

⚠️ NEEDS LIBREOFFICE CALC, and this one is a real MILP: 68 acres + 68 binaries + 312 offered
+ 104 bought hours = 552 decision cells. Engine must be CoinMP (it handles integers; the plain linear solver does
not do branch and bound well).

STRUCTURAL CHANGE FROM v4, and it is what makes 68 successions readable: the planting calendar
is ONE row per succession carrying its acres, its binary and its phase pattern, and the
per-crop harvest is a SUMPRODUCT across that table rather than a stack of per-succession rows.
136 rows of calendar became 68.

Week columns therefore start at E, not C — columns C and D hold the two decision cells that
belong to each succession.
"""
import json
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

from farm_v2.utils.calendar import harvest_weeks_of
import toy_v10_lp as LP

CROP_NAMES = LP.CROP_NAMES
crops = LP.CROPS
CH_NAMES = LP.CH_NAMES
SUCCS = LP.SUCCS

# ⚠️ ONE definition. This count was written out longhand in three places and every one of them
# still said 448 after v8 added 104 flex cells — the sheet's own description of itself was wrong
# in the docstring, the READ ME and the build banner at once. Derive it, do not retype it.
N_OFFER_CELLS = len(CROP_NAMES) * len(CH_NAMES) * 52
# v9: 52 spot-hire cells became ONE advisory headcount, so the model got smaller.
N_FLEX_CELLS = 52 + 1  # overtime hours (52 weeks) + the advisory crew size (one integer)
N_DEC_CELLS = len(SUCCS) * 2 + N_OFFER_CELLS + N_FLEX_CELLS
DEC_BREAKDOWN = (f"{len(SUCCS)} acres + {len(SUCCS)} binaries + {N_OFFER_CELLS} offered "
                 f"+ 52 overtime + 1 proposed-hire headcount")
PACK_OUT = 1.00
COLD_CAP = LP.PAYLOAD["harvest_storage_cap"]
AMB_CAP = LP.PAYLOAD["ambient_storage_cap"]
TOTAL_LAND = LP.PAYLOAD["total_land"]

W0 = 5                                   # week 1 lives in column E
wcol = lambda w: W0 + w - 1
wl = lambda w: get_column_letter(wcol(w))
LAST = get_column_letter(wcol(52))
C_MAXA = get_column_letter(wcol(52) + 1)   # helper: max acres if planted
C_MINA = get_column_letter(wcol(52) + 2)   # helper: min acres if planted
C_START = get_column_letter(wcol(52) + 3)  # helper: the week seed is paid

# ---------------------------------------------------------------------------
# THE PALETTE IS SEMANTIC (v9, at the grower's request). FOUR colours, one
# meaning each, and everything structural is GREY.
#
# v8 had nine fills and they were keyed to SUBJECT — cold pool blue, ambient
# orange, channel green and pink, annual-cap orange, binaries blue. So colour
# told you what a row was ABOUT and never what it was FOR, and the two things
# a reader most needs to find — what may I change, and what is the answer —
# had no colour of their own. A reader could not tell a decision cell from a
# storage pool at a glance, which is the whole job of colour on a sheet this
# size.
#
#   YELLOW  an INPUT      — you type here, and nothing else on the sheet does
#   GREEN   a DECISION    — the solver writes here (acres, binaries, offered
#                           pounds, overtime hours, the advisory crew)
#   RED     a CONSTRAINT  — a limit, and the room left under it
#   PURPLE  the OBJECTIVE — the one cell being maximised
#   GREY    everything else: headers, bands, section rules
#
# ⚠️ Binaries share the DECISION green rather than keeping their own blue.
# They are a different KIND of decision, not a different kind of cell, and the
# label and number format already say which they are.
# ---------------------------------------------------------------------------
F_TITLE = Font(bold=True, size=15)
F_H1 = Font(bold=True, size=12, color="404040")
F_BOLD = Font(bold=True)
F_NOTE = Font(italic=True, size=9, color="666666")
F_SMALL = Font(size=9)
F_KEY = Font(bold=True, size=9, color="404040")

IN_FILL = PatternFill("solid", fgColor="FFF2CC")    # INPUT
DEC_FILL = PatternFill("solid", fgColor="D9EAD3")   # DECISION
CON_FILL = PatternFill("solid", fgColor="F4CCCC")   # CONSTRAINT
OBJ_FILL = PatternFill("solid", fgColor="D9D2E9")   # OBJECTIVE

# Grayscale for everything structural. Three steps is enough to separate a
# section header from a sub-band from an ordinary row.
HDR_FILL = PatternFill("solid", fgColor="D9D9D9")
SUB_FILL = PatternFill("solid", fgColor="EFEFEF")
CAL_FILL = PatternFill("solid", fgColor="F2F2F2")   # the calendar's P/G/H phase markers
BAND_FILL = PatternFill("solid", fgColor="F7F7F7")
# ⚠️ FOUR GREYS AND FOUR COLOURS, ALL NAMED HERE. CAL_FILL was an inline PatternFill literal
# at its one call site — grey, so it honoured the rule, but a colour defined away from the
# palette is a colour that drifts out of it. `tests/test_toy_model.py` asserts that every
# solid fill in the workbook is one of these eight.

# The subject-keyed fills all collapse to grey. Kept as names so the call sites
# do not have to change shape, and so a future reader can see they were retired
# on purpose rather than lost.
POOL_C = BAND_FILL
POOL_A = SUB_FILL
CH_FILL = [BAND_FILL, SUB_FILL]
ANNUAL_FILL = SUB_FILL
BIN_FILL = DEC_FILL
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

wb = Workbook()
rd = wb.active
rd.title = "READ ME"
rd.column_dimensions["A"].width = 112
ws = wb.create_sheet("Model")
ws.column_dimensions["A"].width = 30
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 8
ws.column_dimensions["D"].width = 6
for w in range(1, 53):
    ws.column_dimensions[wl(w)].width = 7.5
for c in (C_MAXA, C_MINA, C_START):
    ws.column_dimensions[c].width = 11


def put(r, c, v, font=None, fill=None, fmt=None, align=None, border=False):
    cell = ws.cell(row=r, column=c, value=v)
    if font: cell.font = font
    if fill: cell.fill = fill
    if fmt: cell.number_format = fmt
    if align: cell.alignment = Alignment(horizontal=align)
    if border: cell.border = BOX
    return cell


def week_header(r, note=""):
    put(r, 1, "Week", font=F_BOLD, fill=HDR_FILL)
    put(r, 2, note, font=F_NOTE, fill=HDR_FILL)
    for w in range(1, 53):
        put(r, wcol(w), w, font=F_BOLD, fill=HDR_FILL, align="center")
    return r + 1


def constraint_triplet(r, label, lhs, cap_ref, fill, note, fmt="0.0"):
    """cap_ref may be a fixed cell ("$B$5") or a callable w -> reference.

    Labour is the first limit on this sheet that VARIES BY WEEK — the crew changes size as the
    seasonal crews come and go — so a single capacity cell cannot express it.
    """
    _cap = cap_ref if callable(cap_ref) else (lambda w: cap_ref)
    # v9: `fill` is ignored — a constraint block is RED because it is a constraint, not
    # tinted by its subject. The parameter stays in the signature so the twelve call sites
    # keep their shape and a reader can see the colour decision moved here, deliberately.
    put(r, 1, label, font=F_BOLD, fill=CON_FILL); put(r, 2, "used", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), lhs(w), fmt=fmt, fill=CON_FILL)
    used = r; r += 1
    put(r, 1, "", font=F_BOLD)
    for w in range(1, 53):
        put(r, wcol(w), "<=", align="center", font=F_BOLD)
    r += 1
    put(r, 1, "  limit", font=F_BOLD, fill=CON_FILL); put(r, 2, "cap", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={_cap(w)}", fmt=fmt, fill=CON_FILL)
    r += 1
    put(r, 1, "  room left", font=F_SMALL, fill=CON_FILL)
    for w in range(1, 53):
        put(r, wcol(w), f"={_cap(w)}-{wl(w)}{used}", fmt=fmt, fill=CON_FILL)
    head = r; r += 1
    put(r, 1, note, font=F_NOTE); r += 2
    for rng, op, f in ((head, "lessThan", ["0"]), (used, "greaterThan", [_cap(1)])):
        ws.conditional_formatting.add(f"{wl(1)}{rng}:{LAST}{rng}", CellIsRule(
            operator=op, formula=f, fill=PatternFill("solid", fgColor="FFC7CE"),
            font=Font(color="9C0006", bold=True)))
    return r, used, head


# A BUILD STAMP, because the filename never changes and there has been no way to tell one
# rebuild from the next. Three separate rounds were spent on a defect that was already fixed on
# disk while an older copy sat open. Cheap, and it ends that class of confusion.
import subprocess as _sp, datetime as _dt
try:
    _SHA = _sp.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                   capture_output=True, text=True).stdout.strip() or "unknown"
except Exception:
    _SHA = "unknown"
_BUILT = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

r = 1
put(r, 1, "FARM TOY MODEL — v10: labour by position", font=F_TITLE)
put(r, 4, f"BUILT {_BUILT}   (from source at {_SHA})", font=F_NOTE)
r += 1
# The legend is COLOURED, not described. A key that names a colour in grey text
# is a key you have to translate; this one you can hold against the sheet.
put(r, 1, "KEY:", font=F_BOLD)
for j, (lab, fill) in enumerate((("INPUT — you type here", IN_FILL),
                                 ("DECISION — the solver writes here", DEC_FILL),
                                 ("CONSTRAINT — a limit and its room left", CON_FILL),
                                 ("OBJECTIVE — the cell being maximised", OBJ_FILL))):
    put(r, 2 + j * 4, lab, font=F_KEY, fill=fill, border=True)
r += 1
put(r, 1, "Everything else is grey. Read the 'READ ME' sheet first.", font=F_NOTE); r += 2

# --- 1. farm ---
put(r, 1, "1 — THE FARM", font=F_H1); r += 1
put(r, 1, "Land you have", font=F_BOLD)
put(r, 2, TOTAL_LAND, fill=IN_FILL, fmt="0.0", border=True); ROW_LAND = r
put(r, 3, "acres", font=F_NOTE); r += 1
put(r, 1, "Cold store (cooler)", font=F_BOLD)
put(r, 2, COLD_CAP, fill=IN_FILL, fmt="#,##0", border=True); ROW_COLDCAP = r
put(r, 3, "m3 — Spinach, Kale", font=F_NOTE); r += 1
put(r, 1, "Ambient store (barn)", font=F_BOLD)
put(r, 2, AMB_CAP, fill=IN_FILL, fmt="#,##0", border=True); ROW_AMBCAP = r
put(r, 3, "m3 — Garlic", font=F_NOTE); r += 2

# --- 2. crops ---
put(r, 1, "2 — HOW EACH CROP BEHAVES", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Yield lb/acre", "Pack-out", "m3 per lb", "Store", "Shelf life wk",
                       "Shrink %/wk", "Seed $/acre", "Min acres if planted", "Harvest weeks",
                       "$/ac plant wk", "$/ac grow wk", "$/ac harvest wk",
                       "hrs/ac plant", "hrs/ac grow", "hrs/ac harvest"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_CROP = r
crop_row = {}
for name in CROP_NAMES:
    c = crops[name]
    pool = "Cold" if c.get("cold_storage", True) else "Ambient"
    put(r, 1, name, border=True)
    put(r, 2, c["yield_per_acre"], fill=IN_FILL, fmt="#,##0", border=True)
    put(r, 3, PACK_OUT, fill=IN_FILL, fmt="0.00", border=True)
    put(r, 4, c["crop_size_m3_per_lb"], fill=IN_FILL, fmt="0.0000000", border=True)
    put(r, 5, pool, border=True, fill=POOL_C if pool == "Cold" else POOL_A)
    put(r, 6, c.get("shelf_life_weeks", c.get("sales_spread_weeks", 1)), fill=IN_FILL, border=True)
    put(r, 7, 0.0, fill=IN_FILL, fmt="0.0%", border=True)
    put(r, 8, c["seed_transplant_cost_per_acre"], fill=IN_FILL, fmt="$#,##0", border=True)
    put(r, 9, c.get("min_acreage_if_planted", 0.0), fill=IN_FILL, fmt="0.0", border=True)
    # Every succession of a crop harvests over the same number of weeks on this data, so
    # lb-per-harvest-week is a per-CROP scalar and the old 68-row helper column was carrying no
    # information. ASSERTED rather than assumed: a crop whose successions differ (a wrapped
    # calendar truncating a harvest window, say) fails the build instead of silently averaging.
    _nh = {max(1, len(harvest_weeks_of(x, 52))) for x in SUCCS if CROP_NAMES[x["crop"]] == name}
    assert len(_nh) == 1, (
        f"{name}: successions harvest over {sorted(_nh)} different week-counts, so lb/harvest-week "
        f"is NOT a per-crop scalar — restore the per-succession helper column")
    # Filled in a SECOND PASS below, once the calendar rows exist — the same lesson the ceiling
    # row taught: do not address a row you have not placed yet. (Written here first, it raised
    # NameError on ROW_SUCC and the build quietly left the previous file in place.)
    put(r, 10, 0, fmt="0", border=True)
    # Fertiliser and fuel, per acre for each week the crop is in that phase — the app's own
    # rates x its own prices. This is what makes cash TIMING honest: a grow week and a harvest
    # week cost different amounts, and they fall in different weeks.
    # ⚠️ WATER IS ABSENT ON PURPOSE. The app prices on-farm water at $0 (backlog W10), so
    # inventing a price here would make the toy disagree with the thing it exists to check.
    _fert, _fuel = LP.PAYLOAD["cost_fert_per_lb"], LP.PAYLOAD["cost_fuel_per_L"]
    for _j, _ph in enumerate(("plant", "grow", "harv")):
        # FULL precision stored, two decimals DISPLAYED. Rounding the stored value to cents
        # put the sheet $2.38 away from the LP on a $1.65M objective — small, but it is the
        # difference between "these are the same model" and "these are nearly the same model",
        # and section E is the check that distinguishes them.
        put(r, 11 + _j, c.get(f"fert_{_ph}", 0.0) * _fert + c.get(f"fuel_{_ph}", 0.0) * _fuel,
            fill=IN_FILL, fmt="$0.00", border=True)
        # ⚠️ LABOUR HOURS ARE INPUTS, not literals inside the C2 formula. They were baked in as
        # `*2`, `*4`, `*50` — numbers the sheet used and could not show, so no one could see WHY
        # spinach crowds the crew (50 h/acre to pick, against kale's 22) or change it to find out.
        # Same class as the shelf-life box that read nothing.
        put(r, 14 + _j, c.get(f"labor_{_ph}", 0.0), fill=IN_FILL, fmt="0.0", border=True)
    crop_row[name] = r; r += 1
put(r, 1, "'Min acres if planted' is what the plant/don't-plant switch enforces — see section 4.",
    font=F_NOTE); r += 2

# --- 3. crop x channel ---
put(r, 1, "3 — WHO BUYS IT   (one row per crop x channel — the grower's ruling)", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Channel", "Cap type", "Cap lb", "From wk", "To wk",
                       "Sell-through", "Returns to store", "Price $/lb",
                       "Packaging $/lb"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_PAIR = r
pair_row = {}
for cname in CROP_NAMES:
    for hi, hname in enumerate(CH_NAMES):
        ctype, cval, w0, w1 = LP.cap_spec(cname, hname)
        st, ret = LP.defaults(cname, hname)
        put(r, 1, cname, border=True)
        put(r, 2, hname, border=True, fill=CH_FILL[hi])
        put(r, 3, ctype, fill=IN_FILL, border=True)
        put(r, 4, cval, fill=IN_FILL, fmt="#,##0", border=True)
        put(r, 5, w0, fill=IN_FILL, border=True)
        put(r, 6, w1, fill=IN_FILL, border=True)
        put(r, 7, st, fill=IN_FILL, fmt="0.00", border=True)
        put(r, 8, ret, fill=IN_FILL, fmt="0.00", border=True)
        put(r, 9, crops[cname].get("channels", {}).get(hname, {}).get("price_per_lb", 0.0),
            fill=IN_FILL, fmt="$0.00", border=True)
        # Packaging is charged per pound SOLD, not per acre — so it lands in the week of sale,
        # which is why it belongs on this row and not in the crop table.
        put(r, 10, crops[cname].get("channels", {}).get(hname, {})
            .get("packaging_cost_per_lb", 0.0), fill=IN_FILL, fmt="$0.00", border=True)
        pair_row[(cname, hname)] = r; r += 1
r += 1

# --- 3b. the crew ---
put(r, 1, "3b — THE CREW", font=F_H1); r += 1
for j, h in enumerate(["Position", "Count", "Type", "Wage", "Hours/wk", "Field time %",
                       "From wk", "To wk"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_CREW = r
for e in LP.PAYLOAD.get("employees", []):
    put(r, 1, e["position"], border=True)
    put(r, 2, e["count"], fill=IN_FILL, fmt="0", border=True)
    put(r, 3, e["type"], border=True)
    put(r, 4, e["wage"], fill=IN_FILL, fmt="$#,##0", border=True)
    put(r, 5, e["hours_per_week"], fill=IN_FILL, fmt="0", border=True)
    put(r, 6, e.get("field_time_pct", 100), fill=IN_FILL, fmt="0", border=True)
    put(r, 7, e.get("start_week", 1), fill=IN_FILL, fmt="0", border=True)
    put(r, 8, e.get("end_week", 52), fill=IN_FILL, fmt="0", border=True)
    r += 1
ROW_CREW_END = r - 1
put(r, 1, "Payroll load %", font=F_BOLD)
put(r, 2, LP.PAYLOAD.get("payroll_load_pct", 0.0), fill=IN_FILL, fmt="0%", border=True)
ROW_LOAD = r
put(r, 3, "employer taxes, workers' comp, benefits — applied to EVERY wage, salaried included",
    font=F_NOTE); r += 1
put(r, 1, "Overtime multiplier", font=F_BOLD)
put(r, 2, 1.5, fill=IN_FILL, fmt="0.00", border=True); ROW_OTMULT = r
put(r, 3, "your own crew staying late, on top of their blended hourly rate", font=F_NOTE); r += 1
put(r, 1, "Overtime ALLOWANCE", font=F_BOLD)
put(r, 2, 1.25, fill=IN_FILL, fmt="0.00", border=True); ROW_OTALLOW = r
put(r, 3, "1.25 = 'I will let people work 125% of normal hours'. ⚠️ v9 REPLACED a typed "
          "hours cap with this. The cap is now DERIVED per week — see the Overtime cap row.",
    font=F_NOTE); r += 1
put(r, 1, "   v8 typed a flat 200 hrs/week here. On the app's own farm that let 15 of 52 weeks "
          "buy MORE overtime than the whole crew's regular hours (185% in winter), and the app's "
          "solver took it: 191 overtime hours against 299 crew hours in one week.",
    font=F_NOTE); r += 1
put(r, 1, "   No flat number can express the rule, because the crew swings 108 to 908 hrs/wk "
          "across the year. That is why it is an allowance and not an amount.", font=F_NOTE)
r += 2

# ---- THE ADVISORY CREW (L1). Not a spot purchase — a roster row you have not hired yet. ----
put(r, 1, "3c — PROPOSED HIRE  (\"what should I take on, and when?\")", font=F_H1); r += 1
put(r, 1, "   You nominate the WINDOW; the solver picks the HEADCOUNT. The answer is a roster "
          "row you can type into 3b above and re-solve.", font=F_NOTE); r += 1
put(r, 1, "   ⚠️ CHARGED FOR THE WHOLE WINDOW, used or not. That is what makes it a hire and "
          "not a spot purchase, and it is the same treatment the standing crew gets (W12).",
    font=F_NOTE); r += 1
put(r, 1, "   Real hiring is a committed block: H-2A wants 60-75 days of lead and guarantees "
          "the worker 3/4 of the contract's hours; domestic seasonal wants 8-10 weeks.",
    font=F_NOTE); r += 1
for j, h in enumerate(["From wk", "To wk", "Hours/wk each", "Field time %", "Wage $/hr",
                       "Max people available", "Productivity %", "$ per head"]):
    put(r, 2 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
put(r, 1, "Proposed hire", font=F_BOLD)
put(r, 2, 43, fill=IN_FILL, fmt="0", border=True);      ADV_START = f"$B${r}"
put(r, 3, 49, fill=IN_FILL, fmt="0", border=True);      ADV_END = f"$C${r}"
put(r, 4, 40, fill=IN_FILL, fmt="0", border=True);      ADV_HRS = f"$D${r}"
put(r, 5, 100, fill=IN_FILL, fmt="0", border=True);     ADV_FIELD = f"$E${r}"
put(r, 6, 20.0, fill=IN_FILL, fmt="$0.00", border=True); ADV_WAGE = f"$F${r}"
put(r, 7, 20, fill=IN_FILL, fmt="0", border=True);      ADV_MAX = f"$G${r}"
put(r, 8, 70, fill=IN_FILL, fmt="0", border=True);      ADV_PROD = f"$H${r}"
put(r, 9, 800, fill=IN_FILL, fmt="$#,##0", border=True); ADV_HEAD = f"$I${r}"
r += 1
put(r, 1, "   ⚠️ PRODUCTIVITY % and $ PER HEAD are new, and without them the hire was "
          "unbeatable: $25.00/hr all-in against overtime at $37.84-48.75, so the solver took "
          "18 of the 20 heads on offer.", font=F_NOTE); r += 1
put(r, 1, "   A green seasonal picker is not as fast as your harvest crew. At 70% you pay for "
          "40 hours and get 28 hours of trained-crew work — an effective $35.71/hr, which is a "
          "real contest with overtime. The two meet at about 65%.", font=F_NOTE); r += 1
put(r, 1, "   $ per head is recruitment, onboarding and transport: paid per PERSON, once, not "
          "per hour. It is what makes 18 casual hires cost more than 4 regardless of hours — "
          "and why H-2A, at ~$10,000/worker of non-wage cost, is not an 80-acre instrument.",
    font=F_NOTE); r += 1
put(r, 1, "PEOPLE TO HIRE", font=F_BOLD, fill=DEC_FILL)
put(r, 2, 0, fill=DEC_FILL, fmt="0", border=True); ROW_ADVCREW = r; ADV_CREW = f"$B${r}"
put(r, 3, "<-- SOLVER (whole people, an INTEGER — 'hire 7.3 people' is not an instruction)",
    font=F_NOTE); r += 1
put(r, 1, "Cost per person per week", font=F_SMALL)  # noqa: E501
put(r, 2, f"={ADV_HRS}*{ADV_WAGE}*(1+$B${ROW_LOAD})", fmt="$#,##0", border=True)
ROW_ADVCOSTWK = r; r += 1
put(r, 1, "Weeks in the window", font=F_SMALL)
put(r, 2, f"={ADV_END}-{ADV_START}+1", fmt="0", border=True); ROW_ADVWKS = r; r += 1
put(r, 1, "TOTAL committed cost", font=F_BOLD)
put(r, 2, f"={ADV_CREW}*($B${ROW_ADVCOSTWK}*$B${ROW_ADVWKS}+{ADV_HEAD})",
    fmt="$#,##0", border=True)
r += 1
put(r, 1, "   Weekly wage for every week of the window, plus $ per head once.", font=F_NOTE)
r += 1
# ⚠️ THE AVAILABILITY BOUND EARNS A "ROOM LEFT" ROW, like every other limit on this sheet.
# I wrote it as a Solver-recipe-only bound first and the dead-input guard caught it — which is
# EXACTLY the defect v8 recorded and fixed ("Max overtime hrs/week is read by no formula"), and
# I recreated it one version later. A cap named only in the recipe is invisible to a reader and
# invisible to the guard, and the tempting fix is to loosen the guard. That is a test bent
# around a builder shortcut. Fix the builder.
put(r, 1, "Room left to hire", font=F_SMALL, fill=CON_FILL)
put(r, 2, f"={ADV_MAX}-{ADV_CREW}", fmt="0", border=True, fill=CON_FILL)
put(r, 3, "how many more hands you said you could find — the availability question the research "
          "says is the real uncertainty", font=F_NOTE)
r += 1
put(r, 1, "   ⚠️ The window is YOUR call and it matters more than the headcount. Measured on "
          "this farm: hiring into weeks 16-21, where C2 binds for six weeks straight, is worth "
          "$5. Weeks 43-49 are worth $58,253.", font=F_NOTE); r += 1
put(r, 1, "   A week where labour BINDS is not the same as a week where more labour PAYS, and "
          "reading the binding weeks off the sheet would send you to the wrong one.",
    font=F_NOTE); r += 2
put(r, 1, "A salary wage is $/YEAR; hourly and seasonal are $/HOUR. 'Field time %' is the share "
          "of paid hours available to the crops —", font=F_NOTE); r += 1
put(r, 1, "the rest is admin and maintenance. It reduces CAPACITY without reducing the WAGE.",
    font=F_NOTE); r += 2

# --- 4. the planting calendar: EVERY succession the app offers ---
put(r, 1, f"4 — THE PLANTING CALENDAR   ({len(SUCCS)} possible plantings — the solver picks)",
    font=F_H1); r += 1
put(r, 1, "One row per legal start week, exactly what the app's generator offers. ACRES and PLANT? "
          "are both decisions.", font=F_NOTE); r += 1
put(r, 1, "Succession", font=F_BOLD, fill=HDR_FILL)
put(r, 2, "Crop", font=F_BOLD, fill=HDR_FILL)
put(r, 3, "ACRES", font=F_BOLD, fill=DEC_FILL)
put(r, 4, "PLANT?", font=F_BOLD, fill=BIN_FILL)
for w in range(1, 53):
    put(r, wcol(w), w, font=F_BOLD, fill=HDR_FILL, align="center")
put(r, wcol(52) + 1, "max if planted", font=F_SMALL, fill=HDR_FILL)
put(r, wcol(52) + 2, "min if planted", font=F_SMALL, fill=HDR_FILL)
put(r, wcol(52) + 3, "starts wk", font=F_SMALL, fill=HDR_FILL)
ROW_SUCC_HDR = r; r += 1
ROW_SUCC = r
PH = {0: "P", 1: "G", 2: "H"}
succ_rows = {}
for s in SUCCS:
    cn = CROP_NAMES[s["crop"]]
    nharv = max(1, len(harvest_weeks_of(s, 52)))
    put(r, 1, s["name"], font=F_SMALL)
    put(r, 2, cn, font=F_SMALL)
    put(r, 3, 0.0, fill=DEC_FILL, fmt="0.00")          # DECISION: acres
    put(r, 4, 0, fill=BIN_FILL, fmt="0")               # DECISION: plant? (binary)
    pbw = {((wk - 1) % 52) + 1: ph for wk, ph in zip(s["weeks"], s["phases"])}
    for w in range(1, 53):
        if w in pbw:
            put(r, wcol(w), PH[pbw[w]], align="center", font=F_SMALL, fill=CAL_FILL)
    # C9 / C10 helpers — the plant/don't-plant linkage, as columns the Solver can constrain
    put(r, wcol(52) + 1, f"=D{r}*$B${ROW_LAND}", fmt="0.0", font=F_SMALL)
    put(r, wcol(52) + 2, f"=D{r}*$I${crop_row[cn]}", fmt="0.0", font=F_SMALL)
    # The week seed is paid for. Genuinely per-succession — unlike the lb/harvest-week column
    # v5 retired, this differs from row to row and no per-crop scalar can carry it.
    put(r, wcol(52) + 3, f'=MATCH("P",${wl(1)}{r}:${LAST}{r},0)', fmt="0", font=F_SMALL)
    succ_rows[s["name"]] = r; r += 1
ROW_SUCC_END = r - 1

# SECOND PASS — "Harvest weeks" as a FORMULA counting the H's on each crop's first planting,
# rather than a number the generator knows and the sheet cannot show. It follows the calendar if
# that changes, and it is not a bare constant sitting among the inputs. Sampling ONE planting is
# exactly the uniformity asserted above.
for _n in CROP_NAMES:
    _first = succ_rows[next(x["name"] for x in SUCCS if CROP_NAMES[x["crop"]] == _n)]
    put(crop_row[_n], 10, f'=COUNTIF(${wl(1)}${_first}:${LAST}${_first},"H")', fmt="0",
        border=True)

put(r, 1, "ACRES <= 'max if planted' and ACRES >= 'min if planted' are the app's C9 and C10: you "
          "cannot plant acres without deciding to plant, and if you plant at all you plant a real "
          "block.", font=F_NOTE); r += 2

SR = f"$C${ROW_SUCC}:$C${ROW_SUCC_END}"          # acres column
CROPCOL = f"$B${ROW_SUCC}:$B${ROW_SUCC_END}"     # crop name column

# --- 5. land, then per crop ---
r = week_header(r, "acres")
land_lhs = lambda w: (f"=SUMPRODUCT(({wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}<>\"\")*{SR})")
r, ROW_LANDUSED, _ = constraint_triplet(
    r, "LAND in the ground", land_lhs, f"$B${ROW_LAND}", None,
    "   Acres standing that week, summed across every planting the solver chose.")

# ---------------------------------------------------------------------------
# LABOUR (v10, rebuilt again on the grower's notes).
#
# TWO CHANGES FROM v9, both his:
#
# 1. SPLIT BY POSITION instead of blending inside a mask. v9 answered "how many
#    hours this week" with a five-factor SUMPRODUCT — (on this week) x (not
#    salary) x (paid) x count x hours — recomputed inside every row that needed
#    it. Here each position gets its own row of plain
#    `IF(in window, count x hours x field%, 0)`, the aggregates are SUMs of
#    named rows, and the overtime blend is a ratio of rows already on the sheet.
#    The mask is gone. The position rows are also the labour calendar (D9).
#
# 2. TOP-TO-BOTTOM FLOW, like the crop blocks. v9 went capacity -> prices ->
#    cap -> decisions -> available -> costs -> constraints, so money appeared
#    twice, split around the middle, and the limits trailed after the costs.
#    Now: A who is on -> B what you can add -> C the limits -> D what it costs.
#    Every row still reads only rows above it.
# ---------------------------------------------------------------------------
put(r, 1, "A — WHO IS ON, WEEK BY WEEK", font=F_H1); r += 1
put(r, 1, "   One row per position. Field hours = count x hours/wk x field time %, inside that "
          "position's own window.", font=F_NOTE); r += 1
r = week_header(r, "hours")
# The window test is written ONCE. Block A (hours) and block D (cost) both need "is this
# position on in week w", and two copies of a predicate is how they drift apart.
_on_wk = lambda i_, w_: f"AND({w_}>=$G${i_},{w_}<=$H${i_})"
POS_ROWS = []
for _i in range(ROW_CREW, ROW_CREW_END + 1):
    _nm = ws.cell(row=_i, column=1).value
    _hourly = ws.cell(row=_i, column=3).value != "salary" and (ws.cell(row=_i, column=4).value or 0) > 0
    put(r, 1, f"   {_nm}", font=F_SMALL)
    put(r, 2, "hrs" + ("" if _hourly else "  (salaried)"), font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w),
            f"=IF({_on_wk(_i, w)},$B${_i}*$E${_i}*$F${_i}/100,0)", fmt="#,##0")
    POS_ROWS.append((r, _i, _hourly))
    r += 1

put(r, 1, "CREW CAPACITY", font=F_BOLD); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w),
        "=" + "+".join(f"{wl(w)}{pr}" for pr, _, _ in POS_ROWS), fmt="#,##0")
ROW_LABCAP = r; r += 1
put(r, 1, "   The sum of the rows above. No mask, no SUMPRODUCT — you can add them up by eye.",
    font=F_NOTE); r += 1

_HOURLY_ROWS = [pr for pr, _, h in POS_ROWS if h]
put(r, 1, "Hourly field hours", font=F_SMALL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{pr}" for pr in _HOURLY_ROWS), fmt="#,##0")
ROW_HFIELD = r; r += 1
put(r, 1, "   Only the HOURLY rows. Salaried staff give capacity but cannot be paid overtime, "
          "so they are in CREW CAPACITY and out of this one — and out of everything derived "
          "from it.", font=F_NOTE); r += 2

put(r, 1, "B — WHAT YOU CAN ADD", font=F_H1); r += 1
r = week_header(r, "hours")
put(r, 1, "Overtime CAP", font=F_SMALL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    # ⚠️ DERIVED, not typed. v8 broadcast one flat number across 52 weeks while the crew is
    # seasonal; on the app's own farm that let 15 of 52 weeks buy MORE overtime than the whole
    # crew's regular hours (185% in winter) and the solver took it.
    put(r, wcol(w), f"=MAX(0,$B${ROW_OTALLOW}-1)*{wl(w)}{ROW_HFIELD}", fmt="#,##0")
ROW_OTCAP = r; r += 1
put(r, 1, "   (allowance - 1) x the hourly row above. ZERO in a week with no hourly crew — you "
          "cannot work overtime on people who are not there.", font=F_NOTE); r += 1

put(r, 1, "OVERTIME hours", font=F_BOLD, fill=DEC_FILL); put(r, 2, "hrs <-- SOLVER", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), 0.0, fmt="#,##0", fill=DEC_FILL)
ROW_OTHRS = r; r += 1

put(r, 1, "Proposed hire hours", font=F_SMALL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    # ⚠️ x PRODUCTIVITY. A green seasonal picker is not as fast as your harvest crew, and until
    # v10 a bought hour was worth exactly as much crop work as a trained one — which made the
    # hire unbeatable at $25.00/hr all-in against overtime at $37.84-48.75, so the solver took
    # every head on offer (18 of 20). It multiplies the HOURS, not the wage: you pay for the
    # hours you booked and get less crop work out of them.
    put(r, wcol(w),
        f"=IF(AND({w}>={ADV_START},{w}<={ADV_END}),"
        f"{ADV_CREW}*{ADV_HRS}*{ADV_FIELD}/100*{ADV_PROD}/100,0)", fmt="#,##0")
ROW_ADVHRS = r; r += 1

put(r, 1, "HOURS AVAILABLE", font=F_BOLD); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w),
        f"={wl(w)}{ROW_LABCAP}+{wl(w)}{ROW_OTHRS}+{wl(w)}{ROW_ADVHRS}", fmt="#,##0")
ROW_HOURSAVAIL = r; r += 1
put(r, 1, "   Crew capacity, plus overtime, plus whatever the proposed hire really delivers.",
    font=F_NOTE); r += 2

put(r, 1, "C — THE LIMITS", font=F_H1); r += 1
r = week_header(r, "hours")
lab_lhs = lambda w: "=" + "+".join(
    f'SUMPRODUCT(({CROPCOL}="{n}")*({wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}="{ph}")*{SR})'
    f'*${cl}${crop_row[n]}'
    for n in CROP_NAMES for ph, cl in (("P", "N"), ("G", "O"), ("H", "P")))
r, ROW_LABUSED, _ = constraint_triplet(
    r, "CROP HOURS needed", lab_lhs, lambda w: f"{wl(w)}${ROW_HOURSAVAIL}", None,
    "   The app's C2. On this farm it is the constraint that binds hardest — in 8 separate "
    "blocks of weeks.", fmt="#,##0")
r, ROW_OTUSED, _ = constraint_triplet(
    r, "OVERTIME bought", lambda w: f"={wl(w)}{ROW_OTHRS}",
    lambda w: f"{wl(w)}${ROW_OTCAP}", None,
    "   The limit MOVES WITH THE CREW. No flat number could: the hourly crew runs 72 to 872 "
    "field hours across the year.", fmt="#,##0")

put(r, 1, "D — WHAT IT COSTS", font=F_H1); r += 1
put(r, 1, "   Nothing above this line is money. Nothing below it is a limit.", font=F_NOTE); r += 1
r = week_header(r, "$")
COST_ROWS = []
for _pr, _i, _hourly in POS_ROWS:
    _nm = ws.cell(row=_i, column=1).value
    put(r, 1, f"   {_nm}", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
    for w in range(1, 53):
        # ⚠️ Salary is $/YEAR over 52; hourly is wage x CONTRACTED hours. Field% reduces the
        # hours the CROPS get and not the hours the PAYSLIP covers, so it is absent here and
        # present in block A — that asymmetry is why both blocks exist.
        if ws.cell(row=_i, column=3).value == "salary":
            body = f"$B${_i}*$D${_i}/52*(1+$B${ROW_LOAD})"
        else:
            body = f"$B${_i}*$D${_i}*$E${_i}*(1+$B${ROW_LOAD})"
        put(r, wcol(w), f"=IF({_on_wk(_i, w)},{body},0)", fmt="#,##0")
    COST_ROWS.append(r); r += 1

put(r, 1, "Wage bill this week", font=F_BOLD); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{cr_}" for cr_ in COST_ROWS), fmt="#,##0")
ROW_WAGEWK = r; r += 1
put(r, 1, "   ⚠️ OWED WHETHER OR NOT THE CROPS NEED THEM (the app's W12). That is why no crop "
          "carries a per-acre labour charge anywhere on this sheet: the marginal crop hour is "
          "FREE, and it is rationed by block C instead of priced.", font=F_NOTE); r += 1

put(r, 1, "Overtime cost this week", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    # The blend is a RATIO OF ROWS ALREADY ON THE SHEET — hourly position rows against their
    # wages — computed where it is used instead of taking a 52-cell row of its own to display
    # three distinct values ($37.74, $39.04, $48.75). v9 spent a row on it and rebuilt the mask
    # to fill it.
    num = "+".join(f"{wl(w)}{pr}*$D${i_}" for pr, i_, h in POS_ROWS if h)
    den = "+".join(f"{wl(w)}{pr}" for pr, i_, h in POS_ROWS if h)
    put(r, wcol(w),
        f"=IFERROR({wl(w)}{ROW_OTHRS}*({num})/({den})*(1+$B${ROW_LOAD})*$B${ROW_OTMULT},0)",
        fmt="#,##0")
ROW_OTCOST = r; r += 1
put(r, 1, "   ⚠️ Overtime hours cost their FULL rate, not the premium above base pay. The wage "
          "bill pays the crew's STATED hours; these are hours beyond it, so charging only the "
          "increment leaves the base wage charged nowhere. Measured in the app at 2,080 hours "
          "costing $0.00.", font=F_NOTE); r += 1

put(r, 1, "Proposed hire cost this week", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    # Weekly wage every week of the window, PLUS the per-head cost once, in the first week —
    # recruitment and moving people happen before they pick anything.
    put(r, wcol(w),
        f"=IF(AND({w}>={ADV_START},{w}<={ADV_END}),{ADV_CREW}*$B${ROW_ADVCOSTWK},0)"
        f"+IF({w}={ADV_START},{ADV_CREW}*{ADV_HEAD},0)", fmt="#,##0")
ROW_ADVWAGE = r; r += 1
put(r, 1, "   ⚠️ CHARGED FOR THE WHOLE WINDOW, used or not — that is what makes it a hire and "
          "not a spot purchase, and it is the same treatment the standing crew gets. Compare "
          "this against 'Proposed hire hours' in a week the plan does not need them.",
    font=F_NOTE); r += 2

crop_block = {}
for name in CROP_NAMES:
    cr = crop_row[name]
    pool = "Cold" if crops[name].get("cold_storage", True) else "Ambient"
    put(r, 1, f"{name.upper()}  —  {pool.lower()} store", font=F_H1)
    put(r, 2, "", fill=POOL_C if pool == "Cold" else POOL_A); r += 1
    R_WK = r                      # the week-number strip this block's SUMIFS reads
    r = week_header(r)

    put(r, 1, "Packed out -> INTO the store", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        # One SUMPRODUCT across the whole calendar instead of a row per succession.
        # acres harvesting this week, times (yield / harvest weeks), times pack-out. The middle
        # term used to be a 68-row column multiplied elementwise; it is the same number on every
        # row of a crop, so it factors straight out of the SUMPRODUCT.
        put(r, wcol(w),
            f'=SUMPRODUCT(({CROPCOL}="{name}")*({wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}="H")'
            f'*{SR})*$B${cr}/$J${cr}*$C${cr}', fmt="#,##0")
    R_PACK = r; r += 1

    put(r, 1, "Stock carried in", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    R_OPEN = r; r += 1
    put(r, 1, "   lost to shrink", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_OPEN}*$G${cr}", fmt="#,##0")
    R_SHRINK = r; r += 1
    put(r, 1, "In store this week", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_OPEN}-{wl(w)}{R_SHRINK}+{wl(w)}{R_PACK}", fmt="#,##0")
    R_STORE = r; r += 1

    ch_rows, consumed_rows = {}, []
    for hi, hname in enumerate(CH_NAMES):
        pr = pair_row[(name, hname)]
        fill = CH_FILL[hi]
        # ONE label that is true for BOTH cap types. "weekly ceiling" was a lie on an annual
        # pair — and the 500,000 it displayed was NOT: under an annual cap there is no weekly
        # limit at all, so if you had 500,000 lb in store in week 1 you could indeed sell it
        # that week. The value was right and the heading was wrong, which is the harder version
        # of this defect to see.
        is_annual = ws.cell(row=pr, column=3).value == "Annual"
        # ⚠️ v10: RED. This is a real constraint (sold <= ceiling) and v9 painted it with the
        # channel's grey, so the sheet's most-used limit did not look like a limit. The palette
        # guard missed it because it was pinned to rows I already knew were right — the same
        # mistake as a test that only runs the default fixture.
        put(r, 1, f"{hname} — most you may sell this week", font=F_SMALL, fill=CON_FILL)
        put(r, 2, "lb", font=F_NOTE)
        R_CAP = r
        # ⚠️ FORMULAS FILLED IN A SECOND PASS, once R_SOLD is known. They used to be written
        # here against `R_CAP + 2`, guessing where SOLD would land — and then the annual note
        # rows were inserted between the two, so the guess pointed at a blank line, the running
        # allowance summed nothing, and the ceiling never declined. Inert for two commits while
        # looking right. Never address a row you have not placed yet.
        for w in range(1, 53):
            # WEEKLY pair: the stated figure, inside its season.
            # ANNUAL pair: what is LEFT of the year's allowance. Writing the whole annual figure
            # into every week (as this did) reads as a 500,000 lb/week ceiling under a heading
            # that says weekly, and pushes the real limit onto one separate constraint entry the
            # reader has to remember to add. A running allowance is truthful AND self-enforcing:
            #     sold[w] <= annual - sum(sold before w)   for every w
            # is exactly "the year's total <= annual", and it is linear — no MAX() needed,
            # because the constraint itself stops the remainder going negative.
            put(r, wcol(w), 0, fmt="#,##0", fill=CON_FILL)  # placeholder; filled below
        r += 1
        if is_annual:
            put(r, 1, f"   ^ {hname} is an ANNUAL cap ({int(ws.cell(row=pr, column=4).value):,} lb "
                      f"a year), so there is NO weekly limit —", font=F_NOTE); r += 1
            put(r, 1, "     this row is what is LEFT of the year, and it falls as you sell.",
                font=F_NOTE); r += 1
        put(r, 1, f"{hname} — OFFERED", font=F_BOLD, fill=DEC_FILL)
        put(r, 2, "lb  <-- SOLVER", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), 0.0, fmt="#,##0", fill=DEC_FILL)
        R_OFF = r; r += 1
        put(r, 1, f"{hname} — SOLD", font=F_BOLD, fill=fill); put(r, 2, "lb", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), f"={wl(w)}{R_OFF}*$G${pr}", fmt="#,##0", fill=fill)
        R_SOLD = r; r += 1
        put(r, 1, "   market loss (gone)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), f"=({wl(w)}{R_OFF}-{wl(w)}{R_SOLD})*(1-$H${pr})", fmt="#,##0")
        R_ML = r; r += 1
        put(r, 1, "   returned to store", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), f"=({wl(w)}{R_OFF}-{wl(w)}{R_SOLD})*$H${pr}", fmt="#,##0")
        R_RET = r; r += 1
        put(r, 1, "   leaves the store (offered - returned)", font=F_SMALL)
        put(r, 2, "lb", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), f"={wl(w)}{R_OFF}-{wl(w)}{R_RET}", fmt="#,##0")
        consumed_rows.append(r); r += 1

        # SECOND PASS — now R_SOLD is a fact rather than an offset guess.
        for w in range(1, 53):
            weekly = f"IF(AND({w}>=$E${pr},{w}<=$F${pr}),$D${pr},0)"
            prior = (f"SUM({wl(1)}{R_SOLD}:{wl(w-1)}{R_SOLD})" if w > 1 else "0")
            put(R_CAP, wcol(w), f'=IF($C${pr}="Annual",$D${pr}-{prior},{weekly})',
                fmt="#,##0", fill=ANNUAL_FILL if is_annual else fill)
        ch_rows[hname] = dict(cap=R_CAP, off=R_OFF, sold=R_SOLD, ml=R_ML, ret=R_RET, con=r - 1)

    put(r, 1, "Stock carried out", font=F_BOLD, fill=CON_FILL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_STORE}" + "".join(f"-{wl(w)}{c}" for c in consumed_rows),
            fmt="#,##0")
    R_CLOSE = r; r += 1
    put(r, 1, "   ^ subtracts what LEAVES, not what was offered — so 'returned to store' is",
        font=F_NOTE); r += 1
    put(r, 1, "     never taken out at all, and shows up as next week's carried in.",
        font=F_NOTE); r += 1
    for w in range(1, 53):
        ws.cell(row=R_OPEN, column=wcol(w),
                value=(0 if w == 1 else f"={wl(w-1)}{R_CLOSE}")).number_format = "#,##0"
    ws.cell(row=R_OPEN, column=2, value="lb").font = F_NOTE

    put(r, 1, "Most stock its shelf life allows", font=F_SMALL, fill=CON_FILL)
    put(r, 2, "lb", font=F_NOTE)
    WKR = f"${wl(1)}${R_WK}:${LAST}${R_WK}"
    for w in range(1, 53):
        # C4c: nothing in store is older than its shelf life, so held stock cannot exceed what
        # arrived in the last L weeks. L counts the harvest week, hence the L-1 window.
        # A CONSTRAINT now, not the warning row v3/v4 printed — v5 has a solver, so it can be
        # enforced instead of merely noticed. Linear: the window comes from an INPUT, not a
        # decision.
        # SUMIFS against the week strip, so the formula READS $F$<crop> rather than having the
        # window baked in by the generator. Baked, the shelf-life box was a yellow cell that
        # changed nothing — which is how the grower found it.
        # DECAYED by age, matching the app's C4c. A pound that arrived k weeks ago is only
        # (1-shrink)^k of a pound now, so bounding today's shrunken stock against undecayed
        # arrivals leaves slack that can ONLY be filled by product older than the shelf life —
        # the single thing this row exists to forbid. The app measured the error at 7.4% of held
        # stock at 5%/wk and 21% at 15%/wk. SUMIFS cannot weight, so this is SUMPRODUCT.
        # The exponent is masked to (weeks <= w) so it is never negative — POWER(0, -n) errors
        # at shrink = 100%, and SUMPRODUCT evaluates every element before the mask is applied.
        older = f"({WKR}<={w})"
        put(r, wcol(w),
            f'=SUMPRODUCT(({WKR}>={w}-$F${cr}+2)*{older}'
            f'*${wl(1)}${R_PACK}:${LAST}${R_PACK}'
            f'*POWER(1-$G${cr},{older}*({w}-{WKR})))', fmt="#,##0", fill=CON_FILL)
    R_SHELF = r; r += 1
    put(r, 1, "   Stock carried out must stay at or below this row.", font=F_NOTE); r += 1

    # ---- what this crop costs, week by week ----
    put(r, 1, "Growing cost this week", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
    SUCCRANGE = f"${wl(1)}${ROW_SUCC}:${LAST}${ROW_SUCC_END}"
    for w in range(1, 53):
        col = f"{wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}"
        # acres in each phase this week x that phase's $/acre, plus seed on any planting that
        # STARTS this week. Three phases and a start test, all off the same calendar.
        parts = "+".join(
            f'SUMPRODUCT(({CROPCOL}="{name}")*({col}="{ph}")*{SR})*${cl}${cr}'
            for ph, cl in (("P", "K"), ("G", "L"), ("H", "M")))
        seed = (f'SUMPRODUCT(({CROPCOL}="{name}")*'
                f'(${C_START}${ROW_SUCC}:${C_START}${ROW_SUCC_END}={w})*{SR})*$H${cr}')
        put(r, wcol(w), f"={parts}+{seed}", fmt="#,##0")
    R_GROW = r; r += 1
    put(r, 1, "Packaging this week", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), "=" + "+".join(
            f"{wl(w)}{ch_rows[h]['sold']}*$J${pair_row[(name, h)]}" for h in CH_NAMES),
            fmt="#,##0")
    R_PKG = r; r += 1

    put(r, 1, "ROOM OCCUPANCY", font=F_BOLD); put(r, 2, "m3", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"=({wl(w)}{R_OPEN}+{wl(w)}{R_PACK})*$D${cr}", fmt="0.0",
            fill=POOL_C if pool == "Cold" else POOL_A)
    R_ROOM = r; r += 2
    crop_block[name] = dict(pack=R_PACK, open=R_OPEN, shrink=R_SHRINK, store=R_STORE,
                            close=R_CLOSE, room=R_ROOM, shelf=R_SHELF, pool=pool, ch=ch_rows,
                            grow=R_GROW, pkg=R_PKG)

# --- 6. stores ---
put(r, 1, "6 — THE TWO STORES", font=F_H1); r += 1
pool_rows = {}
for pool, cap_row, fill in (("Cold", ROW_COLDCAP, POOL_C), ("Ambient", ROW_AMBCAP, POOL_A)):
    members = [n for n in CROP_NAMES if crop_block[n]["pool"] == pool]
    r = week_header(r, "m3")
    lhs = (lambda mem: (lambda w: "=" + "+".join(f"{wl(w)}{crop_block[n]['room']}" for n in mem)))(members)
    r, used, head = constraint_triplet(r, f"{pool.upper()} STORE", lhs, f"$B${cap_row}", fill,
                                       f"   Holds {', '.join(members)}.")
    pool_rows[pool] = dict(used=used, head=head, cap=cap_row)

# --- 7. money, week by week, and the cash floor ---
put(r, 1, "7 — CASH, WEEK BY WEEK", font=F_H1); r += 1
put(r, 1, "Opening cash", font=F_BOLD)
put(r, 2, 50000, fill=IN_FILL, fmt="$#,##0", border=True); ROW_OPCASH = r
put(r, 3, "what is in the bank on 1 January", font=F_NOTE); r += 1
put(r, 1, "Credit line", font=F_BOLD)
put(r, 2, 250000, fill=IN_FILL, fmt="$#,##0", border=True); ROW_CREDIT = r
put(r, 3, "how far below zero you may go", font=F_NOTE); r += 1
put(r, 1, "Fixed cost per week", font=F_BOLD)
put(r, 2, f"=$B${ROW_COLDCAP}*{LP.PAYLOAD['rate_harvest_storage']}"
          f"+$B${ROW_AMBCAP}*{LP.PAYLOAD['rate_ambient_storage']}"
          f"+$B${ROW_LAND}*{LP.PAYLOAD['rate_irrigation']}"
          f"+{LP.PAYLOAD['rate_machinery']}"
          f"+{LP.PAYLOAD['equip_storage']}*{LP.PAYLOAD['rate_equip_storage']}",
    fmt="$#,##0", font=F_BOLD)
ROW_FIXWK = r
put(r, 3, "cooler + barn depreciation, irrigation, machinery, equipment store — owed every "
          "week whether or not you plant", font=F_NOTE); r += 1
put(r, 1, "Overhead, % of revenue", font=F_BOLD)
put(r, 2, LP.PAYLOAD["overhead_pct_of_revenue"], fill=IN_FILL, fmt="0%", border=True)
ROW_OVH = r
put(r, 3, "insurance, admin, utilities — a share of what you sell", font=F_NOTE); r += 1
put(r, 1, "Interest APR on borrowing", font=F_BOLD)
put(r, 2, LP.PAYLOAD.get("interest_rate_apr", 0.0), fill=IN_FILL, fmt="0.0%", border=True)
ROW_APR = r
put(r, 3, "charged on what the credit line actually carries — reported below, not optimised over",
    font=F_NOTE); r += 2

r = week_header(r, "$")
put(r, 1, "Revenue", font=F_BOLD); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(
        f"{wl(w)}{crop_block[n]['ch'][h]['sold']}*$I${pair_row[(n, h)]}"
        for n in CROP_NAMES for h in CH_NAMES), fmt="#,##0")
R_REVWK = r; r += 1
put(r, 1, "  packaging", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{crop_block[n]['pkg']}" for n in CROP_NAMES),
        fmt="#,##0")
R_PKGWK = r; r += 1
put(r, 1, "  growing cost", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{crop_block[n]['grow']}" for n in CROP_NAMES),
        fmt="#,##0")
R_GROWWK = r; r += 1
put(r, 1, "  fixed cost", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"=$B${ROW_FIXWK}", fmt="#,##0")
R_FIXWK = r; r += 1
put(r, 1, "  overhead", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{R_REVWK}*$B${ROW_OVH}", fmt="#,##0")
R_OVHWK = r; r += 1
put(r, 1, "  wages", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{ROW_WAGEWK}", fmt="#,##0")
R_WAGEWK = r; r += 1
put(r, 1, "  overtime", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{ROW_OTCOST}", fmt="#,##0")
R_OTWK = r; r += 1
put(r, 1, "  advisory crew", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{ROW_ADVWAGE}", fmt="#,##0")
R_ADVWK = r; r += 1
put(r, 1, "NET CASH this week", font=F_BOLD); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{R_REVWK}-{wl(w)}{R_PKGWK}-{wl(w)}{R_GROWWK}"
                    f"-{wl(w)}{R_FIXWK}-{wl(w)}{R_OVHWK}-{wl(w)}{R_WAGEWK}"
                    f"-{wl(w)}{R_OTWK}-{wl(w)}{R_ADVWK}", fmt="#,##0")
R_NETWK = r; r += 2

r = week_header(r, "$")
# ⚠️ v10: this was DECISION green and it is a formula — the solver writes nothing
# here. Green on a computed row invites the reader to type in it.
put(r, 1, "CASH IN THE BANK", font=F_BOLD); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    prev = f"{wl(w-1)}{r}" if w > 1 else f"$B${ROW_OPCASH}"
    put(r, wcol(w), f"={prev}+{wl(w)}{R_NETWK}", fmt="#,##0", fill=DEC_FILL)
R_CUM = r; r += 1
for w in range(1, 53):
    put(r, wcol(w), ">=", align="center", font=F_BOLD)
r += 1
put(r, 1, "  floor", font=F_BOLD, fill=CON_FILL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    # ⚠️ MINUS THE CREDIT LINE, not minus (opening + credit). The row above is a BANK BALANCE
    # and already starts from opening cash, so flooring it at -(opening+credit) counted the
    # opening balance twice and allowed the farm $50,000 more overdraft than it has.
    # The app is consistent the other way: its C13 constrains cumulative NET FLOW, which does
    # NOT include opening cash, so -(opening+credit) is right there. Two coherent conventions;
    # this sheet had one of each.
    put(r, wcol(w), f"=-$B${ROW_CREDIT}", fmt="#,##0")
R_FLOOR = r; r += 1
put(r, 1, "  headroom", font=F_SMALL)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{R_CUM}-{wl(w)}{R_FLOOR}", fmt="#,##0")
R_HEAD = r; r += 1
put(r, 1, "   This is the app's C13. Cash may go NEGATIVE — that is the credit line being "
          "drawn — but never below the floor, which is the line fully drawn.", font=F_NOTE); r += 1
put(r, 1, "   The app states the same rule the other way round: it constrains cumulative NET "
          "FLOW (which excludes", font=F_NOTE); r += 1
put(r, 1, "   opening cash) against -(opening + credit). Both are the same constraint; mixing "
          "them double-counts the opening balance.", font=F_NOTE); r += 1
put(r, 1, "   ⚠️ It barely binds here, because the biggest weekly outgoing a real farm has is "
          "PAYROLL, and labour is v7. Do not read this curve as realistic yet.", font=F_NOTE)
r += 2
ws.conditional_formatting.add(f"{wl(1)}{R_HEAD}:{LAST}{R_HEAD}", CellIsRule(
    operator="lessThan", formula=["0"], fill=PatternFill("solid", fgColor="FFC7CE"),
    font=Font(color="9C0006", bold=True)))

# --- 8. the objective ---
put(r, 1, "8 — THE OPTIMIZER", font=F_H1); r += 1
put(r, 1, "Revenue", font=F_BOLD)
put(r, 2, "=" + "+".join(
    f"SUM({wl(1)}{crop_block[n]['ch'][h]['sold']}:{LAST}{crop_block[n]['ch'][h]['sold']})"
    f"*$I${pair_row[(n,h)]}" for n in CROP_NAMES for h in CH_NAMES), fmt="$#,##0", font=F_BOLD)
ROW_REV = r; r += 1
for _lab, _row in (("Growing cost", R_GROWWK), ("Packaging", R_PKGWK),
                   ("Fixed cost", R_FIXWK), ("Overhead", R_OVHWK), ("Wages", R_WAGEWK),
                   ("Overtime", R_OTWK), ("Advisory crew", R_ADVWK)):
    put(r, 1, _lab, font=F_BOLD)
    put(r, 2, f"=SUM({wl(1)}{_row}:{LAST}{_row})", fmt="$#,##0", font=F_BOLD)
    if _lab == "Growing cost":
        put(r, 3, "seed at planting + fertiliser and fuel every week in the ground", font=F_NOTE)
        ROW_COST = r
    if _lab == "Fixed cost":
        put(r, 3, "owed all 52 weeks whatever you plant", font=F_NOTE)
    if _lab == "Wages":
        put(r, 3, "committed — owed whether or not the crops need the hours", font=F_NOTE)
    if _lab == "Overtime":
        put(r, 3, "at the FULL rate — not the premium above base pay", font=F_NOTE)
    if _lab == "Advisory crew":
        put(r, 3, "committed for the whole window, used or not — same basis as Wages above",
            font=F_NOTE)
    ROW_COST_LAST = r          # ⚠️ the LAST cost row, captured as it is written
    r += 1
put(r, 1, "Peak borrowing", font=F_BOLD)
put(r, 2, f"=MAX(0,-MIN({wl(1)}{R_CUM}:{LAST}{R_CUM}))", fmt="$#,##0", font=F_BOLD)
put(r, 3, "the deepest the credit line is ever drawn", font=F_NOTE)
ROW_PEAKB = r; r += 1
put(r, 1, "Interest", font=F_BOLD)
# SUMPRODUCT, not AVERAGE(IF(...)) — the latter needs array entry (Ctrl+Shift+Enter) and
# silently returns the wrong thing when someone types it normally. A formula that depends on
# HOW it was entered has no place on a sheet meant to be edited.
put(r, 2, f"=$B${ROW_APR}*SUMPRODUCT(({wl(1)}{R_CUM}:{LAST}{R_CUM}<0)"
          f"*-{wl(1)}{R_CUM}:{LAST}{R_CUM})/52", fmt="$#,##0", font=F_BOLD)
put(r, 3, "APR x the AVERAGE amount borrowed — the app's own post-solve formula", font=F_NOTE)
ROW_INT = r; r += 1
put(r, 1, "   ⚠️ Reported, NOT optimised over. The plan is chosen first and the borrowing it "
          "implies is priced afterwards,", font=F_NOTE); r += 1
put(r, 1, "     so the solver has no reason to shift sales earlier to borrow less. That is the "
          "app's simplification, inherited on purpose.", font=F_NOTE); r += 1
put(r, 1, "PROFIT  (the objective)", font=F_BOLD, fill=OBJ_FILL)
# ⚠️ THE RANGE IS DERIVED, NOT COUNTED. This read `B{ROW_COST}:B{ROW_COST+5}` — six cost rows
# addressed by a hard-coded offset — and v9 adds a seventh (the advisory crew split out of
# "bought hours"). The stale +5 would have summed six of seven and silently dropped the whole
# advisory wage bill from PROFIT, while every row on the sheet still looked right. That is the
# fourth instance in this toy of "a position written down is a position that will drift", and
# the first where it would have cost money rather than a label.
assert ROW_COST_LAST > ROW_COST, "cost block is empty — the profit range would be inverted"
put(r, 2, f"=B{ROW_REV}-SUM(B{ROW_COST}:B{ROW_COST_LAST})-B{ROW_INT}", fmt="$#,##0",
    font=F_BOLD, fill=OBJ_FILL)
put(r, 3, "<-- MAXIMISE THIS CELL", font=F_BOLD)
ROW_OBJ = r; r += 1
put(r, 1, "Plantings chosen", font=F_BOLD)
put(r, 2, f"=SUM($D${ROW_SUCC}:$D${ROW_SUCC_END})", fmt="0")
put(r, 3, f"of {len(SUCCS)} offered", font=F_NOTE)
r += 2

annual_rows = []
put(r, 1, "Annual caps", font=F_BOLD); r += 1
for n in CROP_NAMES:
    for h in CH_NAMES:
        pr = pair_row[(n, h)]
        if ws.cell(row=pr, column=3).value != "Annual":
            continue
        sr_ = crop_block[n]["ch"][h]["sold"]
        put(r, 1, f"   {n} / {h} — sold all year", font=F_SMALL)
        put(r, 2, f"=SUM({wl(1)}{sr_}:{LAST}{sr_})", fmt="#,##0")
        put(r, 3, "<=", align="center", font=F_BOLD)
        put(r, 4, f"=$D${pr}", fmt="#,##0")
        annual_rows.append(r); r += 1
r += 1

put(r, 1, "SOLVER SETUP — Tools > Solver", font=F_H1); r += 1
recipe = [
    ("Target cell", f"$B${ROW_OBJ}", "set to MAXIMUM"),
    ("By changing cells", f"$C${ROW_SUCC}:$D${ROW_SUCC_END}", "acres AND plant? together"),
    ("  ...and", ";".join(f"${wl(1)}${crop_block[n]['ch'][h]['off']}:${LAST}$"
                          f"{crop_block[n]['ch'][h]['off']}"
                          for n in CROP_NAMES for h in CH_NAMES), "the OFFERED rows"),
    ("Constraint — PLANT? is binary", f"$D${ROW_SUCC}:$D${ROW_SUCC_END}  =  Binary", ""),
    ("Constraint — C9 acres <= max", f"$C${ROW_SUCC}:$C${ROW_SUCC_END}  <=  "
     f"${C_MAXA}${ROW_SUCC}:${C_MAXA}${ROW_SUCC_END}", "no acres without deciding to plant"),
    ("Constraint — C10 acres >= min", f"$C${ROW_SUCC}:$C${ROW_SUCC_END}  >=  "
     f"${C_MINA}${ROW_SUCC}:${C_MINA}${ROW_SUCC_END}", "planted means a real block"),
]
for n in CROP_NAMES:
    for h in CH_NAMES:
        cb = crop_block[n]["ch"][h]
        recipe.append((f"Constraint — {n}/{h} sold <= ceiling",
                       f"${wl(1)}${cb['sold']}:${LAST}${cb['sold']}  <=  "
                       f"${wl(1)}${cb['cap']}:${LAST}${cb['cap']}", ""))
for n in CROP_NAMES:
    recipe.append((f"Constraint — {n} stock never negative",
                   f"${wl(1)}${crop_block[n]['close']}:${LAST}${crop_block[n]['close']}  >=  0", ""))
for n in CROP_NAMES:
    recipe.append((f"Constraint — {n} shelf life",
                   f"${wl(1)}${crop_block[n]['close']}:${LAST}${crop_block[n]['close']}  <=  "
                   f"${wl(1)}${crop_block[n]['shelf']}:${LAST}${crop_block[n]['shelf']}",
                   "nothing held longer than it keeps"))
recipe += [
    ("Constraint — cold store", f"${wl(1)}${pool_rows['Cold']['used']}:"
     f"${LAST}${pool_rows['Cold']['used']}  <=  $B${ROW_COLDCAP}", ""),
    ("Constraint — ambient store", f"${wl(1)}${pool_rows['Ambient']['used']}:"
     f"${LAST}${pool_rows['Ambient']['used']}  <=  $B${ROW_AMBCAP}", ""),
    ("Constraint — land", f"${wl(1)}${ROW_LANDUSED}:${LAST}${ROW_LANDUSED}  <=  $B${ROW_LAND}", ""),
    ("  ...and", f"${wl(1)}${ROW_OTHRS}:${LAST}${ROW_OTHRS};$B${ROW_ADVCREW}",
     "the overtime row and the advisory headcount"),
    ("Constraint — CROP HOURS <= available", f"${wl(1)}${ROW_LABUSED}:${LAST}${ROW_LABUSED}  <=  "
     f"${wl(1)}${ROW_HOURSAVAIL}:${LAST}${ROW_HOURSAVAIL}", "the app's C2, with bought hours"),
    ("Constraint — overtime cap",
     f"${wl(1)}${ROW_OTUSED}:${LAST}${ROW_OTUSED};<=;"
     f"${wl(1)}${ROW_OTUSED + 2}:${LAST}${ROW_OTUSED + 2}",
     "DERIVED per week from the hourly crew — not a typed number (L2)"),
    ("Constraint — advisory crew is a whole number",
     f"$B${ROW_ADVCREW} = integer", "you hire people, not fractions of people"),
    ("Constraint — advisory crew available",
     f"$B${ROW_ADVCREW}  <=  {ADV_MAX}", "how many hands you could actually find"),
    ("Constraint — CASH FLOOR", f"${wl(1)}${R_CUM}:${LAST}${R_CUM}  >=  "
     f"${wl(1)}${R_FLOOR}:${LAST}${R_FLOOR}", "the app's C13"),
]
# No separate annual-cap entry: the ceiling row is now a RUNNING ALLOWANCE, so the same
# "sold <= ceiling" range already enforces the yearly total. One fewer entry to forget.
recipe.append(("Options", "engine = LibreOffice CoinMP Linear Solver",
               "tick 'Assume variables as non-negative'"))
for label, val, note in recipe:
    put(r, 1, label, font=F_BOLD if label.startswith(("Target", "By changing", "Options")) else F_SMALL)
    put(r, 2, val, font=F_SMALL)
    if note: put(r, 7, note, font=F_NOTE)
    r += 1
ws.freeze_panes = "E1"

# ---------------------------------------------------------------------------
# READ ME — every promised number COMPUTED from the MILP, never typed.
# ---------------------------------------------------------------------------
_OPT = LP.solve()
_RELAX = LP.solve(min_acreage=False)
NUMS = {
    "{PROFIT}": f"${_OPT['profit']:,.0f}", "{REV}": f"${_OPT['revenue']:,.0f}",
    "{COST}": f"${_OPT['cost']:,.0f}",
    "{GROW}": f"${_OPT['growing']:,.0f}", "{PKG}": f"${_OPT['packaging']:,.0f}",
    "{FIXED}": f"${_OPT['fixed']:,.0f}", "{OVH}": f"${_OPT['overhead']:,.0f}",
    "{FIXWK}": f"${_OPT['fixed_weekly']:,.0f}",
    "{WAGES}": f"${_OPT['wages']:,.0f}",
    "{WINTERWK}": f"${_OPT['wage_wk'][1]:,.0f}", "{PEAKWK}": f"${max(_OPT['wage_wk']):,.0f}",
    "{PEAKCAP}": f"{max(_OPT['lab_cap']):,.0f}", "{WINTERCAP}": f"{min(_OPT['lab_cap'][1:]):,.0f}",
    "{V6_PROFIT}": "$1,654,922",
    "{INTEREST}": f"${_OPT['interest']:,.0f}", "{PEAKB}": f"${_OPT['peak_borrow']:,.0f}",
    "{OTCOST}": f"${_OPT['ot_cost']:,.0f}",
    "{OTHRS}": f"{sum(_OPT['ot_hours']):,.0f}",
    "{OTRATE}": f"${_OPT['ot_rate'][20]:,.2f}",
    "{ADVCREW}": str(int(round(_OPT['adv_crew']))),
    "{ADVCOST}": f"${_OPT['adv_cost']:,.0f}",
    "{ADVFROM}": str(_OPT['adv_weeks'][0]) if _OPT['adv_weeks'] else "-",
    "{ADVTO}": str(_OPT['adv_weeks'][-1]) if _OPT['adv_weeks'] else "-",
    "{ADVGIVEN}": f"{sum(_OPT['adv_hours_given']):,.0f}",
    "{V8_PROFIT}": "$514,774",
    "{OTPEAKCAP}": f"{max(_OPT['ot_cap']):,.0f}",
    "{V7_PROFIT}": "$388,786",
    "{MARGIN}": f"{_OPT['profit'] / _OPT['revenue'] * 100:.1f}%",
    "{V5_PROFIT}": "$2,384,231",
    "{N_PLANTED}": str(_OPT["n_planted"]), "{N_OFFERED}": str(_OPT["n_offered"]),
    "{RELAX_PROFIT}": f"${_RELAX['profit']:,.0f}", "{RELAX_N}": str(_RELAX["n_planted"]),
    "{MIN_COST}": f"${_RELAX['profit'] - _OPT['profit']:,.0f}",
    "{V4_PROFIT}": "$1,094,831",
    "{N_DEC}": f"{N_DEC_CELLS:,}", "{DEC_BREAKDOWN}": DEC_BREAKDOWN,
    "{N_SUCC}": str(len(SUCCS)),
    "{ACRES_RANGE}": f"C{ROW_SUCC}:C{ROW_SUCC_END}",
    "{BIN_RANGE}": f"D{ROW_SUCC}:D{ROW_SUCC_END}",
    "{OBJ}": f"B{ROW_OBJ}",
}
readme = [
 ("Farm toy model — v10: LABOUR BY POSITION", F_TITLE),
 (f"BUILT {_BUILT}   (from source at commit {_SHA})", F_NOTE),
 ("If that timestamp is older than the change you are looking for, you have a stale copy —", F_NOTE),
 ("close the file and re-open it from WSL rather than from a recent-files list.", F_NOTE),
 ("", None),
 ("WHAT v9 CHANGES — the labour layer, rebuilt on three notes from the grower", F_H1),
 ("This is the first version where a labour change makes the model SMALLER. 52 spot-hire", None),
 ("variables became ONE headcount, and a typed cap became a derived row.", None),
 ("", None),
 ("     profit {V8_PROFIT} (v8) -> {PROFIT}        revenue {REV}        margin {MARGIN}", F_BOLD),
 ("     it hires {ADVCREW} people for weeks {ADVFROM}-{ADVTO} ({ADVCOST}) and works {OTHRS} overtime hours ({OTCOST})", F_BOLD),
 ("", None),
 ("Profit FALLS against v8 and that is the honest direction: v8 could buy an hour in any week", None),
 ("at a spot price and never pay for an hour it did not use.", None),
 ("", None),
 ("1. THERE IS NO SPOT HIRE ANY MORE. You nominate a WINDOW; the solver picks the HEADCOUNT.", F_BOLD),
 ("   v8's plan was unexecutable: 21 separate weeks of hiring in blocks of 2, 2, 2, 3 and 12", None),
 ("   weeks, and one week that bought TWO HOURS. No real hiring path works that way. H-2A wants", None),
 ("   60-75 days of lead and GUARANTEES the worker three-quarters of the contract's hours;", None),
 ("   domestic seasonal hiring wants 8-10 weeks and the good crews book out months ahead.", None),
 ("   Every path is a committed block decided before the season.", None),
 ("", None),
 ("   So the advisory crew is CHARGED FOR ITS WHOLE WINDOW, used or not — the same treatment", None),
 ("   the standing crew already gets. Compare row 13 against row 10 in a week the plan does not", None),
 ("   need the hours: that gap is what committing to people actually costs, and v8 could not", None),
 ("   show it, because an hour it did not want was simply never bought.", None),
 ("", None),
 ("   The answer is a ROSTER ROW: 'hire {ADVCREW} people, weeks {ADVFROM} to {ADVTO}'. Type it into", None),
 ("   section 3b, set the advisory headcount back to 0, and re-solve. That round trip is the", None),
 ("   point — the recommendation is written in the same units as the input.", None),
 ("", None),
 ("2. THE OVERTIME CAP IS DERIVED, NOT TYPED.", F_BOLD),
 ("   v8 typed a flat 200 hrs/week. The crew on this farm swings from 0 to 872 hourly field", None),
 ("   hours across the year, so one number cannot express 'how much overtime will you allow'.", None),
 ("   On the app's own farm that flat cap let 15 of 52 weeks buy MORE overtime than the whole", None),
 ("   crew's regular hours — 185% in winter — and the app's solver took it, buying 191 overtime", None),
 ("   hours against 299 crew hours in one week. A 64% overtime rate is a 66-hour week for", None),
 ("   everybody on the crew.", None),
 ("", None),
 ("   Now you type an ALLOWANCE (1.25 = 'up to 125% of normal hours') and row 8 computes", None),
 ("   (allowance - 1) x row 3, week by week. It peaks at {OTPEAKCAP} hrs and it is ZERO in a week", None),
 ("   with no hourly crew, which is the whole point: you cannot work overtime on people who are", None),
 ("   not there.", None),
 ("", None),
 ("3. THE SECTION BUILDS UP IN NAMED ROWS.", F_BOLD),
 ("   v8 computed the payroll mask — who is on this week, hourly, and paid — INSIDE the overtime", None),
 ("   rate formula, to answer a question the capacity row above had already answered. It was", None),
 ("   dense because an intermediate quantity had no row of its own.", None),
 ("   Rows 1-14 now each read only the rows above them. Row 3 (hourly FIELD hours) is the one", None),
 ("   v8 never wrote down — and it is exactly what the overtime cap needed, which is why the cap", None),
 ("   had to be a typed constant. Give the quantity a name and the defect has nowhere to live.", None),
 ("", None),
 ("⚠️ THE WINDOW IS YOUR CALL, AND IT MATTERS MORE THAN THE HEADCOUNT", F_H1),
 ("Labour binds in EIGHT separate blocks of weeks on this farm. Only one of them is worth", None),
 ("hiring into. Measured, same farm, same solver, only the window changes:", None),
 ("", None),
 ("     weeks 16-21  (C2 binds all six weeks)      worth $5", F_BOLD),
 ("     weeks 27-31  (C2 binds all five weeks)     worth $21", F_BOLD),
 ("     weeks 43-49                                worth $58,253", F_BOLD),
 ("", None),
 ("A week where labour BINDS is not a week where more labour PAYS. In weeks 16-31 the crew is", None),
 ("already 908 hrs/wk and something else is holding the plan back; in weeks 43-49 the seasonal", None),
 ("crews have gone home to 108 hrs/wk and there is garlic in the ground.", None),
 ("", None),
 ("That is worth stating plainly because the obvious report — 'here are your binding weeks' —", None),
 ("would send you to the wrong one. Try it: put 16 and 21 in the window and re-solve.", None),
 ("", None),
 ("WHAT v7 ADDED — labour, which is TWO things at once", F_H1),
 ("", None),
 ("1. A COMMITTED COST. Every listed worker is paid for their stated hours whether or not the", F_BOLD),
 ("   crops need them. So there is NO per-acre labour charge anywhere on this sheet — the", None),
 ("   marginal crop hour is FREE, and it is rationed by capacity instead of priced. That is the", None),
 ("   app's W12, and it is the single largest correction the real model has ever made.", None),
 ("", None),
 ("2. A CAPACITY LIMIT. Crop hours in a week cannot exceed what the crew can give. The app's", F_BOLD),
 ("   C2 — and on this farm it is the constraint that binds hardest, in 22 of 52 weeks.", None),
 ("", None),
 ("AND THE WAGE BILL HAS A SHAPE", F_H1),
 ("     winter {WINTERWK}/wk        peak {PEAKWK}/wk        {WAGES} for the year", F_BOLD),
 ("     crew capacity {WINTERCAP} hrs/wk in winter, {PEAKCAP} at peak", F_BOLD),
 ("Flattening that to an annual average understated the app's own cash floor by $115,615, which", None),
 ("is why it is modelled week by week here rather than as one number.", None),
 ("", None),
 ("WHAT IT DOES TO THE ANSWER", F_H1),
 ("     profit {V6_PROFIT} -> {PROFIT}        net margin {MARGIN}", F_BOLD),
 ("Revenue falls too — {REV} against v6's $2,558,846 — and that is the important half. Labour", None),
 ("does not merely TAX the plan, it RESHAPES it: the crew cannot pick everything the ground", None),
 ("could grow, so acres the land would happily carry are simply not worth planting.", None),
 ("", None),
 ("Net margin {MARGIN} is finally in the same postcode as a real diversified-veg farm (5-15%),", None),
 ("having read 64.7% in v6. Labour was most of the gap.", None),
 ("", None),
 ("!! THE FINDING WORTH TAKING AWAY", F_H1),
 ("Committed wages create a MINIMUM CASH REQUIREMENT that no plan can avoid. This farm owes", None),
 ("$4,884 a week from January with nothing to sell until spring — $56,676 goes out before a", None),
 ("dollar comes in. Measured: below roughly $80,000-$100,000 of opening cash plus credit, there", None),
 ("is NO feasible plan at all. Not a worse plan — none.", None),
 ("", None),
 ("And above that threshold profit is IDENTICAL at every cash level. So cash does not shape the", None),
 ("plan here; it decides whether you may have one. Those are different questions and a single", None),
 ("profit figure hides which one you are asking.", None),
 ("", None),
 ("INTEREST IS REPORTED, NOT OPTIMISED OVER", F_H1),
 ("Peak borrowing {PEAKB}, interest {INTEREST} — APR on the AVERAGE amount the credit line", None),
 ("carries, which is the app's own post-solve formula.", None),
 ("", None),
 ("It sits OUTSIDE the objective deliberately, because that is what the app does: the plan is", None),
 ("chosen first and the borrowing it implies is priced afterwards. The consequence is worth", None),
 ("knowing — the solver has no reason to shift sales earlier to borrow less, so interest is a", None),
 ("REPORT here rather than a lever. On this farm it is trivial ({INTEREST}); on a farm that", None),
 ("borrows through a long winter it would not be.", None),
 ("", None),
 ("INTEREST IS REPORTED, NOT OPTIMISED OVER", F_H1),
 ("Peak borrowing {PEAKB}, interest {INTEREST} — small here, and the reason is worth knowing.", None),
 ("The plan is chosen FIRST and the borrowing it implies is priced afterwards, so the solver has", None),
 ("no reason to shift sales earlier to borrow less. That is the app's own simplification and the", None),
 ("toy inherits it deliberately rather than diverging: a toy that models cash better than the", None),
 ("thing it is checking cannot check it.", None),
 ("", None),
 ("WHAT v6 ADDED — real costs, and the cash floor", F_H1),
 ("These are one job, not two. A cash curve is meaningless without costs to spend, and v5's", None),
 ("profit was absurd precisely because seed was the only cost it charged.", None),
 ("", None),
 ("  TIMED variable costs   seed in the PLANTING week; fertiliser and fuel every week in the", None),
 ("                         ground at that phase's rate; packaging per lb in the week of SALE.", None),
 ("                         Timing is the whole point — a cash floor cannot be honest if the", None),
 ("                         costs land in the wrong week.", None),
 ("  FIXED costs            cooler and barn depreciation, irrigation, machinery, equipment", None),
 ("                         store: {FIXWK} a week, owed whether or not you plant anything.", None),
 ("  OVERHEAD               a share of revenue, exactly as the app internalises it.", None),
 ("  CASH FLOOR             cumulative cash may go negative — that is the credit line being", None),
 ("                         drawn — but never below -(opening cash + credit line). The app's C13.", None),
 ("", None),
 ("Profit falls {V5_PROFIT} -> {PROFIT} once those are charged.", F_BOLD),
 ("", None),
 ("!! AND IT IS STILL ABSURD: net margin {MARGIN}, against 5-15% for real diversified veg.", F_H1),
 ("Because LABOUR IS NOT HERE. On the real farm wages are about 90% of fixed cost — the app's", None),
 ("own demo pays $855,150 a year against the {FIXED} of fixed cost this sheet charges. So:", None),
 ("", None),
 ("     THE CASH FLOOR BARELY BINDS, AND YOU SHOULD NOT TRUST THIS CURVE YET.", F_BOLD),
 ("", None),
 ("Measured: at 50,000 opening and a 250,000 credit line the floor never touches. It only bites", None),
 ("at about 10,000 + 10,000. The mechanism is real and checked; the farm it is checking is not", None),
 ("yet paying anybody. Labour is v7, and it is what makes cash mean something.", None),
 ("", None),
 ("WHAT v5 ADDED — both of these you spotted missing from v4", F_H1),
 ("", None),
 ("1. IT CHOOSES WHEN TO PLANT.", F_BOLD),
 ("   All {N_SUCC} plantings the app's calendar generator offers are on the sheet, one row per legal", None),
 ("   start week. The solver puts acres on some and zero on others — and zero acres IS the", None),
 ("   decision not to plant that week. v4 offered five that I picked by hand.", None),
 ("", None),
 ("2. IT CHOOSES WHETHER TO PLANT AT ALL.", F_BOLD),
 ("   The BLUE column is a binary per planting, tied to the acres by two constraints that are", None),
 ("   the app's own C9 and C10:", None),
 ("        acres <= 'max if planted'   you cannot plant acres without deciding to plant", None),
 ("        acres >= 'min if planted'   if you plant at all, you plant a real block", None),
 ("   That is what stops it planting a third of an acre, and it makes this a MILP — which is", None),
 ("   what farm_v2/solver.py is. Its `integrality` array marks the very same y block.", None),
 ("", None),
 ("WHAT THE TWO CHANGES ARE WORTH — measured, and they pull OPPOSITE ways", F_H1),
 ("     v4, five hand-picked plantings          {V4_PROFIT}", None),
 ("     v5 without the minimum-acreage rule     {RELAX_PROFIT}   ({RELAX_N} plantings)", None),
 ("     v5 as it ships                          {PROFIT}   ({N_PLANTED} plantings)", F_BOLD),
 ("", None),
 ("Letting it choose the weeks more than doubles profit. Then the minimum-acreage rule takes", None),
 ("{MIN_COST} back and drops the plan from {RELAX_N} plantings to {N_PLANTED}, because the", None),
 ("slivers are gone.", None),
 ("", None),
 ("Neither number means anything alone. A fixed calendar UNDERSTATES; a missing minimum", None),
 ("acreage OVERSTATES. That is why the real model has both, and it is the reason it is a MILP", None),
 ("rather than a plain LP.", None),
 ("", None),
 ("WHY IT PLANTS SO MANY — this is the finding worth keeping", F_H1),
 ("{N_PLANTED} plantings out of {N_OFFERED}, staggered across the season rather than a few big", None),
 ("blocks. That is SUCCESSION PLANTING, and now you can see why it pays: spreading the harvest", None),
 ("is what lets you serve a WEEKLY demand cap continuously. Plant it all at once and one huge", None),
 ("harvest slams into the ceiling, the cooler fills, and the surplus is wasted or dumped cheap.", None),
 ("", None),
 ("A model with a fixed planting calendar cannot express the thing the practice exists for.", None),
 ("", None),
 ("!! IT NEEDS LIBREOFFICE, AND THIS ONE IS A REAL MILP", F_H1),
 ("{N_DEC} decision cells: {DEC_BREAKDOWN}. The engine MUST be", None),
 ("CoinMP — it does branch and bound over the integers. Expect it to take appreciably longer", None),
 ("than v4; integers are what make an optimizer work for its living.", None),
 ("", None),
 ("WHERE THINGS ARE", F_H1),
 ("  YELLOW   you type: the farm, the crop table, the crop x channel table.", None),
 ("  GREEN    the solver writes: the ACRES column ({ACRES_RANGE}), the six OFFERED rows, and", None),
 ("           the PROFIT cell ({OBJ}).", None),
 ("  BLUE     the solver writes: the PLANT? binaries ({BIN_RANGE}).", None),
 ("  Everything else is a formula. Columns A-D stay put when you scroll right.", None),
 ("", None),
 ("HOW TO RUN IT", F_H1),
 ("Section 7 lists every entry with exact ranges. In short:", None),
 ("   Tools > Solver, target the PROFIT cell, set to MAXIMUM", None),
 ("   Changing cells: {ACRES_RANGE} and {BIN_RANGE} together, plus the six OFFERED rows", None),
 ("   Add the constraint  {BIN_RANGE} = Binary   — without it the binaries are just numbers", None),
 ("   and the minimum-acreage rule silently stops working", None),
 ("   Options: engine = LibreOffice CoinMP Linear Solver; tick non-negative", None),
 ("", None),
 ("WHAT IT SHOULD FIND", F_H1),
 ("     PROFIT   {PROFIT}       net margin {MARGIN}", F_BOLD),
 ("       revenue      {REV}", None),
 ("       growing      {GROW}      seed at planting + fertiliser and fuel in the ground", None),
 ("       packaging    {PKG}      per lb sold, in the week of sale", None),
 ("       fixed        {FIXED}      {FIXWK} a week, owed whether or not you plant", None),
 ("       overhead     {OVH}      a share of revenue", None),
 ("       wages        {WAGES}      committed — owed whether the crops need the hours or not", None),
 ("       interest     {INTEREST}          APR on what the credit line actually carries", None),
 ("       overtime     {OTCOST}       {OTHRS} hours, capped by row 8 week by week", None),
 ("       advisory     {ADVCOST}      {ADVCREW} people, weeks {ADVFROM}-{ADVTO} — {ADVGIVEN} hrs committed", None),
 ("     peak borrowing {PEAKB} — the deepest the line is ever drawn", None),
 ("       interest     {INTEREST}          on {PEAKB} of peak borrowing — reported, not optimised over", None),
 ("     {N_PLANTED} of {N_OFFERED} plantings used", F_BOLD),
 ("", None),
 ("Computed by solving the same MILP with scipy.milp — the same HiGHS solver your app runs. A", None),
 ("few dollars apart is tolerances. Materially different means one of the two models is not the", None),
 ("model we think it is.", None),
 ("", None),
 ("WHAT SELL-THROUGH IS, AND WHY IT SHIPS AT 1.00", F_H1),
 ("Every 'Sell-through' in section 3 is 1.00, matching the app since 30 Aug. The 85% it used to", None),
 ("carry had no source, and it was being charged on channels where a purchase order exists and", None),
 ("nothing goes unsold. So the market-loss and returned-to-store rows all read ZERO right now.", None),
 ("That is correct, not broken.", None),
 ("", None),
 ("The narrow definition it now carries:", None),
 ("", None),
 ("     Of what you TAKE TO MARKET, the share that converts to cash — display attrition at a", F_BOLD),
 ("     stall, samples, transit damage, a rejected load.", F_BOLD),
 ("", None),
 ("NOT grade-out at harvest (that is pack-out, above the store). NOT spoilage in the store (that", None),
 ("is shrink). And NOT demand uncertainty — which is the one worth understanding, because it is", None),
 ("why the old wording could not be right:", None),
 ("", None),
 ("     The demand ceiling is HARD. At a 6,000 lb cap and 0.85, selling 6,000 means bringing", None),
 ("     7,059 and losing 1,059 — every week, including the best Saturday of the year, because", None),
 ("     the model will never let you sell 6,001. That is the whole downside of bringing extra", None),
 ("     with none of the upside. It is not a model of uncertainty; it is a one-sided penalty.", None),
 ("", None),
 ("So what it CAN mean is a display requirement: a picked-over stall sells less than a full one,", None),
 ("so moving 6,000 lb needs more than 6,000 lb on the table. Deterministic, and an input", None),
 ("requirement like seed. Real demand variance is a different problem (newsvendor) needing", None),
 ("machinery neither this sheet nor the app has yet.", None),
 ("", None),
 ("THREE THINGS TO TRY", F_H1),
 ("", None),
 ("EXPERIMENT 1 — switch sell-through on, and watch the crop decide what happens.", F_BOLD),
 ("   In section 3 set Spinach / {CH1} sell-through to 0.85, and Garlic / {CH1} to 0.85 too.", F_BOLD),
 ("   Re-solve.", F_BOLD),
 ("   Both now offer more than they sell. But look at the two 'market loss' rows: Spinach's is", None),
 ("   positive and Garlic's is ZERO, because garlic's 'Returns to store' is 1.00 — unsold garlic", None),
 ("   comes home and sells later, so the loss is a DELAY, not a loss.", None),
 ("   That is the grower's ruling in two cells: the same sell-through means different things on", None),
 ("   different crops, which is why it belongs on the crop x channel row and not on either one", None),
 ("   alone. Now set Garlic's 'Returns to store' to 0.00 and re-solve: the delay becomes a loss", None),
 ("   and the plan changes.", None),
 ("", None),
 ("EXPERIMENT 2 — move the hiring window.  Set the advisory window to 16 and 21, re-solve.", F_BOLD),
 ("   C2 binds in all six of those weeks, so they LOOK like the place to add people. The solver", None),
 ("   hires nobody, and profit moves by about five dollars. Put it back to 43-49 and it hires", None),
 ("   {ADVCREW} for {ADVCOST}. Utilisation tells you where a constraint is tight; it does not tell", None),
 ("   you what relieving it is worth, and only one of those is a hiring decision.", None),
 ("", None),
 ("EXPERIMENT 2b — tighten the overtime allowance.  Set it to 1.00 and re-solve.", F_BOLD),
 ("   Row 8 goes to zero everywhere and overtime disappears — 1.00 means 'no hours beyond", None),
 ("   normal'. Then try 2.00: the cap doubles in every week, but it doubles PROPORTIONALLY, so", None),
 ("   winter still gets almost none. That is what a typed hours cap could never do.", None),
 ("", None),
 ("EXPERIMENT 3 — sack the harvest crew.  Set the Harvest Crew count to 0 and re-solve.", F_BOLD),
 ("   You save their whole wage bill. Watch what happens to profit anyway: with fewer hours in", None),
 ("   weeks 14-40 the crops that need picking most cannot be picked, and revenue falls further", None),
 ("   than the wages saved. Then try the opposite — double their count — and watch profit rise", None),
 ("   even though payroll rose too. That is the trade a per-acre labour charge cannot express,", None),
 ("   and it is why the app rations hours with a constraint rather than pricing them.", None),
 ("", None),
 ("EXPERIMENT 4 — squeeze the cash.  Set the credit line to 10,000 and opening cash to 10,000,", F_BOLD),
 ("   then re-solve.", F_BOLD),
 ("   Below about $100,000 combined there is no feasible plan at all — see above. Just above", None),
 ("   it, watch WHICH plantings the floor drops: not the least profitable ones, but", None),
 ("   the ones whose costs land earliest relative to their revenue. Garlic goes in around week", None),
 ("   47 and is not sold until week 30 of the following year — nine months of money out before", None),
 ("   a dollar comes back. Cash does not rank crops by margin; it ranks them by TIMING, which no", None),
 ("   column on this sheet shows you.", None),
 ("", None),
 ("EXPERIMENT 5 — drop the minimum acreage.  Set every 'Min acres if planted' in the crop", F_BOLD),
 ("   table to 0 and re-solve.", F_BOLD),
 ("   Expect {RELAX_PROFIT} and {RELAX_N} plantings. The extra profit is real but the plan is", None),
 ("   not: it plants fractions of an acre no one would drive a tractor out for. This is what", None),
 ("   the binaries are FOR, and it is why the app carries them.", None),
 ("", None),
 ("EXPERIMENT 6 — take away the cooler.  Set the cold store to 40 m3 and re-solve.", F_BOLD),
 ("   Watch WHICH WEEKS it abandons, not just which crop. With a full calendar it can retreat", None),
 ("   to a planting pattern that keeps the cooler under its ceiling — an answer v4 could not", None),
 ("   even represent.", None),
 ("", None),
 ("WHAT v5 STILL DOES NOT CARRY", F_H1),
 ("  - Costs are seed/transplant per acre ONLY: no labour, water, packaging, storage, overhead.", None),
 ("    Profit is therefore far too high. The cash layer is next.", None),
 ("  - No cash-flow constraint, so it can spend money it does not have.", None),
 ("  - Shelf life IS enforced now (a real constraint since you found it dead). Shrink is wired", None),
 ("    too, but defaults to 0%, so it stays invisible until you set it.", None),
 ("  - No water, labour, diversity or throughput limits.", None),
 ("  - Three crops, not seven.", None),
 ("", None),
 ("!! THE SCALE WARNING", F_H1),
 ("An optimizer's answer is far more scale-sensitive than a calculator's: which constraint binds,", None),
 ("and therefore which crop and which WEEK wins, can invert between 3 crops and 7. This teaches", None),
 ("the machinery. It is not advice about your farm.", None),
 ("", None),
 ("HAS THIS SHEET BEEN CHECKED?", F_H1),
 ("Yes. Crop data, the calendar and the demand caps are read from the app. The formulas are", None),
 ("calculated by an engine and compared cell by cell against an independent model under three", None),
 ("configurations. Every input is perturbed to prove it propagates. No number is frozen. And the", None),
 ("same MILP is solved with scipy.milp, its answer written into the decision cells, and the", None),
 ("sheet's own PROFIT cell must reproduce the optimum exactly.", None),
 ("     Run it yourself:   .venv/bin/python toy_models/verify_toy_v8.py", None),
]
row_i = 1
for text, font in readme:
    for k, v in NUMS.items():
        text = text.replace(k, v)
    c = rd.cell(row=row_i, column=1, value=text)
    if font: c.font = font
    row_i += 1

out = REPO / "toy_models" / "farm_toy_v10_labour.xlsx"
wb.save(out)
print(f"wrote {out}")
print(f"  successions offered : {len(SUCCS)}")
print(f"  decision cells      : {N_DEC_CELLS:,} ({DEC_BREAKDOWN})")
print(f"  solver recipe entries: {len(recipe)-1}")
