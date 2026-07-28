/**
 * The demo farm is derived, and stays honestly derived.
 *
 * Before SPEC_agronomy Ruling 0, CROP_DEFAULTS was a hand-written second copy of seven crops
 * that had drifted from the template library in 52 fields — including three where the demand
 * cap is a different SHAPE (annual vs weekly), which changes constraint structure, not just a
 * number. Nobody noticed because nothing compared them.
 *
 * Three guards, because the obvious one is a tautology on its own:
 *   1. The derivation reproduces the shipped demo form EXACTLY (the real guard — pins behavior).
 *   2. The override map matches its snapshot (the derivation identity is true by construction,
 *      so without this, drift simply reopens through the sanctioned channel).
 *   3. Every override names a crop in DEMO_CROPS and a key the template actually has, so a
 *      typo cannot sit in the map doing nothing.
 */
const fs = require('fs');
const path = require('path');
const { bootApp } = require('./jsdom_app.cjs');

const ROOT = path.join(__dirname, '..');
let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };

bootApp().then(({ window: w }) => {
  const snapPath = path.join(ROOT, 'tests/golden/demo_form_snapshot.json');
  const ovPath   = path.join(ROOT, 'tests/golden/demo_overrides_snapshot.json');

  // 1 — the derived demo still produces the shipped form
  const expected = JSON.parse(fs.readFileSync(snapPath, 'utf8'));
  const actual = w.eval('serializeCrops()');
  if (JSON.stringify(expected) !== JSON.stringify(actual)) {
    const names = expected.map((c, i) => {
      const d = actual[i] || {};
      const diffs = Object.keys(c).filter(k => JSON.stringify(c[k]) !== JSON.stringify(d[k]));
      return diffs.length ? `${c.name}[${diffs.join(',')}]` : null;
    }).filter(Boolean);
    fail(`demo form changed: ${names.join(' ')} — if intended, re-capture `
       + `tests/golden/demo_form_snapshot.json AND re-pin the golden P&L in the same commit`);
  }

  // 2 — the override map is exactly what was reviewed
  const ovExpected = JSON.parse(fs.readFileSync(ovPath, 'utf8'));
  const ovActual = w.eval('DEMO_OVERRIDES');
  if (JSON.stringify(ovExpected) !== JSON.stringify(ovActual)) {
    const added = Object.keys(ovActual).filter(k => !(k in ovExpected));
    const gone  = Object.keys(ovExpected).filter(k => !(k in ovActual));
    fail(`DEMO_OVERRIDES drifted from its snapshot (added: ${added.join(',') || 'none'}; `
       + `removed: ${gone.join(',') || 'none'}). An override is a documented divergence from the `
       + `canonical template — adding one silently is the drift this guard exists to stop`);
  }

  // 3 — no override is a no-op typo
  const demoCrops = w.eval('DEMO_CROPS');
  const templates = w.eval('CROP_TEMPLATES');
  for (const [crop, fields] of Object.entries(ovActual)) {
    if (!demoCrops.includes(crop)) fail(`override for "${crop}", which is not in DEMO_CROPS`);
    const tpl = templates[crop] || {};
    for (const k of Object.keys(fields)) {
      if (!(k in tpl)) fail(`override ${crop}.${k} names a key the template does not have`);
    }
  }

  if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log(`demo derivation: all checks passed (form identical, ${Object.keys(ovActual).length}`
            + ` overridden crops match snapshot, no orphan keys)`);
  process.exit(0);
}).catch(e => { console.error('FATAL:', e.message); process.exit(1); });
