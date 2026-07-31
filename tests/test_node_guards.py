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
import os
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
