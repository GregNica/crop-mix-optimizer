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

    def test_no_embedded_python_can_reach_the_html_tokenizer(self):
        """No raw `<` in the rendered blob line — the whole class, not one sequence.

        The blob sits inside an inline <script>, and `json.dumps` escapes neither `<` nor `/`.
        The obvious hazard is `</script`, which closes the element early and blanks the page
        invisibly to every Python test (the backtick incident's class, relocated by E2).

        But guarding `</script` alone is whack-a-mole, and a review proved it BOTH ways: an
        unterminated `<!--` in script data enters script-data-escaped, and a following `<script`
        + delimiter enters script-data-DOUBLE-escaped, where the element's own `</script>` no
        longer closes it and the rest of the document is swallowed — worse than the guarded case,
        containing no `</script` at all, and the two ingredients need not even be in the same
        module. Escaping only `</` also REGRESSED that case, because a raw `</script` is what
        exits the double-escaped state.

        So the writer escapes every `<` as `\\u003c` and this asserts the outcome: zero `<`.
        Total, and immune to whichever sequence the tokenizer cares about next.

        Fail-CLOSED: reads the RAW line, never the parsed blob — parsing decodes `\\u003c` back
        to `<`, so a parsed check would pass no matter what shipped.
        """
        raw = next((l for l in INDEX.read_text().splitlines() if l.strip().startswith(PREFIX)),
                   None)
        assert raw is not None, "FARM_V2_FILES line not found"
        assert "<" not in raw, (
            f"the rendered blob contains {raw.count('<')} raw '<' — embedded Python can reach "
            "the HTML tokenizer and break the page. Re-run `python3 scripts/sync_solver_blob.py`."
        )


class TestBlobWriter:
    """The WRITER, not the artifact.

    The escape shipped with no test of its own: no farm_v2 module contains `<` today, so
    deleting `.replace(...)` from the writer left the entire suite green. The artifact guard
    above is fail-closed on what happens to be checked in; this pins the mechanism, on input the
    repo does not contain and should survive if it ever does.
    """

    HOSTILE = {
        # Each line is a plausible docstring/comment for a module that documents this very embed.
        "farm_v2/a.py": '"""the blob sits in a <script> tag, closed by </script> --"""\n',
        "farm_v2/b.py": "s = '</SCRIPT>'; t = '<!--'; u = 'a</b'; v = '<script >'\n",
        "farm_v2/c.py": "p = 'C:\\\\path'; q = '\\\\</'; r = '\u2028\u2029\u4e2d'\n",
    }

    def _render(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_sync_blob", REPO / "scripts" / "sync_solver_blob.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mod.render_blob_line(self.HOSTILE)

    def test_the_writer_neutralises_every_angle_bracket(self):
        _mod, line = self._render()
        assert "<" not in line, "the writer let a raw '<' through"

    def test_the_writer_round_trips_byte_for_byte(self):
        """Neutralising the page must not corrupt the code — Pyodide imports these strings."""
        mod, line = self._render()
        decoded = json.loads(line[len(mod.PREFIX):].rstrip().rstrip(";"))
        assert decoded == self.HOSTILE, (
            "escaping changed the Python source. The browser would run different bytes than "
            "pytest does — the exact false-green the blob-sync guard exists to prevent."
        )

    def test_the_rendered_line_is_pure_ascii(self):
        """json.dumps' ensure_ascii already handles U+2028/U+2029, which are JS line
        terminators — this pins that we still rely on it rather than having turned it off."""
        _mod, line = self._render()
        assert line.isascii()
