"""
The toy model's numbers must not drift from the app's.

`toy_models/farm_toy_v12_fixed_layer.xlsx` exists to be an INDEPENDENT check on the app's
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

Regenerate with:  .venv/bin/python toy_models/build_toy_v12.py
"""
import json
import re

import pytest

from tests.helpers import REPO

openpyxl = pytest.importorskip("openpyxl")

WORKBOOK = REPO / "toy_models" / "farm_toy_v12_fixed_layer.xlsx"
TOY_CROPS = ("Spinach", "Kale", "Garlic")          # the three read straight from the app
# v12 adds a zone variant and a perennial. They are the toy's own (FX.0), so the DRIFT tests
# stay on the three app crops and every structural test runs over all five.
ALL_CROPS = TOY_CROPS + ("Tunnel Spinach", "Asparagus")
# v5 carries EVERY succession the app offers. A hand-picked subset is the exact defect it
# exists to remove, so the list is derived, never typed.
def _all_successions():
    import json
    from farm_v2.utils.calendar import generate_successions
    p = json.load(open(REPO / "tests" / "golden" / "default_farm_payload.json"))
    return generate_successions([c for c in p["crops"] if c["name"] in TOY_CROPS], 2024)


PICKED = [s["name"] for s in _all_successions()]


def _sheet_succession_rows(model):
    """{name: row} for every calendar row, by content (col B is a crop, col C a number)."""
    out = {}
    for r in range(1, model.max_row + 1):
        a, b = model.cell(row=r, column=1).value, model.cell(row=r, column=2).value
        if isinstance(a, str) and b in ALL_CROPS and isinstance(
                model.cell(row=r, column=3).value, (int, float)):
            out[a] = r
    return out


def _zoned(name):
    """Every spelling a planting can carry on the sheet: bare (one zone) or '<name> F'/'<name> T'."""
    return [name, f"{name} F", f"{name} T"]


@pytest.fixture(scope="module")
def model():
    if not WORKBOOK.exists():
        pytest.skip(f"{WORKBOOK.name} not built; run toy_models/build_toy_v12.py")
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
            f"import json, toy_v12_lp as lp\n" + body)
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
    # v12: the WHOLE name before the dash — "TUNNEL SPINACH  —  cold store" starts "TUNNEL".
    _up = {c.upper() for c in ALL_CROPS}
    heads = [r for r in range(1, ws.max_row + 1)
             if isinstance(ws.cell(row=r, column=1).value, str)
             and ws.cell(row=r, column=1).value.endswith("store")
             and ws.cell(row=r, column=1).value.split("  —  ")[0] in _up]
    blocks = {}
    for i, r in enumerate(heads):
        stop = heads[i + 1] if i + 1 < len(heads) else ws.max_row + 1
        seq = {}
        for rr in range(r + 1, stop):
            lv = ws.cell(row=rr, column=1).value
            if isinstance(lv, str) and lv.strip():
                seq.setdefault(lv.strip(), rr)
        blocks[ws.cell(row=r, column=1).value.split("  —  ")[0]] = seq
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
    rows = _sheet_succession_rows(model)
    # (1) every planting the APP's generator offers for the three app crops is on the sheet,
    # in at least one zone — read from the app, not from the toy's own oracle.
    missing = [n for n in PICKED if not any(z in rows for z in _zoned(n))]
    assert not missing, (
        f"{len(missing)} of {len(PICKED)} successions the app offers are absent from the "
        f"calendar (e.g. {missing[:4]}) — the solver cannot choose a week it is not shown")
    # (2) and the sheet carries EXACTLY the oracle's set — no more, no fewer (zones, variant,
    # perennial included). Two sources, because either alone can agree with a wrong sheet.
    names = _lp_probe("print(json.dumps([s['name'] for s in lp.SUCCS]))")
    assert sorted(rows) == sorted(names), (
        f"sheet and oracle disagree on the calendar: only on sheet "
        f"{sorted(set(rows) - set(names))[:4]}, only in oracle {sorted(set(names) - set(rows))[:4]}")


def test_the_phase_pattern_matches_the_apps_generator(model):
    """Each planting's P/G/H row must be the calendar the app would build for that start week."""
    from farm_v2.utils.calendar import harvest_weeks_of
    succ = {}
    for x in _all_successions():
        for z in _zoned(x["name"]):
            succ[z] = x                      # a zoned copy carries the SAME calendar
    checked = 0
    for r in range(1, model.max_row + 1):
        name = model.cell(row=r, column=1).value
        if name not in succ or model.cell(row=r, column=2).value not in TOY_CROPS:
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
    # EXACT, over every app-crop row on the sheet (Kale carries an F and a T copy). `>=` let a
    # missing row hide behind Kale's duplicates (code-review).
    want_rows = sum(1 for r in range(1, model.max_row + 1)
                    if model.cell(row=r, column=1).value in succ
                    and model.cell(row=r, column=2).value in TOY_CROPS)
    assert checked == want_rows and checked >= len(PICKED), (
        f"checked {checked} plantings, expected {want_rows} (app offers {len(PICKED)})")


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

