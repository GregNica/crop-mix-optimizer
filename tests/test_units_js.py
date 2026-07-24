"""
Runs the units.js node self-test as part of the pytest suite, so the client-side
unit-conversion core (metric/US toggle) is protected by CI the same way the Python
solver is. Skips cleanly if `node` isn't on PATH.

The actual assertions live in tests/units_selftest.cjs (pure conversion math +
registry sanity, loaded via a window-stub vm — the real browser code path).
"""
import shutil
import subprocess
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SELFTEST = REPO / "tests" / "units_selftest.cjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
@pytest.mark.skipif(not SELFTEST.exists(), reason="units_selftest.cjs missing")
def test_units_js_selftest():
    proc = subprocess.run(
        [NODE, str(SELFTEST)],
        capture_output=True, text=True, timeout=60, cwd=str(REPO),
    )
    assert proc.returncode == 0, (
        "units.js self-test failed (client-side unit conversion regression):\n"
        + proc.stdout + proc.stderr
    )
