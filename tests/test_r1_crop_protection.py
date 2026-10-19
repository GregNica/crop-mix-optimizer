"""R1 (Batch 2.3) — crop protection is a variable-cost category, charged per acre per planting.

Two things are checked against INDEPENDENT derivations from the solved plan, not against the
solver's own split (which is what the reported total is summed from, so an identity would be
vacuous): the AMOUNT (acres actually planted x the per-acre rate) and the TIMING (only in each
planting's grow weeks — when sprays and covers go on — so the cash floor sees it then).
"""
import copy

import numpy as np
import pytest

from farm_v2.solver import solve_farm_v2

RATE = 180.0   # $/acre per planting, on the first crop only


@pytest.fixture
def protected(two_crop_params):
    p = copy.deepcopy(two_crop_params)
    p["crops"][0]["crop_protection_cost_per_acre"] = RATE
    r = solve_farm_v2(**p)
    assert r["status"] == "optimal", r["status"]
    return p, r


def _planted_acres(p, r, crop_idx):
    x = np.asarray(r["x"])
    return sum(float(x[i]) * p["total_land"] for i, s in enumerate(r["successions"]) if s["crop"] == crop_idx)


def test_the_charge_is_acres_planted_times_the_rate(protected):
    p, r = protected
    acres = _planted_acres(p, r, 0)
    assert acres > 0, "the fixture plants none of the protected crop — the charge would be invisible"
    assert r["variable_cost_split"]["crop_protection"] == pytest.approx(acres * RATE, rel=1e-9)


def test_an_unprotected_farm_charges_nothing(solved_two_crop):
    r, _ = solved_two_crop
    assert r["variable_cost_split"]["crop_protection"] == 0.0


def test_the_charge_lands_in_grow_weeks_only(minimal_params):
    """Same ONE-crop farm with and without protection: the cash curves may differ only by charges
    made in the grow weeks of its plantings. One crop, because two crops gave HiGHS an equal-value
    reshuffle between plantings once the objective moved — the comparison needs the same plan, and
    asserts it rather than assuming it."""
    base = solve_farm_v2(**copy.deepcopy(minimal_params))
    p = copy.deepcopy(minimal_params)
    p["crops"][0]["crop_protection_cost_per_acre"] = RATE
    r = solve_farm_v2(**p)
    assert base["status"] == r["status"] == "optimal"
    assert np.allclose(np.asarray(base["x"]), np.asarray(r["x"])), "plans differ — the comparison below needs the same plan"
    x = np.asarray(r["x"])
    want = np.zeros(53)
    for i, s in enumerate(r["successions"]):
        if s["crop"] != 0 or x[i] <= 1e-9:
            continue
        grow = [w for w, ph in zip(s["weeks"], s["phases"]) if ph == 1] or list(s["weeks"])
        for w in grow:
            want[w] += x[i] * p["total_land"] * RATE / len(grow)
    drop = np.diff(np.concatenate(([0.0], np.asarray(base["weekly_cash_flow"][1:]) - np.asarray(r["weekly_cash_flow"][1:]))))
    assert np.allclose(drop, want[1:], atol=1e-6), "crop protection was charged outside its grow weeks"


@pytest.mark.parametrize("bad", [-2000.0, float("nan"), None, "250"])
def test_a_bad_rate_is_refused(two_crop_params, bad):
    p = copy.deepcopy(two_crop_params)
    p["crops"][0]["crop_protection_cost_per_acre"] = bad
    assert solve_farm_v2(**p)["status"] == "invalid_input"
