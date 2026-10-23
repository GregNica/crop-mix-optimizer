"""
Inventory core (SPEC_v3 §3) — the correctness gate for C4a/C4b/C4c.

"Profit moved in the expected direction" is not evidence that a constraint rewrite is right.
An inventory balance is the easiest family in the model to verify absolutely — every pound is
accounted for, per crop, per week — so these tests reconcile the solution rather than sample
it, rebuilding the expected inventory from `x` and `v` rather than reading the array the
solver returned (that would assert a == a).

Several tests here guard specific defects that a prior version of SPEC_v3 shipped past two
reviewers; each says which one in its own docstring, and those docstrings are the reason not
to simplify the constructions away. Four separate guards in this file were found INERT by
mutation testing before they worked — vacuous fixtures, a tolerance wider than the error it
had to catch, an assertion that compared zero to zero. If you add one, mutate the solver and
watch it fail before you believe it.
"""
import copy

import numpy as np
import pytest

from farm_v2.solver import solve_farm_v2, INVENTORY_TIE_BREAK_PER_LB_WEEK
from farm_v2.utils.calendar import harvest_weeks_of
from farm_v2.utils.water import CATCHMENT_EFFICIENCY

W = 52
TOL = 1e-4


def _weekly_sellable_inflow(r, land, st_farm):
    """H[c,w] — sellable lbs entering inventory each week, rebuilt from the solved acreage.

    Independent of the solver's `inventory` array by construction: this walks the succession
    calendar and the even-split convention, which is what the balance's x-coefficients encode.
    """
    crops, succs, x = r["crops"], r["successions"], r["x"]
    H = np.zeros((len(crops), W + 1))
    for i, s in enumerate(succs):
        if x[i] <= 1e-12:
            continue
        crop = crops[s["crop"]]
        hw = harvest_weeks_of(s, W)
        if not hw:
            continue
        st_c = crop.get("sell_through_fraction", st_farm)
        per_week = st_c * x[i] * land * crop["yield_per_acre"] / len(hw)
        for w in hw:
            H[s["crop"], w] += per_week
    return H


def _held_m3_weekly(r):
    """Weekly storage occupancy in m3, rebuilt from the inventory the solver returned."""
    crops = r["crops"]
    return [sum(r["inventory"][c, w] * crops[c]["crop_size_m3_per_lb"]
                for c in range(len(crops)))
            for w in range(1, W + 1)]


def _solve(params, **overrides):
    r = solve_farm_v2(**{**params, **overrides})
    assert r["status"] == "optimal", f"expected optimal, got {r['status']} for {overrides}"
    return r


_ZEROED_RATES = ("rate_harvest_storage", "rate_water_storage", "rate_irrigation",
                 "rate_equip_storage", "rate_fuel_storage", "rate_machinery",
                 "rate_property_mortgage_rent", "other_debt_service_per_week")


def _one_crop_farm(full_params, harvest_season, demand_season, shelf_life,
                   weekly_lbs=1e6, min_acreage=0.0):
    """A single crop, a single buyer, and no fixed costs — so the only thing that can stop a
    sale is the constraint under test.

    The fixed-cost rates are zeroed deliberately. Left in, a 150-acre farm's overheads swamp
    a one-crop plan (measured: −$18.5bn), the optimizer plants nothing, and every "assert it
    does not sell" passes for the wrong reason.
    """
    p = copy.deepcopy(full_params)
    p["sell_through_fraction"] = 1.0
    crop = copy.deepcopy(p["crops"][0])
    crop["name"] = "ShelfTest"
    crop["shelf_life_weeks"] = shelf_life
    crop["seasons"] = [{"start": harvest_season[0], "end": harvest_season[1]}]
    crop["min_acreage_if_planted"] = min_acreage
    crop["crop_diversity_max"] = 1.0
    ch_name = p["channels"][0]["name"]
    # NOTE the schema: the solver wants `demand_ranges: [{"weeks", "weekly_lbs"}]`, not the
    # payload builder's `demand_season`/`weekly_demand_lbs`. Getting that wrong yields an
    # all-zero demand array, nothing sells, and every "assert it does not sell" passes for
    # the wrong reason — which is what happened here before the controls were added.
    crop["channels"] = {ch_name: {
        "price_per_lb": 5.0, "packaging_cost_per_lb": 0.0,
        "demand_cap_type": "weekly_varying",
        "demand_ranges": [{"weeks": demand_season, "weekly_lbs": weekly_lbs}],
    }}
    p["crops"] = [crop]
    p["channels"] = [p["channels"][0]]
    # No `if rate in p` guard: these are all real kwargs of solve_farm_v2, so a name that is
    # not there is a TYPO, and swallowing it in a file whose whole thesis is "no tests that
    # pass for the wrong reason" would be perverse.
    p.update(dict.fromkeys(_ZEROED_RATES, 0.0))
    p["well_weekly_cap_L"] = 1e12
    # NOTE: the crew is deliberately LEFT IN PLACE. Emptying year_round/seasonal_employees
    # zeroes labor capacity, C2 then forces x = 0, nothing is planted, and every "assert it
    # does not sell" passes vacuously — which is exactly how the first version of these tests
    # passed with the shelf-life row deleted from the solver.
    return p


@pytest.fixture(scope="module")
def solved(full_params):
    p = {**full_params, "sell_through_fraction": 0.85}
    r = _solve(p)
    return r, p


