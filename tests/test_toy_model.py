"""
The toy model's numbers must not drift from the app's.

`toy_models/farm_toy_v1_spine_storage.xlsx` exists to be an INDEPENDENT check on the app's
arithmetic — a grower opens it, changes an acre figure and verifies by hand what the solver
claims. That only works while its crop constants and its planting calendar are the app's.
Nothing about a spreadsheet fails loudly when a crop's m3/lb changes underneath it; it just
starts quietly teaching a farm that no longer exists.

So this pins two things:

  1. DRIFT — every constant baked into the workbook still equals the golden payload's, and the
     five plantings still have the harvest weeks the app's own generator gives them.
  2. THE FORMULAS SAY WHAT THEIR LABELS SAY — specifically that ROOM OCCUPANCY reads the stock
     carried IN plus this week's harvest, and never the stock carried OUT. That single
     substitution is the defect the real model shipped for months (a farm selling everything in
     its harvest week was reported as needing no cooler at all), it is the one thing this toy
     exists to teach, and it is invisible in a rendered spreadsheet — the cells look identical.

Regenerate with:  python3 toy_models/build_toy_v1.py
"""
import json
import re

import pytest

from tests.helpers import REPO

openpyxl = pytest.importorskip("openpyxl")

WORKBOOK = REPO / "toy_models" / "farm_toy_v1_spine_storage.xlsx"
TOY_CROPS = ("Spinach", "Kale", "Garlic")
PICKED = ["Spinach W10", "Spinach W34", "Kale W12", "Kale W32", "Garlic W47"]


@pytest.fixture(scope="module")
def model():
    if not WORKBOOK.exists():
        pytest.skip(f"{WORKBOOK.name} not built; run toy_models/build_toy_v1.py")
    return openpyxl.load_workbook(WORKBOOK)["Model"]


@pytest.fixture(scope="module")
def payload():
    return json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))


def _labelled_rows(ws):
    out = {}
    for row in range(1, ws.max_row + 1):
        v = ws.cell(row=row, column=1).value
        if isinstance(v, str):
            out.setdefault(v.strip(), []).append(row)
    return out


def _crop_blocks(ws):
    """{CROP: {row label: row number}} for each per-crop block."""
    blocks = {}
    for row in range(1, ws.max_row + 1):
        v = ws.cell(row=row, column=1).value
        if isinstance(v, str) and "—" in v and v.endswith("store"):
            seq = {}
            for rr in range(row + 1, row + 12):
                lv = ws.cell(row=rr, column=1).value
                if isinstance(lv, str):
                    seq[lv.strip()] = rr
            blocks[v.split(" ")[0]] = seq
    return blocks


# ---------------------------------------------------------------------------
# 1 — drift
# ---------------------------------------------------------------------------

def test_crop_constants_match_the_app(model, payload):
    """Yield, volume-per-lb and pool are the golden payload's, to the last digit."""
    crops = {c["name"]: c for c in payload["crops"] if c["name"] in TOY_CROPS}
    rows = _labelled_rows(model)
    for name, crop in crops.items():
        r = [x for x in rows[name] if model.cell(row=x, column=2).value == crop["yield_per_acre"]]
        assert r, f"{name}: no settings row carrying the app's yield_per_acre"
        r = r[0]
        assert model.cell(row=r, column=4).value == pytest.approx(
            crop["crop_size_m3_per_lb"], rel=0, abs=1e-15), f"{name}: m3/lb has drifted"
        want_pool = "Cold" if crop.get("cold_storage", True) else "Ambient"
        assert model.cell(row=r, column=5).value == want_pool, f"{name}: storage pool has drifted"


def test_farm_constants_match_the_app(model, payload):
    rows = _labelled_rows(model)
    caps = {
        "Cold store (cooler) capacity": payload["harvest_storage_cap"],
        "Ambient store (barn) capacity": payload["ambient_storage_cap"],
    }
    for label, want in caps.items():
        r = rows[label][0]
        assert model.cell(row=r, column=2).value == want, f"{label} has drifted from the payload"


