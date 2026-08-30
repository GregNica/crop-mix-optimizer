"""
verify_toy_v5.py — EVALUATE the v4 workbook and prove it is the same problem the solver solves.

Run:  .venv/bin/python toy_models/verify_toy_v5.py

v4's answer is not arithmetic, it is a CHOICE, so "is the sheet right?" splits in two and both
halves are checked here:

  A. VALUES     given a set of offered pounds, do the sheet's formulas compute the flow
                correctly? Compared row by row against an independent simulator, under three
                configurations.
  B. PROPAGATION the inputs section A cannot cover.
  C. NO FROZEN   every number is a formula, a declared input, or a decision cell.
  D. READ ME     the prose promises what the model produces.
  E. SAME PROBLEM  ⭐ solve the MILP with scipy.milp (the HiGHS wrapper farm_v2 itself uses),
                write that solution into the sheet's decision cells, and require the sheet's own
                PROFIT cell to reproduce the optimum. THIS is the check that matters: it proves
                the spreadsheet and the optimizer are the same model, so when LibreOffice's
                CoinMP solves it, agreement is meaningful rather than coincidental.
"""
import json
import re
import sys
import pathlib
import warnings

warnings.filterwarnings("ignore")
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import formulas
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from farm_v2.utils.calendar import generate_successions, harvest_weeks_of
import toy_v5_lp as LP

WB = REPO / "toy_models" / "farm_toy_v5_full_calendar.xlsx"
PFX = f"'[{WB.name}]MODEL'!"
CROPS = tuple(LP.CROP_NAMES)
CH = list(LP.CH_NAMES)
PICKED = [s["name"] for s in LP.SUCCS]
CELL_RE = re.compile(rf"'\[{re.escape(WB.name)}\]MODEL'!([A-Z]+\d+)$")

ws = load_workbook(WB)["Model"]
failures = []
crops = LP.CROPS


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
col = lambda w: get_column_letter(w + 4)
xl = formulas.ExcelModel().loads(str(WB)).finish()

PAIR_ROW, CROP_ROW, CAP_ROW = {}, {}, {}
for r in range(1, ws.max_row + 1):
    a, b = ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value
    if a in CROPS and b in CH:
        PAIR_ROW[(a, b)] = r
    if a in CROPS and b == crops[a]["yield_per_acre"]:
        CROP_ROW[a] = r
    if isinstance(a, str) and a.startswith("Cold store"):
        CAP_ROW["cold"] = r
    if isinstance(a, str) and a.startswith("Ambient store"):
        CAP_ROW["ambient"] = r
    if a == "Land you have":
        CAP_ROW["land"] = r
SUCC_ROW = {}
for r in range(1, ws.max_row + 1):
    a, b = ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value
    if isinstance(a, str) and b in CROPS and isinstance(ws.cell(row=r, column=3).value, (int, float)):
        SUCC_ROW[a] = r
OBJ_ROW = LBL["PROFIT  (the objective)"][0]
assert len(PAIR_ROW) == 6 and len(CROP_ROW) == 3, "sheet layout not found"
assert len(SUCC_ROW) == len(LP.SUCCS), (
    f"found {len(SUCC_ROW)} succession rows, the app offers {len(LP.SUCCS)} — v5 must carry ALL "
    f"of them; a hand-picked subset is the exact defect v5 exists to remove")


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
        ok = got is not None and (abs(float(got) - float(v)) < 1e-6
                                  if isinstance(v, (int, float)) else str(got) == str(v))
        assert ok, f"OVERRIDE DID NOT LAND: {k} reads {got!r}, wanted {v!r} — check key case"
    return d


def row(d, r):
    return [d.get(f"{col(w)}{r}") for w in range(1, 53)]