def _loss_of(r, p, c):
    """Per-crop weekly storage shrink, farm default unless the crop overrides it."""
    crop = r["crops"][c]
    return float(crop.get("storage_loss_frac_per_week",
                          p.get("storage_loss_frac_per_week", 0.0)) or 0.0)


class TestBalanceReconciles:
    """inv[c,w] = (1-loss)*inv[c,w-1] + st*H - sold - wasted, to the pound, every crop-week."""

    def test_balance_holds_every_week(self, solved):
        r, p = solved
        H = _weekly_sellable_inflow(r, p["total_land"], p["sell_through_fraction"])
        inv, waste, v = r["inventory"], r["waste"], r["v"]
        worst = 0.0
        for c, crop in enumerate(r["crops"]):
            keep = 1.0 - _loss_of(r, p, c)
            prev = 0.0
            for w in range(1, W + 1):
                expected = keep * prev + H[c, w] - float(v[c, :, w].sum()) - waste[c, w]
                worst = max(worst, abs(inv[c, w] - expected))
                assert abs(inv[c, w] - expected) < max(TOL, 1e-6 * max(1.0, abs(expected))), (
                    f"{crop['name']} W{w}: inventory balance off by "
                    f"{inv[c, w] - expected:,.6f} lb (held {inv[c, w]:,.2f}, "
                    f"expected {expected:,.2f})"
                )
                prev = inv[c, w]
        assert worst < TOL

    def test_opening_stock_is_zero_not_periodic(self, solved):
        """The W1 row must be written against nothing, not against inv[c,52].

        Under a periodic boundary the farm can open the year holding stock it has not grown.
        Detect it directly: week-1 inventory cannot exceed week-1 inflow.
        """
        r, p = solved
        H = _weekly_sellable_inflow(r, p["total_land"], p["sell_through_fraction"])
        for c, crop in enumerate(r["crops"]):
            assert r["inventory"][c, 1] <= H[c, 1] + TOL, (
                f"{crop['name']} holds {r['inventory'][c, 1]:,.1f} lb at the end of W1 but "
                f"only harvested {H[c, 1]:,.1f} lb — the year opened with free stock, which "
                "means the boundary is periodic rather than zero (SPEC_v3 §3.0a)"
            )

    def test_inventory_never_negative(self, solved):
        r, _ = solved
        for c, crop in enumerate(r["crops"]):
            worst = float(r["inventory"][c, 1:].min())
            assert worst > -TOL, f"{crop['name']} holds {worst:,.4f} lb — negative inventory"

    def test_annual_conservation(self, solved):
        """Everything harvested is sold, wasted, or still held at week 52."""
        r, p = solved
        H = _weekly_sellable_inflow(r, p["total_land"], p["sell_through_fraction"])
        for c, crop in enumerate(r["crops"]):
            grown = H[c, 1:].sum()
            accounted = (float(r["v"][c, :, 1:].sum()) + float(r["waste"][c, 1:].sum())
                         + r["inventory"][c, W])
            assert abs(grown - accounted) < max(1e-3, 1e-7 * max(1.0, grown)), (
                f"{crop['name']}: grew {grown:,.2f} lb sellable but accounted for "
                f"{accounted:,.2f} — pounds appeared or vanished"
            )

    def test_nothing_is_sold_before_it_is_harvested(self, solved):
        r, p = solved
        H = _weekly_sellable_inflow(r, p["total_land"], p["sell_through_fraction"])
        for c, crop in enumerate(r["crops"]):
            harvests = [w for w in range(1, W + 1) if H[c, w] > 1e-9]
            sales = [w for w in range(1, W + 1) if r["v"][c, :, w].sum() > 1e-6]
            if not sales:
                continue
            assert harvests, f"{crop['name']} sells but never harvests"
            assert min(sales) >= min(harvests), (
                f"{crop['name']} sells in W{min(sales)} but first harvests in "
                f"W{min(harvests)} — revenue is booking before the cost that produced it"
            )


