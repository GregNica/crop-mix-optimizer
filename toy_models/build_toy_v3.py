"""
build_toy_v3.py — generates the Channels + Demand toy model workbook.

v3 adds the layer that answers "who is allowed to buy this, and how much?" — and with it the
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

⚠️ ALLOCATION IS A DECISION, AND THIS SHEET CANNOT MAKE IT. With two channels competing for one
crop's stock, something must choose who gets served first. A calculator needs a RULE; the real
model has an OPTIMIZER that chooses by margin. This sheet fills the higher-priced channel first
and says so. That gap is the strongest argument for switching the solver on, which is v4.

Output: farm_toy_v3_channels_and_demand.xlsx
"""
import json
import sys
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

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

# Fill order: highest price first, which is what a margin-maximising optimizer would do.
# Farmers Market outprices Wholesale on every crop here (Spinach 2.75 vs 1.00, Garlic 6.00 vs
# 2.75), so it is served first. STATED, not hidden — see the module docstring.
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
                       "Shelf life wk", "Shrink %/wk"]):
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
    assert crop_row_pending[name] == r, f"reserved row {crop_row_pending[name]} for {name}, wrote {r}"
    crop_row[name] = r
    r += 1
put(r, 1, "SELL-THROUGH IS NOT HERE — it is per crop x CHANNEL, in section 3. Grower ruling, "
          "2026-08-29.", font=F_NOTE)
r += 2

# --- 3. crop x channel ---
put(r, 1, "3 — WHO BUYS IT, AND HOW MUCH   (one row per crop x channel)", font=F_H1); r += 1
for j, h in enumerate(["Crop", "Channel", "Cap type", "Cap lb", "From wk", "To wk",
                       "Sell-through", "Returns to store"]):
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
        put(r, 1, f"{hname} — demand cap", font=F_SMALL, fill=fill); put(r, 2, "lb", font=F_NOTE)
        R_CAP = r
        for w in range(1, 53):
            # Weekly: the stated figure inside its season. Annual: the yearly total less what has
            # already been sold — a running allowance, which is what C6b actually enforces.
            sold_ref = f"$C${R_CAP+2}:{wl(w-1)}${R_CAP+2}" if w > 1 else None
            annual = (f"MAX(0,$D${pr}-SUM({sold_ref}))" if sold_ref else f"$D${pr}")
            weekly = f"IF(AND({wl(w)}${ROW_WEEKNUM}>=$E${pr},{wl(w)}${ROW_WEEKNUM}<=$F${pr}),$D${pr},0)"
            put(r, wcol(w), f'=IF($C${pr}="Annual",{annual},{weekly})', fmt="#,##0", fill=fill)
        r += 1
        put(r, 1, f"{hname} — offered", font=F_SMALL); put(r, 2, "lb", font=F_NOTE)
        R_OFF = r
        for w in range(1, 53):
            left = f"{wl(w)}{R_STORE}" + "".join(f"-{wl(w)}{pc}" for pc in prior_consumed)
            put(r, wcol(w), f'=IF($G${pr}<=0,0,MIN({left},{wl(w)}{R_CAP}/$G${pr}))', fmt="#,##0")
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

