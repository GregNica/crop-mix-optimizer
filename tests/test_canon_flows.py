"""
Runs the data-canon FLOW guards under pytest.

tests/canon_invariant.cjs pins the write helpers. It did not catch the last violations, which
were in the flows that use them — a plan saved in Metric and reloaded in US silently
reinterpreted every number, a restored channel list divided packaging costs by 2.2046, and the
chatbot applied "80 acres" as 80 hectares. Six sites in this class have shipped.

A guard over the primitives does not cover the paths, so this drives the paths. Skips if node
is absent.
"""
import shutil
import subprocess
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "canon_flows.cjs"
NODE = shutil.which("node")


def _jsdom_available() -> bool:
    """These flows need jsdom to parse the app's innerHTML-built collections. Skip rather
    than fail for anyone who hasn't run `npm install` — CI installs it explicitly."""
    if NODE is None:
        return False
    probe = subprocess.run([NODE, "-e", "require.resolve('jsdom')"],
                           capture_output=True, cwd=str(REPO))
    return probe.returncode == 0


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
@pytest.mark.skipif(not HARNESS.exists(), reason="canon_flows.cjs missing")
@pytest.mark.skipif(not _jsdom_available(), reason="jsdom not installed (run: npm install)")
def test_canon_flows():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        capture_output=True, text=True, timeout=120, cwd=str(REPO),
    )
    assert proc.returncode == 0, (
        "a data-canon FLOW is broken — a saved plan, a restored collection, or an applied "
        "chatbot proposal is reinterpreting values in the wrong unit system:\n"
        + proc.stdout + proc.stderr
    )
