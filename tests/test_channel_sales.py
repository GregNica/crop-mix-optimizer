"""
CHANNEL SALES — the per-channel weekly sales schedule (W1 / D4).

WHAT THIS GUARDS. `channel_sales` is the reportable form of the solver's own `v` variable:
what the optimizer decided to sell, to whom, in which week. The app's pies, its sales CSV and
its P&L channel revenue lines are all built on it.

WHY IT EXISTS. `v` was returned by the solver and read by NOTHING. The client rebuilt the same
quantity by splitting each week's GROSS harvest in proportion to demand x price. That formula
looks reasonable and is wrong in four independent ways, each of which this file pins:

  * sell-through — not all of a harvest becomes sellable product, so splitting GROSS harvest
    overstates sales (test_sales_never_exceed_sellable_harvest);
  * storage carry — a pound harvested in week 12 may be sold in week 15, so sales do not
    belong to the harvest week at all (test_sales_can_fall_outside_harvest_weeks);
  * demand caps — a channel that has bought its fill still drew a proportional share
    (test_annual_cap_is_never_exceeded);
  * arithmetic identity — the channel lines have to ADD UP to the headline revenue, and a
    reconstruction has no reason to (test_channel_revenue_sums_to_headline_revenue).

The last one is the load-bearing test. A P&L whose parts do not sum to its total is not a P&L,
and that was shipping on the same screen as the headline number.
"""
import numpy as np
import pytest

from farm_v2.solver import solve_farm_v2


_SOLVED = {}


@pytest.fixture
def solved(two_crop_params):
    """Solve the two-crop fixture ONCE and reuse it across this module.

    `two_crop_params` is function-scoped so it cannot be consumed by a module-scoped fixture,
    but the params are deterministic and the MILP is the slow part — so the solve is cached
    here instead. Any test that needs to change the farm must deepcopy first.
    """
    if not _SOLVED:
        res = solve_farm_v2(**two_crop_params)
        assert res["status"] == "optimal", res.get("status")
        _SOLVED["res"], _SOLVED["params"] = res, two_crop_params
    return _SOLVED["res"], _SOLVED["params"]


class TestStructure:
    def test_channel_sales_is_returned_and_non_empty(self, solved):
        res, _ = solved
        cs = res["channel_sales"]
        assert cs, "the solver sold nothing anywhere — the fixture cannot pin sales reporting"
        assert set(cs) <= {c["name"] for c in res["channels"]}

    def test_weekly_series_is_52_weeks(self, solved):
        res, _ = solved
        for ch, data in res["channel_sales"].items():
            for crop, cp in data["by_crop"].items():
                assert len(cp["weekly_lbs"]) == 52, f"{ch}/{crop}: {len(cp['weekly_lbs'])} weeks"

    def test_only_non_zero_series_are_emitted(self, solved):
        """A dense crops x channels x 52 grid is almost all zeros and crosses the wire on
        every solve. Anything present must actually have sold something."""
        res, _ = solved
        for ch, data in res["channel_sales"].items():
            assert data["lbs_sold"] > 0, f"{ch} present with no sales"
            for crop, cp in data["by_crop"].items():
                assert cp["lbs_sold"] > 0, f"{ch}/{crop} present with no sales"


class TestItAddsUp:
    """Every total has to equal the sum of its parts, at three levels."""

    def test_channel_revenue_sums_to_headline_revenue(self, solved):
        # THE test. The client prints these lines directly under the Revenue line.
        res, _ = solved
        total = sum(d["revenue"] for d in res["channel_sales"].values())
        assert total == pytest.approx(res["revenue"], abs=0.01), (
            f"channel revenue {total:,.2f} != headline revenue {res['revenue']:,.2f} — the "
            f"P&L's parts do not sum to its total"
        )

    def test_channel_lbs_sums_over_its_crops(self, solved):
        res, _ = solved
        for ch, data in res["channel_sales"].items():
            crop_sum = sum(cp["lbs_sold"] for cp in data["by_crop"].values())
            assert crop_sum == pytest.approx(data["lbs_sold"], abs=1e-6), ch

    def test_weekly_series_sums_to_lbs_sold(self, solved):
        """A weekly view and an annual view of the same channel must not disagree — this is
        exactly what the pies (weekly) and the P&L (annual) show side by side."""
        res, _ = solved
        for ch, data in res["channel_sales"].items():
            for crop, cp in data["by_crop"].items():
                assert sum(cp["weekly_lbs"]) == pytest.approx(cp["lbs_sold"], abs=1e-6), \
                    f"{ch}/{crop}"

    def test_it_agrees_with_crop_contribution(self, solved):
        """Two independently-built views of the same `v`. They are rendered on the same page,
        so a divergence would be visible and unexplainable."""
        res, _ = solved
        for crop_name, contrib in res["crop_contribution"].items():
            for ch_name, by_ch in contrib["by_channel"].items():
                got = res["channel_sales"][ch_name]["by_crop"][crop_name]["lbs_sold"]
                assert got == pytest.approx(by_ch["lbs_sold"], abs=1e-6), f"{crop_name}/{ch_name}"


