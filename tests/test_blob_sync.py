"""
Blob-sync guard — the browser runs an EMBEDDED copy of farm_v2/*.py inside the
`const FARM_V2_FILES = {...}` blob in public/index.html (written into the Pyodide
FS at boot). Editing a solver file on disk does NOT reach the app until that blob
is regenerated (`python3 scripts/sync_solver_blob.py`). So a solver fix can pass
this entire pytest suite — which exercises the DISK copy — and never ship.

This test fails the moment the two drift, closing that gap. Highest risk-reduction
per line in the repo (audit Part 7).
"""
import json
import re
import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INDEX = REPO / "public" / "index.html"
PREFIX = "const FARM_V2_FILES = "


def _embedded_blob() -> dict:
    """Parse the FARM_V2_FILES literal out of public/index.html."""
    for line in INDEX.read_text().splitlines():
        s = line.strip()
        if s.startswith(PREFIX):
            m = re.match(re.escape(PREFIX) + r"(.*);\s*$", s)
            assert m, "FARM_V2_FILES line found but not in the expected `const … = {…};` shape"
            return json.loads(m.group(1))
    pytest.fail(f"no line starting with {PREFIX!r} found in {INDEX}")


@pytest.mark.skipif(not INDEX.exists(), reason="public/index.html not present")
class TestBlobSync:
    def test_embedded_blob_matches_disk(self):
        blob = _embedded_blob()
        mismatches = []
        for key, embedded in blob.items():
            disk_path = REPO / key
            assert disk_path.exists(), f"embedded file {key!r} does not exist on disk"
            disk = disk_path.read_text()
            if disk != embedded:
                mismatches.append(
                    f"{key}: embed {len(embedded)}B vs disk {len(disk)}B"
                )
        assert not mismatches, (
            "Embedded FARM_V2_FILES blob has drifted from disk — the app runs stale "
            "solver code. Re-sync: `python3 scripts/sync_solver_blob.py`.\n  "
            + "\n  ".join(mismatches)
        )

    def test_blob_covers_all_solver_modules(self):
        """Every farm_v2 *.py that the solver imports should be embedded."""
        blob = _embedded_blob()
        required = {
            "farm_v2/solver.py",
            "farm_v2/validate.py",
            "farm_v2/utils/calendar.py",
            "farm_v2/utils/demand.py",
            "farm_v2/utils/labor.py",
            "farm_v2/utils/water.py",
        }
        missing = required - set(blob.keys())
        assert not missing, f"solver modules missing from the embedded blob: {sorted(missing)}"
