"""
verify_toy_v3.py — EVALUATE the v3 workbook and prove it works.

Run:  .venv/bin/python toy_models/verify_toy_v3.py   (tests/test_toy_model.py runs this)

Same four sections as v2, extended to the channel layer:
  A. VALUES        every computed row against an independent simulator, under THREE
                   configurations. The extra one is not optional: at the shipped defaults
                   shrink is 0 and pack-out is 1.00, so sign and ordering errors in those
                   terms are inert.
  B. PROPAGATION   every input perturbed; the outputs must move. Includes both new axes
                   (sell-through and returns-to-store) on a crop-channel cell.
  C. NO FROZEN     every number is a formula, a declared input, or a whitelisted constant.
  D. READ ME       the prose promises what the workbook computes.

⚠️ `formulas` is CASE-SENSITIVE on the filename in its cell keys. An override posted with the
wrong case does not fail — it creates a NEW orphan node, the real cell keeps its value, and
reading the key back returns what was just injected. `calc()` asserts every override landed.
"""
import json
import re
import sys
import pathlib
import warnings

warnings.filterwarnings("ignore")
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import formulas
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from farm_v2.utils.calendar import generate_successions, harvest_weeks_of
from farm_v2.utils.demand import build_demand_table, build_annual_caps

WB = REPO / "toy_models" / "farm_toy_v3_channels_and_demand.xlsx"
PFX = f"'[{WB.name}]MODEL'!"
CROPS = ("Spinach", "Kale", "Garlic")
PICKED = [("Spinach W10", "Spinach"), ("Spinach W34", "Spinach"), ("Kale W12", "Kale"),
          ("Kale W32", "Kale"), ("Garlic W47", "Garlic")]
CELL_RE = re.compile(rf"'\[{re.escape(WB.name)}\]MODEL'!([A-Z]+\d+)$")

ws = load_workbook(WB)["Model"]
failures = []


def report(ok, msg):
    print(("  OK   " if ok else "  FAIL ") + msg)
    if not ok:
        failures.append(msg)


def labels():
    out = {}
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str):
            out.setdefault(v.strip(), []).append(r)
    return out


def crop_blocks():
    """Delimited by the NEXT block header — never a fixed row count (see v2's note)."""
    heads = [r for r in range(1, ws.max_row + 1)
             if isinstance(ws.cell(row=r, column=1).value, str)
             and "—" in ws.cell(row=r, column=1).value
             and ws.cell(row=r, column=1).value.endswith("store")]
    out = {}
    for i, r in enumerate(heads):
        stop = heads[i + 1] if i + 1 < len(heads) else ws.max_row + 1
        seq = {}
        for rr in range(r + 1, stop):
            lv = ws.cell(row=rr, column=1).value
            if isinstance(lv, str) and lv.strip():
                seq.setdefault(lv.strip(), rr)
        out[ws.cell(row=r, column=1).value.split(" ")[0]] = seq
    return out


LBL, BLK = labels(), crop_blocks()
col = lambda w: get_column_letter(w + 2)
xl = formulas.ExcelModel().loads(str(WB)).finish()


def calc(overrides=None):
    sol = (xl.calculate(inputs={PFX + k: v for k, v in overrides.items()})
           if overrides else xl.calculate())
    d = {}
    for k, v in sol.items():
        m = CELL_RE.match(k)
        if m:
            try:
                d[m.group(1)] = v.value[0, 0]
            except Exception:
                pass
    for k, v in (overrides or {}).items():
        got = d.get(k)
        ok = got is not None and (
            abs(float(got) - float(v)) < 1e-9 if isinstance(v, (int, float)) else str(got) == str(v))
        assert ok, (f"OVERRIDE DID NOT LAND: {k} reads {got!r}, wanted {v!r} — check key case")
    return d


def row(d, r):
    return [d.get(f"{col(w)}{r}") for w in range(1, 53)]


