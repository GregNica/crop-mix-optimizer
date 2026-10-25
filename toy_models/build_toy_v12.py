"""
build_toy_v12.py — generates the FIXED LAYER toy model workbook (a MILP): zones, a variant that
shares its market, a perennial, must-plant floors and contract floors (PLAN Batch FX.0), on top
of v11's labour by role.

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
import toy_v12_lp as LP

CROP_NAMES = LP.CROP_NAMES
crops = LP.CROPS
CH_NAMES = LP.CH_NAMES
SUCCS = LP.SUCCS

# ⚠️ ONE definition. This count was written out longhand in three places and every one of them
# still said 448 after v8 added 104 flex cells — the sheet's own description of itself was wrong
# in the docstring, the READ ME and the build banner at once. Derive it, do not retype it.
N_OFFER_CELLS = len(CROP_NAMES) * len(CH_NAMES) * 52
# v11. Derived from its parts, never retyped — this count was written out longhand in three
# places once and all three were stale.
_N_HOURLY = sum(1 for e in LP.PAYLOAD["employees"]
                if e["type"] != "salary" and e["wage"] > 0)
_N_ROLES = len(LP.PAYLOAD["employees"])
N_OT_CELLS = _N_HOURLY * 52          # one overtime row PER ROLE — no blend
N_EXTRA_CELLS = _N_ROLES             # extra heads, one integer per roster row
N_PIECE_CELLS = len(LP.PIECE_CROPS) * 52 + 1     # lb picked per crop per week + the engage switch
N_FLEX_CELLS = N_OT_CELLS + N_EXTRA_CELLS + N_PIECE_CELLS
# v12: the perennial sits in the calendar but its acres are an INPUT (committed ground), so it
# is not a decision cell — the calendar's decision range stops one row short of it.
N_PLANTABLE = len(SUCCS) - len(LP.PERENNIAL_NAMES)
N_SHORT_CELLS = len(LP.CONTRACTS) * 52           # one shortfall row per contract
N_DEC_CELLS = N_PLANTABLE * 2 + N_OFFER_CELLS + N_FLEX_CELLS + N_SHORT_CELLS
DEC_BREAKDOWN = (f"{N_PLANTABLE} acres + {N_PLANTABLE} binaries + {N_OFFER_CELLS} offered "
                 f"+ {N_OT_CELLS} overtime ({_N_HOURLY} roles x 52) + {N_EXTRA_CELLS} extra "
                 f"heads + {N_PIECE_CELLS} piece-rate + {N_SHORT_CELLS} contract shortfall")
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
C_ZONE = get_column_letter(wcol(52) + 4)   # v12: which land pool this planting stands in
C_ID = get_column_letter(wcol(52) + 5)     # v12: the identity it SELLS AS (read from section 2)

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
for c in (C_MAXA, C_MINA, C_START, C_ZONE, C_ID):
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
put(r, 1, "FARM TOY MODEL — v12: the fixed layer (zones, variants, perennial, floors, contracts)",
    font=F_TITLE)
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

# ---- v12 / FX.4: ZONES. Named land pools, no geometry. Open field is whatever the other
# zones do not take, so "Land you have" keeps meaning the whole farm and v11's land sweep still
# reads the same.
put(r, 1, "1b — ZONES  (named land pools — no map)", font=F_H1); r += 1
ZONE_ROW = {}
for z, a, _code in LP.ZONES:
    put(r, 1, z, font=F_BOLD)
    ZONE_ROW[z] = r
    if a is not None:
        put(r, 2, a, fill=IN_FILL, fmt="0.0", border=True)
        put(r, 3, "acres", font=F_NOTE)
    else:
        put(r, 3, "acres — what the other zones leave of 'Land you have'", font=F_NOTE)
    r += 1
# the remainder zone (acres None in LP.ZONES — data, not a name test), as the oracle derives it
for z, a, _code in LP.ZONES:
    if a is None:
        put(ZONE_ROW[z], 2, f"=$B${ROW_LAND}" + "".join(f"-$B${ZONE_ROW[o]}" for o, oa, _ in LP.ZONES
                                                       if oa is not None),
            fmt="0.0", border=True)
put(r, 1, "   Which crops may stand in which zone is the 'Open field?' / 'High tunnel?' columns of "
          "section 2. A yellow Y can be set to N (its plantings get max acres 0); a grey N has no "
          "plantings to switch on — allowing it means new calendar rows.", font=F_NOTE); r += 2

# --- 2. crops ---
put(r, 1, "2 — HOW EACH CROP BEHAVES", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Yield lb/acre", "Pack-out", "m3 per lb", "Store", "Shelf life wk",
                       "Shrink %/wk", "Seed $/acre", "Min acres if planted", "Harvest weeks",
                       "$/ac plant wk", "$/ac grow wk", "$/ac harvest wk",
                       "hrs/ac plant", "hrs/ac grow", "hrs/ac harvest", "Sells as"]
                      + [f"{z}?" for z in LP.ZONE_NAMES]):
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
    if c.get("perennial"):
        # ⚠️ NOT YELLOW for committed ground: seed and a minimum block mean nothing for acres
        # that are typed, not chosen, so a box here would be a DEAD input (code-review found
        # three on this row). A formula reading 0 keeps the shared column formulas valid.
        put(r, 8, "=0", fmt="$#,##0", border=True)
        put(r, 9, "=0", fmt="0.0", border=True)
    else:
        put(r, 8, c["seed_transplant_cost_per_acre"], fill=IN_FILL, fmt="$#,##0", border=True)
        put(r, 9, c.get("min_acreage_if_planted", 0.0), fill=IN_FILL, fmt="0.0", border=True)
    # Every succession of a crop harvests over the same number of weeks on this data, so
    # lb-per-harvest-week is a per-CROP scalar and the old 68-row helper column was carrying no
    # information. ASSERTED rather than assumed: a crop whose successions differ (a wrapped
    # calendar truncating a harvest window, say) fails the build instead of silently averaging.
    # (A perennial block still ESTABLISHING harvests nothing, so it has no lb/harvest-week to
    # disagree about — it alone is left out. An ANNUAL that lost its harvest still counts as 1
    # and trips the check, which is what the check is for.)
    _nh = {max(1, len(harvest_weeks_of(x, 52))) for x in SUCCS
           if CROP_NAMES[x["crop"]] == name
           and not (x.get("perennial") and not harvest_weeks_of(x, 52))}
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
    # v12 / FX.5: the identity the MARKET knows this crop by. Caps and contracts are keyed by
    # it, so two crops with one identity share one market. Grey, not yellow: which rows exist
    # downstream depends on it, so changing it here would not re-plumb the sheet.
    put(r, 17, LP.identity(name), border=True)
    # v12 / FX.4: eligibility, one Y/N per zone. LIVE — the calendar's 'max if planted' reads it.
    for _zj, _z in enumerate(LP.ZONE_NAMES):
        if _z in LP.ELIGIBLE[name] and not c.get("perennial"):
            put(r, 18 + _zj, "Y", fill=IN_FILL, border=True, align="center")
        elif _z in LP.ELIGIBLE[name]:
            put(r, 18 + _zj, "Y", border=True, align="center")   # committed: where it IS
        else:
            # ⚠️ GREY, NOT YELLOW. No planting rows exist for this crop in this zone, so a Y
            # typed here would change nothing — a dead input, which the guard caught. The sheet
            # can withdraw an eligibility, never grant one; granting means new calendar rows.
            put(r, 18 + _zj, "N", border=True, align="center")
    for _j, _ph in enumerate(("plant", "grow", "harv")):
        # FULL precision stored, two decimals DISPLAYED. Rounding the stored value to cents
        # put the sheet $2.38 away from the LP on a $1.65M objective — small, but it is the
        # difference between "these are the same model" and "these are nearly the same model",
        # and section E is the check that distinguishes them.
        if c.get("perennial"):
            # A formula 0, NOT an input: each planting BLOCK carries its own cost in 2b (blocks
            # of one crop differ by age), so a per-crop $ box here would be read by nothing.
            put(r, 11 + _j, "=0", fmt="$0.00", border=True)
        else:
            put(r, 11 + _j, c.get(f"fert_{_ph}", 0.0) * _fert + c.get(f"fuel_{_ph}", 0.0) * _fuel,
                fill=IN_FILL, fmt="$0.00", border=True)
        # ⚠️ LABOUR HOURS ARE INPUTS, not literals inside the C2 formula. They were baked in as
        # `*2`, `*4`, `*50` — numbers the sheet used and could not show, so no one could see WHY
        # spinach crowds the crew (50 h/acre to pick, against kale's 22) or change it to find out.
        # Same class as the shelf-life box that read nothing.
        put(r, 14 + _j, c.get(f"labor_{_ph}", 0.0), fill=IN_FILL, fmt="0.0", border=True)
    crop_row[name] = r; r += 1
put(r, 1, "'Min acres if planted' is what the plant/don't-plant switch enforces — see section 4.",
    font=F_NOTE); r += 1
put(r, 1, f"⚠️ {LP.VARIANT} is a separate NAME with its own windows, and it SELLS AS Spinach: it "
          f"shares Spinach's market (section 5) instead of getting a second one.", font=F_NOTE)
r += 2

# ---- v12 / FX.2: COMMITTED GROUND — the perennial, ONE ROW PER PLANTING BLOCK ------------
# Grower ruling 2026-10-25: blocks of one crop differ by age, so each is its own row with THIS
# year's cost. A mature block's establishment is SUNK (like the tunnel's structure) — no
# depreciation line. A block still establishing has no harvest this year.
put(r, 1, f"2b — COMMITTED GROUND: {LP.PERENNIAL} (a perennial, in the ground all 52 weeks)",
    font=F_H1); r += 1
put(r, 1, "   Each block's acres are an INPUT on its calendar row (section 4) — not a decision. "
          "It never goes through the planting calendar, which refuses any cycle over 52 weeks.",
    font=F_NOTE); r += 1
for j, h in enumerate(["Block", "$/acre this year", "This year"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
PER_COST_ROW = {}
for _b in LP.PERENNIAL_BLOCKS:
    put(r, 1, f"{_b['name']} — $/acre this year", border=True)
    put(r, 2, _b["cost_per_acre_yr"], fill=IN_FILL, fmt="$#,##0", border=True)
    PER_COST_ROW[_b["name"]] = r; r += 1
put(r, 1, "   Mature: this year's upkeep (Univ. Kentucky 2016 full-harvest year) — what it cost to "
          "put in is SUNK. New: the establishing year's cost — ⚠️ an UNSOURCED share of MSU "
          "Ext. E3315's $4,082/ac for years 0-2.", font=F_NOTE); r += 1
put(r, 1, "   Charged flat across the year like the farm's other fixed costs, and never as seed. "
          "'This year' reads the block's calendar row: no H = establishing, no harvest.",
    font=F_NOTE); r += 1
put(r, 1, "   ⚠️ TOY PLACEHOLDERS where no source was found: the harvest weeks (18-25), the FM "
          "price and caps, the labour hours, the pack volume and shelf life. FX.6 sources them.",
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
        if LP.identity(cname) != cname:
            # ⚠️ FX.5: NO CAP OF ITS OWN. A cap typed here is the trap — a second, full-size
            # market for the same product. The cap lives on the identity's row.
            put(r, 3, f"as {LP.identity(cname)}", border=True)
        else:
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
                       "From wk", "To wk", "Hire more?", "Max more", "EXTRA HIRED",
                       "Room left"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_CREW = r
for e in LP.PAYLOAD.get("employees", []):
    put(r, 1, e["position"], border=True)
    put(r, 2, e["count"], fill=IN_FILL, fmt="0", border=True)
    put(r, 3, e["type"], border=True)
    put(r, 4, e["wage"], fill=IN_FILL, fmt="$#,##0", border=True)
    put(r, 5, e["hours_per_week"], fill=IN_FILL, fmt="0", border=True)
    put(r, 6, (100 - e["admin_pct"] if "admin_pct" in e else e.get("field_time_pct", 100)), fill=IN_FILL, fmt="0", border=True)
    put(r, 7, e.get("start_week", 1), fill=IN_FILL, fmt="0", border=True)
    put(r, 8, e.get("end_week", 52), fill=IN_FILL, fmt="0", border=True)
    # v11: hiring MORE of a role you already listed. Nothing new is entered — the extra heads
    # inherit this row's wage, hours, field% and window, which is exactly why a different
    # window or a different wage is a different ROW rather than another knob.
    put(r, 9, "Y" if e.get("can_hire_more") else "N", fill=IN_FILL, border=True)
    put(r, 10, e.get("max_extra", 0), fill=IN_FILL, fmt="0", border=True)
    put(r, 11, 0, fill=DEC_FILL, fmt="0", border=True)      # <-- SOLVER
    # ⚠️ THE TOGGLE AND THE CAP ARE READ BY FORMULAS, not just obeyed by the Solver recipe.
    # Third time in this toy: v8's "Max overtime hrs/week" and v10's "Max people available"
    # both shipped as recipe-only bounds that no formula touched, invisible to a reader AND to
    # the dead-input guard. The recorded lesson is "fix the builder, not the guard".
    put(r, 12, f'=IF($I${r}="Y",$J${r}-$K${r},0)', fmt="0", border=True, fill=CON_FILL)
    r += 1
ROW_CREW_END = r - 1
put(r, 1, "   EXTRA HIRED is the solver's answer, in whole people: \"change this row's Count "
          "from 8 to 11\". It is committed for the ROLE'S window — a head you add to a 27-week "
          "crew is 27 weeks of wages, which is why the answer is often zero.", font=F_NOTE)
r += 1
put(r, 1, "   ⚠️ If the weeks you could hire for DIFFER from this row's window, add a NEW row "
          "with the same title and its own weeks. A different window is a different job offer, "
          "not a variation on this one.", font=F_NOTE); r += 1
put(r, 1, "   No committed staff of a role, but curious? Put Count 0, Hire more Y, and set the "
          "weeks. That asks \"should I have this crew at all?\"", font=F_NOTE); r += 1
put(r, 1, "Payroll load %", font=F_BOLD)
put(r, 2, LP.payroll_load(), fill=IN_FILL, fmt="0%", border=True)
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
put(r, 1, "New-hire productivity %", font=F_BOLD)
put(r, 2, 70, fill=IN_FILL, fmt="0", border=True); ROW_PROD = r
put(r, 3, "a new hand is not as fast as the crew already doing the job — it multiplies their "
          "HOURS, not their wage", font=F_NOTE); r += 1
put(r, 1, "Cost per new head", font=F_BOLD)
put(r, 2, 800, fill=IN_FILL, fmt="$#,##0", border=True); ROW_HEADCOST = r
put(r, 3, "recruitment, onboarding, transport — per PERSON, once", font=F_NOTE); r += 2

# ---- 3c: the piece-rate crew -------------------------------------------
put(r, 1, "3c — PIECE-RATE HARVEST CREW  (paid per pound, not per hour)", font=F_H1); r += 1
put(r, 1, "   Everything else on this sheet is COMMITTED labour — owed whether the crops need "
          "it or not. This is the opposite: you pay for what they pick and nothing when there "
          "is nothing to pick, which is why it lands in COGS and not the wage bill.",
    font=F_NOTE); r += 1
for j2, h in enumerate(["From wk", "To wk", "Crew hrs/week", "Var cost $/lb", "Fixed cost $",
                        "Pre-committed?"]):
    put(r, 2 + j2, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
put(r, 1, "Piece-rate crew", font=F_BOLD)
put(r, 2, 1, fill=IN_FILL, fmt="0", border=True);        PC_START = f"$B${r}"
put(r, 3, 52, fill=IN_FILL, fmt="0", border=True);       PC_END = f"$C${r}"
put(r, 4, LP.PIECE_MAX_HOURS_PER_WEEK, fill=IN_FILL, fmt="#,##0", border=True)
PC_MAX = f"$D${r}"
put(r, 5, 0.02, fill=IN_FILL, fmt="$0.0000", border=True); PC_VAR = f"$E${r}"
put(r, 6, 2500, fill=IN_FILL, fmt="$#,##0", border=True); PC_FIX = f"$F${r}"
put(r, 7, "N", fill=IN_FILL, border=True);               PC_COMMIT = f"$G${r}"
ROW_PC = r; r += 1
put(r, 1, "ENGAGED?", font=F_BOLD, fill=DEC_FILL)
put(r, 2, 0, fill=DEC_FILL, fmt="0", border=True); ROW_PCBIN = r; PC_BIN = f"$B${r}"
put(r, 3, "<-- SOLVER (0 or 1). The fixed cost is charged only if they are engaged — or "
          "always, if Pre-committed is Y.", font=F_NOTE); r += 1
put(r, 1, "Minimum wage floor $/hr", font=F_BOLD)
put(r, 2, 16.07, fill=IN_FILL, fmt="$0.00", border=True); ROW_FLOOR = r
put(r, 3, "AEWR Skill II, 2026. A piece-rate worker must still earn this for the hours worked; "
          "if the rate falls short the employer makes up the difference (FLSA).", font=F_NOTE)
r += 2

# The per-crop rate table. ⚠️ RATES DIFFER BY CROP AND THE FLOOR IS WHY: it converts to $/lb
# through picking speed, a 3.6x spread here. Entered as $ per container the way a contract
# reads, converted with the crop's OWN volume figure — the same number the storage rows use.
for j2, h in enumerate(["$ per bushel", "lb per bushel", "-> $/lb", "floor $/lb",
                        "EFFECTIVE $/lb", "which binds"]):
    put(r, 2 + j2, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
PC_ROWS = {}
for name in LP.PIECE_CROPS:
    cr = crop_row[name]
    lh = crops[name].get("labor_harv", 0.0) or 0.0
    put(r, 1, f"   {name}", font=F_SMALL)
    put(r, 2, LP.PIECE_CONTAINER[name][1], fill=IN_FILL, fmt="$0.00", border=True)
    put(r, 3, f"={LP.BUSHEL_M3}/$D${cr}", fmt="0.0", border=True)
    put(r, 4, f"=B{r}/C{r}", fmt="$0.0000", border=True)
    # floor $/lb = minimum wage / lb-per-harvest-hour, and lb-per-harvest-hour is
    # yield / harvest labour — both already on this sheet.
    # floor $/lb = minimum wage / (yield / harvest hrs per acre). Every term is a CELL on this
    # sheet — column B is yield and column P is harvest hours per acre — so the formula can be
    # read and changed. Baking the crop's hours in as a literal is the v7 defect ("the sheet
    # used numbers it could not show"), and column E is the STORE NAME, not the yield.
    put(r, 5, f"=$B${ROW_FLOOR}/($B${cr}/$P${cr})" if lh else 0, fmt="$0.0000", border=True)
    put(r, 6, f"=MAX(D{r},E{r})+{PC_VAR}", fmt="$0.0000", border=True, fill=CON_FILL)
    put(r, 7, f'=IF(E{r}>D{r},"FLOOR","rate")', border=True)
    PC_ROWS[name] = r; r += 1
put(r, 1, "   A rate entered BELOW its floor is inoperative — you pay the floor. That is not a "
          "modelling choice, it is FLSA: the make-up pay is real money.", font=F_NOTE); r += 1
put(r, 1, "   ⚠️ 'lb per bushel' comes from the crop's own volume figure. Check it against what "
          "you can lift: a bushel of kale is about 18 lb in the trade. See backlog L6.",
    font=F_NOTE); r += 2

# The piece-rate crew's DECISION rows: pounds of each crop they pick, week by week. The solver
# chooses which crops, how much and when — bounded by what was actually harvested that week,
# by the crew's weekly capacity, and by the harvest hours the relief cannot exceed.
r = week_header(r, "lb")
PIECE_LB_ROW = {}
for name in LP.PIECE_CROPS:
    put(r, 1, f"   {name} — picked by piece-rate crew", font=F_BOLD, fill=DEC_FILL)
    put(r, 2, "lb <-- SOLVER", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), 0.0, fmt="#,##0", fill=DEC_FILL)
    PIECE_LB_ROW[name] = r; r += 1
put(r, 1, "Piece-rate lb this week", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{PIECE_LB_ROW[n]}" for n in LP.PIECE_CROPS), fmt="#,##0")
ROW_PCTOT = r; r += 1
# ⚠️ THE CAPACITY IS IN HOURS, NOT POUNDS, AND THE GROWER FOUND WHY. A crew picks pounds at a
# rate that differs 3.6x by crop, so ONE pound number describes a crew that silently resizes
# with the crop: 20,000 lb/wk is 200 harvest hours of spinach, 150 of garlic, 55 of kale. It
# also distorted the ANSWER — a pound cap rewards hours-per-pound, so it favoured spinach over
# garlic even though garlic is the cheaper relief ($18.74/hr against $20.71). Measured on this
# farm, moving the cap to hours triples the garlic picked. Hours is the thing you actually have.
put(r, 1, "  picking hours used", font=F_BOLD, fill=CON_FILL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    # the ONE definition of this quantity on the sheet — block B reads it from here
    terms = [f"{wl(w)}{PIECE_LB_ROW[n]}/($B${crop_row[n]}/$P${crop_row[n]})"
             for n in LP.PIECE_CROPS if (crops[n].get("labor_harv", 0.0) or 0.0)]
    put(r, wcol(w), ("=" + "+".join(terms)) if terms else 0, fmt="#,##0", fill=CON_FILL)
ROW_PCHRS = r; r += 1
put(r, 1, "  their weekly capacity", font=F_BOLD, fill=CON_FILL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"=IF(AND({w}>={PC_START},{w}<={PC_END}),{PC_BIN}*{PC_MAX},0)",
        fmt="#,##0", fill=CON_FILL)
ROW_PCCAP = r; r += 1
put(r, 1, "  room left", font=F_SMALL, fill=CON_FILL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{ROW_PCCAP}-{wl(w)}{ROW_PCHRS}", fmt="#,##0", fill=CON_FILL)
r += 1
put(r, 1, "   Zero outside their weeks, and zero unless ENGAGED — that link is what makes the "
          "fixed cost conditional. Capacity is HOURS: 200 is five pickers at forty hours, and "
          "it buys whatever pounds that many hours picks of whichever crop they are on.",
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
put(r, wcol(52) + 4, "zone", font=F_SMALL, fill=HDR_FILL)
put(r, wcol(52) + 5, "sells as", font=F_SMALL, fill=HDR_FILL)
ROW_SUCC_HDR = r; r += 1
ROW_SUCC = r
PH = {0: "P", 1: "G", 2: "H"}
succ_rows = {}
for s in SUCCS:
    cn = CROP_NAMES[s["crop"]]
    nharv = max(1, len(harvest_weeks_of(s, 52)))
    put(r, 1, s["name"], font=F_SMALL)
    put(r, 2, cn, font=F_SMALL)
    if s.get("perennial"):
        # FX.2: COMMITTED. The acres are typed, and "plant?" follows from them — the solver
        # touches neither, so this row sits OUTSIDE the recipe's changing-cell range.
        put(r, 3, LP.PERENNIAL_BY_NAME[s["name"]]["acres"],
            fill=IN_FILL, fmt="0.00", border=True)
        put(r, 4, f"=IF(C{r}>0,1,0)", fmt="0")
    else:
        put(r, 3, 0.0, fill=DEC_FILL, fmt="0.00")      # DECISION: acres
        put(r, 4, 0, fill=BIN_FILL, fmt="0")           # DECISION: plant? (binary)
    pbw = {((wk - 1) % 52) + 1: ph for wk, ph in zip(s["weeks"], s["phases"])}
    for w in range(1, 53):
        if w in pbw:
            put(r, wcol(w), PH[pbw[w]], align="center", font=F_SMALL, fill=CAL_FILL)
    # C9 / C10 helpers — the plant/don't-plant linkage, as columns the Solver can constrain
    # v12: x eligibility. A planting in a zone its crop may not use can carry no acres — the
    # Y/N in section 2 is read HERE, which is what makes it a live input and not a label.
    _zc = get_column_letter(18 + LP.ZONE_NAMES.index(s["zone"]))
    put(r, wcol(52) + 1, f'=D{r}*$B${ROW_LAND}*IF(${_zc}${crop_row[cn]}="Y",1,0)', fmt="0.0",
        font=F_SMALL)
    put(r, wcol(52) + 2, f"=D{r}*$I${crop_row[cn]}", fmt="0.0", font=F_SMALL)
    # The week seed is paid for. Genuinely per-succession — unlike the lb/harvest-week column
    # v5 retired, this differs from row to row and no per-crop scalar can carry it.
    if s.get("perennial"):
        put(r, wcol(52) + 3, "-", font=F_SMALL)     # never planted this year: no seed week
    else:
        put(r, wcol(52) + 3, f'=MATCH("P",${wl(1)}{r}:${LAST}{r},0)', fmt="0", font=F_SMALL)
    put(r, wcol(52) + 4, s["zone"], font=F_SMALL)
    put(r, wcol(52) + 5, f"=$Q${crop_row[cn]}", font=F_SMALL)
    succ_rows[s["name"]] = r; r += 1
ROW_SUCC_END = r - 1
# The DECISION range stops before the perennial blocks, which the builder guarantees are last.
_NPB = len(LP.PERENNIAL_BLOCKS)
assert all(x.get("perennial") for x in SUCCS[-_NPB:]) and not any(
    x.get("perennial") for x in SUCCS[:-_NPB])
ROW_DEC_END = ROW_SUCC_END - _NPB
# SECOND PASS: each block's "this year" reads its own calendar row, so it cannot disagree with it.
for _b in LP.PERENNIAL_BLOCKS:
    _cr = succ_rows[_b["name"]]
    put(PER_COST_ROW[_b["name"]], 3,
        f'=IF(COUNTIF(${wl(1)}${_cr}:${LAST}${_cr},"H")>0,"bearing","establishing — no harvest")',
        border=True)

# SECOND PASS — "Harvest weeks" as a FORMULA counting the H's on each crop's first planting,
# rather than a number the generator knows and the sheet cannot show. It follows the calendar if
# that changes, and it is not a bare constant sitting among the inputs. Sampling ONE planting is
# exactly the uniformity asserted above.
for _n in CROP_NAMES:
    # the first planting that HARVESTS — an establishing perennial block has no H to count, and
    # sampling it would divide the crop's yield by 0 if it were ever listed first
    _first = succ_rows[next(x["name"] for x in SUCCS if CROP_NAMES[x["crop"]] == _n
                            and harvest_weeks_of(x, 52))]
    put(crop_row[_n], 10, f'=COUNTIF(${wl(1)}${_first}:${LAST}${_first},"H")', fmt="0",
        border=True)

put(r, 1, "ACRES <= 'max if planted' and ACRES >= 'min if planted' are the app's C9 and C10: you "
          "cannot plant acres without deciding to plant, and if you plant at all you plant a real "
          "block.", font=F_NOTE); r += 2

SR = f"$C${ROW_SUCC}:$C${ROW_SUCC_END}"          # acres column
CROPCOL = f"$B${ROW_SUCC}:$B${ROW_SUCC_END}"     # crop name column
ZONECOL = f"${C_ZONE}${ROW_SUCC}:${C_ZONE}${ROW_SUCC_END}"
IDCOL = f"${C_ID}${ROW_SUCC}:${C_ID}${ROW_SUCC_END}"
STANDS = lambda w: f"({wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}<>\"\")"

# --- 5. land — ONE BLOCK PER ZONE (FX.4). A tunnel acre is not a field acre. ---
ROW_LANDUSED = {}
for _z in LP.ZONE_NAMES:
    r = week_header(r, "acres")
    land_lhs = (lambda z_: lambda w: f'=SUMPRODUCT({STANDS(w)}*({ZONECOL}="{z_}")*{SR})')(_z)
    r, ROW_LANDUSED[_z], _ = constraint_triplet(
        r, f"LAND in the ground — {_z}", land_lhs, f"$B${ZONE_ROW[_z]}", None,
        f"   Acres standing in {_z} that week"
        + (f", the committed {LP.PERENNIAL} blocks included."
           if _z == "Open field" else "."))

# --- 5a. MUST-PLANT floors (FX.1) — UNCONDITIONAL: no PLANT? binary appears in them, so
# the solver cannot escape by not planting, which is exactly how 'min acres if planted' is
# escaped. Two forms, named differently because they are different promises.
put(r, 1, "5a — MUST-PLANT  (what you have already decided to grow)", font=F_H1); r += 1
put(r, 1, "   STANDING = acres in the ground in EVERY week of the window. ANNUAL = acres planted, "
          "summed over the year's plantings.", font=F_NOTE); r += 1
put(r, 1, "   ⚠️ Not the same promise — the READ ME prices both at 30 acres of kale, and one "
          "costs about nothing while the other costs tens of thousands.", font=F_NOTE); r += 1
for j, h in enumerate(["Sells as", "Acres", "From wk", "To wk"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
STAND_IN = []
for gid, ac, a, b in LP.MUST_STAND:
    put(r, 1, gid, border=True)
    put(r, 2, ac, fill=IN_FILL, fmt="0.0", border=True)
    put(r, 3, a, fill=IN_FILL, fmt="0", border=True)
    put(r, 4, b, fill=IN_FILL, fmt="0", border=True)
    put(r, 5, "STANDING", font=F_NOTE)
    STAND_IN.append(r); r += 1
ANNUAL_IN = []
for gid, ac in LP.MUST_ANNUAL.items():
    put(r, 1, gid, border=True)
    put(r, 2, ac, fill=IN_FILL, fmt="0.0", border=True)
    put(r, 5, "ANNUAL — acres planted across the year; committed perennial acres do not count",
        font=F_NOTE)
    ANNUAL_IN.append(r); r += 1
r += 1
# C15 — the CARRY-IN, PINNED (grower ruling 2026-10-25). What went in the ground last fall is a
# fact, not a floor: acres standing in week 1 EQUAL it. The year is cyclic, so those are the same
# plantings that go in this fall — one row honours last fall AND holds this fall's ground, crew
# and barn for the replant. An overwintering crop with nothing carried in cannot be planted.
put(r, 1, "CARRY-IN — in the ground on 1 January, planted last fall", font=F_BOLD); r += 1
for j, h in enumerate(["Sells as", "Acres"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
CARRY_IN = []
for gid in LP.OVERWINTERING:
    put(r, 1, gid, border=True)
    put(r, 2, float(LP.CARRY_IN.get(gid, 0.0)), fill=IN_FILL, fmt="0.0", border=True)
    put(r, 5, "PINNED — exactly this, not at least: no decisions about next year's crop",
        font=F_NOTE)
    CARRY_IN.append((gid, r)); r += 1
r += 1
r = week_header(r, "acres")
STAND_ROWS = []
for _ir in STAND_IN:
    gid = ws.cell(row=_ir, column=1).value
    put(r, 1, f"{gid} standing", font=F_BOLD, fill=CON_FILL); put(r, 2, "acres", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f'=SUMPRODUCT({STANDS(w)}*({IDCOL}="{gid}")*{SR})', fmt="0.0",
            fill=CON_FILL)
    _u = r; r += 1
    put(r, 1, f"  must stand (row {_ir})", font=F_BOLD, fill=CON_FILL)
    for w in range(1, 53):
        put(r, wcol(w), f"=IF(AND({w}>=$C${_ir},{w}<=$D${_ir}),$B${_ir},0)", fmt="0.0",
            fill=CON_FILL)
    _f = r; r += 1
    put(r, 1, "  room above the floor", font=F_SMALL, fill=CON_FILL)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{_u}-{wl(w)}{_f}", fmt="0.0", fill=CON_FILL)
    ws.conditional_formatting.add(f"{wl(1)}{r}:{LAST}{r}", CellIsRule(
        operator="lessThan", formula=["0"], fill=PatternFill("solid", fgColor="FFC7CE"),
        font=Font(color="9C0006", bold=True)))
    STAND_ROWS.append((_u, _f, _ir)); r += 1
ANN_ROWS = []
for _ir in ANNUAL_IN:
    gid = ws.cell(row=_ir, column=1).value
    put(r, 1, f"{gid} planted this year", font=F_BOLD, fill=CON_FILL)
    put(r, 2, f'=SUMPRODUCT(({IDCOL}="{gid}")*(${C_START}${ROW_SUCC}:${C_START}${ROW_SUCC_END}'
              f'<>"-")*{SR})', fmt="0.0", fill=CON_FILL)
    put(r, 3, ">=", align="center", font=F_BOLD)
    put(r, 4, f"=$B${_ir}", fmt="0.0", fill=CON_FILL)
    ANN_ROWS.append(r); r += 1
CARRY_ROWS = []
for gid, _ir in CARRY_IN:
    put(r, 1, f"{gid} in the ground, week 1", font=F_BOLD, fill=CON_FILL)
    put(r, 2, f'=SUMPRODUCT({STANDS(1)}*({IDCOL}="{gid}")*{SR})', fmt="0.0", fill=CON_FILL)
    put(r, 3, "=", align="center", font=F_BOLD)
    put(r, 4, f"=$B${_ir}", fmt="0.0", fill=CON_FILL)
    CARRY_ROWS.append(r); r += 1
put(r, 1, "   ⚠️ Floors and the carry-in are HARD — set one the farm cannot carry and there is no "
          "plan. Garlic's ceiling here is ~18.5 ac, set by the winter crew AND the barn together.",
    font=F_NOTE); r += 2

# ---------------------------------------------------------------------------
# LABOUR (v11). Four blocks, one job each — A who is on, B what you can add,
# C the limits, D what it costs. Nothing above C is money; nothing below it is
# a limit.
#
# WHAT CHANGED FROM v10, and both are the grower's:
#
#  * OVERTIME IS PER ROLE, and there is no blended rate anywhere. Once the
#    solver can also hire extra heads, a blend depends on a decision variable
#    and `hours x blend(extra)` stops being linear. Per role the rate is that
#    role's own wage x load x multiplier — a CONSTANT, because the wage is an
#    input. It is also a better model: with one blend an overtime hour costs
#    the same whoever works it, so the plan cannot prefer the cheap one or tell
#    you who to ask to stay late.
#
#  * HIRING IS "MORE OF A ROLE YOU ALREADY LISTED", not a synthetic new crew.
#    v10 invented a row with its own window, wage, hours and field% — eight
#    inputs to re-describe something the roster already describes, and the same
#    error v9 made with spot hire. Extra heads inherit their role's everything.
# ---------------------------------------------------------------------------
put(r, 1, "A — WHO IS ON, WEEK BY WEEK", font=F_H1); r += 1
put(r, 1, "   Committed staff PLUS whatever the solver decided to hire, at that role's own "
          "hours and window. New heads count for less: they are multiplied by the "
          "new-hire productivity %.", font=F_NOTE); r += 1
r = week_header(r, "hours")
_on_wk = lambda i_, w_: f"AND({w_}>=$G${i_},{w_}<=$H${i_})"
POS_ROWS = []
for _i in range(ROW_CREW, ROW_CREW_END + 1):
    _nm = ws.cell(row=_i, column=1).value
    _hourly = ws.cell(row=_i, column=3).value != "salary" and (ws.cell(row=_i, column=4).value or 0) > 0
    put(r, 1, f"   {_nm}", font=F_SMALL)
    put(r, 2, "hrs" + ("" if _hourly else "  (salaried)"), font=F_NOTE)
    for w in range(1, 53):
        # committed heads at full rate + extra heads at the productivity discount
        put(r, wcol(w),
            f'=IF({_on_wk(_i, w)},($B${_i}+IF($I${_i}="Y",$K${_i},0)*$B${ROW_PROD}/100)'
            f'*$E${_i}*$F${_i}/100,0)',
            fmt="#,##0")
    POS_ROWS.append((r, _i, _hourly))
    r += 1

put(r, 1, "CREW CAPACITY", font=F_BOLD); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{pr}" for pr, _, _ in POS_ROWS), fmt="#,##0")
ROW_LABCAP = r; r += 1
put(r, 1, "   The sum of the rows above — no mask, no SUMPRODUCT. You can add them by eye.",
    font=F_NOTE); r += 2

put(r, 1, "B — WHAT YOU CAN ADD", font=F_H1); r += 1
r = week_header(r, "hours")
OT_ROWS = []
for _pr, _i, _hourly in POS_ROWS:
    if not _hourly:
        continue
    _nm = ws.cell(row=_i, column=1).value
    put(r, 1, f"   {_nm} — overtime CAP", font=F_SMALL); put(r, 2, "hrs", font=F_NOTE)
    for w in range(1, 53):
        # (allowance - 1) x THIS role's hours that week, extra heads included.
        put(r, wcol(w), f"=MAX(0,$B${ROW_OTALLOW}-1)*{wl(w)}{_pr}", fmt="#,##0")
    _cap = r; r += 1
    put(r, 1, f"   {_nm} — OVERTIME hrs", font=F_BOLD, fill=DEC_FILL)
    put(r, 2, "hrs <-- SOLVER", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), 0.0, fmt="#,##0", fill=DEC_FILL)
    OT_ROWS.append((r, _cap, _i, _nm)); r += 1
put(r, 1, "   One cap and one decision per role. The RATE is that role's own wage — see block "
          "D — so the plan can prefer the cheap overtime, which a single blended rate could "
          "never express.", font=F_NOTE); r += 1

put(r, 1, "Harvest hours relieved", font=F_SMALL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    # ⚠️ ONE definition, in 3c, where the crew's own capacity is measured against it. This row
    # carries it into the labour block; it does not restate the conversion.
    put(r, wcol(w), f"={wl(w)}{ROW_PCHRS}", fmt="#,##0")
ROW_PCRELIEF = r; r += 1
put(r, 1, "   ⚠️ The piece-rate crew changes the HOURS you need, not the wages you owe — the "
          "committed crew is paid either way. Bounded below by the harvest hours actually "
          "needed, or pickers would be relieving the planting.", font=F_NOTE); r += 1

put(r, 1, "HOURS AVAILABLE", font=F_BOLD); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    parts = [f"{wl(w)}{ROW_LABCAP}"] + [f"{wl(w)}{o}" for o, _, _, _ in OT_ROWS]
    put(r, wcol(w), "=" + "+".join(parts), fmt="#,##0")
ROW_HOURSAVAIL = r; r += 1
put(r, 1, "   Crew capacity plus every role's overtime. The piece-rate crew is NOT in here — "
          "it removes hours from the demand side instead, which is block C.", font=F_NOTE)
r += 2

put(r, 1, "C — THE LIMITS", font=F_H1); r += 1
r = week_header(r, "hours")
lab_lhs = lambda w: "=" + "+".join(
    f'SUMPRODUCT(({CROPCOL}="{n}")*({wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}="{ph}")*{SR})'
    f'*${cl}${crop_row[n]}'
    for n in CROP_NAMES for ph, cl in (("P", "N"), ("G", "O"), ("H", "P"))) \
    + f"-{wl(w)}{ROW_PCRELIEF}"
r, ROW_LABUSED, _ = constraint_triplet(
    r, "CROP HOURS needed", lab_lhs, lambda w: f"{wl(w)}${ROW_HOURSAVAIL}", None,
    "   The app's C2, less whatever the piece-rate crew picked. On this farm it is the "
    "constraint that binds hardest.", fmt="#,##0")

r = week_header(r, "hours")
put(r, 1, "HARVEST hours needed", font=F_SMALL); put(r, 2, "hrs", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(
        f'SUMPRODUCT(({CROPCOL}="{n}")*({wl(w)}${ROW_SUCC}:{wl(w)}${ROW_SUCC_END}="H")*{SR})'
        f'*$P${crop_row[n]}' for n in LP.PIECE_CROPS), fmt="#,##0")
ROW_HARVNEED = r; r += 1
put(r, 1, "   Harvest-phase hours only, of the crops the piece-rate crew picks. The relief above "
          "cannot exceed this row.", font=F_NOTE)
r += 1
# ⚠️ v11: THREE ROWS, NOT TWENTY-ONE. Each role used to get a full constraint triplet here —
# a "used" row that was an alias of its decision row, a "<=" row, a "limit" row that was an
# alias of its cap row, and a "room left". The Solver recipe constrains the decision row
# against the cap row DIRECTLY (`$E$160:$AZ$160 <= $E$159:$AZ$159`), so those blocks stated a
# constraint nothing read — not the recipe, not the verifier, not a test. The grower spotted
# it. Only the slack was worth keeping, and slack is one row per role.
r = week_header(r, "hours")
OT_ROOM_ROWS = {}
for _ot, _cap, _i, _nm in OT_ROWS:
    put(r, 1, f"   {_nm} — overtime room left", font=F_SMALL, fill=CON_FILL)
    put(r, 2, "hrs", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}${_cap}-{wl(w)}{_ot}", fmt="#,##0", fill=CON_FILL)
    ws.conditional_formatting.add(f"{wl(1)}{r}:{LAST}{r}", CellIsRule(
        operator="lessThan", formula=["0"], fill=PatternFill("solid", fgColor="FFC7CE"),
        font=Font(color="9C0006", bold=True)))
    OT_ROOM_ROWS[_nm] = r; r += 1
put(r, 1, "   Each role's overtime against its OWN crew that week — the cap is two rows above "
          "the decision in block B, and the Solver constrains them there. Zero means that "
          "role is at its limit; negative means the recipe is not loaded.", font=F_NOTE)
r += 2

put(r, 1, "D — WHAT IT COSTS", font=F_H1); r += 1
put(r, 1, "   Nothing above this line is money. Nothing below it is a limit.", font=F_NOTE)
r += 1
r = week_header(r, "$")
COST_ROWS = []
for _pr, _i, _hourly in POS_ROWS:
    _nm = ws.cell(row=_i, column=1).value
    put(r, 1, f"   {_nm}", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
    for w in range(1, 53):
        # ⚠️ Extra heads are paid the FULL wage — the productivity discount is on their HOURS,
        # not their payslip. Field% likewise reduces capacity and not the wage.
        heads = f'($B${_i}+IF($I${_i}="Y",$K${_i},0))' 
        if ws.cell(row=_i, column=3).value == "salary":
            body = f"{heads}*$D${_i}/52*(1+$B${ROW_LOAD})"
        else:
            body = f"{heads}*$D${_i}*$E${_i}*(1+$B${ROW_LOAD})"
        put(r, wcol(w), f"=IF({_on_wk(_i, w)},{body},0)", fmt="#,##0")
    COST_ROWS.append(r); r += 1

r = week_header(r, "$")
put(r, 1, "Wage bill this week", font=F_BOLD); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{c_}" for c_ in COST_ROWS), fmt="#,##0")
ROW_WAGEWK = r; r += 1
put(r, 1, "   ⚠️ OWED WHETHER OR NOT THE CROPS NEED THEM (the app's W12) — which is why no crop "
          "carries a per-acre labour charge anywhere on this sheet.", font=F_NOTE); r += 1

put(r, 1, "New-head cost — ONCE, in the role's first week", font=F_SMALL)
put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    # ⚠️ GATED BY THE TOGGLE, like the hours and the wage rows. Without it the sheet charges
    # recruitment for heads on a role that cannot be hired at all — found by the extra-head
    # fixture (5 heads on a toggle-N role billed $4,000 in week 1), and missed by every other
    # check because at the optimum extra heads are zero.
    terms = [f'IF(AND({w}=$G${_i},$I${_i}="Y",$K${_i}>0),$K${_i}*$B${ROW_HEADCOST},0)'
             for _, _i, _ in POS_ROWS]
    put(r, wcol(w), "=" + "+".join(terms), fmt="#,##0")
ROW_HEADWK = r; r += 1
put(r, 1, "   Recruitment and onboarding, per person, in the week that role starts. ⚠️ The "
          "wage rows above test w>=From AND w<=To, because a wage is owed EVERY week of the "
          "window. This one tests w=From because it is paid ONCE. The two shapes differ on "
          "purpose — charged per week it would bill three heads for 33 weeks, not one.",
    font=F_NOTE); r += 1

put(r, 1, "Overtime cost this week", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    # ⚠️ EACH ROLE AT ITS OWN RATE. No blend: the rate is a constant per role, which is what
    # keeps this linear once extra heads are also a decision.
    terms = [f"{wl(w)}{_o}*$D${_i}*(1+$B${ROW_LOAD})*$B${ROW_OTMULT}"
             for _o, _c, _i, _nm in OT_ROWS]
    put(r, wcol(w), "=" + "+".join(terms), fmt="#,##0")
ROW_OTCOST = r; r += 1
put(r, 1, "   ⚠️ FULL rate, not the premium above base pay — the wage bill pays the stated "
          "hours, these are hours beyond them.", font=F_NOTE); r += 1

put(r, 1, "Piece-rate cost — per lb every week, + the fixed cost ONCE", font=F_SMALL)
put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    terms = [f"{wl(w)}{PIECE_LB_ROW[n]}*$F${PC_ROWS[n]}" for n in LP.PIECE_CROPS]
    # ⚠️ 'Pre-committed?' was read by NOTHING — the FOURTH recipe-only input this toy has
    # shipped (v8's overtime cap, v10's max people, v11's hire toggle). Wire it where it
    # belongs: a pre-committed crew's fixed cost is sunk whether or not the solver engages
    # them, which is the entire meaning of the toggle.
    fixed = f'+IF({w}={PC_START},IF({PC_COMMIT}="Y",1,{PC_BIN})*{PC_FIX},0)'
    put(r, wcol(w), "=" + "+".join(terms) + fixed, fmt="#,##0")
ROW_PCCOST = r; r += 1
put(r, 1, "   COGS, not payroll: you pay for what they pick. ⚠️ The fixed cost lands ONCE, in "
          "the first week of their window — which is why its IF tests w=From and not the "
          "whole window. Charged per week it would bill $2,500 fifty-two times.",
    font=F_NOTE); r += 2

def write_ceiling(cap_row, pr, sold_row):
    """The ceiling row: the stated weekly figure in season, or what is LEFT of an annual cap.

    `sold_row` is what the running allowance subtracts — this crop's own SOLD row, or (FX.5) the
    total of everything selling as its identity. One function so the two cannot drift.
    Always CONSTRAINT red (v10's rule), annual or weekly — v11's second pass still repainted it
    grey with the channel/annual fill, undoing that rule on every ceiling.
    """
    for w in range(1, 53):
        weekly = f"IF(AND({w}>=$E${pr},{w}<=$F${pr}),$D${pr},0)"
        prior = (f"SUM({wl(1)}{sold_row}:{wl(w-1)}{sold_row})" if w > 1 else "0")
        put(cap_row, wcol(w), f'=IF($C${pr}="Annual",$D${pr}-{prior},{weekly})',
            fmt="#,##0", fill=CON_FILL)


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
        is_variant = LP.identity(name) != name
        # ⚠️ v10: RED. This is a real constraint (sold <= ceiling) and v9 painted it with the
        # channel's grey, so the sheet's most-used limit did not look like a limit. The palette
        # guard missed it because it was pinned to rows I already knew were right — the same
        # mistake as a test that only runs the default fixture.
        if is_variant:
            # ⚠️ FX.5: NO CEILING ROW. This crop sells into its identity's market, whose ceiling
            # (in that crop's block) is measured against EVERYTHING that sells as it.
            put(r, 1, f"{hname} — shares {LP.identity(name)}'s ceiling (section 5c)",
                font=F_NOTE)
            R_CAP = None; r += 1
        else:
            put(r, 1, f"{hname} — most you may sell this week", font=F_SMALL, fill=CON_FILL)
            put(r, 2, "lb", font=F_NOTE)
            R_CAP = r
            # ⚠️ FORMULAS FILLED IN A SECOND PASS, once R_SOLD is known. They used to be written
            # here against `R_CAP + 2`, guessing where SOLD would land — and then the annual note
            # rows were inserted between the two, so the guess pointed at a blank line, the
            # running allowance summed nothing, and the ceiling never declined. Inert for two
            # commits while looking right. Never address a row you have not placed yet.
            # WEEKLY pair: the stated figure, inside its season. ANNUAL pair: what is LEFT of the
            # year's allowance — sold[w] <= annual - sum(sold before w) for every w is exactly
            # "the year's total <= annual", linear and self-enforcing (see write_ceiling).
            for w in range(1, 53):
                put(r, wcol(w), 0, fmt="#,##0", fill=CON_FILL)  # placeholder; filled below
            r += 1
            if is_annual:
                put(r, 1, f"   ^ {hname} is an ANNUAL cap ({int(ws.cell(row=pr, column=4).value):,} "
                          f"lb a year), so there is NO weekly limit —", font=F_NOTE); r += 1
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

        # SECOND PASS — now R_SOLD is a fact rather than an offset guess. (A shared market's
        # ceiling is re-written once more, in 5c, against the identity's TOTAL sold.)
        if not is_variant:
            write_ceiling(R_CAP, pr, R_SOLD)
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

# --- 5c. WHAT EACH MARKET TAKES — per IDENTITY (FX.5) ---------------------------------
# For an identity sold by more than one crop name, the market's ceiling is measured against the
# TOTAL, and that is the whole defence against the variant trap: a second NAME is not a second
# MARKET. Measured on this farm: keyed by name instead, the two spinaches sell twice the
# Farmers Market's weekly ceiling and the plan "earns" money that does not exist (READ ME).
put(r, 1, "5c — WHAT EACH MARKET TAKES  (one market per identity, however many names sell into it)",
    font=F_H1); r += 1
r = week_header(r, "lb")
CEIL = {}                      # (identity, channel) -> (ceiling row, sold row it is measured on)
for gid in LP.IDENTITIES:
    members = LP.members(gid)
    for h in CH_NAMES:
        base = crop_block[gid]["ch"][h]
        if len(members) == 1:
            CEIL[(gid, h)] = (base["cap"], base["sold"])
            continue
        put(r, 1, f"{gid} / {h} — SOLD, every name that sells as {gid}", font=F_BOLD,
            fill=CON_FILL)
        put(r, 2, "lb", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), "=" + "+".join(f"{wl(w)}{crop_block[m]['ch'][h]['sold']}"
                                           for m in members), fmt="#,##0", fill=CON_FILL)
        _tot = r; r += 1
        put(r, 1, f"   {', '.join(members)} — against the ceiling in the {gid.upper()} block",
            font=F_NOTE); r += 1
        _pr = pair_row[(gid, h)]
        write_ceiling(base["cap"], _pr, _tot)
        CEIL[(gid, h)] = (base["cap"], _tot)
r += 1

# --- 5d. CONTRACTS (FX.3) ----------------------------------------------------------------
# sold[identity, channel, w] + SHORTFALL >= owed. The shortfall cell is what makes an
# unmeetable contract a REPORTED number rather than "no feasible plan" (grower ruling G3); its
# penalty is what makes the solver try before it gives up.
put(r, 1, "5d — CONTRACTS  (what you have already promised to deliver)", font=F_H1); r += 1
for j, h in enumerate(["Sells as", "Channel", "lb / week", "From wk", "To wk", "Penalty $/lb",
                       "If short"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
CON_IN = []
for gid, h, lb, a, b, mode, pen in LP.CONTRACTS:
    put(r, 1, gid, border=True); put(r, 2, h, border=True)
    put(r, 3, lb, fill=IN_FILL, fmt="#,##0", border=True)
    put(r, 4, a, fill=IN_FILL, fmt="0", border=True)
    put(r, 5, b, fill=IN_FILL, fmt="0", border=True)
    # A 'deliver' contract has no shortfall, so a price box would be read by nothing — grey
    # "-" instead (N() reads it as 0). Switching the mode to penalty means typing a price here.
    if mode == "penalty":
        put(r, 6, pen, fill=IN_FILL, fmt="$0.00", border=True)
    else:
        put(r, 6, "-", border=True, align="center")
    put(r, 7, mode, fill=IN_FILL, border=True, align="center")
    # the mode is REQUIRED: anything but the two words is flagged, not quietly read as 'deliver'
    put(r, 8, f'=IF(AND(G{r}<>"penalty",G{r}<>"deliver"),"⚠️ If short must be penalty or deliver",'
              f'IF(AND(G{r}="penalty",NOT(N(F{r})>0)),"⚠️ a penalty needs a price",""))',
        font=F_NOTE)
    CON_IN.append(r); r += 1
put(r, 1, "   ⚠️ The penalty is per lb SHORT, on top of the sale you did not make. It is what a "
          "missed delivery costs you — cover purchases, a lost account. Set it low and the plan "
          "will short a contract it could have met.", font=F_NOTE); r += 1
put(r, 1, "   'If short' is REQUIRED: penalty (a price per lb short) or deliver (no shortfall at "
          "all — if no plan can fill it, there is no plan). A blank penalty would make the "
          "contract mean nothing.", font=F_NOTE); r += 2
CON_ROWS = []
for _k, _ir in enumerate(CON_IN):
    gid, h = LP.CONTRACTS[_k].gid, LP.CONTRACTS[_k].channel
    _sold = CEIL[(gid, h)][1]
    r = week_header(r, "lb")
    put(r, 1, f"{gid} / {h} — SHORTFALL", font=F_BOLD, fill=DEC_FILL)
    put(r, 2, "lb <-- SOLVER", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), 0.0, fmt="#,##0", fill=DEC_FILL)
    _sh = r; r += 1
    put(r, 1, f"  delivered + short", font=F_BOLD, fill=CON_FILL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{_sold}+{wl(w)}{_sh}", fmt="#,##0", fill=CON_FILL)
    _ds = r; r += 1
    put(r, 1, f"  owed (row {_ir})", font=F_BOLD, fill=CON_FILL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"=IF(AND({w}>=$D${_ir},{w}<=$E${_ir}),$C${_ir},0)", fmt="#,##0",
            fill=CON_FILL)
    _ow = r; r += 1
    put(r, 1, f"  may be short (row {_ir})", font=F_BOLD, fill=CON_FILL)
    put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f'=IF($G${_ir}="penalty",{wl(w)}{_ow},0)', fmt="#,##0", fill=CON_FILL)
    _mx = r; r += 1
    put(r, 1, f"  penalty", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{_sh}*N($F${_ir})", fmt="#,##0")
    _pen = r; r += 1
    put(r, 1, "   delivered + short >= owed, and short <= 'may be short': the order on a penalty "
              "contract (you cannot be short of an order nobody placed), 0 on a deliver one.",
        font=F_NOTE); r += 2
    CON_ROWS.append(dict(short=_sh, ds=_ds, owed=_ow, mx=_mx, pen=_pen, inp=_ir))

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
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{crop_block[n]['grow']}" for n in LP.ANNUALS),
        fmt="#,##0")
R_GROWWK = r; r += 1
put(r, 1, "  perennial blocks (this year's cost)", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=(" + "+".join(f"$C${succ_rows[b_['name']]}*$B${PER_COST_ROW[b_['name']]}"
                                    for b_ in LP.PERENNIAL_BLOCKS) + ")/52", fmt="#,##0")
R_PERWK = r; r += 1
put(r, 1, "  contract shortfall penalty", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), "=" + "+".join(f"{wl(w)}{c_['pen']}" for c_ in CON_ROWS), fmt="#,##0")
R_SHWK = r; r += 1
put(r, 1, "   ^ shown for its timing, but NOT in net cash: a penalty is settled with the buyer after "
          "the season. Charged against the weekly cash floor, an unavoidable shortfall at a big "
          "penalty made the whole plan INFEASIBLE — the very thing a priced shortfall exists to "
          "prevent.", font=F_NOTE); r += 1
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
put(r, 1, "  new-head one-off", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{ROW_HEADWK}", fmt="#,##0")
R_HEADWK = r; r += 1
put(r, 1, "  piece rate (COGS)", font=F_SMALL); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{ROW_PCCOST}", fmt="#,##0")
R_PCWK = r; r += 1
put(r, 1, "NET CASH this week", font=F_BOLD); put(r, 2, "$", font=F_NOTE)
for w in range(1, 53):
    put(r, wcol(w), f"={wl(w)}{R_REVWK}-{wl(w)}{R_PKGWK}-{wl(w)}{R_GROWWK}"
                    f"-{wl(w)}{R_FIXWK}-{wl(w)}{R_OVHWK}-{wl(w)}{R_WAGEWK}"
                    f"-{wl(w)}{R_OTWK}-{wl(w)}{R_HEADWK}-{wl(w)}{R_PCWK}"
                    f"-{wl(w)}{R_PERWK}", fmt="#,##0")
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
                   ("Overtime", R_OTWK), ("New heads", R_HEADWK),
                   ("Piece rate", R_PCWK), ("Perennial", R_PERWK),
                   ("Contract shortfall", R_SHWK)):
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
    if _lab == "New heads":
        put(r, 3, "recruitment and onboarding, per person, once", font=F_NOTE)
    if _lab == "Piece rate":
        put(r, 3, "paid per POUND picked — COGS, not payroll, and nothing owed when there is "
                  "nothing to pick", font=F_NOTE)
    if _lab == "Perennial":
        put(r, 3, f"{LP.PERENNIAL} blocks: this year's cost (upkeep; establishing for a new "
                  f"block) — a mature block's establishment is sunk, and none of it is seed",
            font=F_NOTE)
    if _lab == "Contract shortfall":
        put(r, 3, "the penalty on every lb a contract went short — see 5d", font=F_NOTE)
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
put(r, 2, f"=SUM($D${ROW_SUCC}:$D${ROW_DEC_END})", fmt="0")
put(r, 3, f"of {N_PLANTABLE} offered (the committed perennial is not a planting decision)",
    font=F_NOTE)
r += 2

annual_rows = []
put(r, 1, "Annual caps", font=F_BOLD); r += 1
for n in LP.IDENTITIES:
    for h in CH_NAMES:
        pr = pair_row[(n, h)]
        if ws.cell(row=pr, column=3).value != "Annual":
            continue
        sr_ = CEIL[(n, h)][1]
        put(r, 1, f"   {n} / {h} — sold all year", font=F_SMALL)
        put(r, 2, f"=SUM({wl(1)}{sr_}:{LAST}{sr_})", fmt="#,##0")
        put(r, 3, "<=", align="center", font=F_BOLD)
        put(r, 4, f"=$D${pr}", fmt="#,##0")
        annual_rows.append(r); r += 1
r += 1

put(r, 1, "SOLVER SETUP — Tools > Solver", font=F_H1); r += 1
recipe = [
    ("Target cell", f"$B${ROW_OBJ}", "set to MAXIMUM"),
    ("By changing cells", f"$C${ROW_SUCC}:$D${ROW_DEC_END}",
     f"acres AND plant? together — NOT rows {ROW_DEC_END + 1}-{ROW_SUCC_END}, the committed "
     f"perennial blocks"),
    ("  ...and", ";".join(f"${wl(1)}${crop_block[n]['ch'][h]['off']}:${LAST}$"
                          f"{crop_block[n]['ch'][h]['off']}"
                          for n in CROP_NAMES for h in CH_NAMES), "the OFFERED rows"),
    ("  ...and", ";".join(f"${wl(1)}${c_['short']}:${LAST}${c_['short']}" for c_ in CON_ROWS),
     "the contract SHORTFALL rows"),
    ("Constraint — PLANT? is binary", f"$D${ROW_SUCC}:$D${ROW_DEC_END}  =  Binary", ""),
    ("Constraint — C9 acres <= max", f"$C${ROW_SUCC}:$C${ROW_DEC_END}  <=  "
     f"${C_MAXA}${ROW_SUCC}:${C_MAXA}${ROW_DEC_END}",
     "no acres without deciding to plant — and none in a zone the crop may not use"),
    ("Constraint — C10 acres >= min", f"$C${ROW_SUCC}:$C${ROW_DEC_END}  >=  "
     f"${C_MINA}${ROW_SUCC}:${C_MINA}${ROW_DEC_END}", "planted means a real block"),
]
for (gid, h), (cap_r, sold_r) in CEIL.items():
    # ⚠️ FX.5: measured on the IDENTITY'S total sold — one market however many names sell in.
    recipe.append((f"Constraint — {gid}/{h} sold <= ceiling",
                   f"${wl(1)}${sold_r}:${LAST}${sold_r}  <=  "
                   f"${wl(1)}${cap_r}:${LAST}${cap_r}",
                   "every name that sells as it" if sold_r != crop_block[gid]["ch"][h]["sold"]
                   else ""))
for _u, _f, _ir in STAND_ROWS:
    recipe.append((f"Constraint — must-plant STANDING (row {_ir})",
                   f"${wl(1)}${_u}:${LAST}${_u}  >=  ${wl(1)}${_f}:${LAST}${_f}",
                   "unconditional — no PLANT? binary can switch it off"))
for _ar in ANN_ROWS:
    recipe.append((f"Constraint — must-plant ANNUAL", f"$B${_ar}  >=  $D${_ar}", ""))
for _cr in CARRY_ROWS:
    recipe.append((f"Constraint — carry-in PINNED", f"$B${_cr}  =  $D${_cr}",
                   "equal, not at least — it also holds this fall's replant"))
for c_ in CON_ROWS:
    recipe.append((f"Constraint — contract (row {c_['inp']})",
                   f"${wl(1)}${c_['ds']}:${LAST}${c_['ds']}  >=  "
                   f"${wl(1)}${c_['owed']}:${LAST}${c_['owed']}", "delivered + short >= owed"))
    recipe.append((f"Constraint — shortfall <= may be short (row {c_['inp']})",
                   f"${wl(1)}${c_['short']}:${LAST}${c_['short']}  <=  "
                   f"${wl(1)}${c_['mx']}:${LAST}${c_['mx']}", "0 on a 'deliver' contract"))
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
] + [
    (f"Constraint — land, {z}", f"${wl(1)}${ROW_LANDUSED[z]}:${LAST}${ROW_LANDUSED[z]}  <=  "
     f"$B${ZONE_ROW[z]}", "one pool per zone") for z in LP.ZONE_NAMES
] + [
    ("  ...and", ";".join(f"${wl(1)}${o}:${LAST}${o}" for o, _, _, _ in OT_ROWS),
     "one overtime row per hourly role — no blend"),
    ("  ...and", f"$K${ROW_CREW}:$K${ROW_CREW_END};$B${ROW_PCBIN};"
     + ";".join(f"${wl(1)}${PIECE_LB_ROW[n]}:${LAST}${PIECE_LB_ROW[n]}" for n in LP.PIECE_CROPS),
     "extra heads, the engage switch, and the pounds picked"),
    ("Constraint — CROP HOURS <= available", f"${wl(1)}${ROW_LABUSED}:${LAST}${ROW_LABUSED}  <=  "
     f"${wl(1)}${ROW_HOURSAVAIL}:${LAST}${ROW_HOURSAVAIL}", "the app's C2, less piece-rate relief"),
] + [
    (f"Constraint — overtime {nm}", f"${wl(1)}${o}:${LAST}${o}  <=  ${wl(1)}${c}:${LAST}${c}",
     "that role's own crew that week")
    for o, c, _i, nm in OT_ROWS
] + [
    ("Constraint — relief <= harvest hours",
     f"${wl(1)}${ROW_PCRELIEF}:${LAST}${ROW_PCRELIEF}  <=  "
     f"${wl(1)}${ROW_HARVNEED}:${LAST}${ROW_HARVNEED}", "pickers cannot relieve the planting"),
    ("Constraint — piece-rate capacity",
     f"${wl(1)}${ROW_PCTOT}:${LAST}${ROW_PCTOT}  <=  ${wl(1)}${ROW_PCCAP}:${LAST}${ROW_PCCAP}",
     "and zero unless ENGAGED"),
    ("Constraint — extra heads are whole people",
     f"$K${ROW_CREW}:$K${ROW_CREW_END} = integer", "you hire people, not fractions"),
    ("Constraint — extra heads available",
     f"$K${ROW_CREW}:$K${ROW_CREW_END}  <=  $J${ROW_CREW}:$J${ROW_CREW_END}",
     "each role's own 'max more'"),
    ("Constraint — ENGAGED is binary", f"$B${ROW_PCBIN} = binary", ""),
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
# ---- v12: WHAT EACH FIXED PIECE COSTS, measured on the OBJECTIVE, not on profit ----
# ⚠️ Profit includes INTEREST, which is post-solve and depends on the cash path — and two plans
# with the same objective can borrow differently. Measured: removing a floor that did not bind
# "raised" profit $45 with the objective identical to the cent. A with/without delta on profit
# would report that as the floor's cost. The objective is what the solver actually traded.
_D = {}
# "Without" the carry-in is garlic left FREE (None = unpinned, measurement only) — pinning it
# at 0, what an empty carry-in means, would price "no garlic at all", not the pin.
_FREE_CARRY = {g: None for g in LP.OVERWINTERING}
for _k, _kw in (("contracts", dict(contracts=[])), ("stand", dict(must_stand=[])),
                ("annual", dict(must_annual={})), ("carry", dict(carry_in=_FREE_CARRY)),
                # without the blocks, the contract that sells their crop goes too — a 'deliver'
                # contract on ground you no longer have is refused, not "costed"
                ("perennial", dict(perennial_acres=LP.NO_PERENNIAL,
                                   contracts=[c_ for c_ in LP.CONTRACTS if c_.gid != LP.PERENNIAL])),
                ("tunnel", dict(zones=[("Open field", LP.PAYLOAD["total_land"])])),
                ("all", dict(contracts=[], must_stand=[], must_annual={}, carry_in=_FREE_CARRY,
                             perennial_acres=LP.NO_PERENNIAL))):
    _D[_k] = LP.solve(**_kw)["obj_value"] - _OPT["obj_value"]
_TRAP = LP.solve(share_caps=False)
_VID = LP.identity(LP.VARIANT)                 # the identity the variant shares
_trap_wk = max(sum(_TRAP["offered"][(c_, LP.FM)][w] for c_ in LP.members(_VID))
               for w in range(52))
_SVA = {}
for _k, _kw in (("annual30", dict(must_annual={"Kale": 30.0}, must_stand=[])),
                ("stand30", dict(must_annual={}, must_stand=[("Kale", 30.0, 10, 20)])),
                ("base", dict(must_annual={}, must_stand=[]))):
    _SVA[_k] = LP.solve(**_kw)["obj_value"]
_PEN = LP.solve(contracts=[c_._replace(pen=5.0) if c_.mode == "penalty" else c_
                           for c_ in LP.CONTRACTS])
# A 'deliver' contract, priced and then pushed past what the farm can grow: the refusal must
# NAME it. 700 lb/wk of asparagus is more than 3 acres yield (measured), so it is refused.
_DK = LP.DELIVER_K[0]
_DKC = LP.CONTRACTS[_DK]
_DEL_COST = LP.solve(contracts=[c_ for k, c_ in enumerate(LP.CONTRACTS) if k != _DK])[
    "obj_value"] - _OPT["obj_value"]
try:
    LP.solve(contracts=[c_._replace(lb=700.0) if k == _DK else c_
                        for k, c_ in enumerate(LP.CONTRACTS)])
    raise AssertionError("700 lb/wk of asparagus solved — the README's refusal example is stale")
except RuntimeError as e_:
    # it must be the NAMED refusal — any other error here would be printed as if it were one
    assert f"{_DKC.gid}/{_DKC.channel}" in str(e_) and "weeks" in str(e_), str(e_)
    _DEL_REFUSAL = str(e_).split(": ", 1)[1].split(" — ")[0]


def _fc_line(k):
    """Fact or choice, DERIVED: re-solved at $5/lb, does the shortfall move? Typed, this verdict
    sat beside computed numbers and would have gone stale the first time the data changed."""
    g = LP.CONTRACTS[k].gid
    a, b = _OPT["short_lb"][k], _PEN["short_lb"][k]
    w0, w5 = LP.weeks_short(_OPT, k), LP.weeks_short(_PEN, k)
    if b >= a - 1e-6:
        verdict = f"a FACT — no price delivers weeks {w5[0]}-{w5[-1]}" if w5 else "a FACT"
    else:
        gained = sorted(set(w0) - set(w5))
        verdict = f"a CHOICE — at $5 the plan grows for weeks {', '.join(map(str, gained))}"
    return f"{g:<8} {a:,.0f} lb short -> {b:,.0f} lb   {verdict}"


def _usd(v):
    """Whole dollars, with -0 shown as 0 and a negative as -$X rather than $-X."""
    v = round(v)
    return f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"


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
    "{OTRATES}": " / ".join(f"{n} ${x:,.2f}" for n, x in
                            zip(_OPT['role_names'], _OPT['ot_rate_role']) if x),
    "{OTWHO}": " / ".join(f"{n} {sum(h):,.0f} h" for n, h in
                          zip(_OPT['role_names'], _OPT['ot_by_role']) if sum(h) > 0.5) or "none",
    "{EXTRA}": " / ".join(f"{n} +{x:,.0f}" for n, x in
                          zip(_OPT['role_names'], _OPT['extra_heads']) if x > 0) or "none",
    "{HIRECOST}": f"${_OPT['hire_cost']:,.0f}",
    "{PIECECOST}": f"${_OPT['piece_cost']:,.0f}",
    "{PIECELB}": f"{sum(sum(v) for v in _OPT['piece_lb'].values()):,.0f}",
    "{PIECEREL}": f"{sum(_OPT['piece_hours_relieved']):,.0f}",
    "{V10_PROFIT}": "$472,091",
    "{V7_PROFIT}": "$388,786",
    "{MARGIN}": f"{_OPT['profit'] / _OPT['revenue'] * 100:.1f}%",
    "{V5_PROFIT}": "$2,384,231",
    # PLANTINGS, which the committed perennial is not — counted out of both sides
    "{N_PLANTED}": str(_OPT["n_plantings"]), "{N_OFFERED}": str(_OPT["n_plantable"]),
    "{RELAX_PROFIT}": f"${_RELAX['profit']:,.0f}", "{RELAX_N}": str(_RELAX["n_plantings"]),
    "{MIN_COST}": f"${_RELAX['profit'] - _OPT['profit']:,.0f}",
    "{V4_PROFIT}": "$1,094,831",
    "{N_DEC}": f"{N_DEC_CELLS:,}", "{DEC_BREAKDOWN}": DEC_BREAKDOWN,
    "{N_SUCC}": str(len(SUCCS)),
    "{ACRES_RANGE}": f"C{ROW_SUCC}:C{ROW_DEC_END}",
    "{BIN_RANGE}": f"D{ROW_SUCC}:D{ROW_DEC_END}",
    "{OBJ}": f"B{ROW_OBJ}",
    "{PERCOST}": f"${_OPT['perennial_cost']:,.0f}",
    "{SHORTCOST}": f"${_OPT['shortfall_cost']:,.0f}",
    # _D = objective WITHOUT the piece minus WITH it: a cost when positive. The tunnel is the
    # other way round — removing it LOSES money — so it is reported as what it earns.
    "{D_CON}": _usd(_D['contracts']), "{D_STAND}": _usd(_D['stand']),
    "{D_ANN}": _usd(_D['annual']), "{D_PER}": _usd(_D['perennial']),
    "{D_TUN}": _usd(-_D['tunnel']), "{D_ALL}": _usd(_D['all']),
    **{f"{{FC{j}}}": _fc_line(k) for j, k in enumerate(LP.PENALTY_K)},
    "{D_CARRY}": _usd(_D['carry']),
    "{DELIVER}": (f"{_DKC.gid}/{_DKC.channel} {_DKC.lb:,.0f} lb/wk, "
                  f"weeks {_DKC.first}-{_DKC.last}: met in full, and it costs "
                  f"{_usd(_DEL_COST)} (pounds pulled off the dearer market)"),
    "{DEL_REFUSAL}": _DEL_REFUSAL,
    "{N_BLOCKS}": str(len(LP.PERENNIAL_BLOCKS)),
    "{PER_AC}": f"{sum(b_['acres'] for b_ in LP.PERENNIAL_BLOCKS):g}",
    "{PER_BLOCKS}": f"{LP.PERENNIAL}: " + " and ".join(
        f"{b_['acres']:g} ac {'bearing' if b_['bearing'] else 'establishing (no harvest)'}"
        for b_ in LP.PERENNIAL_BLOCKS),
    "{N_CON}": str(len(LP.CONTRACTS)),
    "{TRAP_GAIN}": f"${_TRAP['obj_value'] - _OPT['obj_value']:,.0f}",
    "{TRAP_WK}": f"{_trap_wk:,.0f}",
    "{FM_CAP}": f"{LP.cap_spec(_VID, LP.FM)[1]:,.0f}",
    "{SVA_ANN}": _usd(_SVA['base'] - _SVA['annual30']),
    "{SVA_STAND}": _usd(_SVA['base'] - _SVA['stand30']),
    "{SHORTS}": "; ".join(f"{c_.gid}/{c_.channel} {_OPT['short_lb'][k_]:,.0f} lb short "
                          f"(weeks {min(ws_)}-{max(ws_)})"
                          for k_, c_ in enumerate(LP.CONTRACTS)
                          if (ws_ := LP.weeks_short(_OPT, k_))) or "none",
    "{N_PLANTABLE}": str(N_PLANTABLE),
    "{CH1}": LP.FM,
}
readme = [
 ("Farm toy model — v12: THE FIXED LAYER", F_TITLE),
 (f"BUILT {_BUILT}   (from source at commit {_SHA})", F_NOTE),
 ("If that timestamp is older than the change you are looking for, you have a stale copy —", F_NOTE),
 ("close the file and re-open it from WSL rather than from a recent-files list.", F_NOTE),
 ("", None),
 ("WHAT v12 ADDS — the things you have already decided, owe, or physically have", F_H1),
 ("Your first page of January: 'what do you know you need to plant? That absorbs the big blocks,", None),
 ("and then the rest gets filled in with extras.' Until now the model optimised every acre from", None),
 ("zero. v12 is the 'absorb the big blocks' half, prototyped here before the app (PLAN FX.0).", None),
 ("", None),
 ("     profit {PROFIT}      revenue {REV}      margin {MARGIN}", F_BOLD),
 ("     {N_PLANTED} of {N_OFFERED} plantings used, plus the committed perennial blocks", F_BOLD),
 ("", None),
 ("WHAT EACH PIECE COSTS — with it vs without it, measured on the objective", F_H1),
 ("     the {N_CON} contracts           {D_CON}   ({SHORTS})", None),
 ("     the standing floor (kale)     {D_STAND}", None),
 ("     the annual floor (kale)       {D_ANN}", None),
 ("     the garlic carry-in, pinned   {D_CARRY}   (against garlic left free)", None),
 ("     the perennial ({PER_AC} ac, {N_BLOCKS} blocks) {D_PER}   (this year's cost: {PERCOST}; with its contract)", None),
 ("     ALL of the above              {D_ALL}", F_BOLD),
 ("     the 2-acre tunnel zone        {D_TUN}   (what the tunnel EARNS, against 2 acres of field)", None),
 ("   ⚠️ Measured on the OBJECTIVE, not profit. Profit includes interest, which is worked out", None),
 ("   AFTER the solve from the cash curve — and two plans worth the same can borrow differently.", None),
 ("   Removing a floor that did not bind once 'raised' profit $45 with the objective unchanged to", None),
 ("   the cent. A with/without on profit would have called that $45 the floor's cost.", None),
 ("", None),
 ("1. ZONES — named land pools, no map.", F_BOLD),
 ("   Section 1b. 'Open field' is whatever the other zones leave of 'Land you have'. Section 2", None),
 ("   says which crop may stand in which zone (Y/N), and a planting is now a (week, zone) pair:", None),
 ("   Kale is allowed in both, so each Kale week appears twice — 'F' and 'T'. Land is one", None),
 ("   constraint block PER ZONE. A tunnel acre is not a field acre; that is why zones exist.", None),
 ("", None),
 ("2. A VARIANT IS A SEPARATE NAME THAT SELLS AS ITS BASE.", F_BOLD),
 ("   'Tunnel Spinach' is Spinach with a longer planting window and a tunnel-sized minimum. Its", None),
 ("   own name, its own windows, its own costs — and NO market of its own. Section 5c measures", None),
 ("   every name that sells as Spinach against ONE Spinach ceiling.", None),
 ("   ⚠️ THE TRAP, measured: key the caps by NAME instead (what the app does today) and the two", None),
 ("   spinaches sell {TRAP_WK} lb a week into a {FM_CAP} lb Farmers Market, and the plan 'earns'", None),
 ("   {TRAP_GAIN} that does not exist. Same family as the duplicate-name defect (W1).", None),
 ("", None),
 ("3. A PERENNIAL IS COMMITTED GROUND, NOT A PLANTING — one row per BLOCK.", F_BOLD),
 ("   {PER_BLOCKS} — in the ground all", None),
 ("   52 weeks. Acres are INPUTS (yellow) on their calendar rows, outside the solver's changing", None),
 ("   cells. Neither goes through the planting calendar — which refuses any cycle over 52 weeks.", None),
 ("   Each block carries THIS year's cost (section 2b). The mature block's establishment is SUNK,", None),
 ("   like the tunnel's structure: no depreciation line. The new block is ESTABLISHING — costs and", None),
 ("   labour, no harvest (its calendar row has no H). Next year you type its first yield.", None),
 ("", None),
 ("4. MUST-PLANT FLOORS — UNCONDITIONAL, IN TWO FORMS. Section 5a.", F_BOLD),
 ("   'Min acres if planted' is NOT this: it is conditional on PLANT?, so the solver escapes it", None),
 ("   by not planting. A must-plant floor has no binary in it.", None),
 ("     STANDING  acres in the ground in EVERY week of a window.", None),
 ("     ANNUAL    acres planted, summed over the year's plantings.", None),
 ("   They are different promises and the toy settles that question. Same 30 acres of kale:", None),
 ("     ANNUAL 30 ac costs {SVA_ANN}   — the plan already plants more than that", None),
 ("     STANDING 30 ac in weeks 10-20 costs {SVA_STAND}", F_BOLD),
 ("   So: both, named differently.", None),
 ("   THE CARRY-IN (garlic in the ground on 1 Jan, the app's C15) is PINNED, not floored:", None),
 ("   acres standing in week 1 EQUAL what went in last fall. The year is cyclic, so those are", None),
 ("   the same plantings that go in THIS fall — one row honours last fall AND holds this fall's", None),
 ("   ground, crew and barn for the replant. No decisions about next year's garlic.", None),
 ("   ⚠️ Floors and the pin are HARD. Garlic's ceiling here is about 18.5 acres, set by TWO limits", None),
 ("   at once: the 108-hour winter crew in the planting weeks AND the 150 m3 barn at harvest.", None),
 ("   Relaxing either alone does not help. An app that refuses an impossible floor must say", None),
 ("   which limits it hit — 'check your land' would be wrong here.", None),
 ("", None),
 ("5. CONTRACTS — YOU CHOOSE WHAT A SHORTFALL MEANS. Section 5d.", F_BOLD),
 ("   delivered + SHORTFALL >= owed, per week, keyed by IDENTITY (the buyer contracted for", None),
 ("   spinach, not for a bed). 'If short' is REQUIRED — a blank penalty would make it mean nothing:", None),
 ("     penalty   the shortfall is a decision priced per lb: a REPORTED number, never 'no plan'.", None),
 ("     deliver   no shortfall at all. {DELIVER}.", None),
 ("               Ask for more than the farm can grow and there is no plan, and the refusal NAMES it:", None),
 ("               '{DEL_REFUSAL}'.", None),
 ("   The two penalty shortfalls look alike on the sheet and they are not. Raise both from $0.50", None),
 ("   to $5.00 a pound and measure:", None),
 ("     {FC0}", None),
 ("     {FC1}", None),
 ("   (both verdicts are re-solved, not reasoned — the first one I reasoned came out backwards)", None),
 ("   Where the plan shorts at $0.50 and not at $5, shorting was cheaper than growing. Only the penalty tells a choice from", None),
 ("   a fact — which is why it has to be the grower's number, and why the app should report", None),
 ("   WHICH kind each shortfall is.", None),
 ("", None),
 ("YOUR RULINGS (2026-10-25) — what this version now does", F_H1),
 ("  - Garlic already in is a pre-commitment, PINNED. Replanting a different amount this fall is", None),
 ("    your edit to the carry-in; separating the two is backlogged (X7).", None),
 ("  - Every contract says penalty (with a price) or deliver. No default.", None),
 ("  - A tunnel's structure and a mature planting's establishment are SUNK — no cost line here.", None),
 ("    Whether to BUILD something new is not the optimiser's call (backlog X6).", None),
 ("", None),
 ("WHAT v11 CHANGED — labour is now ONE mechanism: the roster", F_H1),
 ("v10 invented a separate 'proposed hire' block with its own window, wage, hours and field% —", None),
 ("eight inputs to re-describe something the roster already described. That was the same error", None),
 ("v9 made with spot hire, one version later. It is gone.", None),
 ("", None),
 ("     overtime {OTWHO}      extra heads: {EXTRA}", F_BOLD),
 ("     piece rate {PIECECOST} for {PIECELB} lb, relieving {PIECEREL} harvest hours", F_BOLD),
 ("", None),
 ("1. HIRING IS 'MORE OF A ROLE YOU ALREADY LISTED'.", F_BOLD),
 ("   Three columns on the crew table: Hire more? / Max more / EXTRA HIRED. Extra heads inherit", None),
 ("   that row's wage, hours, field% AND window — nothing new is entered anywhere. The answer", None),
 ("   is a roster edit: 'change this Count from 8 to 11'.", None),
 ("   Different weeks, or a different wage? Add a NEW ROW with the same title. A different", None),
 ("   window is a different job offer, not a variation on this one.", None),
 ("   No committed staff of a role but curious? Count 0, Hire more Y, set the weeks.", None),
 ("   ⚠️ The answer is often ZERO, and that is the finding: a head added to a 27-week crew is", None),
 ("   27 weeks of wages to buy hours you need in a handful of them.", None),
 ("", None),
 ("2. OVERTIME IS PER ROLE. THERE IS NO BLENDED RATE ANYWHERE.", F_BOLD),
 ("   {OTRATES}", None),
 ("   Once the solver can also hire extra heads, a blended rate depends on a decision variable", None),
 ("   and 'hours x blend' stops being linear. Per role the rate is that role's own wage x load", None),
 ("   x multiplier — a constant, because the wage is an input. So the model stays an LP AND it", None),
 ("   gets better: with one blend an overtime hour costs the same whoever works it, so the plan", None),
 ("   could not prefer the cheap one, or tell you WHO to ask to stay late.", None),
 ("", None),
 ("3. A PIECE-RATE HARVEST CREW, PAID PER POUND.", F_BOLD),
 ("   Everything else here is COMMITTED labour — owed whether the crops need it or not. This is", None),
 ("   the opposite: you pay for what they pick and nothing when there is nothing to pick, which", None),
 ("   is why it lands in COGS and not the wage bill.", None),
 ("   You set the weeks, the crew's HOURS per week, and a rate PER CROP. The solver picks", None),
 ("   which crops, how much, and when.", None),
 ("   ⚠️ CAPACITY IS HOURS, NOT POUNDS, and the grower found why. A crew picks pounds at a rate", None),
 ("   that differs 3.6x by crop, so one pound number is a crew that resizes with the crop:", None),
 ("   20,000 lb/wk is 200 hours of spinach, 150 of garlic, 55 of kale. It distorted the answer", None),
 ("   too — a pound cap rewards hours-per-pound, so it picked spinach over the cheaper garlic", None),
 ("   relief ($18.74/hr against $20.71). Moving it to hours triples the garlic picked.", None),
 ("", None),
 ("   ⚠️ RATES DIFFER BY CROP, AND THE LAW IS WHY. A piece-rate worker must still earn the", None),
 ("   minimum wage for the hours worked; if the rate falls short the employer makes up the", None),
 ("   difference (FLSA — the AEWR under H-2A). Converted to $/lb that floor depends entirely on", None),
 ("   how fast the crop picks: spinach $0.161/lb against kale $0.044/lb, a 3.6x spread from", None),
 ("   picking difficulty alone. A rate entered BELOW its floor is inoperative — you pay the", None),
 ("   floor — and the 'which binds' column says so. Garlic's shipped rate is below its floor on", None),
 ("   purpose, so you can see it happen.", None),
 ("", None),
 ("   ⚠️ THE PIECE-RATE CREW CHANGES THE HOURS YOU NEED, NOT THE WAGES YOU OWE. The committed", None),
 ("   crew is paid either way. Pounds picked convert to harvest hours relieved at each crop's", None),
 ("   own yield / harvest-hours — and the relief is capped by the harvest hours actually", None),
 ("   needed, or pickers would be relieving the planting.", None),
 ("", None),
 ("   Enter the rate as $ PER BUSHEL. The sheet converts with the crop's own m3-per-lb — the", None),
 ("   same number the storage rows use. ⚠️ That conversion is also a CHECK: 'lb per bushel' is", None),
 ("   something you can weigh, where m3-per-lb is not. A bushel of kale is about 18 lb in the", None),
 ("   trade; if this sheet says 9, the volume figure is wrong and the cooler is mis-sized too.", None),
 ("   See backlog L6.", None),
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
 ("  GREEN    the solver writes: the ACRES column ({ACRES_RANGE}), every OFFERED row, the contract SHORTFALL rows, and", None),
 ("           the PROFIT cell ({OBJ}).", None),
 ("  BLUE     the solver writes: the PLANT? binaries ({BIN_RANGE}).", None),
 ("  Everything else is a formula. Columns A-D stay put when you scroll right.", None),
 ("", None),
 ("HOW TO RUN IT", F_H1),
 ("SOLVER SETUP, at the foot of the Model sheet, lists every entry with exact ranges. In short:", None),
 ("   Tools > Solver, target the PROFIT cell, set to MAXIMUM", None),
 ("   Changing cells: {ACRES_RANGE} and {BIN_RANGE} together, plus EVERY OFFERED row, the labour", None),
 ("   rows and the contract SHORTFALL rows — leave the shortfalls out and an unmeetable contract", None),
 ("   becomes a hard floor, so the solver reports NO solution", None),
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
 ("       extra heads  {HIRECOST}      {EXTRA}", None),
 ("       piece rate   {PIECECOST}", None),
 ("       perennial    {PERCOST}      this year's cost of the blocks", None),
 ("       shortfall    {SHORTCOST}      the contract penalty", None),
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
 ("EXPERIMENT 2 — raise the contract penalties.  In 5d set both to $5.00, re-solve.", F_BOLD),
 ("     {FC0}", None),
 ("     {FC1}", None),
 ("   One shortfall that moves is a choice; one that does not is a fact — only the penalty tells them apart.", None),
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
 ("     Run it yourself:   .venv/bin/python toy_models/verify_toy_v12.py", None),
]
row_i = 1
for text, font in readme:
    for k, v in NUMS.items():
        text = text.replace(k, v)
    c = rd.cell(row=row_i, column=1, value=text)
    if font: c.font = font
    row_i += 1

# ⚠️ No placeholder may survive into the prose. v11 shipped five ({ADVCOST}, {ADVCREW}, ...)
# printed literally for two versions because the dict lost the keys and nothing looked.
import re as _re
_left = sorted({m for t, _ in readme for m in _re.findall(r"\{[A-Z_0-9]+\}", t)} - set(NUMS))
assert not _left, f"READ ME placeholders with no value: {_left}"

out = REPO / "toy_models" / "farm_toy_v12_fixed_layer.xlsx"
wb.save(out)
print(f"wrote {out}")
print(f"  successions offered : {len(SUCCS)}")
print(f"  decision cells      : {N_DEC_CELLS:,} ({DEC_BREAKDOWN})")
print(f"  solver recipe entries: {len(recipe)-1}")
