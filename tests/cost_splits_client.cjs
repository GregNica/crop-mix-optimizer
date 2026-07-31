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

(async () => {
  const W = await bootApp();
  // captureCSV lives in jsdom_app.cjs: the interception is shared, and it restores
  // document.createElement afterwards rather than leaving a patched click on the prototype.
  const runExport = () => captureCSV(W, () => W.exportPLCSV()) || [];

  // The CSV is [Line item, Amount] and the hierarchy is INDENTATION, one level = four U+00A0.
  // Non-breaking space, not ASCII space: importers trim leading ASCII spaces, which is what
  // flattened the first indented version into a list with nothing showing what summed to what.
  // Detail rows sit at depth 2 under a group name or section header, and each group closes with a
  // "Total …" line at depth 1.
  const IND   = '\u00a0'.repeat(4);
  const text  = cell => String(cell || '').replace(/^\u00a0+/, '');
  const depth = cell => (String(cell || '').length - text(cell).length) / IND.length;
  const amountOf = (rows, label) => {
    const r = rows.find(x => text(x[0]) === label);
    return r ? parseFloat(r[1]) : null;
  };
  // The components of a group: the depth-2 rows immediately following its header. The run ends at
  // the group's own "Total …" line, which sits one level out — so the boundary is the indentation
  // itself and not a list of labels that would rot as lines are added. (It took a stop-label list
  // until /simplify measured that the depth check always broke first: the list was dead, and worse,
  // naming a label that IS at depth 2 would have silently truncated a block.)
  const detailUnder = (rows, headerLabel) => {
    const i = rows.findIndex(x => text(x[0]) === headerLabel);
    if (i < 0) return null;
    const out = [];
    for (let j = i + 1; j < rows.length; j++) {
      if (depth(rows[j][0]) !== 2) break;
      out.push([text(rows[j][0]), parseFloat(rows[j][1])]);
    }
    return out;
  };

  // ── 1. The breakdowns are RENDERED, from the payload ───────────────────────
  {
    W._lastRes = RES; W._lastParams = PARAMS;
    const rows = runExport();
    const cogs = detailUnder(rows, 'COST OF GOODS SOLD');
    ok(`COGS prints one row per variable component (got ${cogs && cogs.length})`,
       cogs && cogs.length === Object.keys(RES.variable_cost_split).length);

    const fixed = detailUnder(rows, 'Fixed & Committed Costs');
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
       amountOf(rows, 'Total Cost of Goods Sold') === -RES.variable_cost);
    const cogs = detailUnder(rows, 'COST OF GOODS SOLD');
    ok(`no COGS detail is invented from rates or shares (got ${JSON.stringify(cogs)})`,
       cogs && cogs.length === 0);
    const fixed = detailUnder(rows, 'Fixed & Committed Costs');
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
       amountOf(rows, 'Overtime (full rate)') === -RES.overtime_cost &&
       amountOf(rows, 'City Water (metered purchase)') === -RES.city_water_cost);
    ok('no UNRECONCILED line when every cost has a row',
       !rows.some(r => text(r[0]).includes('UNRECONCILED')));

    // A component charged exactly nothing does not print. The fixture buys no hired labour, so
    // that row must be absent rather than a 0.00 — and the total below it must still be the sum
    // of what WAS bought, which is what stops the filter from quietly losing money.
    ok('a zero-cost bought component prints no row at all',
       amountOf(rows, 'Hired Labor (wage + markup)') === null);
    // "Charged nothing" is what would PRINT as nothing, not exact zero. A float residual out of
    // the solver renders as "-0.00" — sign and all — which is a row claiming a cost of negative
    // nothing. Exact-equality filtering lets it straight through.
    W._lastRes = { ...RES, hire_cost: 3e-8, operating_profit: RES.operating_profit - 3e-8 };
    ok('a float residual that would print as 0.00 is not a component either',
       amountOf(runExport(), 'Hired Labor (wage + markup)') === null);
    W._lastRes = RES;
    ok('Total Bought Capacity is still the full sum',
       amountOf(rows, 'Total Bought Capacity') ===
       -(RES.city_water_cost + RES.overtime_cost + RES.hire_cost));

    // ...and a farm that buys NO capacity at all — the shipped default, which enables neither city
    // water nor hiring — gets one line, not a group name over three 0.00 rows and a 0.00 total.
    W._lastRes = { ...RES, city_water_cost: 0, overtime_cost: 0, hire_cost: 0,
                   operating_profit: RES.operating_profit
                                   + RES.city_water_cost + RES.overtime_cost + RES.hire_cost };
    const noBuyRows = runExport();
    ok('a farm that buys no capacity prints one collapsed line, no 0.00 detail',
       amountOf(noBuyRows, 'Bought Capacity') === 0 &&
       detailUnder(noBuyRows, 'Bought Capacity').length === 0 &&
       !noBuyRows.some(r => text(r[0]) === 'Total Bought Capacity'));
    W._lastRes = RES;

    // Now hide a cost from the statement the way a future solver line would: operating_profit
    // accounts for it, no row does.
    W._lastRes = { ...RES, operating_profit: RES.operating_profit - 2500 };
    rows = runExport();
    ok('an unaccounted operating cost fires the UNRECONCILED line',
       rows.some(r => text(r[0]).includes('UNRECONCILED')));

    // ⚠️ THE TRIPWIRE FAILED OPEN ON THE ONE FAILURE ITS COMMENT CLAIMS IT WOULD HAVE CAUGHT.
    // Drop a bought-capacity key — which is exactly what happened to `city_water_cost` when the
    // adapter did not forward it — and `boughtTotal` is NaN. NaN fails every comparison, so
    // `Math.abs(NaN) > 0.5` is FALSE: three rows printed "NaN", OPERATING INCOME printed a clean
    // figure, and nothing fired. A check that goes silent precisely when the data is broken reads
    // as a pass, which is this repo's most expensive failure class.
    const { city_water_cost, ...noCityWater } = RES;
    W._lastRes = noCityWater;
    rows = runExport();
    ok('a MISSING payload key fires the UNRECONCILED line rather than printing NaN quietly',
       rows.some(r => text(r[0]).includes('UNRECONCILED')));
    // ...and no cell may carry a number-shaped non-number. "NaN" in a money column is read as a
    // value by a human and by a spreadsheet; an empty cell is worse still, because that is exactly
    // how a group NAME is drawn, so a revenue line with no figure printed as a header while the
    // total above it still counted the money.
    ok('a missing figure says so in words, and is never blank or "NaN"',
       rows.every(r => r[1] !== 'NaN') &&
       rows.some(r => String(r[1]).includes('MISSING FROM PAYLOAD')));
    W._lastRes = RES;

    // The same at the other end: a channel object present but carrying no `revenue`.
    W._lastRes = { ...RES, channel_sales: { Wholesale: { lbs_sold: 1000, by_crop: {} } } };
    const noRevRows = runExport();
    const revRow = noRevRows.find(r => text(r[0]) === 'Wholesale Revenue');
    ok(`a revenue row with no figure does not masquerade as a group name (got ${JSON.stringify(revRow)})`,
       revRow && revRow[1] !== '' && String(revRow[1]).includes('MISSING FROM PAYLOAD'));
    W._lastRes = RES;

    // And the same BELOW the line: a deduction inside `profit` that no row explains. This section
    // reconciles only because the adapter deducts exactly overhead, interest and fixed selling; a
    // fourth deduction would otherwise leave NET PROFIT not summing to its own rows, silently.
    W._lastRes = { ...RES, profit: RES.profit - 3000 };
    rows = runExport();
    ok('an unaccounted below-the-line deduction fires the UNRECONCILED line',
       rows.some(r => text(r[0]).includes('no line above')));
    W._lastRes = RES;
    rows = runExport();
    ok('neither tripwire fires on a consistent statement',
       !rows.some(r => text(r[0]).includes('UNRECONCILED')));
  }

  // ── 5. The file survives a spreadsheet ──────────────────────────────────
  // Browser QA found both of these on the real file: subtotal labels led with "=", so Excel and
  // Sheets parsed every one as a FORMULA and the total rows broke on open, and the indentation was
  // ASCII (see the header comment above). Both are properties of the FILE, so the file is where
  // they are asserted — a check against the source layout would not have caught either.
  {
    W._lastRes = RES; W._lastParams = PARAMS;
    const rows = runExport();
    for (const r of rows) {
      for (const cell of r) {
        ok(`no cell starts with = + or @ (a spreadsheet would treat it as a formula): "${String(cell).slice(0, 50)}"`,
           !/^\s*[=+@]/.test(String(cell)));
      }
      ok(`every row has exactly two columns: ${JSON.stringify(r).slice(0, 60)}`, r.length === 2);
    }

    // The hierarchy is the indentation, so the indentation is what gets pinned: it must exist, it
    // must be U+00A0, and it must never be ASCII space. Checking only "not ASCII space" would pass
    // a statement with no indentation at all — which is the state the grower rejected.
    ok('no line item relies on leading ASCII spaces (importers strip them)',
       !rows.some(r => /^ /.test(r[0] || '')));
    // Together with the line above, this is what pins the indentation: `depth` counts U+00A0
    // blocks specifically, so a statement indented with ASCII spaces or not indented at all fails
    // here. A bare count of indented rows does NOT pin it — it passed on the fixed and bought
    // blocks alone while every COGS indent was deleted, so it is gone.
    ok('components are indented deeper than the total that closes their group',
       depth(rows.find(r => text(r[0]) === EXPECT_VARIABLE_LABELS.seed)[0]) >
       depth(rows.find(r => text(r[0]) === 'Total Cost of Goods Sold')[0]));

    // The three profit lines run flush left, which is what makes them findable in a long statement.
    for (const want of ['GROSS PROFIT', 'OPERATING INCOME', 'NET PROFIT']) {
      const r = rows.find(x => text(x[0]) === want);
      // `r[0] === want`, not `text(r[0]) === want`: the label must carry no indentation at all,
      // which is strictly stronger than depth 0 and makes a depth assertion here redundant.
      ok(`"${want}" prints, flush left, carrying a figure`,
         r && r[0] === want && r[1] !== '');
    }
    // A group NAME carries no figure of its own — the "Total …" line below it does. Printing a
    // number on both is how a reader ends up double-counting a section.
    for (const want of ['Fixed & Committed Costs', 'Bought Capacity']) {
      const r = rows.find(x => text(x[0]) === want);
      ok(`group name "${want}" carries no amount (its total does)`, r && r[1] === '');
    }

    // A total sits one level OUT from the rows it sums. Operating Expenses is the only section
    // with two nested groups, so it is the only place this can go wrong — and it did: the total
    // that adds up the two group totals was printed at their depth, so the indentation stopped
    // saying what rolls into what in exactly the section with the most to say.
    ok('Total Operating Expenses is one level out from the group totals it sums',
       depth(rows.find(r => text(r[0]) === 'Total Operating Expenses')[0]) <
       depth(rows.find(r => text(r[0]) === 'Total Fixed & Committed Costs')[0]));

    // Peak borrowing is cash the plan must HAVE, not money it spends — the charge for carrying it
    // is the interest line. Printed negative in a column headed "negative = cost" it read as
    // $9,000 spent, sitting directly above a positive Opening Cash.
    ok('peak borrowing prints as a positive requirement, not a cost',
       amountOf(rows, 'Peak Borrowing / Working Capital Required') === RES.peak_borrowing);
    // ...and a group with nothing under it does not print as a name with no lines. This fixture's
    // one channel charges no stall fee, which is the common case, so the check is on the shipped
    // path rather than a contrived one.
    ok('a group with no components collapses to a single line carrying its total',
       amountOf(rows, 'Channel Fixed Selling (market fees, retainers)') === -RES.fixed_selling_cost &&
       !rows.some(r => text(r[0]) === 'Total Channel Fixed Selling'));

    // The OTHER branch: a channel that does charge a stall fee prints as a group — name, indented
    // component, then the total. Testing only the empty case would leave the populated one, which
    // is the one with the indentation in it, unexercised.
    // The adapter computes fixed_selling_cost as Σ (per-week fee × 52), so a fixture whose
    // component does not sum to its own total tests a state the app cannot produce — and asserts a
    // "Total …" line that contradicts the row above it. The result is moved with the params.
    const FEE_WK = 25, FEE_YR = FEE_WK * 52;
    W._lastParams = { ...PARAMS,
      channels: [{ name: 'Wholesale', fixed_selling_cost_per_wk: 0 },
                 { name: 'Farmers Market', fixed_selling_cost_per_wk: FEE_WK }] };
    W._lastRes = { ...RES, fixed_selling_cost: FEE_YR,
                   profit: RES.profit - (FEE_YR - RES.fixed_selling_cost) };
    const feeRows = runExport();
    const feeDetail = detailUnder(feeRows, 'Channel Fixed Selling (market fees, retainers)');
    ok(`a channel stall fee prints as an indented component (got ${JSON.stringify(feeDetail)})`,
       feeDetail && feeDetail.length === 1 && feeDetail[0][1] === -FEE_YR);
    ok('the group closes with its own total, and the detail sums to it',
       amountOf(feeRows, 'Total Channel Fixed Selling') === -FEE_YR);
    ok('a consistent populated group fires no tripwire',
       !feeRows.some(r => text(r[0]).includes('UNRECONCILED')));
    W._lastParams = PARAMS; W._lastRes = RES;
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
