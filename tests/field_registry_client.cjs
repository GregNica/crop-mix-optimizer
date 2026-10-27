/* ONE FIELD REGISTRY, AND IT MATCHES THE FORM IN BOTH DIRECTIONS (E5b).
 *
 * public/fields.js replaced six hand-kept lists (units.js FIELD_REGISTRY / DATA_F_REGISTRY,
 * BENCHMARK_DEFAULTS, the Worker's CHATBOT_FIELDS / CROP_DETAIL_FIELDS, and the payload builder's
 * implicit list). This drives the REAL page and requires:
 *
 *   1. every flat input the form renders has a `form` entry, and every entry is rendered;
 *   2. every data-f the crop/channel rows render has a `crop` entry, and every entry is rendered;
 *   3. every non-UI form field feeds at least one `payload` key (an input that reaches nothing is
 *      a dead input — the class the shelf-life box was), and no UI toggle does;
 *   4. the page's views ARE the registry (the objects the app reads, not copies of it);
 *   5. `payload` matches the BUILDER: the main solve sends exactly the declared keys, and nudging
 *      each declared source field moves its key — `from` is measured, not trusted.
 *
 * The other half — the registry against the Python adapter, the golden payload and the bundled
 * Worker — is tests/test_field_registry.py.
 *
 * Run: node tests/field_registry_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };
const diff = (a, b) => [...a].filter(x => !b.has(x));

(async () => {
  const dom = await bootApp();
  const W = dom.window, D = W.document;
  const F = W.FARM_FIELDS;
  ok('FARM_FIELDS is loaded on the page', F && F.form && F.crop && F.payload);

  // 1. Flat inputs, both directions.
  const rendered = new Set(W.eval('buildFieldRegistry()').map(f => f.id));
  const declared = new Set(Object.keys(F.form));
  ok(`every rendered flat input is registered (missing: ${JSON.stringify(diff(rendered, declared))})`,
     diff(rendered, declared).length === 0);
  ok(`every registered flat input is rendered (stale: ${JSON.stringify(diff(declared, rendered))})`,
     diff(declared, rendered).length === 0);

  // 2. Crop / channel / fixed-layer inputs, both directions. The plots card, the crop cards' plot
  //    ticks and the commitment rows (Batch FX) render nothing on the shipped demo, so open two plots
  //    and add one commitment of each kind to a crop card first — then every registered data-f must
  //    be on the page and every data-f on the page registered. A row input that reached no entry
  //    would convert in no unit system, silently.
  W.eval("startPlots(); const card = document.querySelector('#crop-list .crop-detail');"
       + " ['must_stand', 'must_plant_annual', 'contract', 'perennial'].forEach(k => addCommitment(k, card))");
  const dataF = new Set([...D.querySelectorAll('[data-f]')].map(e => e.getAttribute('data-f')));
  const cropDeclared = new Set(Object.keys(F.crop));
  ok(`every rendered data-f is registered (missing: ${JSON.stringify(diff(dataF, cropDeclared))})`,
     diff(dataF, cropDeclared).length === 0);
  ok(`every registered data-f is rendered (stale: ${JSON.stringify(diff(cropDeclared, dataF))})`,
     diff(cropDeclared, dataF).length === 0);
  W.eval("renderAllZones([]); renderAllCommitments([])");

  // 3. Every non-UI form field reaches the payload; no UI toggle does; every source exists.
  const feeds = new Set(Object.values(F.payload).flatMap(p => p.from || []));
  const dead = Object.entries(F.form).filter(([id, f]) => !f.ui && !feeds.has(id)).map(([id]) => id);
  ok(`every form field feeds a payload key (dead inputs: ${JSON.stringify(dead)})`, dead.length === 0);
  const uiFed = Object.entries(F.form).filter(([id, f]) => f.ui && feeds.has(id)).map(([id]) => id);
  ok(`no UI toggle feeds the payload (${JSON.stringify(uiFed)})`, uiFed.length === 0);
  const ghosts = [...feeds].filter(id => !id.startsWith('@') && !F.form[id]);
  ok(`every payload source is a registered field (${JSON.stringify(ghosts)})`, ghosts.length === 0);
  for (const [k, p] of Object.entries(F.payload)) {
    ok(`payload "${k}" says where it comes from (from, or an unsent reason)`,
       Array.isArray(p.from) || (typeof p.unsent === 'string' && p.unsent.length > 10));
  }

  // 4. The views the app reads ARE the registry: the same objects, every key, both directions —
  //    a copy would match today and drift tomorrow.
  const U = W.eval('UNITS');
  const sameView = (view, section, part) => {
    const want = Object.keys(F[section]).filter(k => F[section][k][part]);
    return JSON.stringify(Object.keys(view)) === JSON.stringify(want) &&
           want.every(k => view[k] === F[section][k][part]);
  };
  ok('units FIELD_REGISTRY is exactly the registry\'s form units', sameView(U.FIELD_REGISTRY, 'form', 'units'));
  ok('units DATA_F_REGISTRY is exactly the registry\'s crop units', sameView(U.DATA_F_REGISTRY, 'crop', 'units'));
  ok('BENCHMARK_DEFAULTS is exactly the registry\'s benchmarks', sameView(W.eval('BENCHMARK_DEFAULTS'), 'form', 'benchmark'));
  // Each benchmark is a sourced value (was the in-page console check T30, which asserted 13
  // entries against 9 and had been failing silently).
  for (const [id, f] of Object.entries(F.form).filter(([, f]) => f.benchmark)) {
    const b = f.benchmark;
    ok(`benchmark "${id}" carries a value, label, source, 4-digit vintage and confidence`,
       Number.isFinite(b.value) && b.label && b.source && /^\d{4}$/.test(b.vintage) &&
       ['low', 'medium', 'high'].includes(b.confidence));
  }

  // 4b. A benchmark is written twice — fields.js, and the input's value="" in the HTML that a
  //     non-benchmark boot shows. They must agree, or the two boot paths start different farms.
  {
    const html = require('fs').readFileSync(require('path').join(__dirname, '..', 'public', 'index.html'), 'utf8');
    for (const [id, f] of Object.entries(F.form).filter(([, f]) => f.benchmark)) {
      const tag = (html.match(new RegExp(`<input[^>]*id="${id}"[^>]*>`)) || [''])[0];
      const attr = (tag.match(/value="([^"]*)"/) || [])[1];
      ok(`benchmark "${id}" (${f.benchmark.value}) equals the HTML default (${attr})`, Number(attr) === f.benchmark.value);
    }
  }

  // 5. `payload` against the BUILDER, not just the adapter: the main solve sends exactly the keys
  //    declared for it, and nudging each declared source field MOVES its key. Without this the
  //    `from` lists — and the dead-input check above, which is built on them — were trusted as
  //    written; the golden payload is a frozen capture and cannot see a newly added key.
  {
    const cash = D.getElementById('pd-cash');
    const cashWas = cash.checked; cash.checked = true;          // opening_cash/credit_line ride on it
    const main = Object.keys(W.eval('buildSolveParams()')).sort();
    const declaredMain = Object.keys(F.payload).filter(k => !F.payload[k].sentBy && !F.payload[k].unsent).sort();
    ok(`the main solve sends exactly the declared keys (sent-only: ${JSON.stringify(diff(new Set(main), new Set(declaredMain)))}, ` +
       `declared-only: ${JSON.stringify(diff(new Set(declaredMain), new Set(main)))})`,
       JSON.stringify(main) === JSON.stringify(declaredMain));
    const build = sentBy => sentBy === 'what-if'
      ? W.eval('buildLaborFlexParams(buildSolveParams())') : W.eval('buildSolveParams()');
    const inert = [];
    for (const [key, p] of Object.entries(F.payload)) {
      if (p.unsent || p.sentBy === 'monte-carlo') continue;
      for (const id of (p.from || []).filter(x => !x.startsWith('@'))) {
        const el = D.getElementById(id);
        const before = JSON.stringify(build(p.sentBy)[key]);
        const was = el.type === 'checkbox' ? el.checked : el.value;
        if (el.type === 'checkbox') el.checked = !el.checked;
        else if (el.tagName === 'SELECT') el.value = [...el.options].find(o => o.value !== el.value).value;
        // DOWN, not up: the builder clamps (sell-through at 100%, a multiplier at ≥1), and a nudge
        // past a clamp is a nudge that cannot register.
        else el.value = String((parseFloat(el.value) || 0) * 0.61 + 0.37);
        el.dispatchEvent(new W.Event('input', { bubbles: true }));
        if (JSON.stringify(build(p.sentBy)[key]) === before) inert.push(`${id} → ${key}`);
        if (el.type === 'checkbox') el.checked = was; else el.value = was;
        el.dispatchEvent(new W.Event('input', { bubbles: true }));
      }
    }
    ok(`every declared source field moves its payload key (inert: ${JSON.stringify(inert)})`, inert.length === 0);
    cash.checked = cashWas;
  }

  W.close();

  // 6. fields.js is a hard boot dependency — if it never arrives (dropped request, or an expired
  //    session answered with the sign-in HTML), the grower must SEE that, not a blank page with
  //    errors only in the console (/code-review max).
  {
    // The raw page, NOT bootApp's: jsdom has no resource loader, so <script src="fields.js"> never
    // loads — exactly the failure under test. The guard throws during parsing, synchronously
    // inside the constructor, so the alert exists on return and Pyodide is never reached.
    const fs = require('fs'), path = require('path'), { JSDOM, VirtualConsole } = require('jsdom');
    const html = fs.readFileSync(path.join(__dirname, '..', 'public', 'index.html'), 'utf8');
    const bare = new JSDOM(html, { runScripts: 'dangerously', url: 'http://localhost/', virtualConsole: new VirtualConsole() });
    const alert = bare.window.document.querySelector('[role=alert]');
    ok('a missing fields.js shows a visible "could not finish loading" message with a reload link',
       !!alert && /could not finish loading/.test(alert.textContent) && !!alert.querySelector('a'));
    bare.window.close();
  }

  if (failures) { console.error(`field registry (client): ${failures} FAILED`); process.exit(1); }
  console.log(`field registry (client): all checks passed (${declared.size} form + ${cropDeclared.size} crop ` +
              `fields, ${Object.keys(F.payload).length} payload keys, views are the registry)`);
})().catch(e => { console.error(e); process.exit(1); });
