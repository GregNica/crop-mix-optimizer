"""Run the app's JavaScript under Node from pytest: the field registry, and Worker modules
bundled with esbuild the way wrangler does.

Kept OUT of tests/helpers.py, whose contract is pure functions: this shells out and skips.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from tests.helpers import REPO

NODE = shutil.which("node")
ESBUILD = REPO / "node_modules" / ".bin" / "esbuild"


def load_farm_fields():
    """public/fields.js's FARM_FIELDS, loaded through tests/page_scripts.cjs like every harness."""
    if NODE is None:
        pytest.skip("node not installed")
    code = ("const vm=require('vm');const sb={window:{},console};vm.createContext(sb);"
            "require('./tests/page_scripts.cjs').runPageScripts(sb);"
            "process.stdout.write(JSON.stringify(sb.FARM_FIELDS))")
    out = subprocess.run([NODE, "-e", code], cwd=REPO, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def bundle_and_probe(entry: str, probe_js: str):
    """Bundle `entry`, import it as `M` in an ESM probe, run `probe_js` (which must write JSON to
    stdout) and return the parsed result. The esbuild flags are stated here once."""
    if NODE is None or not ESBUILD.exists():
        pytest.skip("node/esbuild not installed (npm install)")
    with tempfile.TemporaryDirectory() as d:
        out = pathlib.Path(d) / "bundle.mjs"
        subprocess.run([str(ESBUILD), entry, "--bundle", "--format=esm", "--platform=neutral",
                        f"--outfile={out}", "--log-level=error"], cwd=REPO, check=True)
        res = subprocess.run([NODE, "--input-type=module", "-e",
                              f"import * as M from {json.dumps(out.as_uri())};\n{probe_js}"],
                             capture_output=True, text=True)
    assert res.returncode == 0, res.stderr[-1500:]
    return json.loads(res.stdout)
