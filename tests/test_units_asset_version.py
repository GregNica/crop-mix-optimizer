"""
Cache-buster guard for public/units.js.

index.html is one big file, so edits to it always reach the browser. units.js is the app's
only external script — without a versioned URL a browser will happily serve a cached copy
against fresh HTML, and a stale unit registry fails SILENTLY (fields and labels just stop
converting). The `?v=` token guards that, but a token nobody remembers to bump is worse than
none: the file now merely *looks* versioned.

So the token IS the content hash, and this test recomputes it. Change units.js without
updating the tag and CI fails with the exact value to paste in. Same idea as
test_blob_sync.py, which keeps the embedded solver blob honest.
"""
import hashlib
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INDEX = REPO / "public" / "index.html"
UNITS = REPO / "public" / "units.js"

TAG = re.compile(r'<script src="units\.js\?v=([0-9a-f]+)"></script>')


def expected_version() -> str:
    return hashlib.sha256(UNITS.read_bytes()).hexdigest()[:8]


@pytest.mark.skipif(not (INDEX.exists() and UNITS.exists()), reason="app files not present")
def test_units_cache_buster_matches_file_contents():
    m = TAG.search(INDEX.read_text())
    assert m, (
        'no <script src="units.js?v=..."> tag found in public/index.html — the cache-buster '
        "must stay on the units.js tag (see this file's docstring for why)."
    )
    want = expected_version()
    assert m.group(1) == want, (
        f"public/units.js changed but its cache-buster did not: tag says ?v={m.group(1)}, "
        f"contents hash to {want}. Browsers may serve a stale unit registry.\n"
        f'  Fix: set the tag to <script src="units.js?v={want}"></script>'
    )
