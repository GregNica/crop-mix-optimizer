"""
build_toy_v5.py — generates the FULL-CALENDAR toy model workbook (a MILP).

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
= 448 decision cells. Engine must be CoinMP (it handles integers; the plain linear solver does
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
import toy_v5_lp as LP

CROP_NAMES = LP.CROP_NAMES
crops = LP.CROPS
CH_NAMES = LP.CH_NAMES
SUCCS = LP.SUCCS
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

F_TITLE = Font(bold=True, size=15)
F_H1 = Font(bold=True, size=12, color="1F4E79")
F_BOLD = Font(bold=True)
F_NOTE = Font(italic=True, size=9, color="666666")
F_SMALL = Font(size=9)
IN_FILL = PatternFill("solid", fgColor="FFF2CC")
HDR_FILL = PatternFill("solid", fgColor="DDEBF7")
POOL_C = PatternFill("solid", fgColor="E8F0FE")
POOL_A = PatternFill("solid", fgColor="FFF0E6")
CH_FILL = [PatternFill("solid", fgColor="EDF7ED"), PatternFill("solid", fgColor="FDF2F8")]
DEC_FILL = PatternFill("solid", fgColor="D9EAD3")
ANNUAL_FILL = PatternFill("solid", fgColor="FCE5CD")   # an annual-cap row reads differently.
# NOT the input yellow: on this sheet yellow means "you type here", so tinting a FORMULA row
# with it invites the grower to type into a computed cell. The dead-input guard caught it,
# which is the guard doing a job it was not written for.
BIN_FILL = PatternFill("solid", fgColor="C9DAF8")
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
for c in (C_MAXA, C_MINA):
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


def constraint_triplet(r, label, lhs, cap_ref, fill, note):
    put(r, 1, label, font=F_BOLD, fill=fill); put(r, 2, "used", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), lhs(w), fmt="0.0", fill=fill)
    used = r; r += 1
    put(r, 1, "", font=F_BOLD)
    for w in range(1, 53):
        put(r, wcol(w), "<=", align="center", font=F_BOLD)
    r += 1
    put(r, 1, "  limit", font=F_BOLD); put(r, 2, "cap", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={cap_ref}", fmt="0.0")
    r += 1
    put(r, 1, "  room left", font=F_SMALL)
    for w in range(1, 53):
        put(r, wcol(w), f"={cap_ref}-{wl(w)}{used}", fmt="0.0")
    head = r; r += 1
    put(r, 1, note, font=F_NOTE); r += 2
    for rng, op, f in ((head, "lessThan", ["0"]), (used, "greaterThan", [cap_ref])):
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
put(r, 1, "FARM TOY MODEL — v5: the full calendar (a MILP)", font=F_TITLE)
put(r, 4, f"BUILT {_BUILT}   (from source at {_SHA})", font=F_NOTE)
r += 1
put(r, 1, "YELLOW = you type.  GREEN = the solver writes.  BLUE = the solver's plant/don't-plant "
          "switches.  Read the 'READ ME' sheet first.", font=F_NOTE); r += 2

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
                       "Shrink %/wk", "Growing $/acre", "Min acres if planted", "Harvest weeks"]):
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
    crop_row[name] = r; r += 1
put(r, 1, "'Min acres if planted' is what the plant/don't-plant switch enforces — see section 4.",
    font=F_NOTE); r += 2

# --- 3. crop x channel ---
put(r, 1, "3 — WHO BUYS IT   (one row per crop x channel — the grower's ruling)", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Channel", "Cap type", "Cap lb", "From wk", "To wk",
                       "Sell-through", "Returns to store", "Price $/lb"]):
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
        pair_row[(cname, hname)] = r; r += 1
r += 1

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
            put(r, wcol(w), PH[pbw[w]], align="center", font=F_SMALL,
                fill=PatternFill("solid", fgColor="F2F2F2"))
    # C9 / C10 helpers — the plant/don't-plant linkage, as columns the Solver can constrain
    put(r, wcol(52) + 1, f"=D{r}*$B${ROW_LAND}", fmt="0.0", font=F_SMALL)
    put(r, wcol(52) + 2, f"=D{r}*$I${crop_row[cn]}", fmt="0.0", font=F_SMALL)
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
        put(r, 1, f"{hname} — most you may sell this week", font=F_SMALL,
            fill=ANNUAL_FILL if is_annual else fill)
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
            put(r, wcol(w), 0, fmt="#,##0", fill=fill)     # placeholder; filled below
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

    put(r, 1, "Stock carried out", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
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

    put(r, 1, "Most stock its shelf life allows", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
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
            f'*POWER(1-$G${cr},{older}*({w}-{WKR})))', fmt="#,##0")
    R_SHELF = r; r += 1
    put(r, 1, "   Stock carried out must stay at or below this row.", font=F_NOTE); r += 1

    put(r, 1, "ROOM OCCUPANCY", font=F_BOLD); put(r, 2, "m3", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"=({wl(w)}{R_OPEN}+{wl(w)}{R_PACK})*$D${cr}", fmt="0.0",
            fill=POOL_C if pool == "Cold" else POOL_A)
    R_ROOM = r; r += 2
    crop_block[name] = dict(pack=R_PACK, open=R_OPEN, shrink=R_SHRINK, store=R_STORE,
                            close=R_CLOSE, room=R_ROOM, shelf=R_SHELF, pool=pool, ch=ch_rows)

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

# --- 7. the optimizer ---
put(r, 1, "7 — THE OPTIMIZER", font=F_H1); r += 1
put(r, 1, "Revenue", font=F_BOLD)
put(r, 2, "=" + "+".join(
    f"SUM({wl(1)}{crop_block[n]['ch'][h]['sold']}:{LAST}{crop_block[n]['ch'][h]['sold']})"
    f"*$I${pair_row[(n,h)]}" for n in CROP_NAMES for h in CH_NAMES), fmt="$#,##0", font=F_BOLD)
ROW_REV = r; r += 1
put(r, 1, "Growing cost", font=F_BOLD)
put(r, 2, f"=SUMPRODUCT({SR},"
          f"({CROPCOL}=\"{CROP_NAMES[0]}\")*$H${crop_row[CROP_NAMES[0]]}"
          + "".join(f"+({CROPCOL}=\"{n}\")*$H${crop_row[n]}" for n in CROP_NAMES[1:]) + ")",
    fmt="$#,##0", font=F_BOLD)
put(r, 3, "acres x $/acre, across every planting", font=F_NOTE)
ROW_COST = r; r += 1
put(r, 1, "PROFIT  (the objective)", font=F_BOLD, fill=DEC_FILL)
put(r, 2, f"=B{ROW_REV}-B{ROW_COST}", fmt="$#,##0", font=F_BOLD, fill=DEC_FILL)
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
    "{N_PLANTED}": str(_OPT["n_planted"]), "{N_OFFERED}": str(_OPT["n_offered"]),
    "{RELAX_PROFIT}": f"${_RELAX['profit']:,.0f}", "{RELAX_N}": str(_RELAX["n_planted"]),
    "{MIN_COST}": f"${_RELAX['profit'] - _OPT['profit']:,.0f}",
    "{V4_PROFIT}": "$1,094,831",
    "{N_DEC}": f"{len(SUCCS)*2 + len(CROP_NAMES)*len(CH_NAMES)*52:,}",
    "{N_SUCC}": str(len(SUCCS)),
    "{ACRES_RANGE}": f"C{ROW_SUCC}:C{ROW_SUCC_END}",
    "{BIN_RANGE}": f"D{ROW_SUCC}:D{ROW_SUCC_END}",
    "{OBJ}": f"B{ROW_OBJ}",
}
readme = [
 ("Farm toy model — v5: THE FULL CALENDAR", F_TITLE),
 (f"BUILT {_BUILT}   (from source at commit {_SHA})", F_NOTE),
 ("If that timestamp is older than the change you are looking for, you have a stale copy —", F_NOTE),
 ("close the file and re-open it from WSL rather than from a recent-files list.", F_NOTE),
 ("", None),
 ("WHAT v5 ADDS — both of these you spotted missing from v4", F_H1),
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
 ("{N_DEC} decision cells: {N_SUCC} acres + {N_SUCC} binaries + 312 offered. The engine MUST be", None),
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
 ("     PROFIT   {PROFIT}      = revenue {REV} - growing cost {COST}", F_BOLD),
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
 ("EXPERIMENT 2 — drop the minimum acreage.  Set every 'Min acres if planted' in the crop", F_BOLD),
 ("   table to 0 and re-solve.", F_BOLD),
 ("   Expect {RELAX_PROFIT} and {RELAX_N} plantings. The extra profit is real but the plan is", None),
 ("   not: it plants fractions of an acre no one would drive a tractor out for. This is what", None),
 ("   the binaries are FOR, and it is why the app carries them.", None),
 ("", None),
 ("EXPERIMENT 3 — take away the cooler.  Set the cold store to 40 m3 and re-solve.", F_BOLD),
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
 ("     Run it yourself:   .venv/bin/python toy_models/verify_toy_v5.py", None),
]
row_i = 1
for text, font in readme:
    for k, v in NUMS.items():
        text = text.replace(k, v)
    c = rd.cell(row=row_i, column=1, value=text)
    if font: c.font = font
    row_i += 1

out = REPO / "toy_models" / "farm_toy_v5_full_calendar.xlsx"
wb.save(out)
print(f"wrote {out}")
print(f"  successions offered : {len(SUCCS)}")
print(f"  decision cells      : {len(SUCCS)*2 + len(CROP_NAMES)*len(CH_NAMES)*52:,} "
      f"({len(SUCCS)} acres + {len(SUCCS)} binaries + {len(CROP_NAMES)*len(CH_NAMES)*52} offered)")
print(f"  solver recipe entries: {len(recipe)-1}")
