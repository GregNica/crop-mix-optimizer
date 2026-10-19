"""
toy_v11_lp.py — the v5 sheet's model, written as a MILP and solved with scipy.

Imported by BOTH `build_toy_v11.py` (so the READ ME can promise the optimum LibreOffice should
find) and `verify_toy_v11.py` (as the oracle the workbook is checked against).

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

v6 ADDS REAL COSTS AND THE CASH FLOOR, and the two are one job: a cash curve is meaningless
without costs to spend, and v5's profit was absurd precisely because seed was the only cost.

  TIMED variable costs   seed at the PLANTING week; fertiliser and fuel every week in the
                         ground, at the rate for that phase; packaging per lb in the week of
                         SALE. Timing is the point — a cash floor cannot be honest if costs
                         land in the wrong week.
  FIXED costs            cooler and barn depreciation, irrigation, machinery: charged every
                         week whether or not anything is planted.
  OVERHEAD               a share of revenue, internalised in the objective as the app does it.
  CASH FLOOR (C13)       cumulative cash must never fall below -(opening cash + credit line).

DEFERRED, and named so the omissions are not silent: labour (committed-cost machinery, v7),
water (the app prices on-farm water at $0 — backlog W10, not a toy simplification), and
interest on borrowing (post-solve in the app).

v9 REBUILDS THE LABOUR LAYER on the grower's three notes (DECISIONS.md GROUP F, rows L1-L3).
It is the first version where a labour change makes the model SMALLER.

  L1  THE PER-WEEK HIRE VARIABLE IS GONE. v8 let the solver buy hours in any week at a spot
      price, and the plan it produced was unexecutable: 21 non-zero weeks in blocks of
      2/2/2/3/12, and one week that bought TWO HOURS. No real hiring path works that way —
      H-2A wants 60-75 days of lead and carries a three-fourths guarantee, domestic seasonal
      wants 8-10 weeks (research: DECISIONS.md appendix, 2026-08-31). Every path is a
      COMMITTED BLOCK decided before the season, which is what an `employees[]` row already is.

      So v9 has ONE advisory variable — `crew_add`, an INTEGER headcount for a window the
      grower nominates — and it is CHARGED FOR THE WHOLE WINDOW whether the crops need the
      hours or not. That is the guarantee's economics and it is the same treatment W12 gives
      the standing crew. The answer reads "hire N people from week A to week B", which is a
      roster row the grower can type back in. 52 spot variables became 1.

  L2  THE OVERTIME CAP IS DERIVED, NOT TYPED. v8 (and the app) broadcast one scalar flat
      across 52 weeks while the crew is seasonal, so in 15 of 52 weeks the cap exceeded the
      whole crew's regular hours — and the app's solver took it, buying 191 overtime hours
      against 299 crew hours in one week. Here the input is an ALLOWANCE (1.25 = "I will let
      people work 125% of normal") and the cap is
          ot_cap[w] = (allowance - 1) x hourly_field_hours[w]
      over the standing hourly crew only. Salaried staff give capacity but cannot be paid
      overtime, so they are out of the cap for the same reason they are out of the rate.

      The advisory crew is deliberately NOT in the overtime base. Overtime is a policy about
      the people you already employ; letting the advice depend on overtime worked by the
      people the advice tells you to hire is the conflation L1 exists to remove.

  L3  THE LABOUR BLOCK BUILDS UP IN NAMED STEPS instead of recomputing a payroll mask inline.
      `labour_arrays()` now returns the intermediate the sheet needs — hourly field hours per
      week — which v8 computed, used once as a wage-blend denominator, and threw away.
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

# ⚠️ PIECE RATES ARE PER CROP, and the research says why: a piece-rate worker must still earn
# the minimum wage for hours worked, so the FLOOR in $/lb is set by how fast the crop picks —
# a 3.6x spread here. Entered the way a contract actually reads ($ per container) and converted
# with the crop's own volume figure, which is the same number the storage rows use.
BUSHEL_M3 = 1.2444 * 0.0283168        # USDA bushel = 1.2444 cu ft
PIECE_CONTAINER = {"Spinach": ("bushel", 3.00), "Kale": ("bushel", 1.00),
                   "Garlic": ("bushel", 2.00)}


# ⚠️ THE ONE DEFINITION of the piece-rate crew's weekly capacity. The builder writes THIS
# into the sheet's input cell, so the oracle and the workbook cannot carry different caps.
# They did, briefly, and a mutation proved nothing noticed: an LP capped in POUNDS hands
# the sheet a plan that is feasible against an HOURS cap and priced to the cent, so all 403
# checks passed on a plan that was simply worse. Section E proves worth and feasibility,
# never OPTIMALITY.
PIECE_MAX_HOURS_PER_WEEK = 200.0


def piece_rates_per_lb():
    """$/container -> $/lb, using each crop's own m3-per-lb. No new number is invented."""
    out = {}
    for cn, (_unit, per_container) in PIECE_CONTAINER.items():
        lb = BUSHEL_M3 / CROPS[cn]["crop_size_m3_per_lb"]
        out[cn] = per_container / lb
    return out

