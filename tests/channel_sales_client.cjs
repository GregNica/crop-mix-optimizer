/* CLIENT-SIDE guards for the per-channel sales schedule (W1 / D4) — driven in a real DOM.
 *
 * The Python side is pinned by tests/test_channel_sales.py (the solver builds it) and
 * tests/test_golden_farm.py (the adapter forwards it). This file pins the third link: that the
 * CLIENT reads it and does not rebuild it.
 *
 * WHAT WENT WRONG, and why a source-level check is not enough. `v` — the real per-crop x
 * per-channel x 52-week sales schedule — came out of Python and was read by NOTHING. The client
 * recomputed the same quantity by splitting each week's GROSS harvest in proportion to
 * demand x price. On the shipped demo farm that reported 809,200 lb sold against the 686,415 lb
 * the plan actually sells: a 17.9% overstatement, printed beside a revenue figure derived from
 * the honest number. The pies, the sales CSV and the P&L's channel lines were all built on it.
 *
 * The load-bearing test here is THE RECONSTRUCTION GUARD: given a result with a full harvest
 * schedule and a params object full of prices and demands, but no channel_sales, the client
 * must report NO sales. That is the exact input the old code turned into a week of invented
 * sales, so it is the input that proves the behaviour is gone rather than merely relocated.
 *
 * WHY jsdom: the CSV exporter and the pie renderer reach into the DOM and are driven here for
 * real, not pattern-matched. Nothing here needs Pyodide.
 *
 * Run: node tests/channel_sales_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };
const eq = (name, got, want) => {
  if (got !== want) fail(`${name}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
};

const mkWeeks = m => Array.from({ length: 52 }, (_, i) => m[i + 1] || 0);

// A plan that sells two crops into two channels, with the channels deliberately NOT split in
// proportion to price or demand — so any weighting formula would produce different numbers.
const RES = {
  revenue: 4900,
  crop_names: ['Spinach', 'Garlic'],
  succession_schedule: [
    { crop: 'Spinach', acres: 10, weeks: [10, 11, 12], phases: [0, 1, 2], name: 'Spinach #1' },
    { crop: 'Garlic',  acres:  5, weeks: [10, 11, 12], phases: [0, 1, 2], name: 'Garlic #1' },
  ],
  channel_sales: {
    Wholesale: { lbs_sold: 900, revenue: 900, by_crop: {
      Spinach: { lbs_sold: 600, revenue: 600, weekly_lbs: mkWeeks({ 12: 400, 20: 200 }) },
      Garlic:  { lbs_sold: 300, revenue: 300, weekly_lbs: mkWeeks({ 12: 300 }) },
    } },
    'Farmers Market': { lbs_sold: 1000, revenue: 4000, by_crop: {
      Spinach: { lbs_sold: 1000, revenue: 4000, weekly_lbs: mkWeeks({ 12: 700, 20: 300 }) },
    } },
  },
};

// The params the OLD code would have reconstructed from. Kept deliberately rich: prices,
// demands and yields all present, so the reconstruction guard fails loudly if anything starts
// reading them again.
const PARAMS = {
  operating_weeks: 52,
  channels: [{ name: 'Wholesale' }, { name: 'Farmers Market' }],
  crops: [
    { name: 'Spinach', yield_per_acre: 5000, days_to_maturity: 42, planting_weeks: 1,
      harvest_weeks: 1, channels_data: {
        Wholesale: { price: 1.0, demand_value: 99999 },
        'Farmers Market': { price: 4.0, demand_value: 99999 },
      } },
    { name: 'Garlic', yield_per_acre: 4000, days_to_maturity: 240, planting_weeks: 1,
      harvest_weeks: 1, channels_data: {
        Wholesale: { price: 1.0, demand_value: 99999 },
        'Farmers Market': { price: 4.0, demand_value: 99999 },
      } },
  ],
};

(async () => {
  const { window } = await bootApp();
  const W = window;

  // ── 1. It reads the solver's series ──────────────────────────────────────
  {
    const s12 = W.computeWeeklySalesLbs(12, RES);
    eq('wk12 channel count', Object.keys(s12).length, 2);
    eq('wk12 WS Spinach', s12['Wholesale']['Spinach'], 400);
    eq('wk12 WS Garlic',  s12['Wholesale']['Garlic'],  300);
    eq('wk12 FM Spinach', s12['Farmers Market']['Spinach'], 700);
    ok('wk12 FM has no Garlic (it sells none there)',
       s12['Farmers Market']['Garlic'] === undefined);

    // Week 20: Garlic sold nothing, so it must be absent — not present as 0.
    const s20 = W.computeWeeklySalesLbs(20, RES);
    eq('wk20 WS Spinach', s20['Wholesale']['Spinach'], 200);
    ok('wk20 WS Garlic absent', s20['Wholesale']['Garlic'] === undefined);

    // A week nothing sells in.
    eq('wk30 empty', Object.keys(W.computeWeeklySalesLbs(30, RES)).length, 0);
    // Out of range.
    eq('wk0 empty',  Object.keys(W.computeWeeklySalesLbs(0, RES)).length, 0);
    eq('wk53 empty', Object.keys(W.computeWeeklySalesLbs(53, RES)).length, 0);
  }

  // ── 2. THE RECONSTRUCTION GUARD ──────────────────────────────────────────
  {
    // Everything the old code needed to invent sales — a harvest schedule, prices, demands,
    // yields — and no channel_sales. It must report nothing.
    const harvestOnly = { crop_names: RES.crop_names, succession_schedule: RES.succession_schedule };
    const out = W.computeWeeklySalesLbs(12, harvestOnly);
    ok(`no reconstruction from a harvest schedule (got ${JSON.stringify(out)})`,
       Object.keys(out).length === 0);

    // Passing params as a third argument must change nothing: the signature dropped it, and
    // accepting one is what made a client-side recomputation possible in the first place.
    const withParams = W.computeWeeklySalesLbs(12, harvestOnly, PARAMS);
    ok('params argument is ignored', Object.keys(withParams).length === 0);
    eq('arity is (week, res)', W.computeWeeklySalesLbs.length, 2);
  }

  // ── 3. The weekly series reconciles to the annual channel total ───────────
  {
    // The pies show a week; the P&L shows the year. They are on the same screen.
    for (const [ch, data] of Object.entries(RES.channel_sales)) {
      let summed = 0;
      for (let w = 1; w <= 52; w++) {
        summed += Object.values(W.computeWeeklySalesLbs(w, RES)[ch] || {})
          .reduce((a, b) => a + b, 0);
      }
      eq(`${ch}: weekly sum equals lbs_sold`, summed, data.lbs_sold);
    }
  }

  // ── 4. The sales CSV is built from it ────────────────────────────────────
  {
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
    W.exportWeeklySalesCSV();
    W.document.createElement = origCreate;

    ok('CSV captured', csv !== null);
    const lines = (csv || '').split('\n');
    // The exporter names its columns with the ACTIVE mass unit ("lb" / "kg"), and the file
    // opens with a BOM for Excel. Take the unit from the harvest column rather than hardcoding
    // it — two in-page tests hardcoded "lbs_" and had been failing silently against "lb_".
    // (U_LB is a `const` in the app's inline script, so it is not reachable as W.U_LB.)
    const header = (lines[0] || '').replace(/^\uFEFF/, '').replace(/"/g, '');
    const MASS = (header.split(',')[2] || '').replace(/_harvested$/, '');
    ok(`mass unit parsed from the header (got "${MASS}")`, /^(lb|kg)$/.test(MASS));
    ok(`CSV header carries both channels (got "${header}")`,
       header.includes(`${MASS}_sold_wholesale`) && header.includes(`${MASS}_sold_farmers_market`));
    // Wholesale sorts before Farmers Market by the exporter's explicit PRIORITY list.
    ok('CSV channel column order is wholesale then farmers_market',
       header.indexOf('wholesale') < header.indexOf('farmers_market'));

    // The week-12 Spinach row must carry the SOLVER's split (400 / 700), not a price- or
    // demand-weighted one. At price 1.0 vs 4.0 a price split would put ~80% in FM.
    const cols = header.split(',');
    const iWS = cols.indexOf(`${MASS}_sold_wholesale`);
    const iFM = cols.indexOf(`${MASS}_sold_farmers_market`);
    const row = lines.slice(1)
      .map(r => r.replace(/"/g, '').split(','))
      .find(r => r[0] === '12' && r[1] === 'Spinach');
    ok('week-12 Spinach row exists', !!row);
    if (row) {
      eq('CSV wk12 Spinach wholesale', row[iWS], '400');
      eq('CSV wk12 Spinach farmers_market', row[iFM], '700');
    }
  }

  // ── 5. The channel pies are built from it ────────────────────────────────
  {
    W._lastRes = RES; W._lastParams = PARAMS;
    const area = W.document.getElementById('channel-pies-area');
    ok('#channel-pies-area exists', !!area);
    if (area) {
      W.updatePieChart(12);
      const html12 = area.innerHTML;
      ok('wk12 pies name Wholesale', /Wholesale/.test(html12));
      ok('wk12 pies name Farmers Market', /Farmers Market/.test(html12));

      // Week 30 sells nothing: the area must say so rather than show stale week-12 pies.
      W.updatePieChart(30);
      const html30 = area.innerHTML;
      ok(`wk30 shows a nothing-sold message (got "${html30.slice(0, 120)}")`,
         /Nothing is sold this week/.test(html30));
      ok('wk30 does not still show week-12 pies', !/Farmers Market/.test(html30));
    }
  }

  if (failures) {
    console.error(`\nchannel sales (client): ${failures} FAILED`);
    process.exit(1);
  }
  console.log('channel sales (client): all checks passed ' +
              '(series read, no reconstruction, weekly totals, CSV, pies)');
  // jsdom keeps timers on the event loop; without this node hangs after a passing run.
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
