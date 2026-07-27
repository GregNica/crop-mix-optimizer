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
const unitsSrc = fs.readFileSync(path.join(ROOT, 'public', 'units.js'), 'utf8');

// --- extract the main inline script (the one following the units.js tag) ---------------
const afterUnits = html.indexOf('<script src="units.js');
const open = html.indexOf('<script>', afterUnits);
const close = html.indexOf('</script>', open);
if (afterUnits < 0 || open < 0 || close < 0) {
  console.error('FATAL: could not locate the main inline <script> in public/index.html');
  process.exit(1);
}
const appSrc = html.slice(open + '<script>'.length, close);

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
vm.runInContext(unitsSrc, sandbox);
sandbox.UNITS = sandbox.window.UNITS;
if (!sandbox.UNITS) { console.error('FATAL: units.js did not set window.UNITS'); process.exit(1); }

// The app's top-level `const`s live in the script's own lexical scope, so append an epilogue
// that publishes exactly what the tests drive.
const EPILOGUE = `
;window.__T = {
  APP_STATE, setUnitSystem,
  parseCropCSV, parseMCMultiTab, parseRainfallXLSX,
  downloadCropTemplate, downloadMCXLSX, downloadRainfallXLSX,
  rainfallUnitOfFile, MC_TAB_UNITS,
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
    // Each template, read back in the system that wrote it, must land on the same canonical
    // crop — rounding of the example row is the only permitted difference.
    Object.keys(a).forEach(k => {
      if (typeof a[k] !== 'number') return;
      near(`crop CSV round-trip ${k}`, b[k], a[k], 5e-3);
    });
    near('crop CSV US is identity (yield)', a.yield_per_acre, 8000, 1e-12);
  }
  // A US-written CSV uploaded while the app is in Metric is a KNOWN limitation of the format
  // (no unit row is parsed back), so it is deliberately not asserted here.
}

if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
console.log('import round-trip: all checks passed (past-data, rainfall, crop CSV; both unit systems)');
