"""
build_toy_v4.py — generates the OPTIMIZER toy model workbook.

v4 SWITCHES THE OPTIMIZER ON. Everything before it was a calculator: you typed the acres and
I applied a fixed rule for who gets served first. That rule was mine, not the model's, and it
was doing real work — Wholesale's 30,000 lb/wk cap drained the garlic in two weeks, so Farmers
Market got 4,000 lb of a 12,000 lb window purely because of the order I chose.

Two changes make it solvable, and both are the lesson:

  1. EVERY MIN() IS GONE. `offered` is no longer computed — it is a DECISION CELL, bounded by
     constraints instead. MIN() is not linear, so a linear solver cannot use it; the real model
     has no "sold" formula for exactly this reason. This is that footnote becoming the design.
  2. THERE IS MONEY. An optimizer needs something to maximise. Prices per crop x channel and a
     growing cost per acre come from the app; the objective is revenue minus growing cost.

⚠️ NEEDS LIBREOFFICE CALC. 317 decision cells and ~780 constraints against Excel Solver's
ceiling of 200 and 100. Tools > Solver, engine "LibreOffice CoinMP Linear Solver". The exact
setup recipe is on the READ ME sheet.

v3 added the layer that answers "who is allowed to buy this, and how much?" — and with it the
grower's ruling of 2026-08-29 (DECISIONS E1):

    SELL-THROUGH IS PER CROP x CHANNEL.

Not farm-wide, not per-crop, not per-channel. A wholesaler orders, you deliver, you invoice —
there is no unsold portion, so sell-through is ~1.0 by construction. A market stall means
bringing a full display, so you always offer more than you sell — and whether the remainder is
LOST or merely DELAYED depends on the CROP. Only a crop-channel cell can hold that.

The companion field the ruling implies: `returns to store`. Garlic that does not sell at
Saturday's market goes back in the barn and sells next week. Spinach is compost.

  gross harvest --[pack-out]--> INTO THE STORE --[offered]--> market
                                     ^                          |
                                     +------[returns]-----------+
                                                                |
                                                          [sell-through] --> SOLD

Demand caps are the OTHER half, and the grower's framing is the one used here: the cap is the
demand PROJECTION and sell-through is the variance below it. Both weekly and annual caps are
modelled, because the app has both (C6 and C6b) and they read very differently — Garlic at
Farmers Market fills 50% of its annual appetite while sitting at 100% of its weekly ceiling in
every week it sells.

ALLOCATION IS NOW A RESULT, NOT A RULE. v3 filled the higher-priced channel first because a
calculator must. Measured, holding acres at 6: that rule earned $344,478 where optimal
allocation of the same stock earns $469,198 — and it loses while prioritising CORRECTLY,
because the real choice is not only who to serve but whether to serve anyone this week at all.
A greedy rule cannot decide to wait.

Output: farm_toy_v4_optimizer.xlsx
"""
import json
import sys
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

from farm_v2.utils.calendar import generate_successions, harvest_weeks_of
from farm_v2.utils.demand import build_demand_table, build_annual_caps

# ---------------------------------------------------------------------------
# Source data — read from the app, never retyped
# ---------------------------------------------------------------------------
payload = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
CROP_NAMES = ["Spinach", "Kale", "Garlic"]
crops = {c["name"]: c for c in payload["crops"] if c["name"] in CROP_NAMES}
channels = payload["channels"]

# Channel ORDER only decides which sub-block is drawn first; it no longer decides anything about
# the answer. In v1-v3 this ordering WAS the allocation rule.
CH_ORDER = sorted(channels, key=lambda ch: -max(
    crops[c].get("channels", {}).get(ch["name"], {}).get("price_per_lb", 0) for c in CROP_NAMES))
CH_NAMES = [ch["name"] for ch in CH_ORDER]

PICKED = ["Spinach W10", "Spinach W34", "Kale W12", "Kale W32", "Garlic W47"]
all_succ = {s["name"]: s for s in generate_successions(list(crops.values()), 2024)}
succs = [all_succ[n] for n in PICKED]

_dt = build_demand_table(list(crops.values()), CH_ORDER, 52)
_ac = build_annual_caps(list(crops.values()), CH_ORDER)


def cap_spec(crop_name, ch_name):
    """(type, value, first week, last week) for a crop-channel, read off the app's own tables."""
    ci = CROP_NAMES.index(crop_name)
    hi = CH_NAMES.index(ch_name)
    if (ci, hi) in _ac:
        return "Annual", float(_ac[(ci, hi)]), 1, 52
    row = _dt[ci, hi, 1:]
    weeks = [w + 1 for w in range(52) if row[w] > 0]
    if not weeks:
        return "Weekly", 0.0, 1, 52
    return "Weekly", float(row[weeks[0] - 1]), weeks[0], weeks[-1]


# Per the ruling: contract channels sell what they order; a stall does not. Returns follow the
# CROP's storability. ⚠️ These are placeholders pending sourcing — DECISIONS E1 flags that the
# rate ranges carry no citation yet and cannot ship as app defaults until they do.
def defaults(crop_name, ch_name):
    contract = ch_name.lower().startswith("wholesale")
    storable = not crops[crop_name].get("cold_storage", True)
    return (1.00 if contract else 0.85,          # sell-through
            0.00 if contract else (1.00 if storable else 0.00))   # returns to store


PACK_OUT = 1.00
COLD_CAP = payload["harvest_storage_cap"]
AMB_CAP = payload["ambient_storage_cap"]
TOTAL_LAND = payload["total_land"]

