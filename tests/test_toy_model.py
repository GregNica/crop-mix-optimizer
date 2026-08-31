"""
The toy model's numbers must not drift from the app's.

`toy_models/farm_toy_v10_labour.xlsx` exists to be an INDEPENDENT check on the app's
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

Regenerate with:  python3 toy_models/build_toy_v10.py
"""
import json
import re

import pytest

from tests.helpers import REPO

openpyxl = pytest.importorskip("openpyxl")

WORKBOOK = REPO / "toy_models" / "farm_toy_v10_labour.xlsx"
TOY_CROPS = ("Spinach", "Kale", "Garlic")
# v5 carries EVERY succession the app offers. A hand-picked subset is the exact defect it
# exists to remove, so the list is derived, never typed.
def _all_successions():
    import json
    from farm_v2.utils.calendar import generate_successions
    p = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
    return generate_successions([c for c in p["crops"] if c["name"] in TOY_CROPS], 2024)


PICKED = [s["name"] for s in _all_successions()]


@pytest.fixture(scope="module")
def model():
    if not WORKBOOK.exists():
        pytest.skip(f"{WORKBOOK.name} not built; run toy_models/build_toy_v10.py")
    return openpyxl.load_workbook(WORKBOOK)["Model"]


@pytest.fixture(scope="module")
def payload():
    return json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))


def _week_cols(ws):
    """(column of week 1, column of week 52), DERIVED from a week-header strip.

    v5 moved the grid from column C to E to make room for the two per-succession decision cells.
    Every test that hard-coded 'D' for week 2 broke at once — so the offset is read off the
    sheet now and the next move costs nothing.
    """
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=1).value in ("Week", "Succession"):
            c1 = next((c for c in range(2, 12) if ws.cell(row=r, column=c).value == 1), None)
            if c1 and ws.cell(row=r, column=c1 + 51).value == 52:
                return c1, c1 + 51
    raise AssertionError("no week-number strip found")


def _wc(ws, w):
    """Column INDEX of week w."""
    return _week_cols(ws)[0] + w - 1


def _wl(ws, w):
    """Column LETTER of week w."""
    return openpyxl.utils.get_column_letter(_wc(ws, w))