class TestStorageShrinkCostsSomething:
    """SPEC_v3 §3.4 / decision D3. Holding produce has to cost something before honest shelf
    lives can be entered — otherwise a long-keeping crop is pure upside in the objective and the
    optimiser hoards for free. This is the prerequisite the audit's Phase B waits on.

    Ships at 0.0, so every baseline is unmoved; these tests turn it on deliberately.
    """

    def _held_farm(self, full_params, loss):
        # Buyer opens ten weeks after harvest, so the plan MUST carry stock to sell at all —
        # which is the only condition under which shrink can show up.
        p = _one_crop_farm(full_params, ("03-01", "04-26"), "W24-W40",
                           shelf_life=8, min_acreage=5.0)
        p["crops"][0]["sell_through_fraction"] = 1.0
        p["sell_through_fraction"] = 1.0
        p["storage_loss_frac_per_week"] = loss
        return p

    def test_shrink_reconciles_to_the_pound(self, full_params):
        """The decayed balance is still an equality — rebuilt from x and v, not read back."""
        p = self._held_farm(full_params, 0.05)
        r = _solve(p, harvest_storage_cap=1e9, cash_constraint_enabled=False)
        H = _weekly_sellable_inflow(r, p["total_land"], 1.0)
        inv, waste, v = r["inventory"], r["waste"], r["v"]
        keep = 1.0 - _loss_of(r, p, 0)   # not a literal: one place to change, not two
        prev = 0.0
        for w in range(1, W + 1):
            expected = keep * prev + H[0, w] - float(v[0, :, w].sum()) - waste[0, w]
            assert abs(inv[0, w] - expected) < max(TOL, 1e-6 * max(1.0, abs(expected))), (
                f"W{w}: decayed balance off by {inv[0, w] - expected:,.6f} lb"
            )
            prev = inv[0, w]

    def test_shrink_costs_product_and_money(self, full_params):
        """More shrink, same plan shape: less product survives to the buyer, so less money."""
        none = _solve(self._held_farm(full_params, 0.0),
                      harvest_storage_cap=1e9, cash_constraint_enabled=False)
        heavy = _solve(self._held_farm(full_params, 0.08),
                       harvest_storage_cap=1e9, cash_constraint_enabled=False)
        sold_none = float(none["v"][0, :, 1:].sum())
        sold_heavy = float(heavy["v"][0, :, 1:].sum())
        assert sold_none > 1e3, "control sold nothing — the comparison would be vacuous"
        assert sold_heavy < sold_none, (
            f"8%/wk shrink over a ten-week hold must destroy product: sold {sold_heavy:,.0f} lb "
            f"vs {sold_none:,.0f} lb with no shrink. If these are equal the decay coefficient is "
            f"not reaching the balance"
        )
        assert heavy["profit"] < none["profit"], "product lost in store must cost money"

    def test_shrink_is_visible_in_the_results(self, full_params):
        """Product destroyed by shrink must be reported, or the auditability guard goes blind
        exactly when the new mechanism starts destroying things.

        Before this was added: a fixture losing 424,529 lb (50.6% of harvest) to shrink reported
        `waste_by_crop.fraction == 0.0000`, and the results banner — which filters on > 0.5% —
        stayed hidden. That is the failure `waste_by_crop` was written to prevent, reintroduced
        by the mechanism that removes the pounds.
        """
        r = _solve(self._held_farm(full_params, 0.10),
                   harvest_storage_cap=1e9, cash_constraint_enabled=False)
        entry = r["waste_by_crop"]["ShelfTest"]
        assert entry["shrink_lbs"] > 1.0, (
            "a ten-week hold at 10%/wk destroys product; shrink_lbs must show it"
        )
        assert entry["lost_lbs"] == pytest.approx(entry["lbs"] + entry["shrink_lbs"], rel=1e-9)
        assert entry["lost_fraction"] > 0.005, (
            "lost_fraction is what the results banner filters on — below the threshold the "
            "grower is told nothing"
        )

    def test_shelf_life_is_measured_on_decayed_stock(self, full_params):
        """C4c bounds inventory by what arrived inside the window. With shrink, what is HELD is
        smaller than what arrived, so an undecayed bound leaves slack that can only be filled
        with product older than the shelf life — the one thing the row forbids.

        Measured before the fix: 7.4% of held stock overheld at 5%/wk, 21% at 15%/wk, booking
        revenue on pounds that should have been written off.
        """
        loss = 0.05
        p = self._held_farm(full_params, loss)
        r = _solve(p, harvest_storage_cap=1e9, cash_constraint_enabled=False)
        H = _weekly_sellable_inflow(r, p["total_land"], 1.0)
        L = 8
        worst = 0.0
        for w in range(1, W + 1):
            exact = sum((1.0 - loss) ** (w - t) * H[0, t]
                        for t in range(max(1, w - L + 2), w + 1))
            worst = max(worst, r["inventory"][0, w] - exact)
        assert worst < max(TOL, 1e-6 * 1e5), (
            f"held {worst:,.1f} lb more than the shrink-exact shelf-life bound allows — the row "
            f"is still measuring undecayed arrivals"
        )

    def test_a_crop_can_override_the_farm_default(self, full_params):
        """Shrink is per-crop in reality — garlic loses tenths of a percent a week, salad greens
        several percent — so the crop-level key must win over the farm default.

        Added because a mutation that ignored the override was caught only by the blob checksum:
        the path was live and untested, which is how the per-crop sell_through key stayed broken
        for months.
        """
        farm_only = self._held_farm(full_params, 0.0)          # farm default 0, no override
        overridden = self._held_farm(full_params, 0.0)         # farm default STILL 0 ...
        overridden["crops"][0]["storage_loss_frac_per_week"] = 0.08   # ... crop overrides it

        base = _solve(farm_only, harvest_storage_cap=1e9, cash_constraint_enabled=False)
        over = _solve(overridden, harvest_storage_cap=1e9, cash_constraint_enabled=False)
        assert float(base["v"][0, :, 1:].sum()) > 1e3, "control sold nothing — vacuous"
        assert over["profit"] < base["profit"], (
            "a crop-level storage_loss_frac_per_week must apply even when the farm default is 0 — "
            "if these match, the per-crop key is being ignored"
        )

    def test_shrink_makes_holding_strictly_worse_than_selling(self, full_params):
        """What the 1e-6 tie-break was standing in for. With a real holding cost, carrying stock
        is strictly dominated whenever selling now is possible — so the reported inventory series
        is determinate on its own merits rather than by an epsilon nudge."""
        p = self._held_farm(full_params, 0.10)
        p["crops"][0]["shelf_life_weeks"] = 8
        # Buyer open across the harvest weeks AND later: holding is a real choice here.
        p = {**p, "crops": [{**p["crops"][0]}]}
        r = _solve({**p, "crops": [{**p["crops"][0], "channels": {
            list(p["crops"][0]["channels"])[0]: {
                **list(p["crops"][0]["channels"].values())[0],
                "demand_ranges": [{"weeks": "W1-W52", "weekly_lbs": 1e9}],
            }}}]}, harvest_storage_cap=1e9, cash_constraint_enabled=False)
        assert float(r["v"][0, :, 1:].sum()) > 1e3, "nothing sold — vacuous"
        assert float(r["inventory"].max()) < 1e-6, (
            f"with 10%/wk shrink and a buyer available every week, holding stock destroys product "
            f"for no gain — the optimiser should hold nothing, but peak inventory is "
            f"{float(r['inventory'].max()):,.2f} lb"
        )


