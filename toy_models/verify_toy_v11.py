"""
verify_toy_v11.py — EVALUATE the v4 workbook and prove it is the same problem the solver solves.

Run:  .venv/bin/python toy_models/verify_toy_v11.py

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
import toy_v11_lp as LP

WB = REPO / "toy_models" / "farm_toy_v11_labour.xlsx"
PFX = f"'[{WB.name}]MODEL'!"
CROPS = tuple(LP.CROP_NAMES)
CH = list(LP.CH_NAMES)
PICKED = [s["name"] for s in LP.SUCCS]
CELL_RE = re.compile(rf"'\[{re.escape(WB.name)}\]MODEL'!([A-Z]+\d+)$")

ws = load_workbook(WB)["Model"]
failures = []
crops = LP.CROPS


# `--fast` stops at the first failure. For MUTATION TESTING only: a mutation that is caught is
# caught, and running the remaining ~340 checks to confirm it again costs minutes per mutation.
# ⚠️ Never use it for a real verification run — "the first thing that broke" is not the same
# report as "everything that broke", and this project has twice learned more from the second
# and third failures than the first.
FAST = "--fast" in sys.argv


class _Caught(SystemExit):
    pass


_T0 = __import__("time").time()


def _el():
    return f"[{__import__('time').time() - _T0:6.1f}s]"


def report(ok, msg):
    print(_el() + ("  OK   " if ok else "  FAIL ") + msg, flush=True)
    if not ok:
        failures.append(msg)
        if FAST:
            print("\n1+ FAILURE(S) — stopping early (--fast)")
            raise _Caught(1)


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
             adv=None):
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
    # ⚠️ THE POSITION ROWS ARE COMPARED INDIVIDUALLY, not only through their sum. A sum can be
    # right while two rows are wrong in opposite directions, and splitting by position is the
    # whole of v10 — checking only CREW CAPACITY would leave the change itself unverified.
    pos = LP.positions()
    adv = adv or {}
    load = 1.0 + LP.PAYLOAD.get("payroll_load_pct", 0.0)
    prod = float(adv.get("productivity_pct", 70.0)) / 100.0
    head_cost = float(adv.get("cost_per_head", 800.0))
    allowance = float(adv.get("allowance", 1.25))
    mult = float(adv.get("ot_mult", 1.5))
    extra = adv.get("extra", {})
    ot_by_role = adv.get("ot_by_role", {})
    piece_lb = adv.get("piece_lb", {})
    piece_eff = adv.get("piece_eff", {})
    piece_fixed = float(adv.get("piece_fixed", 2500.0))
    piece_used = bool(adv.get("piece_used", False))
    piece_start = int(adv.get("piece_start", 1))

    # ⚠️ REBUILT PER ROLE, in the order the sheet builds it. Committed heads at full rate plus
    # extra heads at the productivity discount — and extra heads paid the FULL wage, because
    # the discount is on their hours and not their payslip.
    pos_field, pos_cost, ot_cap_role, ot_cost_role = {}, {}, {}, {}
    for q in pos:
        nm = q["name"]; ex = float(extra.get(nm, 0.0))
        on = [w for w in range(1, 53) if q["field_h"][w] > 0]
        heads = q["heads"][on[0]] if on else 0.0
        per_head_field = (q["field_h"][on[0]] / heads) if on and heads else 0.0
        per_head_cost = (q["cost"][on[0]] / heads) if on and heads else 0.0
        pos_field[nm] = [ (q["field_h"][w] + ex * per_head_field * prod) if q["field_h"][w] > 0
                          else 0.0 for w in range(53)]
        pos_cost[nm] = [ (q["cost"][w] + ex * per_head_cost) if q["field_h"][w] > 0 else 0.0
                         for w in range(53)]
        # per-role overtime: cap from THIS role's hours, rate from THIS role's wage — and
        # ⚠️ ONLY for hourly roles. Salaried staff give capacity but cannot be paid overtime,
        # so their cap is not "small", it does not exist. Computing one for them made the
        # verifier look for a row the sheet correctly never wrote.
        ot_cap_role[nm] = ([max(0.0, allowance - 1.0) * pos_field[nm][w] for w in range(53)]
                           if q["hourly"] else [0.0] * 53)
        rate = q["wage"] * load * mult if q["hourly"] else 0.0
        hrs = ot_by_role.get(nm, [0.0] * 52)
        ot_cost_role[nm] = [0.0] + [hrs[w - 1] * rate for w in range(1, 53)]
    lab_cap = [sum(pos_field[q["name"]][w] for q in pos) for w in range(53)]
    wage_wk = [sum(pos_cost[q["name"]][w] for q in pos) for w in range(53)]
    hourly_field = [sum(pos_field[q["name"]][w] for q in pos if q["hourly"])
                    for w in range(53)]
    ot_hours = [sum(ot_by_role.get(q["name"], [0.0] * 52)[w] for q in pos) for w in range(52)]
    ot_cost = [sum(ot_cost_role[q["name"]][w] for q in pos) for w in range(53)]
    head_wk = [0.0] * 53
    for q in pos:
        on = [w for w in range(1, 53) if q["field_h"][w] > 0]
        if on:
            head_wk[on[0]] += float(extra.get(q["name"], 0.0)) * head_cost
    # piece rate: pounds picked, the hours they relieve, and the COGS line
    relief = [0.0] * 53
    piece_cost = [0.0] * 53
    for cn, series in piece_lb.items():
        lh = crops[cn].get("labor_harv", 0.0) or 0.0
        lbph = (crops[cn]["yield_per_acre"] / lh) if lh else 0.0
        for w in range(1, 53):
            if lbph:
                relief[w] += series[w - 1] / lbph
            piece_cost[w] += series[w - 1] * piece_eff.get(cn, 0.0)
    if piece_used:
        piece_cost[piece_start] += piece_fixed
    avail = [lab_cap[w] + ot_hours[w - 1] if w else 0.0 for w in range(53)]
    harv_need = [0.0] * 53
    lab_used = [0.0] * 53          # net of piece-rate relief, subtracted below
    for s_ in LP.SUCCS:
        a = acres[s_["name"]]
        if a <= 1e-12:
            continue
        c = crops[CROPS[s_["crop"]]]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            lab_used[((wk - 1) % 52) + 1] += a * c.get(
                f"labor_{['plant', 'grow', 'harv'][ph]}", 0.0)
            if ph == 2:
                harv_need[((wk - 1) % 52) + 1] += a * c.get("labor_harv", 0.0)
    net = [0.0] * 53; cum = [0.0] * 53; running = opening_cash
    for w in range(1, 53):
        # ⚠️ WAGES ARE IN HERE, and in no per-acre charge anywhere. That is the W12 point: every
        # listed worker is paid for their stated hours whether the crops need them or not.
        net[w] = (rev[w] - pkg[w] - grow[w] - fixed_wk - rev[w] * ovh_pct - wage_wk[w]
                  - ot_cost[w] - head_wk[w] - piece_cost[w])
        running += net[w]; cum[w] = running

    # The floor is MINUS THE CREDIT LINE, because `cum` above is a bank balance that already
    # starts from opening cash. Flooring a balance at -(opening+credit) counts the opening
    # twice — it shipped that way, and section E could not see it because the floor is slack.
    floor = [-credit_line] * 53
    return dict(rev=rev, pkg=pkg, grow=grow, net=net, cum=cum, floor=floor, fixed_wk=fixed_wk,
                lab_cap=list(lab_cap), wage_wk=list(wage_wk), lab_used=lab_used,
                avail=avail, ot_cost=ot_cost,
                hourly_field=list(hourly_field),
                pos_field=pos_field, pos_cost=pos_cost,
                head_wk=head_wk, piece_cost=piece_cost, relief=relief,
                harv_need=harv_need,
                # ⚠️ C2's left-hand side on the sheet is crop hours LESS the relief, so the
                # simulator has to net it here — doing it after the comparison ran (which it
                # did at first) simply compares the wrong quantity.
                lab_used_net=[lab_used[w] - relief[w] for w in range(53)],
                ot_cap_role=ot_cap_role, ot_cost_role=ot_cost_role,
                gross=gross, packed=packed, opening=op, shr=shr, store=store, close=close,
                room=room, sold=sold, ret=ret, con=con, cap=cap, shelf=shelf, land=land,
                cold=[room["Spinach"][w] + room["Kale"][w] for w in range(1, 53)],
                amb=[room["Garlic"][w] for w in range(1, 53)])


CREW_ROW = {}


def _pos_row(name, after_label, before_label, suffix=""):
    """The row for position `name` between two block headers — never by ordinal.

    Each position name appears several times in column A (the roster, block A's hours row,
    block B's overtime rows, block D's cost row), so an index into the label list would be an
    ordinal whose meaning depends on layout. Addressing by the surrounding headers cannot
    drift — the trap this toy has hit four times.
    """
    lo = LBL[after_label][0]
    hi = LBL[before_label][0]
    want = (name + suffix).strip()
    hits = [r for r in range(lo, hi)
            if str(ws.cell(row=r, column=1).value or "").strip() == want]
    assert len(hits) == 1, (
        f"expected exactly one {want!r} row between {after_label!r} and {before_label!r}, "
        f"found {hits}")
    return hits[0]


def compare(tag, got, want, tol=1e-5):
    want = want[1:] if len(want) == 53 else want
    bad = [(w + 1, g, x) for w, (g, x) in enumerate(zip(got, want))
           if g is None or abs(float(g) - x) > tol]
    report(not bad, tag + ("" if not bad else
           f" — first mismatch wk{bad[0][0]}: sheet {bad[0][1]}, sim {bad[0][2]:.4f} "
           f"({len(bad)} weeks)"))


def flex_overrides(opt):
    """Every decision cell of the v11 labour layer, written in rather than computed.

    v11 has four kinds: per-ROLE overtime (no blend), extra heads on the roster, pounds picked
    by the piece-rate crew, and the one binary that engages them.
    """
    ov = {}
    for nm, series in zip(opt["role_names"], opt["ot_by_role"]):
        if not any(series):
            continue
        rr = _pos_row(nm, "B — WHAT YOU CAN ADD", "HOURS AVAILABLE", suffix=" — OVERTIME hrs")
        for w in range(1, 53):
            ov[f"{col(w)}{rr}"] = float(series[w - 1])
    for i, nm in enumerate(opt["role_names"]):
        ov[f"K{CREW_ROW[nm]}"] = float(opt["extra_heads"][i])
    for cn, series in opt["piece_lb"].items():
        rr = LBL[f"{cn} — picked by piece-rate crew"][0]
        for w in range(1, 53):
            ov[f"{col(w)}{rr}"] = float(series[w - 1])
    ov[f"B{LBL['ENGAGED?'][0]}"] = 1.0 if opt["piece_used"] else 0.0
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


def _adv_of(opt):
    """Everything the simulator needs to reproduce the LP's labour decisions."""
    return dict(extra=dict(zip(opt["role_names"], opt["extra_heads"])),
                ot_by_role=dict(zip(opt["role_names"], opt["ot_by_role"])),
                piece_lb=opt["piece_lb"], piece_eff=opt["piece_eff"],
                piece_used=opt["piece_used"],
                piece_start=opt["piece_weeks"][0] if opt["piece_weeks"] else 1)


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
                     ("CREW CAPACITY", "lab_cap"),
                     ("Harvest hours relieved", "relief"),
                     ("HOURS AVAILABLE", "avail"),
                     ("Wage bill this week", "wage_wk"),
                     ("New-head cost — ONCE, in the role's first week", "head_wk"),
                     ("Overtime cost this week", "ot_cost"),
                     ("Piece-rate cost — per lb every week, + the fixed cost ONCE", "piece_cost"),
                     ("HARVEST hours needed", "harv_need"),
                     ("CROP HOURS needed", "lab_used_net")):
        compare(f"[{tag}] {lab}", row(d, LBL[lab][0]), s[key], 1e-4)
    # ⚠️ LOCATED BETWEEN THEIR BLOCK HEADERS, not by an index into the label list. Each
    # position name appears THREE times in column A — the crew table, block A's hours row and
    # block D's cost row — so `LBL[name][1]` would be an ordinal into a list whose order
    # depends on layout. That is the "a position written down is a position that will drift"
    # trap this toy has now hit four times; addressing by the surrounding headers cannot drift.
    # every per-role row, both blocks, plus each role's own overtime cap
    for nm, series in s["ot_cap_role"].items():
        if any(series):
            compare(f"[{tag}] overtime cap: {nm}",
                    row(d, _pos_row(nm, "B — WHAT YOU CAN ADD", "HOURS AVAILABLE",
                                    suffix=" — overtime CAP")), series)
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


