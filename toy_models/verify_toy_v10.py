"""
verify_toy_v10.py — EVALUATE the v4 workbook and prove it is the same problem the solver solves.

Run:  .venv/bin/python toy_models/verify_toy_v10.py

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
import toy_v10_lp as LP

WB = REPO / "toy_models" / "farm_toy_v10_labour.xlsx"
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
    # The first token must be a CROP — "endswith('store')" alone also caught the recipe's
    # "Constraint — cold store" lines and made a bogus block out of them.
    heads = [r for r in range(1, ws.max_row + 1)
             if isinstance(ws.cell(row=r, column=1).value, str)
             and "—" in ws.cell(row=r, column=1).value
             and ws.cell(row=r, column=1).value.endswith("store")
             and ws.cell(row=r, column=1).value.split(" ")[0].title() in CROPS]
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
CASH_ROW = {}
for r in range(1, ws.max_row + 1):
    a = ws.cell(row=r, column=1).value
    if a == "Opening cash": CASH_ROW["opening"] = r
    if a == "Credit line": CASH_ROW["credit"] = r
assert set(CASH_ROW) == {"opening", "credit"}, f"cash inputs not found: {CASH_ROW}"

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


def simulate(acres, offered, packout=None, shrink=None, caps=None,
             opening_cash=50_000.0, credit_line=250_000.0,
             ot_hours=None, adv_crew=0.0, adv=None):
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
    cap = {(n, h): [0.0] * 53 for n in CROPS for h in CH}
    shelf = {n: [0.0] * 53 for n in CROPS}
    for n in CROPS:
        for w in range(1, 53):
            op[n][w] = close[n][w - 1] if w > 1 else 0.0
            shr[n][w] = op[n][w] * shrink[n]
            store[n][w] = op[n][w] - shr[n][w] + packed[n][w]
            room[n][w] = (op[n][w] + packed[n][w]) * crops[n]["crop_size_m3_per_lb"]
            # The shelf-life bound, computed independently — it was referenced by the verifier
            # but never COMPARED, so section E only ever checked the sheet against itself and a
            # wrong formula would have passed.
            L = int(crops[n].get("shelf_life_weeks",
                                 crops[n].get("sales_spread_weeks", 1)) or 1)
            shelf[n][w] = sum(packed[n][t] * (1.0 - shrink[n]) ** (w - t)
                              for t in range(max(1, w - L + 2), w + 1))
            left = store[n][w]
            for h in CH:
                st, rt = LP.defaults(n, h)
                # The ceiling row, computed independently. It was compared against NOTHING —
                # so the annual running-allowance form (and the weekly season window) had no
                # test at all, on a sheet whose whole point is that its numbers are checkable.
                ctype, cval, w0, w1 = (caps or {}).get((n, h), LP.cap_spec(n, h))
                cap[(n, h)][w] = (cval - sum(sold[(n, h)][1:w]) if ctype == "Annual"
                                  else (cval if w0 <= w <= w1 else 0.0))
                o = offered[(n, h)][w - 1]
                sold[(n, h)][w] = o * st
                ret[(n, h)][w] = (o - o * st) * rt
                con[(n, h)][w] = o - ret[(n, h)][w]
                left -= con[(n, h)][w]
            close[n][w] = left
    # ---- money, week by week. Built independently of the sheet, which is the point: the whole
    # cash section was added in one commit and compared against NOTHING, the exact gap that has
    # bitten the ceiling row and the shelf-life row already.
    fert, fuel = LP.PAYLOAD["cost_fert_per_lb"], LP.PAYLOAD["cost_fuel_per_L"]
    ovh_pct = LP.PAYLOAD["overhead_pct_of_revenue"]
    fixed_wk = LP.weekly_fixed_cost()
    rev = [0.0] * 53; pkg = [0.0] * 53; grow = [0.0] * 53
    for n in CROPS:
        for h in CH:
            spec = crops[n].get("channels", {}).get(h, {})
            for w in range(1, 53):
                rev[w] += sold[(n, h)][w] * spec.get("price_per_lb", 0.0)
                pkg[w] += sold[(n, h)][w] * spec.get("packaging_cost_per_lb", 0.0)
    key = ["plant", "grow", "harv"]
    for s_ in LP.SUCCS:
        cn = CROPS[s_["crop"]]; c = crops[cn]; a = acres[s_["name"]]
        grow[((s_["weeks"][0] - 1) % 52) + 1] += a * c["seed_transplant_cost_per_acre"]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            w = ((wk - 1) % 52) + 1
            grow[w] += a * (c.get(f"fert_{key[ph]}", 0.0) * fert
                            + c.get(f"fuel_{key[ph]}", 0.0) * fuel)
    # Labour: capacity, the committed wage bill, and the crop hours measured against it.
    # v9's ladder, computed here in the SAME ORDER the sheet builds it, so a row that is
    # wrong on the sheet cannot be masked by a simulator that took a shortcut to the answer.
    lab_cap, wage_wk, hourly_field, hourly_heads = LP.labour_arrays()
    # ⚠️ THE POSITION ROWS ARE COMPARED INDIVIDUALLY, not only through their sum. A sum can be
    # right while two rows are wrong in opposite directions, and splitting by position is the
    # whole of v10 — checking only CREW CAPACITY would leave the change itself unverified.
    pos = LP.positions()
    pos_field = {q["name"]: list(q["field_h"]) for q in pos}
    pos_cost = {q["name"]: list(q["cost"]) for q in pos}
    ot_rate = LP.overtime_rate()
    adv = adv or {}
    adv_lo = int(adv.get("start", 43)); adv_hi = int(adv.get("end", 49))
    adv_h = float(adv.get("hours", 40.0)); adv_fp = float(adv.get("field_pct", 100.0))
    adv_wage = float(adv.get("wage", 20.0))
    adv_prod = float(adv.get("productivity_pct", 70.0))
    adv_head = float(adv.get("cost_per_head", 800.0))
    load = 1.0 + LP.PAYLOAD.get("payroll_load_pct", 0.0)
    adv_cost_wk = adv_h * adv_wage * load
    allowance = float(adv.get("allowance", 1.25))
    ot_cap = [max(0.0, allowance - 1.0) * hourly_field[w] for w in range(53)]
    ot_hours = ot_hours or [0.0] * 52
    ot_cost = [0.0] * 53
    adv_hrs = [0.0] * 53
    adv_wage_wk = [0.0] * 53
    avail = [0.0] * 53
    for w in range(1, 53):
        ot_cost[w] = ot_hours[w - 1] * ot_rate[w]
        inwin = adv_lo <= w <= adv_hi
        # ⚠️ x PRODUCTIVITY — the hours the crops actually get out of a bought hour.
        adv_hrs[w] = (adv_crew * adv_h * adv_fp / 100.0 * adv_prod / 100.0) if inwin else 0.0
        # ⚠️ COMMITTED: charged every week of the window whether the hours are used or not,
        # plus the per-head cost once, in the first week of the window.
        adv_wage_wk[w] = (adv_crew * adv_cost_wk if inwin else 0.0) + (
            adv_crew * adv_head if w == adv_lo else 0.0)
        avail[w] = lab_cap[w] + ot_hours[w - 1] + adv_hrs[w]
    lab_used = [0.0] * 53
    for s_ in LP.SUCCS:
        a = acres[s_["name"]]
        if a <= 1e-12:
            continue
        c = crops[CROPS[s_["crop"]]]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            lab_used[((wk - 1) % 52) + 1] += a * c.get(
                f"labor_{['plant', 'grow', 'harv'][ph]}", 0.0)
    net = [0.0] * 53; cum = [0.0] * 53; running = opening_cash
    for w in range(1, 53):
        # ⚠️ WAGES ARE IN HERE, and in no per-acre charge anywhere. That is the W12 point: every
        # listed worker is paid for their stated hours whether the crops need them or not.
        net[w] = (rev[w] - pkg[w] - grow[w] - fixed_wk - rev[w] * ovh_pct - wage_wk[w]
                  - ot_cost[w] - adv_wage_wk[w])
        running += net[w]; cum[w] = running

    # The floor is MINUS THE CREDIT LINE, because `cum` above is a bank balance that already
    # starts from opening cash. Flooring a balance at -(opening+credit) counts the opening
    # twice — it shipped that way, and section E could not see it because the floor is slack.
    floor = [-credit_line] * 53
    return dict(rev=rev, pkg=pkg, grow=grow, net=net, cum=cum, floor=floor, fixed_wk=fixed_wk,
                lab_cap=list(lab_cap), wage_wk=list(wage_wk), lab_used=lab_used,
                avail=avail, ot_cost=ot_cost, ot_rate=list(ot_rate), ot_cap=ot_cap,
                hourly_field=list(hourly_field), hourly_heads=list(hourly_heads),
                pos_field=pos_field, pos_cost=pos_cost,
                adv_hrs=adv_hrs, adv_wage_wk=adv_wage_wk,
                gross=gross, packed=packed, opening=op, shr=shr, store=store, close=close,
                room=room, sold=sold, ret=ret, con=con, cap=cap, shelf=shelf, land=land,
                cold=[room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)],
                amb=[room["Garlic"][w] for w in range(1, 53)])


def _pos_row(name, after_label, before_label):
    """The row for position `name` between two block headers — never by ordinal."""
    lo = LBL[after_label][0]
    hi = LBL[before_label][0]
    hits = [r for r in range(lo, hi)
            if str(ws.cell(row=r, column=1).value or "").strip() == name.strip()]
    assert len(hits) == 1, (
        f"expected exactly one {name!r} row between {after_label!r} and {before_label!r}, "
        f"found {hits}")
    return hits[0]


def compare(tag, got, want, tol=1e-5):
    want = want[1:] if len(want) == 53 else want
    bad = [(w + 1, g, x) for w, (g, x) in enumerate(zip(got, want))
           if g is None or abs(float(g) - x) > tol]
    report(not bad, tag + ("" if not bad else
           f" — first mismatch wk{bad[0][0]}: sheet {bad[0][1]}, sim {bad[0][2]:.4f} "
           f"({len(bad)} weeks)"))


def flex_overrides(ot_hours, adv_crew):
    """The decision cells of the labour layer, written in rather than computed.

    v9: 52 overtime cells and ONE headcount, where v8 had 104 bought-hour cells. The advisory
    crew is a single scalar in column B — that IS the L1 change, expressed as a fixture.
    """
    ov = {}
    r = LBL["OVERTIME hours"][0]
    for w in range(1, 53):
        ov[f"{col(w)}{r}"] = float(ot_hours[w - 1])
    ov[f"B{LBL['PEOPLE TO HIRE'][0]}"] = float(adv_crew)
    return ov


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
            compare(f"[{tag}] {n}/{h} ceiling",
                    row(d, b[f"{h} — most you may sell this week"]), s["cap"][(n, h)])
            compare(f"[{tag}] {n}/{h} sold", row(d, b[f"{h} — SOLD"]), s["sold"][(n, h)])
        compare(f"[{tag}] {n} carried out", row(d, b["Stock carried out"]), s["close"][n])
        compare(f"[{tag}] {n} shelf-life bound",
                row(d, b["Most stock its shelf life allows"]), s["shelf"][n], 1e-4)
        compare(f"[{tag}] {n} room", row(d, b["ROOM OCCUPANCY"]), s["room"][n], 1e-4)
    # ⚠️ EVERY RUNG OF THE LADDER IS COMPARED, not just the ones that feed money. v8 checked
    # capacity and the two rates and skipped everything between them, which is how an
    # intermediate row can be wrong while the total looks right. The point of naming the rows
    # was to make them checkable; this is that half of the bargain.
    for lab, key in (("Revenue", "rev"), ("packaging", "pkg"), ("growing cost", "grow"),
                     ("NET CASH this week", "net"), ("CASH IN THE BANK", "cum"),
                     ("floor", "floor"),
                     ("Hourly field hours", "hourly_field"),
                     ("CREW CAPACITY", "lab_cap"),
                     ("Overtime CAP", "ot_cap"),
                     ("Proposed hire hours", "adv_hrs"),
                     ("HOURS AVAILABLE", "avail"),
                     ("Wage bill this week", "wage_wk"),
                     ("Proposed hire cost this week", "adv_wage_wk"),
                     ("Overtime cost this week", "ot_cost"),
                     ("CROP HOURS needed", "lab_used")):
        compare(f"[{tag}] {lab}", row(d, LBL[lab][0]), s[key], 1e-4)
    # ⚠️ LOCATED BETWEEN THEIR BLOCK HEADERS, not by an index into the label list. Each
    # position name appears THREE times in column A — the crew table, block A's hours row and
    # block D's cost row — so `LBL[name][1]` would be an ordinal into a list whose order
    # depends on layout. That is the "a position written down is a position that will drift"
    # trap this toy has now hit four times; addressing by the surrounding headers cannot drift.
    for nm, series in s["pos_field"].items():
        compare(f"[{tag}] position hours: {nm}",
                row(d, _pos_row(nm, "A — WHO IS ON, WEEK BY WEEK", "CREW CAPACITY")), series)
    for nm, series in s["pos_cost"].items():
        compare(f"[{tag}] position cost: {nm}",
                row(d, _pos_row(nm, "D — WHAT IT COSTS", "Wage bill this week")), series)
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
check_values("at the LP optimum",
             {**acre_overrides(OPT["acres"]), **offered_overrides(OPT["offered"]),
              **flex_overrides(OPT["ot_hours"], OPT["adv_crew"])},
             OPT["acres"], OPT["offered"],
             ot_hours=OPT["ot_hours"], adv_crew=OPT["adv_crew"])

# An arbitrary FEASIBLE-ish set, so the comparison is not only ever exercised at a vertex.
ARB = {(n, h): [(w * 37 % 900) * (1.0 if h.startswith("Farmers") else 2.0)
                for w in range(52)] for n in CROPS for h in CH}
ARBA = {k: 0.7 for k in PICKED}
check_values("arbitrary offered", {**acre_overrides(ARBA), **offered_overrides(ARB)}, ARBA, ARB)

# ⚠️ A STRESSED CONFIGURATION, AND IT IS NOT OPTIONAL. The three configs above all run at the
# SHIPPED defaults — pack-out 1.00 and shrink 0 — so neither was exercised anywhere, and the
# shelf-life bound's age-decay was untestable by construction.
#
# GARLIC must be the crop carrying the shrink. Decay only bites where a crop has BOTH a long
# shelf life AND shrink: Spinach and Kale are L=2, so their window is a single week, age is
# always 0, and (1-shrink)^0 = 1 whatever shrink is. Measured — with shrink only on Kale,
# deleting the ENTIRE decay term changed nothing and every check still passed.
#
# Offering only a trickle is also deliberate: stock has to SIT for age to exist at all.
STRESS_A = {k: 3.0 for k in PICKED}
STRESS_OFF = {(n, h): [400.0] * 52 for n in CROPS for h in CH}
STRESS_PACK = {"Spinach": 0.80, "Kale": 1.00, "Garlic": 0.90}
STRESS_SHRINK = {"Spinach": 0.0, "Kale": 0.05, "Garlic": 0.02}
check_values("stressed (pack-out + shrink on a storable)",
             {**acre_overrides(STRESS_A), **offered_overrides(STRESS_OFF),
              **{f"C{CROP_ROW[n]}": v for n, v in STRESS_PACK.items()},
              **{f"G{CROP_ROW[n]}": v for n, v in STRESS_SHRINK.items()}},
             STRESS_A, STRESS_OFF, packout=STRESS_PACK, shrink=STRESS_SHRINK)

# ⚠️ A BINDING CASH CASE. At $50k + $250k the deepest position is +$6,585 against a -$250,000
# floor, so the constraint is slack and any floor formula whatsoever would pass. Tightened until
# it bites, the sheet and the LP have to agree on where the line actually is.
# ⚠️ $10k + $10k is now INFEASIBLE, and that is the finding rather than a broken fixture: with
# COMMITTED wages the farm owes $4,884/wk from January against no revenue until spring, so
# $56,676 goes out before a dollar comes in and no plan avoids it. Measured, the farm cannot
# operate at all below roughly $80-100k of opening cash plus credit. $50k + $50k is the tightest
# level that still solves.
TIGHT = dict(opening_cash=50_000.0, credit_line=50_000.0)
_t = LP.solve(**TIGHT)
_tov = {**acre_overrides(_t["acres"]), **offered_overrides(_t["offered"]),
        **flex_overrides(_t["ot_hours"], _t["adv_crew"]),
        f"B{CASH_ROW['opening']}": TIGHT["opening_cash"],
        f"B{CASH_ROW['credit']}": TIGHT["credit_line"]}
_td = check_values("tight cash (the floor BINDS)", _tov, _t["acres"], _t["offered"],
                   opening_cash=TIGHT["opening_cash"], credit_line=TIGHT["credit_line"],
                   ot_hours=_t["ot_hours"], adv_crew=_t["adv_crew"])
_tc = [float(x) for x in row(_td, LBL["CASH IN THE BANK"][0])]
_tf = float(row(_td, LBL["floor"][0])[0])
report(min(_tc) >= _tf - 1e-6,
       f"tight-cash plan respects the floor (deepest ${min(_tc):,.0f} vs floor ${_tf:,.0f})")
report(min(_tc) <= _tf + 25_000,
       f"and the floor is genuinely TIGHT (within $25k of it) — otherwise this proves nothing")

print("\nB. PROPAGATION — the inputs section A cannot cover")
peak = lambda d, lab, i=0: max(float(x) for x in row(d, LBL[lab][i]) if x is not None)
total = lambda d, c, r_: sum(float(x) for x in row(d, BLK[c][r_]) if x is not None)
def worst(d, label):
    """Slack in a constraint block, addressed BY NAME.

    ⚠️ This used to take an ORDINAL into the list of "room left" rows, and it was already wrong:
    the order is land, labour, cold, ambient, so index 1 ("cold cap") was reading LABOUR and
    index 2 ("ambient cap") was reading COLD. Both passed anyway — a wrong row and a right row
    agree whenever neither is the binding one. Adding v8's two purchase-cap blocks shifted every
    index and finally made it fail. Same lesson as the READ ME coordinates and the week columns:
    a position written down is a position that will drift.
    """
    used = LBL[label][0]
    got = str(ws.cell(row=used + 3, column=1).value or "").strip()
    assert got == "room left", f"{label!r}: expected a room-left row at +3, found {got!r}"
    return min(float(x) for x in row(d, used + 3) if x is not None)
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
     lambda d: total(d, "GARLIC", f"{FM} — most you may sell this week") < 200.0 * 52 + 1),
    ("season window  Garlic/FM from wk -> 30", {f"E{PAIR_ROW[('Garlic', FM)]}": 30},
     lambda d: total(d, "GARLIC", f"{FM} — most you may sell this week") <
               total(d0, "GARLIC", f"{FM} — most you may sell this week")),
    # NOT Spinach/Wholesale: its cap runs all 52 weeks, so Weekly and Annual render an identical
    # ceiling row and the test proved nothing. Garlic/FM has a real W22-W35 window.
    # An Annual pair's ceiling is a RUNNING ALLOWANCE now: week 1 shows the whole year's figure
    # and it declines as sales accumulate. Assert on week 1, not the row total.
    ("cap TYPE       Garlic/FM -> Annual", {f"C{PAIR_ROW[('Garlic', FM)]}": "Annual"},
     lambda d: abs(float(d[f"{col(1)}{BLK['GARLIC'][f'{FM} — most you may sell this week']}"])
                   - float(ws.cell(row=PAIR_ROW[('Garlic', FM)], column=4).value)) < 1e-6),
    ("price          Garlic/FM -> $99", {f"I{PAIR_ROW[('Garlic', FM)]}": 99.0,
                                         **offered_overrides(OPT["offered"]),
                                         **acre_overrides(OPT["acres"])},
     lambda d: float(d[f"B{OBJ_ROW}"]) > OPT["profit"] * 1.05),
    ("growing cost   Garlic -> $99,999/ac", {f"H{CROP_ROW['Garlic']}": 99999.0,
                                             **acre_overrides(OPT["acres"])},
     lambda d: float(d[f"B{OBJ_ROW}"]) < OPT["profit"] * 0.5),
    # ⚠️ SELL-THROUGH AND RETURNS SHIP INERT (both effectively off at 1.00 / no offering), so
    # nothing exercised them until these were added — a mechanism that exists, is documented,
    # and is tested by nothing because the DEFAULT makes it invisible. These three are exactly
    # what the READ ME's Experiment 1 promises, so they must hold or the instructions are wrong.
    # Offered pounds are written in first: with nothing offered there is nothing to lose.
    ("SELL-THROUGH   Spinach/FM 1.00 -> 0.85 (perishable: a LOSS)",
     {**offered_overrides(OPT["offered"]), f"G{PAIR_ROW[('Spinach', FM)]}": 0.85},
     lambda d: total(d, "SPINACH", "market loss (gone)") > 0),
    ("SELL-THROUGH   Garlic/FM 1.00 -> 0.85 (storable: a DELAY, not a loss)",
     {**offered_overrides(OPT["offered"]), f"G{PAIR_ROW[('Garlic', FM)]}": 0.85},
     lambda d: total(d, "GARLIC", "market loss (gone)") == 0
               and total(d, "GARLIC", "returned to store") > 0),
    ("RETURNS        Garlic/FM 1.00 -> 0.00 (the delay becomes a loss)",
     {**offered_overrides(OPT["offered"]), f"G{PAIR_ROW[('Garlic', FM)]}": 0.85,
      f"H{PAIR_ROW[('Garlic', FM)]}": 0.00},
     lambda d: total(d, "GARLIC", "market loss (gone)") > 0),
    # Shelf life is a live INPUT again (it was a dead yellow box until the grower found it).
    ("shelf life     Spinach 2 -> 1", {f"F{CROP_ROW['Spinach']}": 1},
     lambda d: total(d, "SPINACH", "Most stock its shelf life allows") <
               total(d0, "SPINACH", "Most stock its shelf life allows")),
    ("opening cash   -> 5,000", {f"B{CASH_ROW['opening']}": 5000.0},
     lambda d: float(d[f"{col(1)}{LBL['CASH IN THE BANK'][0]}"])
               < float(d0[f"{col(1)}{LBL['CASH IN THE BANK'][0]}"])),
    ("credit line    -> 1,000", {f"B{CASH_ROW['credit']}": 1000.0},
     lambda d: float(d[f"{col(1)}{LBL["floor"][0]}"])
               > float(d0[f"{col(1)}{LBL["floor"][0]}"])),
    ("cold cap       -> 50", {f"B{CAP_ROW['cold']}": 50.0}, lambda d: worst(d, "COLD STORE") < 0),
    ("ambient cap    -> 20", {f"B{CAP_ROW['ambient']}": 20.0}, lambda d: worst(d, "AMBIENT STORE") < 0),
    ("land           -> 10", {f"B{CAP_ROW['land']}": 10.0}, lambda d: worst(d, "LAND in the ground") < 0),
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
# Every line of the cost stack, not just a total — the prose now itemises it, and an itemised
# claim that is not itemised-checked is the P&L defect this project already fixed once (W4).
for label, val in (("optimum profit", OPT["profit"]), ("optimum revenue", OPT["revenue"]),
                   ("growing cost", OPT["growing"]), ("packaging", OPT["packaging"]),
                   ("fixed cost", OPT["fixed"]), ("overhead", OPT["overhead"]),
                   ("weekly fixed cost", OPT["fixed_weekly"]), ("wages", OPT["wages"]),
                   ("advisory crew cost", OPT["adv_cost"]), ("interest", OPT["interest"]),
                   ("LP-relaxation profit", RELAX["profit"])):
    report(f"${val:,.0f}" in prose, f"READ ME states the real {label} (${val:,.0f})")
report(f"{OPT['n_planted']} of {OPT['n_offered']}" in prose,
       f"READ ME states how many successions are planted ({OPT['n_planted']} of {OPT['n_offered']})")
report(f"{RELAX['n_planted']}" in prose,
       f"READ ME states the relaxation's planting count ({RELAX['n_planted']})")

print("\nE. THE SHEET AND THE SOLVER ARE THE SAME PROBLEM")
d_opt = calc({**acre_overrides(OPT["acres"]), **offered_overrides(OPT["offered"]),
              **flex_overrides(OPT["ot_hours"], OPT["adv_crew"])})
sheet_profit = float(d_opt[f"B{OBJ_ROW}"])
report(abs(sheet_profit - OPT["profit"]) < 1.0,
       f"sheet PROFIT at the LP optimum = ${sheet_profit:,.2f} vs LP ${OPT['profit']:,.2f}")
# and the LP's answer must actually be FEASIBLE on the sheet's own constraint rows
neg = [w + 1 for n in CROPS
       for w, v in enumerate(row(d_opt, BLK[n.upper()]["Stock carried out"])) if float(v) < -1e-6]
report(not neg, f"no negative stock at the optimum (weeks {neg[:5]})" if neg
       else "no negative stock at the optimum")
for pool in ("COLD STORE", "AMBIENT STORE"):
    report(worst(d_opt, pool) >= -1e-6, f"{pool} not exceeded at the optimum")
report(worst(d_opt, "LAND in the ground") >= -1e-6,
       "land not exceeded at the optimum")
_lu = [float(x) for x in row(d_opt, LBL["CROP HOURS needed"][0])]
# ⚠️ Measured against HOURS AVAILABLE, not the fixed crew. With flex on, crop hours SHOULD
# exceed the standing crew — that is the whole point of buying hours — and this check flagged
# weeks 8/9/11/12 until it was pointed at the right row. A stale ceiling reads as a defect.
_lc = [float(x) for x in row(d_opt, LBL["HOURS AVAILABLE"][0])]
_crew = [float(x) for x in row(d_opt, LBL["CREW CAPACITY"][0])]
_over = [w + 1 for w, (u, c_) in enumerate(zip(_lu, _lc)) if u > c_ + 1e-6]
report(not _over, "crop hours never exceed the hours AVAILABLE at the optimum"
       + (f" (weeks {_over[:4]})" if _over else ""))
_bought = [w + 1 for w, (u, c_) in enumerate(zip(_lu, _crew)) if u > c_ + 1e-6]
report(len(_bought) > 0, f"and bought hours are genuinely USED ({len(_bought)} weeks exceed the "
                         f"standing crew) — otherwise the flex layer is inert")
_tightwks = [w + 1 for w, (u, c_) in enumerate(zip(_lu, _lc)) if c_ > 0 and u >= c_ - 1e-6]
report(len(_tightwks) > 0, f"C2 actually BINDS ({len(_tightwks)} of 52 weeks) — a slack "
                           f"capacity row would prove nothing")

# ⚠️ THE OVERTIME CAP MUST BE CHECKED ON THE SHEET'S OWN ROWS, and this check exists because a
# mutation walked through everything else. Deleting the cap CONSTRAINT from the LP leaves the
# sheet-vs-LP profit comparison perfectly happy: the LP hands over a plan with too much
# overtime, the sheet prices that plan correctly, and the two agree to the cent. Section E
# proves the sheet and the LP agree on what a plan is WORTH; on its own it says nothing about
# whether the plan is FEASIBLE against a limit the sheet draws. That is v5's "the ceiling row
# was compared against nothing" in a new place.
_oth = [float(x) for x in row(d_opt, LBL["OVERTIME hours"][0])]
_otc = [float(x) for x in row(d_opt, LBL["Overtime CAP"][0])]
_otover = [w + 1 for w, (h, c_) in enumerate(zip(_oth, _otc)) if h > c_ + 1e-6]
report(not _otover, "overtime never exceeds its DERIVED weekly cap at the optimum"
       + (f" (weeks {_otover[:4]}: "
          f"{_oth[_otover[0]-1]:.0f} hrs against a {_otc[_otover[0]-1]:.0f} hr cap)"
          if _otover else ""))
_otbind = [w + 1 for w, (h, c_) in enumerate(zip(_oth, _otc)) if c_ > 0 and h >= c_ - 1e-6]
report(len(_otbind) > 0, f"and the overtime cap actually BINDS ({len(_otbind)} weeks) — a cap "
                         f"nothing ever reaches proves nothing")
# ⚠️ THE ZERO CASE NEEDS A ROSTER THAT CAN PRODUCE ONE. This farm keeps two year-round hourly
# Equipment Operators, so its hourly crew never empties (minimum 72 field hours) and asserting
# "some week has no hourly crew" FAILED on a correct model — a guard demanding a condition the
# fixture cannot produce, which is as damaging as missing a defect because it teaches you to
# ignore the guard. So the zero case is tested where it exists: strip the year-round hourly
# roles and the cap must collapse to nothing in the weeks the seasonal crews are away.
# One call. It walks the whole roster, and it was being made three times in six lines.
_hf_shipped = LP.labour_arrays()[2]
_shipped_zero = [w for w in range(1, 53) if _hf_shipped[w] <= 1e-9]
report(not _shipped_zero,
       f"this farm's hourly crew never empties (min {min(_hf_shipped[1:]):.0f} field hrs) — so "
       f"the zero case is tested below, on a roster that can produce one")
_saved = LP.PAYLOAD["employees"]
try:
    LP.PAYLOAD["employees"] = [e for e in _saved
                               if e["type"] == "salary" or e.get("end_week", 52) < 52
                               or e.get("start_week", 1) > 1]
    _hf2 = LP.labour_arrays()[2]
    _cap2 = [max(0.0, 1.25 - 1.0) * _hf2[w] for w in range(53)]
    _quiet = [w for w in range(1, 53) if _hf2[w] <= 1e-9]
    report(len(_quiet) > 0 and all(_cap2[w] <= 1e-9 for w in _quiet),
           f"with no year-round hourly crew the overtime cap is ZERO in all {len(_quiet)} "
           f"unstaffed weeks — you cannot work overtime on people who are not there, and v8's "
           f"flat 200 said you could")
    _busy2 = [w for w in range(1, 53) if _hf2[w] > 0]
    report(bool(_busy2) and all(abs(_cap2[w] - 0.25 * _hf2[w]) < 1e-9 for w in _busy2),
           f"and it is exactly 25% of the hourly crew in the {len(_busy2)} staffed weeks")
finally:
    LP.PAYLOAD["employees"] = _saved

# ⚠️ AND THE LP MUST HAVE OPTIMISED THE OBJECTIVE IT REPORTS. The other survivor: pricing the
# advisory crew for one week in c_obj while the report prices the whole window makes the solver
# choose on numbers nothing else uses. Both the sheet and the report then price that plan
# correctly and agree — the plan is simply the wrong one, chosen against invisible prices.
report(abs(OPT["obj_value"] - OPT["obj_from_parts"]) < 1.0,
       f"the LP maximised the objective it reports (${OPT['obj_value']:,.2f} vs parts "
       f"${OPT['obj_from_parts']:,.2f})")
_int = float(d_opt[f"B{[r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == 'Interest'][0]}"])
report(abs(_int - OPT["interest"]) < 1.0,
       f"sheet interest ${_int:,.2f} matches the LP's ${OPT['interest']:,.2f}")
_pb = float(d_opt[f"B{[r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == 'Peak borrowing'][0]}"])
report(abs(_pb - OPT["peak_borrow"]) < 1.0,
       f"sheet peak borrowing ${_pb:,.0f} matches the LP's ${OPT['peak_borrow']:,.0f}")
_cum = row(d_opt, LBL["CASH IN THE BANK"][0])
_flr = row(d_opt, LBL["floor"][0])
_bust = [w + 1 for w, (c_, f_) in enumerate(zip(_cum, _flr)) if float(c_) < float(f_) - 1e-6]
report(not _bust, "cash never falls through the floor at the optimum"
       + (f" (weeks {_bust[:4]})" if _bust else ""))
_low = min(float(x) for x in _cum)
print(f"       deepest cash position: ${_low:,.0f}  "
      f"(floor ${float(_flr[0]):,.0f}) — headroom ${_low - float(_flr[0]):,.0f}")
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
                                                       row(d_opt, b[f"{h} — most you may sell this week"])))
                if float(s_) > float(c_) + 1e-6]
        report(not over, f"{n}/{h} never sells past its ceiling"
               + (f" (weeks {over[:4]})" if over else ""))

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURE(S)"))
sys.exit(1 if failures else 0)