@pytest.mark.parametrize("crop", [c.upper() for c in ALL_CROPS])
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


@pytest.mark.parametrize("crop", [c.upper() for c in ALL_CROPS])
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
    # derived from the payload / crop table's own pool column, never a typed list
    pool = {}
    for r in range(1, model.max_row + 1):
        a = model.cell(row=r, column=1).value
        if a in ALL_CROPS and model.cell(row=r, column=5).value in ("Cold", "Ambient"):
            pool[a.upper()] = model.cell(row=r, column=5).value
    assert set(pool) == set(b), f"pool column not found for every crop: {sorted(pool)}"
    w2 = _wl(model, 2)
    for crop, p in pool.items():
        ref = f"{w2}{b[crop]['ROOM OCCUPANCY']}"
        inside, outside = (cold, amb) if p == "Cold" else (amb, cold)
        assert ref in inside, f"{crop} ({p}) is missing from its own pool"
        assert ref not in outside, f"{crop} ({p}) is counted in the OTHER pool"


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
    # ⚠️ DETECTED BY CONTENT, not by column A's label. The planting calendar's strip reads
    # "Succession | Crop | ACRES | PLANT? | 1 | 2 | 3 ..." — it IS a week strip, and a guard
    # keyed to the word "Week" reported a 68-row gap across a table that has one. Same family
    # as the crew-table and dead-input false positives: the guard's model of the thing was
    # narrower than the sheet's, and a guard that cries wolf teaches you to ignore it.
    strips = [r for r in range(1, model.max_row + 1)
              if model.cell(row=r, column=_wc(model, 1)).value == 1
              and model.cell(row=r, column=_wc(model, 52)).value == 52
              and model.cell(row=r, column=_wc(model, 26)).value == 26]
    assert len(strips) >= 6, f"only {len(strips)} week strips; every band needs one"
    # ⚠️ THE PLANTING CALENDAR IS EXEMPT, AND FOR A STRUCTURAL REASON, NOT A COSMETIC ONE.
    # It is 68 rows addressed as ONE RANGE (ROW_SUCC..ROW_SUCC_END) by every SUMPRODUCT that
    # reads it. Interleaving week strips to satisfy this rule pushed two successions out of
    # that range and silently changed the model — measured: "2 of 68 successions absent".
    # A readability rule that breaks the thing it is decorating is the wrong rule here.
    succ_lo = succ_hi = None
    for r in range(1, model.max_row + 1):
        if str(model.cell(row=r, column=1).value or "").strip() == "Succession":
            succ_lo = r
        elif succ_lo and not succ_hi and str(model.cell(row=r, column=2).value or "").strip() \
                not in {n for n in _crop_blocks(model)}:
            if str(model.cell(row=r, column=1).value or "").strip().startswith("5 "):
                succ_hi = r
    gaps = [(b - a, a, b) for a, b in zip(strips, strips[1:])]
    bad = [(g, a, b) for g, a, b in gaps
           if g >= 30 and not (succ_lo and a <= succ_lo and b >= succ_lo)]
    assert not bad, (f"a {bad[0][0]}-row gap between week strips (rows {bad[0][1]}-{bad[0][2]}) "
                     f"— too far to read against")


