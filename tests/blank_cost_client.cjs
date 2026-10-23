/* A BLANK OR ZERO COST IS THE GROWER'S NUMBER, NOT A HOLE TO FILL (/code-review max #4, #5).
 *
 * #4: "My Farm Data" mode blanks the fertilizer, fuel and machinery boxes by design, and each blank
 *     used to reach the solver as $0 — an "optimal" plan $88k (+14%) richer than the golden farm,
 *     with no warning. validateParams now refuses a blank and names the box; a typed 0 stays legal.
 * #5: runMonteCarlo built every draw with `(params.cost_fert_per_lb || 0.82)`, so a farm whose
 *     fertilizer genuinely costs $0 was charged the benchmark in every draw — the whole distribution
 *     sat $35.7k below the plan it was meant to stress. Driven for real here: the solve is stubbed,
 *     so the test reads the exact payload each draw would have sent.
 *
 * Run: node tests/blank_cost_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };

(async () => {
  const W = await bootApp(), D = W.document;
  // Set a box the way the grower does: the input event is what refreshes the canonical value
  // the payload reads, so a bare .value write would test the OLD number.
  const setBox = (id, v) => {
    const e = D.getElementById(id);
    e.value = v;
    e.dispatchEvent(new W.Event('input', { bubbles: true }));
  };
  const COSTS = { cost_fert_per_lb: 'Fertilizer price', cost_fuel_per_L: 'Fuel price', rate_machinery: 'Machinery cost' };

  // 1. Each blank cost box is refused by name; the defaults are not.
  ok('the shipped form validates clean', W.validateParams(W.eval('buildSolveParams()')).length === 0);
  for (const [id, label] of Object.entries(COSTS)) {
    const was = D.getElementById(id).value;
    setBox(id, '');
    const errs = W.validateParams(W.eval('buildSolveParams()'));
    ok(`a blank ${id} is refused by name (got ${JSON.stringify(errs)})`, errs.some(e => e.startsWith(label)));
    setBox(id, '0');
    ok(`a typed 0 for ${id} is a legal answer`, W.validateParams(W.eval('buildSolveParams()')).length === 0);
    setBox(id, was);
  }

  // 1b. #8's client half: a blank well box is refused while the well is ON, and not while it is OFF
  //     (the solver never reads it then — refusing it made a no-well farm type a dead number).
  {
    const well = D.getElementById('well_enabled'), wasCap = D.getElementById('well_weekly_cap_L').value;
    setBox('well_weekly_cap_L', '');
    const onErrs = W.validateParams(W.eval('buildSolveParams()'));
    ok(`a blank well capacity is refused while the well is on (got ${JSON.stringify(onErrs)})`,
       onErrs.some(e => e.startsWith('Well capacity')));
    well.checked = false;
    setBox('city_water_cost_per_L', '0.003');
    const cw = D.getElementById('city_water_enabled'), wasCw = cw.checked;
    cw.checked = true;   // the farm still needs one water source
    const offErrs = W.validateParams(W.eval('buildSolveParams()'));
    ok(`a blank well capacity is NOT refused with the well off (got ${JSON.stringify(offErrs)})`,
       !offErrs.some(e => e.startsWith('Well capacity')));
    well.checked = true; cw.checked = wasCw; setBox('well_weekly_cap_L', wasCap);
  }

  // 1c. Every water source off is refused at solve time, and the Optimize gate follows the boxes
  //     LIVE. It used to be re-checked only on section navigation: unticking every source left
  //     Optimize enabled (a "grow nothing" plan solved optimal), and re-ticking one left it locked.
  {
    const src = ['well_enabled', 'catchment_enabled', 'city_water_enabled'].map(id => D.getElementById(id));
    const was = src.map(e => e.checked);
    const btn = D.getElementById('btn-optimize-top');
    const toggle = (e, on) => { e.checked = on; e.dispatchEvent(new W.Event('change', { bubbles: true })); };
    const settle = () => new Promise(r => setTimeout(r, W.eval('REVALIDATE_DEBOUNCE_MS') + 20));   // the gate is debounced
    W.eval("SECTION_ORDER.forEach(id => APP_STATE.visitedSections.add(id)); showSection('water')");
    await settle();
    ok('Optimize starts enabled with the shipped water setup', btn && !btn.disabled);
    src.forEach(e => toggle(e, false));
    const errs = W.validateParams(W.eval('buildSolveParams()'));
    ok(`no water source is refused at solve time (got ${JSON.stringify(errs)})`,
       errs.some(e => e.startsWith('No water source')));
    await settle();
    ok('Optimize locks as soon as the last source is unticked', btn.disabled);
    toggle(src[0], true);
    await settle();
    ok('Optimize unlocks as soon as a source is re-ticked, without leaving the section', !btn.disabled);
    src.forEach((e, i) => toggle(e, was[i]));
    // ...but never DURING a solve: the live gate re-enabling the buttons mid-run let a double-click
    // start a second solve (/code-review max #7).
    await settle();
    W.eval('_optimizeInFlight = true; updateOptimizeBtn()');
    ok('the live gate does not re-enable Optimize while a solve is running', btn.disabled);
    W.eval('_optimizeInFlight = false; updateOptimizeBtn()');
  }

  // 2. Monte Carlo draws charge the plan's own fertilizer and fuel prices, even when they are $0.
  setBox('cost_fert_per_lb', '0');
  setBox('cost_fuel_per_L', '0');
  W._lastParams = W.eval('buildSolveParams()');
  ok('the plan really carries $0 fertilizer and fuel', W._lastParams.cost_fert_per_lb === 0 && W._lastParams.cost_fuel_per_L === 0);
  D.getElementById('mc-n-sims').value = '50';
  // paintYield's hidden-tab path needs MessageChannel, which jsdom does not provide; Node's does.
  W.MessageChannel = MessageChannel;
  W.eval(`window.__draws = [];
          solveForNumbers = async q => { __draws.push(q); return { profit: 1, revenue: 1, variable_cost: 0 }; };`);
  await W.eval('runMonteCarlo()');
  const draws = W.__draws;
  const charged = draws.filter(q => q.cost_fert_per_lb !== 0 || q.cost_fuel_per_L !== 0);
  ok(`every Monte Carlo draw charges the plan's $0 prices (ran ${draws.length}, ` +
     `${charged.length} charged e.g. ${JSON.stringify(charged.slice(0, 1).map(q => [q.cost_fert_per_lb, q.cost_fuel_per_L]))})`,
     draws.length > 0 && charged.length === 0);

  W.close();
  if (failures) { console.error(`blank costs (client): ${failures} FAILED`); process.exit(1); }
  console.log('blank costs (client): all checks passed (blank cost boxes refused by name, typed 0 legal, ' +
              'Monte Carlo charges the plan\'s own prices)');
})().catch(e => { console.error(e); process.exit(1); });