# v11: the hire toggles live on the ROLE. Only the two SEASONAL crews are marked hireable —
# you do not scale a farm manager to get a crop picked, and the equipment operators are a
# skilled year-round role. The cap is the grower's "how many more could I actually find",
# which the research says is the real uncertainty (>half of surveyed farms could not fill).
for _e in PAYLOAD.get("employees", []):
    if _e["type"] == "seasonal":
        _e.setdefault("can_hire_more", True)
        _e.setdefault("max_extra", 10)
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


STORABLE_WEEKS = 4          # below this, unsold product does not survive the trip home


def defaults(cn, hn):
    """Sell-through and returns-to-store for a crop-channel.

    ⚠️ STORABILITY IS SHELF LIFE, NOT THE STORAGE POOL. An earlier version used
    `not cold_storage` as the proxy and it is backwards for a whole class of crop: ambient
    means two opposite things. Garlic is ambient because it CURES AND KEEPS (16 weeks) —
    unsold product goes back in the barn. Basil is ambient because it is CHILLING-SENSITIVE
    (1 week) — the cooler would damage it, and it still does not survive to next Saturday.
    The proxy gave basil returns = 1.00, i.e. a free second chance at market it does not have.

    ⚠️ SELL-THROUGH DEFAULTS TO 1.00 EVERYWHERE, matching the app since 2026-08-30. The 85% it
    used to carry on stall channels had no citation, and this project does not ship numbers a
    stranger cannot check. It also meant the toy asserted a loss on channels where a purchase
    order exists and nothing goes unsold.

    The returns rule is kept because it decides what a LOWERED sell-through does — turn one down
    and a storable crop's unsold product comes home while a perishable's is destroyed. That is
    the distinction the grower's ruling turns on, and it must still be right when the mechanism
    is switched on.
    """
    contract = hn.lower().startswith("wholesale")
    shelf = int(CROPS[cn].get("shelf_life_weeks",
                              CROPS[cn].get("sales_spread_weeks", 1)) or 1)
    storable = shelf >= STORABLE_WEEKS
    return (1.00, 0.00 if contract else (1.00 if storable else 0.00))


def positions():
    """One entry per roster row, with its own weekly hours and its own weekly cost.

    ⚠️ v10, and it is the grower's design. v9 answered "how many hours this week" with a
    five-factor SUMPRODUCT mask — `(on this week) x (not salary) x (paid) x count x hours` —
    recomputed inside every row that needed it. Splitting BY POSITION makes each row a plain
    `IF(in window, count x hours x field%, 0)`, the aggregates become SUMs of named rows, and
    the blended wage becomes a ratio of rows already on the sheet. The mask disappears.

    It also gives the labour calendar for free: per-position weekly hours IS deliverable D9.

    The honest cost: this is O(number of roster rows) where the mask was O(1). Four positions
    is a clear win; a farm with twenty roles would want the aggregate form back.
    """
    load = 1.0 + PAYLOAD.get("payroll_load_pct", 0.0)
    out = []
    for e in PAYLOAD.get("employees", []):
        a, b = e.get("start_week", 1), e.get("end_week", N_WEEKS)
        salaried = e["type"] == "salary"
        # contracted hours are what the WAGE is paid for; field hours are what the CROPS get.
        # field% reduces capacity without reducing the wage — that asymmetry is the whole
        # reason both numbers have to exist.
        contract = e["count"] * e["hours_per_week"]
        field = contract * e.get("field_time_pct", 100) / 100.0
        per_wk = (e["wage"] / N_WEEKS * e["count"] * load if salaried
                  else e["wage"] * e["hours_per_week"] * e["count"] * load)
        f_h = np.zeros(N_WEEKS + 1); c_h = np.zeros(N_WEEKS + 1); cost = np.zeros(N_WEEKS + 1)
        heads = np.zeros(N_WEEKS + 1)
        for w in range(a, b + 1):
            f_h[w] = field; c_h[w] = contract; cost[w] = per_wk; heads[w] = e["count"]
        # v11: "can I hire more of this?" and "how many more could I get?" live on the ROLE.
        # Nothing else is entered — wage, hours, field% and window all come from the row, which
        # is why a different window or wage is a different ROW rather than another knob.
        out.append(dict(name=e["position"], type=e["type"], wage=float(e["wage"]),
                        salaried=salaried, paid=e["wage"] > 0,
                        hourly=(not salaried) and e["wage"] > 0,
                        can_hire_more=bool(e.get("can_hire_more", False)),
                        max_extra=(float(e.get("max_extra", 0.0))
                                   if e.get("can_hire_more", False) else 0.0),
                        field_h=f_h, contract_h=c_h, cost=cost, heads=heads,
                        start=a, end=b))
    return out


