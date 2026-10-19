"""
Cache-buster guard for the page's external scripts: public/fields.js and public/units.js.

index.html is one big file, so edits to it always reach the browser. These two are loaded by
<script src>, and without a versioned URL a browser will happily serve a cached copy against
fresh HTML — a stale unit registry fails SILENTLY (fields and labels just stop converting), and
since E5b units.js derives that registry from fields.js, a stale copy of EITHER desynchronises
them. The `?v=` token guards that, but a token nobody remembers to bump is worse than none: the
file merely *looks* versioned.

So the token IS the content hash, and this test recomputes it. Change a script without updating
its tag and CI fails with the exact value to paste in. Same idea as test_blob_sync.py, which
keeps the embedded solver blob honest.
"""
import hashlib
import re

import pytest

from tests.helpers import INDEX, REPO

SCRIPTS = ("fields.js", "units.js")


@pytest.mark.parametrize("name", SCRIPTS)
def test_cache_buster_matches_file_contents(name):
    script = REPO / "public" / name
    if not (INDEX.exists() and script.exists()):
        pytest.skip("app files not present")
    m = re.search(rf'<script src="{re.escape(name)}\?v=([0-9a-f]+)"></script>', INDEX.read_text())
    assert m, (f'no <script src="{name}?v=..."> tag found in public/index.html — the cache-buster '
               "must stay on the tag (see this file's docstring for why).")
    want = hashlib.sha256(script.read_bytes()).hexdigest()[:8]
    assert m.group(1) == want, (
        f"public/{name} changed but its cache-buster did not: tag says ?v={m.group(1)}, "
        f"contents hash to {want}. Browsers may serve a stale copy.\n"
        f'  Fix: set the tag to <script src="{name}?v={want}"></script>')


def test_fields_js_loads_before_units_js():
    """units.js throws at load without FARM_FIELDS, so the order is load-bearing."""
    if not INDEX.exists():
        pytest.skip("app files not present")
    html = INDEX.read_text()
    assert 0 <= html.index('src="fields.js') < html.index('src="units.js')