for _r in range(1, ws.max_row + 1):
    if str(ws.cell(row=_r, column=9).value or "").strip() in ("Y", "N") \
            and ws.cell(row=_r, column=3).value in ("salary", "hourly", "seasonal"):
        CREW_ROW[str(ws.cell(row=_r, column=1).value).strip()] = _r
assert len(CREW_ROW) == len(LP.PAYLOAD["employees"]), (
    f"found {len(CREW_ROW)} roster rows, expected {len(LP.PAYLOAD['employees'])}: {CREW_ROW}")

print(_el(), "A. VALUES — the sheet's formulas against an independent simulator")
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
              **flex_overrides(OPT)},
             OPT["acres"], OPT["offered"],
             adv=_adv_of(OPT))

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
        **flex_overrides(_t),
        f"B{CASH_ROW['opening']}": TIGHT["opening_cash"],
        f"B{CASH_ROW['credit']}": TIGHT["credit_line"]}
_td = check_values("tight cash (the floor BINDS)", _tov, _t["acres"], _t["offered"],
                   opening_cash=TIGHT["opening_cash"], credit_line=TIGHT["credit_line"],
                   adv=_adv_of(_t))
_tc = [float(x) for x in row(_td, LBL["CASH IN THE BANK"][0])]
_tf = float(row(_td, LBL["floor"][0])[0])
report(min(_tc) >= _tf - 1e-6,
       f"tight-cash plan respects the floor (deepest ${min(_tc):,.0f} vs floor ${_tf:,.0f})")
