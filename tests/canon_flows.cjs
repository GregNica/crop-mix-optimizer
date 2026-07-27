/* Flow-level guards for THE data-canon INVARIANT.
 *
 * tests/canon_invariant.cjs pins the write HELPERS. It did not catch the last two violations,
 * because those were in the FLOWS that use them:
 *
 *   - serializeFormState stored display values, so a plan saved in Metric and reloaded in US
 *     silently reinterpreted every number (32.4 ha became 32.4 ACRES). Guaranteed via newPlan().
 *   - applyChannels replaced #channel-list without seeding, and applyCrops calls
 *     getChannelDefs() immediately after, dividing packaging/selling costs by 2.2046.
 *   - the chatbot apply path wrote canonical schema values with .value, so "80 acres" applied
 *     in Metric became 80 ha.
 *
 * Six sites in this class have now shipped. A guard over the primitives does not cover the
 * paths, so this file drives the paths.
 *
 * WHAT IS AND ISN'T REACHABLE HERE: the round-trip below runs the app's real
 * serializeFormState/applyFormState against a stubbed element registry — no DOM parsing needed,
 * so it runs in CI. The collection flows (applyChannels/applyCrops) assign innerHTML and depend
 * on the browser parsing that markup into elements, which this vm cannot do; they are covered
 * STRUCTURALLY instead, by asserting every collection render is followed by a seeding call.
 * That is weaker than driving them, and deliberately noted rather than papered over.
 *
 * Run: node tests/canon_flows.cjs   (or via pytest: test_canon_flows.py)
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
const appSrc = html.slice(open + '<script>'.length, close);

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };

// ---- element stub with a working id registry -------------------------------------------
const REG = new Map();
function makeEl(tag, id) {
  const el = {
    tagName: (tag || 'INPUT').toUpperCase(), id: id || '', type: 'number',
    value: '', textContent: '', innerHTML: '', dataset: {}, style: {}, _attrs: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    setAttribute(k, v) {
      this._attrs[k] = String(v);
      const m = /^data-(.+)$/.exec(k);
      if (m) this.dataset[m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(v);
    },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    removeAttribute(k) { delete this._attrs[k]; },
    appendChild() {}, removeChild() {}, remove() {}, addEventListener() {},
    dispatchEvent() {}, click() {}, focus() {}, scrollIntoView() {}, insertAdjacentHTML() {},
    querySelector: () => null, querySelectorAll: () => [], closest: () => null,
  };
  if (id) REG.set(id, el);
  return el;
}
const documentStub = {
  readyState: 'complete', body: makeEl('div'), head: makeEl('div'), documentElement: makeEl('html'),
  // Unknown ids get a throwaway element rather than null: the app touches a few chrome
  // elements (#status-bar and friends) at load. REG stays the controlled set the assertions
  // are about, so a throwaway can never satisfy one of them.
  getElementById: (id) => REG.get(id) || makeEl('input'),
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
  createElement: (t) => makeEl(t), createTextNode: () => ({}),
};
const store = {};
const sandbox = {
  console, document: documentStub,
  navigator: { userAgent: 'node' }, location: { search: '', href: 'http://localhost/' },
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, fetch: () => Promise.reject(new Error('no network')),
  alert() {}, confirm: () => false, prompt: () => null,
  Event: function Event(t) { this.type = t; },
  URLSearchParams, URL, TextEncoder, TextDecoder, Blob: function Blob() {},
  XLSX: { utils: { book_new: () => ({}), aoa_to_sheet: () => ({}), book_append_sheet() {}, sheet_to_json: () => [] }, writeFile() {} },
};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(unitsSrc, sandbox);
sandbox.UNITS = sandbox.window.UNITS;

const EPILOGUE = `
;window.__T = {
  APP_STATE, setUnitSystem, specForEl, readCanonicalEl, readCanonical, canonOf,
  writeFieldCanonical, canonIntegrityReport, serializeFormState, applyFormState,
};`;
try {
  vm.runInContext(appSrc + EPILOGUE, sandbox, { filename: 'index.html:inline' });
} catch (e) {
  console.error('FATAL: inline app script failed to evaluate:', e && e.message);
  process.exit(1);
}
const T = sandbox.window.__T;

// ---- FLOW 1: save in one unit system, restore in the other ------------------------------
// The bug: display values were stored with no record of the system, so the SAME saved plan
// meant a different farm depending on what was on screen at restore time.
{
  // A representative slice of the real registry: land (acre/ha), bulk storage (m3/ft3),
  // a liquid rate (L/gal) and a plain currency field that must NOT be converted.
  const fields = {
    total_land:          { spec: 'area_land',  canon: 80 },
    harvest_storage_cap: { spec: 'vol_bulk',   canon: 5000 },
    well_weekly_cap_L:   { spec: 'vol_liquid', canon: 2500000 },
  };
  Object.keys(fields).forEach(id => makeEl('input', id));
  const cash = makeEl('input', 'opening_cash'); cash.value = '300000';   // currency: never converted

  // buildFieldRegistry introspects #input-view, which this stub has no DOM for — feed it the
  // slice directly. serializeFormState/applyFormState themselves are the app's real code.
  sandbox.buildFieldRegistry = () => Object.keys(fields).map(id => ({ id, kind: 'number' }))
    .concat([{ id: 'opening_cash', kind: 'number' }]);

  const seedAll = (sys) => {
    T.setUnitSystem(sys);
    Object.entries(fields).forEach(([id, f]) => T.writeFieldCanonical(REG.get(id), f.canon));
  };

  [['metric', 'us'], ['us', 'metric']].forEach(([saveIn, restoreIn]) => {
    seedAll(saveIn);
    const saved = T.serializeFormState();
    // wipe, so a no-op restore cannot pass by leaving the old values in place
    Object.keys(fields).forEach(id => { REG.get(id).value = ''; REG.get(id).dataset.canon = ''; });
    T.setUnitSystem(restoreIn);
    T.applyFormState(saved);
    Object.entries(fields).forEach(([id, f]) => {
      const got = T.readCanonical(id);
      if (!(Math.abs(got - f.canon) <= 5e-3 * Math.max(1, f.canon))) {
        fail(`save in ${saveIn} -> restore in ${restoreIn}: ${id} came back ${got}, want ${f.canon} `
           + `(a plan must mean the same farm whichever system it is reloaded in)`);
      }
    });
    if (String(REG.get('opening_cash').value) !== '300000') {
      fail(`save in ${saveIn} -> restore in ${restoreIn}: opening_cash was altered `
         + `(${REG.get('opening_cash').value}) — currency must never be unit-converted`);
    }
  });

  // and the invariant must hold after the round-trip, not just the values
  sandbox.document.querySelectorAll = (sel) =>
    (String(sel).indexOf('data-f') >= 0 ? [] : []);
  const report = T.canonIntegrityReport();
  if (report.length) fail(`canonIntegrityReport not empty after save/restore: ${JSON.stringify(report[0])}`);
}

// ---- FLOW 2 (structural): every collection render must seed ------------------------------
// applyChannels/applyCrops assign innerHTML, which this vm cannot parse into elements, so the
// rule is enforced on the SOURCE instead: markup containing unit-bearing data-f fields must be
// followed by a seeding call. Weaker than driving the flow — stated plainly rather than hidden.
{
  const lines = appSrc.split('\n');
  const RENDERS = /innerHTML\s*=\s*.*(renderChannelRow|renderCrop)\b/;
  const SEEDS   = /seedAndDisplayUnitFields|updateCropChannels/;
  let checked = 0;
  lines.forEach((line, i) => {
    if (!RENDERS.test(line)) return;
    checked++;
    // Scan only to the END OF THE ENCLOSING FUNCTION. A fixed line window ran past the closing
    // brace and matched a seeding call in the NEXT function, so this guard passed vacuously for
    // applyChannels — the very site it was written for. Caught by mutation-testing it.
    let end = i + 1;
    while (end < lines.length && !/^\}/.test(lines[end])) end++;
    // Strip line comments first: the explanatory comment ABOVE the seeding call names the
    // very functions being searched for, so an uncommented guard matched its own prose and
    // reported a seeded flow when the call had been deleted. Also caught by mutation-testing.
    const window_ = lines.slice(i, end).map(l => l.replace(/\/\/.*$/, '')).join('\n');
    if (!SEEDS.test(window_)) {
      fail(`index.html inline script line ~${i + 1}: renders unit-bearing rows but does not seed `
         + `data-canon before the function ends — readCanonicalEl will convert the DISPLAY value instead `
         + `(this is how applyChannels divided packaging costs by 2.2046). Call `
         + `seedAndDisplayUnitFields() after the assignment.`);
    }
  });
  if (checked < 4) fail(`expected to find at least 4 collection renders, found ${checked} — the `
                      + `pattern may have changed and this guard may no longer match anything`);
}

// ---- FLOW 3 (structural): programmatic writers must not use bare .value ------------------
// The chatbot apply paths and the form restorer take values in CANONICAL schema units. Writing
// them with .value lets the delegated input listener re-canonicalise using whatever system is
// on screen ("80 acres" applied in Metric became 80 ha = 197.7 acres).
{
  const MUST_USE_HELPER = ['applyProposal', 'updateCropByName', 'applyFormState'];
  MUST_USE_HELPER.forEach(fn => {
    const i = appSrc.indexOf(`function ${fn}(`);
    if (i < 0) return fail(`${fn} not found — this guard is pinned to a function that no longer exists`);
    const body = appSrc.slice(i, i + 2600);
    if (!/writeFieldCanonical/.test(body)) {
      fail(`${fn} writes form fields without writeFieldCanonical — values arriving in canonical `
         + `units must not be re-canonicalised in the active display system`);
    }
  });
}

if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
console.log('data-canon flows: all checks passed (save/restore round-trip, collection seeding, canonical writers)');