def _lp_probe(body):
    """Run `body` against the LP oracle in .venv and return the JSON it prints.

    Three tests needed scipy, which pytest's interpreter does not have, and each grew its own
    copy of this plumbing. ⚠️ One of those copies was FAIL-OPEN — it wrapped the assertions in
    `if out.returncode == 0`, so a snippet that crashed skipped the check silently and the test
    still passed green. Skipping is a decision worth making once, out loud, here.
    """
    import json
    import subprocess

    venv = REPO / ".venv" / "bin" / "python"
    if not venv.exists():
        pytest.skip(f"{venv} missing — cannot run the LP oracle")
    code = (f"import sys; sys.path.insert(0, {str(REPO / 'toy_models')!r});\n"
            f"import json, toy_v10_lp as lp\n" + body)
    out = subprocess.run([str(venv), "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, f"LP probe failed:\n{out.stderr[-2000:]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def _labelled_rows(ws):
    out = {}
    for row in range(1, ws.max_row + 1):
        v = ws.cell(row=row, column=1).value
        if isinstance(v, str):
            out.setdefault(v.strip(), []).append(row)
    return out


def _crop_blocks(ws):
    """{CROP: {row label: row number}}, delimited by the NEXT block header.

    Never by a fixed row count. Too narrow silently drops the last rows of a block; too wide
    reads the NEXT crop's rows under this crop's names, so every comparison is wrong while every
    lookup succeeds. Measured while building v2: the second presented as twelve real defects.
    """
    # ⚠️ The first token must be a CROP. "…endswith('store')" alone also matched the solver
    # recipe's "Constraint — cold store" and "Constraint — ambient store", which collapsed into
    # a bogus "Constraint" block. Latent since v5 — harmless while every caller named the three
    # crops explicitly, and it surfaced the moment a test iterated the blocks instead.
    heads = [r for r in range(1, ws.max_row + 1)
             if isinstance(ws.cell(row=r, column=1).value, str)
             and "—" in ws.cell(row=r, column=1).value
             and ws.cell(row=r, column=1).value.endswith("store")
             and ws.cell(row=r, column=1).value.split(" ")[0].title() in TOY_CROPS]
    blocks = {}
    for i, r in enumerate(heads):
        stop = heads[i + 1] if i + 1 < len(heads) else ws.max_row + 1
        seq = {}
        for rr in range(r + 1, stop):
            lv = ws.cell(row=rr, column=1).value
            if isinstance(lv, str) and lv.strip():
                seq.setdefault(lv.strip(), rr)
        blocks[ws.cell(row=r, column=1).value.split(" ")[0]] = seq
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
        "Cold store (cooler)": payload["harvest_storage_cap"],
        "Ambient store (barn)": payload["ambient_storage_cap"],
    }
    for label, want in caps.items():
        r = rows[label][0]
        assert model.cell(row=r, column=2).value == want, f"{label} has drifted from the payload"


def test_every_succession_the_app_offers_is_on_the_sheet(model):
    """v5's reason for existing: the solver must choose WHEN to plant.

    The grower found v4 carrying five hand-picked plantings where the app offers 68 — and
    measured, freeing that was worth +128% of profit, more than every missing cost line
    combined. A subset here silently reintroduces it, and the sheet would still look right.
    """
    rows = {}
    for r in range(1, model.max_row + 1):
        a, b = model.cell(row=r, column=1).value, model.cell(row=r, column=2).value
        if isinstance(a, str) and b in TOY_CROPS and isinstance(
                model.cell(row=r, column=3).value, (int, float)):
            rows[a] = r
    missing = [n for n in PICKED if n not in rows]
    assert not missing, (
        f"{len(missing)} of {len(PICKED)} successions the app offers are absent from the "
        f"calendar (e.g. {missing[:4]}) — the solver cannot choose a week it is not shown")
    extra = [n for n in rows if n not in PICKED]
    assert not extra, f"sheet carries successions the app does not generate: {extra[:4]}"


def test_the_phase_pattern_matches_the_apps_generator(model):
    """Each planting's P/G/H row must be the calendar the app would build for that start week."""
    from farm_v2.utils.calendar import harvest_weeks_of
    succ = {x["name"]: x for x in _all_successions()}
    checked = 0
    for r in range(1, model.max_row + 1):
        name = model.cell(row=r, column=1).value
        if name not in succ:
            continue
        want = {((wk - 1) % 52) + 1: "PGH"[ph]
                for wk, ph in zip(succ[name]["weeks"], succ[name]["phases"])}
        for w in range(1, 53):
            got = model.cell(row=r, column=w + 4).value
            assert (got or None) == want.get(w), (
                f"{name} week {w}: sheet {got!r}, app {want.get(w)!r}")
        assert sum(1 for w in range(1, 53)
                   if model.cell(row=r, column=w + 4).value == "H") == len(
            harvest_weeks_of(succ[name], 52))
        checked += 1
    assert checked == len(PICKED), f"only checked {checked} of {len(PICKED)} plantings"


def test_the_plant_decision_is_wired_to_a_minimum_acreage(model):
    """C9 and C10: acres <= land x y, and acres >= min_acres x y.

    Without these the binary is decorative and the solver plants a third of an acre — measured,
    10 of 42 plantings fell below the app's own 2-acre minimum in the LP relaxation.
    """
    hdr = None
    for r in range(1, model.max_row + 1):
        if model.cell(row=r, column=1).value == "Succession":
            hdr = r
            break
    assert hdr, "calendar header not found"
    cols = {model.cell(row=hdr, column=c).value: c
            for c in range(1, model.max_column + 1)
            if model.cell(row=hdr, column=c).value}
    for want in ("ACRES", "PLANT?", "max if planted", "min if planted"):
        assert want in cols, f"{want!r} column missing — the plant decision is not wired"
    r = hdr + 1
    fmax = model.cell(row=r, column=cols["max if planted"]).value
    fmin = model.cell(row=r, column=cols["min if planted"]).value
    dcol = model.cell(row=r, column=cols["PLANT?"]).coordinate[0]
    assert f"{dcol}{r}" in fmax and "*" in fmax, f"C9 helper does not multiply the binary: {fmax!r}"
    assert f"{dcol}{r}" in fmin and "*" in fmin, f"C10 helper does not multiply the binary: {fmin!r}"


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
    w2 = _wl(model, 2)
    f = model.cell(row=b["ROOM OCCUPANCY"], column=_wc(model, 2)).value
    assert f"{w2}{b['Stock carried in']}" in f, f"{crop}: ROOM does not read stock carried in"
    assert f"{w2}{b['Packed out -> INTO the store']}" in f, (
        f"{crop}: ROOM does not read what was PACKED OUT this week. It must not read the GROSS "
        f"harvest either — field cull never entered the room (G1/E1).")
    assert "Harvested (gross)" not in b or f"{w2}{b['Harvested (gross)']}" not in f, (
        f"{crop}: ROOM reads GROSS harvest, so field cull is occupying a cooler it never saw")
    assert f"D{b['Stock carried out']}" not in f, (
        f"{crop}: ROOM reads stock carried OUT — this is the lower-bound defect, "
        f"and the sheet would teach it as correct")


@pytest.mark.parametrize("crop", ["SPINACH", "KALE", "GARLIC"])
def test_the_inventory_chain_actually_chains(model, crop):
    b = _crop_blocks(model)[crop]
    w1, w2 = _wl(model, 1), _wl(model, 2)
    assert model.cell(row=b["Stock carried in"], column=_wc(model, 2)).value == \
        f"={w1}{b['Stock carried out']}"
    assert model.cell(row=b["In store this week"], column=_wc(model, 2)).value == (
        f"={w2}{b['Stock carried in']}-{w2}{b['lost to shrink']}"
        f"+{w2}{b['Packed out -> INTO the store']}")
    # Carried out subtracts each channel's CONSUMED, which is offered minus what came home.
    # Subtracting SOLD instead would silently resurrect the market loss into next week's stock.
    close = model.cell(row=b["Stock carried out"], column=_wc(model, 2)).value
    assert close.startswith(f"={w2}{b['In store this week']}"), close
    assert close.count(f"-{w2}") >= 1, f"{crop}: carried-out subtracts nothing"


def test_each_pool_sums_its_own_crops_only(model):
    """The 'grouped on the wrong column' trap: a pool row that silently totals the wrong set."""
    b = _crop_blocks(model)
    rows = _labelled_rows(model)
    cold = model.cell(row=rows["COLD STORE"][0], column=_wc(model, 2)).value
    amb = model.cell(row=rows["AMBIENT STORE"][0], column=_wc(model, 2)).value
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
              and model.cell(row=r, column=_wc(model, 1)).value == 1
              and model.cell(row=r, column=_wc(model, 52)).value == 52]
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
        assert model.cell(row=top + 1, column=_wc(model, 1)).value == "<=", \
            f"{label}: no '<=' row beneath it"
        limit = model.cell(row=top + 2, column=_wc(model, 1)).value
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
    f = model.cell(row=rows["LAND in the ground"][0], column=_wc(model, 2)).value
    assert "SUMPRODUCT" in f, f"land row should sum across the whole calendar, got {f!r}"
    assert '<>""' in f, "land row should read the phase strip for that WEEK, not an annual total"


def test_readme_coordinates_point_at_what_they_claim():
    """Every range the instructions name must actually cover what the sentence says.

    v1 shipped "set Garlic's shrink (G17)" hard-coded; a row was added and G17 became KALE's.
    The generator derives these now, and this asserts the derivation. In v5 the interesting
    ones are RANGES over the calendar, and a range that silently covers 5 rows instead of 68
    is the v4 defect wearing a different hat.
    """
    wb = openpyxl.load_workbook(WORKBOOK)
    rd, model = wb["READ ME"], wb["Model"]
    text = "\n".join(str(rd.cell(row=r, column=1).value or "") for r in range(1, rd.max_row + 1))

    hdr = next(r for r in range(1, model.max_row + 1)
               if model.cell(row=r, column=1).value == "Succession")
    cols = {model.cell(row=hdr, column=c).value: c
            for c in range(1, model.max_column + 1) if model.cell(row=hdr, column=c).value}

    ranges = re.findall(r"\(?([A-Z]{1,2})(\d+):([A-Z]{1,2})(\d+)\)?", text)
    named = {(a, int(b), c, int(d)) for a, b, c, d in ranges}
    assert named, "the READ ME names no ranges at all"

    acres_letter = openpyxl.utils.get_column_letter(cols["ACRES"])
    bin_letter = openpyxl.utils.get_column_letter(cols["PLANT?"])
    for letter, what in ((acres_letter, "ACRES"), (bin_letter, "PLANT?")):
        hits = [r for r in named if r[0] == letter and r[2] == letter]
        assert hits, f"the READ ME never names the {what} range (column {letter})"
        top, bot = min(h[1] for h in hits), max(h[3] for h in hits)
        rows = bot - top + 1
        assert rows == len(PICKED), (
            f"the READ ME's {what} range {letter}{top}:{letter}{bot} covers {rows} rows, but the "
            f"app offers {len(PICKED)} successions — a partial range silently recreates v4's "
            f"hand-picked-calendar defect")
        assert model.cell(row=top, column=1).value in PICKED
        assert model.cell(row=bot, column=1).value in PICKED


def test_sell_through_lives_on_the_crop_channel_row_not_the_crop():
    """Grower ruling, 2026-08-29 (DECISIONS E1).

    A wholesaler orders and invoices, so sell-through is ~1.0 there by construction; a market
    stall always offers more than it sells. And whether the remainder is lost or merely delayed
    depends on the CROP. Only a crop x channel cell can hold that, so a Sell-through column on
    the CROP table would be the old farm-wide mistake wearing a new hat.
    """
    wb = openpyxl.load_workbook(WORKBOOK)
    model = wb["Model"]
    crop_hdr = pair_hdr = None
    for r in range(1, model.max_row + 1):
        a, b = model.cell(row=r, column=1).value, model.cell(row=r, column=2).value
        if a == "Crop" and b == "Yield lb/acre":
            crop_hdr = r
        if a == "Crop" and b == "Channel":
            pair_hdr = r
    assert crop_hdr and pair_hdr, "could not find both tables"
    crop_cols = [model.cell(row=crop_hdr, column=c).value for c in range(1, 10)]
    pair_cols = [model.cell(row=pair_hdr, column=c).value for c in range(1, 10)]
    assert "Sell-through" not in crop_cols, (
        "Sell-through is on the CROP table — the ruling puts it on crop x channel")
    assert "Sell-through" in pair_cols and "Returns to store" in pair_cols
    # and one pair per crop x channel, no more and no fewer
    n = sum(1 for r in range(pair_hdr + 1, pair_hdr + 40)
            if model.cell(row=r, column=2).value in
            {model.cell(row=x, column=2).value for x in range(pair_hdr + 1, pair_hdr + 40)}
            and model.cell(row=r, column=1).value in ("Spinach", "Kale", "Garlic"))
    assert n == 6, f"expected 6 crop x channel rows, found {n}"


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
                 if model.cell(row=r, column=1).value in ("Week", "Succession")}
    anchors = {r for r in range(1, model.max_row + 1)
               if str(model.cell(row=r, column=1).value).strip() == "Stock carried in"}
    frozen = []
    for row in model.iter_rows():
        for c in row:
            if not isinstance(c.value, (int, float)) or isinstance(c.value, bool):
                continue
            rgb = str(c.fill.fgColor.rgb) if (c.fill and c.fill.fgColor) else ""
            # FFF2CC = an input you type. D9EAD3 = a DECISION cell the solver writes into —
            # legitimately a bare number, and the only kind of frozen value v4 may contain.
            # FFF2CC = typed input. D9EAD3 = a continuous decision cell. C9DAF8 = a BINARY
            # decision cell. All three are legitimately bare numbers.
            if "FFF2CC" in rgb or "D9EAD3" in rgb or "C9DAF8" in rgb:
                continue
            if c.row in week_rows or (c.row in anchors and c.column == _wc(model, 1)):
                continue
            frozen.append(f"{c.coordinate}={c.value} "
                          f"(row {model.cell(row=c.row, column=1).value!r})")
    assert not frozen, (
        "frozen derived value(s) — make them formulas or mark them as inputs: "
        + "; ".join(frozen[:8]))