report(min(_tc) <= _tf + 25_000,
       f"and the floor is genuinely TIGHT (within $25k of it) — otherwise this proves nothing")

# ⚠️ A CONFIGURATION WITH EXTRA HEADS ACTUALLY HIRED, AND ONE ROLE'S TOGGLE OFF.
# Found by mutation: removing the `IF(Hire more?="Y", ...)` gate from block A changed NOTHING
# the verifier could see, because at the optimum extra heads are ZERO and every hireable role
# has its toggle on. The gate was guarded structurally (pytest reads the formula) and not
# behaviourally at all — the exact "defaulting a feature off leaves it unguarded" trap this
# project has now hit four times. So: force heads onto a role that is ON, force heads onto a
# role that is OFF, and require the sheet to count the first and ignore the second.
_EX = {}
_ex_on = _ex_off = None
for _q in LP.positions():
    if _q["max_extra"] > 0 and _ex_on is None:
        _ex_on = _q["name"]; _EX[_q["name"]] = 3.0
    elif _q["max_extra"] == 0 and _ex_off is None and not _q["salaried"]:
        _ex_off = _q["name"]; _EX[_q["name"]] = 5.0        # toggle is N — must be ignored
assert _ex_on and _ex_off, "fixture needs one hireable role and one non-hireable one"
_exov = {**acre_overrides(A6)}
for _nm, _n in _EX.items():
    _exov[f"K{CREW_ROW[_nm]}"] = _n
