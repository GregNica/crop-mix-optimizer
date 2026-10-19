/* SPREADSHEET SAFETY — every CSV the app writes, driven for real (X1).
 *
 * WHAT THIS GUARDS. Excel and Sheets parse a cell as a FORMULA when its first character is
 * `=`, `+`, `-` or `@`. Browser QA found it the expensive way: the P&L's subtotal labels led
 * with "=" and every total row broke the moment the file opened.
 *
 * WHY IT IS A SEPARATE FILE. The rule is a property of the FILE FORMAT, not of any one report,
 * and until X1 it was enforced by ONE assertion inside the P&L's own harness — so four of the
 * five exporters were never checked at all, and the one that was passed only because its fixture
 * had benign channel names. `downloadCSV()` now owns escaping, the BOM and the anchor for all
 * five, and this file is where that single implementation is held to the rule.
 *
 * WHAT WAS ACTUALLY MEASURED before the fix (the backlog's description was wrong in both
 * directions, and driving the real exports is what showed it):
 *
 *   * exportGanttCSV wrote THREE risky cells, and the important one is not a hostile-input case:
 *     `--- Garlic ---`, the crop separator, is emitted on EVERY export for benign crop names.
 *     A raw crop name in the Crop column (`=Spinach`) was risky too — unmentioned anywhere.
 *   * exportPLCSV wrote ZERO, even with a channel named `+Market`. The backlog said this
 *     reintroduced the defect; it does not. P&L line items are indented with U+00A0, so the cell
 *     starts with a non-breaking space and Excel sees no formula. What DID happen is that the
 *     old assertion, written as `^\s*[=+@]`, flagged those two cells anyway — because JS `\s`
 *     includes U+00A0. It called a safe file dangerous, which is how someone ends up "fixing"
 *     an export that was never broken.
 *
 * So the rule below looks through leading ASCII blanks (an importer that trims " =SUM()" hands
 * Excel a formula) but NOT through U+00A0 (importers preserve it — which is the whole reason the
 * P&L indents with it), and treats a leading `-` as dangerous ONLY when the cell is not a number,
 * because the amount column is full of legitimate negatives.
 *
 * Run: node tests/csv_safety_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp, captureCSV, mkWeeks } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };

// The real rule, stated once. Deliberately NOT `\s`, which would swallow U+00A0.
const FORMULA_LEAD = /^[ \t\r\n]*([-=+@])/;
const startsFormula = s => {
  const lead = FORMULA_LEAD.exec(s);
  return !!lead && (lead[1] !== '-' || !Number.isFinite(Number(s)));
};

// Hostile names a grower can genuinely type into the crop and channel fields. Each is also a
// real formula: `=Spinach` is a name reference, `+Market` and `@SUM` both parse.
const HOSTILE_CROP    = '=Spinach';
const HOSTILE_CHANNEL = '+Market';
const HOSTILE_CROP2   = '@Garlic';


// Numbers borrowed from cost_splits_client.cjs's fixture (which owns them, and guards their
// arithmetic with its own tripwire) with the crop and channel names swapped for hostile ones.
// Not shared into jsdom_app.cjs on purpose: each harness's fixture encodes ITS OWN oracle —
// cost_splits' numbers are deliberately non-derivable, channel_sales' splits are deliberately
// not price-weighted — and merging them would erase three different questions into one.
const RES = {
  revenue: 100000, variable_cost: 21000, fixed_cost: 22400, operating_profit: 55600,
  overhead_cost: 5000, interest_cost: 400, fixed_selling_cost: 1200, profit: 49000,
  peak_borrowing: 9000,
  // W8: the P&L iterates these, so a fixture without them tests a statement that does not
  // reconcile — and the hostile channel would never reach the selling row at all.
  bought_capacity_split: { city_water: 300, overtime: 700, hire: 0 }, overhead_covers: ['admin'],
  fixed_selling_split: { [HOSTILE_CHANNEL]: 1200 },
  variable_cost_split: { water: 1500, fertilizer: 2500, fuel: 900, seed: 8100, packaging: 8000 },
  fixed_cost_split: {
    harvest_storage: 4000, ambient_storage: 750, water_storage: 1000, irrigation: 2000,
    equipment_storage: 1500, fuel_storage: 250, machinery: 6000,
    property_mortgage_rent: 0, other_debt_service: 1500, wages: 5000, city_water_fixed_fee: 400,
  },
  channel_sales: {
    [HOSTILE_CHANNEL]: { lbs_sold: 900, revenue: 100000, by_crop: {
      [HOSTILE_CROP]:  { lbs_sold: 600, revenue: 60000, weekly_lbs: mkWeeks({ 12: 400, 20: 200 }) },
      [HOSTILE_CROP2]: { lbs_sold: 300, revenue: 40000, weekly_lbs: mkWeeks({ 12: 300 }) },
    } },
  },
  succession_schedule: [
    { crop: HOSTILE_CROP,  acres: 10, weeks: [10, 11, 12], phases: [0, 1, 2], name: 'S W10' },
    { crop: HOSTILE_CROP2, acres:  5, weeks: [20, 21],     phases: [0, 2],    name: 'G W20' },
  ],
  weekly_land_frac:   new Array(52).fill(0.2),
  weekly_harvest_vol: new Array(52).fill(10),
  weekly_labor_used:  new Array(52).fill(50),
  weekly_labor_supply: new Array(52).fill(100),
  demand_at_cap_threshold: 0.95,
  demand_saturation: {
    [HOSTILE_CHANNEL]: {
      [HOSTILE_CROP]: {
        basis: 'weekly', cap_lbs: 28000, sold_lbs: 14000, fill: 0.5,
        peak_week_frac: 1.0, peak_week_cap_lbs: 2000, weeks_at_cap: [29, 30], binding: 1.0,
      },
    },
  },
};

const PARAMS = {
  operating_weeks: 52, total_land: 80, opening_cash: 0, credit_line: 0,
  harvest_storage_cap: 500,
  channels: [{ name: HOSTILE_CHANNEL, fixed_selling_cost_per_wk: 5 }],
  crops: [
    { name: HOSTILE_CROP,  yield_per_acre: 5000, harvest_weeks: 1, channels_data: {
        [HOSTILE_CHANNEL]: { price: 4.0, demand_value: 99999 } } },
    { name: HOSTILE_CROP2, yield_per_acre: 4000, harvest_weeks: 1, channels_data: {
        [HOSTILE_CHANNEL]: { price: 4.0, demand_value: 99999 } } },
  ],
};

(async () => {
  const W = await bootApp();
  W._lastRes = RES; W._lastParams = PARAMS; W._ganttRes = RES;

  // All five. The template takes no fixtures; the other four read the hostile plan above.
  const EXPORTS = [
    ['downloadCropTemplate',   () => W.downloadCropTemplate()],
    ['exportPLCSV',            () => W.exportPLCSV()],
    ['exportConstraintCSV',    () => W.exportConstraintCSV()],
    ['exportGanttCSV',         () => W.exportGanttCSV()],
    ['exportWeeklySalesCSV',   () => W.exportWeeklySalesCSV()],
  ];

  let totalCells = 0;
  for (const [name, run] of EXPORTS) {
    ok(`${name} exists on the page`, typeof W[name] === 'function');
    if (typeof W[name] !== 'function') continue;

    const rows = captureCSV(W, run);
    // A silent no-op would make every assertion below vacuously true — the exact shape of the
    // inert guards this repo keeps finding. An export that writes nothing fails here.
    ok(`${name} produced a file`, !!rows && rows.length > 0);
    if (!rows || !rows.length) continue;

    for (const row of rows) {
      for (const cell of row) {
        totalCells++;
        const s = String(cell == null ? '' : cell);
        ok(`${name}: cell would be read as a formula — ${JSON.stringify(s.slice(0, 44))}`,
           !startsFormula(s));
      }
    }
  }

  // NEGATIVE AMOUNTS SURVIVE. Neutralising a leading `-` wholesale would corrupt every cost line
  // in the P&L — every one on this fixture — turning money into text nothing can sum. This is the
  // assertion that stops the formula rule being "fixed" by simply banning `-`.
  //
  // ⚠️ THIS BLOCK WAS DELETED BY ACCIDENT during a /simplify pass that removed the (genuinely
  // subsumed) block above it, and the deletion was invisible: the suite stayed green, because a
  // missing assertion looks exactly like a passing one. Only re-running the mutation afterwards
  // caught it — the ban-the-dash mutation went from dying to SURVIVING. Re-run the mutations
  // after restructuring this file; that is the whole lesson.
  {
    const rows = captureCSV(W, () => W.exportPLCSV());
    const amounts = rows.map(r => String(r[1] == null ? '' : r[1])).filter(v => /^-\d/.test(v));
    ok(`the P&L still writes negative amounts (got ${amounts.length})`, amounts.length > 5);
    for (const v of amounts) {
      ok(`a negative amount stays a NUMBER, not neutralised text: ${JSON.stringify(v)}`,
         Number.isFinite(Number(v)));
    }
  }

  // NEUTRALISATION TOUCHES ONLY WHAT NEEDS IT. This is the other half of the rule and it needs
  // its own assertion: writing the lead pattern with `\s` (which in JS matches U+00A0) still
  // passes every check above — the file stays safe — while quietly prefixing the P&L's indented
  // labels, which were already safe. That is the over-strictness the old assertion shipped with,
  // and the reason it would have cried wolf on a correct file. The indent is 4 U+00A0 per level,
  // so a depth-2 label carries exactly 8; nine means the rule reached a cell it had no business
  // touching. Verified by mutation: `\s` here survives every other assertion in this file.
  {
    const rows  = captureCSV(W, () => W.exportPLCSV());
    const label = rows.map(r => String(r[0] == null ? '' : r[0]))
                      .find(v => v.includes(`${HOSTILE_CHANNEL} Revenue`));
    ok(`the hostile channel's P&L label is present: ${JSON.stringify(label)}`, !!label);
    // W8 moved the SELLING row onto a new, name-keyed path (fixed_selling_split). Prove the
    // hostile name reaches it, and that the statement under test reconciles — a safety check
    // over a broken P&L proves less than it reads as.
    ok('the hostile channel reaches the channel-selling row',
       rows.some(r => String(r[0]).includes(`${HOSTILE_CHANNEL} Fixed Selling`)));
    ok('the fixture P&L reconciles (no UNRECONCILED row)',
       !rows.some(r => String(r[0]).includes('UNRECONCILED')));
    const lead = ((label || '').match(/^\u00a0*/) || [''])[0].length;
    ok(`an already-safe indented label is left alone (${lead} leading U+00A0, want a multiple `
       + `of 4 — an odd count means the formula rule looked through the indent)`,
       lead > 0 && lead % 4 === 0);
  }

  // A cell that IS neutralised must still carry its text, so the grower reads the same label.
  // This block doubles as the proof that the hostile names REACH the files at all: without it,
  // every assertion above could be passing over output that never contained anything dangerous.
  {
    const gantt = captureCSV(W, () => W.exportGanttCSV());
    const sep = gantt.map(r => String(r[0])).find(v => v.includes('---'));
    ok(`the separator row survived and reads normally: ${JSON.stringify(sep)}`,
       !!sep && sep.includes(`--- ${HOSTILE_CROP} ---`));
    ok('...and it is the U+00A0 prefix doing the work, not a mangled label',
       !!sep && sep.charCodeAt(0) === 0xa0);
  }

  if (failures) {
    console.error(`\ncsv_safety_client: ${failures} failure(s)`);
    process.exit(1);
  }
  console.log(`csv safety (client): all checks passed `
    + `(5 exporters, ${totalCells} cells, hostile crop/channel names, negatives intact)`);
})().catch(e => { console.error(e); process.exit(1); });