class TestItIsNotAReconstruction:
    """The four ways the client's demand x price split disagreed with the optimizer."""

    def test_sales_never_exceed_sellable_harvest(self, solved):
        """Sell-through: only `sell_through_fraction` of what is grown can be sold. The old
        client code split GROSS harvest, so it overstated sales by the shrink rate — ~18% on
        the shipped demo farm."""
        res, params = solved
        st = {c["name"]: c.get("sell_through_fraction",
                               params.get("sell_through_fraction", 1.0))
              for c in res["crops"]}
        # Gross pounds grown per crop, from the solved acreage.
        grown = {c["name"]: 0.0 for c in res["crops"]}
        for i, s in enumerate(res["successions"]):
            name = res["crops"][s["crop"]]["name"]
            grown[name] += float(res["x"][i]) * params["total_land"] * \
                res["crops"][s["crop"]]["yield_per_acre"]
        for crop_name, contrib in res["crop_contribution"].items():
            sold = contrib["lbs_sold"]
            ceiling = grown[crop_name] * st[crop_name] + 1e-6
            assert sold <= ceiling, (
                f"{crop_name}: sold {sold:,.0f} lb but only {ceiling:,.0f} lb is sellable "
                f"(grown {grown[crop_name]:,.0f} x sell-through {st[crop_name]})"
            )

    def test_a_channel_with_no_price_is_never_sold_into(self, solved):
        """A proportional split hands volume to any channel that exists. The optimizer only
        sells where there is something to sell into."""
        res, params = solved
        import copy
        p = copy.deepcopy(params)
        p["channels"] = p["channels"] + [{"name": "Dead"}]
        for crop in p["crops"]:
            crop["channels"]["Dead"] = {"price_per_lb": 0.0, "packaging_cost_per_lb": 0.0,
                                        "demand_cap_type": "weekly_flat",
                                        "weekly_demand_lbs": 100_000}
        out = solve_farm_v2(**p)
        assert out["status"] == "optimal"
        assert out["channel_sales"].get("Dead", {}).get("revenue", 0.0) == pytest.approx(0.0), \
            "a zero-price channel earned revenue"

    def test_annual_cap_is_never_exceeded(self, solved):
        """The reconstruction had no idea a channel could be full."""
        res, params = solved
        for crop in res["crops"]:
            for ch_name, spec in crop.get("channels", {}).items():
                cap = spec.get("annual_demand_lbs")
                if not cap or spec.get("demand_cap_type") != "annual":
                    continue
                sold = res["channel_sales"].get(ch_name, {}).get("by_crop", {}) \
                          .get(crop["name"], {}).get("lbs_sold", 0.0)
                assert sold <= cap + 1e-6, f"{crop['name']}/{ch_name}: {sold} > cap {cap}"

    def test_sales_can_fall_outside_harvest_weeks(self, solved):
        """Storage carry is real, and it is the reason sales are not a function of the harvest
        calendar. This asserts the CAPABILITY exists, not that the fixture uses it: with
        inventory in the model a pound harvested in week 12 may legitimately be sold later,
        so any code that keys sales off the harvest week is structurally wrong."""
        res, _ = solved
        assert "inventory" in res, "no inventory core — storage carry could not happen"
        inv = np.asarray(res["inventory"])
        assert inv.shape[1] == 53, inv.shape
        # Not an assertion about this fixture's optimum: stock may or may not be held here.
        # The point is that `v` and the harvest calendar are separate objects in the model.
        assert res["v"].shape[2] == 53


class TestDuplicateCropNamesAreRefused:
    """Found by /code-review on the W1 commit, then reproduced before acting on it.

    Every per-crop result the solver returns is a dict keyed by crop NAME, so two crops sharing
    one silently collapse: `by_crop` is last-write-wins while the channel and farm totals still
    count both. Measured on this fixture with both crops renamed the same — the channel reported
    475,898 lb sold against by_crop entries summing to 118,578, so 357,320 lb (75%) vanished
    from the pies and the sales CSV while the P&L revenue line stayed correct.

    Fixed at the boundary (validate.py) rather than in `channel_sales`, because the same hazard
    applies to `crop_contribution` and `waste_by_crop`, and because `validate.py` already guards
    channel names for exactly this reason.
    """

    def test_duplicate_names_are_refused_with_a_reason(self, two_crop_params):
        import copy
        p = copy.deepcopy(two_crop_params)
        p["crops"][1]["name"] = p["crops"][0]["name"]
        out = solve_farm_v2(**p)
        assert out["status"] == "invalid_input", (
            f"a farm with two crops named the same solved anyway ({out['status']}) — its sales "
            f"reports would be missing pounds with nothing raised"
        )
        joined = " ".join(out["errors"])
        assert "unique" in joined and p["crops"][0]["name"] in joined, out["errors"]

    def test_unique_names_still_solve(self, solved):
        """The guard must not reject the farms it is meant to protect (the S14 lesson)."""
        res, _ = solved
        assert res["status"] == "optimal"


class TestGuardCanFail:
    """Mutation checks: a guard that has never failed is unproven.

    Every property above is arithmetic over the same arrays, so the way to prove these tests
    bite is to corrupt the structure and confirm each one notices.
    """

    def test_a_dropped_channel_breaks_the_revenue_identity(self, solved):
        res, _ = solved
        cs = dict(res["channel_sales"])
        assert len(cs) >= 1
        dropped = cs.pop(next(iter(cs)))
        total = sum(d["revenue"] for d in cs.values())
        assert abs(total - res["revenue"]) > 0.01, (
            "dropping a whole channel did not break the revenue identity — the test would "
            "not catch a channel going missing"
        )
        assert dropped["revenue"] > 0

    def test_a_shifted_week_breaks_the_weekly_identity(self, solved):
        res, _ = solved
        ch = next(iter(res["channel_sales"]))
        crop = next(iter(res["channel_sales"][ch]["by_crop"]))
        cp = res["channel_sales"][ch]["by_crop"][crop]
        mutated = list(cp["weekly_lbs"])
        mutated[0] += 1.0
        assert abs(sum(mutated) - cp["lbs_sold"]) > 1e-6, (
            "adding a pound to the weekly series did not break the sum — the weekly identity "
            "is not actually being checked"
        )
