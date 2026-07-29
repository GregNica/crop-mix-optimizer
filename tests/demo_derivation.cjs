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

  // 3b — NO OVERRIDE MAY SHADOW AN AUDITED VALUE, AND NONE MAY BE REDUNDANT.
  //
  // This is the guard that was missing. Check 3 above only asks whether an override KEY exists
  // on the template; it cannot see that the VALUE has stopped agreeing with sourced data. On
  // 2026-07-29 that let DEMO_OVERRIDES keep the demo's pre-audit water and fertiliser and shadow
  // the rebuilt templates for four of seven crops, so an audit that "rebuilt 29 templates" never
  // reached the shipped farm — and the measurements taken off it were reported as fact.
  //
  // Phase C of the crop-data audit burns this map toward empty one adjudication at a time, so
  // every future edit touches exactly this mechanism. Two rules:
  //   • an override identical to its template is ballast — delete it, it hides the real ones;
  //   • an override on a field the audit sources needs a written reason, because it means the
  //     demo deliberately disagrees with a citation.
  const AUDITED = [/^water_/, /^fert_/, /^sales_spread_weeks$/, /^cold_storage$/];
  // crop -> field -> why the demo legitimately differs from the sourced value. Empty on purpose.
  const OVERRIDE_REASONS = {};
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  for (const [crop, fields] of Object.entries(ovActual)) {
    const tpl = templates[crop] || {};
    const leaves = [];
    for (const [k, v] of Object.entries(fields)) {
      if (k === 'channels_data') {
        for (const [ch, cv] of Object.entries(v))
          for (const [ck, cvv] of Object.entries(cv))
            leaves.push([`channels_data.${ch}.${ck}`, cvv, ((tpl.channels_data || {})[ch] || {})[ck]]);
      } else leaves.push([k, v, tpl[k]]);
    }
    for (const [field, ovVal, tplVal] of leaves) {
      if (same(ovVal, tplVal))
        fail(`DEMO_OVERRIDES ${crop}.${field} is identical to the template (${JSON.stringify(ovVal)}) `
           + `— ballast that hides the real divergences; delete it`);
      if (AUDITED.some(re => re.test(field)) && !((OVERRIDE_REASONS[crop] || {})[field]))
        fail(`DEMO_OVERRIDES ${crop}.${field} shadows a SOURCED value `
           + `(template ${JSON.stringify(tplVal)}, override ${JSON.stringify(ovVal)}) with no `
           + `reason. Either delete the override so the demo uses the audited number, or add an `
           + `entry to OVERRIDE_REASONS saying why this farm legitimately differs`);
    }
  }

  // 3c — NO DUPLICATE KEYS IN THE HAND-MAINTAINED LITERALS.
  //
  // This one has to read the SOURCE TEXT, and that is the whole point. In a JS object literal a
  // repeated key silently wins WHOLE — not merged, replaced — so by the time the page has parsed
  // CROP_PROVENANCE the evidence is gone and no amount of inspecting the live object can find it.
  // Every other check in this file reads the parsed object and would have passed forever.
  //
  // It happened: appending each research batch as a new block at the top of CROP_PROVENANCE
  // wrote 44 records of which 29 survived, silently discarding 10 transplant-cost citations and
  // 5 planting-labour ones. The values shipped and the golden re-pinned; only the provenance
  // vanished, which is the half nobody re-reads. The success line even printed "29 provenance
  // records" against 44 written, four times, and nobody noticed — including me.
  {
    const src = fs.readFileSync(path.join(ROOT, 'public/index.html'), 'utf8');
    for (const name of ['CROP_PROVENANCE', 'CROP_TEMPLATES', 'DEMO_OVERRIDES']) {
      const at = src.indexOf(`const ${name} = {`);
      if (at < 0) { fail(`${name} not found in public/index.html`); continue; }
      const body = src.slice(src.indexOf('\n', at) + 1, src.indexOf('\n};', at));
      const keys = [...body.matchAll(/^  "([^"]+)":/gm)].map(m => m[1]);
      const seen = new Set(), dupes = new Set();
      keys.forEach(k => (seen.has(k) ? dupes.add(k) : seen.add(k)));
      if (dupes.size)
        fail(`${name} declares duplicate keys: ${[...dupes].join(', ')}. A repeated key in a JS `
           + `object literal REPLACES the earlier record whole — those citations/values are `
           + `silently gone and nothing that reads the parsed object can tell`);
    }
  }

  // 4 — provenance is CHECKED, not decorative. It duplicates values from CROP_TEMPLATES, and an
  // unchecked parallel map is a citation that can quietly stop describing the number it cites.
  const prov = w.eval('CROP_PROVENANCE');
  for (const [crop, fields] of Object.entries(prov)) {
    const tpl = templates[crop];
    if (!tpl) { fail(`CROP_PROVENANCE cites "${crop}", which is not a template`); continue; }
    for (const [field, rec] of Object.entries(fields)) {
      // cold_storage defaults to true by omission, so compare against that default.
      const actual = field === 'cold_storage' ? (tpl[field] !== false) : tpl[field];
      const cited = field === 'cold_storage' ? (rec.value !== false) : rec.value;
      if (JSON.stringify(actual) !== JSON.stringify(cited))
        fail(`CROP_PROVENANCE ${crop}.${field} cites ${JSON.stringify(rec.value)} but the `
           + `template says ${JSON.stringify(tpl[field])} — the citation no longer describes `
           + `the shipped number`);
      if (!rec.source || !rec.confidence)
        fail(`CROP_PROVENANCE ${crop}.${field} has no source/confidence`);
    }
  }
  // Every non-default shelf life must be able to say where it came from.
  for (const [name, tpl] of Object.entries(templates)) {
    if (!tpl || typeof tpl !== 'object') continue;
    if (tpl.sales_spread_weeks !== undefined && !(prov[name] || {}).sales_spread_weeks)
      fail(`${name} carries sales_spread_weeks:${tpl.sales_spread_weeks} with no provenance`);
    if (tpl.cold_storage === false && !(prov[name] || {}).cold_storage)
      fail(`${name} is flagged ambient with no provenance`);
  }

  if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log(`demo derivation: all checks passed (form identical, ${Object.keys(ovActual).length}`
            + ` overridden crops match snapshot, no orphan keys, `
            + `${Object.keys(prov).length} provenance records agree with their templates, `
            + `no override shadows a sourced value, no duplicate keys in any literal)`);
  process.exit(0);
}).catch(e => { console.error('FATAL:', e.message); process.exit(1); });