# --------------------------------------------------------------------------- simulator
payload = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
crops = {c["name"]: c for c in payload["crops"] if c["name"] in CROPS}
channels = payload["channels"]
CH_ORDER = sorted(channels, key=lambda ch: -max(
    crops[c].get("channels", {}).get(ch["name"], {}).get("price_per_lb", 0) for c in CROPS))
CH = [c["name"] for c in CH_ORDER]
gen = {s["name"]: s for s in generate_successions(list(crops.values()), 2024)}
_dt = build_demand_table(list(crops.values()), CH_ORDER, 52)
_ac = build_annual_caps(list(crops.values()), CH_ORDER)


def cap_spec(cn, hn):
    ci, hi = list(CROPS).index(cn), CH.index(hn)
    if (ci, hi) in _ac:
        return "Annual", float(_ac[(ci, hi)]), 1, 52
    r_ = _dt[ci, hi, 1:]
    wks = [w + 1 for w in range(52) if r_[w] > 0]
    return ("Weekly", float(r_[wks[0] - 1]), wks[0], wks[-1]) if wks else ("Weekly", 0.0, 1, 52)


def simulate(acres, packout, shrink, pairs, yld=None, m3=None):
    """pairs[(crop, channel)] = (cap_type, cap_value, w0, w1, sell_through, returns)

    `yld` and `m3` default to the app's values; a configuration may override them so that
    section A covers those inputs by EXACT comparison instead of a directional nudge.
    """
    yld = yld or {n: crops[n]["yield_per_acre"] for n in crops}
    m3 = m3 or {n: crops[n]["crop_size_m3_per_lb"] for n in crops}
    gross = {n: [0.0] * 53 for n in crops}
    land = [0.0] * 53
    for pn, cn in PICKED:
        s = gen[pn]
        hw = harvest_weeks_of(s, 52)
        for w in hw:
            gross[cn][w] += acres[pn] * yld[cn] / max(1, len(hw))
        for wk in s["weeks"]:
            land[((wk - 1) % 52) + 1] += acres[pn]
    packed = {n: [gross[n][w] * packout[n] for w in range(53)] for n in crops}
    cull = {n: [gross[n][w] - packed[n][w] for w in range(53)] for n in crops}
    opening = {n: [0.0] * 53 for n in crops}
    shr = {n: [0.0] * 53 for n in crops}
    store = {n: [0.0] * 53 for n in crops}
    close = {n: [0.0] * 53 for n in crops}
    room = {n: [0.0] * 53 for n in crops}
    cap = {(n, h): [0.0] * 53 for n in crops for h in CH}
    off = {(n, h): [0.0] * 53 for n in crops for h in CH}
    sold = {(n, h): [0.0] * 53 for n in crops for h in CH}
    ml = {(n, h): [0.0] * 53 for n in crops for h in CH}
    ret = {(n, h): [0.0] * 53 for n in crops for h in CH}
    con = {(n, h): [0.0] * 53 for n in crops for h in CH}
    for n in crops:
        for w in range(1, 53):
            opening[n][w] = close[n][w - 1] if w > 1 else 0.0
            shr[n][w] = opening[n][w] * shrink[n]
            store[n][w] = opening[n][w] - shr[n][w] + packed[n][w]
            room[n][w] = (opening[n][w] + packed[n][w]) * m3[n]
            left = store[n][w]
            for h in CH:
                ctype, cval, w0, w1, st, rt = pairs[(n, h)]
                cap[(n, h)][w] = (max(0.0, cval - sum(sold[(n, h)][1:w])) if ctype == "Annual"
                                  else (cval if w0 <= w <= w1 else 0.0))
                off[(n, h)][w] = 0.0 if st <= 0 else min(left, cap[(n, h)][w] / st)
                sold[(n, h)][w] = off[(n, h)][w] * st
                spare = off[(n, h)][w] - sold[(n, h)][w]
                ml[(n, h)][w] = spare * (1 - rt)
                ret[(n, h)][w] = spare * rt
                con[(n, h)][w] = off[(n, h)][w] - ret[(n, h)][w]
                left -= con[(n, h)][w]
            close[n][w] = left
    return dict(gross=gross, cull=cull, packed=packed, opening=opening, shr=shr, store=store,
                close=close, room=room, cap=cap, off=off, sold=sold, ml=ml, ret=ret, con=con,
                land=land,
                cold=[room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)],
                amb=[room["Garlic"][w] for w in range(1, 53)])