def simulate(acres, offered, packout=None, shrink=None):
    """The v4 flow. `offered` is GIVEN — nothing is decided here."""
    packout = packout or {n: 1.00 for n in CROPS}
    shrink = shrink or {n: 0.0 for n in CROPS}
    gross = {n: [0.0] * 53 for n in CROPS}
    land = [0.0] * 53
    for s in LP.SUCCS:
        cn = CROPS[s["crop"]]
        hw = harvest_weeks_of(s, 52)
        for w in hw:
            gross[cn][w] += acres[s["name"]] * crops[cn]["yield_per_acre"] / max(1, len(hw))
        for wk in s["weeks"]:
            land[((wk - 1) % 52) + 1] += acres[s["name"]]
    packed = {n: [gross[n][w] * packout[n] for w in range(53)] for n in CROPS}
    op = {n: [0.0] * 53 for n in CROPS}
    shr = {n: [0.0] * 53 for n in CROPS}
    store = {n: [0.0] * 53 for n in CROPS}
    close = {n: [0.0] * 53 for n in CROPS}
    room = {n: [0.0] * 53 for n in CROPS}
    sold = {(n, h): [0.0] * 53 for n in CROPS for h in CH}
    ret = {(n, h): [0.0] * 53 for n in CROPS for h in CH}
    con = {(n, h): [0.0] * 53 for n in CROPS for h in CH}
    for n in CROPS:
        for w in range(1, 53):
            op[n][w] = close[n][w - 1] if w > 1 else 0.0
            shr[n][w] = op[n][w] * shrink[n]
            store[n][w] = op[n][w] - shr[n][w] + packed[n][w]
            room[n][w] = (op[n][w] + packed[n][w]) * crops[n]["crop_size_m3_per_lb"]
            left = store[n][w]
            for h in CH:
                st, rt = LP.defaults(n, h)
                o = offered[(n, h)][w - 1]
                sold[(n, h)][w] = o * st
                ret[(n, h)][w] = (o - o * st) * rt
                con[(n, h)][w] = o - ret[(n, h)][w]
                left -= con[(n, h)][w]
            close[n][w] = left
    return dict(gross=gross, packed=packed, opening=op, shr=shr, store=store, close=close,
                room=room, sold=sold, ret=ret, con=con, land=land,
                cold=[room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)],
                amb=[room["Garlic"][w] for w in range(1, 53)])


def compare(tag, got, want, tol=1e-5):
    want = want[1:] if len(want) == 53 else want
    bad = [(w + 1, g, x) for w, (g, x) in enumerate(zip(got, want))
           if g is None or abs(float(g) - x) > tol]
    report(not bad, tag + ("" if not bad else
           f" — first mismatch wk{bad[0][0]}: sheet {bad[0][1]}, sim {bad[0][2]:.4f} "
           f"({len(bad)} weeks)"))


def offered_overrides(offered):
    ov = {}
    for (n, h), series in offered.items():
        r = BLK[n.upper()][f"{h} — OFFERED"]
        for w in range(1, 53):
            ov[f"{col(w)}{r}"] = float(series[w - 1])
    return ov


def acre_overrides(acres, binaries=True):
    """Acres in column C, and the plant/don't-plant binary in D beside it."""
    ov = {}
    for k, v in acres.items():
        ov[f"C{SUCC_ROW[k]}"] = float(v)
        if binaries:
            ov[f"D{SUCC_ROW[k]}"] = 1 if v > 1e-9 else 0
    return ov


def check_values(tag, overrides, acres, offered, **kw):
    d = calc(overrides)
    s = simulate(acres, offered, **kw)
    for n in CROPS:
        b = BLK[n.upper()]
        compare(f"[{tag}] {n} packed", row(d, b["Packed out -> INTO the store"]), s["packed"][n])
        compare(f"[{tag}] {n} in store", row(d, b["In store this week"]), s["store"][n])
        for h in CH:
            compare(f"[{tag}] {n}/{h} sold", row(d, b[f"{h} — SOLD"]), s["sold"][(n, h)])
        compare(f"[{tag}] {n} carried out", row(d, b["Stock carried out"]), s["close"][n])
        compare(f"[{tag}] {n} room", row(d, b["ROOM OCCUPANCY"]), s["room"][n], 1e-4)
    compare(f"[{tag}] LAND", row(d, LBL["LAND in the ground"][0]), s["land"])
    compare(f"[{tag}] COLD STORE", row(d, LBL["COLD STORE"][0]), [0] + s["cold"], 1e-4)
    compare(f"[{tag}] AMBIENT STORE", row(d, LBL["AMBIENT STORE"][0]), [0] + s["amb"], 1e-4)
    return d


print("A. VALUES — the sheet's formulas against an independent simulator")
# 1 acre on each of 68 plantings = 68 acres, inside the 80 available. Six each would
# be 408 and the comparison would only ever run on a wildly infeasible plan.
A6 = {k: 1.0 for k in PICKED}
ZERO = {(n, h): [0.0] * 52 for n in CROPS for h in CH}
# NOT "as shipped": v5 ships with every acre at 0 because acres are now DECISION cells. The
# baseline has to be written in, or every comparison runs against an empty farm.
d0 = check_values("1 acre each, nothing offered", acre_overrides(A6), A6, ZERO)

OPT = LP.solve()
check_values("at the LP optimum", {**acre_overrides(OPT["acres"]), **offered_overrides(OPT["offered"])},
             OPT["acres"], OPT["offered"])

