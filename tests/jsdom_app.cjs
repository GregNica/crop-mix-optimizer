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
  // Drop the Pyodide loader: it fetches WASM, which jsdom cannot run. Nothing in these flows
  // needs the solver.
  const beforeStrip = doc;
  doc = doc.replace(/<script[^>]*pyodide[^>]*>[\s\S]*?<\/script>/gi, '');
  if (doc === beforeStrip) throw new Error(
    'pyodide loader not found — jsdom would try to fetch WASM it cannot run');

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

module.exports = { bootApp, ROOT };