W0 = 3
wcol = lambda w: W0 + w - 1
wl = lambda w: get_column_letter(wcol(w))
LAST = get_column_letter(wcol(52))

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
DEC_FILL = PatternFill("solid", fgColor="D9EAD3")   # green = the solver writes here
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

wb = Workbook()
rd = wb.active
rd.title = "READ ME"
rd.column_dimensions["A"].width = 112
ws = wb.create_sheet("Model")
ws.column_dimensions["A"].width = 34
ws.column_dimensions["B"].width = 13
for w in range(1, 53):
    ws.column_dimensions[wl(w)].width = 8.5


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
    """LHS / '<=' / limit / room left — the original Group 5 model's own layout (rows 16-18)."""
    put(r, 1, label, font=F_BOLD, fill=fill)
    put(r, 2, "used", font=F_NOTE)
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


r = 1
put(r, 1, "FARM TOY MODEL — v3: channels + demand", font=F_TITLE); r += 1
put(r, 1, "Type in the YELLOW cells only. Read the 'READ ME' sheet first.", font=F_NOTE); r += 2

# --- 1. plantings ---
put(r, 1, "1 — WHAT YOU PLANT   (acres)", font=F_H1); r += 1
for j, h in enumerate(["Succession", "Acres", "Crop", "Harvest weeks", "gross lb/harvest wk per acre"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_SUCC = r
crop_row_pending = {n: ROW_SUCC + len(PICKED) + 5 + i for i, n in enumerate(CROP_NAMES)}
succ_meta = []
for s in succs:
    crop = crops[CROP_NAMES[s["crop"]]]
    nharv = max(1, len(harvest_weeks_of(s, 52)))
    put(r, 1, s["name"], border=True)
    put(r, 2, 6.0, fill=IN_FILL, fmt="0.0", border=True)
    put(r, 3, crop["name"], border=True)
    put(r, 4, ", ".join("W%d" % w for w in harvest_weeks_of(s, 52)), font=F_SMALL, border=True)
    put(r, 5, f'=$B${crop_row_pending[crop["name"]]}/{nharv}', fmt="#,##0", border=True)
    succ_meta.append({"row": r, "s": s, "crop": crop["name"], "nharv": nharv})
    r += 1
put(r, 1, "Total acres planted", font=F_BOLD)
put(r, 2, f"=SUM(B{ROW_SUCC}:B{r-1})", font=F_BOLD, fmt="0.0")
put(r, 3, "sum of the five above — they overlap in time, so this is NOT peak land use", font=F_NOTE)
r += 1
put(r, 1, "Land you have", font=F_BOLD)
put(r, 2, TOTAL_LAND, fill=IN_FILL, fmt="0.0", border=True); ROW_LAND = r
put(r, 3, "acres", font=F_NOTE); r += 2

# --- 2. crop settings ---
put(r, 1, "2 — HOW EACH CROP BEHAVES", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Yield lb/acre", "Pack-out", "m3 per lb", "Store",
                       "Shelf life wk", "Shrink %/wk", "Growing cost $/acre"]):
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
    assert crop_row_pending[name] == r, f"reserved row {crop_row_pending[name]} for {name}, wrote {r}"
    crop_row[name] = r
    r += 1
put(r, 1, "SELL-THROUGH IS NOT HERE — it is per crop x CHANNEL, in section 3. Grower ruling, "
          "2026-08-29.", font=F_NOTE)
r += 2

# --- 3. crop x channel ---
put(r, 1, "3 — WHO BUYS IT, AND HOW MUCH   (one row per crop x channel)", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Channel", "Cap type", "Cap lb", "From wk", "To wk",
                       "Sell-through", "Returns to store", "Price $/lb"]):
    put(r, 1 + j, h, font=F_BOLD, fill=HDR_FILL, border=True)
r += 1
ROW_PAIR = r
pair_row = {}
for ci, cname in enumerate(CROP_NAMES):
    for hi, hname in enumerate(CH_NAMES):
        ctype, cval, w0, w1 = cap_spec(cname, hname)
        st, ret = defaults(cname, hname)
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
        pair_row[(cname, hname)] = r
        r += 1
put(r, 1, "Cap type 'Weekly' = that many lb every week between From and To. 'Annual' = that many "
          "lb across the whole year.", font=F_NOTE); r += 1
put(r, 1, f"Channels are filled in this order: {' then '.join(CH_NAMES)} — highest price first. "
          f"THE REAL MODEL DECIDES THIS BY MARGIN; a calculator needs a fixed rule.", font=F_NOTE)
r += 2

# --- 4. storage caps ---
put(r, 1, "4 — WHAT YOU CAN STORE", font=F_H1); r += 1
put(r, 1, "Cold store (cooler) capacity", border=True)
put(r, 2, COLD_CAP, fill=IN_FILL, fmt="#,##0", border=True); ROW_COLDCAP = r
put(r, 3, "m3   — Spinach, Kale", font=F_NOTE); r += 1
put(r, 1, "Ambient store (barn) capacity", border=True)
put(r, 2, AMB_CAP, fill=IN_FILL, fmt="#,##0", border=True); ROW_AMBCAP = r
put(r, 3, "m3   — Garlic", font=F_NOTE); r += 2

# --- 5. the year ---
put(r, 1, "5 — THE YEAR, WEEK BY WEEK", font=F_H1); r += 1
ROW_WEEKNUM = r
r = week_header(r)
ws.freeze_panes = "C1"