# An arbitrary FEASIBLE-ish set, so the comparison is not only ever exercised at a vertex.
ARB = {(n, h): [(w * 37 % 900) * (1.0 if h.startswith("Farmers") else 2.0)
                for w in range(52)] for n in CROPS for h in CH}
ARBA = {k: 0.7 for k in PICKED}
check_values("arbitrary offered", {**acre_overrides(ARBA), **offered_overrides(ARB)}, ARBA, ARB)

print("\nB. PROPAGATION — the inputs section A cannot cover")
peak = lambda d, lab, i=0: max(float(x) for x in row(d, LBL[lab][i]) if x is not None)
total = lambda d, c, r_: sum(float(x) for x in row(d, BLK[c][r_]) if x is not None)
worst = lambda d, i: min(float(x) for x in row(d, LBL["room left"][i]) if x is not None)
FM = [h for h in CH if h.startswith("Farmers")][0]
WS_ = [h for h in CH if h.lower().startswith("wholesale")][0]
base_cold = peak(d0, "COLD STORE")

BASE_ACRES = acre_overrides(A6)     # v5 ships empty; every run must plant something first
for tag, ov, pred in [
    # On SPINACH's own room row, not the pool: the cold pool is dominated by Kale, so a
    # Spinach-only change cannot move it far and the pool-level threshold was measuring nothing.
    ("pack-out       Spinach -> 0.60", {f"C{CROP_ROW['Spinach']}": 0.60},
     lambda d: abs(total(d, "SPINACH", "ROOM OCCUPANCY")
                   / total(d0, "SPINACH", "ROOM OCCUPANCY") - 0.60) < 0.01),
    ("m3 per lb      Spinach x2",
     {f"D{CROP_ROW['Spinach']}": crops["Spinach"]["crop_size_m3_per_lb"] * 2},
     lambda d: peak(d, "COLD STORE") > base_cold * 1.2),
    ("weekly ceiling Garlic/FM -> 200", {f"D{PAIR_ROW[('Garlic', FM)]}": 200.0},
     lambda d: total(d, "GARLIC", f"{FM} — ceiling this week") < 200.0 * 52 + 1),
    ("season window  Garlic/FM from wk -> 30", {f"E{PAIR_ROW[('Garlic', FM)]}": 30},
     lambda d: total(d, "GARLIC", f"{FM} — ceiling this week") <
               total(d0, "GARLIC", f"{FM} — ceiling this week")),
    # NOT Spinach/Wholesale: its cap runs all 52 weeks, so Weekly and Annual render an identical
    # ceiling row and the test proved nothing. Garlic/FM has a real W22-W35 window.
    # An Annual pair's ceiling is a RUNNING ALLOWANCE now: week 1 shows the whole year's figure
    # and it declines as sales accumulate. Assert on week 1, not the row total.
    ("cap TYPE       Garlic/FM -> Annual", {f"C{PAIR_ROW[('Garlic', FM)]}": "Annual"},
     lambda d: abs(float(d[f"{col(1)}{BLK['GARLIC'][f'{FM} — ceiling this week']}"])
                   - float(ws.cell(row=PAIR_ROW[('Garlic', FM)], column=4).value)) < 1e-6),
    ("price          Garlic/FM -> $99", {f"I{PAIR_ROW[('Garlic', FM)]}": 99.0,
                                         **offered_overrides(OPT["offered"]),
                                         **acre_overrides(OPT["acres"])},
     lambda d: float(d[f"B{OBJ_ROW}"]) > OPT["profit"] * 1.05),
    ("growing cost   Garlic -> $99,999/ac", {f"H{CROP_ROW['Garlic']}": 99999.0,
                                             **acre_overrides(OPT["acres"])},
     lambda d: float(d[f"B{OBJ_ROW}"]) < OPT["profit"] * 0.5),
    # Shelf life is a live INPUT again (it was a dead yellow box until the grower found it).
    ("shelf life     Spinach 2 -> 1", {f"F{CROP_ROW['Spinach']}": 1},
     lambda d: total(d, "SPINACH", "Most stock its shelf life allows") <
               total(d0, "SPINACH", "Most stock its shelf life allows")),
    ("cold cap       -> 50", {f"B{CAP_ROW['cold']}": 50.0}, lambda d: worst(d, 1) < 0),
    ("ambient cap    -> 20", {f"B{CAP_ROW['ambient']}": 20.0}, lambda d: worst(d, 2) < 0),
    ("land           -> 10", {f"B{CAP_ROW['land']}": 10.0}, lambda d: worst(d, 0) < 0),
]:
    try:
        ok = pred(calc({**BASE_ACRES, **ov}))
    except AssertionError as e:
        ok, tag = False, f"{tag}  [{e}]"
    except Exception as e:
        ok, tag = False, f"{tag}  [{type(e).__name__}: {e}]"
    report(ok, tag)