def test_every_constraint_reads_as_an_inequality(model):
    """LHS row / '<=' row / limit row — the original Group 5 model's own layout.

    Copied from 'Model' rows 16-18 of the source workbook (Available Land / <= / 1). The grower
    wrote that sheet, so it is the one shape here that needs no explaining.
    """
    rows = _labelled_rows(model)
    for label in ("LAND in the ground — Open field", "LAND in the ground — High tunnel",
                  "COLD STORE", "AMBIENT STORE"):
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
    for zone in ("Open field", "High tunnel"):
        f = model.cell(row=rows[f"LAND in the ground — {zone}"][0], column=_wc(model, 2)).value
        assert "SUMPRODUCT" in f, f"land row should sum across the whole calendar, got {f!r}"
        assert '<>""' in f, "land row should read the phase strip for that WEEK, not an annual total"
        # v12 / FX.4: and only ITS OWN zone's plantings — a tunnel acre is not a field acre
        assert f'="{zone}"' in f, f"{zone} land row does not filter on its zone: {f!r}"


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
        # v12: the changing cells are every PLANTABLE row — the committed perennial is an
        # input, and naming it as a changing cell would let the solver dig it up.
        plantable = [n for n, r in _sheet_succession_rows(model).items()
                     if model.cell(row=r, column=2).value != "Asparagus"]
        assert rows == len(plantable), (
            f"the READ ME's {what} range {letter}{top}:{letter}{bot} covers {rows} rows, but the "
            f"sheet offers {len(plantable)} plantings — a partial range silently recreates v4's "
            f"hand-picked-calendar defect, and one row too many hands the perennial to the solver")
        assert model.cell(row=top, column=1).value in plantable
        assert model.cell(row=bot, column=1).value in plantable


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
            and model.cell(row=r, column=1).value in ALL_CROPS)
    assert n == len(ALL_CROPS) * 2, f"expected {len(ALL_CROPS) * 2} crop x channel rows, found {n}"


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
    """Run toy_models/verify_toy_v12.py — it CALCULATES the workbook.

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

    # ⚠️ RAISED FROM 600s AT v11, AND THE REASON MATTERS. The verifier now does ~23 full
    # workbook recalculations — 6 exact fixtures plus 16 input-propagation nudges — against a
    # sheet that grew from 356 rows to 401 and from 552 decision cells to 765. It takes ~13
    # minutes and it is not looping; it is doing more work because the model does more.
    #
    # The tempting fix was to cut checks until they fit the old budget. That is backwards: the
    # propagation nudges test whether an INPUT IS WIRED, which the exact comparisons cannot see
    # at fixed inputs, so none of them is redundant. Cost is tracked as backlog L10 — the
    # answer there is to make each recalculation cheaper, not to run fewer of them.
    r = subprocess.run([str(venv), str(REPO / "toy_models" / "verify_toy_v12.py")],
                       capture_output=True, text=True, cwd=REPO, timeout=2700)
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


def test_hiring_is_more_of_a_role_you_already_listed(model):
    """v11 / the grower's design — the hire decision lives ON the roster, not beside it.

    v10 invented a 'proposed hire' block with its own window, wage, hours and field%: eight
    inputs to re-describe something `employees[]` already describes, and the same error v9 made
    with spot hire. Extra heads now inherit their role's everything, so a different window or
    wage is a different ROW, not another knob.
    """
    rows = _labelled_rows(model)
    hdr = None
    for r in range(1, model.max_row + 1):
        if str(model.cell(row=r, column=1).value or "").strip() == "Position":
            hdr = r
            break
    assert hdr, "the crew table header is missing"
    cols = {str(model.cell(row=hdr, column=c).value or "").strip(): c for c in range(1, 14)}
    for want in ("Hire more?", "Max more", "EXTRA HIRED", "Room left"):
        assert want in cols, f"the crew table has no {want!r} column: {sorted(cols)}"
    assert "Proposed hire" not in rows, (
        "v10's separate proposed-hire block is still on the sheet — hiring is supposed to be "
        "a column on the roster now, not a second description of a roster row")

    # EXTRA HIRED is the solver's; the other two are the grower's
    r0 = hdr + 1
    assert model.cell(row=r0, column=cols["EXTRA HIRED"]).fill.fgColor.rgb[-6:].upper() \
        == "D9EAD3", "EXTRA HIRED is not a decision cell"
    for want in ("Hire more?", "Max more"):
        assert model.cell(row=r0, column=cols[want]).fill.fgColor.rgb[-6:].upper() == "FFF2CC", \
            f"{want} is not an input cell"


def test_extra_heads_inherit_their_role_and_are_gated_by_its_toggle(model):
    """The hours and the cost must both read the ROLE'S own cells, and both obey the toggle.

    If the hours row read a wage, or the cost row read productivity, the two halves would have
    drifted apart — which is exactly what a separate hire block made easy.
    """
    rows = _labelled_rows(model)
    a_hdr = rows["A — WHO IS ON, WEEK BY WEEK"][0]
    d_hdr = rows["D — WHAT IT COSTS"][0]
    w = _wc(model, 20)
    pos_rows = [r for r in range(a_hdr, rows["CREW CAPACITY"][0])
                if str(model.cell(row=r, column=2).value or "").startswith("hrs")]
    assert pos_rows, "no per-position hour rows in block A"
    for r in pos_rows:
        f = str(model.cell(row=r, column=w).value)
        assert '$I$' in f, f"row {r} does not read the Hire more? toggle: {f!r}"
        assert '$K$' in f, f"row {r} does not read EXTRA HIRED: {f!r}"
        # productivity discounts the HOURS
        assert any(str(rr) in f for rr in [rows["New-hire productivity %"][0]]), (
            f"row {r}'s hours are not discounted by productivity: {f!r}")
    # a week strip also carries "$" in column 2; a real cost row has a formula in a week column
    cost_rows = [r for r in range(d_hdr, rows["Wage bill this week"][0])
                 if str(model.cell(row=r, column=2).value or "").strip() == "$"
                 and str(model.cell(row=r, column=w).value or "").startswith("=")]
    assert cost_rows, "no per-position cost rows in block D"
    prod_row = rows["New-hire productivity %"][0]
    for r in cost_rows:
        f = str(model.cell(row=r, column=w).value)
        assert '$K$' in f, f"cost row {r} ignores extra heads: {f!r}"
        assert f"$B${prod_row}" not in f, (
            f"cost row {r} discounts the WAGE by productivity — you pay a new hand their full "
            f"wage and get less work out of them; the discount is on the hours. Got {f!r}")


def test_overtime_is_per_role_with_no_blended_rate(model):
    """v11 / the grower's fix, and it is what keeps the model linear.

    Once extra heads are a decision, a blended overtime rate depends on a decision variable and
    `hours x blend` stops being an LP. Per role the rate is that role's own wage x load x
    multiplier — a constant. It is also strictly better: with one blend an overtime hour costs
    the same whoever works it, so the plan cannot prefer the cheap one.
    """
    rows = _labelled_rows(model)
    b_lo, b_hi = rows["B — WHAT YOU CAN ADD"][0], rows["HOURS AVAILABLE"][0]
    caps = [r for r in range(b_lo, b_hi)
            if str(model.cell(row=r, column=1).value or "").strip().endswith("— overtime CAP")]
    hrs = [r for r in range(b_lo, b_hi)
           if str(model.cell(row=r, column=1).value or "").strip().endswith("— OVERTIME hrs")]
    assert len(caps) >= 2 and len(caps) == len(hrs), (
        f"expected one cap and one hours row per hourly role, got {len(caps)}/{len(hrs)}")
    w = _wc(model, 20)

    # no blended-rate row survives anywhere
    # ⚠️ Only LABELLED DATA ROWS count — a note that explains why the blend is gone is not a
    # blend. Matching prose was my own guard crying wolf on its own documentation.
    for lab, rr in rows.items():
        if not any(str(model.cell(row=x, column=w).value or "").startswith("=") for x in rr):
            continue
        assert "blend" not in lab.lower(), (
            f"a blended-rate row is still on the sheet ({lab!r}) — v11 removed the blend, it "
            f"did not work around it")

    # each cap reads ITS OWN role's hours row, and the allowance
    allow = ("B", rows["Overtime ALLOWANCE"][0])
    for cr in caps:
        reads = _refs(model.cell(row=cr, column=w).value)
        assert allow in reads, f"cap row {cr} does not read the allowance"
        assert not any(rr == rows["CREW CAPACITY"][0] for _, rr in reads), (
            f"cap row {cr} reads CREW CAPACITY, which includes salaried staff — they cannot "
            f"work overtime")
    # the cost row prices each role at ITS OWN wage
    cost = str(model.cell(row=rows["Overtime cost this week"][0], column=w).value)
    for hr in hrs:
        assert f"{_wl(model, 20)}{hr}" in cost, f"overtime cost ignores row {hr}"
    assert cost.count("$D$") == len(hrs), (
        f"overtime cost does not price each role at its own wage column: {cost!r}")
    assert "-" not in cost.replace("=", ""), (
        f"the overtime cost has a subtraction — charging the premium instead of the full rate "
        f"is the W12b defect. Got {cost!r}")


def test_overtime_is_stated_once_not_restated_as_a_triplet(model):
    """v11: the grower found 21 rows that restated a constraint the recipe already makes.

    Each role used to get a full constraint block here whose 'used' row was an alias of its
    decision row and whose 'limit' row was an alias of its cap row — referenced by nothing:
    not the Solver recipe (which constrains the decision against the cap directly), not the
    verifier, not a test. Only the slack was worth keeping, so what remains is one room-left
    row per role, and it must actually be cap minus used.
    """
    rows = _labelled_rows(model)
    w = _wc(model, 20)
    roles = [lab[:-len(" — OVERTIME hrs")] for lab in rows
             if lab.endswith(" — OVERTIME hrs")]
    assert roles, "no per-role overtime rows found"
    for role in roles:
        assert f"OVERTIME — {role}" not in rows, (
            f"{role} still has an alias triplet — the constraint is stated in the recipe")
        room = f"{role} — overtime room left"
        assert room in rows, f"{role} has no room-left row"
        got = _refs(model.cell(row=rows[room][0], column=w).value)
        want = {rows[f"{role} — overtime CAP"][0], rows[f"{role} — OVERTIME hrs"][0]}
        assert {r for _, r in got} == want, (
            f"{room} must read its own cap and its own overtime, got rows "
            f"{sorted(r for _, r in got)} not {sorted(want)}")


def test_piece_rate_is_per_crop_and_floored_by_the_minimum_wage(model):
    """v11 — and the floor is why real rates differ by crop.

    A piece-rate worker must still earn the minimum wage for hours worked; if the rate falls
    short the employer makes up the difference (FLSA; the AEWR under H-2A). Converted to $/lb
    that floor depends on picking speed, a 3.6x spread here. A rate below its floor is
    inoperative — you pay the floor — and nothing about that is optional.
    """
    rows = _labelled_rows(model)
    assert "Minimum wage floor $/hr" in rows, "the wage floor input is missing"
    floor_row = rows["Minimum wage floor $/hr"][0]
    hdr = None
    for r in range(1, model.max_row + 1):
        if str(model.cell(row=r, column=2).value or "").strip() == "$ per bushel":
            hdr = r
            break
    assert hdr, "the per-crop piece-rate table is missing"
    # stop at the first row without a formula in the floor column — the note rows and the
    # week strip below the table both have content in columns 1 and 2
    crop_rows = [r for r in range(hdr + 1, hdr + 8)
                 if str(model.cell(row=r, column=5).value or "").startswith("=")]
    assert len(crop_rows) >= 3, f"expected a rate row per crop, got {crop_rows}"
    for r in crop_rows:
        floor_f = str(model.cell(row=r, column=5).value)
        eff_f = str(model.cell(row=r, column=6).value)
        assert f"$B${floor_row}" in floor_f, (
            f"row {r}'s floor does not read the minimum wage: {floor_f!r}")
        # ⚠️ derived from the sheet's OWN yield and harvest-hour cells, not baked in as a
        # literal — that is the v7 defect ("the sheet used numbers it could not show")
        assert "$B$" in floor_f and "$P$" in floor_f, (
            f"row {r}'s floor bakes the crop's numbers in as literals: {floor_f!r}")
        assert eff_f.startswith("=MAX("), (
            f"row {r}'s effective rate is not max(entered, floor): {eff_f!r}")
    # one crop ships BELOW its floor on purpose, so the mechanism is visible and testable
    import subprocess, json
    d = _lp_probe("r = lp.solve()\n"
                  "print(json.dumps({'eff': r['piece_eff'], 'floor': r['piece_floor'],"
                  " 'entered': lp.piece_rates_per_lb()}))")
    below = [c for c in d["entered"] if d["entered"][c] < d["floor"][c] - 1e-12]
    assert below, ("no shipped rate is below its floor, so the make-up-pay path is never "
                   "exercised — the same 'defaulting a feature off leaves it unguarded' trap "
                   "this project has hit three times")
    for c in below:
        assert abs(d["eff"][c] - (d["floor"][c] + 0.02)) < 1e-9, (
            f"{c}: the floor is not being applied — entered {d['entered'][c]:.4f}, "
            f"floor {d['floor'][c]:.4f}, effective {d['eff'][c]:.4f}")


def test_piece_rate_relieves_harvest_hours_and_no_others(model):
    """The pounds change the HOURS you need, not the wages you owe — and only harvest hours.

    The committed crew is paid either way, so there is no double-count to prevent; what there
    is, is a relief. Bounded by the harvest hours actually needed, or pickers would be
    relieving the planting — free labour wearing a piece rate.
    """
    rows = _labelled_rows(model)
    for lab in ("Harvest hours relieved", "HARVEST hours needed"):
        assert lab in rows, f"missing {lab!r}"
    w = _wc(model, 20)
    rel = str(model.cell(row=rows["Harvest hours relieved"][0], column=w).value)
    # v11: the conversion has ONE definition, in the piece-rate block, where the crew's own
    # capacity is measured against it in the same unit. This row carries it into the labour
    # block. So follow the reference to its definition rather than demanding the arithmetic
    # appear here — asserting the shape of the row in front of you is how a guard ends up
    # pinned to a layout instead of to the intent.
    if _refs(rel) and "$P$" not in rel:
        assert len(_refs(rel)) == 1, f"relief reads {len(_refs(rel))} cells, expected one: {rel!r}"
        _src = next(iter(_refs(rel)))[1]
        assert model.cell(row=_src, column=1).value.strip() == "picking hours used", (
            f"relief points at row {_src}, which is not the picking-hours definition")
        rel = str(model.cell(row=_src, column=w).value)
    assert "$P$" in rel and "$B$" in rel, (
        f"relief is not derived from yield / harvest-hours on the sheet: {rel!r}")
    # it must NOT be added to hours available — it comes off the demand side
    avail = _refs(model.cell(row=rows["HOURS AVAILABLE"][0], column=w).value)
    assert not any(rr == rows["Harvest hours relieved"][0] for _, rr in avail), (
        "piece-rate relief has been added to HOURS AVAILABLE — it belongs on the demand side, "
        "and counting it as supply would let it relieve planting hours too")
    c2 = str(model.cell(row=rows["CROP HOURS needed"][0], column=w).value)
    assert f"-{_wl(model, 20)}{rows['Harvest hours relieved'][0]}" in c2, (
        f"C2 does not subtract the relief: {c2!r}")


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
        "toy_v12_lp", REPO / "toy_models" / "toy_v12_lp.py")
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)

    # a zero multiplier prices an overtime hour at $0 while every wage on the roster is healthy
    with pytest.raises(RuntimeError, match="free labour"):
        lp.solve(flex=True, overtime_multiplier=0.0)

    # ⚠️ and the OTHER axis, which v9 moved: there is no hired-wage input any more, so the way
    # to get free labour now is an advisory crew with no wage. Checking only the overtime side
    # would leave this half unguarded — the same two-axis mistake v8 recorded.
    # ⚠️ the OTHER axis, which v11 moved again: with per-role rates the way to get free labour
    # is a role whose own wage is zero. A blend could hide one unpaid role behind three paid
    # ones, which is why the refusal is now per role.
    import copy
    saved = copy.deepcopy(lp.PAYLOAD["employees"])
    try:
        for e in lp.PAYLOAD["employees"]:
            if e["type"] == "seasonal":
                e["wage"] = 0.0
        with pytest.raises(RuntimeError, match="free labour"):
            lp.solve()
    finally:
        lp.PAYLOAD["employees"] = saved


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
    ot = [r for r in range(rows["B — WHAT YOU CAN ADD"][0], rows["HOURS AVAILABLE"][0])
          if str(model.cell(row=r, column=1).value or "").strip().endswith("— OVERTIME hrs")]
    assert ot, "no per-role overtime decision rows found"
    for r in ot:
        assert _fill(r, 1) == "D9EAD3", f"overtime row {r} is not the decision colour"
    # EXTRA HIRED, on the roster
    hdr = next(r for r in range(1, model.max_row + 1)
               if str(model.cell(row=r, column=1).value or "").strip() == "Position")
    assert _fill(hdr + 1, 11) == "D9EAD3", (
        "EXTRA HIRED is not the decision colour — it is a cell the solver writes")
    assert _fill(rows["ENGAGED?"][0], 2) == "D9EAD3", (
        "the piece-rate engage switch is not the decision colour")
    assert _fill(rows["Payroll load %"][0], 2) == "FFF2CC", (
        "the payroll load is not the input colour — it is a cell you type in")


# ---------------------------------------------------------------------------
# 5 — v12: the fixed layer (PLAN Batch FX.0, DECISIONS GROUP G)
# ---------------------------------------------------------------------------

def test_a_variant_cannot_take_a_second_market(model):
    """FX.5's trap: demand caps keyed by crop NAME give two variants the whole market each.

    Two halves, because either alone is inert. The ORACLE must hold the two spinaches under one
    Farmers Market ceiling — and must exceed it when keyed by name (`share_caps=False`), or the
    first assertion could pass on a model where the cap never binds at all. The SHEET must
    measure the ceiling against the identity's TOTAL and give the variant no ceiling of its own.
    """
    d = _lp_probe(
        "fm = next(h for h in lp.CH_NAMES if h.startswith('Farmers'))\n"
        "cap = lp.cap_spec('Spinach', fm)[1]\n"
        "out = {}\n"
        "for tag, kw in (('shared', {}), ('by_name', {'share_caps': False})):\n"
        "    r = lp.solve(**kw)\n"
        "    out[tag] = max(sum(r['offered'][(c, fm)][w] for c in lp.CROP_NAMES\n"
        "                       if lp.identity(c) == 'Spinach') for w in range(52))\n"
        "out['cap'] = cap\n"
        "print(json.dumps(out))")
    assert d["shared"] <= d["cap"] + 1e-6, (
        f"the two spinaches together sell {d['shared']:,.0f} lb in a week against a "
        f"{d['cap']:,.0f} lb ceiling — a second NAME has become a second MARKET")
    assert d["by_name"] > d["cap"] + 1, (
        f"keyed by name the spinaches still sell only {d['by_name']:,.0f} lb — the cap never "
        f"binds, so the assertion above proves nothing")
    # the sheet: the variant has no ceiling row, and its identity's ceiling reads the total
    blocks = _crop_blocks(model)
    assert not any(k.endswith("most you may sell this week") for k in blocks["TUNNEL SPINACH"]), (
        "Tunnel Spinach has a ceiling row of its own — the trap, on the sheet")
    rows = _labelled_rows(model)
    tot = [lab for lab in rows if lab.startswith("Spinach / Farmers Market — SOLD, every name")]
    assert len(tot) == 1, f"no single total row for the Spinach market: {tot}"
    w = _wc(model, 20)
    f = str(model.cell(row=rows[tot[0]][0], column=w).value)
    want = {blocks["SPINACH"]["Farmers Market — SOLD"], blocks["TUNNEL SPINACH"]["Farmers Market — SOLD"]}
    assert {r for _, r in _refs(f)} == want, f"the market total does not sum both names: {f!r}"
    cap = str(model.cell(row=blocks["SPINACH"]["Farmers Market — most you may sell this week"],
                         column=w).value)
    # ⚠️ PARSED, not substring-matched. `"Annual" in cap` was always true — every ceiling's
    # formula carries the =IF($C="Annual",...) test — so this half could never fail (code-review).
    read = {r for _, r in _refs(cap)}
    assert rows[tot[0]][0] in read, (
        f"the Spinach ceiling's running allowance does not subtract the identity TOTAL "
        f"(row {rows[tot[0]][0]}): {cap!r}")
    assert blocks["SPINACH"]["Farmers Market — SOLD"] not in read, (
        "the shared ceiling subtracts Spinach's own sales only — Tunnel Spinach is invisible to it")


def test_must_plant_is_unconditional_and_min_acreage_is_not(model):
    """FX.1: the floor forces the crop IN; 'min acres if planted' can be escaped by not planting.

    Make garlic ruinous to grow. Without a floor the solver plants none (the escape — PLAN FX.1
    measured it on the app: a 14-acre garlic floor via min acreage -> 0 acres). With a standing
    floor it must plant the floor anyway, and pay for it.
    """
    d = _lp_probe(
        "lp.CROPS['Garlic']['seed_transplant_cost_per_acre'] = 60000.0\n"
        "free = lp.solve(must_stand=[], must_annual={})\n"
        "held = lp.solve(must_stand=[('Garlic', 5.0, 1, 1)], must_annual={})\n"
        "g = lambda r: sum(v for k, v in r['acres'].items() if k.startswith('Garlic'))\n"
        "print(json.dumps([g(free), g(held), free['obj_value'] - held['obj_value']]))")
    free, held, cost = d
    assert free < 1e-6, f"garlic at $60,000/ac seed is still planted ({free:.2f} ac) — the fixture is not hostile"
    assert held >= 5.0 - 1e-6, f"a 5-acre must-plant floor planted {held:.2f} ac — it was escaped"
    assert cost > 0, "the floor cost nothing, so it never bound"
    # and on the sheet: no floor row reads a PLANT? binary
    rows = _labelled_rows(model)
    for lab in [l for l in rows if l.endswith(" standing") or l.endswith(" planted this year")]:
        r = rows[lab][0]
        f = str(model.cell(row=r, column=_wc(model, 20)).value or model.cell(row=r, column=2).value)
        assert "$D$" not in f, f"{lab!r} reads the PLANT? column — a floor that can be switched off: {f!r}"


def test_an_unmeetable_contract_is_a_shortfall_not_infeasible():
    """Grower ruling G3: the plan always solves and the shortfall is reported.

    Order more kale than the farm could ever grow. A hard floor makes this infeasible; the slack
    must carry it instead, never short by more than was ordered, and price every pound.
    """
    d = _lp_probe(
        "c = [('Kale', 'Wholesale', 1_000_000.0, 20, 22, 0.10)]\n"
        "r = lp.solve(contracts=c)\n"
        "print(json.dumps([r['short_lb'][0], r['shortfall_cost'], max(r['short'].values())]))")
    short, cost, worst = d
    assert short > 2_000_000, f"only {short:,.0f} lb short of a 3,000,000 lb order — not credible"
    assert worst <= 1_000_000 + 1e-6, f"short {worst:,.0f} lb in a week that owed 1,000,000"
    assert abs(cost - short * 0.10) < 1e-3, "the shortfall is not priced at the contract's penalty"


def test_the_perennial_is_committed_ground_outside_the_calendar(model):
    """FX.2: the calendar refuses cycles over 52 weeks, so a perennial is written straight in.

    Its acres are an INPUT (the grower already has them), its row sits OUTSIDE the solver's
    changing cells, it stands in all 52 weeks, and its cost line reads the depreciation block —
    establishment over its life, never this year's seed.
    """
    from farm_v2.utils.calendar import generate_successions
    asparagus = dict(name="Asparagus", planting_weeks=1, harvest_weeks=8, days_to_maturity=700,
                     seasons=[{"start": "04-01", "end": "04-15"}])
    with pytest.raises(ValueError, match="52-week"):
        generate_successions([asparagus], 2024)
    rows = _sheet_succession_rows(model)
    r = rows["Asparagus"]
    def _rgb(c):
        f = model.cell(row=r, column=c).fill
        return (f.fgColor.rgb or "")[-6:].upper() if f and f.fill_type == "solid" else ""
    assert _rgb(3) == "FFF2CC", "the perennial's acres are not an input"
    assert str(model.cell(row=r, column=4).value).startswith("="), "its PLANT? is not derived"
    assert all(model.cell(row=r, column=_wc(model, w)).value in ("G", "H") for w in range(1, 53)), (
        "the perennial does not stand all 52 weeks")
    assert max(rows.values()) == r, "the perennial must be the LAST calendar row"
    labels = _labelled_rows(model)
    est = labels["Establishment $/acre"][0]
    per_wk = labels["-> $/acre per week"][0]
    f = str(model.cell(row=per_wk, column=2).value)
    assert f"$B${est}" in f and f"$B${labels['Bearing life, years'][0]}" in f, (
        f"establishment is not depreciated over the bearing life: {f!r}")
    crop_r = next(x for x in labels["Asparagus"] if model.cell(row=x, column=8).value is not None)
    seed = model.cell(row=crop_r, column=8)
    assert seed.value in (0, "=0"), f"the perennial carries a seed cost: {seed.value!r}"
    # and it is not a box you can type in — a seed cost means nothing for committed ground
    assert (seed.fill.fgColor.rgb or "")[-6:].upper() != "FFF2CC", "the perennial's seed is an input"


def test_eligibility_is_wired_into_max_acres(model):
    """FX.4: a Y/N nobody reads is a dead input. Every tunnel planting's C9 helper must read it."""
    hdr = _labelled_rows(model)["Succession"][0]
    cols = {model.cell(row=hdr, column=c).value: c for c in range(1, model.max_column + 1)
            if model.cell(row=hdr, column=c).value}
    assert "zone" in cols, "the calendar has no zone column"
    seen = 0
    for name, r in _sheet_succession_rows(model).items():
        if model.cell(row=r, column=cols["zone"]).value != "High tunnel":
            continue
        f = str(model.cell(row=r, column=cols["max if planted"]).value)
        assert '="Y"' in f, f"{name}: max-if-planted ignores the zone eligibility: {f!r}"
        seen += 1
    assert seen >= 2, f"only {seen} tunnel plantings found"