def test_planting_calendar_matches_the_apps_generator(model, payload):
    """The harvest weeks printed beside each planting are the ones the app would generate."""
    from farm_v2.utils.calendar import generate_successions, harvest_weeks_of

    crops = [c for c in payload["crops"] if c["name"] in TOY_CROPS]
    gen = {s["name"]: s for s in generate_successions(crops, 2024)}
    rows = _labelled_rows(model)
    for name in PICKED:
        assert name in gen, f"{name} is no longer a succession the app generates"
        want = ", ".join("W%d" % w for w in harvest_weeks_of(gen[name], 52))
        r = rows[name][0]                      # first occurrence = the input table
        got = model.cell(row=r, column=4).value
        assert got == want, f"{name}: harvest weeks drifted — sheet says {got!r}, app says {want!r}"


# ---------------------------------------------------------------------------
# 2 — the formulas say what their labels say
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crop", ["SPINACH", "KALE", "GARLIC"])
def test_room_occupancy_measures_throughput_not_what_sleeps_there(model, crop):
    """ROOM = stock carried IN + this week's harvest. Never the stock carried OUT.

    Substituting carried-out is exactly the defect the app shipped: it reports ZERO storage
    for a farm that sells everything the week it picks, so the figure could only ever be a
    lower bound. The two formulas render identically in the sheet.
    """
    b = _crop_blocks(model)[crop]
    f = model.cell(row=b["ROOM OCCUPANCY"], column=4).value      # week 2
    assert f"D{b['Stock carried in']}" in f, f"{crop}: ROOM does not read stock carried in"
    assert f"D{b['Harvested this week']}" in f, f"{crop}: ROOM does not read this week's harvest"
    assert f"D{b['Stock carried out']}" not in f, (
        f"{crop}: ROOM reads stock carried OUT — this is the lower-bound defect, "
        f"and the sheet would teach it as correct")


@pytest.mark.parametrize("crop", ["SPINACH", "KALE", "GARLIC"])
def test_the_inventory_chain_actually_chains(model, crop):
    b = _crop_blocks(model)[crop]
    assert model.cell(row=b["Stock carried in"], column=4).value == f"=C{b['Stock carried out']}"
    assert model.cell(row=b["Available to sell"], column=4).value == (
        f"=D{b['Stock carried in']}-D{b['lost to shrink']}+D{b['Harvested this week']}")
    assert model.cell(row=b["Stock carried out"], column=4).value == (
        f"=D{b['Available to sell']}-D{b['Sold']}")


def test_each_pool_sums_its_own_crops_only(model):
    """The 'grouped on the wrong column' trap: a pool row that silently totals the wrong set."""
    b = _crop_blocks(model)
    rows = _labelled_rows(model)
    cold = model.cell(row=rows["COLD STORE"][0], column=4).value
    amb = model.cell(row=rows["AMBIENT STORE"][0], column=4).value
    sp, ka, ga = (str(b[c]["ROOM OCCUPANCY"]) for c in ("SPINACH", "KALE", "GARLIC"))
    assert sp in cold and ka in cold and ga not in cold, "cold pool is not Spinach + Kale"
    assert ga in amb and sp not in amb and ka not in amb, "ambient pool is not Garlic alone"


def test_no_formula_points_off_the_sheet(model):
    """A reference past the last row is a silently-zero cell, which reads as a real answer."""
    n = 0
    for row in model.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                n += 1
                for m in re.finditer(r"\$?[A-Z]{1,2}\$?(\d+)", c.value):
                    assert int(m.group(1)) <= model.max_row, f"{c.coordinate}: {c.value}"
    assert n > 1500, f"only {n} formulas — the sheet has gone static, which no edit should do"


# ---------------------------------------------------------------------------
# 3 — the layout itself (both defects the grower found on first open)
# ---------------------------------------------------------------------------

