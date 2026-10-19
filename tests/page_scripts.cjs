/* The page's two external scripts, in PAGE ORDER: fields.js (the field registry, E5b), then
 * units.js (which derives its registries from it and throws without it). Every harness that runs
 * them outside a browser loads them through here, so the order is stated once — a fifth copy of
 * "fields before units" is how the next reorder breaks one harness and not the others.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PUBLIC = path.join(__dirname, '..', 'public');
const PAGE_SCRIPTS = ['fields.js', 'units.js'];
const source = name => fs.readFileSync(path.join(PUBLIC, name), 'utf8');

/** Run both scripts in a vm sandbox (already a context), in page order. */
function runPageScripts(sandbox) {
  for (const name of PAGE_SCRIPTS) vm.runInContext(source(name), sandbox, { filename: name });
}

/** Replace each script's `<script src>` tag in the page HTML with the script inlined — for jsdom,
 *  which is given no resource loader. Throws if a tag is missing rather than booting without it. */
function inlinePageScripts(html) {
  return PAGE_SCRIPTS.reduce((doc, name) => {
    const tag = new RegExp(`<script src="${name.replace('.', '\\.')}[^"]*"><\\/script>`);
    const out = doc.replace(tag, () => `<script>${source(name)}</script>`);
    if (out === doc) throw new Error(`${name} <script src> tag not found — the page would boot without it`);
    return out;
  }, html);
}

/** The app's main inline <script>: the first one after the LAST external page script. Located
 *  from PAGE_SCRIPTS so a reorder or a third script cannot make one harness read the wrong block. */
function mainInlineScript(html) {
  const lastTag = Math.max(...PAGE_SCRIPTS.map(n => html.indexOf(`<script src="${n}`)));
  const open = html.indexOf('<script>', lastTag);
  const close = html.indexOf('</script>', open);
  if (PAGE_SCRIPTS.some(n => html.indexOf(`<script src="${n}`) < 0) || open < 0 || close < 0) {
    throw new Error('could not locate the main inline <script> in public/index.html');
  }
  return html.slice(open + '<script>'.length, close);
}

module.exports = { runPageScripts, inlinePageScripts, mainInlineScript, PAGE_SCRIPTS };