# ===========================================================================
# Numbers the READ ME promises — COMPUTED, never typed.
#
# An earlier version wrote them by hand and three shipped 0.1 out from rounding while the prose
# was being written. Same class as a frozen cell beside a live one: a figure written next to its
# source instead of derived from it. verify_toy_v3.py section D closes the loop by checking that
# what this document promises equals what the workbook computes.
# ===========================================================================
def _sim(acres=6.0):
    gross = {n: [0.0] * 53 for n in CROP_NAMES}
    for m in succ_meta:
        for w in harvest_weeks_of(m["s"], 52):
            gross[m["crop"]][w] += acres * crops[m["crop"]]["yield_per_acre"] / m["nharv"]
    close = {n: [0.0] * 53 for n in CROP_NAMES}
    room = {n: [0.0] * 53 for n in CROP_NAMES}
    sold = {(n, h): 0.0 for n in CROP_NAMES for h in CH_NAMES}
    ml = {(n, h): 0.0 for n in CROP_NAMES for h in CH_NAMES}
    ret = {(n, h): 0.0 for n in CROP_NAMES for h in CH_NAMES}
    capsum = {(n, h): 0.0 for n in CROP_NAMES for h in CH_NAMES}
    for n in CROP_NAMES:
        for w in range(1, 53):
            packed = gross[n][w] * PACK_OUT
            opening = close[n][w - 1] if w > 1 else 0.0
            in_store = opening + packed
            room[n][w] = (opening + packed) * crops[n]["crop_size_m3_per_lb"]
            left = in_store
            for h in CH_NAMES:
                ctype, cval, w0, w1 = cap_spec(n, h)
                st, rt = defaults(n, h)
                cap = (max(0.0, cval - sold[(n, h)]) if ctype == "Annual"
                       else (cval if w0 <= w <= w1 else 0.0))
                capsum[(n, h)] += cap
                off = 0.0 if st <= 0 else min(left, cap / st)
                s_ = off * st
                sold[(n, h)] += s_
                ml[(n, h)] += (off - s_) * (1 - rt)
                ret[(n, h)] += (off - s_) * rt
                left -= off - (off - s_) * rt
            close[n][w] = left
    cold = [room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)]
    amb = [room["Garlic"][w] for w in range(1, 53)]
    return dict(cold=max(cold), cold_wk=cold.index(max(cold)) + 1, amb=max(amb),
                amb_wk=amb.index(max(amb)) + 1, sold=sold, ml=ml, ret=ret, capsum=capsum,
                gross={n: sum(gross[n]) for n in CROP_NAMES}, close=close)


_B = _sim()
NUMS = {"{PK_COLD}": f"{_B['cold']:.1f}", "{PK_COLD_WK}": str(_B["cold_wk"]),
        "{PK_AMB}": f"{_B['amb']:.1f}", "{PK_AMB_WK}": str(_B["amb_wk"]),
        "{CH1}": CH_NAMES[0], "{CH2}": CH_NAMES[1]}
for n in CROP_NAMES:
    for h in CH_NAMES:
        tag = f"{n.upper()}_{'FM' if h.startswith('Farmers') else 'WS'}"
        NUMS[f"{{{tag}_SOLD}}"] = f"{_B['sold'][(n,h)]:,.0f}"
        NUMS[f"{{{tag}_ML}}"] = f"{_B['ml'][(n,h)]:,.0f}"
        NUMS[f"{{{tag}_RET}}"] = f"{_B['ret'][(n,h)]:,.0f}"
        cs = _B["capsum"][(n, h)]
        ctype, cval, _, _ = cap_spec(n, h)
        base = cval if ctype == "Annual" else cs
        NUMS[f"{{{tag}_FILL}}"] = f"{(_B['sold'][(n,h)]/base if base else 0):.0%}"

GARLIC_PAIR_FM = pair_row[("Garlic", [h for h in CH_NAMES if h.startswith("Farmers")][0])]
SPIN_PAIR_FM = pair_row[("Spinach", [h for h in CH_NAMES if h.startswith("Farmers")][0])]
COORDS = {"{ACRES}": f"B{ROW_SUCC}:B{ROW_SUCC+len(succ_meta)-1}",
          "{G_RET}": f"H{GARLIC_PAIR_FM}", "{G_ST}": f"G{GARLIC_PAIR_FM}",
          "{S_ST}": f"G{SPIN_PAIR_FM}", "{S_RET}": f"H{SPIN_PAIR_FM}",
          "{PAIRS}": f"A{ROW_PAIR}:H{ROW_PAIR+len(pair_row)-1}"}

