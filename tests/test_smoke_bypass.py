"""The smoke-test gate bypass (worker/smoke.ts) opens ONLY with the flag AND localhost.

It is the one place the login gate can be skipped, so every combination is pinned against the
real module, bundled with esbuild the way wrangler bundles it — not against a reading of its
source. A bypass that opened on the flag alone would expose the app wherever the variable leaked;
one that opened on localhost alone would make every local `npm run dev` ungated.
"""
import json

from tests.bundling import bundle_and_probe
from tests.helpers import REPO

CASES = [
    # (SMOKE_TEST_BYPASS, url, expected)
    ("1", "http://localhost:8787/", True),
    ("1", "http://127.0.0.1:8787/index.html", True),
    ("1", "https://farm.example.com/", False),           # flag leaked to a deployed Worker
    ("1", "http://localhost.evil.com/", False),         # look-alike host
    (None, "http://localhost:8787/", False),             # plain `npm run dev`
    ("0", "http://localhost:8787/", False),
    ("true", "http://localhost:8787/", False),           # only exactly "1"
    ("", "http://localhost:8787/", False),
]


def test_the_bypass_opens_only_with_the_flag_and_localhost():
    got = bundle_and_probe("worker/smoke.ts",
        f"const cases = {json.dumps(CASES)};"
        "process.stdout.write(JSON.stringify(cases.map(([v, u]) => "
        "M.smokeBypassActive(v === null ? {} : { SMOKE_TEST_BYPASS: v }, new URL(u)))))")
    wrong = [(v, u, want) for (v, u, want), g in zip(CASES, got) if g != want]
    assert not wrong, f"bypass decided wrongly for: {wrong}"


def test_the_flag_is_never_configured_where_it_would_persist():
    """It must arrive on the command line only — never in a file a normal run reads."""
    # Wrangler 4 reads local vars from .dev.vars, .dev.vars.<env>, .env and .env.<env> as well as
    # its config — any of them would leave every plain `npm run dev` ungated on localhost.
    # package.json too: its "dev" script IS what every plain run executes, so a flag added there
    # ("wrangler dev --var SMOKE_TEST_BYPASS:1") would ungate every local run (/code-review max).
    candidates = [*REPO.glob(".dev.vars*"), *REPO.glob(".env*"), *REPO.glob("wrangler.*"), REPO / "package.json"]
    leaked = [p.name for p in candidates if p.is_file() and "SMOKE_TEST_BYPASS" in p.read_text(errors="ignore")]
    assert not leaked, f"SMOKE_TEST_BYPASS is set in {leaked}"