def test_freezing_does_not_eat_the_scrollable_window(model):
    """Freeze the label COLUMNS, never the rows.

    v1 froze at C26 to keep the week numbers visible, which pinned rows 1-25 — the entire input
    block — and left about five scrollable rows on a normal screen. Vertical scrolling looked
    broken while horizontal still worked, and it hid the 52-week calendar the grower was looking
    for, so one layout mistake read as two missing features.
    """
    fp = model.freeze_panes
    assert fp is not None, "columns A-B should stay pinned while scrolling right"
    row = int("".join(ch for ch in fp if ch.isdigit()))
    assert row == 1, (
        f"freeze_panes={fp} pins {row - 1} rows; freezing ANY row here re-creates the "
        f"dead-scroll defect. Repeat the week strip instead — see week_header().")


def test_week_numbers_are_repeated_at_every_band(model):
    """With no frozen rows, each band carries its own week strip or the grid is unreadable."""
    strips = [r for r in range(1, model.max_row + 1)
              if model.cell(row=r, column=1).value == "Week"
              and model.cell(row=r, column=3).value == 1
              and model.cell(row=r, column=54).value == 52]
    assert len(strips) >= 6, f"only {len(strips)} week strips; every band needs one"
    gaps = [b - a for a, b in zip(strips, strips[1:])]
    assert max(gaps) < 30, f"a {max(gaps)}-row gap between week strips — too far to read against"


def test_every_constraint_reads_as_an_inequality(model):
    """LHS row / '<=' row / limit row — the original Group 5 model's own layout.

    Copied from 'Model' rows 16-18 of the source workbook (Available Land / <= / 1). The grower
    wrote that sheet, so it is the one shape here that needs no explaining.
    """
    rows = _labelled_rows(model)
    for label in ("LAND in the ground", "COLD STORE", "AMBIENT STORE"):
        assert label in rows, f"{label} band is missing"
        top = rows[label][0]
        assert model.cell(row=top + 1, column=3).value == "<=", f"{label}: no '<=' row beneath it"
        limit = model.cell(row=top + 2, column=3).value
        assert isinstance(limit, str) and limit.startswith("="), (
            f"{label}: the limit row must REFERENCE the input cell, not restate its number — "
            f"got {limit!r}")


def test_land_band_measures_standing_acres_not_the_annual_sum(model):
    """Acres in the ground THAT WEEK.

    Summing the year's plantings instead is a real defect this project already shipped and
    measured (C15): with a 3-acre commitment and a 1-acre/week cap the solver satisfied an
    annual-sum floor with eighteen separate 1-acre plantings, peak standing acreage 6, and not
    one acre actually reserved. A commitment is a quantity of ground, not of activity.
    """
    rows = _labelled_rows(model)
    f = model.cell(row=rows["LAND in the ground"][0], column=4).value
    assert f.count("IF(") == 5, f"land row should test all five plantings, got {f!r}"
    assert 'D' in f and '<>""' in f, "land row should read the phase strip for that WEEK"


def test_readme_coordinates_point_at_what_they_claim():
    """Every cell the instructions name must hold the thing the sentence says it holds.

    This is the defect the grower hit on first read: the READ ME hard-coded "set Garlic's shrink
    (G17)", then a row was added to the input block, every crop settings row shifted by one, and
    G17 became KALE's shrink. The sheet confidently instructed the wrong crop. Same class as this
    project's totals-written-beside-their-parts rule — a reference has to be DERIVED, and the
    generator now builds these from the live row numbers.

    Cheap to assert and it fails the moment the layout moves again.
    """
    wb = openpyxl.load_workbook(WORKBOOK)
    rd, model = wb["READ ME"], wb["Model"]
    text = "\n".join(str(rd.cell(row=r, column=1).value or "") for r in range(1, rd.max_row + 1))

    claims = [
        (r"Set Garlic's 'Sell rate lb/wk' \(([A-Z]+\d+)\)", "Garlic", "Sell rate lb/wk"),
        (r"Set Garlic's 'Shrink %/wk' \(([A-Z]+\d+)\)",     "Garlic", "Shrink %/wk"),
    ]
    header_row = None
    for r in range(1, 40):
        if model.cell(row=r, column=1).value == "Crop" and model.cell(row=r, column=2).value == "Yield lb/acre":
            header_row = r
            break
    assert header_row, "could not find the crop settings header"
    cols = {model.cell(row=header_row, column=c).value: c for c in range(1, 12)}

    for pattern, crop, field in claims:
        m = re.search(pattern, text)
        assert m, f"the READ ME no longer names a cell for {crop} {field}"
        coord = m.group(1)
        cell = model[coord]
        assert model.cell(row=cell.row, column=1).value == crop, (
            f"READ ME says {coord} is {crop}'s {field}, but row {cell.row} is "
            f"{model.cell(row=cell.row, column=1).value!r}")
        assert cell.column == cols[field], (
            f"READ ME says {coord} is {field}, but that column is "
            f"{model.cell(row=header_row, column=cell.column).value!r}")

    m = re.search(r"acre cells \(([A-Z]+\d+):([A-Z]+\d+)\)", text)
    assert m, "the READ ME no longer names the acre input range"
    first, last = model[m.group(1)], model[m.group(2)]
    assert last.row - first.row + 1 == len(PICKED), "acre range does not cover all five plantings"
    for row in range(first.row, last.row + 1):
        assert model.cell(row=row, column=1).value in PICKED, (
            f"row {row} is not one of the five plantings — the acre range has drifted")


