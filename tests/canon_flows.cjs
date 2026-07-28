/* Flow-level guards for THE data-canon INVARIANT — driven in a real (jsdom) DOM.
 *
 * canon_invariant.cjs pins the write HELPERS. It did not catch the last three violations,
 * because those were in the FLOWS that use them:
 *
 *   - serializeFormState stored display values, so a plan saved in Metric and reloaded in US
 *     silently reinterpreted every number (32.4 ha became 32.4 ACRES). Guaranteed via newPlan().
 *   - applyChannels replaced #channel-list without seeding, and applyCrops calls
 *     getChannelDefs() immediately after, dividing packaging/selling costs by 2.2046.
 *   - the chatbot apply path wrote canonical schema values with .value, so "80 acres" applied
 *     in Metric became 80 ha.
 *
 * Six sites in this class have shipped wrong numbers behind a screen that looked right. A
 * guard over the primitives does not cover the paths, so this file drives the paths.
 *
 * WHY jsdom: these flows work by assigning innerHTML and then querying the elements that
 * produces. A hand-rolled element stub cannot parse markup, so an earlier version of this file
 * could only pattern-match the source — and shipped TWO inert guards before mutation-testing
 * caught them (a line window that ran past the function's end and matched the NEXT function;
 * then, once scoped, a check that matched its own explanatory comment). jsdom parses for real,
 * so the flows are executed rather than described.
 *
 * NOT covered here: anything needing Pyodide/WASM. jsdom is not a browser. A solve-level smoke
 * test is a separate job for a real browser, deliberately not attempted.
 *
 * Run: node tests/canon_flows.cjs   (or via pytest: test_canon_flows.py)
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { bootApp, ROOT } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
// Pure RELATIVE tolerance. The `* Math.max(1, |want|)` form degrades to an ABSOLUTE tolerance
// below 1.0, which made the sub-dollar $/lb assertions — the tightest in the file — the loosest
// in practice (0.005 absolute on 0.09 is 5.5%).
const near = (name, got, want, rel) => {
  if (got == null || Number.isNaN(got)) return fail(`${name}: got ${got}`);
  if (Math.abs(got - want) / Math.max(Math.abs(want), 1e-12) > (rel == null ? 5e-3 : rel))
    fail(`${name}: got ${got}, want ${want}`);
};

(async () => {
  const w = await bootApp();
  const d = w.document;
  if (typeof w.UNITS !== 'object') { console.error('FATAL: units.js did not load in jsdom'); process.exit(1); }

  const integrityClean = (label) => {
    const r = w.canonIntegrityReport();
    if (r.length) fail(`${label}: canonIntegrityReport not empty — ${JSON.stringify(r[0])}`);
  };

  // POSITIVE CONTROL, before anything else. Every check below asserts the report is EMPTY, so a
  // checker that stopped matching fields would return [] and all of them would pass silently —
  // precisely how this file's guards have gone inert twice already. Break a field on purpose and
  // require the report to notice. total_land is a FIELD_REGISTRY static, i.e. the half of
  // forEachUnitField that canon_invariant.cjs structurally cannot reach.
  {
    const el = d.getElementById('total_land');
    w.setUnitSystem('us');
    w.writeFieldCanonical(el, 80);
    el.value = String(parseFloat(el.value) * 52);          // display moves, canon does not
    if (!w.canonIntegrityReport().length)
      fail('canonIntegrityReport did NOT flag a deliberately broken field — every integrity '
         + 'check below is inert and would pass no matter what the flows did');
    w.writeFieldCanonical(el, 80);                          // restore
    integrityClean('positive control teardown');
  }

  // ---- FLOW 1: restoring a saved plan must not re-seed channels from the DISPLAY ---------
  // The bug: applyChannels wrote canonical $/lb markup with no data-canon, under $/kg labels.
  // applyCrops then calls getChannelDefs() immediately, so readCanonicalEl fell back to
  // converting the displayed number and every packaging/selling cost was divided by 2.2046.
  {
    w.setUnitSystem('metric');
    w.applyChannels([
      { name: 'Wholesale',      default_pkg: 0.09, var_sell: 0.08, fixed_sell: 0 },
      { name: 'Farmers Market', default_pkg: 0.18, var_sell: 0.05, fixed_sell: 250 },
    ]);
    const defs = w.getChannelDefs();
    near('restore channels in Metric: default_pkg stays canonical $/lb', defs[0].default_pkg, 0.09, 1e-9);
    near('restore channels in Metric: var_sell stays canonical $/lb',    defs[0].var_sell,    0.08, 1e-9);
    near('restore channels in Metric: second row too',                   defs[1].default_pkg, 0.18, 1e-9);
    if (defs[0].fixed_sell !== 0 || defs[1].fixed_sell !== 250)
      fail('restore channels: fixed_sell ($/wk, no physical unit) must pass through untouched');
    integrityClean('after applyChannels in Metric');
    w.setUnitSystem('us');
  }

  // ---- FLOW 3: save in one unit system, restore in the other ------------------------------
  // A saved plan carries no record of the system it was saved in, so storing the DISPLAY value
  // means the same plan means a different farm depending on what is on screen at restore time.
  // Driven through the real buildFieldRegistry against the real form.
  {
    const CHECK = { total_land: 80, harvest_storage_cap: 5000, well_weekly_cap_L: 2500000 };
    [['metric', 'us'], ['us', 'metric']].forEach(([saveIn, restoreIn]) => {
      w.setUnitSystem(saveIn);
      Object.entries(CHECK).forEach(([id, canon]) => w.writeFieldCanonical(d.getElementById(id), canon));
      const cashBefore = d.getElementById('opening_cash').value;

      const saved = w.serializeFormState();
      // wipe first, so a no-op restore cannot pass by leaving the old values in place
      Object.keys(CHECK).forEach(id => w.clearField(d.getElementById(id)));

      w.setUnitSystem(restoreIn);
      w.applyFormState(saved);

      Object.entries(CHECK).forEach(([id, canon]) =>
        near(`save in ${saveIn} -> restore in ${restoreIn}: ${id}`, w.readCanonical(id), canon));
      if (d.getElementById('opening_cash').value !== cashBefore)
        fail(`save in ${saveIn} -> restore in ${restoreIn}: opening_cash changed `
           + `(${cashBefore} -> ${d.getElementById('opening_cash').value}); currency is never converted`);
      integrityClean(`after save ${saveIn} / restore ${restoreIn}`);
    });
    w.setUnitSystem('us');
  }

  // ---- FLOW 3b: the per-crop cold-storage flag survives save/restore -----------------------
  // It did not, and nothing noticed: renderCrop hard-coded `checked` and serializeCrops had no
  // key, so the field was absent from BOTH sides of the round-trip and the existing check above
  // passed vacuously. A crop parked in the barn silently returned to the cooler on every
  // restore, moving the plan and the P&L with no user action. Untick, round-trip, re-read.
  {
    const boxes = () => Array.from(d.querySelectorAll('[data-f="cold_storage"]'));
    if (!boxes().length) {
      fail('cold-storage round-trip: no crop cards rendered, the check would be vacuous');
    } else {
      boxes()[0].checked = false;
      const saved = w.serializeFormState();
      boxes()[0].checked = true;            // wipe, so a no-op restore cannot pass
      w.applyFormState(saved);
      const after = boxes()[0];
      if (!after) fail('cold-storage round-trip: crop card vanished after restore');
      else if (after.checked !== false)
        fail('cold-storage round-trip: crop unticked before saving came back ticked — it '
           + 'silently moves from the barn to the cooler on every restore');
      // silence on success matches the rest of this harness
    }
  }

  // ---- FLOW 3c: shelf life survives the form and the template loader ----------------------
  // Three clamps stood between the input and the solver; B.3 raised only the innermost, so a
  // grower typing 16 reached the solver as 8 with no error, and Garlic's template value of 8
  // was dropped entirely by loadCropTemplate's field list. Both fixed; both pinned here.
  {
    const spreadEls = () => Array.from(d.querySelectorAll('[data-f="sales_spread_weeks"]'));
    if (!spreadEls().length) fail('shelf-life flow: no crop cards rendered — vacuous');
    else {
      spreadEls()[0].value = '16';
      const read = w.eval('getCropsFromForm()')[0].sales_spread_weeks;
      if (read !== 16)
        fail(`shelf-life flow: typed 16, getCropsFromForm returned ${read} — a clamp is back`);
      w.eval("loadCropTemplate(0, 'Garlic')");
      const afterTpl = spreadEls()[0].value;
      if (String(afterTpl) !== '8')
        fail(`shelf-life flow: Garlic template carries sales_spread_weeks:8 but the loader `
           + `wrote ${JSON.stringify(afterTpl)} — template shelf lives are dead on load`);
      const coldAfter = d.querySelectorAll('[data-f="cold_storage"]')[0];
      if (!coldAfter || coldAfter.checked !== true)
        fail('shelf-life flow: template load must leave an unflagged crop refrigerated');
    }
  }

  // ---- FLOW 4: a chatbot proposal carries CANONICAL schema units --------------------------
  // CHATBOT_FIELDS/CROP_DETAIL_FIELDS declare fixed units (acres, liters/week, lbs/acre), so a
  // value written with .value gets re-canonicalised in whatever system is on screen: "80 acres"
  // applied in Metric became 80 ha = 197.7 acres.
  {
    w.setUnitSystem('metric');
    const cropName = (w.getCropsFromForm()[0] || {}).name;
    if (!cropName) {
      fail('flow 4 setup: no crops in the form to update');
    } else {
      const applied = w.updateCropByName(cropName, { yield_per_acre: 9000 });
      if (!applied) fail(`updateCropByName('${cropName}') reported no change`);
      const after = w.getCropsFromForm().find(c => c.name === cropName) || {};
      near('chatbot yield_per_acre applied in Metric stays canonical lb/acre', after.yield_per_acre, 9000);
      integrityClean('after a chatbot crop update in Metric');
    }
    w.setUnitSystem('us');
  }

  // ---- FLOW 2 (runs LAST — it empties the collections): a restored plan with NO crops ---------------------------------------------
  // Seeding used to happen only as a side effect of looping crop cards, so a plan with zero
  // crops left the channel rows unseeded permanently.
  {
    w.setUnitSystem('metric');
    w.applyCrops([]);                       // no crops at all
    w.applyChannels([{ name: 'Wholesale', default_pkg: 0.09, var_sell: 0.08, fixed_sell: 0 }]);
    if (d.querySelectorAll('#crop-list .crop-detail').length !== 0)
      fail('flow 2 setup: expected zero crop cards');
    const defs = w.getChannelDefs();
    near('zero-crop plan: channel costs still canonical', defs[0].default_pkg, 0.09, 1e-9);
    near('zero-crop plan: var_sell still canonical',      defs[0].var_sell,    0.08, 1e-9);
    integrityClean('after a zero-crop restore in Metric');
    w.setUnitSystem('us');
  }

  // ---- FLOW 5 (structural backstop): applyProposal is not reachable from here -------------
  // It reads a module-scoped `let` and the proposal checkboxes, neither addressable from
  // outside the script. Driving it needs a browser; until then pin that it writes through the
  // helper, which flows 1-4 verify behaviourally for their own paths.
  {
    const html = fs.readFileSync(path.join(ROOT, 'public', 'index.html'), 'utf8');
    const i = html.indexOf('function applyProposal(');
    if (i < 0) fail('applyProposal not found — this guard is pinned to a function that no longer exists');
    else {
      // Brace-match rather than slice a fixed window: 2600 chars ran 706 PAST applyProposal's
      // closing brace into the next functions — one edit from matching a neighbour and going
      // inert, which is the failure already seen twice in this file.
      let k = html.indexOf('{', i), depth = 0, end = k;
      for (; end < html.length; end++) {
        if (html[end] === '{') depth++;
        else if (html[end] === '}' && --depth === 0) break;
      }
      const body = html.slice(k, end).replace(/\/\/.*$/gm, '');   // strip comments: an earlier
      if (!/writeFieldCanonical/.test(body))                        // version matched its own prose
        fail('applyProposal writes form fields without writeFieldCanonical — values arriving in '
           + 'canonical schema units must not be re-canonicalised in the active display system');
    }
  }

  if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log('data-canon flows: all checks passed '
            + '(channel restore, zero-crop restore, save/restore round-trip, chatbot update)');
  // jsdom keeps timers and a live window on the event loop, so node would never exit on its
  // own — the failure path only terminated because process.exit was explicit.
  process.exit(0);
})().catch(e => { console.error('FATAL:', e && (e.stack || e)); process.exit(1); });