class TestStorageBindsOnRoomOccupancy:
    """C4b. The cap must see product that is SITTING there, not product that arrived."""

    def test_a_cap_above_weekly_inflow_still_binds_on_accumulated_stock(self, full_params):
        """The one test that a harvest-inflow cap cannot pass.

        Build a crop whose successions harvest in consecutive weeks and whose buyer is
        rate-limited, so stock ACCUMULATES: peak held ends up well above peak weekly inflow.
        Then set the cap between the two. A cap on inflow sees room to spare and leaves the
        plan alone; a cap on held stock bites.

        This replaced two weaker tests. One squeezed to half the peak — a squeeze an
        inflow-based cap fails too, so it proved nothing about WHICH quantity is capped. The
        other asserted the cap was respected on a plan using 0.44% of it, and passed with the
        storage row deleted outright. Both were caught by mutation; keep this one honest.
        """
        # The buyer's weekly ceiling is what forces accumulation, so it is the fixture's real
        # tuning knob. Re-tuned 30,000 -> 15,000 lb/wk on 2026-07-30, when W9 made marginal labour
        # cheaper in low-activity weeks, the plan shifted, and the ratio fell to 1.47x — just under
        # the 1.5x this test needs to tell a held-stock cap from an inflow cap. Measured across the
        # range at that point: 30,000 -> 1.47x, 22,000 -> 2.15x, 15,000 -> 2.46x, 10,000 -> 1.64x,
        # 6,000 -> 1.56x. 15,000 sits at the top of that curve rather than at the edge of the
        # threshold, so the next plan shift moves the ratio without invalidating the fixture.
        # LOWERING THE 1.5x THRESHOLD WOULD HAVE BEEN THE WRONG FIX: the gap between held and
        # inflow IS the discriminating power, so shrinking it to accommodate a plan change trades
        # away the only thing the test proves.
        p = _one_crop_farm(full_params, harvest_season=("03-01", "05-24"),
                           demand_season="W01-W52", shelf_life=8, weekly_lbs=15_000)
        loose = _solve(p, harvest_storage_cap=1e9)
        crop = loose["crops"][0]
        inflow = _weekly_sellable_inflow(loose, p["total_land"], 1.0)[0]
        peak_inflow = float((inflow * crop["crop_size_m3_per_lb"]).max())
        peak_held = max(_held_m3_weekly(loose))
        assert peak_held > peak_inflow * 1.5, (
            f"fixture does not accumulate: peak held {peak_held:,.1f} m3 vs peak weekly "
            f"inflow {peak_inflow:,.1f} m3. It cannot distinguish the two formulations."
        )
        cap = (peak_inflow + peak_held) / 2
        tight = _solve(p, harvest_storage_cap=cap)
        assert max(_held_m3_weekly(tight)) <= cap * 1.0001, (
            f"held {max(_held_m3_weekly(tight)):,.1f} m3 against a {cap:,.1f} m3 cap"
        )
        assert tight["profit"] < loose["profit"] - 1.0, (
            f"a {cap:,.0f} m3 cap left profit unchanged ({tight['profit']:,.0f} vs "
            f"{loose['profit']:,.0f}), yet the plan holds {peak_held:,.0f} m3 at peak. The "
            f"storage row is counting weekly inflow ({peak_inflow:,.0f} m3), not held stock."
        )

    def test_solver_reports_the_peak_it_enforced(self, solved):
        """`storage_peak_m3` is what a grower sizes a building from, so it must be the
        constraint's own number rather than anything re-derived downstream.

        C4b measures everything IN THE ROOM during the week — opening stock plus that week's
        harvest — because field heat has to come off produce whether it ships that week or not.
        Rebuilt here from x and the calendar, independently of the array the solver returned.
        """
        r, p = solved
        H = _weekly_sellable_inflow(r, p["total_land"], p["sell_through_fraction"])
        crops = r["crops"]
        room = [
            sum(crops[c]["crop_size_m3_per_lb"]
                * (H[c, w] + (r["inventory"][c, w - 1] if w > 1 else 0.0))
                for c in range(len(crops))
                if crops[c].get("cold_storage", True))
            for w in range(1, W + 1)
        ]
        assert r["storage_peak_m3"] == pytest.approx(max(room), rel=1e-9)
        assert max(room) > max(_held_m3_weekly(r)), (
            "the room measure must exceed held-only stock, or same-week harvest is not being "
            "counted and the reported peak is back to being a lower bound"
        )