def labour_arrays():
    """(capacity h/wk, committed $/wk, HOURLY field h/wk, hourly headcount), 1-indexed to 52.

    Reproduces the app's own figures exactly — $4,884/wk winter, $24,484/wk at peak, $855,150
    for the year — which is the check that this crew model is the app's and not a paraphrase.

    ⚠️ L3: the third and fourth returns are new in v9 and they are the whole point of the row.
    `hourly_field` is the field hours contributed by HOURLY roles only. v8 computed exactly this
    quantity, used it once as the denominator of the wage blend, and returned it to nobody — so
    the overtime cap had nothing to derive itself from and became a typed constant, which is
    L2's defect. Publishing it here is most of L2's fix.
    """
    # ⚠️ SUMS OF THE POSITION ROWS, not a second walk over the roster. v9 derived these here
    # AND inside overtime_rate() AND on the sheet, three times from the same source — which is
    # how the sheet and the LP can drift while every test passes.
    pos = positions()
    z = lambda: np.zeros(N_WEEKS + 1)
    cap, wage, hourly_field, hourly_heads = z(), z(), z(), z()
    for p_ in pos:
        cap += p_["field_h"]
        wage += p_["cost"]
        # Salaried staff give capacity but cannot be paid overtime — out of the CAP for the
        # same reason they are out of the RATE. An unpaid role is out of both.
        if p_["hourly"]:
            hourly_field += p_["field_h"]
            hourly_heads += p_["heads"]
    return cap, wage, hourly_field, hourly_heads


def overtime_rate(overtime_multiplier=1.5):
    """$/hr for an overtime hour, per week.

    Priced from the crew's own HOURLY blend — salaried staff contribute capacity but you cannot
    pay them overtime, so they are excluded from the RATE while remaining in the capacity (the
    app's deliberate rate/quantity asymmetry).

    ⚠️ v9 DROPPED THE HIRE LEG. There is no spot price for a hired hour any more, because there
    is no spot hire: an advisory crew is paid its own roster wage for a whole committed window
    (L1). That also retires W15's hire-vs-overtime pricing question and W17's wage inference —
    a hired hand's wage is now typed on a roster row like every other wage, so there is nothing
    left to infer.
    """
    load = 1.0 + PAYLOAD.get("payroll_load_pct", 0.0)
    ot = np.zeros(N_WEEKS + 1)
    hourly = [p_ for p_ in positions() if p_["hourly"]]
    for w in range(1, N_WEEKS + 1):
        # ⚠️ WEIGHTED BY FIELD HOURS, matching `farm_v2/utils/labor.py`, which builds this blend
        # from `count x hrs x field%`. v9 here weighted by CONTRACTED hours instead — a real
        # divergence between the toy and the thing it checks, measured at **0.27%** on this
        # roster ($37.84 vs $37.74 in week 20) and zero in any week where one hourly role is
        # alone. It only grows if a large hourly group has low field time.
        #
        # Aligned to the app rather than left to differ, because a toy that quietly computes a
        # different number cannot be a check on anything. ⚠️ But contracted-weighting is
        # arguably the more defensible of the two — the wage is paid per contracted hour, and
        # field% reduces what the CROPS get, not what the payslip covers. Which one is right is
        # a real question and it is filed, not settled here.
        hrs = sum(p_["field_h"][w] for p_ in hourly)
        cost = sum(p_["field_h"][w] * p_["wage"] * load for p_ in hourly)
        ot[w] = (cost / hrs * overtime_multiplier) if hrs else 0.0
    return ot


def weekly_fixed_cost(cold_cap=None, amb_cap=None):
    """Flat $/week the farm owes whatever it plants."""
    p = PAYLOAD
    cold = p["harvest_storage_cap"] if cold_cap is None else cold_cap
    amb = p["ambient_storage_cap"] if amb_cap is None else amb_cap
    return (cold * p["rate_harvest_storage"] + amb * p["rate_ambient_storage"]
            + p["total_land"] * p["rate_irrigation"] + p["rate_machinery"]
            + p["equip_storage"] * p["rate_equip_storage"])


