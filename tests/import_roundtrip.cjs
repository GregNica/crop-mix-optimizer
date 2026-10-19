/* Node round-trip test for the data-import paths (crop CSV, Past-Data multi-tab, rainfall).
 *
 * WHY THIS EXISTS
 * Each importer has TWO halves that must agree: a template writer that emits the user's active
 * units, and a parser that converts back to canonical. They live ~200 lines apart in
 * public/index.html, and nothing about the code makes a drift between them visible — a file
 * would simply be written in one unit and read as another, silently rescaling a whole farm's
 * history (and with it the solver's prices, yields and water). That is the exact shape of two
 * bugs already found by review: crop prices compounding x2.2046 per re-render, and rainfall
 * being read in the active system so a legacy mm file became 25.4x.
 *
 * WHAT IT PINS
 *   1. write -> read is identity, in each unit system (the template says what the parser reads)
 *   2. cross-system: a workbook written in US and uploaded in Metric (and vice versa) still
 *      lands on the same canonical numbers — uploads must trust the FILE, not the toggle
 *   3. equivalent user data typed in either system parses to identical canonical values
 *
 * HOW
 * The parsers are ordinary functions inside index.html's one big inline <script>, so we run
 * that script in a vm with a DOM stub (the app already exposes _parseRainfallMatrix and friends
 * on window for exactly this reason) and a SheetJS stub — the real one is a CDN dependency, and
 * these parsers only need aoa_to_sheet/sheet_to_json, which are a few lines to fake.
 *
 * Run directly (`node tests/import_roundtrip.cjs`) or via pytest (test_import_roundtrip.py).
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'public', 'index.html'), 'utf8');

// --- extract the main inline script (the one following the units.js tag) ---------------
const appSrc = require('./page_scripts.cjs').mainInlineScript(html);

// --- minimal DOM / browser stubs -------------------------------------------------------
// Enough for the script to evaluate: it touches the DOM at top level (a status bar, a
// DOMContentLoaded listener) but the import paths themselves are pure data.
function makeEl() {
  const el = {
    style: {}, dataset: {}, value: '', textContent: '', innerHTML: '', href: '', download: '',
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    appendChild() {}, removeChild() {}, remove() {}, setAttribute() {}, removeAttribute() {},
    getAttribute: () => null, addEventListener() {}, dispatchEvent() {}, click() {},
    querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    insertAdjacentHTML() {}, focus() {}, scrollIntoView() {}, contains: () => false,
  };
  return el;
}
const captured = { csv: null, workbook: null };
const documentStub = {
  readyState: 'loading',
  body: makeEl(),
  head: makeEl(),
  documentElement: makeEl(),
  getElementById: () => makeEl(),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  removeEventListener() {},
  createElement(tag) {
    const el = makeEl();
    if (tag === 'a') {
      el.click = function () {
        if (typeof el.href === 'string' && el.href.startsWith('data:text/csv')) {
          captured.csv = decodeURIComponent(el.href.slice(el.href.indexOf(',') + 1));
        }
      };
    }
    return el;
  },
  createTextNode: () => ({}),
};

// SheetJS stub: a "sheet" is just its array-of-arrays. Only the calls these paths make.
const XLSXStub = {
  utils: {
    book_new: () => ({ SheetNames: [], Sheets: {} }),
    aoa_to_sheet: (aoa) => ({ __aoa: aoa.map(r => r.slice()) }),
    book_append_sheet: (wb, ws, name) => { wb.SheetNames.push(name); wb.Sheets[name] = ws; },
    sheet_to_json: (ws) => (ws && ws.__aoa ? ws.__aoa.map(r => r.slice()) : []),
  },
  writeFile: (wb) => { captured.workbook = wb; },
  read: () => { throw new Error('XLSX.read not stubbed — tests build workbooks directly'); },
};

const store = {};
const sandbox = {
  console,
  document: documentStub,
  navigator: { userAgent: 'node', language: 'en-US' },
  location: { search: '', href: 'http://localhost/', hostname: 'localhost' },
  localStorage: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  setTimeout: (fn) => { void fn; return 0; },   // never fire deferred work
  clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0,
  fetch: () => Promise.reject(new Error('no network in tests')),
  alert() {}, confirm: () => false, prompt: () => null,
  Event: function Event(type) { this.type = type; },
  URLSearchParams, URL, TextEncoder, TextDecoder, Blob: function Blob() {},
  XLSX: XLSXStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

// units.js first (browser classic-script path sets window.UNITS), then alias it to the bare
// global the app code refers to.
require('./page_scripts.cjs').runPageScripts(sandbox);   // fields.js, then units.js (E5b)
sandbox.UNITS = sandbox.window.UNITS;
if (!sandbox.UNITS) { console.error('FATAL: units.js did not set window.UNITS'); process.exit(1); }

// The app's top-level `const`s live in the script's own lexical scope, so append an epilogue
// that publishes exactly what the tests drive.
const EPILOGUE = `
;window.__T = {
  APP_STATE, setUnitSystem,
  parseCropCSV, parseMCMultiTab, parseRainfallXLSX,
  downloadCropTemplate, downloadMCXLSX, downloadRainfallXLSX,
  rainfallUnitOfFile, cropCSVUnitSystem, MC_TAB_UNITS, parseMCXLSX, diversitySelect,
  CSV_TEMPLATE_HEADERS, parseCSVLine,
  U_LB, U_ACRE, U_PER_LB, U_MM,
  dispVal, toCanonicalActive,
};`;

try {
  vm.runInContext(appSrc + EPILOGUE, sandbox, { filename: 'index.html:inline' });
} catch (e) {
  console.error('FATAL: the inline app script failed to evaluate in the sandbox');
  console.error('  ' + (e && e.message));
  console.error('  (a DOM/browser API used at top level may need a stub above)');
  process.exit(1);
}
const T = sandbox.window.__T;
if (!T) { console.error('FATAL: epilogue did not publish window.__T'); process.exit(1); }

// --- assertions ------------------------------------------------------------------------
let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const rel = (a, b) => Math.abs(a - b) / Math.max(Math.abs(b), 1e-12);
function near(name, got, want, tol) {
  if (got == null || Number.isNaN(got)) return fail(`${name}: got ${got}`);
  if (rel(got, want) > (tol == null ? 1e-9 : tol)) fail(`${name}: got ${got}, want ${want}`);
}
const withSystem = (sys, fn) => { T.setUnitSystem(sys); return fn(); };

// Conversion factors, restated here on purpose: if units.js changes a factor, these tests
// should fail rather than silently agree with it.
const LB_PER_KG = 2.2046226, ACRE_PER_HA = 2.47105, MM_PER_IN = 25.4;

// ===== 1. Past-Data multi-tab: user data typed in either system => same canonical =========
function mcWorkbook(harvest, acres, revenue, price) {
  const wb = XLSXStub.utils.book_new();
  const S = XLSXStub.utils.aoa_to_sheet;
  XLSXStub.utils.book_append_sheet(wb, S([['crop_name', 'Year_2020'], ['(text)', 'u'], ['Spinach', harvest]]), 'Harvest');
  XLSXStub.utils.book_append_sheet(wb, S([['crop_name', 'Year_2020'], ['(text)', 'u'], ['Spinach', acres]]), 'Acres');
  XLSXStub.utils.book_append_sheet(wb, S([
    ['crop_name', 'channel_name', 'Revenue_2020', 'Price_2020'],
    ['(text)', '(text)', '$', 'p'],
    ['Spinach', 'Wholesale', revenue, price],
  ]), 'Sales');
  return wb;
}
function mcParse(sys, wb) {
  return withSystem(sys, () => {
    T.APP_STATE.mcMultiTabData = null;
    T.parseMCMultiTab(wb);
    const d = T.APP_STATE.mcMultiTabData && T.APP_STATE.mcMultiTabData.Spinach;
    if (!d) return null;
    const ch = d.channels.Wholesale;
    return {
      harvest: d.harvestByYear[2020], acres: d.acresByYear[2020],
      price: ch.priceByYear[2020], sold: ch.soldByYear[2020],
      yield_per_acre: d.harvestByYear[2020] / d.acresByYear[2020],
    };
  });
}
const mcUS = mcParse('us', mcWorkbook(82000, 10, 63000, 1.05));
const mcME = mcParse('metric', mcWorkbook(82000 / LB_PER_KG, 10 / ACRE_PER_HA, 63000, 1.05 * LB_PER_KG));
if (!mcUS || !mcME) {
  fail('past-data: parseMCMultiTab produced no crop data');
} else {
  near('past-data harvest (lb)', mcME.harvest, mcUS.harvest, 1e-9);
  near('past-data acres', mcME.acres, mcUS.acres, 1e-9);
  near('past-data price ($/lb)', mcME.price, mcUS.price, 1e-9);
  near('past-data lbs sold', mcME.sold, mcUS.sold, 1e-9);
  near('past-data yield (lb/acre)', mcME.yield_per_acre, mcUS.yield_per_acre, 1e-9);
  // and the US numbers are the literal canonical inputs (no conversion applied at all)
  near('past-data US is identity', mcUS.harvest, 82000, 1e-12);
  near('past-data revenue/price = lbs', mcUS.sold, 63000 / 1.05, 1e-9);
}

// ===== 2. Past-Data template: write -> read is identity in each system ====================
['us', 'metric'].forEach(sys => {
  const written = withSystem(sys, () => { captured.workbook = null; T.downloadMCXLSX(); return captured.workbook; });
  if (!written) return fail(`past-data template (${sys}): nothing written`);
  const back = mcParse(sys, written);
  if (!back) return fail(`past-data template (${sys}): re-parse produced nothing`);
  // Template example rows are rounded for display, so allow that (and only that) much loss.
  near(`past-data template ${sys} harvest`, back.harvest, 82000, 5e-3);
  near(`past-data template ${sys} acres`, back.acres, 10, 5e-3);
  near(`past-data template ${sys} price`, back.price, 1.05, 5e-3);
});

// ===== 2b. Past-Data structural hazards (silent data loss, not unit conversion) ===========
// A workbook the user built from their own records has no units row. The old "row 2 is
// non-numeric ⇒ units row" heuristic ate the first CROP (crop names are non-numeric too).
{
  const wb = XLSXStub.utils.book_new();
  XLSXStub.utils.book_append_sheet(wb, XLSXStub.utils.aoa_to_sheet(
    [['crop_name', 'Year_2020'], ['Spinach', 100000], ['Garlic', 50000]]), 'Harvest');
  XLSXStub.utils.book_append_sheet(wb, XLSXStub.utils.aoa_to_sheet(
    [['crop_name', 'Year_2020'], ['Spinach', 10], ['Garlic', 5]]), 'Acres');
  withSystem('us', () => { T.APP_STATE.mcMultiTabData = null; T.parseMCMultiTab(wb); });
  const got = Object.keys(T.APP_STATE.mcMultiTabData || {}).sort();
  if (got.join(',') !== 'Garlic,Spinach') fail(`past-data without a units row: parsed [${got}], want both crops (first row must not be eaten)`);
}
// Revenue with no price makes lbs-sold unknowable for that channel-year; counting the OTHER
// channels' sales against the full harvest silently understates sell-through, which scales
// revenue in the objective.
{
  const mk = (blank) => {
    const wb = XLSXStub.utils.book_new(), S = XLSXStub.utils.aoa_to_sheet, A = XLSXStub.utils.book_append_sheet;
    A(wb, S([['crop_name', 'Year_2020', 'Year_2021'], ['(text)', 'u', 'u'], ['Spinach', 100000, 100000]]), 'Harvest');
    A(wb, S([['crop_name', 'Year_2020', 'Year_2021'], ['(text)', 'u', 'u'], ['Spinach', 10, 10]]), 'Acres');
    A(wb, S([['crop_name', 'channel_name', 'Revenue_2020', 'Price_2020', 'Revenue_2021', 'Price_2021'],
             ['(text)', '(text)', '$', 'p', '$', 'p'],
             ['Spinach', 'Wholesale', 40000, 1.00, 40000, 1.00],
             ['Spinach', 'Farmers Market', 60000, 2.00, 60000, blank ? '' : 2.00]]), 'Sales');
    return wb;
  };
  const st = (wb) => withSystem('us', () => {
    T.APP_STATE.mcMultiTabData = null; T.APP_STATE.mcUploadSummary = null;
    T.parseMCMultiTab(wb);
    return (T.APP_STATE.mcUploadSummary || [])[0] || {};
  });
  near('sell-through, all cells filled', st(mk(false)).sellThroughMean, 70, 1e-9);
  near('sell-through, one price cell blank (must not deflate)', st(mk(true)).sellThroughMean, 70, 1e-9);
}
// The legacy single "Data" tab must actually apply its demand caps and std-dev spread — it
// used to import yield and price only, while reporting that sales and risk had been applied.
{
  const hdr = ['crop_name', 'channel_name', 'yield_per_acre_lbs', 'price_per_lb', 'demand_cap_type',
               'demand_annual_lbs', 'demand_weekly_lbs', 'yield_std_dev_pct', 'price_std_dev_pct', 'demand_std_dev_pct'];
  const wb = XLSXStub.utils.book_new();
  XLSXStub.utils.book_append_sheet(wb, XLSXStub.utils.aoa_to_sheet([
    hdr, ['(text)', '(text)', 'lbs/acre', '$/lb', 'type', 'lbs', 'lbs', '%', '%', '%'],
    ['Spinach', 'Wholesale', 8000, 1.10, 'annual', 1200000, '', 12, 8, 20],
  ]), 'Data');
  const out = withSystem('us', () => { T.APP_STATE.mcComputedCVs = null; return T.parseMCXLSX(wb); });
  const row = (out.rows || [])[0];
  if (!row) fail('legacy Data tab: no rows parsed');
  else near('legacy Data tab annualSold', row.annualSold, 1200000, 1e-9);
  const cv = (T.APP_STATE.mcComputedCVs || {}).Spinach;
  if (!cv) fail('legacy Data tab: std-dev columns produced no computed CVs (risk spread silently dropped)');
  else { near('legacy CV yield', cv.yield, 12, 1e-9); near('legacy CV price', cv.price, 8, 1e-9); near('legacy CV demand', cv.demand, 20, 1e-9); }
}
// An imported diversity fraction that is not one of the presets must snap to the nearest,
// not fall through to the browser's first option (10%, a 3x tighter solver constraint).
{
  const sel = T.diversitySelect(0.33);
  if (!/value="0.35"[^>]*selected/.test(sel)) fail(`diversitySelect(0.33) must snap to 35%, got: ${(sel.match(/value="[^"]+"[^>]*selected/) || ['none'])[0]}`);
  if (!/value="0.5"[^>]*selected/.test(T.diversitySelect(0.5))) fail('diversitySelect(0.5) must keep an exact preset selected');
}

// ===== 3. Rainfall: the FILE's units row governs, not the active toggle ===================
// This is the regression that matters most: every template issued before the unit system
// existed is in mm, so a US-mode upload must not silently multiply it by 25.4.
function rainWorkbook(unitLabel, cellValue) {
  const hdr = ['week'], units = ['(1-52)'];
  for (let y = 2000; y < 2020; y++) { hdr.push('Year_' + y); units.push(unitLabel); }
  const rows = [hdr, units];
  for (let w = 1; w <= 52; w++) {
    const r = [w];
    for (let y = 2000; y < 2020; y++) r.push(cellValue);
    rows.push(r);
  }
  const wb = XLSXStub.utils.book_new();
  XLSXStub.utils.book_append_sheet(wb, XLSXStub.utils.aoa_to_sheet(rows), 'Data');
  return wb;
}
function rainParse(sys, wb) {
  return withSystem(sys, () => {
    const r = T.parseRainfallXLSX(wb);
    return r.history ? r.history.data.week_1[0] : null;
  });
}
if (T.rainfallUnitOfFile(['(1-52)', 'mm/week']) !== 'mm') fail('rainfallUnitOfFile: mm/week not detected as mm');
if (T.rainfallUnitOfFile(['(1-52)', 'in/week']) !== 'in') fail('rainfallUnitOfFile: in/week not detected as in');
if (T.rainfallUnitOfFile(null) !== 'mm') fail('rainfallUnitOfFile: unlabelled must default to canonical mm');

const mmFile = rainWorkbook('mm/week', 20);
const inFile = rainWorkbook('in/week', 20 / MM_PER_IN);
[['us', 'US'], ['metric', 'Metric']].forEach(([sys, name]) => {
  near(`rainfall mm-file read in ${name}`, rainParse(sys, mmFile), 20, 1e-9);
  near(`rainfall in-file read in ${name}`, rainParse(sys, inFile), 20, 1e-9);
});

// rainfall template: writes the active unit, and is large enough to actually be uploaded
['us', 'metric'].forEach(sys => {
  const wb = withSystem(sys, () => { captured.workbook = null; T.downloadRainfallXLSX(); return captured.workbook; });
  if (!wb) return fail(`rainfall template (${sys}): nothing written`);
  const aoa = wb.Sheets.Data.__aoa;
  const yearCols = aoa[0].filter(h => /\d{4}/.test(String(h))).length;
  const wantUnit = sys === 'us' ? 'in' : 'mm';
  if (String(aoa[1][1]).indexOf(wantUnit) !== 0) fail(`rainfall template ${sys}: units row says "${aoa[1][1]}", want ${wantUnit}/week`);
  const parsed = withSystem(sys, () => T.parseRainfallXLSX(wb));
  if (!parsed.history) {
    fail(`rainfall template ${sys}: its own parser rejects it (${(parsed.errors || [])[0] && parsed.errors[0].msg}) — ${yearCols} year columns`);
  } else if (parsed.history.data.week_1.some(v => v === 0)) {
    fail(`rainfall template ${sys}: contains zero-filled year columns, which would report a bogus CV`);
  }
});
// the two templates describe the same weather
const wbUS = withSystem('us', () => { captured.workbook = null; T.downloadRainfallXLSX(); return captured.workbook; });
const wbME = withSystem('metric', () => { captured.workbook = null; T.downloadRainfallXLSX(); return captured.workbook; });
['us', 'metric'].forEach(readSys => {
  const a = rainParse(readSys, wbUS), b = rainParse(readSys, wbME);
  if (a == null || b == null) fail(`rainfall cross-system: unparseable in ${readSys}`);
  else near(`rainfall US-file vs Metric-file, read in ${readSys}`, a, b, 5e-3);
});

// ===== 4. Crop CSV: template write -> read, in each system ================================
function cropParse(sys, text) {
  return withSystem(sys, () => {
    const r = T.parseCropCSV(text);
    const c = (r.crops || [])[0];
    if (!c) return { err: (r.errors || []).map(e => e.msg).slice(0, 2) };
    const chName = Object.keys(c.channels_data || {})[0];
    const ch = chName ? c.channels_data[chName] : {};
    return {
      yield_per_acre: c.yield_per_acre, lbs_per_tote: c.lbs_per_tote,
      min_acreage: c.min_acreage_if_planted, seed_cost: c.seed_transplant_cost_per_acre,
      price: ch.price, pkg: ch.pkg, water_plant: c.water_plant,
    };
  });
}
const csvUS = withSystem('us', () => { captured.csv = null; T.downloadCropTemplate(); return captured.csv; });
const csvME = withSystem('metric', () => { captured.csv = null; T.downloadCropTemplate(); return captured.csv; });
if (!csvUS || !csvME) {
  fail('crop CSV: template not captured');
} else {
  const a = cropParse('us', csvUS), b = cropParse('metric', csvME);
  if (a.err || b.err) {
    fail(`crop CSV: parse errors us=${JSON.stringify(a.err)} metric=${JSON.stringify(b.err)}`);
  } else {
    // Pin the ABSOLUTE canonical values from the template's own example row, not just
    // "both parses agree". Comparing two parses to each other passes vacuously when a column
    // is dropped and both sides read 0 — which is exactly how a bug that zeroed every
    // imported water and fuel figure survived the first version of this test.
    const EXPECTED = {                       // template example row EX1 (Spinach), canonical
      yield_per_acre: 8000, lbs_per_tote: 20, min_acreage: 2, seed_cost: 280,
      price: 1.10, pkg: 0.09, water_plant: 10400,
    };
    Object.keys(EXPECTED).forEach(k => {
      if (!(k in a)) return fail(`crop CSV: field "${k}" missing from the parsed crop`);
      if (typeof a[k] !== 'number' || Number.isNaN(a[k])) return fail(`crop CSV: ${k} is ${a[k]}, expected a number`);
      near(`crop CSV canonical ${k}`, a[k], EXPECTED[k], 5e-3);
    });
    // Each template, read back in the system that wrote it, must land on the same canonical
    // crop — rounding of the example row is the only permitted difference.
    Object.keys(a).forEach(k => {
      if (typeof a[k] !== 'number') return;
      near(`crop CSV round-trip ${k}`, b[k], a[k], 5e-3);
    });
    near('crop CSV US is identity (yield)', a.yield_per_acre, 8000, 1e-12);
  }

  // ===== 4b. A stated 0 is a statement, not a missing column ==============================
  // `parseFloat(x) || default` rewrote explicit zeros to form defaults: a file's
  // min_acreage 0 (a legitimate "no floor") became a 1-acre C10 floor and yield 0 became a
  // phantom 2000 lb/acre the farm then solved on — against the import contract (uploads
  // trust the FILE). Blank still defaults; stated nonsense (0 planting weeks) errors loudly.
  const mkCsv = rows => [
    'crop_name,channel_name,price_per_lb,demand_cap_type,demand_weekly_lbs,yield_per_acre_lbs,min_acreage_if_planted,planting_weeks,diversity_max_fraction',
    ...rows,
  ].join('\n');
  const zeroKept = withSystem('us', () =>
    T.parseCropCSV(mkCsv(['Kale,Direct,2.00,weekly_flat,500,0,0,2'])));
  if (zeroKept.errors.length) {
    fail(`crop CSV stated-zero: unexpected errors ${JSON.stringify(zeroKept.errors.map(e => e.msg))}`);
  } else {
    const c = zeroKept.crops[0];
    if (c.min_acreage_if_planted !== 0) fail(`crop CSV: stated min_acreage 0 became ${c.min_acreage_if_planted} — the silent 1-acre floor is back`);
    if (c.yield_per_acre !== 0) fail(`crop CSV: stated yield 0 became ${c.yield_per_acre} — a phantom default yield (validation refuses 0 later, with a message)`);
  }
  const blankDefaults = withSystem('us', () =>
    T.parseCropCSV(mkCsv(['Kale,Direct,2.00,weekly_flat,500,,,'])));
  if (blankDefaults.errors.length) {
    fail(`crop CSV blank-defaults: unexpected errors ${JSON.stringify(blankDefaults.errors.map(e => e.msg))}`);
  } else {
    const c = blankDefaults.crops[0];
    if (c.yield_per_acre !== 2000) fail(`crop CSV: blank yield gave ${c.yield_per_acre}, expected the 2000 default`);
    if (c.min_acreage_if_planted !== 1) fail(`crop CSV: blank min_acreage gave ${c.min_acreage_if_planted}, expected the 1 default`);
  }
  const statedNonsense = withSystem('us', () =>
    T.parseCropCSV(mkCsv(['Kale,Direct,2.00,weekly_flat,500,8000,2,0'])));
  if (!statedNonsense.errors.some(e => e.field === 'planting_weeks')) {
    fail('crop CSV: a STATED planting_weeks of 0 imported without an error — silently defaulting '
       + 'it is the coercion class, and forwarding it is garbage; it must be refused loudly');
  }
  // A stated FRACTION in a whole-number column is refused too — it used to pass the ≥1 gate
  // and then be silently truncated by intOr ("1.5 planting weeks" became 1).
  const statedFraction = withSystem('us', () =>
    T.parseCropCSV(mkCsv(['Kale,Direct,2.00,weekly_flat,500,8000,2,1.5'])));
  if (!statedFraction.errors.some(e => e.field === 'planting_weeks' && /whole number/.test(e.msg))) {
    fail('crop CSV: a stated planting_weeks of 1.5 was not refused — intOr silently truncates it to 1');
  }
  // Stated diversity 0 is refused AT IMPORT because nothing downstream can refuse it: the
  // crop card renders diversity through a preset select that cannot express 0, so it would
  // be snapped to a preset with a success message and validate.py would never see the file's
  // value.
  const statedZeroDiversity = withSystem('us', () =>
    T.parseCropCSV(mkCsv(['Kale,Direct,2.00,weekly_flat,500,8000,2,2,0'])));
  if (!statedZeroDiversity.errors.some(e => e.field === 'diversity_max_fraction')) {
    fail('crop CSV: a stated diversity_max_fraction of 0 was not refused — the select would '
       + 'silently snap it to a preset');
  }
  // First-row-wins retry: when a crop's FIRST row fails the crop-level check, the error must
  // name that row, the import must abort (all-or-nothing), and the next row must have been
  // validated as the would-be source (a second bad row must produce its own error).
  const retry = withSystem('us', () => T.parseCropCSV(mkCsv([
    'Kale,Direct,2.00,weekly_flat,500,8000,2,0',
    'Kale,Wholesale,1.00,weekly_flat,900,8000,2,3',
  ])));
  if (retry.crops.length !== 0) fail('crop CSV: a file with errors must import nothing (all-or-nothing)');
  const rowsFlagged = retry.errors.filter(e => e.field === 'planting_weeks').map(e => e.row);
  // Header is row 1, so the bad first data row is row 2; the valid row 3 is promoted to the
  // first-row-wins source and passes validation without an error of its own.
  if (JSON.stringify(rowsFlagged) !== JSON.stringify([2])) {
    fail(`crop CSV: expected exactly row 2 flagged (row 3 is valid and becomes the retried `
       + `first-row source), got rows ${JSON.stringify(rowsFlagged)}`);
  }
  const retryBothBad = withSystem('us', () => T.parseCropCSV(mkCsv([
    'Kale,Direct,2.00,weekly_flat,500,8000,2,0',
    'Kale,Wholesale,1.00,weekly_flat,900,8000,2,0',
  ])));
  if (retryBothBad.errors.filter(e => e.field === 'planting_weeks').length !== 2) {
    fail('crop CSV: after a bad first row, the promoted second row must be validated too — '
       + 'a bad row 2 sailed through as the unvalidated first-row-wins source');
  }

  // Cross-system: the units row is what decides, so a CSV downloaded in one system and
  // uploaded in the other must still land on the same canonical crop. Without this, a
  // colleague's US export opened in Metric reads 8000 lb/acre as 8000 kg/ha (2.2x).
  if (T.cropCSVUnitSystem(['(text)', 'lb/acre', '$/lb']) !== 'us') fail('cropCSVUnitSystem: lb/acre row not detected as US');
  if (T.cropCSVUnitSystem(['(text)', 'kg/ha', '$/kg']) !== 'metric') fail('cropCSVUnitSystem: kg/ha row not detected as Metric');
  if (T.cropCSVUnitSystem(['(text)', 'days int>0']) !== null) fail('cropCSVUnitSystem: unlabelled row must return null (caller keeps old behaviour)');
  if (T.cropCSVUnitSystem(null) !== null) fail('cropCSVUnitSystem: missing row must return null');
  // A pre-metric template mixed canonical litres with US acres ("lbs/acre" + "L/ac/wk"); no
  // single system describes that, and the compound water spec needs one for both halves — so
  // it must decline and let the toggle decide rather than half-trusting the file.
  if (T.cropCSVUnitSystem(['(text)', 'lbs/acre', 'L/ac/wk', '$/lb']) !== null)
    fail('cropCSVUnitSystem: a row mixing US mass/area with canonical litres must return null');
  if (T.cropCSVUnitSystem(['(text)', 'lb/acre', 'gal/acre/wk', '$/lb']) !== 'us')
    fail('cropCSVUnitSystem: a consistent US row must be detected as US');
  if (T.cropCSVUnitSystem(['(text)', 'kg/ha', 'L/ha/wk', '$/kg']) !== 'metric')
    fail('cropCSVUnitSystem: a consistent Metric row must be detected as Metric');

  [['us', csvUS], ['metric', csvME]].forEach(([wroteIn, csv]) => {
    const home = cropParse(wroteIn, csv);
    ['us', 'metric'].forEach(readIn => {
      const away = cropParse(readIn, csv);
      if (home.err || away.err) return fail(`crop CSV cross-system: parse error (${wroteIn} file read in ${readIn})`);
      Object.keys(home).forEach(k => {
        if (typeof home[k] !== 'number' || Number.isNaN(home[k]))
          return fail(`crop CSV cross-system: ${k} is ${home[k]}, expected a number`);
        near(`crop CSV ${wroteIn}-file read in ${readIn}: ${k}`, away[k], home[k], 1e-9);
      });
    });
  });
}

// ---- crop CSV: the fields B.3 added must survive the round-trip -------------------------------
// Without these columns the writer drops shelf life and the cold flag, the parser defaults them
// to strict-1-week + refrigerated, and every export/import cycle silently re-creates the B.3
// regression the audit exists to undo. Garlic is the case that shows it: 16 sellable weeks in a
// barn is the whole point of the ambient pool.
{
  const hdr = T.CSV_TEMPLATE_HEADERS;
  ['sellable_weeks', 'needs_cold_storage', 'sell_through_pct'].forEach(col => {
    if (!hdr.includes(col)) fail(`crop CSV: header contract is missing "${col}"`);
  });
  const row = ['Garlic','10-1','4-30','','','196','1','1','2000','40','5','0.6','5','1','10',
               '8000','6000','5000','0.40','0.20','0.15','4.0','1.5','3.0','150',
               '16','FALSE','TRUE','90','Wholesale','3.00','0.20','annual','200000','','',''];
  if (row.length !== hdr.length) {
    fail(`crop CSV: test row has ${row.length} cells for ${hdr.length} headers — fix the row`);
  } else {
    const r = withSystem('us', () => T.parseCropCSV(hdr.join(',') + '\n' + row.join(',')));
    if ((r.errors || []).length) fail('crop CSV: parse errors ' + JSON.stringify(r.errors));
    else {
      const c = r.crops[0];
      if (c.sales_spread_weeks !== 16)
        fail(`crop CSV: sellable_weeks 16 came back as ${c.sales_spread_weeks} — a clamp or a `
           + `missing column is eating shelf life on import`);
      if (c.cold_storage !== false)
        fail(`crop CSV: needs_cold_storage FALSE came back as ${c.cold_storage} — an ambient `
           + `crop silently returns to the cooler through the import door`);
      if (c.sell_through_pct !== 90)
        fail(`crop CSV: sell_through_pct 90 came back as ${c.sell_through_pct}`);
      // Without an `overwinters` column a round-trip silently clears the flag, and a
      // fall-planted crop then has NO valid successions at all — garlic disappears from the
      // plan with no warning, because weeks 46-48 plus a 35-week cycle cannot fit in the year.
      if (c.overwinters !== true)
        fail(`crop CSV: overwinters TRUE came back as ${c.overwinters} — a fall-planted crop `
           + `loses its only route to a succession through the import door`);
    }
  }
}

// ---- crop CSV: phase-resource columns must carry their PER-WEEK dimension --------------------
// Every phase rate is charged once for EACH week of the phase (farm_v2/utils/labor.py and
// water.py, solver.py for fert/fuel). The columns were named `labor_plant_hr_ac` etc until
// 2026-07-29 — "hours per acre", no week in it — so a grower who entered a per-acre TOTAL for a
// 3-week planting was charged 3x. Renaming is only half the fix: files saved under the old names
// must still import to the SAME numbers, because the stored value was always per-week.
{
  const hdr = T.CSV_TEMPLATE_HEADERS;
  // The unit row is the second line of the template and is what a grower reads while filling
  // it in. It is a positional array with no key, so adding a header without adding its unit
  // entry shifts every hint after it by one column — silently. That shipped: `overwinters` was
  // added to the headers and not here, which labelled demand_annual_lbs "lbs/wk" and
  // demand_weekly_lbs "lbs/yr". The importer accepts both, so the swapped caps would have gone
  // straight into the solve with no error.
  {
    const csv = withSystem('metric', () => { captured.csv = null; T.downloadCropTemplate(); return captured.csv; });
    const lines = String(csv || '').split('\n');
    // Split with the app's own CSV parser: unit hints contain commas ("weeks int 1-52,
    // incl. harvest week"), so a naive split counts cells that are not there.
    const hdrCells = T.parseCSVLine(lines[0]).length;
    const unitCells = T.parseCSVLine(lines[1]).length;
    if (hdrCells !== unitCells)
      fail(`crop CSV: header row has ${hdrCells} cells but the unit row has ${unitCells} — `
         + `every unit hint after the mismatch describes the wrong column`);
    if (/undefined/.test(lines[1]))
      fail(`crop CSV: unit row contains "undefined" — it is shorter than the header row`);
  }

  const BARE = /^(labor|water|fert|fuel)_(plant|grow|harv)_(hr|L|lb)_ac$/;
  ['labor_plant_hr_ac_wk','water_grow_L_ac_wk','fert_harv_lb_ac_wk','fuel_plant_L_ac_wk'].forEach(c => {
    if (!hdr.includes(c)) fail(`crop CSV: header contract is missing "${c}"`);
  });
  hdr.forEach(c => {
    if (BARE.test(c)) fail(`crop CSV: "${c}" names no week, but the solver charges it once per `
                         + `week of the phase — the label invites a per-acre total`);
  });

  const row = ['Garlic','10-1','4-30','','','196','1','1','2000','40','5','0.6','5','1','10',
               '8000','6000','5000','0.40','0.20','0.15','4.0','1.5','3.0','150',
               '16','FALSE','TRUE','90','Wholesale','3.00','0.20','annual','200000','','',''];
  const legacyHdr = hdr.map(c => c.replace(/^((?:labor|water|fert|fuel)_(?:plant|grow|harv)_(?:hr|L|lb)_ac)_wk$/, '$1'));
  if (legacyHdr.join(',') === hdr.join(',')) {
    fail('crop CSV: legacy header derivation is a no-op — the rename test is inert');
  } else if (row.length !== hdr.length) {
    fail(`crop CSV: test row has ${row.length} cells for ${hdr.length} headers — fix the row`);
  } else {
    const now = withSystem('us', () => T.parseCropCSV(hdr.join(',')       + '\n' + row.join(',')));
    const old = withSystem('us', () => T.parseCropCSV(legacyHdr.join(',') + '\n' + row.join(',')));
    if ((now.errors || []).length) fail('crop CSV: new headers failed to parse ' + JSON.stringify(now.errors));
    else if ((old.errors || []).length) fail('crop CSV: legacy headers failed to parse ' + JSON.stringify(old.errors));
    else {
      const a = now.crops[0], b = old.crops[0];
      ['labor_plant','labor_grow','labor_harv','water_plant','water_grow','water_harv',
       'fert_plant','fert_grow','fert_harv','fuel_plant','fuel_grow','fuel_harv'].forEach(f => {
        if (a[f] !== b[f])
          fail(`crop CSV: "${f}" imports as ${a[f]} under the new header but ${b[f]} under the `
             + `legacy one — the rename silently rescaled a saved file`);
      });
      if (a.labor_plant !== 5)
        fail(`crop CSV: labor_plant 5 came back as ${a.labor_plant} — a phase rate is being `
           + `rescaled on import`);
    }
  }
}

if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
console.log('import round-trip: all checks passed (past-data, rainfall, crop CSV; both unit systems)');
