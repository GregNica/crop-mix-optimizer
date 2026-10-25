"""
variants.py — a crop grown a second way and sold as the first (FX.5): "Tunnel Spinach".

A variant is its own crop card for everything about GROWING it — windows, days to maturity,
yield, seed and per-acre costs, zones, minimum acres — and is the parent for everything about
SELLING and handling it: the same pound, into the same buyers, at the same prices and caps, with
the same labour and the same diversity allowance (grower ruling, SPEC_batchFX §5 ruling 3).

Why it exists, measured in the app before it was built: keyed by crop name, Spinach and a Tunnel
Spinach copy each got the Farmers Market's 6,000 lb/wk and sold 12,000 lb into it in 10 weeks.
The solver therefore groups every cap by IDENTITY (`identity_groups`), and this module makes the
inherited fields the parent's own, so there is no second copy of a price or a cap to disagree.

Resolved by the adapter before it normalises the payload (so parent and variant are normalised
alike) and by the solver before validation (which needs the inherited fields present) — the
solver is where a bad variant is REFUSED. Resolving twice is a no-op.
"""

import copy

# Everything about SELLING and HANDLING the pound. The ruling names channels (prices, packaging,
# caps), diversity and labour; storage and shelf life are inherited because they are the same
# product in the same cooler. sell_through_fraction is NOT here: grade-out is a property of how
# it was grown (a tunnel crop grades better), so the variant may edit it.
INHERITED_KEYS = (
    "channels",
    "crop_diversity_max",
    "labor_plant", "labor_grow", "labor_harv",
    "cold_storage", "crop_size_m3_per_lb",
    "shelf_life_weeks", "sales_spread_weeks", "storage_loss_frac_per_week",
)
_ABSENT = object()


def resolve_variants(crops: list[dict]) -> list[dict]:
    """`crops` with each variant's inherited fields filled from its parent, or ValueError.

    A variant that leaves an inherited field out takes the parent's; one that sends the parent's
    value is fine (a payload may carry copies). One that sends a DIFFERENT value is refused by
    name: a second price or cap is a second product, which is a new crop card, not a variant.
    Copies, never mutates — callers reuse their crop list across solves.
    """
    if all(c.get("sells_as") is None for c in crops):
        # No variants: nothing to resolve, and nothing here may pre-empt validation's own
        # wording for a malformed crop (a missing name is ITS refusal to make).
        return list(crops)
    # Names before parents: a parent found by a duplicate or non-text name is the wrong card.
    names = [c.get("name") for c in crops]
    if any(not isinstance(n, str) for n in names) or len(names) != len(set(names)):
        raise ValueError(
            f"Crop names must be unique text before a variant can name its parent. Got: {names}."
        )
    by_name = dict(zip(names, crops))
    out = []
    for crop in crops:
        parent_name = crop.get("sells_as")
        if parent_name is None:
            out.append(crop)
            continue
        name = crop.get("name")
        if not isinstance(parent_name, str) or not parent_name.strip():
            raise ValueError(f"Crop '{name}': sells_as must name a crop, got {parent_name!r}.")
        if parent_name == name:
            raise ValueError(f"Crop '{name}' sells as itself; leave sells_as out instead.")
        parent = by_name.get(parent_name)
        if parent is None:
            raise ValueError(
                f"Crop '{name}' sells as '{parent_name}', which is not one of the farm's crops."
            )
        if parent.get("sells_as") is not None:
            raise ValueError(
                f"Crop '{name}' sells as '{parent_name}', which itself sells as "
                f"'{parent['sells_as']}'. Point it at '{parent['sells_as']}' directly."
            )
        variant = dict(crop)
        for key in INHERITED_KEYS:
            # A key the parent leaves out is a default the parent uses; the variant setting it
            # is just as much a second value as overriding a key the parent sends.
            if key in crop and crop[key] != parent.get(key, _ABSENT):
                raise ValueError(
                    f"Crop '{name}' sells as '{parent_name}', so it takes {parent_name}'s "
                    f"{key}. To sell or handle it differently, make it its own crop."
                )
            if key in parent:
                variant[key] = copy.deepcopy(parent[key])
        out.append(variant)
    return out


def identity_groups(crops: list[dict]) -> dict[int, list[int]]:
    """{index of the crop sold AS: [indices of every crop sold as it]}, in crop order.

    Call on resolved crops. Every demand cap, the diversity allowance and the saturation report
    are per identity: two names selling one product share one market. A crop with no variant is
    a group of one, so a farm with none groups exactly as it indexes.
    """
    index = {c.get("name"): i for i, c in enumerate(crops) if c.get("sells_as") is None}
    groups: dict[int, list[int]] = {}
    for i, c in enumerate(crops):
        root = index[c["sells_as"]] if c.get("sells_as") is not None else i
        groups.setdefault(root, []).append(i)
    return groups
