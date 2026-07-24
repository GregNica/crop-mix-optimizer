/* Node self-test for public/units.js — the unit-conversion core behind the
 * metric/US toggle. The browser (Pyodide/DOM) path can't be driven headlessly,
 * so this pins the pure conversion math + registry that everything else relies on.
 *
 * Run directly (`node tests/units_selftest.cjs`) or via pytest (test_units_js.py).
 * Exits non-zero with a message on the first failure.
 *
 * units.js attaches to `window` when loaded as a browser <script>; package.json is
 * type:module so a plain require() returns {}. We load it in a vm with a window stub
 * (exactly the browser code path) and read window.UNITS.
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const code = fs.readFileSync(path.join(__dirname, '..', 'public', 'units.js'), 'utf8');
const sandbox = { window: {}, console };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const U = sandbox.window.UNITS;

let failures = 0;
function fail(msg) { failures++; console.error('  x ' + msg); }
function approx(a, b, rel) { return Math.abs(a - b) <= (rel || 1e-9) * Math.max(1, Math.abs(b)); }
function eq(name, got, want, rel) { if (!approx(got, want, rel)) fail(`${name}: got ${got}, want ${want}`); }
function assert(name, cond) { if (!cond) fail(name); }

// --- module shape ---
assert('window.UNITS is set', !!U);
if (!U) { console.error('FATAL: window.UNITS not set'); process.exit(1); }

// --- factor correctness (canonical units per 1 display unit) ---
eq('area_land metric ha', U.DIMENSIONS.area_land.metric.perDisplay, 2.47105);
eq('mass metric kg',      U.DIMENSIONS.mass.metric.perDisplay,      2.2046226);
eq('vol_liquid us gal',   U.DIMENSIONS.vol_liquid.us.perDisplay,    3.7854118);
eq('vol_bulk us ft3',     U.DIMENSIONS.vol_bulk.us.perDisplay,      0.02831685, 1e-6);
eq('length us in',        U.DIMENSIONS.length.us.perDisplay,        25.4);
eq('time invariant us',   U.DIMENSIONS.time.us.perDisplay,          1);
eq('time invariant metric', U.DIMENSIONS.time.metric.perDisplay,    1);

// --- known conversions ---
eq('80 acre -> ha',        U.toDisplay(80, { measure: 'area_land' }, 'metric'), 32.3752, 1e-4);
eq('$0.82/lb -> $/kg',     U.toDisplay(0.82, { measure: 'mass', inverse: true }, 'metric'), 1.80779, 1e-4);
eq('2.5M L -> gal',        U.toDisplay(2500000, { measure: 'vol_liquid' }, 'us'), 660430.13, 1e-4);
eq('5000 m3 -> ft3',       U.toDisplay(5000, { measure: 'vol_bulk' }, 'us'), 176573.31, 1e-4);
eq('20000 lb/ac -> kg/ha', U.toDisplay(20000, { num: 'mass', den: 'area_land' }, 'metric'), 22416.99, 1e-4);
eq('3 hr/ac -> hr/ha',     U.toDisplay(3, { num: 'time', den: 'area_land' }, 'metric'), 7.41315, 1e-4);
eq('$5000/acre -> $/ha',   U.toDisplay(5000, { measure: 'area_land', inverse: true }, 'metric'), 12355.25, 1e-4);

// --- 'canonical' pseudo-system is identity ---
eq('canonical identity',   U.toDisplay(123.4, { measure: 'vol_bulk' }, 'canonical'), 123.4);
eq('canonical identity 2', U.toCanonical(123.4, { measure: 'mass', inverse: true }, 'canonical'), 123.4);

// --- round-trips exact, all dimensions, both systems ---
const specs = [
  { measure: 'area_land' }, { measure: 'area_floor' }, { measure: 'mass' },
  { measure: 'vol_liquid' }, { measure: 'vol_bulk' }, { measure: 'length' },
  { measure: 'mass', inverse: true }, { measure: 'area_land', inverse: true },
  { num: 'mass', den: 'area_land' }, { num: 'time', den: 'area_land' },
  { num: 'vol_liquid', den: 'area_land' },
];
['us', 'metric'].forEach(sys => {
  specs.forEach((spec, i) => {
    const canon = 137.5 + i;
    const back = U.toCanonical(U.toDisplay(canon, spec, sys), spec, sys);
    if (!approx(back, canon, 1e-9)) fail(`round-trip ${sys} spec#${i}: ${canon} -> ${back}`);
  });
});

// --- NaN / null safety ---
assert('NaN passthrough', Number.isNaN(U.toDisplay(NaN, { measure: 'mass' }, 'metric')));
assert('null passthrough', U.toDisplay(null, { measure: 'mass' }, 'metric') === null);

// --- unitLabel ---
eq_s('label $/lb metric', U.unitLabel({ measure: 'mass', inverse: true }, 'metric'), '$/kg');
eq_s('label yield metric', U.unitLabel({ num: 'mass', den: 'area_land' }, 'metric'), 'kg/ha');
eq_s('label storage rate us', U.unitLabel({ measure: 'vol_bulk', inverse: true, perWeek: true }, 'us'), '$/ft³/wk');
eq_s('label labor us', U.unitLabel({ num: 'time', den: 'area_land', perWeek: true }, 'us'), 'hr/acre/wk');
eq_s('label labor metric', U.unitLabel({ num: 'time', den: 'area_land', perWeek: true }, 'metric'), 'hr/ha/wk');
function eq_s(name, got, want) { if (got !== want) fail(`${name}: got "${got}", want "${want}"`); }

// --- registry sanity ---
assert('FIELD_REGISTRY has total_land', !!U.FIELD_REGISTRY.total_land);
assert('DATA_F_REGISTRY has yield_per_acre', !!U.DATA_F_REGISTRY.yield_per_acre);
assert('DATA_F_REGISTRY has 12 phase fields',
  ['labor_plant', 'water_grow', 'fert_harv', 'fuel_plant'].every(k => !!U.DATA_F_REGISTRY[k]));
// every registry spec must reference a real dimension
[...Object.values(U.FIELD_REGISTRY), ...Object.values(U.DATA_F_REGISTRY)].forEach(spec => {
  const dims = spec.num && spec.den ? [spec.num, spec.den] : [spec.measure];
  dims.forEach(d => { if (!U.DIMENSIONS[d]) fail(`registry spec references unknown dimension "${d}"`); });
});

if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
console.log(`units.js self-test: all checks passed (${Object.keys(U.FIELD_REGISTRY).length} static + ${Object.keys(U.DATA_F_REGISTRY).length} data-f fields)`);
