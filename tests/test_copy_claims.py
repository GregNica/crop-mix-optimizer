"""The sentences the UI tells the grower about inventory, pinned as tests.

`test_inventory.py` proves the MECHANISM (the balance reconciles to the pound, the shelf-life
row binds, the cap holds). This file proves the CLAIMS — the specific promises the results
copy makes, in the direction a grower would test them by hand:

  1. "Produce not sold in its harvest week is carried forward week by week"
     ...and "occupies harvest storage for as long as it is held"
  2. "must be sold within the crop's shelf life or it is written off as waste"
  3. "produce sold in the same week it is picked (field-to-truck sales occupy nothing)"
  4. "only the sell-through share enters storage" (culls occupy nothing)

Claims 3 and 4 are the two exclusions behind the "treat reported storage use as a LOWER BOUND
on the cooler you need" caveat. If either stops holding, that caveat becomes false and a
grower sizing a building from this number is misled — so they are pinned separately rather
than folded into one storage test.

Every test forces the behaviour with a constructed plan rather than reading it off the default
farm, which currently wastes nothing and holds little: assertions against it would pass while
saying nothing. The fixture comes from test_inventory.py deliberately — it encodes several
non-obvious requirements (keep the crew, use `demand_ranges` not `demand_season`, zero the
fixed-cost rates) that were each learned by writing a test that passed for the wrong reason.

Same discipline as test_inventory.py: if you add a test here, mutate the solver and watch it
fail before you believe it.
"""
import pytest

from tests.test_inventory import _one_crop_farm, _solve

W = 52

# The crop plants across 03-01..04-26 and harvests around W14, which leaves room for a buyer
# window later in the year — the geometry test_inventory.py established for shelf-life work.
HARVEST_SEASON = ("03-01", "04-26")
# Overrides so the constraint under test is the ONLY thing that can bite.
_FREE = dict(harvest_storage_cap=1e9, cash_constraint_enabled=False)


def _farm(full_params, shelf_life, demand_season="W24-W40", sell_through=1.0, weekly_lbs=1e6):
    p = _one_crop_farm(full_params, HARVEST_SEASON, demand_season,
                       shelf_life=shelf_life, weekly_lbs=weekly_lbs, min_acreage=5.0)
    # Set it on the CROP, not just the farm: the balance reads
    # `crop.get("sell_through_fraction", farm_default)`, so a crop-level key inherited from
    # the template would silently win over a farm-level override and the sell-through test
    # would compare two identical runs.
    p["crops"][0]["sell_through_fraction"] = sell_through
    p["sell_through_fraction"] = sell_through
    return p


def _total_waste_lbs(r):
    return sum(d["lbs"] for d in r["waste_by_crop"].values())


def _sold_lbs(r):
    return float(r["v"][0, :, 1:].sum())


def _peak_held_m3(r):
    return float(r["storage_peak_m3"])


def _planted_acres(r, p):
    return float(sum(r["x"])) * float(p["total_land"])


# ── Claims 1 + 2: carry it forward, or write it off ──────────────────────────

