#!/usr/bin/env python3
"""
Sync (or verify) the FARM_V2_FILES blob embedded in public/index.html against farm_v2/ on disk.

The browser runs an embedded copy of the solver, written into the Pyodide FS at boot.
Editing farm_v2/*.py on disk does NOT reach the app until that blob is regenerated —
so a solver fix can pass pytest and still never ship.

    python3 scripts/sync_solver_blob.py --check   # exit 1 on drift (use in CI)
    python3 scripts/sync_solver_blob.py           # rewrite the blob from disk
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
INDEX = REPO / "public" / "index.html"
PREFIX = "const FARM_V2_FILES = "


def find_blob(lines: list[str]) -> tuple[int, dict]:
    """Return (0-based line index, parsed blob) for the FARM_V2_FILES literal."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(PREFIX):
            m = re.match(re.escape(PREFIX) + r"(.*);\s*$", stripped)
            if not m:
                sys.exit(f"error: line {i+1} starts with {PREFIX!r} but does not match "
                         "the expected `const FARM_V2_FILES = {...};` shape.")
            return i, json.loads(m.group(1))
    sys.exit(f"error: no line starting with {PREFIX!r} found in {INDEX}")


def read_disk(keys: list[str]) -> dict[str, str]:
    out = {}
    for key in keys:
        p = REPO / key
        if not p.exists():
            sys.exit(f"error: embedded file {key!r} does not exist on disk at {p}")
        out[key] = p.read_text()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify only; exit 1 on drift (does not write)")
    args = ap.parse_args()

    lines = INDEX.read_text().splitlines(keepends=True)
    idx, blob = find_blob(lines)
    disk = read_disk(list(blob))

    drift = [k for k in blob if blob[k] != disk[k]]

    # Any farm_v2 module on disk that the blob doesn't carry is a silent gap.
    embedded = set(blob)
    on_disk = {str(p.relative_to(REPO)) for p in (REPO / "farm_v2").rglob("*.py")}
    missing = sorted(on_disk - embedded)

    for k in sorted(blob):
        status = "DRIFT" if k in drift else "ok"
        print(f"  {status:5}  {k}  (embed {len(blob[k]):,}B / disk {len(disk[k]):,}B)")
    if missing:
        print("\n  on disk but NOT embedded (the app will not have these):")
        for k in missing:
            print(f"    - {k}")

    if args.check:
        if drift or missing:
            print(f"\nFAIL: {len(drift)} file(s) drifted, {len(missing)} missing from the blob.")
            print("Run: python3 scripts/sync_solver_blob.py")
            return 1
        print("\nOK: embedded blob matches disk.")
        return 0

    if not drift and not missing:
        print("\nAlready in sync; nothing written.")
        return 0

    for k in missing:
        disk[k] = (REPO / k).read_text()
    new_blob = {k: disk[k] for k in sorted(disk)}
    # Escape every `</` as `<\/`. The blob lives inside an inline <script>, and json.dumps does
    # NOT escape `/` — so a `</script` anywhere in farm_v2/*.py (a docstring, a comment about the
    # HTML embed, a URL) would close the tag early and blank the page. `\/` is a legal JSON
    # escape that decodes to `/`, so json.loads round-trips it and the drift check is unaffected.
    #
    # This is the backtick hazard, relocated. E2 retired the "no backticks in PYTHON_CODE" guard
    # because the adapter stopped living in a JS template literal — correct for backticks, but
    # the CLASS is "embedded Python breaks out of its JS container", and that moved rather than
    # died. Closed by construction here, with a fail-closed backstop in tests/test_blob_sync.py.
    escaped = json.dumps(new_blob).replace("</", "<\\/")
    lines[idx] = f"{PREFIX}{escaped};\n"
    INDEX.write_text("".join(lines))
    print(f"\nRewrote blob: {len(drift)} updated, {len(missing)} added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
