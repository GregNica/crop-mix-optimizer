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
            "farm_v2/adapter.py",
            "farm_v2/charts.py",
            "farm_v2/utils/calendar.py",
            "farm_v2/utils/demand.py",
            "farm_v2/utils/labor.py",
            "farm_v2/utils/water.py",
        }
        missing = required - set(blob.keys())
        assert not missing, f"solver modules missing from the embedded blob: {sorted(missing)}"

    def test_no_embedded_python_can_close_the_script_tag(self):
        """A `</script` in any embedded module would blank the page, invisibly to Python.

        The blob sits inside an inline <script>, and `json.dumps` does NOT escape `/` — so a
        `</script` in a docstring, a comment about the HTML embed, or a URL closes the tag early.
        The page dies; every Python test stays green. That asymmetry is exactly the backtick
        incident (a backtick inside a comment closed the old PYTHON_CODE template literal while
        the extractor kept returning valid Python), and E2 retired that guard on the correct but
        narrow ground that backticks are ordinary inside a double-quoted JS string.

        The hazard CLASS — embedded Python breaking out of its JS container — moved rather than
        died, so the guard is re-pointed at the class instead of the character. `sync_solver_blob`
        escapes `</` as `<\\/` when it writes, which closes this by construction; this asserts the
        rendered line, so a hand-edit or a future writer change cannot quietly reopen it.

        Fail-CLOSED: it checks the RAW line, not the parsed blob (the parse decodes `<\\/` back to
        `</`, which would make this pass no matter what shipped).
        """
        raw = next((l for l in INDEX.read_text().splitlines() if l.strip().startswith(PREFIX)),
                   None)
        assert raw is not None, "FARM_V2_FILES line not found"
        assert "</script" not in raw.lower(), (
            "an embedded farm_v2 module contains `</script`, which closes the inline <script> "
            "early and blanks the page. Re-run `python3 scripts/sync_solver_blob.py` (it escapes "
            "`</` as `<\\/`), or remove the sequence from the source."
        )