print("\nC. NO FROZEN DERIVED VALUES")
week_rows = {r for r in range(1, ws.max_row + 1)
             if ws.cell(row=r, column=1).value in ("Week", "Succession")}
anchors = {r for r in range(1, ws.max_row + 1)
           if str(ws.cell(row=r, column=1).value).strip() == "Stock carried in"}
dec_rows = {BLK[n.upper()][f"{h} — OFFERED"] for n in CROPS for h in CH}
frozen = []
for line in ws.iter_rows():
    for c in line:
        if not isinstance(c.value, (int, float)) or isinstance(c.value, bool):
            continue
        rgb = str(c.fill.fgColor.rgb) if (c.fill and c.fill.fgColor) else ""
        if "FFF2CC" in rgb or "D9EAD3" in rgb or "C9DAF8" in rgb:   # input, decision, binary
            continue
        if c.row in week_rows or (c.row in anchors and c.column == 5) or c.row in dec_rows:
            continue
        frozen.append(f"{c.coordinate}={c.value} (row {ws.cell(row=c.row, column=1).value!r})")
report(not frozen, "every number is a formula, an input, or a decision cell"
       + ("" if not frozen else " — FROZEN: " + "; ".join(frozen[:6])))

print("\nD. THE READ ME PROMISES WHAT THE MODEL PRODUCES")
rd = load_workbook(WB)["READ ME"]
prose = "\n".join(str(rd.cell(row=r, column=1).value or "") for r in range(1, rd.max_row + 1))
RELAX = LP.solve(min_acreage=False)
for label, val in (("optimum profit", OPT["profit"]), ("optimum revenue", OPT["revenue"]),
                   ("growing cost", OPT["cost"]),
                   ("LP-relaxation profit", RELAX["profit"])):
    report(f"${val:,.0f}" in prose, f"READ ME states the real {label} (${val:,.0f})")
report(f"{OPT['n_planted']} of {OPT['n_offered']}" in prose,
       f"READ ME states how many successions are planted ({OPT['n_planted']} of {OPT['n_offered']})")
report(f"{RELAX['n_planted']}" in prose,
       f"READ ME states the relaxation's planting count ({RELAX['n_planted']})")

print("\nE. THE SHEET AND THE SOLVER ARE THE SAME PROBLEM")
d_opt = calc({**acre_overrides(OPT["acres"]), **offered_overrides(OPT["offered"])})
sheet_profit = float(d_opt[f"B{OBJ_ROW}"])
report(abs(sheet_profit - OPT["profit"]) < 1.0,
       f"sheet PROFIT at the LP optimum = ${sheet_profit:,.2f} vs LP ${OPT['profit']:,.2f}")
# and the LP's answer must actually be FEASIBLE on the sheet's own constraint rows
neg = [w + 1 for n in CROPS
       for w, v in enumerate(row(d_opt, BLK[n.upper()]["Stock carried out"])) if float(v) < -1e-6]
report(not neg, f"no negative stock at the optimum (weeks {neg[:5]})" if neg
       else "no negative stock at the optimum")
for pool, i in (("COLD", 1), ("AMBIENT", 2)):
    report(worst(d_opt, i) >= -1e-6, f"{pool} store not exceeded at the optimum")
report(worst(d_opt, 0) >= -1e-6, "land not exceeded at the optimum")
for n in CROPS:
    b = BLK[n.upper()]
    over = [w + 1 for w, (held, allowed) in enumerate(
        zip(row(d_opt, b["Stock carried out"]),
            row(d_opt, b["Most stock its shelf life allows"])))
        if float(held) > float(allowed) + 1e-6]
    report(not over, f"{n} never holds stock past its shelf life"
           + (f" (weeks {over[:4]})" if over else ""))

for n in CROPS:
    for h in CH:
        b = BLK[n.upper()]
        over = [w + 1 for w, (s_, c_) in enumerate(zip(row(d_opt, b[f"{h} — SOLD"]),
                                                       row(d_opt, b[f"{h} — ceiling this week"])))
                if float(s_) > float(c_) + 1e-6]
        report(not over, f"{n}/{h} never sells past its ceiling"
               + (f" (weeks {over[:4]})" if over else ""))

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURE(S)"))
sys.exit(1 if failures else 0)