class TestShelfLife:
    """C4c. Guards the construction SPEC_v3 originally got wrong (§3.0b)."""

    def test_bound_holds_on_the_real_plan(self, solved):
        r, p = solved
        H = _weekly_sellable_inflow(r, p["total_land"], p["sell_through_fraction"])
        for c, crop in enumerate(r["crops"]):
            L = max(1, min(W, int(crop.get("shelf_life_weeks",
                                           crop.get("sales_spread_weeks", 1)) or 1)))
            if L > W:
                continue
            for w in range(1, W + 1):
                # w-L+2, matching the STRICT reading: L counts selling weeks INCLUDING the
                # harvest week, so only L-1 of them are storage weeks. Using w-L+1 here (the
                # pre-B.3 window) makes this assertion pass under both readings — strictly
                # wider than the real bound — so it could no longer detect a revert. Found
                # inert by review, not by failing.
                window = H[c, max(1, w - L + 2):w + 1].sum()
                assert r["inventory"][c, w] <= window + max(TOL, 1e-6 * max(1.0, window)), (
                    f"{crop['name']} W{w}: holds {r['inventory'][c, w]:,.1f} lb, more than the "
                    f"{L}-week rolling inflow of {window:,.1f} lb — product is older than its "
                    "shelf life"
                )

    def test_shelf_life_gates_a_late_buyer(self, full_params):
        """CONTROL + TREATMENT, because the obvious version of this test is vacuous.

        "Assert nothing sells" passes trivially if the crop never plants — and it did: the
        first draft of this test planted 0 acres and passed with the shelf-life row deleted
        from the solver. So solve it twice. A shelf life long enough to reach the buyer must
        SELL (proving the fixture works), and a one-week shelf life must sell NOTHING
        (proving the bound bites). Only the pair is evidence.
        """
        sells = _solve(_one_crop_farm(full_params, harvest_season=("03-01", "04-26"),
                                      demand_season="W20-W52", shelf_life=8),
                       harvest_storage_cap=1e9, cash_constraint_enabled=False)
        assert float(sells["v"][0, :, 1:].sum()) > 1e3, (
            "the CONTROL sold nothing — this fixture cannot detect anything, so the "
            "treatment below would pass vacuously"
        )
        blocked = _solve(_one_crop_farm(full_params, harvest_season=("03-01", "04-26"),
                                        demand_season="W40-W52", shelf_life=1),
                         harvest_storage_cap=1e9, cash_constraint_enabled=False)
        sold = float(blocked["v"][0, :, 1:].sum())
        assert sold < 1e-6, (
            f"sold {sold:,.0f} lb of a 1-week-shelf-life crop harvested around W14 into a "
            "buyer who only exists from W40 — the shelf-life bound is inert"
        )

    def test_shelf_life_binds_across_the_year_boundary(self, full_params):
        """The wrap case: harvest LATE, buyer EARLY.

        In calendar order the sale week precedes the harvest week, and this is precisely what
        SPEC_v3's doubled-104-week rows let through as a tautology (§3.0b). Under the zero
        anchor it must fail closed — a W42 harvest cannot reach a buyer who came and went in
        W1-W5, because that buyer belongs to the previous year.

        Control first, again: the same late crop selling to a buyer AFTER its harvest proves
        the fixture plants and sells.
        """
        sells = _solve(_one_crop_farm(full_params, harvest_season=("09-20", "11-15"),
                                      demand_season="W42-W52", shelf_life=8),
                       harvest_storage_cap=1e9, cash_constraint_enabled=False)
        assert float(sells["v"][0, :, 1:].sum()) > 1e3, (
            "the CONTROL sold nothing — a late-harvest crop must be able to sell to a late "
            "buyer, or this fixture proves nothing about the wrap"
        )
        wrapped = _solve(_one_crop_farm(full_params, harvest_season=("09-20", "11-15"),
                                        demand_season="W01-W05", shelf_life=8),
                         harvest_storage_cap=1e9, cash_constraint_enabled=False)
        sold = float(wrapped["v"][0, :, 1:].sum())
        assert sold < 1e-6, (
            f"sold {sold:,.0f} lb across the year boundary — a W42+ harvest reached a buyer "
            "who only exists in W1-W5. Either the boundary went periodic or the shelf-life "
            "row is vacuous on the wrap, which is the exact pair of defects SPEC_v3 §3.0 "
            "documents."
        )


