"""The sentences the UI tells the grower about inventory, pinned as tests.

`test_inventory.py` proves the MECHANISM (the balance reconciles to the pound, the shelf-life
row binds, the cap holds). This file proves the CLAIMS — the specific promises the results
copy makes, in the direction a grower would test them by hand:

  1. "Produce not sold in its harvest week is carried forward week by week"
     ...and "occupies harvest storage for as long as it is held"
  2. "must be sold within the crop's shelf life or it is written off as waste"
  3. produce sold in the week it is picked STILL occupies the cooler that week
  4. "only the sell-through share enters storage" (culls occupy nothing)

Claim 3 INVERTED on 2026-07-28. It used to read "field-to-truck sales occupy nothing" — true of
end-of-week `inv`, false of coolers: field heat has to come off greens within the hour whether
they ship Tuesday or Friday, so a farm selling everything the week it picks was reporting a
storage requirement of zero. C4b now measures what is in the room DURING the week, which is why
the results copy no longer has to disclaim the number as a lower bound. Claim 4 is still a real
exclusion: culls never enter the room at all.

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


def _peak_room_m3(r):
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

        Measured as m3-WEEKS across the year, not as the peak. Since C4b started counting the
        harvest week itself (field heat), the peak usually falls in a harvest week — the room is
        fullest the day it is picked — so holding product longer adds occupancy in the weeks
        AFTER the peak and need not raise it at all. Peak answers "how big a room"; the sum
        answers "for how long", which is the claim being made here.
        """
        short = _solve(_farm(full_params, shelf_life=1, **self.BUYER), **_FREE)
        long_ = _solve(_farm(full_params, shelf_life=8, **self.BUYER), **_FREE)
        occ = lambda r: sum(r["capacity_series"]["storage"]["used"])
        assert occ(long_) > occ(short) * 1.05, (
            f"produce held for weeks must occupy the room for those weeks: {occ(short):.1f} "
            f"m3-weeks on the 1-week shelf life vs {occ(long_):.1f} on the 8-week one. No "
            f"increase means held stock is not being counted, only the harvest-week inflow"
        )


# ── Claim 3: same-week sales still occupy the cooler ─────────────────────────