def test_a_zone_the_farm_lacks_grows_nothing():
    """Found while measuring FX.0: drop the tunnel and its plantings had NO land row at all.

    The oracle then 'grew' tunnel spinach on no ground and reported the tunnel as COSTING $91k.
    A planting whose zone is not on the farm must be pinned to zero, not left unbounded.
    """
    d = _lp_probe(
        "r = lp.solve(zones=[('Open field', lp.PAYLOAD['total_land'])])\n"
        "print(json.dumps(sum(r['acres'][s['name']] for s in lp.SUCCS\n"
        "                     if s['zone'] == 'High tunnel')))")
    assert d < 1e-9, f"{d:.2f} acres planted in a zone the farm does not have"


def test_committed_perennial_acres_do_not_count_as_planted_this_year():
    """An ANNUAL must-plant floor counts acres PLANTED this year; a perennial is not planted.

    Survived mutation until this existed: the default annual floor is on kale and the perennial
    is asparagus, so counting the perennial changed nothing — the effect needs a floor and a
    perennial with the SAME identity, two conditions at once. Asparagus has no annual plantings,
    so an annual asparagus floor must be unmeetable; counting the 3 committed acres would 'meet' it.
    """
    d = _lp_probe(
        "try:\n"
        "    lp.solve(must_annual={'Asparagus': 1.0})\n"
        "    print(json.dumps('solved'))\n"
        "except RuntimeError as e:\n"
        "    print(json.dumps('refused' if 'must be planted this year' in str(e) else str(e)))")
    assert d == "refused", (
        "an annual floor on the perennial was met — committed acres were counted as this "
        "year's planting")


