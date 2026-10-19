"""R8 — overhead is a defined residual, and everything around it must agree with the model.

The ledger is OVERHEAD_COVERS / OVERHEAD_EXCLUDES in farm_v2/solver.py. Two ends are held here:

  * the MODEL end: every cost line the solver actually charges is claimed by an EXCLUDES entry —
    so a cost line added without telling the grower to take it out of overhead fails;
  * the PROSE end: the overhead field's tooltip and the assistant's description put each entry's
    words on its own side of "EXCLUDES" and NOT on the other, so a half-finished move (insurance
    added to the exclusions but still listed as covered) fails too. The tooltip had already
    dropped channel selling costs; the description had dropped rent, machinery and selling.

(The P&L label's half is in tests/cost_splits_client.cjs; the adapter forwarding in
tests/test_adapter_contract.py.)
"""
import html
import re

import pytest

from farm_v2 import solver
from tests.bundling import load_farm_fields
from tests.helpers import index_src


def _has(word, text):
    return re.search(rf"\b{re.escape(word)}", text) is not None   # word START: no "rent" in "current"


def _sides(text):
    covers, sep, excludes = text.lower().partition("excludes")
    assert sep, "the text no longer says EXCLUDES — it cannot state what overhead leaves out"
    return covers, excludes


def _tooltip():
    page = index_src()
    label = page[:page.index('<input type="number" id="overhead_pct"')].rsplit("<label>", 1)[1]
    return html.unescape(re.search(r'data-tip="([^"]*)"', label).group(1))


def _description():
    return load_farm_fields()["form"]["overhead_pct"]["chat"]["description"]


def test_every_cost_line_the_solver_charges_is_excluded_from_overhead(solved_two_crop):
    r, _ = solved_two_crop
    charged = (set(r["fixed_cost_split"]) | set(r["variable_cost_split"]) | set(r["bought_capacity_split"])
               | {"fixed_selling", "interest"})
    claimed = {line for lines, _ in solver.OVERHEAD_EXCLUDES.values() for line in lines}
    assert charged - claimed == set(), (
        f"the solver charges {sorted(charged - claimed)} on its own line but the overhead ledger does "
        "not exclude it — a grower would be told nothing, and could pay for it twice")


@pytest.mark.parametrize("name,text", [("tooltip", _tooltip), ("assistant description", _description)])
def test_the_prose_puts_every_line_on_its_side_and_only_there(name, text):
    covers, excludes = _sides(text())
    wrong = []
    for key, (_, words) in solver.OVERHEAD_COVERS.items():
        if not all(_has(w, covers) for w in words) or any(_has(w, excludes) for w in words):
            wrong.append(f"{key} (should read as COVERED)")
    for key, (_, words) in solver.OVERHEAD_EXCLUDES.items():
        if not all(_has(w, excludes) for w in words) or any(_has(w, covers) for w in words):
            wrong.append(f"{key} (should read as EXCLUDED)")
    assert not wrong, f"the overhead {name} disagrees with the ledger: {wrong}"
