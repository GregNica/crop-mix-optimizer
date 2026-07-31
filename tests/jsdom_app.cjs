/* Boot the real app in jsdom, for tests that need a DOM that actually parses innerHTML.
 *
 * The hand-rolled element stubs in canon_invariant.cjs are fine for testing pure helpers, but
 * the collection flows (applyChannels/applyCrops/loadCropsFromData) work by assigning innerHTML
 * and then querying the elements that produces. A stub cannot do that, so those flows could
 * only ever be checked by pattern-matching the source — which shipped two inert guards before
 * mutation-testing caught them.
 *
 * jsdom parses markup for real, so those flows can be DRIVEN. It is not a browser: no layout,
 * no WASM, so Pyodide (and therefore anything requiring a solve) is out of scope here. That is
 * a smoke-test job for a real browser, deliberately not attempted in this harness.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '..');

/** Boot index.html in jsdom and resolve once the app's DOMContentLoaded work has run. */
function bootApp({ quiet = true } = {}) {
  const html = fs.readFileSync(path.join(ROOT, 'public', 'index.html'), 'utf8');
  const units = fs.readFileSync(path.join(ROOT, 'public', 'units.js'), 'utf8');

  // Inline units.js — jsdom is given no resource loader on purpose (no network, no surprise
  // fetches), so the <script src> would silently never load and UNITS would be undefined.
  let doc = html.replace(/<script src="units\.js[^"]*"><\/script>/,
                         `<script>${units}</script>`);
  if (doc === html) throw new Error(
    'units.js <script src> tag not found — jsdom would boot the app with UNITS undefined');
  // Drop the Pyodide kick-off: it injects a loader that fetches WASM, which jsdom cannot run.
  // Nothing in these flows needs the solver. (The loader is injected by bootPyodide() rather
  // than a static <script src>, so disabling the call is what stops the fetch.)
  const beforeStrip = doc;
  doc = doc.replace(/^bootPyodide\(\);$/m, '/* bootPyodide() disabled under jsdom */');
  if (doc === beforeStrip) throw new Error(
    'bootPyodide() kick-off not found — jsdom would try to fetch WASM it cannot run');

  const dom = new JSDOM(doc, {
    runScripts: 'dangerously',
    url: 'http://localhost:3000/',
    beforeParse(w) {
      w.fetch = () => Promise.reject(new Error('no network in tests'));
      w.alert = () => {}; w.confirm = () => false; w.prompt = () => null;
      if (quiet) {
        // The app logs its in-page self-tests and warns about absent server routes; silence
        // that so real assertion failures are visible.
        w.console.log = () => {}; w.console.info = () => {};
        w.console.warn = () => {}; w.console.error = () => {};
      }
    },
  });

  // Poll for readiness rather than guessing a delay. Measured, the app finishes its
  // DOMContentLoaded work within a single macrotask; a fixed sleep is dead wait today and a
  // latent flake later — and a flow running against a half-booted window would fail somewhere
  // confusing instead of here.
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 5000;
    const ready = () => dom.window.document.querySelectorAll('#crop-list .crop-detail').length > 0;
    (function poll() {
      if (ready()) return resolve(dom.window);
      if (Date.now() > deadline)
        return reject(new Error('app did not finish DOMContentLoaded init within 5s '
                              + '(no .crop-detail cards rendered)'));
      setTimeout(poll, 10);
    })();
  });
}

/** Split one CSV row, honouring quotes and escaped quotes.
 *
 * A real quoted-CSV split, not `row.split(',')`. Cells in these exports hold things like
 * "2,000 lb/wk cap", so splitting on every comma silently shifts every column after it — which
 * is how one of these tests once "failed" against a correct exporter. It also beats matching
 * only quoted cells (`/"(...)"/g`), which silently DROPS an unquoted cell instead of
 * mis-splitting it: absence rather than corruption, the harder failure to see.
 */
function splitCSVRow(row) {
  const out = [];
  let cur = '', q = false;
  for (let i = 0; i < row.length; i++) {
    const c = row[i];
    if (c === '"') {
      if (q && row[i + 1] === '"') { cur += '"'; i++; } else { q = !q; }
    } else if (c === ',' && !q) { out.push(cur); cur = ''; }
    else cur += c;
  }
  out.push(cur);
  return out;
}

/** Run `trigger` and return the CSV it downloaded, as rows of cells (null if it produced none).
 *
 * The exporters build an `<a href="data:text/csv,...">` and click it, so a test has to intercept
 * that. Three harnesses had grown their own version of this interception; one of them replaced
 * `HTMLElement.prototype.click` permanently, which silently no-ops every later click in the
 * window. This restores `createElement` afterwards, so the patch cannot outlive the call.
 */
function captureCSV(W, trigger) {
  let csv = null;
  const origCreate = W.document.createElement.bind(W.document);
  W.document.createElement = function (tag) {
    const el = origCreate(tag);
    if (tag === 'a') el.click = () => {
      csv = decodeURIComponent((el.href || '').replace(/^data:text\/csv;charset=utf-8,/, ''));
    };
    return el;
  };
  try {
    trigger();
  } finally {
    W.document.createElement = origCreate;
  }
  if (csv === null) return null;
  // \uFEFF as an escape, not a literal: the BOM is invisible in the source, and the exporter
  // that writes it uses the escape for the same reason.
  return csv.replace(/^\uFEFF/, '').split('\n').map(splitCSVRow);
}

/** A 52-week array from a {week: value} map — `mkWeeks({12: 400})` is week 12 = 400, rest 0.
 *  Pure array shaping with no expectation baked in, so it is machinery and belongs here; the
 *  FIXTURES that use it stay in their own harnesses, because each one's numbers are its oracle. */
function mkWeeks(byWeek) {
  return Array.from({ length: 52 }, (_, i) => byWeek[i + 1] || 0);
}

module.exports = { bootApp, ROOT, splitCSVRow, captureCSV, mkWeeks };
