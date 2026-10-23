/* R7 IN THE PAGE: land tenure inputs that tell the grower the truth (Batch 2.2).
 *
 * The solver half of R7 is pinned in tests/test_r7_ownership.py. This is the part only the page
 * can get wrong, found by /code-review:
 *   1. both "your land costs nothing" nudges used to check the MORTGAGE field alone — so a grower
 *      who had correctly entered rented acres was told to type the rent into the mortgage box too,
 *      double-charging the land;
 *   2. "Rented Acres" had no trailing unit parenthetical, so in Metric it showed HECTARES under a
 *      label that said acres (renderUnitLabels only rewrites a trailing bracket), and the "/yr" in
 *      "($/acre/yr)" was erased by that same rewrite;
 *   3. the What-If "+% land" scenario grew total land but not rented land — new acres came free.
 *
 * Run: node tests/land_cost_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const ok = (name, cond) => { if (!cond) { failures++; console.error('  x ' + name); } };

(async () => {
  const dom = await bootApp();
  const W = dom.window, D = W.document;
  const set = (id, v) => W.eval('writeFieldCanonical')(D.getElementById(id), v);
  const entered = () => W.eval('landCostEntered()');

  // 1. Either kind of land cost silences the nudge; neither leaves it on.
  set('rate_property_mortgage_rent', 0); set('rented_acres', 0); set('cash_rent_per_acre_yr', 0);
  ok('no mortgage and no rented land reads as no land cost', entered() === false);
  set('rented_acres', 40); set('cash_rent_per_acre_yr', 300);
  ok('rented acres at a rent count as a land cost (the nudge must not ask for a mortgage too)', entered() === true);
  set('rented_acres', 40); set('cash_rent_per_acre_yr', 0);
  ok('rented acres at $0 rent are still no cost', entered() === false);
  set('rented_acres', 0); set('rate_property_mortgage_rent', 500);
  ok('a mortgage alone counts as a land cost', entered() === true);
  set('rate_property_mortgage_rent', 0);
  ok('the nudge banner no longer tells a renter to use the mortgage box alone',
     /Rented Land and Rent per Rented Acre/.test(D.getElementById('land-rent-nudge').textContent));

  // 2. Labels carry their unit as the trailing bracket, so Metric relabels them — and keeps "per Year".
  const label = id => D.getElementById(id).closest('.form-group').querySelector('label').firstChild.textContent;
  W.eval('setUnitSystem')('metric');
  ok(`rented land is labelled in hectares in Metric (got "${label('rented_acres')}")`, /\(ha\)/.test(label('rented_acres')));
  ok(`cash rent stays per YEAR, per hectare in Metric (got "${label('cash_rent_per_acre_yr')}")`,
     /per Year/.test(label('cash_rent_per_acre_yr')) && /\/ha/.test(label('cash_rent_per_acre_yr')));
  W.eval('setUnitSystem')('us');

  // 3. +20% land grows rented land by the same share.
  const scaled = W.eval('scaleParamsForScenario')({ total_land: 80, rented_acres: 40, crops: [], employees: [] },
                                                   { scaleType: 'land' }, 1.2);
  ok(`the land What-If scales rented acres with total land (got ${scaled.rented_acres})`,
     Math.abs(scaled.rented_acres - 48) < 1e-9 && Math.abs(scaled.total_land - 96) < 1e-9);

  W.close();
  if (failures) { console.error(`land cost (client): ${failures} FAILED`); process.exit(1); }
  console.log('land cost (client): all checks passed (nudge sees rent, Metric labels, land What-If)');
})().catch(e => { console.error(e); process.exit(1); });