put(r, 1, "PLANTING CALENDAR", font=F_BOLD); r += 1
PH = {0: "P", 1: "G", 2: "H"}
succ_harv_row = {}
for m in succ_meta:
    s = m["s"]
    pbw = {((wk - 1) % 52) + 1: ph for wk, ph in zip(s["weeks"], s["phases"])}
    put(r, 1, s["name"], font=F_SMALL); put(r, 2, "P/G/H", font=F_NOTE)
    for w in range(1, 53):
        if w in pbw:
            put(r, wcol(w), PH[pbw[w]], align="center", font=F_SMALL,
                fill=PatternFill("solid", fgColor="F2F2F2"))
    m["phase_row"] = r; r += 1
    put(r, 1, "   lbs harvested (GROSS)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f'=IF({wl(w)}{m["phase_row"]}="H",$B${m["row"]}*$B${crop_row[m["crop"]]}'
                        f'/{m["nharv"]},0)', fmt="#,##0")
    succ_harv_row.setdefault(m["crop"], []).append(r); r += 1
put(r, 1, "P = planting   G = growing   H = harvesting.  GROSS pounds off the field.", font=F_NOTE)
r += 2

r = week_header(r, "acres")
land_lhs = lambda w: "=" + "+".join(
    f'IF({wl(w)}{m["phase_row"]}<>"",$B${m["row"]},0)' for m in succ_meta)
r, ROW_LANDUSED, _ = constraint_triplet(
    r, "LAND in the ground", land_lhs, f"$B${ROW_LAND}", None,
    "   Acres standing that week. Plantings overlap, so the five acre figures can sum past your "
    "land and still be legal — only a single WEEK can break it.")

