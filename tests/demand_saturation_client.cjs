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
 * export must write NO demand rows and the ranking must offer NO demand levers. That is the exact
 * input the old code turned into a table of invented percentages.
 *
 * SURFACES (changed by W7, 2026-07-31). This used to drive the constraint-summary PANEL as well.
 * That panel had been display:none with no unhide path since Phase 2.3 and is now deleted, so
 * every check it carried was re-pointed at the two surfaces that still ship the series: the
 * What-If pills and exportConstraintCSV(). Three of its assertions needed a decision, not a
 * move, and it is worth being precise about which is which:
 *   - the at-cap threshold coming from the SOLVER: MOVED to the export, and strengthened — it is
 *     now driven at a non-default 0.80 rather than asserted at the default.
 *   - rows built from `res` and never from the form: MOVED (§2b).
 *   - row ORDER following params: RETIRED, not moved. The export has no such ordering — it ranks
 *     most-binding-first — so there was nothing to re-point it at. §2 pins the export's own
 *     ordering instead.
 *   - "an annual contract has no weekly ceiling", which the panel showed as a blank cell: this
 *     one was genuinely DROPPED by the first pass of the rework and the export was printing the
 *     annual fill under "Peak Util %". Caught by review, fixed in the export, and pinned in §2.
 *
 * WHY jsdom: the CSV exporter reaches into the DOM and the pills write innerHTML. Both are
 * driven for real here, not pattern-matched — two inert guards shipped in this codebase because
 * a source-level check looked equivalent. Nothing here needs Pyodide.
 *
 * Run: node tests/demand_saturation_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp, captureCSV } = require('./jsdom_app.cjs');

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
//   Tomatoes/WS   — an annual contract that DOES sell, so a peak-week figure printed for it
//                   would look like a measurement rather than the 0 a zero-sales row shows.
const RES = {
  revenue: 1621122,
  demand_at_cap_threshold: 0.95,
  crop_names: ['Spinach', 'Garlic', 'Basil', 'Tomatoes'],
  succession_schedule: [
    { crop: 'Spinach',  acres: 25, weeks: [10, 11, 12], phases: [0, 1, 2], name: 'Spinach #1', start_week: 10 },
    { crop: 'Garlic',   acres: 23, weeks: [28, 29, 30], phases: [0, 1, 2], name: 'Garlic #1', start_week: 28 },
    { crop: 'Basil',    acres:  6, weeks: [20, 21, 22], phases: [0, 1, 2], name: 'Basil #1', start_week: 20 },
    { crop: 'Tomatoes', acres: 11, weeks: [24, 25, 26], phases: [0, 1, 2], name: 'Tomatoes #1', start_week: 24 },
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

/** Drive exportConstraintCSV for real and return its parsed lines (row 0 is the header). */
function exportLines(window, res, params) {
  window._lastRes = res; window._lastParams = params;
  const lines = captureCSV(window, () => window.exportConstraintCSV());
  if (!lines) throw new Error('exportConstraintCSV wrote no file — the export cannot be driven');
  return lines;
}

/**
 * The demand rows of the exported CSV, as [{label, season, peak, weeks, ...}].
 * `season` is the annual fill and `peak` the binding figure the solver enforces — the two
 * different, both-correct numbers whose collapse was the W6 defect.
 */
function demandRowsOf(window, res, params) {
  const lines = exportLines(window, res, params);
  const hdr   = lines[0] || [];
  // A renamed column would otherwise index at -1 and hand every assertion `undefined`, which
  // reads as a wrong VALUE rather than a missing column. Fail on the column instead. Matched by
  // prefix because "Weeks at Cap" carries its threshold in the heading; no other column name is
  // a prefix of another.
  const col = name => {
    const i = hdr.findIndex(h => h.startsWith(name));
    if (i < 0) throw new Error(`the export has no "${name}" column — got ${JSON.stringify(hdr)}`);
    return i;
  };
  const iPeak = col('Peak Util %'), iSeason = col('Avg Util %');
  const iBase = col('Baseline Value'), iWeeks = col('Peak Week List');
  const iAtCap = col('Weeks at Cap');
  return lines.filter(r => r[1] === 'demand_single').map(r => ({
    label: r[0], peak: r[iPeak], season: r[iSeason],
    baseline: r[iBase], atCap: r[iAtCap], weeks: r[iWeeks],
  }));
}

(async () => {
  const { window } = await bootApp();
  const W = window;

  // ── 1. The export draws its rows from res.demand_saturation ───────────────
  {
    const rows = demandRowsOf(W, RES, PARAMS);
    // EVERY crop-channel is exported, not just the three that fit the What-If pill row. A
    // presentation limit on a pill row has no business bounding an export.
    eq('row count matches the saturation entries', rows.length, 5);

    const find = lbl => rows.find(r => r.label === lbl);

    // THE case: two different, both-correct figures on one row. Collapsing them is the defect.
    const garlic = find('Garlic / Farmers Market');
    ok('Garlic / Farmers Market row exists', !!garlic);
    if (garlic) {
      eq('Garlic/FM season fill is the annual figure', garlic.season, '50');
      eq('Garlic/FM peak is the binding weekly figure', garlic.peak, '100');
      eq('Garlic/FM counts its at-cap weeks instead of "N/A"', garlic.atCap, '7');
      // Bare week numbers, the same format the physical rows use — the column used to mix
      // "29; 30" (physical) with "W29; W30" (demand).
      ok(`Garlic/FM lists its at-cap weeks (got "${garlic.weeks}")`, /^29; 30; 31/.test(garlic.weeks));
      ok('the baseline value names the weekly ceiling, not a yearly one',
         /\/wk cap$/.test(garlic.baseline));
    }

    // The W6 contradiction: sells nothing, must read 0%. Old formula printed 16%.
    const spWs = find('Spinach / Wholesale');
    ok('Spinach / Wholesale row exists', !!spWs);
    if (spWs) {
      eq('Spinach/Wholesale sells nothing so reads 0%', spWs.season, '0');
      eq('Spinach/Wholesale has no at-cap weeks', spWs.atCap, '0');
    }
  }

  // ── 2. An annual contract is reported per YEAR, with no weekly ceiling ─────
  {
    const rows = demandRowsOf(W, RES, PARAMS);
    const basil = rows.find(r => r.label === 'Basil / Wholesale');
    const toms  = rows.find(r => r.label === 'Tomatoes / Wholesale');
    ok('Basil / Wholesale row exists', !!basil);
    ok('Tomatoes / Wholesale row exists', !!toms);
    // `annual/52` is a limit the solver stopped imposing at B4; the readers kept printing it.
    // On this fixture it would read 2,885 lb/wk for a channel with no weekly ceiling at all.
    if (basil) {
      ok(`an annual contract says so rather than counting weeks (got "${basil.atCap}")`,
         /annual contract/.test(basil.atCap));
      ok(`and is priced per YEAR, never annual/52 (got "${basil.baseline}")`,
         /\/yr contract$/.test(basil.baseline));
      eq('Basil/Wholesale sells nothing so reads 0%', basil.season, '0');
    }
    if (toms) eq('Tomatoes/Wholesale fills 2% of its contract', toms.season, '2');

    // THE PEAK COLUMN. No weekly ceiling means no peak-week utilisation to report, and the
    // solver sets `binding` to the annual fill for these rows — so printing it here labels a
    // yearly figure as a peak week AND repeats the Avg column verbatim. Tomatoes is the case
    // that matters: it SELLS, so a number in this column would look like a real measurement
    // rather than the zero a row selling nothing would show.
    for (const r of [basil, toms].filter(Boolean)) {
      ok(`${r.label} reports no peak week for an annual contract (got "${r.peak}")`,
         /annual contract/.test(r.peak));
      ok(`${r.label} does not print its annual fill under Peak Util % (Avg reads "${r.season}")`,
         r.peak !== r.season);
    }
    // ...while a weekly cap still reports a real peak-week figure in that column.
    const spFm = rows.find(r => r.label === 'Spinach / Farmers Market');
    if (spFm) eq('a weekly cap still reports its peak week', spFm.peak, '100');

    // The rows are RANKED most-binding-first, and that has to survive the text cell above. The
    // export used to sort on the printed Peak cell; once one of them reads "N/A (annual
    // contract)" that subtraction is NaN, which leaves the order arbitrary rather than failing —
    // a grower opening the file sees an unranked list and nothing says so. The sort key now
    // travels beside the cells instead of being read back out of them.
    const keyOf = r => Number(/annual contract/.test(r.peak) ? r.season : r.peak);
    const keys  = rows.map(keyOf);
    ok(`every row has a numeric rank key (got ${JSON.stringify(keys)})`, keys.every(Number.isFinite));
    ok(`rows are ordered most-binding-first (got ${JSON.stringify(keys)})`,
       keys.every((k, i) => i === 0 || keys[i - 1] >= k));
    // Not vacuous on this fixture: the keys genuinely differ (100, 100, 2, 0, 0), so a shuffled
    // or NaN-collapsed order has something to violate.
    ok('and the fixture actually exercises an ordering', new Set(keys).size > 1);
  }

  // ── 2b. A stale form cannot drop a row the solver reported ────────────────
  {
    // The demand rows are built from `res` alone — params is never consulted for them. An older
    // saved plan whose params predate one of the collections must still export every row, not
    // none: reading the form here is what would hide real numbers behind a stale field.
    const noLists = { ...PARAMS, crops: undefined, channels: undefined };
    eq('every row still exports without params.crops/channels',
       demandRowsOf(W, RES, noLists).length, 5);

    const dropped = { ...PARAMS, crops: PARAMS.crops.filter(c => c.name !== 'Garlic') };
    const rows2 = demandRowsOf(W, RES, dropped);
    eq('a crop missing from params is still exported', rows2.length, 5);
    ok('including the dropped one', rows2.some(r => r.label.startsWith('Garlic')));
  }

  // ── 2c. The at-cap heading states the SOLVER's threshold ──────────────────
  {
    // The counts under this heading are measured at res.demand_at_cap_threshold. The header used
    // to say ">=100%" over numbers counted at >=95% — the same class of untrue label as the
    // "(harvest / cap)" chip W6 removed. Driven at a NON-default value, which is the only way to
    // tell reading the threshold from restating it.
    const headingOf = res =>
      (exportLines(W, res, PARAMS)[0] || []).find(h => h.startsWith('Weeks at Cap')) || 'none';
    // Captured once: driving the export twice would let the failure message quote a different
    // run from the one that failed.
    const shifted = headingOf({ ...RES, demand_at_cap_threshold: 0.80 });
    ok(`the heading states the solver's threshold, not a literal (got "${shifted}")`,
       /demand ≥80%/.test(shifted));
    ok('and the default reads 95%', /demand ≥95%/.test(headingOf(RES)));
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
    ok(`the export writes no demand rows without the solver's series (got ${rows.length}: `
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

  // ── 4. The export and the What-If ranking cannot disagree ─────────────────
  {
    const rows = demandRowsOf(W, RES, PARAMS);
    const labels = new Set(rows.map(r => r.label));
    const cands = W.computeDemandCandidates(RES);
    ok('ranking produced candidates', cands.length > 0);
    for (const dc of cands) {
      const lbl = `${dc.cropName} / ${dc.channelName}`;
      ok(`ranked "${lbl}" is a row the export writes`, labels.has(lbl));
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

  if (failures) {
    console.error(`\ndemand_saturation_client: ${failures} failure(s)`);
    process.exit(1);
  }
  console.log('demand_saturation_client: all checks passed');
})().catch(e => { console.error(e); process.exit(1); });