class TestInventoryIsDeterminate:
    """Guards §3.0(a): a free inventory level makes the reported series meaningless."""

    def test_inventory_is_determinate(self, solved):
        """Perturb an objective coefficient by a hair. The PLAN may shift microscopically;
        the inventory series must not jump, because it should be pinned by the balance
        rather than floating on a solver tie-break."""
        base, p = solved
        nudged = copy.deepcopy(p)
        ch = nudged["crops"][0]["channels"]
        first = next(iter(ch))
        ch[first]["price_per_lb"] = ch[first]["price_per_lb"] * (1 + 1e-9)
        other = _solve(nudged)
        if abs(other["profit"] - base["profit"]) > 1.0:
            pytest.skip("the nudge moved the plan; this test needs an identical plan")
        delta = float(np.abs(base["inventory"] - other["inventory"]).max())
        scale = max(1.0, float(np.abs(base["inventory"]).max()))
        assert delta / scale < 1e-6, (
            f"inventory moved by {delta:,.2f} lb on a 1e-9 price nudge that left profit "
            "unchanged — the level is not determined by the constraints (a periodic boundary "
            "would do exactly this; SPEC_v3 §3.0a)"
        )

    def test_the_tie_break_does_not_buy_determinacy_with_money(self, solved):
        """The holding tie-break exists to make `inventory` unique, not to price storage.

        If it ever grows big enough to change which plan wins, it has stopped being a tie-break
        and become an un-disclosed cost. Bound it: removing it entirely must not move profit by
        more than a dollar.
        """
        r, _ = solved
        held_lb_weeks = float(r["inventory"][:, 1:].sum())
        tie_break_cost = held_lb_weeks * INVENTORY_TIE_BREAK_PER_LB_WEEK
        # A FRACTION of profit, not an absolute dollar bound: the dollar figure scales with
        # farm size and lb-weeks held, so a fixed $1 ceiling silently tightens as the model
        # grows. The usable band is narrow — the constant cannot shrink much below 1e-6
        # (HiGHS's dual-feasibility tolerance is 1e-7) — so when this fires the answer is not
        # to loosen the bound, it is to ship the real storage_loss_frac_per_week of §3.4.
        assert tie_break_cost < 1e-5 * abs(r["profit"]), (
            f"the holding tie-break is worth ${tie_break_cost:,.2f} against a "
            f"${r['profit']:,.0f} profit ({held_lb_weeks:,.0f} lb-weeks held). It is an "
            "undisclosed objective term, tolerable only while it rounds to nothing. "
            "B.3's longer shelf lives will push it here — that is the signal to implement "
            "SPEC_v3 §3.4's storage_loss_frac_per_week, not to raise this bound."
        )


def _assert_within_caps(r, tag=""):
    prefix = f"[{tag}] " if tag else ""
    for name, series in r["capacity_series"].items():
        for w, (used, cap) in enumerate(zip(series["used"], series["cap"]), start=1):
            assert used <= cap * (1 + 1e-6) + 1e-6, (
                f"{prefix}{name} W{w}: used {used:,.2f} exceeds the cap {cap:,.2f} it was "
                "solved against"
            )


class TestCapacitySeriesIsTheConstraints:
    """SPEC_v3 §9 / audit N5-N6: what the client renders must be what the model enforced.

    Exporting these arrays is only worth anything if they are the constraints' own. Verified
    by mutation: inflating the water cap by 1.5x — which is roughly the error the client's
    hand-rolled version had, because it counted rain on fields as SUPPLY where C3 treats rain
    as a reduction in demand — passed every other test in this file.
    """

    def test_water_cap_is_the_row_C3_used(self, solved):
        from farm_v2.utils.water import compute_free_water
        r, p = solved
        expected = compute_free_water(
            p["rainfall_weekly_L_per_acre"],
            p.get("catchment_enabled", False),
            p.get("catchment_surface_area_m2", 0.0),
            p.get("catchment_efficiency", CATCHMENT_EFFICIENCY),
            p.get("well_enabled", False),
            p.get("well_weekly_cap_L", 0.0),
        )
        got = r["capacity_series"]["water"]["cap"]
        # Since B7 the row's right-hand side is inflow PLUS the tank's opening level, so the
        # reported cap is free_water + (city water) + wstore[w-1]. It must therefore be at
        # least free_water in every week, and equal to it wherever the tank is empty — which
        # week 1 always is, because wstore is anchored at zero like the inventory balance.
        assert len(got) == len(expected)
        assert got[0] == pytest.approx(float(expected[0]), rel=1e-9), (
            "week 1 opens with an empty tank, so its cap must be exactly C3's inflow"
        )
        for w, (g, e) in enumerate(zip(got, expected), start=1):
            assert g >= float(e) - 1e-6, (
                f"week {w}: reported water cap {g:,.0f} is BELOW the inflow {float(e):,.0f} — "
                f"the published cap no longer contains the row's own right-hand side"
            )

    def test_labor_cap_is_the_row_C2_used(self, solved):
        from farm_v2.utils.labor import compute_labor_arrays
        r, p = solved
        arrays = compute_labor_arrays(
            p.get("year_round_employees", []), p.get("seasonal_employees", []), 52,
        )
        got = r["capacity_series"]["labor"]["cap"]
        assert got == pytest.approx([float(v) for v in arrays["labor_capacity"]], rel=1e-9), (
            "the reported labor capacity is not C2's right-hand side (field_time_pct dropped?)"
        )

    def test_every_series_respects_its_own_cap(self, solved):
        r, _ = solved
        _assert_within_caps(r)

    @pytest.mark.parametrize("tag,extra", [
        # The plain fixture has no well-off/city-on case and no labor flex, so it cannot see
        # the two rows that BUY headroom with a decision variable. Both were reported as
        # correct by every other test in this file while the cap was the bare RHS.
        ("city water alongside a well", dict(city_water_enabled=True,
                                             city_water_cost_per_L=0.0005)),
        ("city water, no well",         dict(city_water_enabled=True,
                                             city_water_cost_per_L=0.0005,
                                             well_enabled=False, well_weekly_cap_L=0.0)),
        ("overtime + hire",             dict(overtime_enabled=True,
                                             overtime_rate_multiplier=1.5,
                                             hire_enabled=True,
                                             max_hire_hrs_per_week=400.0,
                                             hire_wage_markup=0.2)),
    ])
    def test_caps_hold_when_a_row_buys_extra_headroom(self, full_params, tag, extra):
        """C2 and C3 are satisfied against capacity PLUS what the plan purchased, so `cap`
        has to be the RHS as solved. Reporting the bare standing capacity makes `used`
        exceed `cap` (water ranked #1 wrongly, labor shown over-subscribed in the very
        scenario that bought the hours) or makes it zero (well off + city on: every consumer
        guards `cap > 0` and the row vanishes from the bottleneck ranking entirely)."""
        r = _solve({**full_params, "sell_through_fraction": 0.85}, **extra)
        _assert_within_caps(r, tag)
        for name in ("labor", "water"):
            assert max(r["capacity_series"][name]["cap"]) > 0, (
                f"[{tag}] {name} cap is all zeros — consumers guard `cap > 0` and drop the "
                "row, so this resource can never be ranked as the bottleneck"
            )