def solve(pack_out=1.00, shrink=None, land=None, cold_cap=None, amb_cap=None,
          fixed_acres=None, min_acreage=True, annual_override=None,
          opening_cash=None, credit_line=None, cash_floor=True,
          flex=True, overtime_multiplier=1.5, overtime_allowance=1.25,
          hire_more=True, hire_productivity_pct=70.0, hire_cost_per_head=800.0,
          piece=True, piece_committed=False, piece_start=1, piece_end=52,
          piece_max_hours_per_week=None, piece_rate_per_lb=None,
          piece_var_cost_per_lb=0.02, piece_fixed_cost=2_500.0,
          wage_floor_per_hr=16.07):
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
    POS = positions()
    n_roles = len(POS)
    # ⚠️ OVERTIME IS PER ROLE NOW, AND THAT IS WHAT MAKES THE MODEL LINEAR AGAIN.
    # v10 priced overtime at a BLENDED rate. Once the solver can also hire extra heads, the
    # blend depends on a decision variable, so `hours x blend(extra)` is variable x variable —
    # no longer an LP. Per role, the rate is that role's own wage x load x multiplier, which is
    # a CONSTANT because the wage is an input. cost = sum_r ot[r][w] x rate[r]: linear.
    # It is also a better model: with one blended rate an overtime hour costs the same whoever
    # works it, so the plan cannot prefer the cheap one or tell you who to ask to stay late.
    n_ot = n_roles * N_WEEKS if flex else 0
    n_extra = n_roles if hire_more else 0
    n_piece = len(CROP_NAMES) * N_WEEKS if piece else 0
    n_pbin = 1 if piece else 0
    N = n_s + n_off + n_y + n_ot + n_extra + n_piece + n_pbin
    off_i = lambda p, w: n_s + p * N_WEEKS + (w - 1)
    y_i = lambda i: n_s + n_off + i
    _ot0 = n_s + n_off + n_y
    ot_i = lambda r, w: _ot0 + r * N_WEEKS + (w - 1)
    _ex0 = _ot0 + n_ot
    extra_i = lambda r: _ex0 + r
    _pc0 = _ex0 + n_extra
    piece_i = lambda c, w: _pc0 + c * N_WEEKS + (w - 1)
    pbin_i = _pc0 + n_piece          # 1 if the piece-rate crew is engaged at all

    # The nominated window. Everything about the advisory crew is derived from it, so the
    # window is stated ONCE and never re-derived — v8's labour bugs were all a quantity
    # recomputed in a second place.
    load = 1.0 + PAYLOAD.get("payroll_load_pct", 0.0)
    # Per-role overtime rate: a CONSTANT, because the wage is an input.
    ot_rate_role = [p_["wage"] * load * overtime_multiplier if p_["hourly"] else 0.0
                    for p_ in POS]
    # Per-role cost of ONE extra head, per week, over that role's own window. Extra heads
    # inherit the role's wage, hours, field% AND window — nothing new is entered anywhere,
    # which is the whole point: a different window or wage is a different ROW, not a knob.
    ex_head_cost = []
    ex_head_field = []
    for p_ in POS:
        on = [w for w in range(1, N_WEEKS + 1) if p_["field_h"][w] > 0]
        heads = p_["heads"][on[0]] if on else 0.0
        ex_head_cost.append((p_["cost"][on[0]] / heads) if on and heads else 0.0)
        # x productivity: a new hand is not as fast as the crew already doing the job.
        ex_head_field.append(((p_["field_h"][on[0]] / heads) if on and heads else 0.0)
                             * max(0.0, hire_productivity_pct) / 100.0)
    ex_on = [[1.0 if p_["field_h"][w] > 0 else 0.0 for w in range(N_WEEKS + 1)] for p_ in POS]

    # ---- PIECE RATE -----------------------------------------------------------------
    # Pounds a harvest hour moves, per crop — derived from the crop's own harvest labour and
    # yield, so no new input. It is what converts pounds picked into HOURS RELIEVED.
    lb_per_harvest_hr = {}
    for cn in CROP_NAMES:
        lh = CROPS[cn].get("labor_harv", 0.0) or 0.0
        lb_per_harvest_hr[cn] = (CROPS[cn]["yield_per_acre"] / lh) if lh else 0.0
    # ⚠️ THE MINIMUM-WAGE FLOOR, AND IT COLLAPSES TO A CONSTANT. A piece-rate worker must still
    # earn at least the floor for the hours worked; if the rate falls short the employer makes
    # up the difference (FLSA; the AEWR under H-2A). Cost per lb is therefore
    #     max(rate, floor / lb-per-harvest-hour)
    # and BOTH terms are linear in pounds, so the max resolves per crop at build time — no
    # binary, no piecewise anything. A rate entered below its floor is simply inoperative.
    # It is also why real rates differ by crop: the floor per lb differs by picking speed, and
    # on this farm that is a 3.6x spread (spinach $0.161/lb vs kale $0.044/lb at $16.07).
    piece_rate_per_lb = piece_rate_per_lb or piece_rates_per_lb()
    if piece_max_hours_per_week is None:
        piece_max_hours_per_week = PIECE_MAX_HOURS_PER_WEEK
    piece_eff = {}
    piece_floor = {}
    for cn in CROP_NAMES:
        lbph = lb_per_harvest_hr[cn]
        floor = (wage_floor_per_hr / lbph) if lbph else 0.0
        piece_floor[cn] = floor
        piece_eff[cn] = max(float(piece_rate_per_lb.get(cn, 0.0)), floor) + piece_var_cost_per_lb
    piece_weeks = [w for w in range(int(piece_start), int(piece_end) + 1)
                   if 1 <= w <= N_WEEKS]

    # lb packed out per acre of succession i, in week w
    packed_per_acre = np.zeros((n_s, N_WEEKS + 1))
    for i, s in enumerate(SUCCS):
        cn = CROP_NAMES[s["crop"]]
        hw = harvest_weeks_of(s, N_WEEKS)
        for w in hw:
            packed_per_acre[i, w] += CROPS[cn]["yield_per_acre"] / max(1, len(hw)) * pack_out

    # ---- per-acre cost of a succession, WEEK BY WEEK (this is what cash timing needs) ----
    # seed at the planting week; fertiliser and fuel every week in the ground at that phase's
    # rate. Water is deliberately absent: the app prices on-farm water at $0 (backlog W10), and
    # inventing a price here would make the toy disagree with the thing it is checking.
    fert_rate, fuel_rate = PAYLOAD["cost_fert_per_lb"], PAYLOAD["cost_fuel_per_L"]
    var_week = np.zeros((n_s, N_WEEKS + 1))
    for i, s_ in enumerate(SUCCS):
        c = CROPS[CROP_NAMES[s_["crop"]]]
        first = s_["weeks"][0]
        if 1 <= ((first - 1) % N_WEEKS) + 1 <= N_WEEKS:
            var_week[i, ((first - 1) % N_WEEKS) + 1] += c["seed_transplant_cost_per_acre"]
        key = ["plant", "grow", "harv"]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            w = ((wk - 1) % N_WEEKS) + 1
            var_week[i, w] += c.get(f"fert_{key[ph]}", 0.0) * fert_rate
            var_week[i, w] += c.get(f"fuel_{key[ph]}", 0.0) * fuel_rate

    overhead = PAYLOAD["overhead_pct_of_revenue"]

    # Crop labour hours per acre, week by week — the C2 left-hand side.
    lab_week = np.zeros((n_s, N_WEEKS + 1))
    for i, s_ in enumerate(SUCCS):
        c = CROPS[CROP_NAMES[s_["crop"]]]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            lab_week[i, ((wk - 1) % N_WEEKS) + 1] += c.get(
                f"labor_{['plant', 'grow', 'harv'][ph]}", 0.0)
    # Harvest-phase hours only — what a piece-rate crew can actually relieve. C2 pools all
    # three phases, and relieving the pool would let pickers do the planting.
    harv_week = np.zeros((n_s, N_WEEKS + 1))
    for i, s_ in enumerate(SUCCS):
        c = CROPS[CROP_NAMES[s_["crop"]]]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            if ph == 2:
                harv_week[i, ((wk - 1) % N_WEEKS) + 1] += c.get("labor_harv", 0.0)

    lab_cap, wage_wk, hourly_field, hourly_heads = labour_arrays()
    ot_rate = overtime_rate(overtime_multiplier)
    # The app's own refusal: a bought hour with no price is a free hour. Now checked PER ROLE,
    # where it belongs — a blend could hide one unpaid role behind three paid ones.
    if flex:
        for r_, p_ in enumerate(POS):
            if p_["hourly"] and not ot_rate_role[r_] > 0:
                raise RuntimeError(
                    f"{p_['name']} can work overtime priced at $0/hr — refusing to hand out "
                    f"free labour (the app refuses this too)")
    if hire_more:
        for r_, c_ in enumerate(ex_head_cost):
            if any(ex_on[r_][1:]) and not c_ > 0:
                raise RuntimeError(
                    f"an extra head on {POS[r_]['name']} costs $0 — free labour, refused")

    # objective: -(revenue - cost) because milp minimises
    c_obj = np.zeros(N)
    for i, s_ in enumerate(SUCCS):
        c_obj[i] += var_week[i, 1:].sum()
    for p, (cn, hn) in enumerate(pairs):
        st, _ = defaults(cn, hn)
        spec = CROPS[cn].get("channels", {}).get(hn, {})
        price = spec.get("price_per_lb", 0.0)
        pkg = spec.get("packaging_cost_per_lb", 0.0)
        # per lb OFFERED: st of it sells at price, all of it carries packaging, and overhead is
        # a share of revenue — the same net-of-everything price the app puts in its objective.
        net = st * price * (1.0 - overhead) - st * pkg
        for w in range(1, N_WEEKS + 1):
            c_obj[off_i(p, w)] -= net

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
        if annual_override and (cn, hn) in annual_override:
            ctype, cval = "Annual", float(annual_override[(cn, hn)])
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

    # C2 — crop hours in a week cannot exceed what the crew can give. Wages do NOT appear
    # here: they are already owed. That is the W12 point — the marginal crop hour is free and
    # is rationed by this row instead of priced in the objective.
    for w in range(1, N_WEEKS + 1):
        e = np.zeros(N)
        for i in range(n_s):
            if lab_week[i, w]:
                e[i] = lab_week[i, w]
        if flex:
            for r_ in range(n_roles):
                if POS[r_]["hourly"]:
                    e[ot_i(r_, w)] = -1.0
        if hire_more:
            # Extra heads are committed for their ROLE'S window — they give hours in every
            # week of it, used or not, exactly like the crew already on that row.
            for r_ in range(n_roles):
                if ex_on[r_][w]:
                    e[extra_i(r_)] = -ex_head_field[r_]
        if piece:
            # ⚠️ POUNDS PICKED BY THE PIECE-RATE CREW RELIEVE HARVEST HOURS. Without this the
            # farm pays committed wages for hours it no longer needs AND a rate per pound for
            # the same picking — the hours are the thing that moves, not the wages, which are
            # owed either way.
            for c_, cn in enumerate(CROP_NAMES):
                if lb_per_harvest_hr[cn] and w in piece_weeks:
                    e[piece_i(c_, w)] = -1.0 / lb_per_harvest_hr[cn]
        add(e, -np.inf, lab_cap[w])

    # Overtime is bounded PER ROLE by that role's own crew, extra heads included. Linear:
    #     ot[r][w] <= (allowance-1) x (count + extra) x hours x field%
    # rearranges to  ot[r][w] - k.extra[r] <= k.count[r].
    if flex:
        k = max(0.0, overtime_allowance - 1.0)
        for r_, p_ in enumerate(POS):
            if not p_["hourly"]:
                continue
            for w in range(1, N_WEEKS + 1):
                e = np.zeros(N)
                e[ot_i(r_, w)] = 1.0
                if hire_more and ex_on[r_][w]:
                    e[extra_i(r_)] = -k * ex_head_field[r_]
                add(e, -np.inf, k * p_["field_h"][w])

    if flex:
        for r_ in range(n_roles):
            if POS[r_]["hourly"]:
                for w in range(1, N_WEEKS + 1):
                    c_obj[ot_i(r_, w)] += ot_rate_role[r_]
    if hire_more:
        for r_ in range(n_roles):
            c_obj[extra_i(r_)] += (ex_head_cost[r_] * sum(ex_on[r_][1:])
                                   + max(0.0, hire_cost_per_head))
    if piece:
        # Piece-rate cost is a COGS line: rate (floored at minimum wage) plus the variable
        # cost, on every pound picked. The fixed cost is charged once — always if the crew is
        # pre-committed, otherwise only if the solver engages them at all.
        for c_, cn in enumerate(CROP_NAMES):
            for w in piece_weeks:
                c_obj[piece_i(c_, w)] += piece_eff[cn]
        c_obj[pbin_i] += max(0.0, piece_fixed_cost)

    if piece:
        crop_succs = {cn: [i for i, s_ in enumerate(SUCCS)
                           if CROP_NAMES[s_["crop"]] == cn] for cn in CROP_NAMES}
        for w in range(1, N_WEEKS + 1):
            for c_, cn in enumerate(CROP_NAMES):
                if w not in piece_weeks:
                    e = np.zeros(N); e[piece_i(c_, w)] = 1.0
                    add(e, -np.inf, 0.0)                 # outside their window: nothing
                    continue
                # (a) they cannot pick what was not harvested that week
                e = np.zeros(N)
                e[piece_i(c_, w)] = 1.0
                for i in crop_succs[cn]:
                    e[i] -= packed_per_acre[i, w]
                add(e, -np.inf, 0.0)
            # (b) the crew's weekly capacity, and the on/off link to the fixed cost.
            # ⚠️ MEASURED IN HOURS, NOT POUNDS. A pound cap describes a crew whose size moves
            # with the crop (20,000 lb = 200 h of spinach, 55 h of kale) and it distorts the
            # mix: it rewards hours-per-pound, favouring spinach over the cheaper garlic
            # relief. Hours is what a crew actually has.
            e = np.zeros(N)
            for c_, cn in enumerate(CROP_NAMES):
                if lb_per_harvest_hr[cn]:
                    e[piece_i(c_, w)] = 1.0 / lb_per_harvest_hr[cn]
            e[pbin_i] = -float(piece_max_hours_per_week)
            add(e, -np.inf, 0.0)
            # (c) ⚠️ relief cannot exceed the HARVEST hours actually needed that week. Without
            # it the crew relieves planting and growing hours it never touches — free labour
            # wearing a piece rate.
            e = np.zeros(N)
            for c_, cn in enumerate(CROP_NAMES):
                if lb_per_harvest_hr[cn]:
                    e[piece_i(c_, w)] = 1.0 / lb_per_harvest_hr[cn]
            for i in range(n_s):
                if harv_week[i, w]:
                    e[i] -= harv_week[i, w]
            add(e, -np.inf, 0.0)
        if piece_committed:
            # Pre-committed: you signed, so the fixed cost is sunk whether or not it is used.
            e = np.zeros(N); e[pbin_i] = 1.0
            add(e, 1.0, 1.0)

    # C13 — the weekly cash floor. Cumulative cash from week 1 to W must never fall below
    # -(opening cash + credit line). Revenue lands in the week of sale, variable costs in the
    # week they are incurred, fixed costs every week.
    fixed_wk = weekly_fixed_cost(cold_cap, amb_cap)
    op_cash = PAYLOAD.get("opening_cash", 50_000.0) if opening_cash is None else opening_cash
    cred = PAYLOAD.get("credit_line", 250_000.0) if credit_line is None else credit_line
    if cash_floor:
        for W in range(1, N_WEEKS + 1):
            e = np.zeros(N)
            for i in range(n_s):
                e[i] -= var_week[i, 1:W + 1].sum()
            for p, (cn, hn) in enumerate(pairs):
                st, _ = defaults(cn, hn)
                spec = CROPS[cn].get("channels", {}).get(hn, {})
                net = (st * spec.get("price_per_lb", 0.0) * (1.0 - overhead)
                       - st * spec.get("packaging_cost_per_lb", 0.0))
                for w in range(1, W + 1):
                    e[off_i(p, w)] += net
            if flex:
                for r_ in range(n_roles):
                    if POS[r_]["hourly"]:
                        for w in range(1, W + 1):
                            e[ot_i(r_, w)] -= ot_rate_role[r_]
            if hire_more:
                for r_ in range(n_roles):
                    e[extra_i(r_)] -= ex_head_cost[r_] * sum(ex_on[r_][1:W + 1])
                    if any(ex_on[r_][1:W + 1]):
                        e[extra_i(r_)] -= max(0.0, hire_cost_per_head)
            if piece:
                for c_, cn in enumerate(CROP_NAMES):
                    for w in range(1, W + 1):
                        if w in piece_weeks:
                            e[piece_i(c_, w)] -= piece_eff[cn]
                if piece_weeks and W >= piece_weeks[0]:
                    e[pbin_i] -= max(0.0, piece_fixed_cost)
            add(e, -(op_cash + cred) + W * fixed_wk + wage_wk[1:W + 1].sum(), np.inf)

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
    # ⚠️ NO per-week ub for overtime any more — its cap is the constraint block above, because
    # a bound can only hold a constant and the honest cap is a weekly quantity.
    integrality = np.zeros(N, dtype=int)
    if hire_more:
        # INTEGER heads, because the output is a roster edit a grower types in — "change
        # Harvest Crew from 8 to 11". "Hire 7.3 people" is not an instruction. The cap is that
        # role's own "max more"; a role with the toggle off is pinned at zero.
        for r_, p_ in enumerate(POS):
            ub_v[extra_i(r_)] = float(p_.get("max_extra", 0.0))
            integrality[extra_i(r_)] = 1
    if piece:
        ub_v[pbin_i] = 1.0
        integrality[pbin_i] = 1
    if min_acreage:
        ub_v[n_s + n_off:n_s + n_off + n_y] = 1.0
        integrality[n_s + n_off:n_s + n_off + n_y] = 1
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
    growing = sum(x[i] * var_week[i, 1:].sum() for i in range(n_s))
    packaging = sum(sold[(cn, hn)] * CROPS[cn].get("channels", {}).get(hn, {})
                    .get("packaging_cost_per_lb", 0.0) for cn, hn in pairs)
    fixed = fixed_wk * N_WEEKS
    wages = float(wage_wk[1:].sum())

    # Interest, POST-SOLVE and off the realised cash curve — exactly how the app does it
    # (solver.py: interest_cost = interest_rate_apr x mean(borrowed_weekly)). It is NOT in the
    # objective: the plan is chosen first and the borrowing it implies is priced afterwards.
    # That is a real simplification — the optimizer has no incentive to shift sales earlier to
    # borrow less — and it is the app's, so the toy inherits it rather than diverging.
    week_net = np.zeros(N_WEEKS + 1)
    for w in range(1, N_WEEKS + 1):
        rev_w = sum(x[off_i(p_, w)] * defaults(cn, hn)[0]
                    * CROPS[cn].get("channels", {}).get(hn, {}).get("price_per_lb", 0.0)
                    for p_, (cn, hn) in enumerate(pairs))
        pkg_w = sum(x[off_i(p_, w)] * defaults(cn, hn)[0]
                    * CROPS[cn].get("channels", {}).get(hn, {}).get("packaging_cost_per_lb", 0.0)
                    for p_, (cn, hn) in enumerate(pairs))
        grow_w = sum(x[i] * var_week[i, w] for i in range(n_s))
        flex_w = sum(x[ot_i(r_, w)] * ot_rate_role[r_]
                     for r_ in range(n_roles) if POS[r_]["hourly"]) if flex else 0.0
        if hire_more:
            flex_w += sum(x[extra_i(r_)] * ex_head_cost[r_]
                          for r_ in range(n_roles) if ex_on[r_][w])
            for r_ in range(n_roles):
                on = [ww for ww in range(1, N_WEEKS + 1) if ex_on[r_][ww]]
                if on and w == on[0]:
                    flex_w += x[extra_i(r_)] * max(0.0, hire_cost_per_head)
        if piece:
            flex_w += sum(x[piece_i(c_, w)] * piece_eff[cn]
                          for c_, cn in enumerate(CROP_NAMES)) if w in piece_weeks else 0.0
            if piece_weeks and w == piece_weeks[0]:
                flex_w += x[pbin_i] * max(0.0, piece_fixed_cost)
        week_net[w] = (rev_w - pkg_w - grow_w - fixed_wk - wage_wk[w] - overhead * rev_w
                       - flex_w)
    bank = np.cumsum(week_net[1:]) + op_cash
    borrowed = np.maximum(0.0, -bank)
    interest = PAYLOAD.get("interest_rate_apr", 0.0) * float(borrowed.mean())
    peak_borrow = float(borrowed.max())
    ovh = overhead * revenue
    ot_by_role = [[float(x[ot_i(r_, w)]) if (flex and POS[r_]["hourly"]) else 0.0
                   for w in range(1, N_WEEKS + 1)] for r_ in range(n_roles)]
    ot_hours = [sum(ot_by_role[r_][w] for r_ in range(n_roles)) for w in range(N_WEEKS)]
    ot_cost = sum(sum(ot_by_role[r_]) * ot_rate_role[r_] for r_ in range(n_roles))
    extra_heads = [float(x[extra_i(r_)]) if hire_more else 0.0 for r_ in range(n_roles)]
    hire_cost = sum(extra_heads[r_] * (ex_head_cost[r_] * sum(ex_on[r_][1:])
                                       + max(0.0, hire_cost_per_head))
                    for r_ in range(n_roles))
    piece_lb = {cn: [float(x[piece_i(c_, w)]) if piece else 0.0
                     for w in range(1, N_WEEKS + 1)]
                for c_, cn in enumerate(CROP_NAMES)}
    piece_used = bool(piece and x[pbin_i] > 0.5)
    piece_cost = (sum(sum(v) * piece_eff[cn] for cn, v in piece_lb.items())
                  + (max(0.0, piece_fixed_cost) if piece_used else 0.0))
    piece_hours_relieved = [sum(piece_lb[cn][w] / lb_per_harvest_hr[cn]
                                for cn in CROP_NAMES if lb_per_harvest_hr[cn])
                            for w in range(N_WEEKS)]
    cost = (growing + packaging + fixed + ovh + wages + interest
            + ot_cost + hire_cost + piece_cost)

    # ⚠️ THE OBJECTIVE MUST RECONCILE AGAINST THE COST BREAKDOWN, and this check exists because
    # a mutation walked straight through everything else. Charging the advisory crew for ONE
    # week in `c_obj` while the report charges the whole window leaves the solver optimising a
    # problem nobody ever sees: it picks a too-large crew, the reported cost prices that crew
    # correctly, the SHEET prices it correctly too — so the sheet-vs-LP comparison agrees to the
    # cent and the defect is invisible. Both sides right about a plan chosen on wrong prices.
    #
    # `res.fun` is the minimised value, so -res.fun is what the objective actually maximised.
    # Wages and fixed costs are constants (committed, not decided) and interest is post-solve,
    # so none of them appear in it.
    obj_from_parts = (revenue - growing - packaging - ovh
                      - ot_cost - hire_cost - piece_cost)
    if abs(-float(res.fun) - obj_from_parts) > max(1.0, abs(obj_from_parts) * 1e-9):
        raise RuntimeError(
            f"the objective and the cost breakdown disagree: solver maximised "
            f"{-float(res.fun):,.2f} but the parts sum to {obj_from_parts:,.2f}. Some cost is "
            f"priced one way in c_obj and another way in the report, so the plan was chosen on "
            f"prices nothing else on this sheet uses.")
    planted = {k: v for k, v in acres.items() if v > 1e-6}
    return dict(profit=revenue - cost, obj_value=-float(res.fun),
                obj_from_parts=obj_from_parts, revenue=revenue, cost=cost, acres=acres,
                growing=growing, packaging=packaging, fixed=fixed, overhead=ovh,
                wages=wages, lab_cap=lab_cap, wage_wk=wage_wk, lab_week=lab_week,
                interest=interest, peak_borrow=peak_borrow, bank=list(bank),
                ot_cost=ot_cost, ot_hours=ot_hours, ot_by_role=ot_by_role,
                ot_rate_role=ot_rate_role, hourly_field=list(hourly_field),
                hourly_heads=list(hourly_heads),
                extra_heads=extra_heads, hire_cost=hire_cost,
                ex_head_cost=ex_head_cost, ex_head_field=ex_head_field,
                role_names=[p_["name"] for p_ in POS],
                piece_lb=piece_lb, piece_cost=piece_cost, piece_used=piece_used,
                piece_eff=piece_eff, piece_floor=piece_floor, piece_weeks=piece_weeks,
                lb_per_harvest_hr=lb_per_harvest_hr,
                piece_hours_relieved=piece_hours_relieved, harv_week=harv_week,
                positions=[dict(name=q["name"], hourly=q["hourly"], wage=q["wage"],
                                field_h=list(q["field_h"]), contract_h=list(q["contract_h"]),
                                cost=list(q["cost"]), heads=list(q["heads"]))
                           for q in positions()],
                fixed_weekly=fixed_wk, opening_cash=op_cash, credit_line=cred,
                var_week=var_week,
                offered=offered, sold=sold, status=res.status, planted=planted,
                n_planted=len(planted), n_offered=len(SUCCS))


if __name__ == "__main__":
    r = solve()
    print(f"OPTIMUM  profit ${r['profit']:,.0f}")
    print(f"   revenue    {r['revenue']:>12,.0f}")
    for k in ("growing", "packaging", "fixed", "overhead", "wages", "interest",
              "ot_cost", "hire_cost", "piece_cost"):
        print(f"   {k:<10} {-r[k]:>12,.0f}")
    print(f"   plants {r['n_planted']} of {r['n_offered']} successions the app offers")
    print("\nacres:")
    for k, v in sorted(r["planted"].items(), key=lambda kv: -kv[1]):
        print(f"   {k:<14} {v:7.2f}")
    print("\nsold, lb:")
    for (cn, hn), v in sorted(r["sold"].items(), key=lambda kv: -kv[1]):
        print(f"   {cn:<8} / {hn:<15} {v:10,.0f}")