_exd = check_values("extra heads hired (one role toggled OFF)", _exov, A6, ZERO,
                    adv=dict(extra={_ex_on: 3.0}))     # the OFF role contributes nothing
# ⚠️ `report(True, ...)` renders as OK and checks NOTHING — a vacuous check dressed as a
# passing one, which is the antipattern this project has hit on the ceiling row and the cash
# floor. State the fixture, then actually test it: the ON role's heads must reach capacity and
# the OFF role's must not.
print(f"       fixture: +3 on {_ex_on!r} (toggle Y), +5 on {_ex_off!r} (toggle N)")
_cap_ex = [float(x) for x in row(_exd, LBL["CREW CAPACITY"][0])]
_cap_base = [float(x) for x in row(d0, LBL["CREW CAPACITY"][0])]
_on_wks = [w for w in range(52) if _cap_ex[w] > _cap_base[w] + 1e-6]
report(bool(_on_wks),
       f"the toggled-ON role's extra heads DO reach capacity ({len(_on_wks)} weeks) — "
       f"otherwise the fixture proves nothing")
# the OFF role is year-round, so any week outside the ON role's window must be unchanged
_q_off = next(q for q in LP.positions() if q["name"] == _ex_off)
_q_on = next(q for q in LP.positions() if q["name"] == _ex_on)
_off_only = [w for w in range(1, 53)
             if _q_off["field_h"][w] > 0 and _q_on["field_h"][w] == 0]
