"""The field registry (public/fields.js, E5b) against everything OUTSIDE the page.

tests/field_registry_client.cjs pins the registry to the rendered form. This pins the other three
readers, each of which used to keep its own list:

  * the Python adapter — every top-level key `run_from_js` reads is declared in `payload`, and
    every declared key is read. Found by PARSING adapter.py (ast), not by regex: a regex over its
    source matched keys of unrelated dicts (cp['revenue'], …) and reported 21 phantom keys.
  * the golden payload the real form builds — every key it sends is declared, and none of the
    keys declared `unsent` is actually sent (if one starts being sent, the `unsent` note is a lie).
  * the Worker — grounding.ts is BUNDLED with esbuild exactly as wrangler bundles it and imported
    under Node, so the check is on the code that ships, not on a reading of its source.
"""
import ast
import json
import shutil
import subprocess

import pytest

from tests.helpers import GOLDEN_PAYLOAD, REPO

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

READERS = {"_num", "_num_no_invent"}


@pytest.fixture(scope="module")
def registry():
    # Through tests/page_scripts.cjs, like every other harness, so the load contract is stated once.
    code = ("const vm=require('vm');const sb={window:{},console};vm.createContext(sb);"
            "require('./tests/page_scripts.cjs').runPageScripts(sb);"
            "process.stdout.write(JSON.stringify(sb.FARM_FIELDS))")
    out = subprocess.run([NODE, "-e", code], cwd=REPO, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _adapter_payload_keys():
    """Every literal top-level key run_from_js reads off the payload `p`."""
    keys = set()
    for n in ast.walk(ast.parse((REPO / "farm_v2" / "adapter.py").read_text())):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in READERS
                and n.args and isinstance(n.args[0], ast.Constant)):
            keys.add(n.args[0].value)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get"
              and isinstance(n.func.value, ast.Name) and n.func.value.id == "p"
              and n.args and isinstance(n.args[0], ast.Constant)):
            keys.add(n.args[0].value)
        elif (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "p"
              and isinstance(n.slice, ast.Constant)):
            keys.add(n.slice.value)
        elif (isinstance(n, ast.Compare) and isinstance(n.left, ast.Constant)
              and any(isinstance(o, ast.In) for o in n.ops)
              and isinstance(n.comparators[0], ast.Name) and n.comparators[0].id == "p"):
            keys.add(n.left.value)
    return keys


def test_the_parser_sees_the_adapter_at_all():
    """Guard the guard: if the adapter stops reading through `_num`/`p`, the set goes empty and
    both directions below would pass vacuously."""
    keys = _adapter_payload_keys()
    assert {"total_land", "crops", "channels", "employees", "harvest_storage_cap"} <= keys
    assert len(keys) >= 40


def test_every_key_the_adapter_reads_is_declared(registry):
    undeclared = _adapter_payload_keys() - set(registry["payload"])
    assert not undeclared, (
        f"run_from_js reads {sorted(undeclared)} but public/fields.js `payload` does not declare "
        "them — say which form fields they come from, or why nothing sends them (`unsent`)")


def test_every_declared_key_is_read_by_the_adapter(registry):
    unread = set(registry["payload"]) - _adapter_payload_keys()
    assert not unread, (
        f"public/fields.js declares payload keys {sorted(unread)} that run_from_js never reads — "
        "a declared input the solver never sees")


def test_the_form_sends_only_declared_keys_and_no_unsent_one(registry):
    sent = set(json.loads(GOLDEN_PAYLOAD.read_text()))
    assert not sent - set(registry["payload"]), f"the form sends undeclared keys {sorted(sent - set(registry['payload']))}"
    unsent = {k for k, v in registry["payload"].items() if "unsent" in v}
    assert unsent, "no `unsent` key declared — this check is inert"
    assert not unsent & sent, (
        f"{sorted(unsent & sent)} are declared `unsent` but the form now sends them — "
        "replace the `unsent` note with `from`")


