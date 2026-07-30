/* CLIENT-SIDE guards for demand saturation (W6) — driven in a real DOM.
 *
 * The Python side is pinned by tests/test_demand_saturation.py (the solver builds it) and
 * tests/test_golden_farm.py (the adapter forwards it, and the shipped farm demonstrates the
 * defect). This file pins the third link: that the CLIENT reads it and cannot rebuild it.
 *
 * WHAT WENT WRONG. The constraint panel and the What-If ranking each computed
 *
 *     sat = min(1, gross annual harvest / this channel's annual cap)
 *
 * with a numerator covering the crop's harvest across EVERY channel. So a crop selling nothing
 * into Wholesale printed a Wholesale saturation, next to a channel pie — built from the real
 * `v` since W1 — showing it selling nothing there. On the shipped farm 10 of 14 rows were
 * overstated by more than 10 points and three sold zero pounds while reading 29%, 16% and 4%.
 *
 * The client also rebuilt the weekly caps from the form, and it ASSIGNED overlapping demand
 * ranges where the solver accumulates them — the client half of S7, on a farm with two buyers
 * wanting the same weeks.
 *
 * THE LOAD-BEARING TEST here is the RECONSTRUCTION GUARD: given a result with a full harvest
 * schedule and a params object full of yields and demand caps, but no demand_saturation, the
 * panel must draw NO demand rows and the ranking must offer NO demand levers. That is the exact
 * input the old code turned into a table of invented percentages.
 *
 * WHY jsdom: renderConstraintSummary writes innerHTML and the CSV exporter reaches into the
 * DOM. Both are driven for real here, not pattern-matched — two inert guards shipped in this
 * codebase because a source-level check looked equivalent. Nothing here needs Pyodide.
 *
 * Run: node tests/demand_saturation_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };
const eq = (name, got, want) => {
  if (got !== want) fail(`${name}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
};

const range = (a, b) => Array.from({ length: b - a + 1 }, (_, i) => a + i);

// Shaped after the shipped farm's real numbers (see test_golden_farm.py):
//   Garlic/FM     — fill 50%, weekly cap binding in all 7 weeks it can supply. THE case.
//   Spinach/WS    — sells nothing; the old formula printed 16% here.
//   Basil/WS      — sells nothing, on an ANNUAL contract; the old formula printed 29%.
//   Tomatoes/WS   — an annual contract that DOES sell, so "—" in the peak column is not
//                   confusable with the zero-sales rows.
const RES = {
  revenue: 1621122,
  demand_at_cap_threshold: 0.95,
  crop_names: ['Spinach', 'Garlic', 'Basil', 'Tomatoes'],
  succession_schedule: [
    { crop: 'Spinach',  acres: 25, weeks: [10, 11, 12], phases: [0, 1, 2], name: 'Spinach #1' },
    { crop: 'Garlic',   acres: 23, weeks: [28, 29, 30], phases: [0, 1, 2], name: 'Garlic #1' },
    { crop: 'Basil',    acres:  6, weeks: [20, 21, 22], phases: [0, 1, 2], name: 'Basil #1' },
    { crop: 'Tomatoes', acres: 11, weeks: [24, 25, 26], phases: [0, 1, 2], name: 'Tomatoes #1' },
  ],
  demand_saturation: {
    'Farmers Market': {
      Garlic: {
        basis: 'weekly', cap_lbs: 28000, sold_lbs: 14000, fill: 0.50,
        peak_week_frac: 1.0, peak_week_cap_lbs: 2000, weeks_at_cap: range(29, 35), binding: 1.0,
      },
      Spinach: {
        basis: 'weekly', cap_lbs: 234000, sold_lbs: 174000, fill: 174000 / 234000,
        peak_week_frac: 1.0, peak_week_cap_lbs: 4500, weeks_at_cap: range(12, 40), binding: 1.0,
      },
    },
    Wholesale: {
      Spinach: {
        basis: 'weekly', cap_lbs: 1300000, sold_lbs: 0, fill: 0,
        peak_week_frac: 0, peak_week_cap_lbs: 25000, weeks_at_cap: [], binding: 0,
      },
      Basil: {
        basis: 'annual', cap_lbs: 150000, sold_lbs: 0, fill: 0,
        peak_week_frac: null, peak_week_cap_lbs: null, weeks_at_cap: [], binding: 0,
      },
      Tomatoes: {
        basis: 'annual', cap_lbs: 900000, sold_lbs: 14000, fill: 14000 / 900000,
        peak_week_frac: null, peak_week_cap_lbs: null, weeks_at_cap: [], binding: 14000 / 900000,
      },
    },
  },
};

// Deliberately rich: yields and every demand-cap variant are present, so the reconstruction
// guard fails loudly if anything starts reading them again to compute a saturation.
const PARAMS = {
  total_land: 80,
  harvest_storage_cap: 500,
  channels: [{ name: 'Wholesale' }, { name: 'Farmers Market' }],
  crops: [
    { name: 'Spinach', yield_per_acre: 8000, harvest_weeks: 2, channels: {
        Wholesale: { demand_cap_type: 'weekly_flat', weekly_demand_lbs: '25000', price_per_lb: '1' },
        'Farmers Market': { demand_cap_type: 'weekly_varying', price_per_lb: '3',
          demand_ranges: [{ weeks: 'W1-W52', weekly_lbs: '4500' }] },
      } },
    { name: 'Garlic', yield_per_acre: 7000, harvest_weeks: 3, channels: {
        'Farmers Market': { demand_cap_type: 'weekly_varying', price_per_lb: '6',
          demand_ranges: [{ weeks: 'W22-W35', weekly_lbs: '2000' }] },
      } },
    { name: 'Basil', yield_per_acre: 7200, harvest_weeks: 4, channels: {
        Wholesale: { demand_cap_type: 'annual', annual_demand_lbs: '150000', price_per_lb: '4' },
      } },
    { name: 'Tomatoes', yield_per_acre: 12000, harvest_weeks: 6, channels: {
        Wholesale: { demand_cap_type: 'annual', annual_demand_lbs: '900000', price_per_lb: '2' },
      } },
  ],
};

/** The demand rows of the rendered panel, as [{label, season, peak, weeks}]. */
function demandRowsOf(window, res, params) {
  const el = window.document.getElementById('constraint-summary-content');
  if (!el) throw new Error('#constraint-summary-content missing — the panel cannot be driven');
  el.innerHTML = '<!-- cleared -->';
  window.renderConstraintSummary(res, params);
  return Array.from(el.querySelectorAll('tr'))
    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim()))
    .filter(c => c.length === 4 && c[0].includes('→'))
    .map(c => ({ label: c[0], season: c[1], peak: c[2], weeks: c[3] }));
}