_leak = [w for w in _off_only if _cap_ex[w - 1] > _cap_base[w - 1] + 1e-6]
report(bool(_off_only) and not _leak,
       f"and the toggled-OFF role's {_EX[_ex_off]:.0f} heads are IGNORED in all "
       f"{len(_off_only)} weeks only it is on"
       + (f" — LEAKED in weeks {_leak[:4]}" if _leak else ""))

print(_el(), "\nB. PROPAGATION — the inputs section A cannot cover")
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

print(_el(), "\nC. NO FROZEN DERIVED VALUES")
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

print(_el(), "\nD. THE READ ME PROMISES WHAT THE MODEL PRODUCES")
rd = load_workbook(WB)["READ ME"]
prose = "\n".join(str(rd.cell(row=r, column=1).value or "") for r in range(1, rd.max_row + 1))
RELAX = LP.solve(min_acreage=False)
# Every line of the cost stack, not just a total — the prose now itemises it, and an itemised
# claim that is not itemised-checked is the P&L defect this project already fixed once (W4).
for label, val in (("optimum profit", OPT["profit"]), ("optimum revenue", OPT["revenue"]),
                   ("growing cost", OPT["growing"]), ("packaging", OPT["packaging"]),
                   ("fixed cost", OPT["fixed"]), ("overhead", OPT["overhead"]),
                   ("weekly fixed cost", OPT["fixed_weekly"]), ("wages", OPT["wages"]),
                   ("extra-head cost", OPT["hire_cost"]), ("piece-rate cost", OPT["piece_cost"]), ("interest", OPT["interest"]),
                   ("LP-relaxation profit", RELAX["profit"])):
    report(f"${val:,.0f}" in prose, f"READ ME states the real {label} (${val:,.0f})")
report(f"{OPT['n_planted']} of {OPT['n_offered']}" in prose,
       f"READ ME states how many successions are planted ({OPT['n_planted']} of {OPT['n_offered']})")
report(f"{RELAX['n_planted']}" in prose,
       f"READ ME states the relaxation's planting count ({RELAX['n_planted']})")

print(_el(), "\nE. THE SHEET AND THE SOLVER ARE THE SAME PROBLEM")
d_opt = calc({**acre_overrides(OPT["acres"]), **offered_overrides(OPT["offered"]),
              **flex_overrides(OPT)})
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
# ⚠️ PER ROLE now, and each role is checked against ITS OWN cap. Summing them first would
# let one role's slack hide another's breach — the whole reason the blend had to go.
_oth = [0.0] * 52
_otc = [0.0] * 52
for _nm in OPT["role_names"]:
    try:
        _cr = _pos_row(_nm, "B — WHAT YOU CAN ADD", "HOURS AVAILABLE", suffix=" — overtime CAP")
        _hr = _pos_row(_nm, "B — WHAT YOU CAN ADD", "HOURS AVAILABLE", suffix=" — OVERTIME hrs")
    except AssertionError:
        continue                      # salaried: no overtime rows, correctly
    _h = [float(x) for x in row(d_opt, _hr)]
    _c = [float(x) for x in row(d_opt, _cr)]
    _bad = [w + 1 for w in range(52) if _h[w] > _c[w] + 1e-6]
    report(not _bad, f"{_nm}: overtime never exceeds ITS OWN derived cap"
           + (f" (weeks {_bad[:4]})" if _bad else ""))
    for w in range(52):
        _oth[w] += _h[w]; _otc[w] += _c[w]
_otover = [w + 1 for w, (h, c_) in enumerate(zip(_oth, _otc)) if h > c_ + 1e-6]
report(not _otover, "overtime never exceeds its DERIVED weekly cap at the optimum"
       + (f" (weeks {_otover[:4]}: "
          f"{_oth[_otover[0]-1]:.0f} hrs against a {_otc[_otover[0]-1]:.0f} hr cap)"
          if _otover else ""))