def default_pairs():
    out = {}
    for n in CROPS:
        for h in CH:
            t, v, a, b = cap_spec(n, h)
            contract = h.lower().startswith("wholesale")
            storable = not crops[n].get("cold_storage", True)
            out[(n, h)] = (t, v, a, b, 1.00 if contract else 0.85,
                           0.00 if contract else (1.00 if storable else 0.00))
    return out


BASE = dict(acres={pn: 6.0 for pn, _ in PICKED}, packout={n: 1.00 for n in crops},
            shrink={n: 0.0 for n in crops}, pairs=default_pairs())


def compare(tag, got, want, tol=1e-6):
    want = want[1:] if len(want) == 53 else want
    bad = [(w + 1, g, x) for w, (g, x) in enumerate(zip(got, want))
           if g is None or abs(float(g) - x) > tol]
    report(not bad, tag + ("" if not bad else
           f" — first mismatch wk{bad[0][0]}: sheet {bad[0][1]}, sim {bad[0][2]:.4f} "
           f"({len(bad)} weeks)"))


def check_values(tag, overrides, params):
    d = calc(overrides)
    s = simulate(**params)
    for n in CROPS:
        b = BLK[n.upper()]
        compare(f"[{tag}] {n} gross",       row(d, b["Harvested (gross)"]), s["gross"][n])
        compare(f"[{tag}] {n} packed",      row(d, b["Packed out -> INTO the store"]), s["packed"][n])
        compare(f"[{tag}] {n} carried in",  row(d, b["Stock carried in"]), s["opening"][n])
        compare(f"[{tag}] {n} shrink",      row(d, b["lost to shrink"]), s["shr"][n])
        compare(f"[{tag}] {n} in store",    row(d, b["In store this week"]), s["store"][n])
        for h in CH:
            compare(f"[{tag}] {n}/{h} cap",    row(d, b[f"{h} — demand cap"]), s["cap"][(n, h)])
            compare(f"[{tag}] {n}/{h} offered", row(d, b[f"{h} — offered"]), s["off"][(n, h)])
            compare(f"[{tag}] {n}/{h} sold",   row(d, b[f"{h} — SOLD"]), s["sold"][(n, h)])
        compare(f"[{tag}] {n} carried out", row(d, b["Stock carried out"]), s["close"][n])
        compare(f"[{tag}] {n} room",        row(d, b["ROOM OCCUPANCY"]), s["room"][n], 1e-4)
    compare(f"[{tag}] LAND", row(d, LBL["LAND in the ground"][0]), s["land"])
    compare(f"[{tag}] COLD STORE", row(d, LBL["COLD STORE"][0]), [0] + s["cold"], 1e-4)
    compare(f"[{tag}] AMBIENT STORE", row(d, LBL["AMBIENT STORE"][0]), [0] + s["amb"], 1e-4)
    return d


# pair-table rows, so overrides can address them
PAIR_ROW = {}
for r in range(1, ws.max_row + 1):
    a, b_ = ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value
    if a in CROPS and b_ in CH:
        PAIR_ROW[(a, b_)] = r
CROP_ROW = {n: [r for r in LBL[n] if ws.cell(row=r, column=2).value == crops[n]["yield_per_acre"]][0]
            for n in CROPS}

FM = [h for h in CH if h.startswith("Farmers")][0]
WS_ = [h for h in CH if h.lower().startswith("wholesale")][0]

CAP_ROW = {}
for r in range(1, ws.max_row + 1):
    a = ws.cell(row=r, column=1).value
    if isinstance(a, str) and a.endswith("capacity"):
        CAP_ROW["cold" if "Cold" in a else "ambient"] = r
