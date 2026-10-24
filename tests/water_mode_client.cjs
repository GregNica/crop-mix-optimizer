/* BATCH W — THE WATER-MODE QUESTION ON THE FORM (BACKLOG BC4, SPEC_batchW).
 *
 * The solver half is pinned in test_water_mode.py. This is the form half: the select reaches the
 * payload, the source ticks stop counting outside Irrigated (so a rain-fed farm is not refused for
 * having no source, and a remembered tick cannot water it), D11's refusal still fires in
 * Irrigated, the mode survives save/load, an old plan loads as Irrigated, and the water card and
 * its "+10% water" lever disappear where there is no limit to relieve.
 *
 * Run: node tests/water_mode_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };

(async () => {
  const W = await bootApp(), D = W.document;
  const el = id => D.getElementById(id);
  const change = (e, v) => {
    if (e.type === 'checkbox') e.checked = v; else e.value = v;
    e.dispatchEvent(new W.Event('change', { bubbles: true }));
  };
  const params = () => W.eval('buildSolveParams()');
  const errs = () => W.validateParams(params());
  const SRC = ['well_enabled', 'catchment_enabled', 'city_water_enabled'];

  // 1. Default: Irrigated, sent, and the shipped farm validates clean.
  ok('the select ships on Irrigated', el('water_mode').value === 'irrigated');
  ok(`the payload says irrigated (got ${params().water_mode})`, params().water_mode === 'irrigated');
  ok('the shipped form validates clean', errs().length === 0);

  // 2. D11 kept: every source unticked in Irrigated is refused — at solve time and in the section.
  const was = SRC.map(id => el(id).checked);
  SRC.forEach(id => change(el(id), false));
  ok(`no source in Irrigated is refused at solve time (got ${JSON.stringify(errs())})`,
     errs().some(e => e.startsWith('No water source')));
  ok('…and by the Water section check', W.validateSection('water').some(e => e.startsWith('No water source')));

  // 3. The other two modes ARE the answer: no source, no refusal.
  for (const mode of ['rainfed', 'unlimited']) {
    change(el('water_mode'), mode);
    ok(`${mode} with no source validates clean (got ${JSON.stringify(errs())})`, errs().length === 0);
    ok(`${mode}: the Water section check is clean`, W.validateSection('water').length === 0);
    ok(`${mode} reaches the payload`, params().water_mode === mode);
  }

  // 4. A remembered tick does not water a non-irrigated plan, and its blank box blocks nothing.
  change(el('water_mode'), 'rainfed');
  SRC.forEach(id => change(el(id), true));
  const wasCap = el('well_weekly_cap_L').value;
  el('well_weekly_cap_L').value = '';
  el('well_weekly_cap_L').dispatchEvent(new W.Event('input', { bubbles: true }));
  const p = params();
  ok(`rain-fed sends every source OFF (got ${SRC.map(k => p[k])})`, SRC.every(k => p[k] === false));
  ok(`rain-fed: a blank well box blocks nothing (got ${JSON.stringify(errs())})`, errs().length === 0);
  ok('the ticks stay on the form, remembered', SRC.every(id => el(id).checked));
  ok('the source controls are locked outside Irrigated', el('well_enabled').disabled && el('well_weekly_cap_L').disabled);
  ok('…but the tank box is not (it is still depreciated)', !el('water_storage_capacity').disabled);
  ok('the mode note says the sources are ignored', /ignored/.test(el('water-mode-note').textContent)
     && !el('water-mode-note').hidden);
  el('well_weekly_cap_L').value = wasCap;
  el('well_weekly_cap_L').dispatchEvent(new W.Event('input', { bubbles: true }));

  // 5. Save/load carries the mode; an old plan (no water_mode) loads as Irrigated, not as
  //    whatever mode the form was left on.
  const saved = W.eval('serializeFormState()');
  ok('the mode is saved', saved.fields.water_mode === 'rainfed');
  change(el('water_mode'), 'irrigated');
  W.eval('applyFormState')(saved);
  ok('…and restored', el('water_mode').value === 'rainfed');
  ok('…with the source rows re-locked', el('well_enabled').disabled);
  const old = JSON.parse(JSON.stringify(saved));
  delete old.fields.water_mode;
  W.eval('applyFormState')(old);
  ok(`an old plan loads as Irrigated (got ${el('water_mode').value})`, el('water_mode').value === 'irrigated');
  ok('…with the source rows unlocked', !el('well_enabled').disabled);

  // 6. No water card / lever where water has no limit.
  const res = { weekly_land_frac: [0.5], weekly_labor_used: [1], weekly_labor_supply: [2],
                weekly_water_used: [9], weekly_water_supply: [10], weekly_harvest_vol: [] };
  const hasWater = r => W.rankBottlenecks(r, params()).some(c => c.type === 'water');
  ok('Irrigated ranks water', hasWater({ ...res, water_mode: 'irrigated' }));
  ok('a result from before Batch W (no water_mode) still ranks water', hasWater(res));
  for (const mode of ['rainfed', 'unlimited']) ok(`${mode} offers no water card`, !hasWater({ ...res, water_mode: mode }));

  SRC.forEach((id, i) => change(el(id), was[i]));
  if (failures) { console.error(`water_mode_client: ${failures} failure(s)`); process.exit(1); }
  console.log('water_mode_client: all checks passed');
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