_otbind = [w + 1 for w, (h, c_) in enumerate(zip(_oth, _otc)) if c_ > 0 and h >= c_ - 1e-6]
report(len(_otbind) > 0, f"and the overtime cap actually BINDS ({len(_otbind)} weeks) — a cap "
                         f"nothing ever reaches proves nothing")

# ⚠️ THE PIECE-RATE CREW'S CAPACITY, ON THE SHEET'S OWN ROWS AND IN THE SHEET'S OWN UNIT.
# v11 moved this cap from POUNDS to HOURS after the grower asked whether one lb/week figure
# could describe one crew — it cannot, because pounds per hour differ 3.6x by crop, so the
# same number was a crew of five for spinach and 1.4 for kale. The new rows need their own
# comparison in the same commit: exactly the failure this toy has shipped three times (the
# ceiling row, the shelf-life row, the whole v6 cash section were each compared against
# nothing). Section E's profit agreement cannot see an infeasible plan.
# labels() strips, and a row addressed by a label that appears twice is an ordinal in
# disguise — the trap this toy has hit four times. Assert uniqueness rather than take [0].
for _lb in ("picking hours used", "their weekly capacity"):
    assert len(LBL.get(_lb, [])) == 1, f"{_lb!r} appears {len(LBL.get(_lb, []))}x — ambiguous"
_pch = [float(x) for x in row(d_opt, LBL["picking hours used"][0])]
_pcc = [float(x) for x in row(d_opt, LBL["their weekly capacity"][0])]
_pcbad = [w + 1 for w in range(52) if _pch[w] > _pcc[w] + 1e-6]
report(not _pcbad, "piece-rate picking hours never exceed the crew's weekly capacity"
       + (f" (weeks {_pcbad[:4]}: {_pch[_pcbad[0]-1]:.1f} hrs against {_pcc[_pcbad[0]-1]:.1f})"
          if _pcbad else ""))
_pcbind = [w + 1 for w in range(52) if _pcc[w] > 0 and _pch[w] >= _pcc[w] - 1e-6]
report(len(_pcbind) > 0, f"and the piece-rate capacity actually BINDS ({len(_pcbind)} weeks) — "
                         f"a cap nothing ever reaches proves nothing")
# ⚠️ AND THE SHEET'S CAP IS THE ORACLE'S CAP. Found by a surviving mutation: give the LP a
# POUND cap while the sheet keeps its HOURS cap and every check here passes — 20,000 lb can
# never breach 200 hrs whatever the mix, so the LP hands over a plan that is feasible, priced
# to the cent, and simply WORSE. Section E proves what a plan is WORTH and that it FITS; it
# cannot see that a better one was available. The structural half of the answer is that the
# number now has one definition (LP.PIECE_MAX_HOURS_PER_WEEK, written into the sheet by the
# builder); this pins it so a retyped copy cannot come back. The optimality half is open —
# backlog L11.
_pccap_in = float(ws.cell(row=LBL["Piece-rate crew"][0], column=4).value)
report(abs(_pccap_in - LP.PIECE_MAX_HOURS_PER_WEEK) < 1e-9,
       f"the sheet's crew-hours input is the oracle's own constant "
       f"(sheet {_pccap_in:g} vs LP {LP.PIECE_MAX_HOURS_PER_WEEK:g})")
# ⚠️ AND IT IS REALLY IN HOURS. A cap still measured in pounds would satisfy both checks above
# while meaning something else entirely, so pin the unit to the arithmetic: the hours row must
# equal pounds / lb-per-harvest-hour, crop by crop, which no pound total can reproduce.
_pcexp = [sum(OPT["piece_lb"][cn][w] / OPT["lb_per_harvest_hr"][cn]
              for cn in OPT["piece_lb"] if OPT["lb_per_harvest_hr"][cn]) for w in range(52)]
_pcunit = [w + 1 for w in range(52) if abs(_pch[w] - _pcexp[w]) > 1e-6]
report(not _pcunit, "the picking-hours row converts pounds at each crop's own picking rate"
       + (f" (week {_pcunit[0]}: sheet {_pch[_pcunit[0]-1]:.3f} vs {_pcexp[_pcunit[0]-1]:.3f})"
          if _pcunit else ""))
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