def test_floors_aggregate_by_identity_not_by_name(model):
    """A floor on an identity sold by TWO names must count both.

    The shipped floors are on garlic and kale, each its own sole name, so name-vs-identity was
    never exercised — every floor guard passed with the aggregation keyed by name (code-review).
    Spinach is the one shared identity, and in weeks 2-3 only TUNNEL spinach can stand: a
    Spinach floor there is meetable only if the variant counts.
    """
    d = _lp_probe(
        "try:\n"
        "    r = lp.solve(must_stand=[('Spinach', 1.0, 2, 3)], must_annual={})\n"
        "    print(json.dumps(sum(r['acres'][s['name']] for s in lp.SUCCS\n"
        "                         if lp.CROP_NAMES[s['crop']] == lp.VARIANT\n"
        "                         and any(((w - 1) % 52) + 1 == 2 for w in s['weeks']))))\n"
        "except RuntimeError as e:\n"
        "    print(json.dumps(str(e)))")
    assert isinstance(d, float) and d >= 1.0 - 1e-6, (
        f"a Spinach floor in weeks 2-3 was not met by Tunnel Spinach: {d!r}")
    # and the SHEET's floor rows read the identity column, never the crop-name column
    hdr = _labelled_rows(model)["Succession"][0]
    cols = {model.cell(row=hdr, column=c).value: c for c in range(1, model.max_column + 1)
            if model.cell(row=hdr, column=c).value}
    id_col = openpyxl.utils.get_column_letter(cols["sells as"])
    rows = _labelled_rows(model)
    for lab in [l for l in rows if l.endswith(" standing") or l.endswith(" planted this year")]:
        r = rows[lab][0]
        f = str(model.cell(row=r, column=_wc(model, 20)).value
                if lab.endswith(" standing") else model.cell(row=r, column=2).value)
        assert f"${id_col}$" in f, f"{lab!r} does not read the 'sells as' column: {f!r}"
        assert "$B$" + str(hdr + 1) not in f, f"{lab!r} reads the crop NAME column: {f!r}"
        if lab.endswith(" planted this year"):
            assert '<>"-"' in f, f"{lab!r} does not exclude the committed perennial: {f!r}"
