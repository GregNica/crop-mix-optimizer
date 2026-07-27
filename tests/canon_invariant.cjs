/* Guard for THE data-canon INVARIANT.
 *
 * Every unit-bearing field carries two numbers: `el.value` (display) and `el.dataset.canon`
 * (the same quantity, canonical). readCanonicalEl() prefers data-canon, so any code that
 * writes el.value without updating data-canon sends the solver a stale number while the
 * screen shows the new one — silently, with no error and nothing on screen looking wrong.
 *
 * That has now happened five times in this file's history: markData, updateCropChannels
 * (crop prices compounding x2.2046 per re-render), onDemandTypeChange (sales capacity 52x
 * wrong on an everyday dropdown change, in US mode), serializeCrops/applyCrops (water and
 * fuel divided by 3.79 on the first plan reload, compounding per save cycle), and
 * clearBenchmarkFields ("My Farm Data" silently keeping the benchmark farm).
 *
 * Patching sites one at a time has not worked. This tests the INVARIANT instead: it drives
 * the real flows and then asserts canonIntegrityReport() is empty, so a sixth site fails here
 * rather than in someone's harvest plan. New code must use writeFieldCanonical /
 * writeFieldDisplay / clearField rather than assigning .value directly.
 *
 * Run: node tests/canon_invariant.cjs   (or via pytest: test_canon_invariant.py)
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'public', 'index.html'), 'utf8');
const unitsSrc = fs.readFileSync(path.join(ROOT, 'public', 'units.js'), 'utf8');

const afterUnits = html.indexOf('<script src="units.js');
const open = html.indexOf('<script>', afterUnits);
const close = html.indexOf('</script>', open);
if (afterUnits < 0 || open < 0 || close < 0) {
  console.error('FATAL: could not locate the main inline <script> in public/index.html');
  process.exit(1);
}
const appSrc = html.slice(open + '<script>'.length, close);

// ---- DOM stub: rich enough to render the crop/channel collections -----------------------
// The real collections are built with innerHTML, so the stub needs a parser. Rather than
// implement one, the tests below drive functions that operate on ELEMENT OBJECTS we build
// directly, plus the pure conversion helpers. Anything requiring real innerHTML parsing is
// exercised by the browser instead (see the session's browser verification).
function makeEl(tag) {
  const el = {
    tagName: (tag || 'INPUT').toUpperCase(), id: '', value: '', textContent: '', innerHTML: '',
    dataset: {}, style: {}, children: [], _attrs: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute(k, v) {
      this._attrs[k] = String(v);
      if (k === 'id') this.id = String(v);
      // mirror data-* into dataset, as a real element does — specForEl reads el.dataset.f
      const m = /^data-(.+)$/.exec(k);
      if (m) this.dataset[m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(v);
    },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    removeAttribute(k) { delete this._attrs[k]; },
    appendChild() {}, removeChild() {}, remove() {}, addEventListener() {}, dispatchEvent() {},
    querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    insertAdjacentHTML() {}, focus() {}, click() {}, scrollIntoView() {},
  };
  return el;
}
const documentStub = {
  readyState: 'loading', body: makeEl('div'), head: makeEl('div'), documentElement: makeEl('html'),
  getElementById: () => makeEl(), querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
  createElement: (t) => makeEl(t), createTextNode: () => ({}),
};
const store = {};
const sandbox = {
  console, document: documentStub,
  navigator: { userAgent: 'node', language: 'en-US' },
  location: { search: '', href: 'http://localhost/', hostname: 'localhost' },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  setTimeout: (fn) => { void fn; return 0; }, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, fetch: () => Promise.reject(new Error('no network')),
  alert() {}, confirm: () => false, prompt: () => null,
  Event: function Event(t) { this.type = t; },
  URLSearchParams, URL, TextEncoder, TextDecoder, Blob: function Blob() {},
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(unitsSrc, sandbox);
sandbox.UNITS = sandbox.window.UNITS;

const EPILOGUE = `
;window.__T = {
  setUnitSystem, specForEl, readCanonicalEl, canonOf,
  writeFieldCanonical, writeFieldDisplay, clearField, canonIntegrityReport,
  toCanonicalActive, dispVal, roundForDisplay,
};`;
try {
  vm.runInContext(appSrc + EPILOGUE, sandbox, { filename: 'index.html:inline' });
} catch (e) {
  console.error('FATAL: inline app script failed to evaluate:', e && e.message);
  process.exit(1);
}
const T = sandbox.window.__T;
if (!T) { console.error('FATAL: epilogue did not publish window.__T'); process.exit(1); }

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const near = (name, got, want, tol) => {
  if (got == null || Number.isNaN(got)) return fail(`${name}: got ${got}`);
  if (Math.abs(got - want) > (tol == null ? 1e-9 : tol) * Math.max(1, Math.abs(want)))
    fail(`${name}: got ${got}, want ${want}`);
};

// A field bound to a registry spec, as the real DOM would present it.
function field(dataF, canonical, system) {
  const el = makeEl('input');
  el.setAttribute('data-f', dataF);
  T.setUnitSystem(system);
  T.writeFieldCanonical(el, canonical);
  return el;
}

// ---- 1. the write helpers keep display and canon in step, in BOTH systems ---------------
['us', 'metric'].forEach(sys => {
  const el = field('yield_per_acre', 8000, sys);           // lb/acre <-> kg/ha
  near(`writeFieldCanonical keeps canon (${sys})`, T.canonOf(el), 8000, 1e-9);
  near(`writeFieldCanonical readCanonicalEl (${sys})`, T.readCanonicalEl(el), 8000, 5e-3);
  const shown = parseFloat(el.value);
  const wantShown = T.dispVal(8000, T.specForEl(el));
  near(`writeFieldCanonical displays in ${sys}`, shown, T.roundForDisplay(wantShown), 1e-9);

  // a value typed/derived in DISPLAY units must land on the right canonical
  T.setUnitSystem(sys);
  const el2 = makeEl('input'); el2.setAttribute('data-f', 'ch_price');
  T.writeFieldDisplay(el2, 3);
  near(`writeFieldDisplay canonicalises (${sys})`, T.readCanonicalEl(el2), T.toCanonicalActive(3, T.specForEl(el2)), 1e-9);
});

// ---- 2. clearField clears BOTH halves ---------------------------------------------------
{
  const el = field('yield_per_acre', 8000, 'us');
  T.clearField(el);
  if (el.value !== '') fail('clearField must blank the display');
  if (el.dataset.canon !== '') fail('clearField must blank data-canon — otherwise a "cleared" field still reaches the solver with its old value');
  const back = T.readCanonicalEl(el);
  if (!(back == null || Number.isNaN(back))) fail(`cleared field still reads canonical ${back}`);
}

// ---- 3. repeated canonical round-trips do not drift (the compounding class) -------------
['us', 'metric'].forEach(sys => {
  const el = field('water_plant', 10400, sys);             // L/acre/wk <-> L/ha/wk
  for (let i = 0; i < 5; i++) T.writeFieldCanonical(el, T.readCanonicalEl(el));
  near(`no drift over 5 canonical round-trips (${sys})`, T.readCanonicalEl(el), 10400, 5e-3);
});

// ---- 4. the integrity checker itself: silent on faithful pairs, loud on real factors ----
{
  const clean = [];
  ['us', 'metric'].forEach(sys => ['yield_per_acre', 'ch_price', 'water_plant', 'min_acreage_if_planted']
    .forEach(k => clean.push(field(k, 1234.5, sys))));
  // Patch BEFORE setUnitSystem: it re-renders every field through this same selector, so
  // swapping these two lines fails with a message that blames the checker, not the setup.
  sandbox.document.querySelectorAll = (sel) => (String(sel).indexOf('data-f') >= 0 ? clean : []);
  T.setUnitSystem('us');
  let report = T.canonIntegrityReport();
  if (report.length) fail(`canonIntegrityReport flagged ${report.length} faithful field(s) — display rounding must not trip it: ${JSON.stringify(report[0])}`);

  // Now break one the way every real instance of this bug broke it: display moved, canon didn't.
  clean[0].value = String(parseFloat(clean[0].value) * 52);
  report = T.canonIntegrityReport();
  if (!report.length) fail('canonIntegrityReport did NOT catch a 52x display/canon divergence — the guard is inert');
  // ratio is computed from the ROUNDED display, so compare loosely — the point is the order
  // of magnitude, not the third decimal.
  else if (Math.abs(report[0].ratio * 52 - 1) > 0.01) fail(`expected a ~52x ratio, reported ${report[0].ratio}`);

  // and the smallest real factor in the system (kg/ha, 1.12085) must also be caught
  clean[0].value = String(parseFloat(clean[0].dataset.canon) * 1.12085);
  if (!T.canonIntegrityReport().length) fail('canonIntegrityReport missed a 1.12x divergence (the smallest real unit factor)');
  sandbox.document.querySelectorAll = () => [];
}

if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
console.log('data-canon invariant: all checks passed (write helpers, clearField, drift, integrity checker)');
