"""
toy_v5_lp.py — the v5 sheet's model, written as a MILP and solved with scipy.

Imported by BOTH `build_toy_v5.py` (so the READ ME can promise the optimum LibreOffice should
find) and `verify_toy_v5.py` (as the oracle the workbook is checked against).

WHY THIS EXISTS. v4 is the first version whose answer is not arithmetic — it is a CHOICE, made
by a solver. So "is the sheet right?" splits in two:

  * do the sheet's FORMULAS compute correctly for any given set of offered pounds?  — the
    simulator, as in v1-v3.
  * is the sheet's CONSTRAINT STRUCTURE the same problem?  — this module. It builds the same
    LP independently and solves it with `scipy.optimize.milp`, the same HiGHS wrapper
    `farm_v2/solver.py` uses. Writing its solution into the sheet must reproduce the sheet's
    own objective cell exactly.

If LibreOffice's CoinMP finds a different optimum than HiGHS finds here, one of the two models
is not the model we think it is — which is the only question that matters about v4.

v5 ADDS THE TWO THINGS THE GROWER FOUND MISSING FROM v4:

  * EVERY succession the app's calendar generator offers, not five hand-picked ones. Choosing
    WHEN to plant is part of what the real solver decides, and freeing it was worth +128%.
  * BINARY plant / do-not-plant variables with a minimum acreage (the app's C9 and C10), which
    is what stops the optimizer planting a third of an acre. This makes it a MILP, exactly as
    `farm_v2/solver.py` is — `integrality` there marks the same y block.

Those two pull in opposite directions: the full calendar raises profit, the minimum acreage
lowers it. Neither is meaningful alone.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from farm_v2.utils.calendar import generate_successions, harvest_weeks_of
from farm_v2.utils.demand import build_demand_table, build_annual_caps

CROP_NAMES = ["Spinach", "Kale", "Garlic"]
# v5 offers EVERY legal start week, exactly as generate_successions does for the app.
PICKED = None
N_WEEKS = 52


def load():
    payload = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
    crops = {c["name"]: c for c in payload["crops"] if c["name"] in CROP_NAMES}
    ch_order = sorted(payload["channels"], key=lambda ch: -max(
        crops[c].get("channels", {}).get(ch["name"], {}).get("price_per_lb", 0)
        for c in CROP_NAMES))
    return payload, crops, ch_order, generate_successions(list(crops.values()), 2024)


PAYLOAD, CROPS, CH_ORDER, SUCCS = load()
CH_NAMES = [c["name"] for c in CH_ORDER]
_DT = build_demand_table(list(CROPS.values()), CH_ORDER, N_WEEKS)
_AC = build_annual_caps(list(CROPS.values()), CH_ORDER)


def cap_spec(cn, hn):
    ci, hi = CROP_NAMES.index(cn), CH_NAMES.index(hn)
    if (ci, hi) in _AC:
        return "Annual", float(_AC[(ci, hi)]), 1, N_WEEKS
    row = _DT[ci, hi, 1:]
    wks = [w + 1 for w in range(N_WEEKS) if row[w] > 0]
    return ("Weekly", float(row[wks[0] - 1]), wks[0], wks[-1]) if wks else ("Weekly", 0.0, 1, N_WEEKS)


def defaults(cn, hn):
    contract = hn.lower().startswith("wholesale")
    storable = not CROPS[cn].get("cold_storage", True)
    return (1.00 if contract else 0.85, 0.00 if contract else (1.00 if storable else 0.00))


def solve(pack_out=1.00, shrink=None, land=None, cold_cap=None, amb_cap=None,
          fixed_acres=None, min_acreage=True):
    """Maximise revenue - growing cost, as a MILP. Returns a dict of the optimum.

    `min_acreage=False` drops the binaries and solves the LP relaxation — useful only to show
    what the minimum-acreage rule costs, never as an answer.
    """
    shrink = shrink or {n: 0.0 for n in CROP_NAMES}
    land = PAYLOAD["total_land"] if land is None else land
    cold_cap = PAYLOAD["harvest_storage_cap"] if cold_cap is None else cold_cap
    amb_cap = PAYLOAD["ambient_storage_cap"] if amb_cap is None else amb_cap

    n_s = len(SUCCS)
    pairs = [(c, h) for c in CROP_NAMES for h in CH_NAMES]
    n_off = len(pairs) * N_WEEKS
    n_y = n_s if min_acreage else 0
    N = n_s + n_off + n_y
    off_i = lambda p, w: n_s + p * N_WEEKS + (w - 1)
    y_i = lambda i: n_s + n_off + i

    # lb packed out per acre of succession i, in week w
    packed_per_acre = np.zeros((n_s, N_WEEKS + 1))
    for i, s in enumerate(SUCCS):
        cn = CROP_NAMES[s["crop"]]
        hw = harvest_weeks_of(s, N_WEEKS)
        for w in hw:
            packed_per_acre[i, w] += CROPS[cn]["yield_per_acre"] / max(1, len(hw)) * pack_out

    # objective: -(revenue - cost) because milp minimises
    c_obj = np.zeros(N)
    for i, s in enumerate(SUCCS):
        c_obj[i] += CROPS[CROP_NAMES[s["crop"]]]["seed_transplant_cost_per_acre"]
    for p, (cn, hn) in enumerate(pairs):
        st, _ = defaults(cn, hn)
        price = CROPS[cn].get("channels", {}).get(hn, {}).get("price_per_lb", 0.0)
        for w in range(1, N_WEEKS + 1):
            c_obj[off_i(p, w)] -= st * price

    rows, lo, hi = [], [], []

    def add(coefs, l, h):
        rows.append(coefs); lo.append(l); hi.append(h)

    # closing stock, as a linear expression per crop-week (carries with shrink)
    close = {cn: [np.zeros(N) for _ in range(N_WEEKS + 1)] for cn in CROP_NAMES}
    opening = {cn: [np.zeros(N) for _ in range(N_WEEKS + 1)] for cn in CROP_NAMES}
    packed = {cn: [np.zeros(N) for _ in range(N_WEEKS + 1)] for cn in CROP_NAMES}
    for cn in CROP_NAMES:
        for w in range(1, N_WEEKS + 1):
            pk = np.zeros(N)
            for i, s in enumerate(SUCCS):
                if CROP_NAMES[s["crop"]] == cn:
                    pk[i] = packed_per_acre[i, w]
            packed[cn][w] = pk
            op = close[cn][w - 1] if w > 1 else np.zeros(N)
            opening[cn][w] = op
            expr = op * (1.0 - shrink[cn]) + pk
            for p, (c2, h2) in enumerate(pairs):
                if c2 != cn:
                    continue
                st, ret = defaults(c2, h2)
                consumed = 1.0 - (1.0 - st) * ret       # offered minus what came home
                expr = expr.copy()
                expr[off_i(p, w)] -= consumed
            close[cn][w] = expr
            add(expr, 0.0, np.inf)                       # stock never negative

    # sold <= weekly ceiling  (an Annual pair gets no weekly row — same as the app)
    for p, (cn, hn) in enumerate(pairs):
        ctype, cval, w0, w1 = cap_spec(cn, hn)
        st, _ = defaults(cn, hn)
        if ctype == "Annual":
            e = np.zeros(N)
            for w in range(1, N_WEEKS + 1):
                e[off_i(p, w)] = st
            add(e, -np.inf, cval)                        # C6b: the yearly total
        else:
            for w in range(1, N_WEEKS + 1):
                e = np.zeros(N)
                e[off_i(p, w)] = st
                add(e, -np.inf, cval if w0 <= w <= w1 else 0.0)

    # C4c — shelf life. Nothing in store may be older than its shelf life, so held stock is
    # bounded by what arrived in the last L weeks (L counts the harvest week, so the window is
    # L-1 weeks of arrivals). Linear: the window bounds come from an INPUT, not a decision.
    for cn in CROP_NAMES:
        L = int(CROPS[cn].get("shelf_life_weeks",
                              CROPS[cn].get("sales_spread_weeks", 1)) or 1)
        if L >= N_WEEKS:
            continue
        for w in range(1, N_WEEKS + 1):
            e = close[cn][w].copy()
            for t in range(max(1, w - L + 2), w + 1):
                e -= packed[cn][t]
            add(e, -np.inf, 0.0)

    # storage: opening stock + everything packed out this week, by pool
    for pool, cap in (("Cold", cold_cap), ("Ambient", amb_cap)):
        members = [n for n in CROP_NAMES
                   if ("Cold" if CROPS[n].get("cold_storage", True) else "Ambient") == pool]
        for w in range(1, N_WEEKS + 1):
            e = np.zeros(N)
            for cn in members:
                e += (opening[cn][w] + packed[cn][w]) * CROPS[cn]["crop_size_m3_per_lb"]
            add(e, -np.inf, cap)

    # land standing in the ground
    for w in range(1, N_WEEKS + 1):
        e = np.zeros(N)
        for i, s in enumerate(SUCCS):
            if any(((wk - 1) % N_WEEKS) + 1 == w for wk in s["weeks"]):
                e[i] = 1.0
        add(e, -np.inf, land)

    # C9 / C10 — the plant / do-not-plant decision, exactly as farm_v2 states it:
    #     x_i <= land x y_i        (cannot plant acres without deciding to plant)
    #     x_i >= min_acres x y_i   (if you plant it at all, you plant a real block)
    # Without these the LP happily plants a third of an acre, which no farm does.
    if min_acreage:
        for i, s_ in enumerate(SUCCS):
            cn = CROP_NAMES[s_["crop"]]
            mn = float(CROPS[cn].get("min_acreage_if_planted", 0.0) or 0.0)
            e = np.zeros(N); e[i] = 1.0; e[y_i(i)] = -land
            add(e, -np.inf, 0.0)
            e = np.zeros(N); e[i] = 1.0; e[y_i(i)] = -mn
            add(e, 0.0, np.inf)

    A = np.vstack(rows)
    lb_v, ub_v = np.zeros(N), np.full(N, np.inf)
    integrality = np.zeros(N, dtype=int)
    if min_acreage:
        ub_v[n_s + n_off:] = 1.0
        integrality[n_s + n_off:] = 1
    if fixed_acres is not None:
        # Pin the acreage to compare ALLOCATION alone against the v3 fill rule — same plan,
        # same stock, only the choice of who gets served differs.
        for i, s_ in enumerate(SUCCS):
            lb_v[i] = ub_v[i] = float(fixed_acres)
    res = milp(c=c_obj, constraints=LinearConstraint(A, lo, hi), integrality=integrality,
               bounds=Bounds(lb_v, ub_v), options={"disp": False, "time_limit": 300})
    if not res.success:
        raise RuntimeError(f"LP did not solve: {res.message}")

    x = res.x
    acres = {SUCCS[i]["name"]: float(x[i]) for i in range(n_s)}
    offered = {(cn, hn): [float(x[off_i(p, w)]) for w in range(1, N_WEEKS + 1)]
               for p, (cn, hn) in enumerate(pairs)}
    sold = {k: sum(v) * defaults(*k)[0] for k, v in offered.items()}
    revenue = sum(sold[(cn, hn)] * CROPS[cn].get("channels", {}).get(hn, {}).get("price_per_lb", 0.0)
                  for cn, hn in pairs)
    cost = sum(acres[SUCCS[i]["name"]] *
               CROPS[CROP_NAMES[SUCCS[i]["crop"]]]["seed_transplant_cost_per_acre"]
               for i in range(n_s))
    planted = {k: v for k, v in acres.items() if v > 1e-6}
    return dict(profit=revenue - cost, revenue=revenue, cost=cost, acres=acres,
                offered=offered, sold=sold, status=res.status, planted=planted,
                n_planted=len(planted), n_offered=len(SUCCS))


if __name__ == "__main__":
    r = solve()
    print(f"OPTIMUM  profit ${r['profit']:,.0f}  (revenue ${r['revenue']:,.0f} "
          f"- growing cost ${r['cost']:,.0f})")
    print(f"   plants {r['n_planted']} of {r['n_offered']} successions the app offers")
    print("\nacres:")
    for k, v in sorted(r["planted"].items(), key=lambda kv: -kv[1]):
        print(f"   {k:<14} {v:7.2f}")
    print("\nsold, lb:")
    for (cn, hn), v in sorted(r["sold"].items(), key=lambda kv: -kv[1]):
        print(f"   {cn:<8} / {hn:<15} {v:10,.0f}")