class TestWasteIsVisible:
    """§3.5: deleting C7 makes overproduction legal, so it has to be reported.

    The first version of this class was INERT and a mutation proved it: hardcoding
    waste_by_crop[...]["lbs"] = 0.0 in the solver left every test here green, because waste
    is exactly 0.0 in all the ambient fixtures. Asserting `0 == approx(0)` fifteen times is
    the failure this file's own docstring warns about. It needs a plan that actually throws
    product away.
    """

    @pytest.fixture(scope="class")
    def wasteful(self, full_params):
        """A crop that MUST dump product.

        Rate-limiting the buyer is not enough on its own — the optimizer simply grows less
        (measured: 50,000 lb grown, 50,000 sold, zero waste). Overproduction has to be
        FORCED, and min_acreage_if_planted is what forces it: the crop cannot be planted at
        less than 10 acres, 10 acres yields far more than a 1-week shelf life can push
        through a 5,000 lb/week buyer, and the price is high enough that planting-and-dumping
        still beats not planting. This is the B1 case from SPEC_v3 §10 test 2.
        """
        p = _one_crop_farm(full_params, harvest_season=("03-01", "05-24"),
                           demand_season="W01-W52", shelf_life=1, weekly_lbs=5_000,
                           min_acreage=10.0)
        return _solve(p, harvest_storage_cap=1e9)

    def test_the_fixture_actually_wastes(self, wasteful):
        """Non-vacuity check, first. Everything below is meaningless without it."""
        entry = wasteful["waste_by_crop"]["ShelfTest"]
        assert entry["sellable_lbs"] > 1e3, "nothing was grown; the fixture proves nothing"
        assert entry["lbs"] > 1e3, (
            f"nothing was wasted ({entry['lbs']:,.1f} lb of {entry['sellable_lbs']:,.1f} "
            "sellable) — this fixture cannot detect a broken waste report"
        )
        assert 0.05 < entry["fraction"] < 0.95, (
            f"waste fraction {entry['fraction']:.1%} is at an extreme; a mid-range value is "
            "what makes the arithmetic below meaningful"
        )

    def test_waste_by_crop_matches_the_waste_variables(self, wasteful):
        for c, crop in enumerate(wasteful["crops"]):
            entry = wasteful["waste_by_crop"][crop["name"]]
            assert entry["lbs"] == pytest.approx(float(wasteful["waste"][c, 1:].sum()),
                                                 rel=1e-9, abs=1e-6)

    def test_reported_sellable_matches_an_independent_recount(self, wasteful, full_params):
        """`sellable_lbs` is computed inside the solver a second way (per-succession weekly
        lbs times the harvest-week count). Nothing checked the two agree until this."""
        H = _weekly_sellable_inflow(wasteful, full_params["total_land"], 1.0)
        for c, crop in enumerate(wasteful["crops"]):
            entry = wasteful["waste_by_crop"][crop["name"]]
            assert entry["sellable_lbs"] == pytest.approx(float(H[c, 1:].sum()), rel=1e-6)

    def test_fraction_is_lbs_over_sellable(self, wasteful):
        for entry in wasteful["waste_by_crop"].values():
            if entry["sellable_lbs"] > 1e-9:
                assert entry["fraction"] == pytest.approx(
                    entry["lbs"] / entry["sellable_lbs"], rel=1e-9)