(async () => {
  const { window } = await bootApp();
  const W = window;

  // ── 1. The panel draws its rows from res.demand_saturation ────────────────
  {
    const rows = demandRowsOf(W, RES, PARAMS);
    eq('row count matches the saturation entries', rows.length, 5);

    const find = lbl => rows.find(r => r.label.startsWith(lbl));

    // THE case: two different, both-correct figures on one row. Collapsing them is the defect.
    const garlic = find('Garlic → Farmers Market');
    ok('Garlic → Farmers Market row exists', !!garlic);
    if (garlic) {
      eq('Garlic/FM season fill is the annual figure', garlic.season, '50%');
      eq('Garlic/FM peak week is the binding weekly figure', garlic.peak, '100%');
      ok(`Garlic/FM lists its at-cap weeks (got "${garlic.weeks}")`, /Wk 29, 30/.test(garlic.weeks));
      ok('Garlic/FM chip says sold, not harvest', /sold \/ cap/.test(garlic.label));
    }

    // The W6 contradiction: sells nothing, must read 0%. Old formula printed 16%.
    const spWs = find('Spinach → Wholesale');
    ok('Spinach → Wholesale row exists', !!spWs);
    if (spWs) {
      eq('Spinach/Wholesale sells nothing so reads 0%', spWs.season, '0%');
      eq('Spinach/Wholesale has no at-cap weeks', spWs.weeks, '—');
    }
  }

  // ── 2. An annual contract shows no weekly ceiling ─────────────────────────
  {
    const rows = demandRowsOf(W, RES, PARAMS);
    const basil = rows.find(r => r.label.startsWith('Basil → Wholesale'));
    const toms  = rows.find(r => r.label.startsWith('Tomatoes → Wholesale'));
    ok('Basil → Wholesale row exists', !!basil);
    ok('Tomatoes → Wholesale row exists', !!toms);
    // `annual/52` is a limit the solver stopped imposing at B4; the panel kept printing it.
    if (basil) eq('Basil/Wholesale peak column is blank (annual contract)', basil.peak, '—');
    if (toms)  eq('Tomatoes/Wholesale peak column is blank (annual contract)', toms.peak, '—');
    if (basil) eq('Basil/Wholesale sells nothing so reads 0%', basil.season, '0%');
    if (toms)  eq('Tomatoes/Wholesale fills 2% of its contract', toms.season, '2%');
    if (toms)  ok('annual rows are labelled as a yearly contract',
                  /sold \/ yr contract/.test(toms.label));
  }

  // ── 2b. A stale form cannot drop a row the solver reported ────────────────
  {
    // params is consulted ONLY for row order. An older saved plan whose params predate one of
    // the collections must still render every row, in some order — not none. Ordering by params
    // and silently skipping the rest would hide real numbers behind a form field.
    const noLists = { ...PARAMS, crops: undefined, channels: undefined };
    const rows = demandRowsOf(W, RES, noLists);
    eq('every row still renders without params.crops/channels', rows.length, 5);

    // A crop the form no longer lists is appended rather than dropped.
    const dropped = { ...PARAMS, crops: PARAMS.crops.filter(c => c.name !== 'Garlic') };
    const rows2 = demandRowsOf(W, RES, dropped);
    eq('a crop missing from params is still shown', rows2.length, 5);
    ok('and it sorts after the ones params does list',
       rows2.findIndex(r => r.label.startsWith('Garlic')) > 0);
  }

  // ── 2c. Both surfaces label the at-cap threshold from the SOLVER ──────────
  {
    // The panel header hardcoded 95 while the CSV read res.demand_at_cap_threshold, so moving
    // the solver's threshold would have made the table lie while the export stayed honest.
    // Driven at a non-default value, which is the only way to tell reading it from restating it.
    const shifted = { ...RES, demand_at_cap_threshold: 0.80 };
    const el = W.document.getElementById('constraint-summary-content');
    W.renderConstraintSummary(shifted, PARAMS);
    ok(`panel header states the solver's threshold, not a literal (got "${
        (el.textContent.match(/Weeks ≥\d+%/) || ['none'])[0]}")`,
       /Weeks ≥80%/.test(el.textContent));
    // ...and the default still renders as before.
    W.renderConstraintSummary(RES, PARAMS);
    ok('and the default reads 95%', /Weeks ≥95%/.test(el.textContent));
  }

  // ── 3. THE RECONSTRUCTION GUARD ───────────────────────────────────────────
  {
    // Everything the old code needed to invent a saturation — planted acreage, yields, and
    // every demand-cap variant — and no demand_saturation. It must report nothing at all.
    const noSat = {
      crop_names: RES.crop_names,
      succession_schedule: RES.succession_schedule,
      revenue: RES.revenue,
    };
    const rows = demandRowsOf(W, noSat, PARAMS);
    ok(`panel draws no demand rows without the solver's series (got ${rows.length}: `
       + `${rows.map(r => r.label).join(' | ')})`, rows.length === 0);

    // The ranking must not fall back either — it shares the basis, which is why W6 could not be
    // fixed in the panel alone without the two silently diverging.
    const cands = W.computeDemandCandidates(noSat);
    eq('ranking offers no demand levers without the series', cands.length, 0);
    eq('single-pair lookup returns 0, not NaN',
       W.computeSingleDemandPeak(noSat, 'Garlic', 'Farmers Market'), 0);

    // A client-side cap builder is what let the two panels diverge in the first place.
    eq('_channelAnnualCap is gone', typeof W._channelAnnualCap, 'undefined');
  }

  // ── 4. The panel and the What-If ranking cannot disagree ──────────────────
  {
    const rows = demandRowsOf(W, RES, PARAMS);
    const labels = new Set(rows.map(r => r.label.split(' (')[0].trim()));
    const cands = W.computeDemandCandidates(RES);
    ok('ranking produced candidates', cands.length > 0);
    for (const dc of cands) {
      const lbl = `${dc.cropName} → ${dc.channelName}`;
      ok(`ranked "${lbl}" is a row the panel draws`, labels.has(lbl));
      eq(`ranked "${lbl}" uses the enforced-row basis`,
         dc.sat, RES.demand_saturation[dc.channelName][dc.cropName].binding);
    }
    // Top-1 per crop, and a crop's no-sales channel can never be its pick.
    const perCrop = cands.map(c => c.cropName);
    eq('one entry per crop', perCrop.length, new Set(perCrop).size);
    ok('Spinach is offered via Farmers Market, not the channel it sells nothing into',
       (cands.find(c => c.cropName === 'Spinach') || {}).channelName === 'Farmers Market');
    // Ties on binding (Garlic and Spinach are both 1.0) break on weeks at cap: 29 vs 7.
    const first = cands[0];
    eq('the tie between two fully-binding caps breaks on weeks at cap', first.cropName, 'Spinach');
  }

  // ── 4b. The What-If pill labels its lever from the solver, not the form ───
  {
    // The pill text is the one place a stale cap builder survived W6's first pass: displayFn
    // re-derived a weekly figure from `params`, and all three of its branches were the deleted
    // builder's failure modes. T83 pins this too, but T83 is in the in-page suite, which never
    // runs automatically — so the guard has to be here to be a guard.
    const ranked = W.rankBottlenecks(RES, PARAMS);
    const pills = ranked.filter(c => c.type === 'demand_single');
    ok('demand pills present', pills.length > 0);

    // Weekly cap: the ceiling in the tightest week, scaling with the lever.
    const garlicPill = pills.find(c => c.cropName === 'Garlic');
    if (garlicPill) {
      eq('weekly pill names the peak-week cap', garlicPill.displayFn(PARAMS, 1.0), '2,000 lb/wk cap');
      eq('and +10% scales it',                  garlicPill.displayFn(PARAMS, 1.10), '2,200 lb/wk cap');
    }

    // Annual contract: priced per YEAR. Labelling it per week is the `annual/52` fiction — on
    // this fixture that would read 2,885 lb/wk (150,000 / 52) for a channel whose own row says
    // it has no weekly ceiling at all.
    const annualOnly = {
      ...RES,
      demand_saturation: { Wholesale: { Basil: RES.demand_saturation.Wholesale.Basil } },
    };
    const annualPill = W.rankBottlenecks(annualOnly, PARAMS)
      .find(c => c.type === 'demand_single');
    ok('annual-contract pill present', !!annualPill);
    if (annualPill) {
      const label = annualPill.displayFn(PARAMS, 1.0);
      eq('annual contract is labelled per year', label, '150,000 lb/yr contract');
      ok(`and never per week (annual/52 would be ${Math.round(150000 / 52)}) — got "${label}"`,
         !/\/wk/.test(label));
    }
  }

  // ── 4c. The pill TOOLTIP names the basis it actually shows ────────────────
  {
    // The pill is the one user-visible surface W6 changed, and its tooltip kept naming the basis
    // the commit deleted: "total crop harvest ÷ channel annual cap". The percentage beside it is
    // `binding`, so the sentence described a formula giving a different number — on the shipped
    // farm Spinach/Farmers Market reads 100% where harvest ÷ cap is 87%, and Garlic/Wholesale
    // reads 100% against a fill of 8%. Driven here because the in-page suite does not run.
    const card = W.document.getElementById('bottleneck-content');
    ok('#bottleneck-content exists', !!card);
    W.renderWhatIfCard(RES, PARAMS);
    const tips = Array.from(card.querySelectorAll('button.cn-btn'))
      .map(b => ({ text: b.textContent.trim(), title: b.getAttribute('title') || '' }));
    ok(`pills rendered (got ${tips.length})`, tips.length > 0);

    const demandTips = tips.filter(t => /→|\//.test(t.text) && /Demand/.test(t.title));
    ok(`demand pills carry a tooltip (got ${demandTips.length})`, demandTips.length > 0);
    for (const t of tips) {
      ok(`no tooltip claims the deleted basis — "${t.title.slice(0, 70)}"`,
         !/harvest\s*÷|total crop harvest|total harvest/i.test(t.title));
    }
    // A weekly cap's tooltip must say which week, an annual contract's must say the year.
    const weeklyTip = demandTips.find(t => /Spinach|Garlic/.test(t.text));
    if (weeklyTip) {
      ok(`weekly pill names the tightest week — "${weeklyTip.title.slice(0, 80)}"`,
         /tightest week/.test(weeklyTip.title));
    }
    // Tomatoes, not Basil: Basil's binding is 0, so it never becomes a pill at all. Tomatoes
    // fills 1.6% of its contract and reaches the pill row through the informational fallback —
    // so this covers the OTHER tooltip branch, which carried the same false sentence.
    const annualOnly = {
      ...RES,
      demand_saturation: { Wholesale: { Tomatoes: RES.demand_saturation.Wholesale.Tomatoes } },
    };
    W.renderWhatIfCard(annualOnly, PARAMS);
    const annualTip = String(Array.from(card.querySelectorAll('button.cn-btn'))
      .map(b => b.getAttribute('title') || '').find(t => /Demand/.test(t)));
    ok(`an annual contract's tooltip says yearly contract — "${annualTip.slice(0, 90)}"`,
       /yearly contract/.test(annualTip));
    ok(`and the informational variant drops the deleted basis too — "${annualTip.slice(0, 90)}"`,
       !/harvest\s*÷|total harvest/i.test(annualTip));
  }

  // ── 5. The constraint CSV reports weeks for a WEEKLY cap ──────────────────
  {
    // It used to write "N/A (annual basis)" for every demand row, hiding the one column that
    // explains a low season figure on a binding weekly cap.
    let csv = null;
    const origCreate = W.document.createElement.bind(W.document);
    W.document.createElement = function (tag) {
      const el = origCreate(tag);
      if (tag === 'a') el.click = () => {
        csv = decodeURIComponent((el.href || '').replace(/^data:text\/csv;charset=utf-8,/, ''));
      };
      return el;
    };
    W._lastRes = RES; W._lastParams = PARAMS;
    W.exportConstraintCSV();
    W.document.createElement = origCreate;

    ok('constraint CSV captured', csv !== null);
    // A real quoted-CSV split: the Baseline Value column holds things like "2,000 lb/wk cap",
    // so splitting on every comma silently shifts every column after it — which is how the
    // first version of this test "failed" against a correct exporter.
    const splitRow = row => {
      const out = []; let cur = '', q = false;
      for (let i = 0; i < row.length; i++) {
        const c = row[i];
        if (c === '"') {
          if (q && row[i + 1] === '"') { cur += '"'; i++; } else { q = !q; }
        } else if (c === ',' && !q) { out.push(cur); cur = ''; }
        else cur += c;
      }
      out.push(cur);
      return out;
    };
    const lines = (csv || '').replace(/^﻿/, '').split('\n').map(splitRow);
    const hdr = lines[0] || [];
    const iSeason = hdr.indexOf('Avg Util %');
    const iAtCap  = hdr.findIndex(h => h.startsWith('Weeks at Cap'));
    const iPeakL  = hdr.indexOf('Peak Week List');
    ok('CSV has the expected columns', iSeason > 0 && iAtCap > 0 && iPeakL > 0);
    // The heading has to state the threshold the numbers under it were measured at. It said
    // ">=100%" while demand rows were counted at >=95%, which is the same untrue label as the
    // "(harvest / cap)" chip W6 removed.
    ok(`the at-cap heading states the demand threshold (got "${hdr[iAtCap]}")`,
       hdr[iAtCap].includes('95'));

    // EVERY crop-channel is exported, not just the three that fit the What-If pill row.
    const demandCsvRows = lines.filter(r => r[1] === 'demand_single');
    eq('the CSV exports every crop-channel, not the top 3 pills', demandCsvRows.length, 5);

    const garlicRow = lines.find(r => r[0] === 'Garlic / Farmers Market');
    ok('Garlic / Farmers Market reached the CSV', !!garlicRow);
    if (garlicRow) {
      eq('CSV carries the season fill for a weekly cap', garlicRow[iSeason], '50');
      eq('CSV counts the at-cap weeks instead of "N/A"', garlicRow[iAtCap], '7');
      // Bare week numbers, same format weekEvidence uses for the physical rows — the column
      // used to mix "29; 30" (physical) with "W29; W30" (demand).
      ok(`CSV lists the at-cap weeks (got "${garlicRow[iPeakL]}")`,
         /^29; 30; 31/.test(garlicRow[iPeakL]));
      ok('the baseline value names the weekly ceiling, not a yearly one',
         /\/wk cap$/.test(garlicRow[hdr.indexOf('Baseline Value')]));
    }

    const basilRow = lines.find(r => r[0] === 'Basil / Wholesale');
    ok('Basil / Wholesale (annual contract) reached the CSV', !!basilRow);
    if (basilRow) {
      ok(`an annual contract still says so (got "${basilRow[iAtCap]}")`,
         /annual contract/.test(basilRow[iAtCap]));
      ok(`and is priced per YEAR, never annual/52 (got "${basilRow[hdr.indexOf('Baseline Value')]}")`,
         /\/yr contract$/.test(basilRow[hdr.indexOf('Baseline Value')]));
    }
  }

  if (failures) {
    console.error(`\ndemand_saturation_client: ${failures} failure(s)`);
    process.exit(1);
  }
  console.log('demand_saturation_client: all checks passed');
})().catch(e => { console.error(e); process.exit(1); });
