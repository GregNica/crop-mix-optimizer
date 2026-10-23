"""Admin % and task tags on roster rows (Batch L.4 — GROUP I2 / I2a), via the real adapter.

Admin % is the share of paid hours that is NOT task work; field capacity = (100 − admin)%.
A row with its Field tag off adds no field capacity, overtime or extra-head hours — but is still
paid in full (committed, W12). Post-harvest / Selling tags get demand in Batch 3 (Q4).
"""
import json

import pytest

from farm_v2.adapter import run_from_js
from tests.helpers import golden_payload


def _solve(edit=None):
    p = golden_payload()
    if edit:
        edit(p)
    out = json.loads(run_from_js(json.dumps(p)))
    assert out["status"] == "optimal", out.get("error", "")[:300]
    return out


@pytest.fixture
def golden(golden_out):
    return golden_out


def _role(out, name):
    return next(r for r in out["labor_by_role"] if r["position"] == name)


def test_admin_pct_is_the_share_that_is_not_task_work(golden):
    """Manager: 45 h at 20% admin → 36 field h; operators: 2 × 40 at 10% → 72. Catches admin
    applied AS the field share (9 h / 8 h) — the inverse-meaning trap of this rename."""
    assert _role(golden, "Farm Manager")["task_hours"][0] == pytest.approx(36.0)
    assert _role(golden, "Equipment Operator")["task_hours"][0] == pytest.approx(72.0)


def test_a_legacy_field_pct_payload_solves_identically(golden):
    """Pre-L.4 callers send field_time_pct (the inverse); same farm, same answer, to the cent."""
    def legacy(p):
        for e in p["employees"]:
            e["field_time_pct"] = 100 - e.pop("admin_pct")
    assert _solve(legacy)["profit"] == pytest.approx(golden["profit"], abs=0.005)


def test_a_row_with_the_field_tag_off_adds_no_field_capacity_but_is_still_paid(golden):
    def untag(p):
        next(e for e in p["employees"] if e["position"] == "Harvest Crew")["task_field"] = False
    out = _solve(untag)
    hc, hc0 = _role(out, "Harvest Crew"), _role(golden, "Harvest Crew")
    assert max(hc["task_hours"]) == 0.0, "an untagged row still adds field hours"
    assert hc["cost"] == hc0["cost"], "the crew is paid whether or not they do field work"
    assert "Harvest Crew" not in {r["position"] for r in out["overtime_by_role"]}, (
        "an untagged row still offers field overtime")
    assert out["fixed_cost_split"]["wages"] == pytest.approx(golden["fixed_cost_split"]["wages"])
    assert out["profit"] < golden["profit"], "losing 320 field h/wk in harvest season cost nothing"


def test_the_other_tags_change_nothing_yet(golden):
    """Q4: no demand for post-harvest / selling hours until Batch 3 — the tags must not move
    the plan (a claim the UI makes: 'used from Batch 3')."""
    def off(p):
        for e in p["employees"]:
            e["task_postharvest"] = e["task_selling"] = False
    assert _solve(off)["profit"] == pytest.approx(golden["profit"], abs=0.005)
