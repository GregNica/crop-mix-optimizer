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
  // Drop the Pyodide loader: it fetches WASM, which jsdom cannot run. Nothing in these flows
  // needs the solver.
  doc = doc.replace(/<script[^>]*pyodide[^>]*>[\s\S]*?<\/script>/gi, '');

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

  return new Promise((resolve) => setTimeout(() => resolve(dom.window), 300));
}

module.exports = { bootApp, ROOT };