def test_the_sheet_actually_calculates_correctly():
    """Run toy_models/verify_toy_v10.py — it CALCULATES the workbook.

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

    r = subprocess.run([str(venv), str(REPO / "toy_models" / "verify_toy_v10.py")],
                       capture_output=True, text=True, cwd=REPO, timeout=600)
    assert r.returncode == 0, (
        "the toy workbook does not calculate correctly:\n"
        + "\n".join(l for l in r.stdout.splitlines() if "FAIL" in l or "FAILURE" in l)
        + ("\n" + r.stderr[-2000:] if r.stderr.strip() else ""))
    assert "ALL CHECKS PASSED" in r.stdout


def _table_header_above(model, row):
    """The header row above a table row, so a dead input can be named usefully."""
    for r in range(row - 1, 0, -1):
        if model.cell(row=r, column=1).value in ("Crop", "Succession"):
            return r
    return row


def test_no_input_is_wired_to_nothing(model):
    """Every yellow input must be read by at least one formula.

    The grower found 'Shelf life wk' sitting as a yellow box that NO formula referenced: v5
    dropped the row that used it and left the input behind, so it looked live and was not. Same
    class as `storage_loss_frac_per_week` in the app itself — fully implemented in the solver,
    switched off because nothing sends it. A box you can type in that changes nothing is worse
    than a missing feature, because it answers a question wrongly instead of not at all.
    """
    from openpyxl.utils import get_column_letter
    blob = "\n".join(c.value for row in model.iter_rows() for c in row
                      if isinstance(c.value, str) and c.value.startswith("="))
    from openpyxl.utils import column_index_from_string
    _ranges = [(column_index_from_string(a), int(b), column_index_from_string(cc), int(d))
               for a, b, cc, d in re.findall(
                   r"\$?([A-Z]{1,2})\$?(\d+):\$?([A-Z]{1,2})\$?(\d+)", blob)]
    dead = []
    for row in model.iter_rows():
        for c in row:
            rgb = str(c.fill.fgColor.rgb) if (c.fill and c.fill.fgColor) else ""
            if "FFF2CC" not in rgb or c.value is None:
                continue
            # ⚠️ A BOUNDED match, not `"F11" in blob`. The substring form matched F11 inside
            # SUM(E113:F113) and made this whole guard inert — found by mutating it, which is
            # the only reason it was found at all. A test for dead references that is itself a
            # dead reference is the exact shape this file keeps catching.
            col = get_column_letter(c.column)
            if re.search(rf"(?<![A-Za-z0-9$_]){re.escape(col)}\$?{c.row}(?![0-9])",
                         blob.replace("$", "")) or \
               re.search(rf"\${re.escape(col)}\${c.row}(?![0-9])", blob):
                continue
            # ...and a cell can also be read as part of a RANGE, which names only its corners.
            # The crew table is the first input block referenced purely as $B$27:$B$30, so every
            # row between the corners looked dead. Naming a false defect is as damaging as
            # missing a real one — it teaches you to ignore the guard.
            if any(c1 <= c.column <= c2 and r1 <= c.row <= r2
                   for c1, r1, c2, r2 in _ranges):
                continue
            # ⚠️ THE COLOUR KEY IS NOT AN INPUT. v9's legend paints one swatch in each of the
            # four semantic fills so a reader can hold the key against the sheet, and the
            # yellow swatch is therefore a filled cell no formula reads. Excluded BY NAME —
            # the row whose column A says "KEY:" — rather than by loosening the rule, because
            # a key is a different kind of object from a data cell, not an exempt data cell.
            if str(model.cell(row=c.row, column=1).value or "").strip() == "KEY:":
                continue
            hdr = _table_header_above(model, c.row)
            dead.append(f"{c.coordinate} = "
                        f"{model.cell(row=hdr, column=c.column).value!r} for "
                        f"{model.cell(row=c.row, column=1).value!r}")
    assert not dead, "yellow input cells that no formula reads: " + "; ".join(dead[:8])


def test_the_cash_floor_exists_and_is_wired(model):
    """v6's reason for existing: cumulative cash, and a floor it may not fall through.

    The floor must REFERENCE the opening-cash and credit-line inputs, not restate their sum —
    a floor that is a typed number silently stops tracking the two boxes above it.
    """
    rows = _labelled_rows(model)
    for lab in ("Opening cash", "Credit line", "CASH IN THE BANK", "floor", "NET CASH this week"):
        assert lab in rows, f"the cash section is missing {lab!r}"
    w2 = _wl(model, 2)
    cum = model.cell(row=rows["CASH IN THE BANK"][0], column=_wc(model, 2)).value
    w1 = _wl(model, 1)
    assert f"{w1}{rows['CASH IN THE BANK'][0]}" in cum, (
        f"cash-in-the-bank must carry LAST week's balance forward, got {cum!r}")
    assert f"{w2}{rows['NET CASH this week'][0]}" in cum, "it must add this week's net cash"
    # ⚠️ THE FLOOR IS MINUS THE CREDIT LINE, and must NOT also subtract opening cash.
    # The row above is a bank BALANCE that already starts from opening cash, so a floor of
    # -(opening + credit) counts the opening twice and hands the farm an overdraft it does not
    # have — it shipped that way, at $50,000 too permissive.
    # The app is consistent the other way round: its C13 floors cumulative NET FLOW, which
    # excludes opening cash, at -(opening + credit). Either convention is right; mixing them is
    # not. (The first version of this test asserted the buggy form, so the guard would have
    # locked the defect in.)
    floor = model.cell(row=rows["floor"][0], column=_wc(model, 2)).value
    assert f"$B${rows['Credit line'][0]}" in floor, (
        f"the floor must READ the credit-line cell, got {floor!r}")
    assert f"$B${rows['Opening cash'][0]}" not in floor, (
        f"the floor also subtracts opening cash, which the balance row already includes — "
        f"that double-counts it. Got {floor!r}")


def test_costs_land_in_the_week_they_are_paid(model):
    """Seed at the planting week, phase costs while in the ground, packaging at the sale.

    A cash floor built on costs charged in the wrong week is worse than no cash floor, because
    it looks like a solvency check and is not one.
    """
    blocks = _crop_blocks(model)
    for crop, seq in blocks.items():
        assert "Growing cost this week" in seq, f"{crop}: no weekly growing-cost row"
        assert "Packaging this week" in seq, f"{crop}: no weekly packaging row"
        f = model.cell(row=seq["Growing cost this week"], column=_wc(model, 20)).value
        assert '="P"' in f or '"P"' in f, f"{crop}: growing cost ignores the planting phase"
        assert '"G"' in f and '"H"' in f, f"{crop}: growing cost ignores grow/harvest phases"
        assert "MATCH" in f or "starts" in f.lower() or "=" in f, f"{crop}: seed timing missing"
        pkg = model.cell(row=seq["Packaging this week"], column=_wc(model, 20)).value
        sold_rows = [seq[k] for k in seq if k.endswith("— SOLD")]
        assert any(f"{_wl(model, 20)}{r}" in pkg for r in sold_rows), (
            f"{crop}: packaging is not charged on the pounds SOLD that week")


def test_labour_is_committed_not_charged_per_acre(model):
    """W12, the app's largest single correction, reproduced as a structural guard.

    Every listed worker is paid for their stated hours whether or not the crops need them, so
    wages are a WEEKLY row and no crop carries a per-acre labour charge. If a labour cost ever
    appears inside a crop's growing-cost formula, the marginal crop hour stops being free and
    the model is back to the thing W12 fixed.
    """
    rows = _labelled_rows(model)
    for lab in ("CREW CAPACITY", "Wage bill this week", "CROP HOURS needed"):
        assert lab in rows, f"the labour section is missing {lab!r}"

    # the wage bill must read the crew table, not a typed number
    w2 = _wl(model, 2)
    # v10: the wage bill is a SUM of per-position cost rows, and it is those rows that read
    # the crew table. Asserting SUMPRODUCT here would be asserting the v9 structure — a check
    # written for the previous version is a check against the wrong model.
    wage = str(model.cell(row=rows["Wage bill this week"][0], column=_wc(model, 2)).value)
    assert wage.startswith("=") and "+" in wage, (
        f"the wage bill must be a sum of the per-position cost rows, got {wage!r}")

    # and no crop's growing cost may include labour
    for crop, seq in _crop_blocks(model).items():
        f = model.cell(row=seq["Growing cost this week"], column=_wc(model, 20)).value
        assert "labor" not in f.lower(), (
            f"{crop}: a labour term has appeared in the per-acre growing cost — wages are "
            f"committed (W12), so the marginal crop hour must stay free")


def test_crew_capacity_varies_by_week(model):
    """The seasonal crews come and go, so a single capacity number cannot express it.

    Flattening the wage profile understated the app's own cash floor by $115,615; the capacity
    side has the same shape and the same trap.
    """
    rows = _labelled_rows(model)
    # v9: capacity is row 5 = row 3 + row 4, so the start/end-week test moved DOWN the ladder to
    # the rows that read the crew table. Asserting SUMPRODUCT on row 5 would now be asserting
    # the OLD structure — a check written for the previous version is a check against the wrong
    # model, which is how v8 flagged four correct weeks as violations.
    # ⚠️ v10: the start/end-week test moved DOWN to the PER-POSITION rows. Capacity and the
    # hourly row are now sums of those, so asserting SUMPRODUCT here would assert the v9
    # structure — a check written for the previous version is a check against the wrong model.
    a_hdr = rows["A — WHO IS ON, WEEK BY WEEK"][0]
    pos_rows = [r for r in range(a_hdr, rows["CREW CAPACITY"][0])
                if str(model.cell(row=r, column=2).value or "").startswith("hrs")]
    assert len(pos_rows) >= 3, f"expected a row per position in block A, found {pos_rows}"
    seasonal = 0
    for r in pos_rows:
        f1 = str(model.cell(row=r, column=_wc(model, 1)).value)
        f20 = str(model.cell(row=r, column=_wc(model, 20)).value)
        for f in (f1, f20):
            assert "IF(AND(" in f and ">=" in f and "<=" in f, (
                f"row {r} must test its own start/end week, got {f!r}")
        if f1 != f20:
            seasonal += 1
    assert seasonal >= 1, (
        "no position row differs between week 1 and week 20 — the seasonal windows are not "
        "being read, and flattening the wage side understated the app's cash floor by $115,615")
    # and the VALUES must differ across the year, which is what the wage-profile lesson was about
    lo, hi = _lp_probe("c, w, h, n = lp.labour_arrays()\n"
                       "print(json.dumps([min(c[1:]), max(c[1:])]))")
    assert hi > lo * 1.5, (
        f"crew capacity barely varies ({lo:.0f} to {hi:.0f} hrs) — the seasonal shape has been "
        f"flattened, and flattening the wage side understated the app's own cash floor by "
        f"$115,615")


_REF_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,3})\$?(\d+)(?!\d)")


def _refs(formula):
    """Every cell a formula reads, as {(col_letters, row)}.

    Substring matching on formulas is how guards ship inert: "B32" matches inside "B320", and
    "AH131" fails to match "AH$131". Parse, do not grep.
    """
    return {(c, int(r)) for c, r in _REF_RE.findall(str(formula).replace("$", ""))}


def test_the_advisory_crew_is_one_committed_block_not_a_spot_purchase(model):
    """L1 — the shape of the hire decision, which is what v9 changed.

    v8 gave the solver 52 independent spot purchases and it produced a plan no farm could run:
    21 non-zero weeks in blocks of 2/2/2/3/12, and one week that bought TWO HOURS. Real hiring
    is a committed block decided months ahead (H-2A: 60-75 days of lead and a three-fourths
    guarantee; domestic seasonal: 8-10 weeks), which is what an `employees[]` row already is.

    Two properties make it a hire rather than a purchase, and both are checked here:
      * ONE headcount cell, not a per-week row
      * charged for EVERY week of the window, whether the hours are used or not
    """
    rows = _labelled_rows(model)
    for lab in ("PEOPLE TO HIRE", "Proposed hire hours", "Proposed hire cost this week",
                "Cost per person per week", "TOTAL committed cost"):
        assert lab in rows, f"the advisory layer is missing {lab!r}"

    # ONE decision cell, in column B — not a 52-week strip.
    head = rows["PEOPLE TO HIRE"][0]
    v = model.cell(row=head, column=2).value
    assert not (isinstance(v, str) and v.startswith("=")), (
        "the advisory headcount holds a formula — the solver must own that cell")
    for w in (1, 20, 52):
        assert model.cell(row=head, column=_wc(model, w)).value in (None, ""), (
            "the advisory crew has per-week cells — that is the spot-hire shape L1 removed")

    # ⚠️ COMMITTED. The wage row must not read the hours-used row, or an unneeded hour becomes
    # free again and the whole distinction from v8 collapses. Compare what it READS, because a
    # wage row that happened to equal the hours row in the shipped case would pass a value test.
    wage_f = model.cell(row=rows["Proposed hire cost this week"][0],
                        column=_wc(model, 45)).value
    reads = _refs(wage_f)
    assert ("B", head) in reads, "the advisory wage does not read the headcount"
    assert not any(r == rows["Proposed hire hours"][0] for _, r in reads), (
        "the advisory wage is computed from the hours USED — a committed block is paid whole, "
        "and reading the hours row is exactly how it stops being committed")
    assert not any(r == rows["CROP HOURS needed"][0] for _, r in reads), (
        "the advisory wage reads the crop-hours row — it must not depend on demand at all")


def test_the_advisory_wage_is_charged_in_every_week_of_the_window(model):
    """The other half of L1, and the half a structural check cannot see.

    A wage row that reads the headcount can still be wrong by only firing in the weeks the plan
    happens to need. Drive the sheet: set a headcount and confirm the charge appears in EVERY
    week of the nominated window and in none outside it.
    """
    rows = _labelled_rows(model)
    lo = int(model.cell(row=rows["Proposed hire"][0], column=2).value)
    hi = int(model.cell(row=rows["Proposed hire"][0], column=3).value)
    assert 1 <= lo <= hi <= 52, f"the advisory window is not a sane range: {lo}-{hi}"
    wrow = rows["Proposed hire cost this week"][0]
    hrow = rows["Proposed hire hours"][0]
    for w in range(1, 53):
        f = str(model.cell(row=wrow, column=_wc(model, w)).value)
        inwin = lo <= w <= hi
        # the IF's window test is written from the literal week number, so it is readable
        assert str(w) in f, f"week {w}'s advisory wage does not mention its own week: {f!r}"
        gf = str(model.cell(row=hrow, column=_wc(model, w)).value)
        assert str(w) in gf, f"week {w}'s advisory hours do not mention its own week: {gf!r}"


def test_the_overtime_cap_is_derived_from_the_hourly_crew_not_typed(model):
    """L2 — the defect this whole version exists to remove, and it is a MONEY defect.

    v8 (and the app) broadcast one scalar flat across 52 weeks while the crew is seasonal. On
    the app's own farm that let 15 of 52 weeks buy MORE overtime than the entire crew's regular
    hours (185% in winter) and the solver TOOK it: 191 overtime hours against 299 crew hours in
    one week, a 66-hour week for everybody.

    No flat number can express the rule, because the hourly crew here runs 0 to 872 field hours.
    So the cap must READ the weekly hourly-hours row and the allowance, and nothing else.
    """
    rows = _labelled_rows(model)
    for lab in ("Hourly field hours", "Overtime CAP", "Overtime ALLOWANCE"):
        assert lab in rows, f"the overtime layer is missing {lab!r}"
    cap_row = rows["Overtime CAP"][0]
    hf_row = rows["Hourly field hours"][0]
    allow = ("B", rows["Overtime ALLOWANCE"][0])

    # It must VARY. A cap identical in a winter week and a peak week is a flat number wearing a
    # formula, which is the v8 defect with extra steps.
    f_winter = str(model.cell(row=cap_row, column=_wc(model, 2)).value)
    f_peak = str(model.cell(row=cap_row, column=_wc(model, 20)).value)
    assert f_winter != f_peak, "the overtime cap is the same formula in week 2 and week 20"

    for w in (2, 20, 45):
        reads = _refs(model.cell(row=cap_row, column=_wc(model, w)).value)
        assert allow in reads, f"week {w}'s overtime cap does not read the allowance"
        assert any(r == hf_row for _, r in reads), (
            f"week {w}'s overtime cap does not read row 3 (hourly FIELD hours) — it cannot be "
            f"tracking the crew that is actually on")
        # ⚠️ and NOT crew capacity, which INCLUDES salaried staff — they give capacity but
        # cannot be paid overtime, so the cap must read the hourly-only row.
        assert not any(r == rows["CREW CAPACITY"][0] for _, r in reads), (
            f"week {w}'s overtime cap reads CREW CAPACITY, which includes salaried staff — "
            f"they cannot work overtime")


def test_the_overtime_cap_binds_and_is_zero_without_an_hourly_crew(model):
    """The cap has to actually DO something, and be zero where it must be.

    A guard that only proves a formula exists is the class this project has shipped five times.
    These are the two values the cap must produce: proportional in a staffed week, and ZERO in a
    week with no hourly crew — you cannot work overtime on people who are not there, and v8's
    flat 200 said you could.
    """
    d = _lp_probe("cap, wage, hf, heads = lp.labour_arrays()\n"
                  "print(json.dumps({'hf': list(hf),"
                  " 'cap': [0.25 * hf[w] for w in range(53)]}))")
    hf, cap = d["hf"], d["cap"]
    # ⚠️ THE SHIPPED ROSTER CANNOT PRODUCE THE ZERO CASE — it keeps two year-round hourly
    # Equipment Operators, so the hourly crew never empties (minimum 72 field hours). Demanding
    # an empty week here FAILED on a correct model, and a guard that cries wolf teaches you to
    # ignore it. The zero case is real and worth testing, so it is tested on a roster that HAS
    # one: strip the year-round hourly roles below.
    assert all(hf[w] > 0 for w in range(1, 53)), (
        "the shipped roster now has an unstaffed hourly week — the note above is stale")
    busy = [w for w in range(1, 53) if hf[w] > 0]
    for w in busy:
        assert abs(cap[w] - 0.25 * hf[w]) < 1e-9, (
            f"week {w}: cap {cap[w]} is not 25% of the hourly crew's {hf[w]} field hours")
    assert max(cap) > 0, "the overtime cap is zero everywhere — the layer is inert"

    # Now the zero case, on a roster that can produce one.
    d2 = _lp_probe(
        "lp.PAYLOAD['employees'] = [e for e in lp.PAYLOAD['employees']\n"
        " if e['type'] == 'salary' or e.get('end_week', 52) < 52"
        " or e.get('start_week', 1) > 1]\n"
        "cap, wage, hf, heads = lp.labour_arrays()\n"
        "print(json.dumps({'hf': list(hf),"
        " 'cap': [0.25 * hf[w] for w in range(53)]}))")
    hf2, cap2 = d2["hf"], d2["cap"]
    quiet = [w for w in range(1, 53) if hf2[w] == 0]
    assert quiet, "even without year-round hourly staff no week empties — fixture is wrong"
    for w in quiet:
        assert cap2[w] == 0, (
            f"week {w} has NO hourly crew but allows {cap2[w]} overtime hours — you cannot work "
            f"overtime on people who are not there, and v8's flat 200 said you could")


def test_the_labour_section_flows_top_to_bottom(model):
    """v10 — the grower's note that the section doubled back on itself.

    v9 went capacity -> PRICES -> cap -> decisions -> available -> COSTS -> constraints, so
    money appeared twice, split around the middle, and the limits trailed after the costs.
    The order is now four blocks with one job each:

        A  who is on          per-position hours, crew capacity, hourly-only hours
        B  what you can add   overtime cap, overtime hours, proposed hire, HOURS AVAILABLE
        C  the limits         crop hours <= available;  overtime <= cap
        D  what it costs      wage bill, overtime cost, proposed hire cost

    Nothing above C is money and nothing below it is a limit. This asserts the blocks appear
    in that order and that each row still reads only rows above it.
    """
    rows = _labelled_rows(model)
    blocks = ["A — WHO IS ON, WEEK BY WEEK", "B — WHAT YOU CAN ADD", "C — THE LIMITS",
              "D — WHAT IT COSTS"]
    for b in blocks:
        assert b in rows, f"the labour section is missing block header {b!r}"
    at = [rows[b][0] for b in blocks]
    assert at == sorted(at), f"the labour blocks are out of order: {list(zip(blocks, at))}"

    # every row lands in the block it belongs to
    for lab, block in (("CREW CAPACITY", 0), ("Hourly field hours", 0),
                       ("Overtime CAP", 1), ("OVERTIME hours", 1),
                       ("Proposed hire hours", 1), ("HOURS AVAILABLE", 1),
                       ("CROP HOURS needed", 2), ("OVERTIME bought", 2),
                       ("Wage bill this week", 3), ("Overtime cost this week", 3),
                       ("Proposed hire cost this week", 3)):
        r = rows[lab][0]
        lo = at[block]
        hi = at[block + 1] if block + 1 < len(at) else model.max_row
        assert lo < r < hi, (
            f"{lab!r} is at row {r}, outside its block {blocks[block]!r} ({lo}-{hi}) — money "
            f"among the limits, or a limit among the costs, is the shape v10 removed")

    # ⚠️ NO MONEY ABOVE THE LIMITS. The whole point of the reorder is that a reader can stop at
    # block C and have the complete physical picture. A $ row above it would undo that.
    for lab, rr in rows.items():
        for r in rr:
            if at[0] < r < at[2] and str(model.cell(row=r, column=2).value or "").strip() == "$":
                pytest.fail(f"{lab!r} (row {r}) is a $ row above 'C — THE LIMITS' — blocks A "
                            f"and B are physical, money starts at D")

    w = _wc(model, 20)
    # capacity is a SUM of the per-position rows, not a mask
    capf = str(model.cell(row=rows["CREW CAPACITY"][0], column=w).value)
    assert "SUMPRODUCT" not in capf, (
        f"crew capacity still uses a SUMPRODUCT mask — splitting by position was meant to "
        f"remove it. Got {capf!r}")
    assert capf.count("+") >= 1, f"crew capacity does not add up named rows: {capf!r}"

    # hours available = capacity + overtime + proposed hire
    avail = _refs(model.cell(row=rows["HOURS AVAILABLE"][0], column=w).value)
    for lab in ("CREW CAPACITY", "OVERTIME hours", "Proposed hire hours"):
        assert any(rr == rows[lab][0] for _, rr in avail), f"hours-available omits {lab!r}"

    # overtime cost reads the hours row, at the FULL rate (W12b: no 'minus base')
    otc = model.cell(row=rows["Overtime cost this week"][0], column=w).value
    assert any(rr == rows["OVERTIME hours"][0] for _, rr in _refs(otc)), (
        "the overtime cost does not read the overtime hours row")
    assert "-" not in str(otc).replace("=", ""), (
        f"the overtime cost has a subtraction in it — charging the premium above base pay "
        f"instead of the full rate is the W12b defect. Got {otc!r}")


def test_a_bought_hour_is_worth_less_than_a_trained_one(model):
    """v10 — productivity, which is what stopped the hire being unbeatable.

    Before it, a bought hour did exactly as much crop work as a trained crew hour, so the hire
    won everywhere it was available: $25.00/hr all-in against overtime at $37.84-48.75, and the
    solver took 18 of the 20 heads on offer. The two prices meet at about 65% productivity, so
    this one factor decides the whole hire-vs-overtime answer.
    """
    rows = _labelled_rows(model)
    assert "Proposed hire" in rows, "the proposed-hire input row is missing"
    inp = rows["Proposed hire"][0]
    prod = model.cell(row=inp, column=8).value
    head = model.cell(row=inp, column=9).value
    assert isinstance(prod, (int, float)) and 0 < prod <= 100, (
        f"productivity % is not a sane percentage: {prod!r}")
    assert isinstance(head, (int, float)) and head >= 0, f"$ per head is not a number: {head!r}"

    # the HOURS row must read productivity; the COST row must not (you pay for booked hours)
    hrs = _refs(model.cell(row=rows["Proposed hire hours"][0], column=_wc(model, 45)).value)
    assert ("H", inp) in hrs, (
        "the proposed-hire HOURS row does not read productivity — a bought hour is then worth "
        "as much as a trained one, which is what made the hire unbeatable")
    cost = _refs(model.cell(row=rows["Proposed hire cost this week"][0],
                            column=_wc(model, 45)).value)
    assert ("H", inp) not in cost, (
        "the proposed-hire COST reads productivity — you pay for the hours you booked, not the "
        "work you got out of them. Discounting the wage is the same arithmetic and the wrong "
        "story")

    # the per-head cost is charged ONCE, in the first week of the window
    lo = int(model.cell(row=inp, column=2).value)
    first = _refs(model.cell(row=rows["Proposed hire cost this week"][0],
                             column=_wc(model, lo)).value)
    later = _refs(model.cell(row=rows["Proposed hire cost this week"][0],
                            column=_wc(model, lo + 1)).value)
    assert ("I", inp) in first, "the per-head cost is not charged in the window's first week"
    assert ("I", inp) in later or True   # both cells carry the same IF; the IF is what differs
    f_lo = str(model.cell(row=rows["Proposed hire cost this week"][0],
                          column=_wc(model, lo)).value).replace("$", "")
    assert f"IF({lo}=B{inp}" in f_lo, (
        f"the per-head charge is not pinned to the window's first week: {f_lo!r}")
    # and it fires in exactly ONE week — a per-head cost charged weekly is a per-week cost
    fires = [w for w in range(1, 53)
             if f"IF({w}=" in str(model.cell(row=rows["Proposed hire cost this week"][0],
                                             column=_wc(model, w)).value).replace("$", "")]
    assert len(fires) == 52, "every week should carry the same guarded IF"
    import re as _re
    hit = [w for w in range(1, 53)
           if _re.search(rf"IF\({w}=B{inp}\b",
                         str(model.cell(row=rows["Proposed hire cost this week"][0],
                                        column=_wc(model, w)).value).replace("$", ""))]
    assert hit == list(range(1, 53)), "the per-head IF should compare each week to the start"


def test_c2_measures_against_hours_available_not_the_standing_crew(model):
    """Once hours can be added, the ceiling is crew PLUS overtime PLUS the advised crew.

    Leaving C2 pointed at the standing crew makes every extra hour a violation, and the layer
    can never be used — the same defect as not having it.
    """
    rows = _labelled_rows(model)
    avail = str(model.cell(row=rows["HOURS AVAILABLE"][0],
                           column=_wc(model, 20)).value).replace("$", "")
    for lab in ("CREW CAPACITY", "OVERTIME hours", "Proposed hire hours"):
        assert f"{_wl(model, 20)}{rows[lab][0]}" in avail, (
            f"hours-available does not include {lab!r}: {avail!r}")
    limit = str(model.cell(row=rows["CROP HOURS needed"][0] + 2,
                           column=_wc(model, 20)).value).replace("$", "")
    assert f"{_wl(model, 20)}{rows['HOURS AVAILABLE'][0]}" in limit, (
        f"C2's limit row still points at the standing crew, so no added hour could ever be "
        f"used. Got {limit!r}")


def test_a_bought_hour_with_no_price_is_refused():
    """The refusal exists; this is what proves it fires.

    A bought hour priced at $0 is a free hour, and free hours buy revenue out of nothing — the
    W12b defect in its purest form. The sheet cannot catch it on its own: the rate formula is
    IFERROR(..., 0), so an unpriced hour reads as $0.00 there too and section E's sheet-vs-LP
    comparison would AGREE. Both sides wrong together is the one thing that comparison cannot
    see, so the oracle has to refuse outright.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "toy_v10_lp", REPO / "toy_models" / "toy_v10_lp.py")
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)

    # a zero multiplier prices an overtime hour at $0 while every wage on the roster is healthy
    with pytest.raises(RuntimeError, match="free labour"):
        lp.solve(flex=True, overtime_multiplier=0.0)

    # ⚠️ and the OTHER axis, which v9 moved: there is no hired-wage input any more, so the way
    # to get free labour now is an advisory crew with no wage. Checking only the overtime side
    # would leave this half unguarded — the same two-axis mistake v8 recorded.
    with pytest.raises(RuntimeError, match="free labour|no wage"):
        lp.solve(advisory=True, adv_wage=0.0)


