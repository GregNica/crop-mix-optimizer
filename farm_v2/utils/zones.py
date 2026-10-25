"""
zones.py — named land pools (FX.4): "2 ac high tunnel, the rest open field".

A zone is a share of the farm's land with its own weekly land row (C1). Crops name the zones they
may stand in. Absent zones are one zone, "Whole farm", so a farm that names none is the farm every
caller described before zones existed. Read by validation and the solver alike, so a zone one of
them would refuse, the other refuses too.
"""

import math

WHOLE_FARM = "Whole farm"


def resolve_zones(zones: list[dict] | None, total_land: float) -> list[dict]:
    """[{name, acres}] with every acreage filled in, or ValueError naming what is wrong.

    At most one zone may leave `acres` out: it takes what the others leave of `total_land`.
    Otherwise the zones must add up to the farm. A shortfall is refused rather than left
    unusable — a plan quietly unable to use land the grower owns is a silent failure.
    """
    if not zones:
        return [{"name": WHOLE_FARM, "acres": float(total_land)}]

    names = [z.get("name") for z in zones]
    if any(not isinstance(n, str) or not n.strip() for n in names):
        raise ValueError(f"Every zone needs a name. Got: {names}.")
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"Zone names must be unique — crops name their zones. Rename: {dupes}.")

    acres = []                                  # None = the zone taking the rest of the farm
    for name, z in zip(names, zones):
        a = z.get("acres")
        # bool and str refused, as validate._is_number refuses them for every money input:
        # float(True) is a 1-acre zone and float("2") a typed box that was never a number.
        if a is not None and (isinstance(a, bool) or not isinstance(a, (int, float))):
            raise ValueError(f"Zone '{name}': acres must be a number, got {a!r}.")
        if a is not None and not (math.isfinite(a) and a > 0):
            raise ValueError(f"Zone '{name}': acres must be > 0, got {a:g}.")
        acres.append(None if a is None else float(a))

    remainder = [n for n, a in zip(names, acres) if a is None]
    if len(remainder) > 1:
        raise ValueError(
            f"Only one zone can take 'the rest of the farm'; {remainder} all left acres blank."
        )
    fixed = sum(a for a in acres if a is not None)
    rest = float(total_land) - fixed
    if remainder and rest <= 1e-9:
        raise ValueError(
            f"Zone '{remainder[0]}' takes the rest of the farm, but the other zones already "
            f"use {fixed:g} of the {total_land:g} acres."
        )
    if not remainder and abs(rest) > 1e-6:
        raise ValueError(
            f"Zones add up to {fixed:g} acres but the farm is {total_land:g}. Make them add up, "
            f"or leave one zone's acres blank to take the rest."
        )
    return [{"name": n, "acres": rest if a is None else a} for n, a in zip(names, acres)]


def crop_zone_names(crop: dict, zone_names: list[str]) -> list[str]:
    """The farm zones `crop` may be planted in, in farm order, or ValueError.

    Absent (None) = every zone. A name the farm lacks is refused, never skipped: skipping it
    withdraws the crop from that zone without a word, and in the toy the version that kept such
    plantings with no land row at all was unbounded (+$91k of land that does not exist). An
    empty list is refused too — "eligible nowhere" is a crop to delete, not a crop to drop.
    """
    wanted = crop.get("zones")
    if wanted is None:
        return list(zone_names)
    if not isinstance(wanted, list) or not wanted:
        raise ValueError(
            f"Crop '{crop['name']}': zones must list at least one of the farm's zones "
            f"{zone_names}, or be left out to allow all of them. Got {wanted!r}."
        )
    unknown = [z for z in wanted if z not in zone_names]
    if unknown:
        raise ValueError(
            f"Crop '{crop['name']}' is allowed in zone(s) {unknown}, which the farm does not "
            f"have. The farm's zones are {zone_names}."
        )
    return [z for z in zone_names if z in wanted]