assert set(CAP_ROW) == {"cold", "ambient"}, f"storage cap rows not found: {CAP_ROW}"


print("A. VALUES — the sheet against an independent simulator, FOUR configurations")
d0 = check_values("defaults", None, BASE)

FM = [h for h in CH if h.startswith("Farmers")][0]
WS_ = [h for h in CH if h.lower().startswith("wholesale")][0]

# Stressed: pack-out and shrink off their defaults, both new axes moved, on different crops,
# and the annual-cap pair given a smaller allowance so C6b-style carry-over actually binds.
sp = default_pairs()
sp[("Garlic", FM)] = sp[("Garlic", FM)][:4] + (0.70, 0.40)
sp[("Spinach", FM)] = sp[("Spinach", FM)][:4] + (0.60, 0.00)
sp[("Kale", WS_)] = ("Annual", 90000.0, 1, 52, 1.00, 0.00)
STRESS_OV = {f"C{CROP_ROW['Spinach']}": 0.80, f"G{CROP_ROW['Kale']}": 0.05,
             f"C{CROP_ROW['Garlic']}": 0.90,
             f"G{PAIR_ROW[('Garlic', FM)]}": 0.70, f"H{PAIR_ROW[('Garlic', FM)]}": 0.40,
             f"G{PAIR_ROW[('Spinach', FM)]}": 0.60,
             f"D{PAIR_ROW[('Kale', WS_)]}": 90000.0}
check_values("stressed", STRESS_OV,
             dict(acres={pn: 6.0 for pn, _ in PICKED},
                  packout={"Spinach": 0.80, "Kale": 1.00, "Garlic": 0.90},
                  shrink={"Spinach": 0.0, "Kale": 0.05, "Garlic": 0.0}, pairs=sp))

# GEOMETRY. Acres, yield, volume-per-lb, the season window and a weekly cap value, all moved at
# once and compared row by row. This replaces five directional propagation nudges with an EXACT
# check — stricter AND cheaper, since a full recalculation is the expensive step here.
gp = default_pairs()
gp[("Garlic", FM)] = ("Weekly", 900.0, 30, 40) + gp[("Garlic", FM)][4:]
GEO_OV = {"B6": 11.0, "B10": 4.0,
          f"B{CROP_ROW['Spinach']}": 7000, f"D{CROP_ROW['Kale']}": 0.006,
          f"D{PAIR_ROW[('Garlic', FM)]}": 900.0, f"E{PAIR_ROW[('Garlic', FM)]}": 30,
          f"F{PAIR_ROW[('Garlic', FM)]}": 40}
check_values("geometry", GEO_OV, dict(
    acres={**{pn: 6.0 for pn, _ in PICKED}, "Spinach W10": 11.0, "Garlic W47": 4.0},
    packout={n: 1.00 for n in crops}, shrink={n: 0.0 for n in crops}, pairs=gp,
    yld={**{n: crops[n]["yield_per_acre"] for n in crops}, "Spinach": 7000},
    m3={**{n: crops[n]["crop_size_m3_per_lb"] for n in crops}, "Kale": 0.006}))

# The grower's own Experiment 1: garlic stops coming home. One cell, and the ruling's whole point.
pe = default_pairs()
pe[("Garlic", FM)] = pe[("Garlic", FM)][:5] + (0.00,)
check_values("garlic-perishable", {f"H{PAIR_ROW[('Garlic', FM)]}": 0.00},
             dict(BASE, pairs=pe))