@pytest.fixture(scope="module")
def bundled_grounding(tmp_path_factory):
    esbuild = REPO / "node_modules" / ".bin" / "esbuild"
    if not esbuild.exists():
        pytest.skip("esbuild not installed (npm install)")
    out = tmp_path_factory.mktemp("bundle") / "grounding.mjs"
    subprocess.run([str(esbuild), "worker/grounding.ts", "--bundle", "--format=esm",
                    "--platform=neutral", f"--outfile={out}", "--log-level=error"],
                   cwd=REPO, check=True)
    probe = (f"import * as G from {json.dumps(out.as_uri())};"
             "const tool=G.buildSetFormFieldsTool();"
             "process.stdout.write(JSON.stringify({form:G.CHATBOT_FIELDS,crop:G.CROP_DETAIL_FIELDS,"
             "toolProps:Object.keys(tool.function?.parameters?.properties||tool.parameters?.properties||{})}))")
    res = subprocess.run([NODE, "--input-type=module", "-e", probe], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr[-1500:]
    return json.loads(res.stdout)


def test_the_bundled_worker_offers_exactly_the_registrys_chat_fields(registry, bundled_grounding):
    """The Worker's allowlist (grounding.ts CHAT_ALLOWLIST) names exactly the fields fields.js
    describes, each described by fields.js — so neither can widen or shrink the assistant alone.
    ORDER is the allowlist's own (the field guide's curated order), so it is compared as given."""
    for section, name in (("form", "CHATBOT_FIELDS"), ("crop", "CROP_DETAIL_FIELDS")):
        described = {k: v["chat"] for k, v in registry[section].items() if "chat" in v}
        assert described, f"no chat fields in registry section {section} — inert"
        offered = bundled_grounding[section]
        assert sorted(f["id"] for f in offered) == sorted(described), (
            f"{name}: the Worker allowlist and fields.js `chat` blocks name different fields — "
            "exposing a field to the assistant takes BOTH (allowlist in grounding.ts = the review step)")
        for f in offered:
            assert {k: v for k, v in f.items() if k != "id"} == described[f["id"]], f"{name}: {f['id']} drifted"


def test_the_field_guide_keeps_its_curated_order(bundled_grounding):
    """E5b first derived these lists in FORM order and silently reordered the assistant's prompt
    (rent before sell-through; yield ninth). Pinned to the reviewed order."""
    assert [f["id"] for f in bundled_grounding["form"]][:3] == ["total_land", "sell_through_pct", "overhead_pct"]
    assert bundled_grounding["crop"][0]["id"] == "yield_per_acre"


def test_the_assistant_tool_schema_has_a_property_per_chat_field(registry, bundled_grounding):
    ids = {k for k, v in registry["form"].items() if "chat" in v}
    assert ids <= set(bundled_grounding["toolProps"]), (
        f"set_form_fields cannot propose {sorted(ids - set(bundled_grounding['toolProps']))}")


def test_every_chat_spec_is_well_formed(registry):
    """fields.js is plain JS, so TypeScript never checks it — a malformed `chat` block reaches the
    Worker unchecked. An `enum` with no options would crash validateFieldUpdates on the first
    proposal (`f.enum!.includes`); a number field with min > max would refuse every value."""
    bad = []
    for section in ("form", "crop"):
        for fid, f in registry[section].items():
            c = f.get("chat")
            if not c:
                continue
            if c.get("type") not in ("number", "enum", "boolean"):
                bad.append(f"{fid}: type {c.get('type')!r}")
            if not (isinstance(c.get("label"), str) and c["label"] and isinstance(c.get("description"), str)
                    and len(c["description"]) > 20):
                bad.append(f"{fid}: needs a label and a real description")
            if c.get("type") == "enum" and not (isinstance(c.get("enum"), list) and c["enum"]):
                bad.append(f"{fid}: enum without options")
            if "min" in c and "max" in c and c["min"] > c["max"]:
                bad.append(f"{fid}: min > max")
    assert not bad, bad