class TestTruncatedSolveStatusMapping:
    """The load-bearing half of SPEC_v3 §7.1, with no solver involved.

    This is where "a truncated solve must not have its plan discarded" is actually pinned. It
    used to live only in the integration test below, which had to pick a wall-clock budget small
    enough to truncate and large enough to find something — a window that is a property of the
    machine, not the model, and that had been retuned twice before failing 8 runs out of 8 under
    load. Escalating the budget was worse: the regression presents as exactly the state that
    triggers escalation, so the loop climbs past it to `optimal` and the test SKIPS. A test that
    can launder the defect it guards is not a guard.

    The decision is a mapping from (scipy status, did a plan come back) to a reported status, so
    it is tested as one: exhaustive, deterministic, and identical on every machine.
    """

    @pytest.mark.parametrize("highs_status,has_solution,expected", [
        # The whole point: status 1 WITH a plan is a usable truncated solve, not a failure.
        (1, True,  "time_limit_feasible"),
        # Status 1 with nothing found stays a failure — the caller gets profit=None and no plan.
        (1, False, "iteration_limit"),
        # A solution object on any other status must NOT be promoted to the truncated path;
        # `infeasible` in particular can carry an x that satisfies nothing.
        (0, True,  "optimal"),
        (0, False, "optimal"),
        (2, True,  "infeasible"),
        (2, False, "infeasible"),
        (3, True,  "unbounded"),
        (4, True,  "other"),
    ])
    def test_the_reported_status(self, highs_status, has_solution, expected):
        from farm_v2.solver import has_time_limited_incumbent, report_solve_status
        incumbent = has_time_limited_incumbent(highs_status, has_solution)
        assert report_solve_status(highs_status, incumbent) == expected

    def test_an_unknown_scipy_status_says_so_rather_than_guessing(self):
        from farm_v2.solver import has_time_limited_incumbent, report_solve_status
        assert report_solve_status(99, has_time_limited_incumbent(99, True)) == "unknown(99)"

    def test_only_status_1_carries_a_plan_forward(self):
        """The predicate that decides whether extraction runs at all, stated on its own.

        If this ever returns True for a status other than 1, the solver extracts numbers from a
        solution vector that satisfies no constraints and reports them as a plan.
        """
        from farm_v2.solver import has_time_limited_incumbent
        assert has_time_limited_incumbent(1, True)
        assert not any(has_time_limited_incumbent(s, True) for s in (0, 2, 3, 4, 99))
        assert not has_time_limited_incumbent(1, False)


class TestTimeLimitedSolveKeepsItsPlan:
    """SPEC_v3 §7.1, end to end. HiGHS stopping on the clock is not the same as finding nothing.

    B.2 made this reachable: the golden farm went from closing at the root in one
    branch-and-bound node to needing 41, so a farm bigger than the demo can plausibly hit the
    75s budget the client sets. The old code returned profit=None and discarded result.x,
    showing "no solution found" while a usable incumbent sat in the object.

    This is now an INTEGRATION smoke test, and it is allowed to skip: the mapping it used to be
    the only guard on is pinned deterministically in TestTruncatedSolveStatusMapping above. What
    it adds is that a real truncated solve carries a real plan through real extraction.
    """

    def test_a_time_limited_solve_returns_the_incumbent(self, full_params):
        # A budget small enough that HiGHS cannot prove optimality but will have something.
        #
        # Retuned twice on 2026-07-29: 0.05 -> 0.5 when B5/B6 grew the model, then 0.5 -> 0.1
        # when the days_to_maturity correction shrank it again and 0.5s started solving to
        # OPTIMALITY — at which point this test skipped every run and quietly stopped covering
        # the incumbent path. Measured after that change: 0.02s finds nothing, 0.05s and 0.1s
        # truncate with a usable plan, 0.5s proves optimality.
        #
        # Original note — raised 0.05 -> 0.5 on 2026-07-29. When season windows became PLANTING windows this
        # fixture went from 74 successions to 152, and at 50ms HiGHS no longer reaches a FIRST
        # feasible solution at all — it returned status 1 with x=None, so the test failed
        # claiming the incumbent was discarded when there was no incumbent to discard.
        # Measured after the change: 0.05s -> no incumbent, 0.2s -> $101k, 0.5s -> $290k,
        # 1.0s -> $291k and still not proven. 0.5 sits inside the window that exercises the
        # rescue path.
        #
        # 2026-07-30, THIRD RETUNE — and the constant is gone, because the constant was never the
        # problem. The budget is WALL CLOCK, so the window it has to land in is a property of the
        # machine and its load: under load the 0.1s constant failed 8 runs out of 8 on an
        # unmodified tree, which reads exactly like a regression and cost a real diagnosis to rule
        # out. Escalating the budget was tried and was WORSE — a genuine regression presents as
        # `iteration_limit` with no plan, which is precisely the state that triggers escalation, so
        # the loop climbs past it, lands on `optimal`, and skips. It laundered the defect.
        #
        # So the mapping moved OUT of this test, to TestTruncatedSolveStatusMapping, where it needs
        # no solver and cannot race. What is left here is a smoke test over real extraction, and it
        # is allowed to skip on a machine that lands outside the window — because skipping no
        # longer costs the guarantee.
        r = solve_farm_v2(**{**full_params, "sell_through_fraction": 0.85},
                          solver_time_limit=0.1)
        if r["status"] == "optimal":
            pytest.skip("solved to optimality inside the budget — nothing truncated to inspect")
        if r.get("profit") is None:
            pytest.skip(f"no incumbent inside the budget (status {r['status']!r}) — this machine "
                        f"is outside the truncation window; the status mapping is pinned in "
                        f"TestTruncatedSolveStatusMapping")
        assert r["status"] == "time_limit_feasible", (
            f"a truncated solve came back with a plan but reported {r['status']!r} — the "
            f"incumbent was thrown away"
        )
        assert r["profit"] is not None, "profit is None: the incumbent was discarded"
        assert r["gap_note"], "a non-proven plan must say so"
        # And it must be a real plan, not an empty shell.
        assert r["x"] is not None and float(sum(r["x"])) > 0
        _assert_within_caps(r, "time-limited")

    def test_an_optimal_solve_carries_no_gap_note(self, solved):
        r, _ = solved
        assert r["status"] == "optimal"
        assert r["gap_note"] is None, (
            "a proven-optimal plan must not warn about a time limit, or the warning stops "
            "meaning anything"
        )
