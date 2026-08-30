"""
The toy model's numbers must not drift from the app's.

`toy_models/farm_toy_v6_cash.xlsx` exists to be an INDEPENDENT check on the app's
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

Regenerate with:  python3 toy_models/build_toy_v6.py
"""
import json
import re

import pytest

from tests.helpers import REPO

openpyxl = pytest.importorskip("openpyxl")

WORKBOOK = REPO / "toy_models" / "farm_toy_v6_cash.xlsx"
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
        pytest.skip(f"{WORKBOOK.name} not built; run toy_models/build_toy_v6.py")
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
    for r in range(1, 40):
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

    hdr = next(r for r in range(1, 40) if model.cell(row=r, column=1).value == "Succession")
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
    for r in range(1, 60):
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
    """Run toy_models/verify_toy_v6.py — it CALCULATES the workbook.

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

    r = subprocess.run([str(venv), str(REPO / "toy_models" / "verify_toy_v6.py")],
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
