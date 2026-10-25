"""
commitments.py — the farm-level commitments table (SPEC_batchFX §6.1): what is already decided,
owed or physically in the ground, entered BEFORE the optimiser fills the rest.

Every entry is `{id, kind, source, ...}`. This module owns what all kinds share — the list shape,
unique ids, `source`, which kinds exist, and "a suggestion does not bind" — and resolves the two
FLOOR kinds itself (FX.1). Perennial patches are resolved by `perennials.py`.

    {"id": "k1", "kind": "must_stand", "crop": "Kale", "acres": 8, "from_week": 10, "to_week": 20}
        at least 8 acres of kale IN THE GROUND every week 10-20 (a CSA share, a promise to a
        buyer that the crop is there). The window may wrap the year.
    {"id": "k2", "kind": "must_plant_annual", "crop": "Kale", "acres": 45}
        at least 45 acres of kale PLANTED over the year, counted planting by planting.

Naming a crop counts it and its FX.5 variants (a Tunnel Spinach counts toward a Spinach floor);
naming a variant counts that variant only. The two kinds are different promises, measured so in
the toy: 30 ac kale as an annual floor cost $0 (the plan already plants more); standing over
weeks 10-20 it cost $49,240. A
standing floor counts every planting in the ground that week, a perennial patch included; the
annual floor counts chosen plantings only — a patch is not "planted" this year.

Carry-in (grower ruling 1, 2026-10-25). An overwintering crop's `committed_acres` is the ground
already standing when the plan is made, so it becomes a standing commitment with window [1, 1]
and an EQUAL ceiling: a PIN, not a floor. The planning year is cyclic, so the same pin also
reserves this fall's ground for replanting that quantity. An overwintering crop with no acres
entered is pinned at 0 in week 1 — nothing was planted last fall, so nothing overwinters. This is
the migration of the old C15 (`committed_acres` = a week-1 floor); there is no second code path.
"""

from farm_v2.utils.calendar import week_span
from farm_v2.utils.numbers import check_positive, is_number
from farm_v2.utils.variants import identity_groups

N_WEEKS = 52
FLOOR_KINDS = ("must_stand", "must_plant_annual")
KINDS = FLOOR_KINDS + ("perennial",)
KINDS_PLANNED = ("contract",)
SOURCES = ("user", "suggested", "accepted")
CARRY_IN = "carry-in:"          # id prefix of the carry-in the app makes for each crop


def committed_acres(crop):
    """The acres of `crop` already in the ground when the plan is made (0 when blank)."""
    return float(crop.get("committed_acres", 0.0) or 0.0)


def check_entries(commitments):
    """The commitments list, each entry's shared fields checked, or ValueError.
    Returns [(entry, id, kind, source)] in the order given; every entry is checked, a
    suggestion included, so the result says which bind (source != "suggested")."""
    commitments = [] if commitments is None else commitments
    if not isinstance(commitments, list) or not all(isinstance(e, dict) for e in commitments):
        raise ValueError(f"commitments must be a list of entries, got {commitments!r}.")
    seen, out = set(), []
    for e in commitments:
        cid = e.get("id")
        if isinstance(cid, bool) or not isinstance(cid, (str, int)) or cid == "":
            raise ValueError(f"Every commitment needs an id (text or a number), got {cid!r}.")
        if cid in seen:
            raise ValueError(f"Commitment id {cid!r} is used twice; ids must be unique.")
        if isinstance(cid, str) and cid.startswith(CARRY_IN):
            # The app names each crop's carry-in this way; sharing the name would merge the two
            # in a refusal and in a per-entry with/without (/code-review high #7).
            raise ValueError(f"Commitment id {cid!r}: ids starting {CARRY_IN!r} are reserved.")
        seen.add(cid)
        kind, source = e.get("kind"), e.get("source", "user")
        if source not in SOURCES:
            raise ValueError(f"Commitment {cid!r}: source must be one of {list(SOURCES)}, got {source!r}.")
        if kind in KINDS_PLANNED:
            raise ValueError(f"Commitment {cid!r}: kind {kind!r} is not supported yet.")
        if kind not in KINDS:
            raise ValueError(f"Commitment {cid!r}: unknown kind {kind!r}.")
        out.append((e, cid, kind, source))
    return out