print("\nB. PROPAGATION — the inputs section A cannot cover")
# Deliberately SHORT. Pack-out, shrink, sell-through, returns and the annual cap value are all
# moved by the 'stressed' configuration above and compared row by row against the simulator —
# an EXACT check, strictly stronger than a directional nudge, and the simulator reads each of
# those parameters independently, so agreement proves the sheet responds to them. Repeating them
# here bought nothing and cost a full recalculation each (the expensive step in this script).
#
# What is left is what section A genuinely cannot see: a cap TYPE (a string, not a flow),
# shelf life (a diagnostic the simulator does not model), and the three capacity limits, which
# are constraint right-hand sides rather than inputs to the flow.
peak = lambda d, lab, i=0: max(float(x) for x in row(d, LBL[lab][i]) if x is not None)
total = lambda d, c, r_: sum(float(x) for x in row(d, BLK[c][r_]) if x is not None)
worst = lambda d, i: min(float(x) for x in row(d, LBL["room left"][i]) if x is not None)
b_gr = total(d0, "SPINACH", "Harvested (gross)")
b_cold = peak(d0, "COLD STORE")
b_gfm = total(d0, "GARLIC", f"{FM} — SOLD")
b_gret = total(d0, "GARLIC", "returned to store")
b_sml = total(d0, "SPINACH", "market loss (gone)")

for tag, ov, pred in [
    ("cap TYPE       Spinach/WS -> Annual", {f"C{PAIR_ROW[('Spinach', WS_)]}": "Annual"},
     lambda d: total(d, "SPINACH", f"{WS_} — SOLD") <= float(
         ws.cell(row=PAIR_ROW[("Spinach", WS_)], column=4).value) + 1e-6),
    ("shelf life     Garlic -> 2", {f"F{CROP_ROW['Garlic']}": 2,
                                    f"D{PAIR_ROW[('Garlic', FM)]}": 200.0,
                                    f"D{PAIR_ROW[('Garlic', WS_)]}": 200.0},
     lambda d: total(d, "GARLIC", "Over shelf life?") > 0),
    ("cold cap       -> 50", {f"B{CAP_ROW['cold']}": 50.0}, lambda d: worst(d, 1) < 0),
    ("ambient cap    -> 20", {f"B{CAP_ROW['ambient']}": 20.0}, lambda d: worst(d, 2) < 0),
    ("land           -> 10", {"B12": 10.0}, lambda d: worst(d, 0) < 0),
]:
    try:
        ok = pred(calc(ov))
    except AssertionError as e:
        ok, tag = False, f"{tag}  [{e}]"
    except Exception as e:
        ok, tag = False, f"{tag}  [{type(e).__name__}: {e}]"
    report(ok, tag)

print("\nC. NO FROZEN DERIVED VALUES")
week_rows = {r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Week"}
anchors = {r for r in range(1, ws.max_row + 1)
           if str(ws.cell(row=r, column=1).value).strip() == "Stock carried in"}
frozen = []
for line in ws.iter_rows():
    for c in line:
        if not isinstance(c.value, (int, float)) or isinstance(c.value, bool):
            continue
        yellow = bool(c.fill and c.fill.fgColor and c.fill.fgColor.rgb
                      and "FFF2CC" in str(c.fill.fgColor.rgb))
        if yellow or c.row in week_rows or (c.row in anchors and c.column == 3):
            continue
        frozen.append(f"{c.coordinate}={c.value} (row {ws.cell(row=c.row, column=1).value!r})")
report(not frozen, "every number is a formula or a declared input"
       + ("" if not frozen else " — FROZEN: " + "; ".join(frozen[:6])))

print("\nD. THE READ ME PROMISES WHAT THE SHEET PRODUCES")
rd = load_workbook(WB)["READ ME"]
prose = "\n".join(str(rd.cell(row=r, column=1).value or "") for r in range(1, rd.max_row + 1))
for name, val, unit in (("COLD", peak(d0, "COLD STORE"), "m3"),
                        ("AMBIENT", peak(d0, "AMBIENT STORE"), "m3")):
    report(f"{val:.1f} {unit}" in prose, f"READ ME states the real peak {name} ({val:.1f} {unit})")
for n in CROPS:
    for h in CH:
        v = total(d0, n.upper(), f"{h} — SOLD")
        report(f"{v:,.0f}" in prose, f"READ ME states {n}/{h} sold ({v:,.0f} lb)")

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURE(S)"))
sys.exit(1 if failures else 0)
