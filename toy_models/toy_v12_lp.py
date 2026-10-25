"""
toy_v12_lp.py — the v5 sheet's model, written as a MILP and solved with scipy.

Imported by BOTH `build_toy_v12.py` (so the READ ME can promise the optimum LibreOffice should
find) and `verify_toy_v12.py` (as the oracle the workbook is checked against).

v12 ADDS THE FIXED LAYER (PLAN Batch FX.0, DECISIONS GROUP G) — the things a grower has already
decided, owes, or physically has, which constrain the plan BEFORE the optimiser fills the rest:

  ZONES (FX.4)       named land pools with a crop x zone eligibility table. A succession is
                     now a (planting week, ZONE) pair, and land is one row per zone per week.
  VARIANTS (FX.5)    a zone-specific crop is a separate NAME ("Tunnel Spinach") with its own
                     windows, and a `sells_as` identity. ⚠️ Demand caps and contract floors are
                     keyed by the IDENTITY, not the name — otherwise two variants each get the
                     whole market (measured below: `share_caps=False`).
  PERENNIAL (FX.2)   committed ground standing all 52 weeks: one PINNED pseudo-succession per
                     planting BLOCK, never through the calendar generator (which refuses cycles
                     > 52 wk). A block carries THIS year's cost; a mature block's establishment
                     is SUNK (grower ruling 2026-10-25), and an ESTABLISHING block has no harvest.
  MUST-PLANT (FX.1)  UNCONDITIONAL floors, in the two forms the plan said to decide here:
                       standing   acres in the ground in EVERY week of a window
                       annual     acres planted, summed over the year's plantings
  CARRY-IN (C15)     an overwintering crop already in the ground is PINNED: acres standing in
                     week 1 == what was planted last fall. The year is cyclic, so the same row
                     also reserves THIS fall's replant — and with no carry-in the crop cannot
                     be planted at all (no decisions about next year; grower ruling 2026-10-25).
  CONTRACTS (FX.3)   sold >= floor per identity x channel x week, in one of two MODES the grower
                     must choose: 'penalty' (a SHORTFALL slack priced per lb short) or 'deliver'
                     (hard — no slack; an unmeetable one is refused, naming its weeks).

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
from typing import NamedTuple

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from farm_v2.utils.calendar import generate_successions, harvest_weeks_of
from farm_v2.utils.demand import build_demand_table, build_annual_caps

BASE_CROPS = ["Spinach", "Kale", "Garlic"]          # straight from the golden payload
VARIANT = "Tunnel Spinach"                           # FX.5 — a zone-specific NAME
PERENNIAL = "Asparagus"                              # FX.2 — committed ground, all year
ANNUALS = BASE_CROPS + [VARIANT]                     # everything the calendar generates
CROP_NAMES = ANNUALS + [PERENNIAL]
# v5 offers EVERY legal start week, exactly as generate_successions does for the app.
PICKED = None
N_WEEKS = 52

# ---- FX.4 ZONES ------------------------------------------------------------------------
# Named pools, no geometry. Open field is whatever the tunnel does not take, so the farm's
# total land is unchanged and the golden figure still means what it meant.
TUNNEL_ACRES = 2.0
# (name, acres, the code a planting's name carries when its crop may use more than one zone).
# acres None = THE REMAINDER: whatever 'Land you have' leaves after the others. Stated as data so
# the oracle and the sheet derive it the same way — once both did it by testing a zone's NAME.
ZONES = [("Open field", None, "F"), ("High tunnel", TUNNEL_ACRES, "T")]
ZONE_NAMES = [z for z, _, _ in ZONES]
ZONE_CODE = {z: code for z, _, code in ZONES}
# Eligibility. Kale is deliberately allowed in BOTH zones — the one crop that exercises a
# succession being split across pools; everything else lives in exactly one.
ELIGIBLE = {"Spinach": ["Open field"], "Kale": ["Open field", "High tunnel"],
            "Garlic": ["Open field"], VARIANT: ["High tunnel"], PERENNIAL: ["Open field"]}

# ---- FX.2 THE PERENNIAL -----------------------------------------------------------------
# ⚠️ TOY PLACEHOLDER DATA, sourced where a source was found and LABELLED where not. Templates
# proper are FX.6 under Batch 3's data discipline; the toy needs a shape, not a library entry.
#   mature yield 1,750 lb/ac         Univ. Kentucky asparagus budget (2016) base case
#   upkeep $1,296/ac/yr              UKY 2016, full-harvest-year total cost
#   wholesale $1.75/lb               UKY 2016
#   establishing-year $2,000/ac      ⚠️ UNSOURCED SHARE: MSU Ext. E3315 (2016) puts establishment
#                                    at $4,082/ac over years 0-2 and does not split it by year
#   UNSOURCED: harvest weeks 18-25, the FM price and caps, the per-acre labour, the pack
#   volume and shelf life — round figures in the right order, to be replaced in FX.6.
# ONE ENTRY PER PLANTING BLOCK (grower ruling 2026-10-25): blocks of one crop differ by age, so
# each carries its own acres and THIS year's cost. A mature block's establishment is SUNK, like
# the tunnel's structure. A block still establishing has NO harvest this year; it is committed
# ground with costs and labour, and next year the grower types its first yield. No yield ramp.
PERENNIAL_SPEC = dict(harvest_weeks=list(range(18, 26)), labour_grow=0.5, labour_harv=5.5)
PERENNIAL_BLOCKS = [
    dict(name=PERENNIAL, acres=3.0, cost_per_acre_yr=1_296.0, bearing=True),
    dict(name=f"{PERENNIAL} (new)", acres=1.0, cost_per_acre_yr=2_000.0, bearing=False),
]

# ---- C15 CARRY-IN ----------------------------------------------------------------------
#   identity -> acres planted LAST FALL and standing on 1 January. PINNED (floor = ceiling), for
#   every crop flagged `overwinters`; an overwintering crop not listed is pinned at 0.
# ⚠️ Pinned, not floored (grower ruling 2026-10-25), so it can bind in BOTH directions: left
# free, garlic plants 17.76 ac (measured), so 18.3 pushes it UP — and a carry-in of 17 holds it
# DOWN, which a floor never could. verify_toy_v12 prices both.
CARRY_IN = {"Garlic": 18.3}

# ---- FX.1 MUST-PLANT -------------------------------------------------------------------
# Every floor below BINDS at the unfloored v12 optimum, on purpose — measured, each one moves
# the objective: a floor the optimum already clears is a guard that cannot fail (the L4 /
# "defaulted off" trap in its quieter form). Unfloored (garlic unpinned): kale 4.4 ac standing
# in weeks 10-20 and 35.0 ac planted. Costs, each added on top of the previous (measured
# 2026-10-25): kale standing $4,787, kale annual $2,488, then the garlic pin $3,518.
#
# ⚠️ GARLIC'S CEILING IS ~18.5 AC (18.5 solves, 18.6 is refused — measured 2026-10-25), and
# it is set by TWO rows at once: the winter crew's 108 h
# in the planting weeks (6.7 h/ac) and the 150 m3 barn at harvest. Relaxing either alone left
# it infeasible — so "check the land" is not what an infeasible carry-in should tell anyone.
#   (identity, acres, first week, last week)  — acres standing in EVERY week of the window
MUST_STAND = [("Kale", 8.0, 10, 20)]         # "keep kale in the ground for the CSA, spring"
#   identity -> acres planted, summed across the year (legitimate for a succession crop)
MUST_ANNUAL = {"Kale": 45.0}

# ---- FX.3 CONTRACTS --------------------------------------------------------------------
#   (identity, channel, lb per week, first week, last week, mode, penalty $ per lb short)
# MODE IS REQUIRED (grower ruling 2026-10-25): with a blank penalty a contract would mean
# nothing — the plan just sells those pounds where they pay best. 'penalty' needs an amount;
# 'deliver' takes None and has no shortfall at all.
CONTRACT_MODES = ("penalty", "deliver")


class Contract(NamedTuple):
    """One contract, by NAME — it was a positional tuple, and adding `mode` shifted every index
    and slice in four files. Plain 7-tuples are still accepted by `solve()` and wrapped there."""
    gid: str
    channel: str
    lb: float
    first: int
    last: int
    mode: str
    pen: float | None


# Kale's and spinach's are 'penalty' and PARTLY UNMEETABLE — kale has no harvest in weeks 36-37,
# spinach's weeks 35-36 sit in the summer gap — so neither could be 'deliver' (measured: both are
# refused, naming those weeks). Asparagus is 'deliver' and meetable: 500 lb/wk of a 3-acre block
# pulls pounds off the dearer farmers market, so it BINDS (costs ~$2,000), and 700 is refused.
CONTRACTS = [Contract("Kale", "Wholesale", 1_500.0, 20, 40, "penalty", 0.50),
             Contract("Spinach", "Wholesale", 2_000.0, 28, 36, "penalty", 0.50),
             Contract(PERENNIAL, "Wholesale", 500.0, 18, 25, "deliver", None)]
DELIVER_K = [k for k, c in enumerate(CONTRACTS) if c.mode == "deliver"]
PENALTY_K = [k for k, c in enumerate(CONTRACTS) if c.mode == "penalty"]


def load():
    payload = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
    crops = {c["name"]: c for c in payload["crops"] if c["name"] in BASE_CROPS}
    # The variant: the SAME crop data with a longer planting window (a tunnel's job is season
    # extension) and a tunnel-sized minimum block. Nothing else is invented.
    v = json.loads(json.dumps(crops["Spinach"]))
    v.update(name=VARIANT, sells_as="Spinach", min_acreage_if_planted=0.25,
             seasons=[{"start": "01-02", "end": "06-30"}, {"start": "08-01", "end": "12-15"}])
    crops[VARIANT] = v
    ps = PERENNIAL_SPEC
    crops[PERENNIAL] = dict(
        name=PERENNIAL, perennial=True, yield_per_acre=1_750.0, cold_storage=True,
        crop_size_m3_per_lb=0.0012, shelf_life_weeks=2, min_acreage_if_planted=0.0,
        labor_plant=0.0, labor_grow=ps["labour_grow"], labor_harv=ps["labour_harv"],
        seed_transplant_cost_per_acre=0.0,
        channels={"Wholesale": {"price_per_lb": 1.75, "packaging_cost_per_lb": 0.15,
                                "demand_cap_type": "weekly_flat", "weekly_demand_lbs": 1_500},
                  "Farmers Market": {"price_per_lb": 4.00, "packaging_cost_per_lb": 0.30,
                                     "demand_cap_type": "weekly_varying",
                                     "demand_ranges": [{"weeks": "W18-W25",
                                                        "weekly_lbs": 300}]}})
    ch_order = sorted(payload["channels"], key=lambda ch: -max(
        crops[c].get("channels", {}).get(ch["name"], {}).get("price_per_lb", 0)
        for c in BASE_CROPS))
    annual = [crops[n] for n in ANNUALS]
    succs = []
    for s in generate_successions(annual, 2024):
        cn = ANNUALS[s["crop"]]
        for z in ELIGIBLE[cn]:
            succs.append(dict(s, zone=z, name=s["name"] if len(ELIGIBLE[cn]) == 1
                              else f"{s['name']} {ZONE_CODE[z]}"))
    # Each perennial BLOCK as a PINNED pseudo-succession: in the ground every week, acres fixed.
    # Everything downstream (land, labour, stock, cash) then treats it like any planting, and
    # nothing has to know a perennial exists except the acres bound. A bearing block harvests in
    # the crop's window; an establishing one is all G — no H, so it packs out nothing.
    # Its cost rides on the row as DATA: THIS year's, flat over 52 weeks like the farm's other
    # fixed costs. No depreciation line — a mature block's establishment is sunk.
    hw = set(PERENNIAL_SPEC["harvest_weeks"])
    for b in PERENNIAL_BLOCKS:
        succs.append(dict(name=b["name"], crop=CROP_NAMES.index(PERENNIAL), zone="Open field",
                          weeks=list(range(1, N_WEEKS + 1)), start_week=1, perennial=True,
                          cost_per_acre_wk=b["cost_per_acre_yr"] / N_WEEKS,
                          phases=[2 if (b["bearing"] and w in hw) else 1
                                  for w in range(1, N_WEEKS + 1)]))
    return payload, crops, ch_order, succs


PAYLOAD, CROPS, CH_ORDER, SUCCS = load()


def zone_acres(zones=None, land=None):
    """{zone: acres}, the remainder zone (acres None) taking what the others leave of `land`."""
    zones = ZONES if zones is None else zones
    land = PAYLOAD["total_land"] if land is None else land
    fixed = sum(z[1] for z in zones if z[1] is not None)
    return {z[0]: (land - fixed if z[1] is None else z[1]) for z in zones}


def identity(cn):
    """The name the MARKET knows a crop by. A variant sells as its base; everything else is itself."""
    return CROPS[cn].get("sells_as", cn)


IDENTITIES = list(dict.fromkeys(identity(c) for c in CROP_NAMES))   # Spinach Kale Garlic Asparagus


def members(gid):
    """Every crop NAME that sells as identity `gid` — the FX.5 grouping, stated once."""
    return [c for c in CROP_NAMES if identity(c) == gid]


def stands(s, w):
    """Is planting `s` in the ground in week `w` of the cyclic year? THE definition — the land
    rows, the floors, the carry-in pin and the guards that check them all read this one."""
    return any(((wk - 1) % N_WEEKS) + 1 == w for wk in s["weeks"])


def weeks_short(res, k):
    """The weeks contract `k` came out short in a solve result."""
    return sorted(w for (kk, w), v in res["short"].items() if kk == k and v > 1e-6)


# Identities the C15 carry-in pin applies to: any with a member flagged `overwinters`.
OVERWINTERING = [g for g in IDENTITIES if any(CROPS[m].get("overwinters") for m in members(g))]


def payroll_load():
    """The regular-hour payroll load: FICA + straight-time (L.5 split), or the legacy single key."""
    if "fica_pct" in PAYLOAD:
        return PAYLOAD["fica_pct"] + PAYLOAD.get("straight_time_load_pct", 0.0)
    return PAYLOAD.get("payroll_load_pct", 0.0)

# ⚠️ PIECE RATES ARE PER CROP, and the research says why: a piece-rate worker must still earn
# the minimum wage for hours worked, so the FLOOR in $/lb is set by how fast the crop picks —
# a 3.6x spread here. Entered the way a contract actually reads ($ per container) and converted
# with the crop's own volume figure, which is the same number the storage rows use.
BUSHEL_M3 = 1.2444 * 0.0283168        # USDA bushel = 1.2444 cu ft
PIECE_CONTAINER = {"Spinach": ("bushel", 3.00), "Kale": ("bushel", 1.00),
                   "Garlic": ("bushel", 2.00)}
# v12: piece rate stays on the three field crops. Tunnel spinach and asparagus are picked by the
# crew — a simplification, stated, and one the FX layer does not need to test.
PIECE_CROPS = list(PIECE_CONTAINER)


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
FM = next(h for h in CH_NAMES if h.startswith("Farmers"))
PERENNIAL_NAMES = {s["name"] for s in SUCCS if s.get("perennial")}
PERENNIAL_BY_NAME = {b["name"]: b for b in PERENNIAL_BLOCKS}
NO_PERENNIAL = {n: 0.0 for n in PERENNIAL_BY_NAME}   # the "without" side of its delta
# ⚠️ CAPS ARE BUILT PER IDENTITY, never per name — the variant has no cap of its own. Handing
# the app's demand builder the variant too is exactly the FX.5 trap: it would mint a second,
# full-size Spinach market.
_DT = build_demand_table([CROPS[i] for i in IDENTITIES], CH_ORDER, N_WEEKS)
_AC = build_annual_caps([CROPS[i] for i in IDENTITIES], CH_ORDER)


def cap_spec(cn, hn):
    """The cap on an IDENTITY x channel. Pass a crop name and you get its identity's cap."""
    ci, hi = IDENTITIES.index(identity(cn)), CH_NAMES.index(hn)
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
    load = 1.0 + payroll_load()
    out = []
    for e in PAYLOAD.get("employees", []):
        a, b = e.get("start_week", 1), e.get("end_week", N_WEEKS)
        salaried = e["type"] == "salary"
        # contracted hours are what the WAGE is paid for; field hours are what the CROPS get.
        # field% reduces capacity without reducing the wage — that asymmetry is the whole
        # reason both numbers have to exist.
        contract = e["count"] * e["hours_per_week"]
        # Admin % (L.4) is the inverse of the old Field %; a pre-L.4 payload still sends Field %.
        field_pct = 100 - e["admin_pct"] if "admin_pct" in e else e.get("field_time_pct", 100)
        field = contract * field_pct / 100.0
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
    load = 1.0 + payroll_load()
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
          wage_floor_per_hr=16.07,
          zones=None, share_caps=True, perennial_acres=None, carry_in=None,
          must_stand=None, must_annual=None, contracts=None):
    """Maximise revenue - growing cost, as a MILP. Returns a dict of the optimum.

    `min_acreage=False` drops the binaries and solves the LP relaxation — useful only to show
    what the minimum-acreage rule costs, never as an answer.

    v12 fixed-layer arguments default to the module's toy settings; pass `[]` / `{}` to switch a
    piece OFF (that is how the with/without deltas are measured). `perennial_acres` is
    {block name: acres}, merged over each block's default — `NO_PERENNIAL` switches all off.
    `share_caps=False` is the FX.5 TRAP, kept only so it can be measured: every crop NAME gets
    its own full market.
    """
    _args = dict(locals())   # MUST STAY FIRST: the caller's arguments, for the re-solve below
    zone_cap = zone_acres(zones, land)
    # {block: acres}. A bare number (the pre-blocks API) or an unknown name is REFUSED: either one
    # silently kept the default acres, so `perennial_acres=0.0` "removed" nothing.
    if perennial_acres is not None and not isinstance(perennial_acres, dict):
        raise ValueError(f"perennial_acres is {{block: acres}}, got {perennial_acres!r}")
    for n, ac in (perennial_acres or {}).items():
        if n not in PERENNIAL_BY_NAME or ac < 0:
            raise ValueError(f"perennial block {n!r}: {ac} acres (blocks: {list(PERENNIAL_BY_NAME)})")
    perennial_acres = {**{n: b["acres"] for n, b in PERENNIAL_BY_NAME.items()},
                       **(perennial_acres or {})}
    carry_in = CARRY_IN if carry_in is None else carry_in
    must_stand = MUST_STAND if must_stand is None else must_stand
    must_annual = MUST_ANNUAL if must_annual is None else must_annual
    contracts = [Contract(*c) for c in (CONTRACTS if contracts is None else contracts)]
    # Windows are WEEKS OF THIS YEAR. Unchecked, a week 53 indexed straight into the NEXT
    # crop-channel's week-1 offered cell (off_i is a flat index), so a contract was "met" by
    # another crop's January sales with no error. And one floor or contract per identity
    # (x channel): the sheet labels its rows by identity, so a second would collide there.
    for gid, _ac, a, b in must_stand:
        if not 1 <= a <= b <= N_WEEKS:
            raise ValueError(f"must-plant {gid}: window {a}-{b} is not inside weeks 1-{N_WEEKS}")
    for gid, h, _lb, a, b, mode, pen in contracts:
        if not 1 <= a <= b <= N_WEEKS:
            raise ValueError(f"contract {gid}/{h}: window {a}-{b} is not inside weeks 1-{N_WEEKS}")
        # The mode is a choice the grower MUST make, and 'penalty' must carry its price: a blank
        # or $0 penalty is a contract that binds nobody — exactly what the ruling forbids.
        if mode not in CONTRACT_MODES:
            raise ValueError(f"contract {gid}/{h}: mode {mode!r} is not one of {CONTRACT_MODES}")
        if mode == "penalty" and not (pen is not None and pen > 0):
            raise ValueError(f"contract {gid}/{h}: 'penalty' needs a $/lb above 0, got {pen!r}")
    for gid, ac in carry_in.items():
        if ac is not None and ac < 0:
            raise ValueError(f"carry-in {gid}: {ac} acres")
        if gid not in OVERWINTERING:
            raise ValueError(f"carry-in {gid}: nothing that sells as it overwinters")
    for what, keys in (("standing floor", [f[0] for f in must_stand]),
                       ("contract", [(c.gid, c.channel) for c in contracts])):
        if len(keys) != len(set(keys)):
            raise ValueError(f"the toy carries one {what} per identity — got {keys}")
    # Validated, so normalised ONCE: a 'deliver' contract has no price, and every use below reads 0.
    contracts = [c._replace(pen=c.pen or 0.0) for c in contracts]
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
    n_piece = len(PIECE_CROPS) * N_WEEKS if piece else 0
    n_pbin = 1 if piece else 0
    # FX.3: one shortfall cell per contract week. Weeks listed once per contract, in order.
    short_keys = [(k, w) for k, (_i, _h, _lb, a, b, _m, _pen) in enumerate(contracts)
                  for w in range(a, b + 1)]
    n_short = len(short_keys)
    N = n_s + n_off + n_y + n_ot + n_extra + n_piece + n_pbin + n_short
    off_i = lambda p, w: n_s + p * N_WEEKS + (w - 1)
    y_i = lambda i: n_s + n_off + i
    _ot0 = n_s + n_off + n_y
    ot_i = lambda r, w: _ot0 + r * N_WEEKS + (w - 1)
    _ex0 = _ot0 + n_ot
    extra_i = lambda r: _ex0 + r
    _pc0 = _ex0 + n_extra
    piece_i = lambda c, w: _pc0 + c * N_WEEKS + (w - 1)
    pbin_i = _pc0 + n_piece          # 1 if the piece-rate crew is engaged at all
    _sh0 = pbin_i + n_pbin
    short_i = {kw: _sh0 + j for j, kw in enumerate(short_keys)}
    is_per = [bool(s_.get("perennial")) for s_ in SUCCS]

    # The nominated window. Everything about the advisory crew is derived from it, so the
    # window is stated ONCE and never re-derived — v8's labour bugs were all a quantity
    # recomputed in a second place.
    load = 1.0 + payroll_load()
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
    for cn in PIECE_CROPS:
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
    for cn in PIECE_CROPS:
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
    # FX.2: a perennial block carries THIS year's cost, spread flat over 52 weeks like the farm's
    # other fixed costs, and NEVER as seed. A mature block's establishment is sunk.
    for i, s_ in enumerate(SUCCS):
        c = CROPS[CROP_NAMES[s_["crop"]]]
        if "cost_per_acre_wk" in s_:          # FX.2: committed ground carries its own cost
            var_week[i, 1:] += s_["cost_per_acre_wk"]
            continue
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
        if CROP_NAMES[s_["crop"]] not in PIECE_CROPS:
            continue                     # only hours a piece crew could actually pick
        c = CROPS[CROP_NAMES[s_["crop"]]]
        for wk, ph in zip(s_["weeks"], s_["phases"]):
            if ph == 2:
                harv_week[i, ((wk - 1) % N_WEEKS) + 1] += c.get("labor_harv", 0.0)

    lab_cap, wage_wk, hourly_field, hourly_heads = labour_arrays()
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
    # ⚠️ FX.5: ONE row per IDENTITY x channel, summing every crop that sells as it. With
    # `share_caps=False` each NAME gets its own row — the trap, reproduced on purpose.
    groups = {}
    for p, (cn, hn) in enumerate(pairs):
        key = (identity(cn), hn) if share_caps else (cn, hn)
        groups.setdefault(key, []).append(p)
    for (gid, hn), grp in groups.items():
        ctype, cval, w0, w1 = cap_spec(gid, hn)
        if annual_override and (gid, hn) in annual_override:
            ctype, cval = "Annual", float(annual_override[(gid, hn)])
        if ctype == "Annual":
            e = np.zeros(N)
            for p in grp:
                st, _ = defaults(*pairs[p])
                for w in range(1, N_WEEKS + 1):
                    e[off_i(p, w)] = st
            add(e, -np.inf, cval)                        # C6b: the yearly total
        else:
            for w in range(1, N_WEEKS + 1):
                e = np.zeros(N)
                for p in grp:
                    e[off_i(p, w)] = defaults(*pairs[p])[0]
                add(e, -np.inf, cval if w0 <= w <= w1 else 0.0)

    # FX.3 — contract floors, on the IDENTITY (a buyer contracted for spinach, not for a bed):
    #     sold[identity, ch, w] + short[k, w] >= floor
    # The slack is what makes an unmeetable contract a REPORTED SHORTFALL instead of an
    # infeasible model, and its penalty is what makes the solver try before it gives up.
    for (k, w) in short_keys:
        gid, hn, lb, _a, _b, _mode, pen = contracts[k]
        e = np.zeros(N)
        for p, (cn, h2) in enumerate(pairs):
            if identity(cn) == gid and h2 == hn:
                e[off_i(p, w)] = defaults(cn, h2)[0]
        e[short_i[(k, w)]] = 1.0
        add(e, lb, np.inf)
        c_obj[short_i[(k, w)]] += pen             # 'deliver': 0, and the short cell is bounded to 0

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
        in_pool = [n for n in CROP_NAMES
                   if ("Cold" if CROPS[n].get("cold_storage", True) else "Ambient") == pool]
        for w in range(1, N_WEEKS + 1):
            e = np.zeros(N)
            for cn in in_pool:
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
            for c_, cn in enumerate(PIECE_CROPS):
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
        for c_, cn in enumerate(PIECE_CROPS):
            for w in piece_weeks:
                c_obj[piece_i(c_, w)] += piece_eff[cn]
        c_obj[pbin_i] += max(0.0, piece_fixed_cost)

    if piece:
        crop_succs = {cn: [i for i, s_ in enumerate(SUCCS)
                           if CROP_NAMES[s_["crop"]] == cn] for cn in PIECE_CROPS}
        for w in range(1, N_WEEKS + 1):
            for c_, cn in enumerate(PIECE_CROPS):
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
            for c_, cn in enumerate(PIECE_CROPS):
                if lb_per_harvest_hr[cn]:
                    e[piece_i(c_, w)] = 1.0 / lb_per_harvest_hr[cn]
            e[pbin_i] = -float(piece_max_hours_per_week)
            add(e, -np.inf, 0.0)
            # (c) ⚠️ relief cannot exceed the HARVEST hours actually needed that week. Without
            # it the crew relieves planting and growing hours it never touches — free labour
            # wearing a piece rate.
            e = np.zeros(N)
            for c_, cn in enumerate(PIECE_CROPS):
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
            # ⚠️ NO SHORTFALL PENALTY IN HERE. It was charged in the week of the miss, and then a
            # big penalty on an UNAVOIDABLE shortfall (kale, wks 36-37) drained the credit line and
            # made the model infeasible — measured at $200/lb — which is exactly the "no feasible
            # plan" ruling G3 forbids. A penalty is settled with the buyer after the season, like
            # interest is post-solve here: in the objective and the P&L, never the cash floor.
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
                for c_, cn in enumerate(PIECE_CROPS):
                    for w in range(1, W + 1):
                        if w in piece_weeks:
                            e[piece_i(c_, w)] -= piece_eff[cn]
                if piece_weeks and W >= piece_weeks[0]:
                    e[pbin_i] -= max(0.0, piece_fixed_cost)
            add(e, -(op_cash + cred) + W * fixed_wk + wage_wk[1:W + 1].sum(), np.inf)

    # land standing in the ground — FX.4: ONE ROW PER ZONE PER WEEK. A tunnel acre and a field
    # acre are not interchangeable, which is the whole reason a zone exists. `land` (the old
    # single-pool override) resizes the remainder zone only, so v11's land sweep means the same.
    # ⚠️ Rows for EVERY zone a planting names, at 0 acres if the farm lacks it. Built only over the
    # farm's zones (as first written), a planting in a missing zone had NO land row and was
    # unbounded — measured: dropping the tunnel "raised" profit $91k on ground that did not exist.
    for z in dict.fromkeys(s_["zone"] for s_ in SUCCS):
        for w in range(1, N_WEEKS + 1):
            e = np.zeros(N)
            for i, s in enumerate(SUCCS):
                if s["zone"] == z and stands(s, w):
                    e[i] = 1.0
            add(e, -np.inf, zone_cap.get(z, 0.0))

    # FX.1 — must-plant floors. UNCONDITIONAL: no binary appears, so the solver cannot escape
    # by not planting (which is exactly how `min_acreage_if_planted` is escaped — measured in
    # PLAN FX.1 as a 14-acre garlic floor -> 0 acres).
    #   standing  every week of [a, b]:  acres of the identity in the ground >= floor
    #   annual    acres planted across the year's successions >= floor (perennial excluded:
    #             its acres are committed, not planted this year)
    def floor_row(gid, ac, keep, what, hi=np.inf, kind="must-plant"):
        """ac <= acres over the identity's plantings that pass `keep` <= hi — a FLOOR by default,
        a PIN with hi=ac. REFUSED, with the reason, when nothing can qualify (an empty row would
        only surface as a generic 'infeasible') — except a pin at 0, which an empty row meets."""
        e = np.zeros(N)
        for i, s in enumerate(SUCCS):
            if identity(CROP_NAMES[s["crop"]]) == gid and keep(i, s):
                e[i] = 1.0
        if not e.any():
            if ac == hi == 0:
                return
            raise RuntimeError(f"{kind}: {ac:g} ac of {gid} {what}, but nothing it can grow "
                               f"qualifies — refused, not silently dropped")
        add(e, ac, hi)

    for gid, ac, a, b in must_stand:
        for w in range(a, b + 1):
            floor_row(gid, ac, lambda i, s, w=w: stands(s, w), f"must stand in week {w}")
    for gid, ac in must_annual.items():
        floor_row(gid, ac, lambda i, s: not is_per[i], "must be planted this year")

    # C15 — the carry-in PIN. For every identity with an overwintering member: acres standing in
    # week 1 == what is already in the ground. In the cyclic year those are the plantings that
    # WRAP — the same acres replanted this fall — so the one row both honours last fall and
    # holds back this fall's ground, crew and storage for the replant. Unlisted -> pinned at 0.
    # The SAME row builder as the floors, with an equal ceiling — one mechanism, as the spec asks.
    for gid in OVERWINTERING:
        if gid in carry_in and carry_in[gid] is None:
            continue          # MEASUREMENT ONLY: unpinned, so a test can price the pin itself
        ac = float(carry_in.get(gid, 0.0))
        floor_row(gid, ac, lambda i, s: stands(s, 1), "in the ground on 1 January", hi=ac,
                  kind="carry-in")

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
    for i in range(n_s):
        if is_per[i]:
            # FX.2: committed ground. Acres are an INPUT, so the bound IS the decision; the
            # binary is pinned on (min acreage 0) so C9/C10 hold trivially.
            ac = float(perennial_acres[SUCCS[i]["name"]])
            lb_v[i] = ub_v[i] = ac
            if min_acreage:
                lb_v[y_i(i)] = ub_v[y_i(i)] = 1.0 if ac > 0 else 0.0
    for kw in short_keys:
        # cannot be short more than the order — and a 'deliver' contract cannot be short at all
        c_ = contracts[kw[0]]
        ub_v[short_i[kw]] = c_.lb if c_.mode == "penalty" else 0.0
    res = milp(c=c_obj, constraints=LinearConstraint(A, lo, hi), integrality=integrality,
               bounds=Bounds(lb_v, ub_v), options={"disp": False, "time_limit": 300,
                                              # v12: the default 1e-4 gap is ~$50 of noise on a
                                              # $490k plan — larger than some FX deltas measured.
                                              "mip_rel_gap": 1e-7})
    if not res.success:
        # ⚠️ Reachable by INPUT, not only by a bug: floors, the carry-in pin and 'deliver'
        # contracts are all hard. A 'deliver' contract is diagnosed by name: re-solve with it as
        # a heavily-penalised shortfall, and the weeks still short are the ones no plan can fill.
        hard = [k for k, c_ in enumerate(contracts) if c_.mode == "deliver"]
        if hard:
            soft = [c_._replace(mode="penalty", pen=1_000.0) if k in hard else c_
                    for k, c_ in enumerate(contracts)]
            try:
                el = solve(**{**_args, "contracts": soft})
            except RuntimeError:
                el = None
            # Only blame a 'deliver' contract the soft re-solve actually shows short — otherwise
            # the cause is elsewhere and the general message below is the honest one.
            if el is not None and any(el["short_lb"][k] > 1e-6 for k in hard):
                why = "; ".join(
                    f"{contracts[k].gid}/{contracts[k].channel} {el['short_lb'][k]:,.0f} lb short "
                    f"(weeks {', '.join(map(str, weeks_short(el, k)))})"
                    for k in hard if el["short_lb"][k] > 1e-6)
                raise RuntimeError(f"no plan can deliver every 'deliver' contract: {why} — "
                                   f"switch it to a penalty or change the order")
        raise RuntimeError(f"LP did not solve: {res.message} — if must-plant floors or a "
                           f"carry-in are set, check them against land, the crew in the "
                           f"planting and harvest weeks, and storage: any of the three can make "
                           f"one unplantable")

    x = res.x
    acres = {SUCCS[i]["name"]: float(x[i]) for i in range(n_s)}
    offered = {(cn, hn): [float(x[off_i(p, w)]) for w in range(1, N_WEEKS + 1)]
               for p, (cn, hn) in enumerate(pairs)}
    sold = {k: sum(v) * defaults(*k)[0] for k, v in offered.items()}
    revenue = sum(sold[(cn, hn)] * CROPS[cn].get("channels", {}).get(hn, {}).get("price_per_lb", 0.0)
                  for cn, hn in pairs)
    # FX.2 reported on its own line: a block's year is not "growing cost" a grower would
    # recognise, and folding it in would hide what the perennial costs.
    cost_i = x[:n_s] * var_week[:, 1:].sum(axis=1)
    per_mask = np.array(is_per)
    growing, perennial_cost = float(cost_i[~per_mask].sum()), float(cost_i[per_mask].sum())
    short = {kw: float(x[short_i[kw]]) for kw in short_keys}
    shortfall_cost = sum(short[kw] * contracts[kw[0]].pen for kw in short_keys)
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
                          for c_, cn in enumerate(PIECE_CROPS)) if w in piece_weeks else 0.0
            if piece_weeks and w == piece_weeks[0]:
                flex_w += x[pbin_i] * max(0.0, piece_fixed_cost)
        week_net[w] = (rev_w - pkg_w - grow_w - fixed_wk - wage_wk[w] - overhead * rev_w
                       - flex_w)              # the shortfall penalty is settled post-season
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
                for c_, cn in enumerate(PIECE_CROPS)}
    piece_used = bool(piece and x[pbin_i] > 0.5)
    piece_cost = (sum(sum(v) * piece_eff[cn] for cn, v in piece_lb.items())
                  + (max(0.0, piece_fixed_cost) if piece_used else 0.0))
    piece_hours_relieved = [sum(piece_lb[cn][w] / lb_per_harvest_hr[cn]
                                for cn in PIECE_CROPS if lb_per_harvest_hr[cn])
                            for w in range(N_WEEKS)]
    cost = (growing + packaging + fixed + ovh + wages + interest
            + ot_cost + hire_cost + piece_cost + perennial_cost + shortfall_cost)

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
                      - ot_cost - hire_cost - piece_cost - perennial_cost - shortfall_cost)
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
                var_week=var_week, perennial_cost=perennial_cost,
                short=short, shortfall_cost=shortfall_cost,
                short_lb={k: sum(v for (kk, _w), v in short.items() if kk == k)
                          for k in range(len(contracts))},
                zone_peak={z: max(sum(x[i] for i, s_ in enumerate(SUCCS)
                                      if s_["zone"] == z and stands(s_, w))
                                  for w in range(1, N_WEEKS + 1)) for z in zone_cap},
                identity_sold={(gid, hn): sum(v for (cn, h2), v in sold.items()
                                              if identity(cn) == gid and h2 == hn)
                               for gid in IDENTITIES for hn in CH_NAMES},
                offered=offered, sold=sold, status=res.status, planted=planted,
                n_planted=len(planted), n_offered=len(SUCCS),
                # PLANTINGS — the committed perennial is in the calendar but is not one
                n_plantings=sum(1 for k in planted if k not in PERENNIAL_NAMES),
                n_plantable=len(SUCCS) - len(PERENNIAL_NAMES))


if __name__ == "__main__":
    r = solve()
    print(f"OPTIMUM  profit ${r['profit']:,.0f}")
    print(f"   revenue    {r['revenue']:>12,.0f}")
    for k in ("growing", "packaging", "fixed", "overhead", "wages", "interest",
              "ot_cost", "hire_cost", "piece_cost", "perennial_cost", "shortfall_cost"):
        print(f"   {k:<10} {-r[k]:>12,.0f}")
    print(f"   plants {r['n_planted']} of {r['n_offered']} successions the app offers")
    print("\nacres:")
    for k, v in sorted(r["planted"].items(), key=lambda kv: -kv[1]):
        print(f"   {k:<14} {v:7.2f}")
    print("\nsold, lb:")
    for (cn, hn), v in sorted(r["sold"].items(), key=lambda kv: -kv[1]):
        print(f"   {cn:<8} / {hn:<15} {v:10,.0f}")
