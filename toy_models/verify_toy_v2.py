"""
verify_toy_v2.py — EVALUATE the toy workbook and prove it works.

Run:  .venv/bin/python toy_models/verify_toy_v2.py
      (needs `formulas`; `tests/test_toy_model.py` runs this as a subprocess)

WHY THIS EXISTS. openpyxl reads formulas as TEXT. Every static check — "is this a formula",
"does it reference the right row" — can pass over a sheet that computes nonsense. The grower
opened v1 and within a minute found a column of frozen numbers sitting beside the live ones
they described, then said: if there is an error right at the beginning, there are more. That
is the correct inference, and the only way to answer it is to CALCULATE the sheet.

Three things are checked, in increasing strength:

  A. VALUES — every computed row equals an independent Python simulator built from the app's
     own crop data. Catches a formula that is well-formed and wrong.
  B. PROPAGATION — perturb each input, recalculate, and assert the outputs actually move.
     Catches an input wired to nothing, which is what E6:E10 was.
  C. NO FROZEN DERIVED VALUES — every number on the Model sheet is a formula, a declared
     input, or one of three whitelisted constants (the week strips, the week-1 stock anchor).

⚠️ THE TRAP THAT COST AN HOUR HERE, WRITTEN DOWN SO IT IS NOT REPEATED.
`formulas` keys cells as "'[filename.xlsx]SHEET'!A1" and is CASE-SENSITIVE on the filename.
An override posted with an uppercased name does not fail — it creates a NEW orphan node, the
real cell keeps its old value, and reading the key back returns the value just injected. So
the check confirms itself and every propagation test reports a pass over a sheet nothing was
done to. Both the case and a landed-assertion are enforced in `calc()` below.
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

WB = REPO / "toy_models" / "farm_toy_v2_loss_and_storage.xlsx"
PFX = f"'[{WB.name}]MODEL'!"          # exact case — see the trap note above
CROPS = ("Spinach", "Kale", "Garlic")
PICKED = [("Spinach W10", "Spinach"), ("Spinach W34", "Spinach"),
          ("Kale W12", "Kale"), ("Kale W32", "Kale"), ("Garlic W47", "Garlic")]
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


def _is_block_header(v):
    return isinstance(v, str) and "—" in v and v.endswith("store")


def crop_blocks():
    """Delimit each block by the NEXT header, never by a fixed row count.

    A fixed window is wrong in both directions and fails silently either way: too narrow and
    the last rows vanish (KeyError, loud); too wide and it reads the NEXT crop's rows under
    this crop's names, so every comparison comes out wrong while the lookup succeeds. The
    second is the dangerous one — it looks like twelve real defects.
    """
    heads = [r for r in range(1, ws.max_row + 1)
             if _is_block_header(ws.cell(row=r, column=1).value)]
    out = {}
    for i, r in enumerate(heads):
        stop = heads[i + 1] if i + 1 < len(heads) else ws.max_row + 1
        seq = {}
        for rr in range(r + 1, stop):
            lv = ws.cell(row=rr, column=1).value
            if isinstance(lv, str) and lv.strip():
                seq.setdefault(lv.strip(), rr)      # first occurrence wins
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
        assert got is not None and abs(float(got) - float(v)) < 1e-9, (
            f"OVERRIDE DID NOT LAND: {k} reads {got!r}, wanted {v}. Check the key case — an "
            f"uppercased filename silently creates an orphan node instead of overriding.")
    return d


def row(d, r):
    return [d.get(f"{col(w)}{r}") for w in range(1, 53)]


# --------------------------------------------------------------------------- simulator
payload = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
crops = {c["name"]: c for c in payload["crops"] if c["name"] in CROPS}
gen = {s["name"]: s for s in generate_successions(list(crops.values()), 2024)}


def simulate(acres, packout, stf, sell, shrink):
    """The v2 flow: pack-out BEFORE the store, sell-through AFTER it."""
    gross = {n: [0.0] * 53 for n in crops}
    land = [0.0] * 53
    for pn, cn in PICKED:
        s = gen[pn]
        hw = harvest_weeks_of(s, 52)
        for w in hw:
            gross[cn][w] += acres[pn] * crops[cn]["yield_per_acre"] / max(1, len(hw))
        for wk in s["weeks"]:
            land[((wk - 1) % 52) + 1] += acres[pn]
    packed = {n: [gross[n][w] * packout[n] for w in range(53)] for n in crops}
    cull = {n: [gross[n][w] - packed[n][w] for w in range(53)] for n in crops}
    close = {n: [0.0] * 53 for n in crops}
    room = {n: [0.0] * 53 for n in crops}
    ship = {n: [0.0] * 53 for n in crops}
    sold = {n: [0.0] * 53 for n in crops}
    mloss = {n: [0.0] * 53 for n in crops}
    for n, c in crops.items():
        for w in range(1, 53):
            opening = close[n][w - 1] if w > 1 else 0.0
            in_store = opening - opening * shrink[n] + packed[n][w]
            ship[n][w] = min(in_store, sell[n] / stf[n])
            sold[n][w] = ship[n][w] * stf[n]
            mloss[n][w] = ship[n][w] - sold[n][w]
            close[n][w] = in_store - ship[n][w]
            # Room = opening + everything PACKED OUT. Market loss is inside this: it was in the
            # room before it left. Field cull never appears, because it never came in.
            room[n][w] = (opening + packed[n][w]) * c["crop_size_m3_per_lb"]
    return dict(gross=gross, packed=packed, cull=cull, ship=ship, sold=sold, mloss=mloss,
                land=land, room=room, close=close,
                cold=[room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)],
                amb=[room["Garlic"][w] for w in range(1, 53)])


BASE = dict(acres={pn: 6.0 for pn, _ in PICKED}, packout={n: 1.00 for n in crops},
            stf={n: 0.85 for n in crops}, sell={n: 1e6 for n in crops},
            shrink={n: 0.0 for n in crops})


def compare(tag, got, want, tol=1e-6):
    want = want[1:] if len(want) == 53 else want
    bad = [(w + 1, g, x) for w, (g, x) in enumerate(zip(got, want))
           if g is None or abs(float(g) - x) > tol]
    report(not bad, tag + ("" if not bad else
           f" — first mismatch wk{bad[0][0]}: sheet {bad[0][1]}, simulator {bad[0][2]:.4f} "
           f"({len(bad)} weeks differ)"))


def check_values(tag, overrides, params):
    d = calc(overrides)
    s = simulate(**params)
    for n in CROPS:
        b = BLK[n.upper()]
        compare(f"[{tag}] {n} harvested gross",   row(d, b["Harvested (gross)"]),  s["gross"][n])
        compare(f"[{tag}] {n} field cull",        row(d, b["field cull (never cooled)"]), s["cull"][n])
        compare(f"[{tag}] {n} packed out",        row(d, b["Packed out -> INTO the store"]), s["packed"][n])
        compare(f"[{tag}] {n} shipped",           row(d, b["Shipped out of store"]), s["ship"][n])
        compare(f"[{tag}] {n} sold",              row(d, b["Sold"]),               s["sold"][n])
        compare(f"[{tag}] {n} market loss",       row(d, b["market loss (did not come back)"]), s["mloss"][n])
        compare(f"[{tag}] {n} stock carried out", row(d, b["Stock carried out"]),   s["close"][n])
        compare(f"[{tag}] {n} room occupancy",    row(d, b["ROOM OCCUPANCY"]),      s["room"][n], 1e-4)
    compare(f"[{tag}] LAND in the ground", row(d, LBL["LAND in the ground"][0]), s["land"])
    compare(f"[{tag}] COLD STORE used",    row(d, LBL["COLD STORE"][0]),    [0] + s["cold"], 1e-4)
    compare(f"[{tag}] AMBIENT STORE used", row(d, LBL["AMBIENT STORE"][0]), [0] + s["amb"],  1e-4)
    return d


print("A. VALUES — the sheet against an independent simulator")
print("   TWO configurations, and the second is not optional. At the shipped defaults shrink is")
print("   0 and every sell rate is effectively infinite, so a whole class of sign and ordering")
print("   errors is INERT: `opening - 0 + harvest` and `opening + 0 + harvest` agree exactly.")
print("   Measured — flipping the shrink sign in the generator passed this section until the")
print("   stressed configuration was added.")
d0 = check_values("defaults", None, BASE)

# Both fractions off their defaults, on different crops, so a swap between them cannot pass.
STRESS_OV = {"B6": 10.0, "B10": 8.0,
             "C16": 0.80, "D16": 0.50, "I16": 9000.0,          # Spinach: both fractions + cap
             "C17": 0.90, "H17": 0.05,                          # Kale: pack-out + shrink
             "D18": 0.70, "I18": 2000.0, "H18": 0.02}           # Garlic: sell-through + shrink
STRESS_P = dict(
    acres={**{pn: 6.0 for pn, _ in PICKED}, "Spinach W10": 10.0, "Garlic W47": 8.0},
    packout={"Spinach": 0.80, "Kale": 0.90, "Garlic": 1.00},
    stf={"Spinach": 0.50, "Kale": 0.85, "Garlic": 0.70},
    sell={"Spinach": 9000.0, "Kale": 1e6, "Garlic": 2000.0},
    shrink={"Spinach": 0.0, "Kale": 0.05, "Garlic": 0.02})
check_values("stressed", STRESS_OV, STRESS_P)

# The v1 configuration, reachable from v2: all loss in the field. This is the sheet's own
# built-in demonstration, so it is pinned rather than left to the reader to trust.
V1_OV = {f"{c}{r}": v for r in (16, 17, 18) for c, v in (("C", 0.85), ("D", 1.00))}
V1_P = dict(acres={pn: 6.0 for pn, _ in PICKED}, packout={n: 0.85 for n in crops},
            stf={n: 1.00 for n in crops}, sell={n: 1e6 for n in crops},
            shrink={n: 0.0 for n in crops})
check_values("v1-equivalent", V1_OV, V1_P)

print("\nB. PROPAGATION — perturb each input, does anything downstream move?")
peak = lambda d, lab, i=0: max(float(x) for x in row(d, LBL[lab][i]) if x is not None)
total = lambda d, c, r: sum(float(x) for x in row(d, BLK[c][r]) if x is not None)
worst = lambda d, i: min(float(x) for x in row(d, LBL["room left"][i]) if x is not None)
base_sp = total(d0, "SPINACH", "Harvested (gross)")
base_sold = total(d0, "SPINACH", "Sold")
base_cold = peak(d0, "COLD STORE")

for tag, ov, pred in [
    ("acres         B6  6 -> 12",        {"B6": 12.0},
     lambda d: total(d, "SPINACH", "Harvested (gross)") > base_sp * 1.4),
    ("PACK-OUT      C16 1.00 -> 0.60",   {"C16": 0.60},
     lambda d: peak(d, "COLD STORE") < base_cold * 0.85),
    ("SELL-THROUGH  D16 0.85 -> 0.50",   {"D16": 0.50},
     lambda d: total(d, "SPINACH", "Sold") < base_sold * 0.7),
    ("yield         B16 5000 -> 10000",  {"B16": 10000},
     lambda d: total(d, "SPINACH", "Harvested (gross)") > base_sp * 1.8),
    ("m3 per lb     E16 x2",             {"E16": crops["Spinach"]["crop_size_m3_per_lb"] * 2},
     lambda d: peak(d, "COLD STORE") > base_cold * 1.2),
    ("sell rate     I18 -> 2000",        {"I18": 2000.0},
     lambda d: total(d, "GARLIC", "Stock carried out") > 0),
    ("shrink        H18 -> 2%",          {"I18": 2000.0, "H18": 0.02},
     lambda d: total(d, "GARLIC", "lost to shrink") > 0),
    ("cold cap      B22 275 -> 50",      {"B22": 50.0},  lambda d: worst(d, 1) < 0),
    ("ambient cap   B23 150 -> 20",      {"B23": 20.0},  lambda d: worst(d, 2) < 0),
    ("land          B12 80 -> 10",       {"B12": 10.0},  lambda d: worst(d, 0) < 0),
    ("shelf life    G18 16 -> 2",        {"I18": 2000.0, "G18": 2},
     lambda d: total(d, "GARLIC", "Over shelf life?") > 0),
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
anchor = {r for r in range(1, ws.max_row + 1)
          if str(ws.cell(row=r, column=1).value).strip() == "Stock carried in"}
frozen = []
for line in ws.iter_rows():
    for c in line:
        if not isinstance(c.value, (int, float)) or isinstance(c.value, bool):
            continue
        yellow = bool(c.fill and c.fill.fgColor and c.fill.fgColor.rgb
                      and "FFF2CC" in str(c.fill.fgColor.rgb))
        if yellow or c.row in week_rows or (c.row in anchor and c.column == 3):
            continue
        frozen.append(f"{c.coordinate}={c.value} (row {ws.cell(row=c.row, column=1).value!r})")
report(not frozen, f"every number is a formula or a declared input"
                   + ("" if not frozen else " — FROZEN: " + "; ".join(frozen[:6])))

print("\nD. THE READ ME PROMISES WHAT THE SHEET PRODUCES")
# The prose names numbers the reader will check by eye. They are generated from a simulator, so
# this closes the loop: what the document promises must equal what the workbook computes.
rd = load_workbook(WB)["READ ME"]
prose = "\n".join(str(rd.cell(row=r, column=1).value or "") for r in range(1, rd.max_row + 1))
peak_cold = max(float(x) for x in row(d0, LBL["COLD STORE"][0]) if x is not None)
peak_amb = max(float(x) for x in row(d0, LBL["AMBIENT STORE"][0]) if x is not None)
peak_land = max(float(x) for x in row(d0, LBL["LAND in the ground"][0]) if x is not None)
for name, val, unit in (("COLD", peak_cold, "m3"), ("AMBIENT", peak_amb, "m3"),
                        ("LAND in the ground", peak_land, "acres")):
    txt = f"{val:.1f} {unit}"
    report(txt in prose, f"READ ME states the real peak {name} ({txt})")
for crop in CROPS:
    b = BLK[crop.upper()]
    sold = sum(float(x) for x in row(d0, b["Sold"]) if x is not None)
    report(f"{sold:,.0f}" in prose, f"READ ME states {crop}'s real sold total ({sold:,.0f} lb)")
# and the v1-equivalent figures the demonstration turns on
dv1 = calc(V1_OV)
v1c = max(float(x) for x in row(dv1, LBL["COLD STORE"][0]) if x is not None)
v1a = max(float(x) for x in row(dv1, LBL["AMBIENT STORE"][0]) if x is not None)
report(f"{v1c:.1f} m3" in prose and f"{v1a:.1f} m3" in prose,
       f"READ ME states the real v1-equivalent peaks ({v1c:.1f} / {v1a:.1f} m3)")

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURE(S)"))
sys.exit(1 if failures else 0)