readme = [
 ("Farm toy model — v3: CHANNELS + DEMAND", F_TITLE),
 ("", None),
 ("WHAT v3 ADDS", F_H1),
 ("Who is allowed to buy this, and how much. Two channels — {CH1} and {CH2} — with the real", None),
 ("demand caps from your app, and your ruling of 29 Aug built in:", None),
 ("", None),
 ("     SELL-THROUGH IS PER CROP x CHANNEL.", F_BOLD),
 ("", None),
 ("Section 3 is the new table: one row per crop x channel, holding the demand cap, the season,", None),
 ("the sell-through, and whether unsold product comes home. That is where these belong in the", None),
 ("app too — beside price and packaging on each crop's channel, not on the crop and not on the", None),
 ("channel.", None),
 ("", None),
 ("WHY IT HAD TO MOVE THERE", F_H1),
 ("A wholesaler orders, you deliver, you invoice. There IS no unsold portion, so sell-through is", None),
 ("1.00 by construction — the losses on that channel are rejections, which are a different event.", None),
 ("A market stall is the opposite: you bring a full display because you cannot sell from an empty", None),
 ("table, so you always offer more than you sell.", None),
 ("", None),
 ("And what happens to the remainder depends on the CROP, not the channel:", None),
 ("     Garlic comes home and sells next week.        Returns to store = 1.00", None),
 ("     Spinach has been out of the cooler all day.   Returns to store = 0.00", None),
 ("", None),
 ("So the quantity is channel x storability, and only a crop-channel cell can hold it. That is", None),
 ("your ruling, and this sheet is what it looks like.", None),
 ("", None),
 ("THE CAP IS THE PROJECTION; SELL-THROUGH IS THE VARIANCE BELOW IT", F_H1),
 ("Your framing, and it is the one used here. The cap says what the buyer will take. Sell-through", None),
 ("says how much of that you actually convert. It only bites where the remainder cannot be", None),
 ("carried forward — which is why garlic's 15% is a DELAY and spinach's is a LOSS.", None),
 ("", None),
 ("Watch it in the summary: at the shipped defaults Garlic sells {GARLIC_FM_SOLD} lb at {CH1},", None),
 ("loses {GARLIC_FM_ML} lb, and returns {GARLIC_FM_RET} lb to the barn. Spinach loses", None),
 ("{SPINACH_FM_ML} lb and returns {SPINACH_FM_RET}.", None),
 ("", None),
 ("WEEKLY CAPS AND ANNUAL CAPS READ VERY DIFFERENTLY", F_H1),
 ("Both are in section 3, and the app enforces both (C6 weekly, C6b annual).", None),
 ("  - Kale/{CH2} is an ANNUAL cap: 500,000 lb across the year, no weekly ceiling at all.", None),
 ("  - Everything else is WEEKLY, inside a season window.", None),
 ("Garlic/{CH1} is the case that made this subtle in the real app: its weekly cap runs W22-W35", None),
 ("but the garlic is not out of the ground until W30, so seven of the fourteen capped weeks are", None),
 ("unservable. It fills {GARLIC_FM_FILL} of the year's appetite while sitting at its weekly", None),
 ("ceiling in every week it can sell at all. Both numbers are true; they answer different", None),
 ("questions.", None),
 ("", None),
 ("!! WHAT THIS SHEET CANNOT DO — AND IT IS THE POINT", F_H1),
 ("Two channels want the same pounds. SOMETHING has to decide who is served first, and a", None),
 ("calculator cannot: it needs a fixed rule. This sheet fills {CH1} first because it pays more.", None),
 ("", None),
 ("The real model does not use a rule. It has an OPTIMIZER that weighs margin, demand, storage", F_BOLD),
 ("and every other constraint at once, across all 52 weeks simultaneously.", F_BOLD),
 ("", None),
 ("That gap is the best argument for v4, which switches the solver on. Until then, remember that", None),
 ("every allocation on this sheet is MY rule, not the model's answer.", None),
 ("", None),
 ("HOW TO USE IT", F_H1),
 ("1. Every YELLOW cell is an input. Nothing else should be typed in.", None),
 ("2. Start with the acre cells ({ACRES}). Change one and watch the whole sheet move.", None),
 ("3. Then go to section 3 — the crop x channel table ({PAIRS}). That is the new part, and it", None),
 ("   is where your ruling lives.", None),
 ("4. Watch the 'room left' rows under LAND, COLD STORE and AMBIENT STORE. Red = over the limit", None),
 ("   in that week, which the app treats as an infeasible plan, not a warning.", None),
 ("", None),
 ("CHECK IT WORKED — the numbers you should see on opening", F_H1),
 ("Every planting 6 acres, pack-out 1.00, shrink 0:", None),
 ("     Peak COLD store     {PK_COLD} m3  in week {PK_COLD_WK}", F_BOLD),
 ("     Peak AMBIENT store  {PK_AMB} m3  in week {PK_AMB_WK}", F_BOLD),
 ("     Spinach sold  {SPINACH_FM_SOLD} at {CH1}  +  {SPINACH_WS_SOLD} at {CH2}", None),
 ("     Kale    sold  {KALE_FM_SOLD} at {CH1}  +  {KALE_WS_SOLD} at {CH2}", None),
 ("     Garlic  sold  {GARLIC_FM_SOLD} at {CH1}  +  {GARLIC_WS_SOLD} at {CH2}", None),
 ("If those do not match, tell me — do not work around it.", None),
 ("", None),
 ("THREE THINGS TO TRY", F_H1),
 ("", None),
 ("EXPERIMENT 1 — make garlic perishable.  Set Garlic's 'Returns to store' at {CH1} ({G_RET})", F_BOLD),
 ("   from 1.00 to 0.00.", F_BOLD),
 ("   The same 15% that was a delay becomes a loss. Sold falls, market loss appears, and the", None),
 ("   stock that used to come home is gone. Nothing else changed — same cap, same sell-through.", None),
 ("   This is the distinction your ruling turns on, in one cell.", None),
 ("", None),
 ("EXPERIMENT 2 — put the wholesale haircut back.  Set every 'Sell-through' in {PAIRS} to 0.85.", F_BOLD),
 ("   That is what the app does today: one number for every channel. Watch the contract channel", None),
 ("   start throwing away product it had a purchase order for.", None),
 ("", None),
 ("EXPERIMENT 3 — widen garlic's market window.  Change Garlic/{CH1} 'From wk' ({PAIRS}) to 30.", F_BOLD),
 ("   The annual fill jumps even though the weekly cap never moved, because the unservable weeks", None),
 ("   before harvest stop counting against it. Same plan, same buyer — a truer number.", None),
 ("", None),
 ("WHAT v3 STILL DOES NOT CARRY", F_H1),
 ("  - No prices, costs or profit. Physical only, still.", None),
 ("  - No optimizer. You type the acres and I fill channels in a fixed order.", None),
 ("  - No cash, labour, water, or diversity limits.", None),
 ("  - Shelf life is a WARNING, not enforced.", None),
 ("  - The app does NOT yet do per-crop-channel sell-through. Your ruling is recorded", None),
 ("    (DECISIONS E1) and this sheet is the prototype; the app change is still to come.", None),
 ("", None),
 ("!! THE SCALE WARNING", F_H1),
 ("Small models are TIGHT, large ones LOOSE. 3 crops and 5 plantings here against 7 crops and", None),
 ("220 acre-plantings on the real farm. This teaches MECHANISM; the app's capacity_series tells", None),
 ("you which constraint actually binds. Re-measure before concluding anything.", None),
 ("", None),
 ("HAS THIS SHEET BEEN CHECKED?", F_H1),
 ("Yes. Crop constants, planting dates AND the demand caps are read from the app — the caps come", None),
 ("through its own build_demand_table/build_annual_caps, so the weekly-vs-annual split is the", None),
 ("app's, not my reading of it. The workbook is CALCULATED by a formula engine and compared", None),
 ("cell by cell against an independent model, every input is perturbed to prove it propagates,", None),
 ("and no number is frozen.", None),
 ("     Run it yourself:   .venv/bin/python toy_models/verify_toy_v3.py", None),
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

out = REPO / "toy_models" / "farm_toy_v3_channels_and_demand.xlsx"
wb.save(out)
print(f"wrote {out}")
print(f"  channels (fill order): {' -> '.join(CH_NAMES)}")
print(f"  crop x channel rows: {len(pair_row)}   annual-cap pairs: "
      f"{[k for k in pair_row if cap_spec(*k)[0]=='Annual']}")
print(f"  peak cold {_B['cold']:.1f} m3 wk{_B['cold_wk']}  |  peak ambient {_B['amb']:.1f} m3 wk{_B['amb_wk']}")
