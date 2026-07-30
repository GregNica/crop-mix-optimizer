/* CLIENT-SIDE guards for the P&L cost breakdowns (W4) — driven in a real DOM.
 *
 * The Python side is pinned by tests/test_cost_splits.py (the solver sums each total from its
 * own split) and tests/test_golden_farm.py (the adapter forwards both, still reconciling). This
 * file pins the third link: that the P&L EXPORTER actually reads them.
 *
 * WHAT WENT WRONG. exportPLCSV asked for thirteen flat keys — res.cost_seed, res.cost_fert,
 * res.cost_harvest_storage and so on. Twelve were returned by nothing at all, so the `!= null`
 * filter dropped every row and the statement printed two opaque totals with no detail under
 * either. The thirteenth was gated on `> 0` at a value of 0. Measured on the shipped farm: 13 of
 * 13 detail rows rendered nothing, and nothing anywhere noticed, because a CSV with fewer rows
 * than intended looks exactly like a CSV.
 *
 * THE LOAD-BEARING TEST HERE IS THE RECONSTRUCTION GUARD: given a result carrying the two
 * totals and no splits, the exporter must print NO detail rows and must not invent any. The old
 * code's failure was silent absence, so absence is what has to be proved to be visible — and
 * the ONLY way it becomes visible is that the rows come from the payload rather than from a
 * formula over rates the client holds.
 *
 * The fixture below is the real adapter's output shape, not a convenient one. A fixture that
 * supplies what the app does not send is a fixture that tests the fixture (W6, T6a).
 *
 * Run: node tests/cost_splits_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp, captureCSV } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };

// Deliberately NOT proportional to anything the client could re-derive: the fixed components do
// not scale with the totals, and labor is not a fixed share of variable cost. Any formula would
// produce different numbers than these.
const RES = {
  revenue: 100000,
  variable_cost: 21000,   // = sum(variable_cost_split)
  fixed_cost: 22400,   // = sum(fixed_cost_split)
  operating_profit: 55600,   // = 100000 - 21000 - 22400 - (300 + 700 + 0)
  overhead_cost: 5000,
  interest_cost: 400,
  fixed_selling_cost: 1200,
  profit: 49000,             // = 55600 - 5000 - 400 - 1200
  peak_borrowing: 9000,
  city_water_cost: 300,
  overtime_cost: 700,
  hire_cost: 0,
  variable_cost_split: {
    water: 1500, fertilizer: 2500, fuel: 900, seed: 8100, packaging: 8000,
  },
  fixed_cost_split: {
    harvest_storage: 4000, ambient_storage: 750, water_storage: 1000, irrigation: 2000,
    equipment_storage: 1500, fuel_storage: 250, machinery: 6000,
    property_mortgage_rent: 0, other_debt_service: 1500, wages: 5000,
    // The one component that appears CONDITIONALLY (only when a metered supply charges a standing
    // fee), so the one whose label a hand-written row list would have been most likely to miss.
    city_water_fixed_fee: 400,
  },
  channel_sales: { Wholesale: { lbs_sold: 1000, revenue: 100000, by_crop: {} } },
};
// operating_profit must equal revenue - variable - fixed - (city water + overtime + hire), or the
// tripwire assertion below would be testing arithmetic that was never true.
const RES_OP = RES.revenue - RES.variable_cost - RES.fixed_cost
             - (RES.city_water_cost + RES.overtime_cost + RES.hire_cost);
if (RES.operating_profit !== RES_OP) {
  console.error(`fixture is inconsistent: operating_profit ${RES.operating_profit} != ${RES_OP}`);
  process.exit(1);
}

const PARAMS = {
  channels: [{ name: 'Wholesale', fixed_selling_cost_per_wk: 0 }],
  opening_cash: 0, credit_line: 0,
};

// The labels a grower actually reads, written out here rather than read back off the app's own
// PL_*_LABELS maps. Asserting the CSV against the very map that produced it would be circular —
// it would pass for any labels at all, which is the vacuous shape this repo has caught twice
// (T27, T83). These are user-visible copy, so a change to them SHOULD have to be made twice.
const EXPECT_VARIABLE_LABELS = {
  water:      'Irrigation Water (on-farm supply — $0 until a pumping cost is entered)',
  fertilizer: 'Fertilizer',
  fuel:       'Fuel',
  seed:       'Seed / Transplants',
  packaging:  'Packaging (per lb sold)',
};
const EXPECT_FIXED_LABELS = {
  harvest_storage:        'Harvest Storage (refrigerated)',
  ambient_storage:        'Ambient Storage (barn)',
  water_storage:          'Water Storage',
  irrigation:             'Irrigation Infrastructure',
  equipment_storage:      'Equipment Storage',
  fuel_storage:           'Fuel Storage',
  machinery:              'Machinery',
  property_mortgage_rent: 'Property Mortgage/Rent',
  other_debt_service:     'Other Debt Service',
  wages:                  'Wages — all listed staff at their stated hours',
  city_water_fixed_fee:   'City Water Standing Charge',
};
// Note "Fertilizer", not "Fertilizer & Pesticide", which is what this row said until W4: the model
// has no crop-protection cost of any kind (backlog R1), so the old label named a cost the farm was
// never charged. The loop below is what pins it — comparing this literal to itself would not.

// The three rows for capacity the optimizer BUYS, which sit outside both cost totals. Used as
// stop-labels when slicing the fixed-cost detail block, in more than one check below.
const BOUGHT = ['City Water (metered purchase)', 'Overtime Premium', 'Hired Labor Markup'];

(async () => {
  const W = await bootApp();
  // captureCSV lives in jsdom_app.cjs: the interception is shared, and it restores
  // document.createElement afterwards rather than leaving a patched click on the prototype.
  const runExport = () => captureCSV(W, () => W.exportPLCSV()) || [];

  const amountOf = (rows, label) => {
    const r = rows.find(x => (x[0] || '').trim() === label);
    return r ? parseFloat(r[1]) : null;
  };
  // Detail rows are the indented ones between a subtotal and the next non-indented line.
  const detailUnder = (rows, headerLabel, stopAt) => {
    const i = rows.findIndex(x => (x[0] || '').trim() === headerLabel);
    if (i < 0) return null;
    const out = [];
    for (let j = i + 1; j < rows.length; j++) {
      const label = (rows[j][0] || '').trim();
      if (!(rows[j][0] || '').startsWith('    ') || stopAt.includes(label)) break;
      out.push([label, parseFloat(rows[j][1])]);
    }
    return out;
  };

  // ── 1. The breakdowns are RENDERED, from the payload ───────────────────────
  {
    W._lastRes = RES; W._lastParams = PARAMS;
    const rows = runExport();
    const cogs = detailUnder(rows, 'Variable Production Cost', []);
    ok(`COGS prints one row per variable component (got ${cogs && cogs.length})`,
       cogs && cogs.length === Object.keys(RES.variable_cost_split).length);

    const fixed = detailUnder(rows, 'Fixed & Committed Costs',
                              ['Total Operating Expenses', ...BOUGHT]);
    ok(`fixed cost prints one row per component (got ${fixed && fixed.length})`,
       fixed && fixed.length === Object.keys(RES.fixed_cost_split).length);

    // Every value is the payload's own, negated. This is what makes it a read and not a formula.
    for (const [key, amount] of Object.entries(RES.variable_cost_split)) {
      const label = EXPECT_VARIABLE_LABELS[key];
      const got = amountOf(rows, label);
      ok(`COGS row "${label}" carries the payload value (got ${got}, want ${-amount})`,
         got === -amount);
    }
    for (const [key, amount] of Object.entries(RES.fixed_cost_split)) {
      const label = EXPECT_FIXED_LABELS[key];
      const got = amountOf(rows, label);
      ok(`fixed row "${label}" carries the payload value (got ${got}, want ${-amount})`,
         got === -amount);
    }

    // Every cost row prints negative in a column headed "negative = cost". W9's credit was the
    // one exception and it is gone: W12 made every listed worker a committed cost, so there is no
    // double charge left to credit back.
    ok('every COGS row prints as a cost, not a credit',
       cogs.filter(([, v]) => v > 0).length === 0);

    // ...and they add up to the totals printed above them. The point of the whole fix.
    const sum = a => a.reduce((s, [, v]) => s + v, 0);
    ok(`COGS detail sums to its total (${sum(cogs)} vs ${-RES.variable_cost})`,
       Math.abs(sum(cogs) + RES.variable_cost) < 0.02);
    ok(`fixed detail sums to its total (${sum(fixed)} vs ${-RES.fixed_cost})`,
       Math.abs(sum(fixed) + RES.fixed_cost) < 0.02);
  }

  // ── 2. RECONSTRUCTION GUARD — no splits means no rows, not invented rows ───
  {
    const noSplits = { ...RES };
    delete noSplits.variable_cost_split;
    delete noSplits.fixed_cost_split;
    W._lastRes = noSplits;
    const rows = runExport();
    // The totals still print — they are separate keys and still arrive.
    ok('the totals still print without the splits',
       amountOf(rows, 'Variable Production Cost') === -RES.variable_cost);
    const cogs = detailUnder(rows, 'Variable Production Cost', []);
    ok(`no COGS detail is invented from rates or shares (got ${JSON.stringify(cogs)})`,
       cogs && cogs.length === 0);
    const fixed = detailUnder(rows, 'Fixed & Committed Costs',
                              ['Total Operating Expenses', ...BOUGHT]);
    ok(`no fixed detail is invented (got ${JSON.stringify(fixed)})`,
       fixed && fixed.length === 0);
    W._lastRes = RES;
  }

  // ── 3. An UNLABELLED component still reaches the statement ────────────────
  // The reason the exporter iterates the split instead of naming its keys. The old hand-written
  // list named eight of eleven fixed components, so the other three were charged to the total
  // and appeared in no row — money missing from a P&L with nothing reporting it. A component
  // nobody has written a label for yet must still print, under its own name.
  {
    W._lastRes = {
      ...RES,
      fixed_cost_split: { ...RES.fixed_cost_split, crop_insurance_premium: 3300 },
      fixed_cost: RES.fixed_cost + 3300,
    };
    const rows = runExport();
    const got = amountOf(rows, 'Crop Insurance Premium');
    ok(`an unlabelled component prints under a readable form of its key (got ${got})`,
       got === -3300);
    W._lastRes = RES;
  }

  // ── 4. The reconcile line is a TRIPWIRE, not a bridge ─────────────────────
  // It used to absorb city water, overtime and the hire markup under "items outside the
  // optimizer", so a farm that bought a week of overtime saw the money as an unexplained plug.
  // Those three now have rows, which must drive the plug to silence — and it must still fire
  // when a cost really is missing, or it is decoration.
  {
    W._lastRes = RES;
    let rows = runExport();
    ok('overtime and city water print as named rows',
       amountOf(rows, 'Overtime Premium') === -RES.overtime_cost &&
       amountOf(rows, 'City Water (metered purchase)') === -RES.city_water_cost);
    ok('no UNRECONCILED line when every cost has a row',
       !rows.some(r => (r[0] || '').includes('UNRECONCILED')));

    // Now hide a cost from the statement the way a future solver line would: operating_profit
    // accounts for it, no row does.
    W._lastRes = { ...RES, operating_profit: RES.operating_profit - 2500 };
    rows = runExport();
    ok('an unaccounted operating cost fires the UNRECONCILED line',
       rows.some(r => (r[0] || '').includes('UNRECONCILED')));

    // And the same BELOW the line: a deduction inside `profit` that no row explains. This section
    // reconciles only because the adapter deducts exactly overhead, interest and fixed selling; a
    // fourth deduction would otherwise leave NET PROFIT not summing to its own rows, silently.
    W._lastRes = { ...RES, profit: RES.profit - 3000 };
    rows = runExport();
    ok('an unaccounted below-the-line deduction fires the UNRECONCILED line',
       rows.some(r => (r[0] || '').includes('no line above')));
    W._lastRes = RES;
    rows = runExport();
    ok('neither tripwire fires on a consistent statement',
       !rows.some(r => (r[0] || '').includes('UNRECONCILED')));
  }

  if (failures) {
    console.error(`\ncost splits (client): ${failures} FAILED`);
    process.exit(1);
  }
  console.log('cost splits (client): all checks passed ' +
              '(both breakdowns rendered from the payload, nothing reconstructed, ' +
              'unlabelled component still prints, reconcile tripwire live)');
  // jsdom keeps timers on the event loop; without this node hangs after a passing run.
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