class TestShelfLifeDecidesCarryOrWaste:
    """A buyer who is always open but can only take 2,000 lb a week, against a harvest that
    arrives far faster than that. The surplus must either be held or dumped, and which one
    happens is a pure function of shelf life — which is what separates the two claims.

    Note the shape: this is the same shape as the real defect B.2 fixed, where the shipped app
    silently dumped 45% of its garlic. A "no buyer at all until week N" fixture does NOT work
    here — the solver simply declines to plant, waste is zero in both arms, and the test
    passes for the wrong reason (observed, before this fixture replaced it).
    """

    BUYER = dict(demand_season="W1-W52", weekly_lbs=2_000)

    def test_a_short_shelf_life_wastes_the_crop(self, full_params):
        """Claim 2. On a one-week shelf life, everything above 2,000 lb in the harvest week
        itself has nowhere to go."""
        r = _solve(_farm(full_params, shelf_life=1, **self.BUYER), **_FREE)
        assert _total_waste_lbs(r) > 0, (
            "a harvest that outruns its buyer on a 1-week shelf life must be written off — "
            "zero waste here means the shelf-life row is not binding"
        )

    def test_a_long_shelf_life_carries_it_to_the_buyer(self, full_params):
        """Claim 1. Same farm, same buyer, a shelf life that spans the following weeks."""
        short = _solve(_farm(full_params, shelf_life=1, **self.BUYER), **_FREE)
        long_ = _solve(_farm(full_params, shelf_life=8, **self.BUYER), **_FREE)

        assert _sold_lbs(long_) > _sold_lbs(short), (
            "widening the shelf life past the gap must let produce reach the buyer"
        )
        assert _total_waste_lbs(long_) < _total_waste_lbs(short), (
            "produce that now reaches a buyer must stop being dumped"
        )
        assert long_["profit"] > short["profit"], (
            "carrying produce to a buyer instead of dumping it must be worth money"
        )

    def test_carrying_it_occupies_storage(self, full_params):
        """Claim 1's second half — 'occupies harvest storage for as long as it is held'.

        The mutation this catches: a storage row that measures harvest-week INFLOW rather than
        held stock reports the same peak in both runs, because the same pounds are harvested in
        the same weeks either way. Only a held-stock measure moves here.
        """
        short = _solve(_farm(full_params, shelf_life=1, **self.BUYER), **_FREE)
        long_ = _solve(_farm(full_params, shelf_life=8, **self.BUYER), **_FREE)
        assert _peak_held_m3(long_) > _peak_held_m3(short), (
            f"produce held for weeks must show in storage: got {_peak_held_m3(short):.2f} m3 "
            f"held on the 1-week shelf life vs {_peak_held_m3(long_):.2f} m3 on the 8-week "
            f"one. No increase means the series is measuring inflow, not what is held"
        )


# ── Claim 3: field-to-truck sales occupy nothing ─────────────────────────────

def test_same_week_sales_occupy_no_storage(full_params):
    """The buyer is open across the harvest weeks themselves, with demand to absorb it all.

    Nothing is ever held past the week it was picked, so a series measuring END-of-week stock
    must read essentially zero — where one measuring throughput would report the whole
    harvest. This is what MAKES the reported peak a lower bound, so it is the pin on that
    caveat. Determinacy comes from the inventory tie-break: holding stock costs an epsilon,
    so selling immediately is strictly optimal rather than merely tied.
    """
    r = _solve(_farm(full_params, shelf_life=8, demand_season="W1-W52", weekly_lbs=1e9), **_FREE)

    assert _sold_lbs(r) > 1e3, "nothing sold — the assertion below would be vacuous"
    assert _peak_held_m3(r) < 1e-6, (
        f"produce sold in its own harvest week must occupy no storage, got "
        f"{_peak_held_m3(r):.4f} m3. A non-zero peak here means the series counts throughput, "
        f"which would make the 'lower bound' caveat in the results copy false"
    )


# ── Claim 4: culls never enter storage ───────────────────────────────────────

def test_only_the_sell_through_share_is_stored(full_params):
    """Same forced hold, two sell-through fractions.

    Compared per planted acre, so the test survives the plan choosing a different acreage at
    the lower sell-through — the claim is about what happens to a pound of harvest, not about
    how many acres get planted.
    """
    p_full = _farm(full_params, shelf_life=8, sell_through=1.0)
    p_half = _farm(full_params, shelf_life=8, sell_through=0.5)
    full, half = _solve(p_full, **_FREE), _solve(p_half, **_FREE)

    assert _peak_held_m3(full) > 0, "nothing held — the comparison would be vacuous"
    assert _planted_acres(full, p_full) > 0 and _planted_acres(half, p_half) > 0

    per_acre_full = _peak_held_m3(full) / _planted_acres(full, p_full)
    per_acre_half = _peak_held_m3(half) / _planted_acres(half, p_half)
    ratio = per_acre_half / per_acre_full
    assert 0.45 < ratio < 0.55, (
        f"halving sell-through must halve what is stored per acre — culls are removed at "
        f"harvest and never enter the cooler — got ratio {ratio:.3f} "
        f"({per_acre_half:.3f} vs {per_acre_full:.3f} m3/acre). A ratio near 1.0 means culls "
        f"ARE occupying storage and the results copy is wrong"
    )
