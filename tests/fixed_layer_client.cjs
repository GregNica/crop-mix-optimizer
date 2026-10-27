/* THE FIXED LAYER IN THE FORM (Batch FX UI step) — zones, variants, perennials, commitments.
 *
 * Everything the solver learned in FX.1–FX.5 reaches it through this form, and nothing else drives
 * the form: the golden farm has no zones and no commitments, so a payload builder that silently
 * dropped a zone tick, sent a variant's inherited channels, or wrote a blank penalty as $0 would
 * pass every Python guard. This drives the real page in jsdom and reads the PAYLOAD
 * (buildSolveParams), the SAVED PLAN (serializeFormState/applyFormState) and the rendered results
 * card off it. What it pins:
 *
 *   1. the plots card → `zones` (empty list with no rows; "Plant by plots" opens TWO at once and
 *      one plot alone is refused; the blank-acres remainder; covered); Metric typing converts to
 *      canonical acres;
 *   2. the crop card's plot ticks → `zones` on the crop only when it withdraws from a plot; the
 *      grid follows a rename and disappears below two plots; the plot rows mirror the ticks;
 *   3. a variant card sends `sells_as` and NONE of the inherited keys; it follows its parent's
 *      rename; a missing parent is refused by name, not silently made its own crop;
 *   4. a perennial card sends `perennial: true` and NONE of the annual calendar; it is refused
 *      until it has a patch; the growing season goes as a pair or not at all;
 *   5. every commitment kind, added ON ITS CROP CARD (the crop is the card) → its payload shape; a
 *      blank number is LEFT OUT (never 0); a deliver contract carries no penalty; a contract with no
 *      mode is refused; unit-bearing fields convert; the Committed card gathers them in words;
 *   6. zones and commitments round-trip through a saved plan in both unit systems, a row of an
 *      unknown kind is REPORTED, and a plan saved before FX loads clean;
 *   7. the What-If scalers: "+10% land" scales fixed zones, a zone lever scales one zone and the
 *      farm, the demand scalers leave a variant's (absent) channels alone;
 *   8. the Committed results card renders zones, patches, floors and contracts off the result,
 *      says fact vs choice, words every delta status (X15), escapes hostile names, and hides when
 *      the farm has none of it; the P&L puts a contract penalty under its own heading (X12); the
 *      demand label names the variant that sold (FX.5 3/6); the Gantt labels a patch and its zone.
 *
 * Run: node tests/fixed_layer_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp, captureCSV, setValue, setChecked } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const near = (a, b, tol) => Math.abs(a - b) <= (tol == null ? 1e-6 : tol);

(async () => {
  const W = await bootApp();
  const D = W.document;
  const build = () => W.eval('buildSolveParams()');
  const errorsOf = () => W.eval('validateParams')(build());
  const set = (el, v) => setValue(W, el, v);
  const tick = (el, on) => setChecked(W, el, on);
  const cards = () => [...D.querySelectorAll('#crop-list .crop-detail')];
  const cardOf = name => cards().find(c => c.querySelector('.crop-name-inline').value === name);
  const zoneRows = () => [...D.querySelectorAll('#zone-list .zone-row')];
  const cmRows = () => W.commitmentRows().map(r => r.row);      // every card's rows, in insertion order
  const btns = () => D.getElementById('zone-buttons').textContent;
  const f = (root, key) => root.querySelector(`[data-f="${key}"]`);
  const baseState = W.eval('serializeFormState()');
  const reset = () => W.eval('applyFormState')(JSON.parse(JSON.stringify(baseState)));

  // ── 1. The plots card ────────────────────────────────────────────────────────────────────
  {
    ok('no plot rows → zones: [] (one whole-farm zone, the pre-FX farm)', same(build().zones, []));
    ok('the shipped farm sends no commitments', same(build().commitments, []));
    ok('with no plots the card offers "Plant by plots"', /Plant by plots instead of total acreage/.test(btns()) && !/Add plot/.test(btns()));
    W.startPlots();
    ok(`"Plant by plots" opens TWO named plots at once (got ${zoneRows().map(r => f(r, 'zone_name').value).join()})`,
       zoneRows().length === 2 && zoneRows().map(r => f(r, 'zone_name').value).join() === 'Plot 1,Plot 2');
    const xShown = () => zoneRows().map(r => W.getComputedStyle(r.querySelector('.delete-zone-btn')).display !== 'none');
    ok('...with "+ Add plot" and "Back to one field", and no ✕ on the pair', /Add plot/.test(btns()) && /Back to one field/.test(btns())
       && same(xShown(), [false, false]));
    ok('both plots list every crop at once (pre-named, so no typing is needed first)', zoneRows().every(r => !r.querySelector('.zone-crop-ticks').hidden
       && r.querySelectorAll('[data-f="zone_crop"]').length === cards().length));
    ok('every plot row says a blank size is the rest of the farm', zoneRows().every(r => f(r, 'zone_acres').placeholder === 'blank = rest'));
    const [z0, z1] = zoneRows();
    set(f(z0, 'zone_name'), 'High tunnel'); set(f(z0, 'zone_acres'), '2'); tick(f(z0, 'zone_covered'), true);
    set(f(z1, 'zone_name'), 'Open field');
    const z = build().zones;
    ok(`two rows, one blank → [{High tunnel 2 covered}, {Open field, no acres}] (got ${JSON.stringify(z)})`,
       same(z, [{ name: 'High tunnel', acres: 2, covered: true }, { name: 'Open field', covered: false }]));
    ok('pre-flight passes with a remainder plot', !errorsOf().some(e => /[Pp]lot/.test(e)));
    // A blank name, a duplicate name, a non-positive size, a lone plot: the FORM's refusals. Whether
    // the plots add up to the farm is the solver's arithmetic (zones.py), refused in Step 0 and rendered as sent.
    set(f(z1, 'zone_name'), 'High tunnel');
    ok('duplicate plot names are refused', errorsOf().some(e => /Plot names must be unique/.test(e)));
    set(f(z1, 'zone_name'), '');
    ok('a nameless plot is refused', errorsOf().some(e => /Plot 2 needs a name/.test(e)));
    set(f(z1, 'zone_name'), 'Open field');
    set(f(z0, 'zone_acres'), '0');
    ok('a zero-size plot is refused', errorsOf().some(e => /size must be > 0, or blank/.test(e)));
    set(f(z0, 'zone_acres'), '2');
    ok('a lone plot (a saved plan could carry one) is refused by name', (() => { const p = build(); p.zones = [p.zones[0]]; return W.eval('validateParams')(p).some(e => /One plot is the whole farm/.test(e)); })());
    W.addZone();
    ok('"+ Add plot" appends a pre-named third plot, and the ✕ buttons appear', zoneRows().length === 3 && f(zoneRows()[2], 'zone_name').value === 'Plot 3'
       && same(xShown(), [true, true, true]));
    W.deleteZone(2);
    ok('deleting one of three leaves the pair', zoneRows().length === 2 && same(xShown(), [false, false]));
    // Metric: the grower types hectares, the solver gets acres.
    W.eval('setUnitSystem')('metric');
    set(f(z0, 'zone_acres'), '1.21406');                 // 3.0 acres
    ok(`a zone typed in ha reaches the payload in acres (got ${build().zones[0].acres})`, near(build().zones[0].acres, 3.0, 1e-3));
    ok('the plot size label says ha in Metric', /\(ha\)/.test(f(z0, 'zone_acres').closest('.form-group').querySelector('label').textContent));
    ok('...and so do the crop cards\' "+ … acres" buttons', /Grow at least N ha this year/.test(cardOf('Kale').querySelector('.cm-add-row').textContent));
    W.eval('setUnitSystem')('us');
    ok(`...and reads back as 3 acres in US (got ${f(z0, 'zone_acres').value})`, near(parseFloat(f(z0, 'zone_acres').value), 3.0, 1e-3));
    ok('...and the buttons say acres again', /Grow at least N acre this year/.test(cardOf('Kale').querySelector('.cm-add-row').textContent));
    set(f(z0, 'zone_acres'), '2');
  }

  // ── 2. Crop-card plot ticks ──────────────────────────────────────────────────────────────
  {
    const kale = cardOf('Kale');
    const ticks = () => [...kale.querySelectorAll('[data-f="crop_zone"]')];
    ok(`every card shows one tick per zone (Kale: ${ticks().length})`, ticks().length === 2 && cards().every(c => c.querySelectorAll('[data-f="crop_zone"]').length === 2));
    ok('all ticked → no `zones` key on the crop (absent = every zone)', !('zones' in build().crops.find(c => c.name === 'Kale')));
    // The same ticks from the zone's side: each zone row lists the crops it may hold.
    const zoneTick = (zone, crop) => zoneRows().find(r => f(r, 'zone_name').value === zone).querySelector(`[data-f="zone_crop"][data-crop="${crop}"]`);
    ok('each zone row lists every crop, ticked', zoneTick('High tunnel', 'Kale') && zoneTick('High tunnel', 'Kale').checked
       && zoneRows().every(r => r.querySelectorAll('[data-f="zone_crop"]').length === cards().length));
    tick(ticks().find(t => t.dataset.zone === 'High tunnel'), false);
    ok('unticking one zone sends the remaining names', same(build().crops.find(c => c.name === 'Kale').zones, ['Open field']));
    ok('...and the zone side shows it', zoneTick('High tunnel', 'Kale').checked === false && zoneTick('Open field', 'Kale').checked === true);
    tick(zoneTick('High tunnel', 'Kale'), true);
    ok('ticking on the zone side writes the crop card (two-way)', ticks().find(t => t.dataset.zone === 'High tunnel').checked && !('zones' in build().crops.find(c => c.name === 'Kale')));
    tick(zoneTick('High tunnel', 'Kale'), false);
    ok('...and back', same(build().crops.find(c => c.name === 'Kale').zones, ['Open field']));
    // A rename follows positionally (same count), so the untick survives it.
    set(f(zoneRows()[1], 'zone_name'), 'Open field (east)');
    ok('a zone rename keeps each card\'s ticks', same(build().crops.find(c => c.name === 'Kale').zones, ['Open field (east)']));
    set(f(zoneRows()[1], 'zone_name'), 'Open field');
    tick(ticks().find(t => t.dataset.zone === 'Open field'), false);
    ok('no plot ticked is refused by name', errorsOf().some(e => /Kale: no plot is ticked/.test(e)));
    ok('...and sends an empty list, which the solver refuses too (never silently every zone)', same(build().crops.find(c => c.name === 'Kale').zones, []));
    tick(ticks().find(t => t.dataset.zone === 'Open field'), true); tick(ticks().find(t => t.dataset.zone === 'High tunnel'), false);
    // A zone name mid-edit passes through "one zone": the grid hides, nothing is sent, and the
    // untick SURVIVES — a wiped grid came back all-ticked, with Kale quietly back in the tunnel.
    set(f(zoneRows()[1], 'zone_name'), '');
    ok('below two named zones the grid is hidden and no crop sends zones', cards().every(c => c.querySelector('.crop-zones-container').hidden)
       && build().crops.every(c => !('zones' in c)));
    set(f(zoneRows()[1], 'zone_name'), 'Open field');
    ok('...and the untick is still there when the second zone is named again', same(build().crops.find(c => c.name === 'Kale').zones, ['Open field']));
    tick(ticks().find(t => t.dataset.zone === 'High tunnel'), true);
    W.deleteZone(1);
    ok('deleting one of the last two plots removes both (one plot is the farm): the grid hides and no crop sends zones',
       zoneRows().length === 0 && cards().every(c => c.querySelector('.crop-zones-container').hidden) && build().crops.every(c => !('zones' in c))
       && /Plant by plots/.test(btns()));
    // An untick must not outlive "Back to one field": the next pair of plots starts all-ticked.
    W.startPlots(); tick(ticks().find(t => t.dataset.zone === 'Plot 1'), false);
    ok('(setup) Kale withdrawn from Plot 1', same(build().crops.find(c => c.name === 'Kale').zones, ['Plot 2']));
    W.clearZones(); W.startPlots();
    ok('"Back to one field" then "Plant by plots" again: every crop may stand in both new plots', !('zones' in build().crops.find(c => c.name === 'Kale'))
       && ticks().every(t => t.checked));
    set(f(zoneRows()[0], 'zone_name'), 'High tunnel'); set(f(zoneRows()[0], 'zone_acres'), '2'); set(f(zoneRows()[1], 'zone_name'), 'Open field');
  }

  // ── 3. Variants ──────────────────────────────────────────────────────────────────────────
  {
    const n0 = cards().length;
    const spinachIdx = cards().indexOf(cardOf('Spinach'));
    W.addVariant(spinachIdx);
    ok('addVariant adds one card right after its parent', cards().length === n0 + 1 && cards()[spinachIdx + 1].classList.contains('is-variant'));
    const v = cards()[spinachIdx + 1];
    set(v.querySelector('.crop-name-inline'), 'Tunnel Spinach');
    ok('the variant card says what it is sold as', f(v, 'sells_as').value === 'Spinach' && /sold as Spinach/.test(v.querySelector('.crop-kind-badge').textContent));
    ok('a variant card offers no "+ Variant" of its own (no chains)', W.getComputedStyle(v.querySelector('.add-variant-btn')).display === 'none'
       && W.getComputedStyle(cardOf('Spinach').querySelector('.add-variant-btn')).display !== 'none');
    // Every baked index is consistent after the mid-list insert (the stale-index class).
    cards().forEach((el, i) => {
      ok(`card ${i} id`, el.id === 'crop-' + i);
      ok(`card ${i} delete index`, String(el.querySelector('.delete-crop-btn').getAttribute('onclick')).includes(`deleteCrop(${i})`));
      ok(`card ${i} template index`, String(el.querySelector('select[onchange*="loadCropTemplate"]').getAttribute('onchange')).includes(`loadCropTemplate(${i},`));
      ok(`card ${i} variant index`, String(el.querySelector('.add-variant-btn').getAttribute('onclick')).includes(`addVariant(${i})`));
    });
    const p = build();
    const tv = p.crops.find(c => c.name === 'Tunnel Spinach');
    const INHERITED = ['channels', 'crop_diversity_max', 'labor_plant', 'labor_grow', 'labor_harv', 'cold_storage',
                       'crop_size_m3_per_lb', 'sales_spread_weeks'];
    ok('the variant sends sells_as', tv && tv.sells_as === 'Spinach');
    ok(`the variant sends NONE of the inherited keys (sent: ${JSON.stringify(INHERITED.filter(k => tv && k in tv))})`,
       tv && INHERITED.every(k => !(k in tv)));
    ok('the variant keeps its own growing keys', tv && 'seasons' in tv && 'days_to_maturity' in tv && 'yield_per_acre' in tv
       && 'seed_transplant_cost_per_acre' in tv && 'water_grow' in tv && 'committed_acres' in tv);
    ok('the parent still sends everything', (() => { const sp = p.crops.find(c => c.name === 'Spinach'); return INHERITED.every(k => k in sp) && !('sells_as' in sp); })());
    ok('pre-flight does not ask the variant for a price (its parent has them)', !errorsOf().some(e => /Tunnel Spinach.*price/.test(e)));
    ok('the stepper gate agrees', !W.validateSection('crops').some(e => /Tunnel Spinach/.test(e)));
    // Rename the parent: the variant follows (one old name gone, one new name arrived).
    set(cardOf('Spinach').querySelector('.crop-name-inline'), 'Spinach (field)');
    ok(`renaming the parent re-points the variant (sells_as = ${f(v, 'sells_as').value})`, f(v, 'sells_as').value === 'Spinach (field)'
       && build().crops.find(c => c.name === 'Tunnel Spinach').sells_as === 'Spinach (field)');
    set(cardOf('Spinach (field)').querySelector('.crop-name-inline'), 'Spinach');
    // Loading a template renames the parent WITHOUT an input event: the variant must still follow.
    W.loadCropTemplate(spinachIdx, 'Lettuce (Head)');     // a name the farm does not already have
    ok(`a template load renames the parent and the variant follows (sells_as = ${f(v, 'sells_as').value})`, f(v, 'sells_as').value === 'Lettuce (Head)');
    W.loadCropTemplate(spinachIdx, 'Spinach');
    ok('...and back', f(v, 'sells_as').value === 'Spinach');
    // The What-If demand scalers must not write channels onto a variant.
    const scaled = W.scaleParamsForScenario(p, { scaleType: 'demand' }, 1.2);
    ok('+20% demand leaves the variant without channels', !('channels' in scaled.crops.find(c => c.name === 'Tunnel Spinach')));
    const scaled1 = W.scaleParamsForScenario(p, { scaleType: 'demand_single', cropName: 'Spinach', channelName: 'Wholesale' }, 1.2);
    ok('+20% on Spinach/Wholesale scales the parent only', !('channels' in scaled1.crops.find(c => c.name === 'Tunnel Spinach'))
       && scaled1.crops.find(c => c.name === 'Spinach').channels.Wholesale.weekly_demand_lbs
          === p.crops.find(c => c.name === 'Spinach').channels.Wholesale.weekly_demand_lbs * 1.2);
    // A perennial is never offered as a parent, and a saved plan that points a variant at one is refused by name.
    W.addCrop(); const asp = cards()[cards().length - 1]; set(asp.querySelector('.crop-name-inline'), 'Asparagus'); tick(f(asp, 'perennial'), true);
    ok('"Sold as" does not offer a perennial card', ![...f(v, 'sells_as').options].some(o => o.value === 'Asparagus'));
    ok('...and a variant pointed at one is refused by name', (() => { const p = build(); p.crops.find(c => c.name === 'Tunnel Spinach').sells_as = 'Asparagus';
       return W.eval('validateParams')(p).some(e => /sold as "Asparagus", which is perennial/.test(e)); })());
    W.deleteCrop(cards().indexOf(asp));
    // A variant whose parent is deleted is REFUSED by name — never quietly its own crop.
    W.deleteCrop(cards().indexOf(cardOf('Spinach')));
    ok('a variant whose parent is gone keeps pointing at it', build().crops.find(c => c.name === 'Tunnel Spinach').sells_as === 'Spinach');
    ok('...and the solve is refused naming it', errorsOf().some(e => /Tunnel Spinach is sold as "Spinach", which is not one of your crops/.test(e)));
    reset();
    ok('reset restores the demo (no variant, no zones)', cards().length === n0 && zoneRows().length === 0);
  }

  // ── 4. Perennials ────────────────────────────────────────────────────────────────────────
  {
    W.addCrop();
    const card = cards()[cards().length - 1];
    set(card.querySelector('.crop-name-inline'), 'Asparagus');
    set(f(card, 'ch_price'), '1.75');          // the first channel's price box
    tick(f(card, 'perennial'), true);
    ok('ticking Perennial marks the card', card.classList.contains('is-perennial') && /perennial/.test(card.querySelector('.crop-kind-badge').textContent));
    ok('...and opens its first patch row on the card', cmRows().length === 1 && cmRows()[0].closest('.crop-detail') === card && cmRows()[0].dataset.kind === 'perennial');
    tick(f(card, 'perennial'), false); tick(f(card, 'perennial'), true);
    ok('ticking it again does not add a second patch', cmRows().length === 1);
    W.deleteCommitment(cmRows()[0].querySelector('.delete-cm-btn'));
    const asp = () => build().crops.find(c => c.name === 'Asparagus');
    const ANNUAL = ['seasons', 'days_to_maturity', 'planting_weeks', 'harvest_weeks', 'min_acreage_if_planted', 'committed_acres',
                    'overwinters', 'planting_type', 'yield_per_acre', 'labor_plant', 'water_plant', 'fert_plant', 'fuel_plant'];
    ok('the perennial sends perennial: true', asp().perennial === true);
    ok(`...and NONE of the annual calendar (sent: ${JSON.stringify(ANNUAL.filter(k => k in asp()))})`, ANNUAL.every(k => !(k in asp())));
    ok('...but its product keys', ['channels', 'cold_storage', 'crop_size_m3_per_lb', 'labor_grow', 'labor_harv', 'water_grow', 'fert_harv', 'fuel_grow',
                                   'crop_protection_cost_per_acre', 'sales_spread_weeks'].every(k => k in asp()));
    ok('no growing season → neither key (all year)', !('growing_from_week' in asp()) && !('growing_to_week' in asp()));
    ok('a perennial with no patch is refused', errorsOf().some(e => /Asparagus is perennial but has no patch/.test(e)));
    ok('...and pre-flight does not ask it for a season or a yield', !errorsOf().some(e => /Asparagus.*(season|Yield)/.test(e)));
    set(f(card, 'growing_from_week'), '14');
    ok('one end of the growing season alone is refused', errorsOf().some(e => /Asparagus: enter both ends/.test(e)));
    set(f(card, 'growing_to_week'), '40');
    ok('both ends are sent as whole weeks', asp().growing_from_week === 14 && asp().growing_to_week === 40);
    // The "+ Perennial patch" button on the card opens a patch row ON the card: the crop is the card.
    ok('a perennial card offers "+ Perennial patch" and not the annual floors; an annual card the reverse',
       W.getComputedStyle(card.querySelector('.cm-add-row .perennial-only')).display !== 'none'
       && W.getComputedStyle(card.querySelector('.cm-add-row .annual-only')).display === 'none'
       && W.getComputedStyle(cardOf('Kale').querySelector('.cm-add-row .perennial-only')).display === 'none'
       && W.getComputedStyle(cardOf('Kale').querySelector('.cm-add-row .annual-only')).display !== 'none');
    tick(f(card, 'perennial'), false); tick(f(card, 'perennial'), true);     // the box opens the patch
    const row = cmRows()[0];
    ok('the patch row sits on its crop card and is a patch', row.closest('.crop-detail') === card && row.dataset.kind === 'perennial');
    set(f(row, 'cm_acres'), '3'); set(f(row, 'cm_planted_year'), '2019'); set(f(row, 'cm_yield_per_acre'), '1750');
    set(f(row, 'cm_harvest_from_week'), '18'); set(f(row, 'cm_harvest_to_week'), '25');
    ok('with a patch the perennial is no longer refused', !errorsOf().some(e => /no patch/.test(e)));
    const e = build().commitments[0];
    ok(`the patch payload (got ${JSON.stringify(e)})`, same(e, { id: e.id, kind: 'perennial', source: 'user', crop: 'Asparagus', acres: 3, planted_year: 2019,
       yield_per_acre: 1750, harvest_from_week: 18, harvest_to_week: 25, extra_cost_per_acre: 0 }));
    ok('with no plots the patch sends no zone (the solver infers the only one)', !('zone' in e));
    W.startPlots(); set(f(zoneRows()[0], 'zone_name'), 'High tunnel'); set(f(zoneRows()[0], 'zone_acres'), '2'); set(f(zoneRows()[1], 'zone_name'), 'Open field');
    set(f(row, 'cm_zone'), 'High tunnel');
    ok('with two plots the chosen plot is sent', build().commitments[0].zone === 'High tunnel');
    W.clearZones();
    ok('plots removed out from under a patch do not travel from the hidden select', !('zone' in build().commitments[0]) && row.querySelector('.cm-zone').classList.contains('cm-hidden'));
    set(f(row, 'cm_yield_per_acre'), '0');
    ok('yield 0 = establishing: the harvest weeks are hidden and not sent', row.querySelectorAll('.cm-harvest.cm-hidden').length === 2
       && !('harvest_from_week' in build().commitments[0]) && build().commitments[0].yield_per_acre === 0);
    set(f(row, 'cm_yield_per_acre'), '');
    ok('a blank yield is refused, not sent as 0', errorsOf().some(e => /enter this year's yield/.test(e)) && !('yield_per_acre' in build().commitments[0]));
    reset();
  }

  // ── 5. The other commitment kinds ────────────────────────────────────────────────────────
  {
    const kale = cardOf('Kale');
    W.addCommitment('must_stand', kale); W.addCommitment('must_plant_annual', kale); W.addCommitment('contract', kale);
    const [ms, mp, ct] = cmRows();
    ok('three rows with distinct ids, all on the Kale card, no crop select', new Set(cmRows().map(r => r.dataset.cid)).size === 3
       && cmRows().every(r => r.closest('.crop-detail') === kale && !r.querySelector('[data-f="cm_crop"]')));
    set(f(ms, 'cm_acres'), '8'); set(f(ms, 'cm_from_week'), '24'); set(f(ms, 'cm_to_week'), '30');
    set(f(mp, 'cm_acres'), '45');
    set(f(ct, 'cm_channel'), 'Wholesale'); set(f(ct, 'cm_lb_per_week'), '1500');
    set(f(ct, 'cm_from_week'), '20'); set(f(ct, 'cm_to_week'), '40');
    ok('a contract with no mode is refused — there is no default (and no mode key is sent)', errorsOf().some(e => /say what happens if you come up short/.test(e))
       && !('mode' in build().commitments[2]));
    ok('the penalty box is disabled until the mode is penalty', f(ct, 'cm_penalty_per_lb').disabled);
    set(f(ct, 'cm_mode'), 'penalty');
    ok('penalty mode with a blank penalty is refused', errorsOf().some(e => /penalty per lb short must be > 0/.test(e)));
    set(f(ct, 'cm_penalty_per_lb'), '0.5');
    let c = build().commitments;
    ok(`must_stand payload (got ${JSON.stringify(c[0])})`, same({ ...c[0], id: 'x' }, { id: 'x', kind: 'must_stand', source: 'user', crop: 'Kale', acres: 8, from_week: 24, to_week: 30 }));
    ok(`must_plant_annual payload`, same({ ...c[1], id: 'x' }, { id: 'x', kind: 'must_plant_annual', source: 'user', crop: 'Kale', acres: 45 }));
    ok(`penalty contract payload (got ${JSON.stringify(c[2])})`, same({ ...c[2], id: 'x' }, { id: 'x', kind: 'contract', source: 'user', crop: 'Kale', channel: 'Wholesale',
       lb_per_week: 1500, from_week: 20, to_week: 40, mode: 'penalty', penalty_per_lb: 0.5 }));
    ok('the three pass pre-flight', errorsOf().filter(e => /entry/.test(e)).length === 0);
    set(f(ct, 'cm_mode'), 'deliver');
    ok('a deliver contract carries no penalty, even one left in the (disabled) box', !('penalty_per_lb' in build().commitments[2]) && build().commitments[2].mode === 'deliver');
    set(f(ms, 'cm_acres'), '');
    ok('a blank acres is LEFT OUT and refused, never sent as 0', !('acres' in build().commitments[0]) && errorsOf().some(e => /"Keep in the ground" entry .*: acres must be > 0/.test(e)));
    set(f(ms, 'cm_acres'), '8');
    set(f(ms, 'cm_to_week'), '60');
    ok('a week outside 1–52 is refused', errorsOf().some(e => /"Keep in the ground" entry .*: enter both weeks/.test(e)));
    set(f(ms, 'cm_to_week'), '30');
    // The crop IS the card: a rename is followed with nothing to re-point, and a deleted crop takes
    // its commitments with it (nothing is left pointing at a crop that is gone).
    set(kale.querySelector('.crop-name-inline'), 'Curly Kale');
    ok('a commitment follows its card\'s rename', build().commitments[0].crop === 'Curly Kale' && !errorsOf().some(e => /no longer one of your crops/.test(e)));
    set(kale.querySelector('.crop-name-inline'), 'Kale');
    const n0 = cards().length;
    W.addCrop(); set(cards()[n0].querySelector('.crop-name-inline'), 'Okra');
    W.addCommitment('must_plant_annual', cards()[n0]);
    ok('a row added on the new card is Okra\'s', cmRows().length === 4 && build().commitments[3].crop === 'Okra');
    W.deleteCrop(n0);
    ok('deleting a crop takes its commitments with it', cmRows().length === 3 && !build().commitments.some(e => e.crop === 'Okra') && !errorsOf().some(e => /Okra/.test(e)));
    // Units: lb/wk typed as kg/wk, $/lb as $/kg, acres as ha.
    set(f(ct, 'cm_mode'), 'penalty');
    W.eval('setUnitSystem')('metric');
    set(f(ct, 'cm_lb_per_week'), '453.592');     // 1,000 lb
    set(f(ct, 'cm_penalty_per_lb'), '2.2046');    // $1.00/lb
    set(f(ms, 'cm_acres'), '4.04686');            // 10 acres
    c = build().commitments;
    ok(`Metric commitment inputs reach the payload canonical (lb/wk ${c[2].lb_per_week}, $/lb ${c[2].penalty_per_lb}, acres ${c[0].acres})`,
       near(c[2].lb_per_week, 1000, 0.5) && near(c[2].penalty_per_lb, 1.0, 1e-3) && near(c[0].acres, 10, 1e-3));
    ok('Metric labels on the rows', /kg\/wk/.test(f(ct, 'cm_lb_per_week').closest('.form-group').querySelector('label').textContent)
       && /\$\/kg/.test(f(ct, 'cm_penalty_per_lb').closest('.form-group').querySelector('label').textContent));
    W.eval('setUnitSystem')('us');
    ok('back in US the boxes show pounds and acres', near(parseFloat(f(ct, 'cm_lb_per_week').value), 1000, 0.5) && near(parseFloat(f(ms, 'cm_acres').value), 10, 1e-3));
    // The Committed card is a dashboard of every card's rows, in words and display units.
    const dash = () => D.getElementById('committed-summary').textContent.replace(/\s+/g, ' ');
    ok(`the Committed card gathers the rows (got "${dash().slice(0, 200)}")`, /Kale/.test(dash()) && /keep 10\.0 acre in the ground W24–30/.test(dash())
       && /grow at least 45\.0 acre this year/.test(dash()) && /1,000 lb\/wk to Wholesale, W20–40; \$1\/lb if short/.test(dash()) && /edit on card/.test(dash()));
    ok('...in the display units', (() => { W.eval('setUnitSystem')('metric'); const m = /keep 4\.0 ha in the ground/.test(dash()) && /454 kg\/wk/.test(dash()); W.eval('setUnitSystem')('us'); return m; })());
    W.deleteCommitment(mp.querySelector('.delete-cm-btn'));
    ok('deleting a row removes just that row', cmRows().length === 2 && !cmRows().includes(mp) && !/grow at least/.test(dash()));
    // The carry-ins: the demo's garlic is already in the ground.
    ok(`...and lists the demo's 18 ac of garlic`, /Garlic/.test(dash()) && /18(\.0)? acre/.test(dash()) && /overwintered/.test(dash()));
    set(f(cardOf('Garlic'), 'committed_acres'), '0');
    ok('garlic at 0 says none is grown this year', /0 acres are entered/.test(dash()));
    set(f(cardOf('Garlic'), 'committed_acres'), '18');
    reset();
    ok('reset clears every card\'s commitments', cmRows().length === 0);
    ok('...and the dashboard lists only the demo\'s carry-in', !/Grow this year|Keep in the ground|Contract|Perennial planting/.test(dash()) && /Garlic/.test(dash()));
  }

  // ── 6. Saved plans ───────────────────────────────────────────────────────────────────────
  {
    W.startPlots();
    set(f(zoneRows()[0], 'zone_name'), 'High tunnel'); set(f(zoneRows()[0], 'zone_acres'), '2'); tick(f(zoneRows()[0], 'zone_covered'), true);
    set(f(zoneRows()[1], 'zone_name'), 'Open field');
    tick([...cardOf('Kale').querySelectorAll('[data-f="crop_zone"]')][0], false);
    // A contract on Kale, then a floor on SPINACH: the saved order (contract first) must survive the
    // round trip even though Spinach's card comes before Kale's.
    W.addCommitment('contract', cardOf('Kale')); W.addCommitment('must_stand', cardOf('Spinach'));
    const ct = cmRows()[0];
    set(f(ct, 'cm_channel'), 'Wholesale'); set(f(ct, 'cm_lb_per_week'), '1500');
    set(f(ct, 'cm_from_week'), '20'); set(f(ct, 'cm_to_week'), '40'); set(f(ct, 'cm_mode'), 'penalty'); set(f(ct, 'cm_penalty_per_lb'), '0.5');
    const ms = cmRows()[1];
    set(f(ms, 'cm_acres'), '8'); set(f(ms, 'cm_from_week'), '24'); set(f(ms, 'cm_to_week'), '30');
    ok('rows keep their insertion order across cards', build().commitments.map(e => e.crop).join() === 'Kale,Spinach');
    const payloadBefore = build();
    for (const sys of ['us', 'metric']) {
      W.eval('setUnitSystem')(sys);
      const a = W.eval('serializeFormState()');
      ok(`[${sys}] the saved plan carries plots and commitments, each naming its crop`, a.zones.length === 2 && a.commitments.length === 2
         && a.zones[0].acres === 2 && a.commitments[0].lb_per_week === 1500 && a.commitments[0].crop === 'Kale' && a.commitments[1].crop === 'Spinach'
         && a.crops.find(c => c.name === 'Kale').zones.length === 1);
      const r = W.eval('applyFormState')(JSON.parse(JSON.stringify(a)));
      ok(`[${sys}] loading it reports nothing lost (${JSON.stringify(r)})`, r.dropped.length === 0 && r.notes.length === 0);
      const b = W.eval('serializeFormState()');
      ok(`[${sys}] save → load → save is identical`, same(a, b));
      W.eval('setUnitSystem')('us');
      ok(`[${sys}] the payload after the round-trip is the payload before`, same(build(), payloadBefore));
    }
    // A plan saved by a newer app with a kind this one lacks: REPORTED, the rest lands.
    const s = W.eval('serializeFormState()');
    s.commitments.push({ id: 'zz9', kind: 'rotation_rule', crop: 'Kale' }, { id: 'zz8', kind: 'must_stand', crop: 'Okra', acres: 1, from_week: 1, to_week: 2 });
    const r = W.eval('applyFormState')(s);
    ok(`an unknown commitment kind, and a row whose crop is not on the farm, are reported (${JSON.stringify(r.dropped)})`,
       r.dropped.some(d => /Commitment "zz9"/.test(d)) && r.dropped.some(d => /Commitment "zz8"/.test(d)) && cmRows().length === 2);
    // A row saved without an id (a hand-edited plan) is given a fresh `cm<n>`, never "undefined".
    const s2 = W.eval('serializeFormState()');
    s2.commitments.push({ kind: 'must_plant_annual', crop: 'Kale', acres: 2 }, { kind: 'must_plant_annual', crop: 'Kale', acres: 3 });
    W.eval('applyFormState')(s2);
    const ids = build().commitments.map(e => e.id);
    ok(`rows without ids are minted distinct cm<n> ids (got ${JSON.stringify(ids)})`, ids.length === 4 && new Set(ids).size === 4 && ids.every(id => /^(cm\d+)$/.test(id)));
    // A card whose name carries a stray space keeps its commitments across save → load.
    set(cardOf('Kale').querySelector('.crop-name-inline'), 'Kale ');
    const s3 = W.eval('serializeFormState()');
    const r3 = W.eval('applyFormState')(s3);
    ok(`a trailing space in the card name loses nothing on reload (${JSON.stringify(r3.dropped)})`, r3.dropped.length === 0 && build().commitments.filter(e => e.crop === 'Kale').length === 3);
    set(cards().find(c => c.querySelector('.crop-name-inline').value === 'Kale ').querySelector('.crop-name-inline'), 'Kale');   // the saved plan keeps the typed name
    // A plan saved before Batch FX: no zones, no commitments keys at all.
    const old = JSON.parse(JSON.stringify(baseState));
    delete old.zones; delete old.commitments; old.crops.forEach(c => { delete c.zones; delete c.sells_as; delete c.perennial; delete c.growing_from_week; delete c.growing_to_week; });
    const r2 = W.eval('applyFormState')(old);
    ok(`a pre-FX plan loads clean (${JSON.stringify(r2)})`, r2.dropped.length === 0 && r2.notes.length === 0 && zoneRows().length === 0 && cmRows().length === 0
       && same(build().zones, []) && same(build().commitments, []));
    reset();
  }

  // ── 7. What-If scalers over zones ────────────────────────────────────────────────────────
  {
    const p = { ...build(), total_land: 80, zones: [{ name: 'High tunnel', acres: 2, covered: true }, { name: 'Open field', covered: false }] };
    const land = W.scaleParamsForScenario(p, { scaleType: 'land' }, 1.1);
    ok('+10% land with a remainder zone: the remainder takes the new ground, the tunnel is untouched', near(land.total_land, 88) && near(land.zones[0].acres, 2) && !('acres' in land.zones[1]) && land.zones.length === 2);
    const fixedP = { ...p, zones: [{ name: 'High tunnel', acres: 2, covered: true }, { name: 'Open field', acres: 78, covered: false }],
                     crops: [{ name: 'Kale', zones: ['Open field'] }, { name: 'Basil' }] };
    const land2 = W.scaleParamsForScenario(fixedP, { scaleType: 'land' }, 1.1);
    ok('+10% land with every zone fixed: a new open zone of the added acres, open to every crop', near(land2.total_land, 88) && land2.zones.length === 3
       && near(land2.zones[2].acres, 8) && land2.zones[2].covered === false && near(land2.zones[0].acres, 2)
       && same(land2.crops[0].zones, ['Open field', land2.zones[2].name]) && !('zones' in land2.crops[1]));
    const less = W.scaleParamsForScenario(fixedP, { scaleType: 'land' }, 0.5);
    ok('−50% land with every plot fixed: each plot gives up half (the sensitivity sweep walks below the farm)', near(less.total_land, 40) && less.zones.length === 2
       && near(less.zones[0].acres, 1) && near(less.zones[1].acres, 39));
    const tun = W.scaleParamsForScenario(p, { scaleType: 'zone', zoneName: 'High tunnel', zoneAcres: 2 }, 1.5);
    ok('a zone lever grows that zone and the farm by the same acres', near(tun.zones[0].acres, 3) && near(tun.total_land, 81) && !('acres' in tun.zones[1]));
    const field = W.scaleParamsForScenario(p, { scaleType: 'zone', zoneName: 'Open field', zoneAcres: 78 }, 1.1);
    ok('a remainder-zone lever grows the farm only (the remainder takes it)', near(field.total_land, 87.8) && near(field.zones[0].acres, 2));
    const res = { zones: [{ name: 'High tunnel', acres: 2, covered: true, used_acres: Array(52).fill(1.5).map((v, i) => i === 20 ? 2 : v) },
                          { name: 'Open field', acres: 78, covered: false, used_acres: Array(52).fill(30) }],
                  weekly_land_frac: Array(52).fill(0.4), weekly_labor_used: [], weekly_labor_supply: [], demand_saturation: {}, water_mode: 'irrigated' };
    const ranked = W.rankBottlenecks(res, p);
    const tunnel = ranked.find(c => c.type === 'zone' && c.zoneName === 'High tunnel');
    ok('a full tunnel is a ranked constraint of its own', tunnel && near(tunnel.peak, 1) && ranked[0] === tunnel);
    ok('the zone lever is labelled by its size', /3\.0 acre.*High tunnel/.test(tunnel.displayFn(p, 1.5)));
    ok('getBottleneckPeak reads the zone', near(W.getBottleneckPeak(res, p, 'zone', tunnel), 1) && near(W.getBottleneckPeak(res, p, 'zone', ranked.find(c => c.zoneName === 'Open field')), 30 / 78));
    const one = W.rankBottlenecks({ ...res, zones: [res.zones[1]] }, p);
    ok('one zone → no zone levers (Total Land is the whole)', !one.some(c => c.type === 'zone'));
  }

  // ── 8. The Committed results card, the P&L group, the market label, the Gantt ────────────
  {
    const hostile = 'Tom\'s <b>Beets</b> & "Co"';
    const res = {
      zones: [{ name: 'High tunnel', acres: 2, covered: true, used_acres: Array(52).fill(2) }, { name: hostile, acres: 78, covered: false, used_acres: Array(52).fill(40) }],
      perennial_blocks: [{ id: 'p1', source: 'user', crop: 'Asparagus', zone: hostile, name: 'Asparagus · planted 2019', acres: 3, planted_year: 2019, stage: 'bearing',
                           yield_per_acre: 1750, harvest_weeks: [18, 19, 20, 21, 22, 23, 24, 25], cost: 3888, sellable_lbs: 5250, labor_hours: 198 },
                         { id: 'p2', source: 'user', crop: 'Asparagus', zone: hostile, name: 'x', acres: 1, planted_year: 2025, stage: 'establishing', yield_per_acre: 0, harvest_weeks: [], cost: 2000, sellable_lbs: 0, labor_hours: 26 }],
      contracts: [{ id: 'c1', source: 'user', crop: 'Kale', channel: 'Wholesale', mode: 'penalty', lb_per_week: 1500, weeks: [20, 21, 22, 36, 37], penalty_per_lb: 0.5,
                    owed_lbs: 7500, delivered_lbs: 4500, short_lbs: 3000, penalty_cost: 1500, short_kind: 'mixed',
                    by_week: [{ week: 20, owed: 1500, delivered: 1500, short: 0, kind: null }, { week: 21, owed: 1500, delivered: 1500, short: 0, kind: null }, { week: 22, owed: 1500, delivered: 1500, short: 0, kind: null },
                              { week: 36, owed: 1500, delivered: 0, short: 1500, kind: 'fact' }, { week: 37, owed: 1500, delivered: 0, short: 1500, kind: 'choice' }] },
                  { id: 'c3', source: 'user', crop: hostile, channel: 'Wholesale', mode: 'deliver', lb_per_week: 500, weeks: [18, 19], penalty_per_lb: 0,
                    owed_lbs: 1000, delivered_lbs: 1000, short_lbs: 0, penalty_cost: 0, short_kind: null, by_week: [] }],
      commitment_deltas: [{ id: 'p1', label: 'x', delta: -1200, tolerance: 300, status: 'optimal' }, { id: 'p2', label: 'x', delta: null, tolerance: null, status: 'infeasible' },
                          { id: 'k1', label: 'x', delta: 30, tolerance: 300, status: 'optimal' }, { id: 'c1', label: 'x', delta: 6500, tolerance: 300, status: 'optimal' },
                          { id: 'c3', label: 'x', delta: null, tolerance: null, status: 'time_limit' }, { id: 'carry-in:Garlic', label: 'x', delta: null, tolerance: null, status: 'error' }],
      succession_schedule: [{ name: 'Kale W10', crop: 'Kale', zone: 'High tunnel', start_week: 10, commitment_id: null, acres: 1.5, weeks: [10, 11, 12], phases: [0, 1, 2] },
                            { name: 'Asparagus · planted 2019', crop: 'Asparagus', zone: hostile, start_week: 1, commitment_id: 'p1', acres: 3, weeks: [1, 2, 3], phases: [1, 1, 2] }],
      crop_names: ['Kale', 'Asparagus'], weekly_land_frac: Array(52).fill(0.5),
    };
    const params = { total_land: 80, crops: [{ name: 'Garlic', committed_acres: 18, overwinters: true }, { name: 'Kale' }, { name: 'Asparagus', perennial: true }],
                     commitments: [{ id: 'k1', kind: 'must_stand', crop: 'Kale', acres: 8, from_week: 24, to_week: 30 }, { id: 'c1', kind: 'contract', crop: 'Kale' }] };
    W.renderCommitmentsCard(res, params);
    const card = D.getElementById('commitments-card');
    const text = card.textContent;
    ok('the card shows', card.style.display !== 'none');
    ok('zones table: the full tunnel is full every week', /High tunnel.*52 — W1–52/.test(text.replace(/\s+/g, ' ')));
    ok('carry-in listed with its acres', /Garlic/.test(text) && /18\.0 acre/.test(text));
    ok('patches: bearing with its weeks, establishing without', /bearing — W18–25/.test(text) && /establishing \(no harvest\)/.test(text));
    ok('floor listed as held', /Kale: at least 8\.0 acre in the ground W24–30/.test(text));
    ok('contract shortfall says fact vs choice by week', /W36: no plan can deliver/.test(text) && /W37: a choice/.test(text));
    ok('a filled contract says so', /filled every week/.test(text));
    ok('delta: earns / costs / within noise / X15 infeasible wording / time budget / error', /earns \$1,200\/yr/.test(text) && /costs \$6,500\/yr/.test(text)
       && /no measurable cost/.test(text) && /cannot be removed on its own — without it the plan has no solution/.test(text)
       && /pricing time budget ran out/.test(text) && /solver error/.test(text));
    ok('the pricing button reads re-price once deltas exist', /Re-price/.test(D.getElementById('btn-price-commitments').textContent));
    ok('hostile names are escaped everywhere on the card', !card.innerHTML.includes('<b>Beets</b>') && card.textContent.includes(hostile));
    W.renderCommitmentsCard({ zones: [{ name: 'Whole farm', acres: 80, used_acres: [] }], perennial_blocks: [], contracts: [] }, { crops: [{ name: 'Kale' }], commitments: [] });
    ok('a farm with none of it hides the card', card.style.display === 'none');

    // X12 — the penalty under its own P&L heading, inside the same total.
    const RES = { revenue: 100000, variable_cost: 21000, fixed_cost: 22400, overhead_cost: 5000, interest_cost: 400, fixed_selling_cost: 0, fixed_selling_split: {},
                  peak_borrowing: 0, overhead_covers: ['admin'], variable_cost_split: { seed: 21000 }, fixed_cost_split: { wages: 22400 },
                  bought_capacity_split: { city_water: 300, overtime: 700, hire: 0, contract_shortfall: 1500 },
                  operating_profit: 100000 - 21000 - 22400 - 2500, profit: 100000 - 21000 - 22400 - 2500 - 5400,
                  channel_sales: { Wholesale: { lbs_sold: 1, revenue: 100000, by_crop: {} } } };
    W._lastRes = RES; W._lastParams = { channels: [{ name: 'Wholesale', fixed_selling_cost_per_wk: 0 }], opening_cash: 0, credit_line: 0 };
    const rows = captureCSV(W, () => W.exportPLCSV()) || [];
    const label = r => String(r[0]).replace(/ /g, ' ').trim();
    const amt = name => { const r = rows.find(r => label(r) === name); return r ? Number(r[1]) : NaN; };
    ok('the penalty renders under "Contract Settlements", not Bought Capacity', rows.some(r => /^Contract Settlements/.test(label(r)))
       && near(amt('Contract Shortfall Penalties (lb short × $/lb, settled after the season)'), -1500)
       && near(amt('Total Contract Settlements'), -1500) && near(amt('Total Bought Capacity'), -1000));
    ok('Total Operating Expenses includes both groups and the tripwire is silent', near(amt('Total Operating Expenses'), -(22400 + 2500)) && !rows.some(r => /UNRECONCILED/.test(label(r))));
    W._lastRes = { ...RES, bought_capacity_split: { city_water: 300, overtime: 700, hire: 0, contract_shortfall: 0 }, operating_profit: RES.operating_profit + 1500, profit: RES.profit + 1500 };
    const rows0 = captureCSV(W, () => W.exportPLCSV()) || [];
    ok('no penalty → no Contract Settlements group at all', !rows0.some(r => /Contract Settlements/.test(label(r))));

    // FX.5 (3)/(6) — the demand label names who sold.
    ok('marketLabel', W.marketLabel('Spinach', ['Spinach']) === 'Spinach' && W.marketLabel('Spinach', undefined) === 'Spinach'
       && W.marketLabel('Spinach', ['Tunnel Spinach']) === 'Spinach market (Tunnel Spinach)'
       && W.marketLabel('Spinach', ['Spinach', 'Tunnel Spinach']) === 'Spinach market (Spinach + Tunnel Spinach)');
    const satRes = { zones: [], weekly_land_frac: Array(52).fill(0.3), water_mode: 'irrigated',
                     demand_saturation: { 'Farmers Market': { Spinach: { basis: 'weekly', cap_lbs: 1000, sold_lbs: 1000, fill: 1, peak_week_frac: 1, weeks_at_cap: [20], peak_week_cap_lbs: 100, binding: 1, sold_by: ['Tunnel Spinach'] } } } };
    const dem = W.rankBottlenecks(satRes, { total_land: 80 }).find(c => c.type === 'demand_single');
    ok('the What-If pill names the variant that sold', dem && dem.name === 'Spinach market (Tunnel Spinach) / Farmers Market' && dem.cropName === 'Spinach');
    W._lastRes = satRes; W._lastParams = { total_land: 80, harvest_storage_cap: 0, channels: [] };
    const crows = captureCSV(W, () => W.exportConstraintCSV()) || [];
    ok('...and so does the constraint CSV', crows.some(r => String(r[0]) === 'Spinach market (Tunnel Spinach) / Farmers Market'));

    // Gantt: a patch is labelled by its id and zone; CSV agrees.
    W.renderGanttCalendar(res);
    const gantt = D.getElementById('gantt-outer').textContent;
    ok('the Gantt labels the patch and its zone', /Patch p1 ·/.test(gantt.replace(/ /g, ' ')) && /Wk 10 · High tunnel/.test(gantt.replace(/ /g, ' ')));
    W._ganttRes = res; W._lastParams = { total_land: 80 };
    const grows = captureCSV(W, () => W.exportGanttCSV()) || [];
    ok('the Gantt CSV carries the same label, unescaped', grows.some(r => r[0] === `Patch p1 · ${hostile}`) && grows.some(r => r[0] === 'Wk 10 · High tunnel'));
  }

  W.close();
  if (failures) { console.error(`fixed layer (client): ${failures} FAILED`); process.exit(1); }
  console.log('fixed layer (client): all checks passed (plots card, crop plot ticks, variant + perennial cards, '
            + 'commitments on the crop cards + the Committed dashboard, saved plans in both unit systems, What-If zone levers, Committed results card, X12 P&L group, market label, Gantt labels)');
})().catch(e => { console.error(e); process.exit(1); });
