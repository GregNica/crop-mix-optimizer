"""W10 (Batch 2.4) — utilities are an ENTERED bill, charged as their own fixed line.

The grower's ruling: an entered bill beats a computed pump cost. The overhead ledger moved
utilities into its exclusions in the same commit (tests/test_overhead_ledger.py holds the prose),
so a grower is told to take the bill out of their overhead %.
"""
import copy
import json

import pytest

from farm_v2.adapter import run_from_js
from farm_v2.solver import solve_farm_v2
from tests.helpers import GOLDEN_PAYLOAD


def test_the_bill_is_charged_as_entered(two_crop_params):
    base = solve_farm_v2(**copy.deepcopy(two_crop_params))
    p = copy.deepcopy(two_crop_params)
    p["utilities_cost_per_yr"] = 7_800.0
    r = solve_farm_v2(**p)
    assert base["status"] == r["status"] == "optimal"
    assert r["fixed_cost_split"]["utilities"] == 7_800.0
    assert base["fixed_cost_split"]["utilities"] == 0.0, "utilities must default to $0 until the re-pin"
    assert r["fixed_cost"] - base["fixed_cost"] == pytest.approx(7_800.0, abs=1e-6)


def test_the_adapter_forwards_it():
    """Guardrail 10. (Null and bad-value refusal are in tests/test_r7_ownership.py's lists.)"""
    p = json.loads(GOLDEN_PAYLOAD.read_text())
    p["utilities_cost_per_yr"] = 4_000.0
    out = json.loads(run_from_js(json.dumps(p)))
    assert out["fixed_cost_split"]["utilities"] == pytest.approx(4_000.0)
