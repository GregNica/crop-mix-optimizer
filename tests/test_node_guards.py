"""
Runs the node-side guards under pytest, because CI runs pytest and NOT `npm test`.

Two guards built on 2026-07-28 — "the demo stays derived from CROP_TEMPLATES" and "the golden
payload is not stale" — were wired into `npm test` only, so neither ran in CI and both were
being reported as protection they did not provide. A guard that does not run is worse than no
guard: it buys false confidence.

The four older harnesses each have their own ~40-line wrapper (test_canon_flows.py,
test_canon_invariant.py, test_import_roundtrip.py, test_units_js.py). This file covers the new
ones with one parametrised case rather than copying that boilerplate a fifth and sixth time.
"""
import json
import os
import re
import shutil
import subprocess
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

# (label, argv relative to the repo root, failure message)
GUARDS = [
    (
        "demo-derivation",
        ["tests/demo_derivation.cjs"],
        "the shipped demo no longer matches CROP_TEMPLATES + DEMO_OVERRIDES. If the change was "
        "intended, re-capture tests/golden/demo_form_snapshot.json AND re-pin the golden P&L in "
        "the same commit",
    ),
    (
        "channel-sales-client",
        ["tests/channel_sales_client.cjs"],
        "the client is no longer reading the solver's per-channel sales schedule (W1/D4). If "
        "computeWeeklySalesLbs starts deriving sales from harvest, prices or demand again, the "
        "pies, the sales CSV and the P&L channel lines stop reconciling to the headline revenue",
    ),
    (
        "demand-saturation-client",
        ["tests/demand_saturation_client.cjs"],
        "the client is no longer reading the solver's demand saturation (W6). If the constraint "
        "panel or the What-If ranking starts deriving saturation from gross harvest and the "
        "form's caps again, a crop that sells nothing into a channel will read as saturated "
        "beside a pie showing it selling nothing there",
    ),
    (
        "cost-splits-client",
        ["tests/cost_splits_client.cjs"],
        "the P&L exporter is no longer reading the solver's cost breakdowns (W4). If it goes "
        "back to naming flat per-component keys, the detail rows silently disappear — which is "
        "how twelve of thirteen of them came to be missing for the exporter's whole life — or a "
        "component charged to a total ends up with no row anywhere",
    ),
    (
        "escaping-client",
        ["tests/escaping_client.cjs"],
        "a user-typed crop, channel or labor name renders as LIVE MARKUP (E7). The app builds "
        "HTML by string interpolation, so an unescaped name becomes a DOM element — the class "
        "found in the CSV-error sink during /code-review. This drives every render surface with "
        "TWO payloads (text and attribute-breaking) because the text one alone reports clean on "
        "the form inputs, and also pins the mirror defect: escaping must not become visible to a "
        "grower whose crop is honestly called \"Tom's Beets & Co\"",
    ),
    (
        "csv-safety-client",
        ["tests/csv_safety_client.cjs"],
        "a CSV the app writes can be read as a FORMULA when it opens (X1). Excel and Sheets "
        "parse a cell starting with = + - or @; the P&L's subtotals once led with '=' and every "
        "total row broke. All five exporters go through downloadCSV(), which neutralises the "
        "lead with U+00A0 — but ONLY on non-numeric cells, because the amount column is full of "
        "legitimate negatives. This drives all five with hostile crop and channel names",
    ),
    (
        "golden-payload-staleness",
        ["scripts/capture_golden_payload.cjs", "--check"],
        "tests/golden/default_farm_payload.json pins a farm the app no longer ships. Run "
        "`node scripts/capture_golden_payload.cjs` and re-pin the P&L in the same commit",
    ),
    (
        "labor-ui-client",
        ["tests/labor_ui_client.cjs"],
        "the labor roster's money inputs regressed: either Count went back to hidden-but-billed "
        "(a field that multiplies the committed wage bill must be on screen for every row type) "
        "or a blank wage box is once again silently coerced to $0, erasing that role's payroll "
        "with nothing on screen",
    ),
    (
        "yield-client",
        ["tests/yield_client.cjs"],
        "paintYield regressed: either a hidden tab yields through a timer again (Chromium "
        "throttles it to one wake-up a minute, so a backgrounded Monte Carlo crawls) or a visible "
        "tab no longer waits for a frame (the spinner never paints before the solve blocks)",
    ),
    (
        "form-state-client",
        ["tests/form_state_client.cjs"],
        "a saved plan can lose a value silently again: either a save/load round-trip moves a "
        "setting (unit drift), a saved field the form no longer has is skipped without a report, "
        "a rename bypasses FORM_FIELD_RENAMES, or a collection input is never serialized",
    ),
    (
        "field-registry-client",
        ["tests/field_registry_client.cjs"],
        "public/fields.js and the form disagree: an input is rendered but not registered (or the "
        "reverse), a form field feeds no payload key (a dead input), or a view the page reads "
        "(units registries, BENCHMARK_DEFAULTS) is no longer built from the registry",
    ),
    (
        "blank-cost-client",
        ["tests/blank_cost_client.cjs"],
        "a blank fertilizer/fuel/machinery box reaches the solver as $0 again (My Farm Data mode "
        "blanks all three), or Monte Carlo swaps a $0 price for the benchmark in every draw",
    ),
]


def _jsdom_available() -> bool:
    if NODE is None:
        return False
    probe = subprocess.run([NODE, "-e", "require.resolve('jsdom')"],
                           capture_output=True, cwd=str(REPO))
    return probe.returncode == 0


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
@pytest.mark.skipif(not _jsdom_available() and not os.environ.get("CI"),
                    reason="jsdom not installed (run: npm install)")
@pytest.mark.parametrize("label,argv,why", GUARDS, ids=[g[0] for g in GUARDS])
def test_node_guard(label, argv, why):
    script = REPO / argv[0]
    if not script.exists():
        pytest.skip(f"{argv[0]} missing")
    proc = subprocess.run([NODE, *argv], capture_output=True, text=True,
                          timeout=180, cwd=str(REPO))
    assert proc.returncode == 0, why + ":\n" + proc.stdout + proc.stderr


# The four older harnesses run from their own wrappers (see the module docstring).
_OWN_WRAPPER = {"tests/units_selftest.cjs", "tests/import_roundtrip.cjs",
                "tests/canon_invariant.cjs", "tests/canon_flows.cjs"}


def test_npm_test_and_GUARDS_list_the_same_harnesses():
    """`npm test` and GUARDS are two hand-kept lists of the same harnesses, and a harness in only
    one of them runs in only that runner — the exact failure this file exists to stop. Every
    harness added on the batch-1 branch was added to both by hand; this makes forgetting one loud."""
    npm = set(re.findall(r"node (tests/\S+\.cjs)",
                         json.loads((REPO / "package.json").read_text())["scripts"]["test"]))
    guarded = {argv[0] for _, argv, _ in GUARDS if argv[0].startswith("tests/")}
    assert npm - _OWN_WRAPPER == guarded, (
        f"in `npm test` only: {sorted(npm - _OWN_WRAPPER - guarded)}; "
        f"in GUARDS only: {sorted(guarded - npm)}")
    assert _OWN_WRAPPER <= npm, f"a legacy harness left `npm test`: {sorted(_OWN_WRAPPER - npm)}"
