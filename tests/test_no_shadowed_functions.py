"""
Shadowed-function guard for the one giant inline <script> in public/index.html.

Everything in that script shares ONE scope, so two `function foo()` declarations
silently collapse: declarations hoist, the LAST one wins, and the earlier one
becomes unreachable dead code. No parse error, no console warning, no failing
test — the call site just quietly starts calling a different function.

This is not hypothetical. The unit system's `labelFor(el)` (takes an element,
returns its <label>) was shadowed by the chatbot's later `labelFor(id)` (takes a
field id, returns a label string). `renderUnitLabels` therefore handed an <input>
to `rewriteLabelUnit`, which found no text node and returned silently — so the
US/Metric toggle converted every VALUE but never changed a single unit LABEL. It
shipped through a browser QA pass because the values, which is what you look at,
were right. Renamed to `labelElFor`; this test keeps the class of bug from
recurring as the file grows.
"""
import collections
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
INDEX = REPO / "public" / "index.html"

# Top-level function declarations only: no leading indentation, so nested/inner
# functions (legitimately scoped, may repeat) are not flagged.
DECL = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)


@pytest.mark.skipif(not INDEX.exists(), reason="public/index.html not present")
def test_no_duplicate_top_level_function_declarations():
    src = INDEX.read_text()
    lines = src.splitlines()

    seen = collections.defaultdict(list)
    for i, line in enumerate(lines, 1):
        m = DECL.match(line)
        if m:
            seen[m.group(1)].append(i)

    dupes = {name: at for name, at in seen.items() if len(at) > 1}
    assert not dupes, (
        "Two top-level `function` declarations share a name in public/index.html's "
        "single inline script scope. The later one silently wins and the earlier "
        "becomes dead code — every call site gets the wrong function, with no error. "
        "Rename one.\n  "
        + "\n  ".join(f"{name}: lines {at}" for name, at in sorted(dupes.items()))
    )
