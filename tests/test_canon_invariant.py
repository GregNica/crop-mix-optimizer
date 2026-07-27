"""
Runs the data-canon invariant guard (tests/canon_invariant.cjs) under pytest so CI enforces it.

Unit-bearing fields carry a display value AND a canonical shadow in data-canon, and
readCanonicalEl prefers the shadow. Code that writes .value without updating data-canon
therefore sends the solver a stale number while the screen shows the new one — no error,
nothing visibly wrong. Five separate sites have done this, twice with >50x errors.

Patching sites individually has not held. The .cjs drives the write helpers and asserts the
INVARIANT, so a sixth site fails here instead of in a harvest plan. Skips if node is absent.
"""
import shutil
import subprocess
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "canon_invariant.cjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
@pytest.mark.skipif(not HARNESS.exists(), reason="canon_invariant.cjs missing")
def test_canon_invariant():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        capture_output=True, text=True, timeout=120, cwd=str(REPO),
    )
    assert proc.returncode == 0, (
        "the data-canon invariant is broken — a unit-bearing field's displayed value and its "
        "canonical shadow disagree, which silently sends the solver the wrong number:\n"
        + proc.stdout + proc.stderr
    )