# ---------------------------------------------------------------------------
# 4 — the deep check: EVALUATE the sheet
# ---------------------------------------------------------------------------

def test_no_derived_value_is_frozen(model):
    """Every number is a formula, a declared input, or one of three known constants.

    The grower found `lb/harvest wk` shipped as five baked numbers sitting beside the live
    harvest rows they described: change sell-through and the real figures moved while the
    printed one did not. Same class as this project's totals-written-beside-their-parts rule,
    in a spreadsheet.

    A whitelist, not a spot fix — anything new that is neither computed nor typed by the
    grower fails here, including whatever the next layer adds.
    """
    week_rows = {r for r in range(1, model.max_row + 1)
                 if model.cell(row=r, column=1).value == "Week"}
    anchors = {r for r in range(1, model.max_row + 1)
               if str(model.cell(row=r, column=1).value).strip() == "Stock carried in"}
    frozen = []
    for row in model.iter_rows():
        for c in row:
            if not isinstance(c.value, (int, float)) or isinstance(c.value, bool):
                continue
            yellow = bool(c.fill and c.fill.fgColor and c.fill.fgColor.rgb
                          and "FFF2CC" in str(c.fill.fgColor.rgb))
            if yellow or c.row in week_rows or (c.row in anchors and c.column == 3):
                continue
            frozen.append(f"{c.coordinate}={c.value} "
                          f"(row {model.cell(row=c.row, column=1).value!r})")
    assert not frozen, (
        "frozen derived value(s) — make them formulas or mark them as inputs: "
        + "; ".join(frozen[:8]))


def test_the_sheet_actually_calculates_correctly():
    """Run toy_models/verify_toy_v1.py — it CALCULATES the workbook.

    Everything above reads formulas as text, and text can be well-formed and wrong. This shells
    out to the venv because `formulas` cannot be installed into the system interpreter pytest
    runs on (PEP 668), and because a check that silently skips is not a check. Same subprocess
    pattern E2 used to prove the adapter imports no matplotlib.

    Skips ONLY if the venv or the engine is genuinely absent, and says so loudly.
    """
    import subprocess

    venv = REPO / ".venv" / "bin" / "python"
    if not venv.exists():
        pytest.skip(f"{venv} missing — cannot evaluate the workbook")
    probe = subprocess.run([str(venv), "-c", "import formulas"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("`formulas` not installed in .venv — run: .venv/bin/pip install formulas")

    r = subprocess.run([str(venv), str(REPO / "toy_models" / "verify_toy_v1.py")],
                       capture_output=True, text=True, cwd=REPO, timeout=600)
    assert r.returncode == 0, (
        "the toy workbook does not calculate correctly:\n"
        + "\n".join(l for l in r.stdout.splitlines() if "FAIL" in l or "FAILURE" in l)
        + ("\n" + r.stderr[-2000:] if r.stderr.strip() else ""))
    assert "ALL CHECKS PASSED" in r.stdout
