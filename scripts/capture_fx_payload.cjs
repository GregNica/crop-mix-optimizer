/**
 * Capture the FX golden farm FROM THE FORM (Batch FX UI step).
 *
 * tests/helpers.py `fx_farm()` builds the fixed-layer fixture in code because, until the UI step,
 * the form could not express any of it. This script builds the SAME farm as a saved plan (a
 * serializeFormState() object — the zones card, a Tunnel Spinach variant card, an Asparagus
 * perennial card, and the commitments table with the fixture's ids), loads it through
 * applyFormState() like any saved plan, and reads the payload off buildSolveParams(). So what is
 * pinned by tests/test_fx_form.py is what the form can send, and the two builds of one farm —
 * code and form — are compared there, like for like.
 *
 *   node scripts/capture_fx_payload.cjs            # rewrite tests/golden/fx_farm_form_state.json
 *                                                  #   and tests/golden/fx_farm_payload.json
 *   node scripts/capture_fx_payload.cjs --check    # exit 1 if the form now builds a different payload
 *
 * Crop ORDER is the code fixture's (the variant and the perennial appended after the demo crops),
 * not the nested order the "+ Variant" button produces: slot order changes the MILP's path, and
 * the point of the capture is a payload the code pin can be compared with to the cent.
 */
const fs = require('fs');
const path = require('path');
const { bootApp } = require('../tests/jsdom_app.cjs');

const ROOT = path.join(__dirname, '..');
const STATE = path.join(ROOT, 'tests/golden/fx_farm_form_state.json');
const PAYLOAD = path.join(ROOT, 'tests/golden/fx_farm_payload.json');
const CHECK = process.argv.includes('--check');

/** The fixed layer, in FORM shape, laid over the demo farm's saved state. Mirrors
 *  tests/helpers.py (TUNNEL_AND_FIELD, ASPARAGUS, BEARING/ESTABLISHING, FX_COMMITMENTS, fx_farm). */
function fxFormState(demo) {
  const state = JSON.parse(JSON.stringify(demo));
  state.zones = [
    { name: 'High tunnel', acres: 2, covered: true },
    { name: 'Open field', acres: '', covered: false },     // takes the rest of the farm
  ];
  state.crops.forEach(c => { c.zones = c.name === 'Kale' ? null : ['Open field']; });   // null = every zone
  const spinach = state.crops.find(c => c.name === 'Spinach');
  state.crops.push({
    ...JSON.parse(JSON.stringify(spinach)),
    name: 'Tunnel Spinach', sells_as: 'Spinach', zones: ['High tunnel'],
    min_acreage_if_planted: 0.25,
    s1_start: '01-02', s1_end: '06-30', s2_start: '08-01', s2_end: '12-15',
  });
  state.crops.push({
    ...JSON.parse(JSON.stringify(spinach)),    // every field the card has; the perennial ones below matter
    name: 'Asparagus', sells_as: '', perennial: true, zones: ['Open field'],
    growing_from_week: '', growing_to_week: '',
    committed_acres: '', overwinters: false,
    sell_through_pct: '', sales_spread_weeks: '2', cold_storage: true,
    // TOTE_M3 / 0.0012 m³/lb = 56.8 lb per tote; the card takes whole pounds per tote.
    lbs_per_tote: 57,
    seed_transplant_cost_per_acre: 500, crop_protection_cost_per_acre: 150,
    labor_grow: 0.5, labor_harv: 5.5, water_grow: 100000, water_harv: 100000,
    fert_grow: 2.0, fert_harv: 2.0, fuel_grow: 1.0, fuel_harv: 3.0,
    channels_data: {
      'Wholesale':      { price: 1.75, pkg: 0.15, demand_type: 'weekly_flat',    demand_value: 1500, demand_season: '' },
      'Farmers Market': { price: 4.00, pkg: 0.30, demand_type: 'weekly_varying', demand_value: 300,  demand_season: 'W18-W25' },
    },
  });
  state.commitments = [
    { id: 'p1', kind: 'perennial', crop: 'Asparagus', zone: '', acres: 3, planted_year: 2019,
      yield_per_acre: 1750, harvest_from_week: 18, harvest_to_week: 25, extra_cost_per_acre: 0, labor_grow: '', labor_harv: '' },
    { id: 'p2', kind: 'perennial', crop: 'Asparagus', zone: '', acres: 1, planted_year: 2025,
      yield_per_acre: 0, harvest_from_week: '', harvest_to_week: '', extra_cost_per_acre: 800, labor_grow: '', labor_harv: '' },
    { id: 'k1', kind: 'must_stand', crop: 'Kale', acres: 8, from_week: 24, to_week: 30 },
    { id: 'k2', kind: 'must_plant_annual', crop: 'Kale', acres: 45 },
    { id: 'c1', kind: 'contract', crop: 'Kale', channel: 'Wholesale', lb_per_week: 1500, from_week: 20, to_week: 40, mode: 'penalty', penalty_per_lb: 0.5 },
    { id: 'c2', kind: 'contract', crop: 'Spinach', channel: 'Wholesale', lb_per_week: 2000, from_week: 28, to_week: 36, mode: 'penalty', penalty_per_lb: 0.5 },
    { id: 'c3', kind: 'contract', crop: 'Asparagus', channel: 'Wholesale', lb_per_week: 500, from_week: 18, to_week: 25, mode: 'deliver', penalty_per_lb: '' },
  ];
  return state;
}

bootApp().then(w => {
  const state = fxFormState(w.eval('serializeFormState()'));
  const report = w.eval('applyFormState')(state);
  if (report.dropped.length || report.notes.length) {
    console.error('the FX form state did not load clean:', report);
    process.exit(1);
  }
  const payload = w.eval('buildSolveParams()');
  const errors = w.eval('validateParams')(payload);
  if (errors.length) { console.error('the FX form does not pass pre-flight:', errors); process.exit(1); }
  const stateText = JSON.stringify(state, null, 1) + '\n';
  const payloadText = JSON.stringify(payload, null, 1) + '\n';
  const same = fs.existsSync(PAYLOAD) && fs.readFileSync(PAYLOAD, 'utf8') === payloadText
            && fs.existsSync(STATE) && fs.readFileSync(STATE, 'utf8') === stateText;
  if (same) { console.log('FX form payload: already current'); process.exit(0); }
  if (CHECK) {
    console.error('the FX form payload is STALE — the form now builds a different farm from the same saved plan.');
    console.error('Run: node scripts/capture_fx_payload.cjs, and re-pin tests/test_fx_form.py in the same commit.');
    process.exit(1);
  }
  fs.writeFileSync(STATE, stateText);
  fs.writeFileSync(PAYLOAD, payloadText);
  console.log(`FX form payload captured: ${payload.crops.length} crops, ${payload.zones.length} zones, ${payload.commitments.length} commitments`);
  w.close();
}).catch(e => { console.error(e); process.exit(1); });
