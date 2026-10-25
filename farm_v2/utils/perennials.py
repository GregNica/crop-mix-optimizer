"""
perennials.py — committed ground that stands all year (FX.2): "3 acres of asparagus, planted 2019".

A perennial is a crop card flagged `perennial: true` (channels, prices, storage, and per-week
labour, water, fertiliser and fuel rates plus crop protection, like any crop) plus one or more
BLOCKS in the farm-level `commitments` list — one per planting ("patch"), because plantings of
one crop differ by age (grower ruling, SPEC_batchFX §5 ruling 6):

    {"id": "c1", "kind": "perennial", "crop": "Asparagus", "acres": 3, "zone": "Open field",
     "planted_year": 2019, "yield_per_acre": 1750, "extra_cost_per_acre": 0,
     "harvest_from_week": 18, "harvest_to_week": 25}

A block is never an optimiser choice. It enters the solver as a PINNED planting: in the ground
weeks 1-52, its acres fixed, so land, labour, water, storage and cash all see it like any crop and
nothing downstream needs to know a perennial exists. `yield_per_acre` is THIS year's (0 while
establishing — then it has no harvest weeks and packs out nothing). Its inputs are charged from
the card's rates like any crop's (grower, 2026-10-25: "perennials still need those"), never seed;
`extra_cost_per_acre` (default 0) is what this patch alone costs this year, spread flat. A mature
block's establishment is SUNK: no depreciation line (ruling 6 overrides OWN->depreciate for now).
`labor_grow`/`labor_harv` on a block override the card's (a young patch picks less). No yield ramp.

The card's growing season (`growing_from_week`, `growing_to_week`; absent = all year) bounds when
a patch uses anything: outside it the patch is DORMANT — it holds its land and uses no water,
fertiliser, fuel, crop protection or labour (grower, 2026-10-25: asparagus is not irrigated or
crewed in January). Harvest weeks must lie inside the season.

Read by validation and the solver alike, so a block one of them would refuse, the other refuses.
The checks every commitment kind shares (ids, source, which kinds exist) live in commitments.py.
"""

from farm_v2.utils.calendar import DORMANT, GROW, HARVEST, week_span
from farm_v2.utils.commitments import N_WEEKS, check_entries, week as _week
from farm_v2.utils.numbers import check_nonneg, check_positive
from farm_v2.utils.zones import crop_zone_names



def _number(v, what, *, positive=False):
    """`v` as a float, or ValueError — the shared money-input refusals (bool, str, NaN, < 0)."""
    (check_positive if positive else check_nonneg)(v, what)
    return float(v)


def growing_weeks(crop):
    """The weeks a perennial card's patches are active, or ValueError. Both ends or neither."""
    first, last = crop.get("growing_from_week"), crop.get("growing_to_week")
    if first is None and last is None:
        return list(range(1, N_WEEKS + 1))
    name = crop.get("name")
    if first is None or last is None:
        raise ValueError(f"Crop '{name}': give both growing_from_week and growing_to_week, or neither "
                         f"(neither = active all year).")
    return week_span(_week(first, f"Crop '{name}': growing_from_week"),
                     _week(last, f"Crop '{name}': growing_to_week"))


def resolve_perennial_blocks(commitments, crops, zone_names):
    """The perennial blocks in `commitments` that BIND this plan, each with every field filled
    in, or ValueError.

    `crops` are the resolved crops (variants filled in), `zone_names` the farm's zones in order.
    Every entry is checked, but one with `source: "suggested"` is left out of the result: a
    co-pilot suggestion is priced by a "try it" solve that sends it as accepted, and does not
    bind the plan until the grower accepts it (grower, 2026-10-25).
    Also refuses a perennial crop with no block at all: it would stand nowhere and read as
    unplanted. A crop whose only block is a suggestion is not refused — it is simply not planted.
    """
    by_name = {c.get("name"): c for c in crops}
    blocks = [_resolve_block(e, cid, source, by_name, zone_names)
              for e, cid, kind, source in check_entries(commitments) if kind == "perennial"]

    with_blocks = {b["crop"] for b in blocks}
    blocks = [b for b in blocks if b["source"] != "suggested"]
    for c in crops:
        if c.get("perennial") and c.get("name") not in with_blocks:
            raise ValueError(
                f"Crop '{c.get('name')}' is perennial but has no block in the commitments table. "
                f"Add its block(s) — acres, this year's yield and costs — or untick perennial."
            )
    return blocks