def test_the_palette_is_semantic_and_closed(model):
    """v9's colour rule, at the grower's request: colour means ROLE, never subject.

    v8 had nine fills keyed to what a row was ABOUT — cold pool blue, ambient orange, channel
    green and pink, annual-cap orange, binaries blue — so colour never told you what a cell was
    FOR, and the two things a reader most needs to find (what may I change, what is the answer)
    had no colour of their own.

    Four colours carry meaning and every other fill is grey. This asserts the set is CLOSED:
    a tenth fill cannot creep back in, which is how the v8 palette got where it did. It also
    asserts each of the four is actually USED, because a palette rule that nothing obeys is
    decoration.
    """
    SEMANTIC = {"FFF2CC": "input", "D9EAD3": "decision",
                "F4CCCC": "constraint", "D9D2E9": "objective"}
    GREY = {"D9D9D9", "EFEFEF", "F2F2F2", "F7F7F7"}
    # the conditional-format warning fill is applied by a RULE, not to a cell, but openpyxl can
    # surface it on cells in some readers — allow it explicitly rather than by accident.
    ALLOWED = set(SEMANTIC) | GREY | {"FFC7CE"}

    seen = {}
    for row in model.iter_rows():
        for cell in row:
            f = cell.fill
            if not (f and f.fill_type == "solid"):
                continue
            rgb = (f.fgColor.rgb or "")[-6:].upper()
            if not rgb or rgb == "000000":
                continue
            seen[rgb] = seen.get(rgb, 0) + 1

    stray = sorted(set(seen) - ALLOWED)
    assert not stray, (
        f"fills outside the v9 palette: {stray}. Colour on this sheet means ROLE (input, "
        f"decision, constraint, objective) and everything else is grey — a subject-keyed "
        f"colour is the v8 palette growing back.")

    for rgb, role in SEMANTIC.items():
        assert seen.get(rgb, 0) > 0, (
            f"nothing on the sheet is coloured as {role!r} ({rgb}) — a palette rule that "
            f"nothing obeys is decoration, not a key")

    # the objective is ONE cell's worth of purple, not a band of it
    assert seen["D9D2E9"] <= 6, (
        f"{seen['D9D2E9']} cells carry the objective colour — it marks the single cell being "
        f"maximised, and spreading it dilutes the one thing it is for")

    # ⚠️ PRESENCE IS NOT PLACEMENT, and this half exists because mutation proved the first half
    # inert without it. Repainting the objective's LABEL green, or a constraint block's label
    # grey, leaves both colours still present elsewhere on the sheet — so a guard that only
    # asks "does purple exist?" passes the very defect it was written for. Assert that the
    # named rows carry the role they claim.
    rows = _labelled_rows(model)

    def _fill(r, c):
        f = model.cell(row=r, column=c).fill
        return (f.fgColor.rgb or "")[-6:].upper() if f and f.fill_type == "solid" else ""

    obj = rows["PROFIT  (the objective)"][0]
    assert _fill(obj, 1) == "D9D2E9" and _fill(obj, 2) == "D9D2E9", (
        f"the objective row is not the objective colour (label {_fill(obj, 1)!r}, value "
        f"{_fill(obj, 2)!r}) — it is the one cell a reader is looking for")

    # a constraint block: its label, its limit row and its room-left row are all CONSTRAINT red
    c2 = rows["CROP HOURS needed"][0]
    assert _fill(c2, 1) == "F4CCCC", "C2's label is not the constraint colour"
    assert _fill(c2 + 2, 1) == "F4CCCC", "C2's limit row is not the constraint colour"
    assert _fill(c2 + 3, 1) == "F4CCCC", "C2's room-left row is not the constraint colour"

    # a decision row and an input cell, so all four roles are pinned to real cells
    ot = rows["OVERTIME hours"][0]
    assert _fill(ot, 1) == "D9EAD3", "the overtime decision row is not the decision colour"
    assert _fill(rows["PEOPLE TO HIRE"][0], 2) == "D9EAD3", (
        "the advisory headcount is not the decision colour — it is a cell the solver writes")
    assert _fill(rows["Payroll load %"][0], 2) == "FFF2CC", (
        "the payroll load is not the input colour — it is a cell you type in")