def test_same_week_sales_still_occupy_storage(full_params):
    """Buyer open across the harvest weeks with demand to absorb everything, so nothing is ever
    held overnight and end-of-week `inv` is flat zero. The room is still full.

    This assertion is the inverse of the one that shipped this morning, which required the peak
    to be ~0 here — the behaviour that let the model report no cooler at all for a farm selling
    everything the week it picks. If it ever reverts to asserting zero, the reported peak has
    silently become a lower bound again and the results copy is wrong.
    """
    r = _solve(_farm(full_params, shelf_life=8, demand_season="W1-W52", weekly_lbs=1e9), **_FREE)

    assert _sold_lbs(r) > 1e3, "nothing sold — the assertion below would be vacuous"
    assert float(r["inventory"][:, 1:].max()) < 1e-6, (
        "nothing should be HELD overnight in this fixture; if it is, the test is no longer "
        "isolating same-week throughput"
    )
    assert _peak_room_m3(r) > 1e-6, (
        f"produce sold in its own harvest week must still occupy the cooler that week (field "
        f"heat), got {_peak_room_m3(r):.4f} m3. Zero here means the row is measuring end-of-week "
        f"stock again, and the reported peak cannot size a building"
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

    assert _peak_room_m3(full) > 0, "nothing held — the comparison would be vacuous"
    assert _planted_acres(full, p_full) > 0 and _planted_acres(half, p_half) > 0

    per_acre_full = _peak_room_m3(full) / _planted_acres(full, p_full)
    per_acre_half = _peak_room_m3(half) / _planted_acres(half, p_half)
    ratio = per_acre_half / per_acre_full
    assert 0.45 < ratio < 0.55, (
        f"halving sell-through must halve what is stored per acre — culls are removed at "
        f"harvest and never enter the cooler — got ratio {ratio:.3f} "
        f"({per_acre_half:.3f} vs {per_acre_full:.3f} m3/acre). A ratio near 1.0 means culls "
        f"ARE occupying storage and the results copy is wrong"
    )


# ── The ambient pool: capped and priced, never free ──────────────────────────

class TestAmbientStorageIsNotFree:
    """`cold_storage: False` moves a crop to the barn. The barn is a building the farm owns:
    it has a size you cannot exceed and a cost you pay whether it is full or empty.

    An UNCAPPED ambient pool was measured at $91,274/yr of free money — mark every crop
    ambient and the storage constraint stops existing, with the plan unchanged. These two
    tests are what stand between the toggle and that exploit.
    """

    def _farm_ambient(self, full_params, cap, rate):
        p = _farm(full_params, shelf_life=8, demand_season="W24-W40")
        p["crops"][0]["cold_storage"] = False
        p["ambient_storage_cap"] = cap
        p["rate_ambient_storage"] = rate
        return p

    def test_the_ambient_cap_actually_binds(self, full_params):
        """A cap below what the plan wants to store must change the plan. Without this, the
        toggle is a free pass out of every storage constraint on the farm."""
        roomy = _solve(self._farm_ambient(full_params, 1e9, 0.0), **_FREE)
        peak = roomy["ambient_peak_m3"]
        assert peak > 1.0, "the ambient crop stores nothing — the cap could not bind either way"
        assert roomy["storage_peak_m3"] < 1e-9, (
            "an ambient crop must not consume COLD capacity; that is the whole point of the flag"
        )

        squeezed = _solve(self._farm_ambient(full_params, peak * 0.25, 0.0), **_FREE)
        assert squeezed["ambient_peak_m3"] <= peak * 0.25 + 1e-6, (
            f"ambient stock {squeezed['ambient_peak_m3']:.2f} m3 exceeds its own "
            f"{peak * 0.25:.2f} m3 cap — the row is not enforced"
        )
        assert squeezed["profit"] < roomy["profit"], (
            "squeezing the barn must cost something, or the cap is decorative"
        )

    def test_ambient_capacity_is_paid_for(self, full_params):
        """Owned building → depreciation line, per the project's locked cost-accounting basis.
        Free barn space is what made the uncapped version an exploit."""
        free = _solve(self._farm_ambient(full_params, 500.0, 0.0), **_FREE)
        paid = _solve(self._farm_ambient(full_params, 500.0, 0.40), **_FREE)
        expected = 500.0 * 0.40 * W
        assert free["profit"] - paid["profit"] == pytest.approx(expected, rel=1e-6), (
            f"charging $0.40/m3/wk on a 500 m3 barn must cost {expected:,.0f}/yr; got "
            f"{free['profit'] - paid['profit']:,.0f}. A barn you own is paid for whether or "
            f"not it is full"
        )


def test_the_cold_cap_binds_on_the_number_it_reports(full_params):
    """The reported peak must be the quantity the ROW enforces, not a prettier one computed
    alongside it.

    Written after a mutation slipped through: reverting C4b to end-of-week held stock, while
    the reporter kept computing room occupancy, passed every other test in this file. That is
    the exact report-vs-enforce divergence that shipped twice on this branch (B.1's 5x
    overstatement, and the pre-B.2 inflow-vs-held mismatch), so it needs a test that can only
    pass when the two agree.

    The fixture sells everything in its harvest week, so end-of-week stock is zero. A row
    measuring held stock is therefore vacuous here and CANNOT bind, which makes the reported
    peak sail past a cap set below it.
    """
    p = _farm(full_params, shelf_life=8, demand_season="W1-W52", weekly_lbs=1e9)
    roomy = _solve(p, **_FREE)
    peak = roomy["storage_peak_m3"]
    assert peak > 1.0, "nothing in the room — the squeeze below would prove nothing"

    cap = peak * 0.5
    squeezed = _solve(p, **{**_FREE, "harvest_storage_cap": cap})
    assert squeezed["storage_peak_m3"] <= cap + 1e-6, (
        f"reported peak {squeezed['storage_peak_m3']:.2f} m3 exceeds the {cap:.2f} m3 cap it "
        f"was solved against — the row is enforcing a different quantity than the one being "
        f"reported, so the published number cannot size a building"
    )


def test_the_sell_through_default_is_defined_once():
    """The shipped default must not disagree with the fallbacks that stand in for it.

    It was written in THREE places: the input's `value=` attribute, the per-crop placeholder
    (`?.value || 85`), and the payload builder (`numOr(..., 85)`). Lowering the shipped default
    moved one and left two saying 85 — a fallback that disagrees with the field it backs up is a
    silent second default, and the payload builder's copy is on the money path.

    Now one `SELL_THROUGH_DEFAULT_PCT`, and this asserts the input agrees with it.
    """
    import re
    from tests.helpers import REPO

    html = (REPO / "public" / "index.html").read_text(encoding="utf-8")

    m = re.search(r"const SELL_THROUGH_DEFAULT_PCT\s*=\s*(\d+)", html)
    assert m, "SELL_THROUGH_DEFAULT_PCT is gone — the default has scattered again"
    const = int(m.group(1))

    m = re.search(r'id="sell_through_pct"[^>]*\bvalue="(\d+)"', html)
    assert m, "the sell-through input has no value attribute"
    shipped = int(m.group(1))

    assert shipped == const, (
        f"the sell-through input ships {shipped}% but SELL_THROUGH_DEFAULT_PCT is {const}% — "
        f"a blank or missing field would silently get a different farm than the form shows")

    stray = re.findall(r"sell_through_pct'\)\?\.value\s*\|\|\s*(\d+)", html)
    stray += re.findall(r"numOr\(g\('sell_through_pct'\)\?\.value,\s*(\d+)\)", html)
    assert not stray, (
        f"hard-coded sell-through fallbacks still present: {stray} — they must read "
        f"SELL_THROUGH_DEFAULT_PCT")
