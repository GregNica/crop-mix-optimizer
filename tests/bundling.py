"""Bundle a Worker module with esbuild the way wrangler does, and probe it under Node.

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
