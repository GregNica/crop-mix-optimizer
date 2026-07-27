"""
Runs the data-import round-trip test (tests/import_roundtrip.cjs) under pytest, so the
template-writer <-> parser contract is covered by CI.

Every importer has two halves that must agree: a template written in the user's active units,
and a parser that converts back to canonical. They sit far apart in public/index.html and a
disagreement between them is invisible — the file is simply written in one unit and read as
another, silently rescaling a farm's whole history and, through it, the solver's prices,
yields and water. Two bugs of exactly that shape have already shipped, which is why this is
pinned rather than checked by hand.

The assertions live in the .cjs (the parsers are browser functions, run in a vm with DOM and
SheetJS stubs). Skips cleanly if `node` isn't on PATH.
"""
import shutil
import subprocess
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
HARNESS = REPO / "tests" / "import_roundtrip.cjs"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
@pytest.mark.skipif(not HARNESS.exists(), reason="import_roundtrip.cjs missing")
def test_import_roundtrip():
    proc = subprocess.run(
        [NODE, str(HARNESS)],
        capture_output=True, text=True, timeout=120, cwd=str(REPO),
    )
    assert proc.returncode == 0, (
        "data-import round-trip failed — a template writer and its parser disagree about "
        "units, or a template can no longer be parsed by the app that wrote it:\n"
        + proc.stdout + proc.stderr
    )