def week(v, what):
    """A whole week 1-52, or ValueError naming `what`."""
    if not is_number(v) or v != int(v) or not 1 <= v <= N_WEEKS:
        raise ValueError(f"{what} must be a whole week 1-{N_WEEKS}, got {v!r}.")
    return int(v)


def resolve_floors(commitments, crops, total_land):
    """Every floor that BINDS this plan, or ValueError: the must_stand / must_plant_annual
    entries (suggestions left out, like a suggested patch), then one carry-in per overwintering
    crop (or crop with committed acres), in crop order.

    Each floor: {id, kind, crop, members, acres, weeks}. `members` are the crop indices it counts:
    naming a crop counts the crop and its FX.5 variants (a Tunnel Spinach counts toward Spinach);
    naming a VARIANT counts that variant only — "5 ac of tunnel spinach" is not met by field
    spinach (/code-review high #6). `weeks` is the standing window (None for an annual floor). A
    `carry_in` is a PIN — its row has an equal ceiling — and covers only its own crop."""
    root_of = {m: root for root, ms in identity_groups(crops).items() for m in ms}
    index = {c.get("name"): i for i, c in enumerate(crops)}
    floors = []
    for e, cid, kind, source in check_entries(commitments):
        if kind not in FLOOR_KINDS:
            continue
        name = e.get("crop")
        what = f"Commitment {cid!r} ({kind})"
        if name not in index:
            raise ValueError(f"{what} names crop {name!r}, which is not one of the farm's crops.")
        if crops[index[name]].get("perennial") and kind == "must_plant_annual":
            raise ValueError(
                f"{what}: '{name}' is perennial — its patches are planted already and are not "
                f"counted as this year's planting. Use a standing commitment, or its patches."
            )
        check_positive(e.get("acres"), f"{what}: acres")
        acres = float(e["acres"])
        if acres > total_land + 1e-9:
            raise ValueError(f"{what} asks for {acres:g} acres of '{name}' on a {total_land:g}-acre farm.")
        weeks = None
        if kind == "must_stand":
            weeks = week_span(week(e.get("from_week"), f"{what}: from_week"),
                              week(e.get("to_week"), f"{what}: to_week"))
        if source == "suggested":
            continue
        i = index[name]
        members = [m for m, r in root_of.items() if r == i] if root_of[i] == i else [i]
        floors.append({"id": cid, "kind": kind, "crop": name, "acres": acres, "weeks": weeks,
                       "members": members})
    for c_idx, crop in enumerate(crops):
        if committed_acres(crop) <= 0 and not crop.get("overwinters"):
            continue
        floors.append({"id": f"{CARRY_IN}{crop.get('name')}", "kind": "carry_in",
                       "crop": crop.get("name"), "acres": committed_acres(crop), "weeks": [1],
                       "members": [c_idx]})
    return floors


def floor_columns(floor, successions, phase_table):
    """[(week, [planting indices])] the floor's rows sum over: per standing week, the identity's
    plantings in the ground that week (a pinned patch included); for an annual floor one entry,
    week None, over its chosen plantings (pins excluded — a patch is not planted this year)."""
    mine = [i for i, s in enumerate(successions) if s["crop"] in floor["members"]]
    if floor["weeks"] is None:
        return [(None, [i for i in mine if "pinned_acres" not in successions[i]])]
    return [(w, [i for i in mine if phase_table[i][w] is not None]) for w in floor["weeks"]]


def describe(floor):
    """The floor in the grower's words, for refusals: 'Kale: 8 ac standing weeks 10–20 (k1)'."""
    if floor["kind"] == "carry_in":
        return f"{floor['crop']}: {floor['acres']:g} ac already in the ground (overwintered)"
    if floor["kind"] == "must_plant_annual":
        return f"{floor['crop']}: at least {floor['acres']:g} ac planted this year ({floor['id']})"
    w = floor["weeks"]
    span = f"week {w[0]}" if len(w) == 1 else f"weeks {w[0]}–{w[-1]}"
    return f"{floor['crop']}: at least {floor['acres']:g} ac standing {span} ({floor['id']})"