# --- per crop ---
crop_block = {}
for name in CROP_NAMES:
    cr = crop_row[name]
    pool = "Cold" if crops[name].get("cold_storage", True) else "Ambient"
    put(r, 1, f"{name.upper()}  —  {pool.lower()} store", font=F_H1)
    put(r, 2, "", fill=POOL_C if pool == "Cold" else POOL_A); r += 1
    r = week_header(r)

    put(r, 1, "Harvested (gross)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), "=" + "+".join(f"{wl(w)}{hr}" for hr in succ_harv_row[name]), fmt="#,##0")
    R_GROSS = r; r += 1
    put(r, 1, "   field cull (never cooled)", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_GROSS}*(1-$C${cr})", fmt="#,##0")
    R_CULL = r; r += 1
    put(r, 1, "Packed out -> INTO the store", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_GROSS}*$C${cr}", fmt="#,##0")
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

    ch_rows = {}
    prior_consumed = []
    for hi, hname in enumerate(CH_NAMES):
        pr = pair_row[(name, hname)]
        fill = CH_FILL[hi]
        put(r, 1, f"{hname} — weekly ceiling", font=F_SMALL, fill=fill); put(r, 2, "lb", font=F_NOTE)
        R_CAP = r
        for w in range(1, 53):
            # An ANNUAL-cap pair has NO weekly ceiling — the app emits no C6 row for it at all.
            # Writing the annual figure here keeps one uniform "sold <= ceiling" constraint range
            # for every pair while never binding weekly; the real limit is the yearly total
            # constrained separately below, which is exactly C6b.
            weekly = f"IF(AND({wl(w)}${ROW_WEEKNUM}>=$E${pr},{wl(w)}${ROW_WEEKNUM}<=$F${pr}),$D${pr},0)"
            put(r, wcol(w), f'=IF($C${pr}="Annual",$D${pr},{weekly})', fmt="#,##0", fill=fill)
        r += 1
        put(r, 1, f"{hname} — OFFERED", font=F_BOLD, fill=DEC_FILL)
        put(r, 2, "lb  <-- SOLVER", font=F_NOTE)
        R_OFF = r
        for w in range(1, 53):
            # A DECISION CELL. No formula, no MIN(). v1-v3 computed this as
            # MIN(what is in store, what the buyer will take) — which is not linear, so no linear
            # solver can use it. The real model does exactly what this row now does: makes the
            # quantity a variable and lets CONSTRAINTS bound it. That is why farm_v2 has no
            # "sold" formula anywhere.
            put(r, wcol(w), 0.0, fmt="#,##0", fill=DEC_FILL)
        r += 1
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
        put(r, 1, "   consumed from store", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
        for w in range(1, 53):
            put(r, wcol(w), f"={wl(w)}{R_OFF}-{wl(w)}{R_RET}", fmt="#,##0")
        R_CON = r; r += 1
        prior_consumed.append(R_CON)
        ch_rows[hname] = dict(cap=R_CAP, off=R_OFF, sold=R_SOLD, ml=R_ML, ret=R_RET, con=R_CON)

    put(r, 1, "Stock carried out", font=F_BOLD); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"={wl(w)}{R_STORE}" + "".join(f"-{wl(w)}{pc}" for pc in prior_consumed),
            fmt="#,##0")
    R_CLOSE = r; r += 1
    for w in range(1, 53):
        ws.cell(row=R_OPEN, column=wcol(w),
                value=(0 if w == 1 else f"={wl(w-1)}{R_CLOSE}")).number_format = "#,##0"
    ws.cell(row=R_OPEN, column=2, value="lb").font = F_NOTE

    put(r, 1, "ROOM OCCUPANCY", font=F_BOLD); put(r, 2, "m3", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w), f"=({wl(w)}{R_OPEN}+{wl(w)}{R_PACK})*$D${cr}", fmt="0.0",
            fill=POOL_C if pool == "Cold" else POOL_A)
    R_ROOM = r; r += 1
    put(r, 1, "   = carried in + everything PACKED OUT this week, before any of it ships.", font=F_NOTE)
    r += 1
    put(r, 1, "Over shelf life?", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
    for w in range(1, 53):
        put(r, wcol(w),
            f'=MAX(0,{wl(w)}{R_CLOSE}-SUMIFS(${wl(1)}${R_PACK}:${LAST}${R_PACK},'
            f'${wl(1)}${ROW_WEEKNUM}:${LAST}${ROW_WEEKNUM},">="&{wl(w)}${ROW_WEEKNUM}-$F${cr}+2,'
            f'${wl(1)}${ROW_WEEKNUM}:${LAST}${ROW_WEEKNUM},"<="&{wl(w)}${ROW_WEEKNUM}))', fmt="#,##0")
    R_OLD = r; r += 1
    put(r, 1, "   stock older than its shelf life — WARNING here, a hard constraint in the app",
        font=F_NOTE); r += 2
    crop_block[name] = dict(gross=R_GROSS, cull=R_CULL, pack=R_PACK, open=R_OPEN, shrink=R_SHRINK,
                            store=R_STORE, close=R_CLOSE, room=R_ROOM, old=R_OLD, pool=pool,
                            ch=ch_rows)

# --- 6. stores ---
put(r, 1, "6 — THE TWO STORES", font=F_H1); r += 1
pool_rows = {}
for pool, cap_row, fill in (("Cold", ROW_COLDCAP, POOL_C), ("Ambient", ROW_AMBCAP, POOL_A)):
    members = [n for n in CROP_NAMES if crop_block[n]["pool"] == pool]
    r = week_header(r, "m3")
    lhs = (lambda mem: (lambda w: "=" + "+".join(f"{wl(w)}{crop_block[n]['room']}" for n in mem)))(members)
    r, used, head = constraint_triplet(r, f"{pool.upper()} STORE", lhs, f"$B${cap_row}", fill,
                                       f"   Holds {', '.join(members)}. RED = the app refuses this plan.")
    pool_rows[pool] = dict(used=used, head=head, cap=cap_row)

# --- 7. summary ---
put(r, 1, "7 — WHAT THIS PLAN DOES", font=F_H1); r += 1


def summary(label, formula, fmt="#,##0", note="", bold=False):
    global r
    put(r, 1, label, font=F_BOLD if bold else None)
    put(r, 2, formula, fmt=fmt, font=F_BOLD if bold else None)
    if note: put(r, 3, note, font=F_NOTE)
    r += 1


summary("Peak COLD store used", f"=MAX({wl(1)}{pool_rows['Cold']['used']}:{LAST}{pool_rows['Cold']['used']})",
        "0.0", f"m3 against {COLD_CAP}", bold=True)
summary("Peak AMBIENT store used", f"=MAX({wl(1)}{pool_rows['Ambient']['used']}:{LAST}{pool_rows['Ambient']['used']})",
        "0.0", f"m3 against {AMB_CAP}", bold=True)
r += 1
for name in CROP_NAMES:
    b = crop_block[name]
    summary(f"{name} — harvested (gross)", f"=SUM({wl(1)}{b['gross']}:{LAST}{b['gross']})", "#,##0", "lb")
    summary(f"{name} — packed out", f"=SUM({wl(1)}{b['pack']}:{LAST}{b['pack']})", "#,##0",
            "lb — what the store has to hold")
    for hname in CH_NAMES:
        cb = b["ch"][hname]
        pr = pair_row[(name, hname)]
        summary(f"   {hname} — SOLD", f"=SUM({wl(1)}{cb['sold']}:{LAST}{cb['sold']})", "#,##0",
                "lb", bold=True)
        summary(f"   {hname} — fill of the cap",
                f'=IF($C${pr}="Annual",SUM({wl(1)}{cb["sold"]}:{LAST}{cb["sold"]})/$D${pr},'
                f'SUM({wl(1)}{cb["sold"]}:{LAST}{cb["sold"]})/SUM({wl(1)}{cb["cap"]}:{LAST}{cb["cap"]}))',
                "0%", "of the year's appetite")
        summary(f"   {hname} — market loss", f"=SUM({wl(1)}{cb['ml']}:{LAST}{cb['ml']})", "#,##0",
                "lb gone")
        summary(f"   {hname} — returned to store", f"=SUM({wl(1)}{cb['ret']}:{LAST}{cb['ret']})",
                "#,##0", "lb came home and sold later")
    summary(f"{name} — left at year end", f"={LAST}{b['close']}", "#,##0", "lb stranded")
    r += 1

# ---------------------------------------------------------------------------
# 8 — THE OPTIMIZER: objective, annual totals, and the exact Solver recipe
# ---------------------------------------------------------------------------
put(r, 1, "8 — THE OPTIMIZER", font=F_H1); r += 1
put(r, 1, "Everything below is what LibreOffice's Solver needs. Nothing here is typed by you.",
    font=F_NOTE); r += 2

put(r, 1, "Revenue", font=F_BOLD)
rev_terms = "+".join(f"SUM({wl(1)}{crop_block[n]['ch'][h]['sold']}:{LAST}"
                     f"{crop_block[n]['ch'][h]['sold']})*$I${pair_row[(n,h)]}"
                     for n in CROP_NAMES for h in CH_NAMES)
put(r, 2, f"={rev_terms}", fmt="$#,##0", font=F_BOLD)
put(r, 3, "pounds sold x price, summed over every crop x channel", font=F_NOTE)
ROW_REV = r; r += 1
put(r, 1, "Growing cost", font=F_BOLD)
cost_terms = "+".join(f"$B${m['row']}*$H${crop_row[m['crop']]}" for m in succ_meta)
put(r, 2, f"={cost_terms}", fmt="$#,##0", font=F_BOLD)
put(r, 3, "acres x growing cost per acre, for every planting", font=F_NOTE)
ROW_COST = r; r += 1
put(r, 1, "PROFIT  (the objective)", font=F_BOLD, fill=DEC_FILL)
put(r, 2, f"=B{ROW_REV}-B{ROW_COST}", fmt="$#,##0", font=F_BOLD, fill=DEC_FILL)
put(r, 3, "<-- MAXIMISE THIS CELL", font=F_BOLD)
ROW_OBJ = r; r += 2

put(r, 1, "Annual caps — total sold vs the year's allowance", font=F_BOLD); r += 1
annual_rows = []
for n in CROP_NAMES:
    for h in CH_NAMES:
        pr = pair_row[(n, h)]
        if ws.cell(row=pr, column=3).value != "Annual":
            continue
        sold_r = crop_block[n]["ch"][h]["sold"]
        put(r, 1, f"   {n} / {h} — sold all year", font=F_SMALL)
        put(r, 2, f"=SUM({wl(1)}{sold_r}:{LAST}{sold_r})", fmt="#,##0")
        put(r, 3, "<=", align="center", font=F_BOLD)
        put(r, 4, f"=$D${pr}", fmt="#,##0")
        put(r, 5, "lb  — this is the app's C6b, the only row an annual-cap pair gets", font=F_NOTE)
        annual_rows.append(r); r += 1
if not annual_rows:
    put(r, 1, "   (none)", font=F_NOTE); r += 1
r += 1

# --- the recipe, on the sheet so it travels with the file ---
put(r, 1, "SOLVER SETUP — Tools > Solver", font=F_H1); r += 1
recipe = [
    ("Target cell", f"$B${ROW_OBJ}", "set to MAXIMUM"),
    ("By changing cells", "$B$%d:$B$%d" % (ROW_SUCC, ROW_SUCC + len(succ_meta) - 1),
     "the acres — one per planting"),
    ("  ...and", ";".join(f"${wl(1)}${crop_block[n]['ch'][h]['off']}:${LAST}$"
                          f"{crop_block[n]['ch'][h]['off']}"
                          for n in CROP_NAMES for h in CH_NAMES),
     "every OFFERED row (the green cells)"),
]
for n in CROP_NAMES:
    for h in CH_NAMES:
        cb = crop_block[n]["ch"][h]
        recipe.append((f"Constraint — {n}/{h} sold <= ceiling",
                       f"${wl(1)}${cb['sold']}:${LAST}${cb['sold']}  <=  "
                       f"${wl(1)}${cb['cap']}:${LAST}${cb['cap']}", ""))
for n in CROP_NAMES:
    recipe.append((f"Constraint — {n} stock never negative",
                   f"${wl(1)}${crop_block[n]['close']}:${LAST}${crop_block[n]['close']}  >=  0",
                   "you cannot sell what you do not have"))
recipe += [
    ("Constraint — cold store",
     f"${wl(1)}${pool_rows['Cold']['used']}:${LAST}${pool_rows['Cold']['used']}  <=  $B${ROW_COLDCAP}", ""),
    ("Constraint — ambient store",
     f"${wl(1)}${pool_rows['Ambient']['used']}:${LAST}${pool_rows['Ambient']['used']}  <=  $B${ROW_AMBCAP}", ""),
    ("Constraint — land",
     f"${wl(1)}${ROW_LANDUSED}:${LAST}${ROW_LANDUSED}  <=  $B${ROW_LAND}", ""),
]
for row_ in annual_rows:
    recipe.append((f"Constraint — annual cap", f"$B${row_}  <=  $D${row_}", ""))
recipe.append(("Options", "engine = LibreOffice CoinMP Linear Solver",
               "tick 'Assume variables as non-negative'"))
for label, val, note in recipe:
    put(r, 1, label, font=F_BOLD if label.startswith(("Target", "By changing", "Options")) else F_SMALL)
    put(r, 2, val, font=F_SMALL)
    if note: put(r, 6, note, font=F_NOTE)
    r += 1
put(r, 1, f"{len(recipe)-1} entries in total — the 780 underlying constraints collapse into ranges.",
    font=F_NOTE)
r += 2

# ===========================================================================
# Numbers the READ ME promises — COMPUTED, never typed.
#
# An earlier version wrote them by hand and three shipped 0.1 out from rounding while the prose
# was being written. Same class as a frozen cell beside a live one: a figure written next to its
# source instead of derived from it. verify_toy_v4.py section D closes the loop by checking that
# what this document promises equals what the workbook computes.
# ===========================================================================
from toy_v4_lp import solve as _lp_solve, greedy as _lp_greedy   # noqa: E402

# The optimum LibreOffice should find, and the fixed-rule answer it beats. COMPUTED with
# scipy.milp — the same HiGHS wrapper farm_v2/solver.py uses — so the READ ME cannot promise a
# number the model does not produce, and the comparison cannot go stale.
_OPT = _lp_solve()
_FIX = _lp_solve(fixed_acres=6.0)
_GRD = _lp_greedy(6.0)
_land = [0.0] * 53
for m in succ_meta:
    for wk in m["s"]["weeks"]:
        _land[((wk - 1) % 52) + 1] += _OPT["acres"][m["s"]["name"]]

NUMS = {
    "{OPT_PROFIT}": f"${_OPT['profit']:,.0f}",
    "{OPT_REV}": f"${_OPT['revenue']:,.0f}",
    "{OPT_COST}": f"${_OPT['cost']:,.0f}",
    "{OPT_LAND}": f"{max(_land[1:]):.1f}",
    "{GRD_PROFIT}": f"${_GRD['profit']:,.0f}",
    "{FIX_PROFIT}": f"${_FIX['profit']:,.0f}",
    "{ALLOC_GAIN}": f"${_FIX['profit'] - _GRD['profit']:,.0f}",
    "{ALLOC_PCT}": f"{(_FIX['profit'] / _GRD['profit'] - 1) * 100:.0f}%",
    "{ACRE_GAIN}": f"${_OPT['profit'] - _FIX['profit']:,.0f}",
    "{CH1}": CH_NAMES[0], "{CH2}": CH_NAMES[1],
    "{N_DEC}": f"{len(succ_meta) + len(CROP_NAMES) * len(CH_NAMES) * 52:,}",
}
for n in CROP_NAMES:
    NUMS[f"{{{n.upper()}_ACRES}}"] = f"{sum(v for k, v in _OPT['acres'].items() if k.startswith(n)):.1f}"
    for h in CH_NAMES:
        tag = f"{n.upper()}_{'FM' if h.startswith('Farmers') else 'WS'}"
        NUMS[f"{{{tag}_OPT}}"] = f"{_OPT['sold'][(n, h)]:,.0f}"
        NUMS[f"{{{tag}_GRD}}"] = f"{_GRD['sold'][(n, h)]:,.0f}"
        NUMS[f"{{{tag}_FIX}}"] = f"{_FIX['sold'][(n, h)]:,.0f}"

GARLIC_PAIR_FM = pair_row[("Garlic", [h for h in CH_NAMES if h.startswith("Farmers")][0])]
SPIN_PAIR_FM = pair_row[("Spinach", [h for h in CH_NAMES if h.startswith("Farmers")][0])]
COORDS = {"{ACRES}": f"B{ROW_SUCC}:B{ROW_SUCC+len(succ_meta)-1}",
          "{G_RET}": f"H{GARLIC_PAIR_FM}", "{G_ST}": f"G{GARLIC_PAIR_FM}",
          "{S_ST}": f"G{SPIN_PAIR_FM}", "{S_RET}": f"H{SPIN_PAIR_FM}",
          "{PAIRS}": f"A{ROW_PAIR}:I{ROW_PAIR+len(pair_row)-1}",
          "{G_PRICE}": f"I{GARLIC_PAIR_FM}", "{COLDCAP}": f"B{ROW_COLDCAP}",
          "{OBJ}": f"B{ROW_OBJ}"}

readme = [
 ("Farm toy model — v4: THE OPTIMIZER", F_TITLE),
 ("", None),
 ("!! THIS ONE NEEDS LIBREOFFICE CALC, NOT EXCEL", F_H1),
 ("{N_DEC} decision cells and about 780 constraints. Excel's Solver stops at 200 and 100 — over", None),
 ("by 1.6x and 7.8x. LibreOffice's CoinMP engine has no such ceiling.", None),
 ("Right-click the file, Open with > LibreOffice Calc. Excel stays your default for everything", None),
 ("else.", None),
 ("", None),
 ("WHAT CHANGED, AND WHY IT IS THE WHOLE POINT", F_H1),
 ("v1 to v3 were CALCULATORS. You typed the acres and I applied a fixed rule for who gets served", None),
 ("first: highest price, up to that channel's weekly ceiling, then the next. Every allocation", None),
 ("number you have seen so far was MY RULE, not the model's answer.", None),
 ("", None),
 ("v4 hands both decisions to a solver: how many acres of each planting, and how many pounds go", None),
 ("to each channel in each of the 52 weeks.", None),
 ("", None),
 ("Two things had to change to make that possible.", None),
 ("", None),
 ("1. EVERY MIN() IS GONE. 'Offered' used to be MIN(what is in store, what the buyer will take).", F_BOLD),
 ("   MIN is not linear, so no linear solver can use it. Those rows are now GREEN — they are", None),
 ("   decision cells the solver writes into, bounded by constraints instead of by a formula.", None),
 ("   This is exactly why farm_v2 has no 'sold' formula anywhere: it makes pounds sold a", None),
 ("   variable and bounds it with C6/C6b. The footnote in the last two READ MEs is now the", None),
 ("   design.", None),
 ("", None),
 ("2. THERE IS MONEY NOW. A solver needs something to maximise. Prices per crop x channel and a", F_BOLD),
 ("   growing cost per acre come from your app. Objective = revenue - growing cost.", None),
 ("", None),
 ("WHERE THINGS ARE", F_H1),
 ("  YELLOW cells   things you type: the acre cells ({ACRES}), the crop settings, and the", None),
 ("                 crop x channel table ({PAIRS}) where sell-through and returns live.", None),
 ("  GREEN cells    the OFFERED rows and the PROFIT cell ({OBJ}) — the solver writes these.", None),
 ("                 Do not type in them; whatever you put there is overwritten on the next run.", None),
 ("  Everything else is a formula.", None),
 ("", None),
 ("WHAT YOU WILL SEE WHEN YOU OPEN IT", F_H1),
 ("Every OFFERED cell is 0, so nothing sells and the PROFIT cell is negative — it is just the", None),
 ("growing cost of whatever acres are typed in. That is correct and expected. The sheet is a", None),
 ("QUESTION until you run the Solver.", None),
 ("", None),
 ("HOW TO RUN IT", F_H1),
 ("Section 8 of the Model sheet lists every entry, with the exact ranges. In short:", None),
 ("   Tools > Solver", None),
 ("   Target cell     the PROFIT cell in section 8, set to MAXIMUM", None),
 ("   Changing cells  the acres, plus all six green OFFERED rows", None),
 ("   Constraints     about 15 entries, each a RANGE (the 780 underlying rows collapse into", None),
 ("                   ranges, so this is a five-minute dialog fill, not 780 of anything)", None),
 ("   Options         engine = LibreOffice CoinMP Linear Solver", None),
 ("                   tick 'Assume variables as non-negative'", None),
 ("", None),
 ("WHAT IT SHOULD FIND", F_H1),
 ("     PROFIT   {OPT_PROFIT}      = revenue {OPT_REV} - growing cost {OPT_COST}", F_BOLD),
 ("     Acres    Spinach {SPINACH_ACRES}   Kale {KALE_ACRES}   Garlic {GARLIC_ACRES}", None),
 ("     Peak land in the ground {OPT_LAND} acres", None),
 ("", None),
 ("     sold, lb        {CH1}      {CH2}", None),
 ("       Spinach       {SPINACH_FM_OPT}          {SPINACH_WS_OPT}", None),
 ("       Kale          {KALE_FM_OPT}          {KALE_WS_OPT}", None),
 ("       Garlic        {GARLIC_FM_OPT}          {GARLIC_WS_OPT}", None),
 ("", None),
 ("These come from solving the SAME model in Python with scipy.milp — the identical HiGHS", None),
 ("solver your app runs. If CoinMP lands somewhere materially different, one of the two models", None),
 ("is not the model we think it is, and that is worth knowing. A few dollars apart is just", None),
 ("tolerances.", None),
 ("", None),
 ("!! WHAT MY FILL RULE WAS COSTING — the reason v4 exists", F_H1),
 ("Hold the acres at 6 per planting, exactly as in v3, and change NOTHING except who decides", None),
 ("the allocation:", None),
 ("", None),
 ("     my fixed rule      {GRD_PROFIT}", F_BOLD),
 ("     the optimizer      {FIX_PROFIT}       +{ALLOC_GAIN}  ({ALLOC_PCT})", F_BOLD),
 ("", None),
 ("Same plan, same crops, same stock, same caps. The allocation alone is worth {ALLOC_PCT}.", None),
 ("", None),
 ("And here is the part I did not expect. The optimizer sells FEWER total pounds than my rule", F_BOLD),
 ("and still makes more money.", F_BOLD),
 ("", None),
 ("     Garlic at {CH1}     my rule {GARLIC_FM_GRD} lb   ->   optimizer {GARLIC_FM_FIX} lb", None),
 ("     Kale at {CH1}        my rule {KALE_FM_GRD} lb   ->   optimizer {KALE_FM_FIX} lb", None),
 ("     Spinach at {CH1}     my rule {SPINACH_FM_GRD} lb   ->   optimizer {SPINACH_FM_FIX} lb", None),
 ("", None),
 ("My rule served the expensive channel FIRST, which is the obvious right priority — and it", None),
 ("still lost, because the real choice is not only WHO to serve. It is whether to serve anyone", None),
 ("THIS week at all. A greedy rule dumps the surplus into the cheap channel now; the optimizer", None),
 ("holds it in store and sells it to the expensive one later. No fixed rule can see that,", None),
 ("because it depends on what happens in weeks that have not arrived yet.", None),
 ("", None),
 ("That is what an optimizer buys you, and it is why the app has one.", None),
 ("", None),
 ("Then let it choose the acres as well and profit goes to {OPT_PROFIT} — another {ACRE_GAIN}.", None),
 ("But treat that number with suspicion: with no land rent, no labour, no water and no cash", None),
 ("limit, growing more is nearly free here. Which is precisely the M1 problem in your real app,", None),
 ("reproduced in miniature.", None),
 ("", None),
 ("THREE THINGS TO TRY — each one, re-solve and watch the PLAN change", F_H1),
 ("This is the part a calculator could never do. You are not changing an answer now; you are", None),
 ("changing the QUESTION and getting a different answer back.", None),
 ("", None),
 ("EXPERIMENT 1 — make garlic perishable.  Set Garlic's 'Returns to store' at {CH1} ({G_RET})", F_BOLD),
 ("   from 1.00 to 0.00, then re-run the Solver.", F_BOLD),
 ("   In v3 this changed some totals. Here it changes the FARM: unsold garlic is no longer", None),
 ("   recoverable, so offering it at the stall becomes a gamble and the optimizer rebalances", None),
 ("   how much garlic to plant at all. Compare acres before and after.", None),
 ("", None),
 ("EXPERIMENT 2 — take the cooler away.  Set the cold store capacity ({COLDCAP}) to 40 m3 and", F_BOLD),
 ("   re-solve.", F_BOLD),
 ("   Watch which crop it abandons. It will not be the least profitable one — it will be the one", None),
 ("   whose profit per CUBIC METRE OF COOLER is worst. That is a ranking no spreadsheet column", None),
 ("   shows you, and it is why 'which crop is most profitable' is the wrong question.", None),
 ("", None),
 ("EXPERIMENT 3 — pay more at the stall.  Raise Garlic's price at {CH1} ({G_PRICE}) and re-solve.", F_BOLD),
 ("   Nothing happens for a while, then the whole plan jumps. Constraints are cliffs, not slopes:", None),
 ("   right up until the moment garlic outbids something for the same acre-week, the answer is", None),
 ("   identical. This is why sensitivity has to be MEASURED and cannot be reasoned about.", None),
 ("", None),
 ("If a run comes back with everything zero, the Solver did not find a feasible plan — check", None),
 ("that 'Assume variables as non-negative' is ticked and that the engine is CoinMP.", None),
 ("", None),
 ("WHAT v4 STILL DOES NOT CARRY", F_H1),
 ("  - Costs are seed/transplant per acre ONLY. No labour, water, fuel, packaging, storage or", None),
 ("    overhead. So the profit figure is far too high, deliberately — v5 adds the cash layer.", None),
 ("  - No cash-flow constraint, so it can spend money it does not have.", None),
 ("  - Shelf life is still a WARNING, not enforced.", None),
 ("  - Three crops and five plantings, against seven and 220 on the real farm.", None),
 ("", None),
 ("!! THE SCALE WARNING — it matters more here than anywhere", F_H1),
 ("Small models are TIGHT, large ones LOOSE. An optimizer's answer is far more scale-sensitive", None),
 ("than a calculator's: which constraints bind, and therefore which crop wins, can invert", None),
 ("entirely between 3 crops and 7. Do not read this plan as advice about your farm. Read it as", None),
 ("a demonstration of what the machinery does.", None),
 ("", None),
 ("HAS THIS SHEET BEEN CHECKED?", F_H1),
 ("Yes, and v4 adds a check the others could not have. Crop constants, planting dates and demand", None),
 ("caps are read from the app. The formulas are calculated by an engine and compared cell by", None),
 ("cell against an independent model. Every input is perturbed to prove it propagates. No number", None),
 ("is frozen. AND: the same LP is solved with scipy.milp, its answer written into the OFFERED", None),
 ("cells, and the sheet's own PROFIT cell must reproduce the optimum exactly — which proves the", None),
 ("spreadsheet and the solver are the same problem.", None),
 ("     Run it yourself:   .venv/bin/python toy_models/verify_toy_v4.py", None),
]
row_i = 1
for text, font in readme:
    for k, v in {**COORDS, **NUMS}.items():
        text = text.replace(k, v)
    c = rd.cell(row=row_i, column=1, value=text)
    if font: c.font = font
    row_i += 1

# --- crop data sheet ---
cd = wb.create_sheet("Crop data")
cd.column_dimensions["A"].width = 30
for col in "BCDE":
    cd.column_dimensions[col].width = 18
cd.cell(row=1, column=1, value="Read from the app — nothing retyped").font = F_TITLE
cd.cell(row=2, column=1, value="tests/golden/default_farm_payload.json + "
        "farm_v2.utils.calendar/demand").font = F_NOTE
rr = 4
for j, h in enumerate(["Field", "Spinach", "Kale", "Garlic"]):
    c = cd.cell(row=rr, column=1 + j, value=h); c.font = F_BOLD; c.fill = HDR_FILL
rr += 1
for key in ("yield_per_acre", "crop_size_m3_per_lb", "cold_storage", "days_to_maturity",
            "planting_weeks", "harvest_weeks", "overwinters"):
    cd.cell(row=rr, column=1, value=key).font = F_BOLD
    for j, n in enumerate(CROP_NAMES):
        cd.cell(row=rr, column=2 + j, value=str(crops[n].get(key, "")))
    rr += 1
rr += 1
cd.cell(row=rr, column=1, value="Demand caps — via the app's own helpers").font = F_H1
rr += 1
for j, h in enumerate(["Crop", "Channel", "Type", "lb", "Weeks"]):
    c = cd.cell(row=rr, column=1 + j, value=h); c.font = F_BOLD; c.fill = HDR_FILL
rr += 1
for n in CROP_NAMES:
    for h in CH_NAMES:
        t, v, a, b_ = cap_spec(n, h)
        for j, val in enumerate([n, h, t, v, f"W{a}-W{b_}"]):
            cd.cell(row=rr, column=1 + j, value=val)
        rr += 1

out = REPO / "toy_models" / "farm_toy_v4_optimizer.xlsx"
wb.save(out)
print(f"wrote {out}")
print(f"  channels (fill order): {' -> '.join(CH_NAMES)}")
print(f"  crop x channel rows: {len(pair_row)}   annual-cap pairs: "
      f"{[k for k in pair_row if cap_spec(*k)[0]=='Annual']}")
print(f"  LP optimum: profit ${_OPT['profit']:,.0f} "
      f"(revenue ${_OPT['revenue']:,.0f} - cost ${_OPT['cost']:,.0f})")
print(f"  fixed fill rule at 6 ac ${_GRD['profit']:,.0f} -> optimal allocation "
      f"${_FIX['profit']:,.0f}  (+${_FIX['profit']-_GRD['profit']:,.0f})")
print(f"  decision cells {len(succ_meta) + len(CROP_NAMES)*len(CH_NAMES)*52:,}  "
      f"| solver recipe entries {len(recipe)-1}")