def _resolve_block(e, cid, source, by_name, zone_names):
    name = e.get("crop")
    crop = by_name.get(name)
    if crop is None:
        raise ValueError(f"Perennial block {cid!r} names crop {name!r}, which is not one of the farm's crops.")
    if not crop.get("perennial"):
        raise ValueError(
            f"Perennial block {cid!r} is for '{name}', which is not marked perennial. Tick "
            f"perennial on its card, or plant it as an annual."
        )
    what = f"Perennial block {cid!r} ({name})"
    acres = _number(e.get("acres"), f"{what}: acres", positive=True)

    eligible = crop_zone_names(crop, zone_names)
    zone = e.get("zone")
    if zone is None:
        if len(eligible) != 1:
            raise ValueError(f"{what}: say which zone it stands in — '{name}' may be in {eligible}.")
        zone = eligible[0]
    if zone not in zone_names:
        raise ValueError(f"{what} stands in zone {zone!r}, which the farm does not have ({zone_names}).")
    if zone not in eligible:
        raise ValueError(f"{what} stands in zone {zone!r}, but '{name}' is only allowed in {eligible}.")

    planted = e.get("planted_year")
    if planted is not None and (isinstance(planted, bool) or not isinstance(planted, int)):
        raise ValueError(f"{what}: planted_year must be a year, got {planted!r}.")

    # This year's yield, typed by the grower — no default: a guessed yield on committed ground is
    # a number nobody entered. The extra cost is an addition to the card's rates, so 0 is "none".
    ypa = _number(e.get("yield_per_acre"), f"{what}: this year's yield_per_acre (0 while establishing)")
    extra = _number(e.get("extra_cost_per_acre", 0.0), f"{what}: extra_cost_per_acre")
    if ypa > 0:
        first = _week(e.get("harvest_from_week"), f"{what}: harvest_from_week")
        last = _week(e.get("harvest_to_week"), f"{what}: harvest_to_week")
        harvest = week_span(first, last)            # may wrap the year, as a season window does
    else:
        harvest = []
    season = growing_weeks(crop)
    outside = [w for w in harvest if w not in season]
    if outside:
        raise ValueError(
            f"{what} harvests in week(s) {outside}, outside '{name}'s growing season (weeks "
            f"{season[0]}–{season[-1]}). Move the harvest weeks or widen the season on its card."
        )
    labour = {k: _number(e.get(k, crop.get(k)), f"{what}: {k}") for k in ("labor_grow", "labor_harv")}
    return {"id": cid, "source": source, "crop": name, "acres": acres, "zone": zone,
            "planted_year": planted, "yield_per_acre": ypa, "extra_cost_per_acre": extra,
            "harvest_weeks": harvest, "growing_weeks": season, **labour}


def perennial_successions(blocks, crops, zone_names):
    """One pinned pseudo-succession per block, in the shape generate_successions returns. Phases:
    harvest in the block's harvest weeks, grow in the rest of its card's growing season, DORMANT
    outside it; no planting phase — it is already in the ground.

    What the solver needs is carried as PLANTING properties, so its core asks about pins and
    overrides, never about perennials: `pinned_acres` (the acres are an input), `commitment_id`,
    and, under the crop card's own keys, this year's yield, the labour rates and a zero seed cost
    (establishment is sunk), read through calendar.planting_value; `extra_cost_per_acre` is the
    patch's own line. `block` is kept for the report only."""
    index = {c.get("name"): i for i, c in enumerate(crops)}
    out, used = [], set()
    for b in blocks:
        base = (f"{b['crop']} · planted {b['planted_year']}" if b["planted_year"] is not None
                else f"{b['crop']} block")
        if len(zone_names) > 1:
            base = f"{base} · {b['zone']}"
        name, n = base, 2
        while name in used:                    # two blocks of one crop, year and zone
            name, n = f"{base} ({n})", n + 1
        used.add(name)
        hw, season = set(b["harvest_weeks"]), set(b["growing_weeks"])
        out.append({
            "name": name,
            "crop": index[b["crop"]],
            "weeks": list(range(1, N_WEEKS + 1)),
            "phases": [HARVEST if w in hw else GROW if w in season else DORMANT
                       for w in range(1, N_WEEKS + 1)],
            "start_week": 1,
            "zone": zone_names.index(b["zone"]),
            "pinned_acres": b["acres"],
            "commitment_id": b["id"],
            "yield_per_acre": b["yield_per_acre"],
            "labor_grow": b["labor_grow"],
            "labor_harv": b["labor_harv"],
            "seed_transplant_cost_per_acre": 0.0,
            "extra_cost_per_acre": b["extra_cost_per_acre"],
            "block": b,
        })
    return out
