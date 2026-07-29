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
      // Expected values are read FROM the template, not hardcoded — the transfer is what is
      // under test, and pinning the data here made this fail the moment Phase B entered real
      // shelf lives (it did, on 2026-07-28).
      const tpl = w.eval('CROP_TEMPLATES');
      w.eval("loadCropTemplate(0, 'Garlic')");
      const wantSpread = String(tpl['Garlic'].sales_spread_weeks);
      const gotSpread = String(spreadEls()[0].value);
      if (gotSpread !== wantSpread)
        fail(`shelf-life flow: Garlic's template carries sales_spread_weeks:${wantSpread} but the `
           + `loader wrote ${JSON.stringify(gotSpread)} — template shelf lives are dead on load`);
      const coldAfter = d.querySelectorAll('[data-f="cold_storage"]')[0];
      const wantCold = tpl['Garlic'].cold_storage !== false;
      if (!coldAfter || coldAfter.checked !== wantCold)
        fail(`shelf-life flow: Garlic's template says cold_storage=${wantCold} but the loader `
           + `left the box ${coldAfter && coldAfter.checked ? 'ticked' : 'unticked'}`);
      // And a crop with NO flag must come back refrigerated — absence means cooler, not barn.
      w.eval("loadCropTemplate(0, 'Spinach')");
      const coldDefault = d.querySelectorAll('[data-f="cold_storage"]')[0];
      if (!coldDefault || coldDefault.checked !== true)
        fail('shelf-life flow: a template with no cold_storage key must load as refrigerated');
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

  // ---- an error raised from the input view must be VISIBLE there ------------------------
  // #error-box is markup inside #hub-view, but every section's Optimize button is in
  // #input-view. validateParams would refuse to solve, showError would write the reason onto
  // the hub screen, and the grower — sitting in the Crops section — saw a button that did
  // nothing. Reported from real use 2026-07-29 against the ambient-storage guard, which was
  // working correctly the whole time. A refusal nobody can read is a refusal that did not happen.
  {
    const doc = w.document;
    const hub = doc.getElementById('hub-view');
    const inp = doc.getElementById('input-view');
    const box = doc.getElementById('error-box');
    if (!hub || !inp || !box) {
      fail('error visibility: #hub-view, #input-view or #error-box is missing');
    } else {
      hub.style.display = 'none';
      inp.style.display = '';
      w.showError(box, 'ambient capacity is 0');
      if (!inp.contains(box))
        fail('error visibility: an error raised while the input view is open landed outside it '
           + '— the message is written to a screen the user is not looking at, which reads as '
           + 'a dead Optimize button');
      if (box.style.display !== 'block')
        fail(`error visibility: box not displayed (display=${box.style.display})`);
      if (!String(box.textContent).includes('ambient capacity is 0'))
        fail('error visibility: message text did not reach the box');
      // And it must go back to the hub when the hub is the visible view.
      inp.style.display = 'none';
      hub.style.display = '';
      w.showError(box, 'back on the hub');
      if (!hub.contains(box))
        fail('error visibility: error raised from the hub view did not land in the hub view');
    }
  }

  // ---- renaming a channel must not wipe every crop's numbers for it ---------------------
  // `prev` inside updateCropChannels is keyed by the channel name as it stands in the DOM
  // BEFORE the re-render, and the lookup uses the name AFTER it. So a rename missed on every
  // crop and silently blanked price, packaging, demand type, volume and season across the whole
  // farm. Nothing warned; the numbers were simply gone.
  {
    // Fresh window: earlier blocks in this file deliberately restore a zero-crop plan, so the
    // shared `w` has no crop cards left by the time we get here.
    const w2 = await bootApp();
    const doc = w2.document;
    const card = doc.getElementById('crop-0');
    const defs = w2.getChannelDefs();
    const readCh = () => {
      const sec = card && card.querySelector('.crop-channel-section');
      if (!sec) return null;
      const g = f => { const el = sec.querySelector(`[data-f="${f}"]`); return el ? el.value : null; };
      return { name: sec.getAttribute('data-ch'), price: g('ch_price'), pkg: g('ch_pkg'),
               dtype: g('ch_demand_type'), dval: g('ch_demand_value') };
    };
    const before = readCh();
    if (!card || !defs || defs.length === 0 || !before || before.price === null) {
      fail('channel rename: could not read a crop channel section to test');
    } else {
      const renamed = defs.map((d, i) => (i === 0 ? { ...d, name: d.name + ' (East)' } : d));
      w2.updateCropChannels(card, renamed, null);
      const after = readCh();
      if (!after) fail('channel rename: the channel section vanished after the rename');
      else {
        if (after.name !== renamed[0].name)
          fail(`channel rename: section still labelled "${after.name}", expected "${renamed[0].name}"`);
        ['price', 'pkg', 'dtype', 'dval'].forEach(k => {
          if (after[k] !== before[k])
            fail(`channel rename: ${k} was "${before[k]}" and came back "${after[k]}" — renaming a `
               + `channel silently wiped this crop's numbers for it`);
        });
      }
      // An INSERT AT THE FRONT must NOT pull the old first channel's numbers into the new one.
      // Appending at the end cannot collide (there is no prior entry at that index), so the
      // front is the position that actually exercises the count guard.
      const inserted = [{ ...defs[0], name: 'Brand New Channel' }, ...defs];
      w2.updateCropChannels(card, inserted, null);
      const firstSec = card.querySelector('.crop-channel-section');
      const firstPrice = firstSec && firstSec.querySelector('[data-f="ch_price"]');
      if (firstSec && firstSec.getAttribute('data-ch') !== 'Brand New Channel')
        fail('channel rename: inserted channel did not land first, test cannot check the guard');
      else if (firstPrice && firstPrice.value !== '' && firstPrice.value === before.price)
        fail('channel rename: a NEW channel inherited an existing channel\'s price by position '
           + '— the positional fallback must only apply when the channel count is unchanged');
    }
  }

  // ---- deleting a crop must leave no card holding a stale index -------------------------
  // renderCrop() bakes the crop index into two inline handlers: the delete button and the
  // template <select>. deleteCrop() renumbered the id and the button but NOT the select, so
  // after any mid-list delete, choosing a template wrote into a DIFFERENT crop's fields.
  {
    const w3 = await bootApp();
    const doc = w3.document;
    const before = doc.querySelectorAll('#crop-list .crop-detail').length;
    if (before < 3) {
      fail(`crop delete: need >=3 crops to test a mid-list delete, found ${before}`);
    } else {
      const namesBefore = [...doc.querySelectorAll('#crop-list .crop-detail')]
        .map(el => el.querySelector('.crop-name-inline')?.value);
      w3.deleteCrop(1);                       // mid-list, not the last card
      const cards = [...doc.querySelectorAll('#crop-list .crop-detail')];
      if (cards.length !== before - 1)
        fail(`crop delete: expected ${before - 1} cards, got ${cards.length}`);
      cards.forEach((el, i) => {
        if (el.id !== 'crop-' + i) fail(`crop delete: card ${i} has id "${el.id}"`);
        const btn = el.querySelector('.delete-crop-btn');
        if (btn && !String(btn.getAttribute('onclick')).includes(`deleteCrop(${i})`))
          fail(`crop delete: card ${i} delete button still calls "${btn.getAttribute('onclick')}"`);
        const sel = el.querySelector('select[onchange*="loadCropTemplate"]');
        if (!sel) {
          fail(`crop delete: card ${i} has no template select — the guard cannot check it`);
        } else if (!String(sel.getAttribute('onchange')).includes(`loadCropTemplate(${i},`)) {
          fail(`crop delete: card ${i} ("${el.querySelector('.crop-name-inline')?.value}") still `
             + `calls ${sel.getAttribute('onchange')} — loading a template would overwrite `
             + `another crop`);
        }
      });
      // The surviving cards must be the right crops, in order.
      const expect = namesBefore.filter((_, i) => i !== 1);
      const got = cards.map(el => el.querySelector('.crop-name-inline')?.value);
      if (JSON.stringify(got) !== JSON.stringify(expect))
        fail(`crop delete: survivors are ${JSON.stringify(got)}, expected ${JSON.stringify(expect)}`);
    }
  }

  // ---- loading a template must CLEAR the previous crop's season 2 --------------------------
  // setMMDD routed the empty case through set(), which deliberately ignores '' because it
  // carries canonical unit values where blank means "leave alone". So a one-season template
  // loaded onto a two-season card inherited the old second window. Under the whole-cycle rule
  // that leftover generated nothing and was invisible; now that windows are PLANTING windows
  // it generates real successions — measured at 23 garlic successions instead of 3, including
  // a mid-July planting harvesting in March.
  {
    const w4 = await bootApp();
    const before = w4.getCropsFromForm();
    const twoSeason = before.findIndex(c => (c.seasons || []).length > 1);
    if (twoSeason < 0) {
      fail('template load: no demo crop has two seasons — the guard cannot be exercised');
    } else {
      w4.loadCropTemplate(twoSeason, 'Garlic');
      const after = w4.getCropsFromForm()[twoSeason];
      if (after.name !== 'Garlic')
        fail(`template load: expected Garlic on card ${twoSeason}, got ${after.name}`);
      if ((after.seasons || []).length !== 1)
        fail(`template load: Garlic is a one-season template but the card kept `
           + `${JSON.stringify(after.seasons)} — the previous crop's window survived and will `
           + `generate successions that template never described`);
      if (after.overwinters !== true)
        fail('template load: Garlic must arrive with overwinters set');
    }
  }

  // ---- the solve progress bar must animate on the compositor, not on timers --------------
  // Pyodide solves on the main thread, so during a solve no setTimeout fires, no rAF fires and
  // no layout runs. The old bar was seven setTimeout stages animating `width` — blocked twice
  // over — and it narrated "may take 30-60 s" for what the browser measured at ~5s. A bar that
  // is frozen for exactly the seconds it exists to cover is worse than none, because it reads
  // as a hung app.
  {
    const w5 = await bootApp();
    const doc = w5.document;
    const fill = doc.getElementById('progress-bar-fill');
    const label = doc.getElementById('progress-label');
    const track = fill && fill.parentElement;
    if (!fill || !label || !track) {
      fail('progress: #progress-bar-fill / #progress-label / track missing');
    } else {
      const timers = w5.startProgress(fill, label);
      if (!track.classList.contains('is-indeterminate'))
        fail('progress: startProgress did not put the track into its indeterminate state, so '
           + 'the bar is driven by something the blocked main thread controls');
      if (!/solving/i.test(label.textContent))
        fail(`progress: label reads "${label.textContent}" — it should say the solve is running`);
      if (/30.60|60 s|minute/i.test(label.textContent))
        fail(`progress: label still quotes the old 60-second staging: "${label.textContent}"`);
      w5.stopProgress(timers, fill, label, true);
      if (track.classList.contains('is-indeterminate'))
        fail('progress: stopProgress left the bar animating after the solve returned');
    }
    // And the CSS must animate a COMPOSITED property. `width` needs layout, which is exactly
    // what is unavailable while Pyodide holds the thread.
    const css = require('fs').readFileSync(
      require('path').join(ROOT, 'public', 'index.html'), 'utf8');
    const kf = css.match(/@keyframes pb-slide\s*{[^}]*}[^}]*}/);
    if (!kf) fail('progress: @keyframes pb-slide not found');
    else if (!/transform:\s*translateX/.test(kf[0]))
      fail(`progress: pb-slide does not animate transform — a non-composited property will be `
         + `frozen for the whole solve: ${kf[0].replace(/\s+/g, ' ')}`);
  }

  // ---- unplanted crops and pre-flight warnings must reach the screen ----------------------
  // The audit called the zero-acre explanation the single highest-value trust feature, because
  // of what it replaces: a crop the grower asked for, missing from the plan, nothing on screen,
  // and four different causes that all looked identical. Computing it in Python is only half
  // the job — S1's warnings and S2's reasons both have to be rendered.
  {
    const w6 = await bootApp();
    const doc = w6.document;
    const host = doc.getElementById('unplanted-crops-banner');
    if (!host) {
      fail('unplanted crops: #unplanted-crops-banner is missing from the page');
    } else {
      // The banner must live in the RESULTS view. It was originally put in #hub-view, which
      // switchToResults hides before rendering — so the whole feature was invisible in the app
      // while this test passed, because calling the render function directly only proves the
      // style property changed, not that anyone can see it. Check the ancestry.
      {
        let anc = host, view = null;
        while (anc && anc.parentElement) {
          anc = anc.parentElement;
          if (anc.id === 'results-view' || anc.id === 'results-main') { view = anc.id; break; }
          if (anc.id === 'hub-view' || anc.id === 'input-view') { view = anc.id; break; }
        }
        if (view !== 'results-view' && view !== 'results-main')
          fail(`unplanted crops: banner lives in ${view || 'no known view'} — the results screen `
             + `hides everything outside #results-view, so it can never be seen`);
      }

      w6.renderUnplantedCrops({ unplanted_crops: [], warnings: [] });
      if (host.style.display !== 'none')
        fail('unplanted crops: banner shown with nothing to say');

      // Structured in, sentence out: the solver sends a reason code and numbers, this layer
      // writes the English. A `detail` string from the solver would put narration in the
      // wrong place and leave a future assistant re-parsing prose.
      w6.renderUnplantedCrops({
        unplanted_crops: [{ crop: 'Garlic', reason: 'no_demand', cycle_weeks: 34,
                            min_acres: 5, excluded_channels: [], tightest: null }],
        warnings: ['Crop Kale season window is unusually short.'],
      });
      if (host.style.display === 'none')
        fail('unplanted crops: a crop was dropped and the banner stayed hidden');
      const txt = host.textContent || '';
      ['Garlic', 'sales capacity', 'Kale'].forEach(frag => {
        if (!txt.includes(frag))
          fail(`unplanted crops: rendered text is missing "${frag}" — got: ${txt.slice(0, 160)}`);
      });

      // User-controlled crop names go through escHtml at the render boundary.
      w6.renderUnplantedCrops({
        unplanted_crops: [{ crop: '<img src=x onerror=alert(1)>', reason: 'outcompeted',
                            cycle_weeks: 6, min_acres: 0, excluded_channels: [],
                            tightest: null }], warnings: [],
      });
      if (host.querySelector('img'))
        fail('unplanted crops: a crop name was injected as live markup rather than escaped');

      // Each reason must read differently. A switch that quietly falls through to the generic
      // case for everything would still pass a test that only checked the banner is visible.
      const seen = new Set();
      ['no_plantable_window', 'all_channels_excluded', 'no_demand', 'outcompeted'].forEach(rc => {
        const txt = w6.unplantedReasonText({
          crop: 'X', reason: rc, cycle_weeks: 6, min_acres: 0,
          excluded_channels: ['Wholesale'], tightest: null,
        });
        if (!txt || txt.length < 30) fail(`unplanted crops: ${rc} produced no usable sentence`);
        if (seen.has(txt)) fail(`unplanted crops: ${rc} reads identically to another reason`);
        seen.add(txt);
      });
      if (!w6.unplantedReasonText({ crop: 'X', reason: 'no_plantable_window', cycle_weeks: 6 })
             .toLowerCase().includes('overwinter'))
        fail('unplanted crops: the calendar reason names the symptom but not the fix');
    }
  }

  // ---- a refused solve must say WHY --------------------------------------------------------
  // run_from_js returns {status:'invalid_input', errors:[...]}. The failure branch rendered
  // `res.error` (singular), which is never set on that path, so every reason was dropped and
  // the grower saw a bare status code — precisely the failure the pre-flight guard exists to
  // remove, reintroduced one layer above it.
  {
    const w7 = await bootApp();
    const doc = w7.document;
    const box = doc.getElementById('error-box');
    if (!box) {
      fail('invalid_input: #error-box missing');
    } else {
      w7.showError(box, 'reset');
      const src = require('fs').readFileSync(
        require('path').join(ROOT, 'public', 'index.html'), 'utf8');
      if (!/res\.status === 'invalid_input'/.test(src))
        fail('invalid_input: the failure branch does not special-case it, so `errors` is dropped');
      if (!/res\.errors/.test(src))
        fail('invalid_input: nothing reads res.errors — the reasons never reach the screen');
    }
  }

  // ---- per-crop fields must survive the form -> payload trip -------------------------------
  // A field can reach the solver without ever being READ from the form, and nothing fails: the
  // solver just sees its default forever. That shipped twice on this branch — `overwinters`
  // missed the CSV contract, and `committed_acres` was unguarded until this test. Set each
  // field on a card, read the crops back, and check the value arrived.
  {
    const w8 = await bootApp();
    const doc = w8.document;
    const card = doc.getElementById('crop-0');
    const cases = [
      { field: 'committed_acres', set: '3.5', key: 'committed_acres', want: 3.5 },
      { field: 'min_acreage_if_planted', set: '2', key: 'min_acreage_if_planted', want: 2 },
    ];
    if (!card) {
      fail('form round-trip: crop-0 missing');
    } else {
      cases.forEach(c => {
        const el = card.querySelector(`[data-f="${c.field}"]`);
        if (!el) return fail(`form round-trip: no input for ${c.field} — the field is not on `
                          + `the form at all, so a grower can never set it`);
        el.value = c.set;
        el.dispatchEvent(new w8.Event('change', { bubbles: true }));
        const got = w8.getCropsFromForm()[0][c.key];
        if (Math.abs((got || 0) - c.want) > 1e-9)
          fail(`form round-trip: ${c.field} set to ${c.set} came back as ${got} — the payload `
             + `builder is not reading it, so the solver sees its default forever`);
      });
    }
  }

  if (failures) { console.error(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log('data-canon flows: all checks passed '
            + '(channel restore, zero-crop restore, save/restore round-trip, chatbot update)');
  // jsdom keeps timers and a live window on the event loop, so node would never exit on its
  // own — the failure path only terminated because process.exit was explicit.
  process.exit(0);
})().catch(e => { console.error('FATAL:', e && (e.stack || e)); process.exit(1); });
