/* A SAVED PLAN NEVER LOSES A VALUE SILENTLY (E5).
 *
 * WHAT THIS GUARDS. applyFormState used to `return` on any saved field id the form no longer had,
 * so renaming one input in the markup dropped that value from every plan ever saved, with nothing
 * on screen. Now every value that cannot land is named in the load report the grower sees, renames
 * go through FORM_FIELD_RENAMES, and a plan from a newer app or with no version stamp says so.
 *
 * AND THE OTHER DIRECTION — a value that is never SAVED. serializeCrops names its keys by hand, so a
 * crop-card input added without a matching line there would be dropped at SAVE time, which no load
 * report can see. Checked behaviourally: change every input on a card, re-serialize, and require
 * the saved object to change. (Measured 2026-10-19: all 46 crop-card fields are captured; the
 * season start/end pair only saves as a pair, by design, so it is driven as one.)
 *
 * The round-trip used to live only as window._testFormState, a console self-test nobody ran.
 * jsdom can run it, so it runs here.
 *
 * Run: node tests/form_state_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };

(async () => {
  const dom = await bootApp();
  const W = dom.window, D = W.document;
  const ser = () => W.eval('serializeFormState()');
  const apply = s => W.eval('applyFormState')(s);
  const clone = o => JSON.parse(JSON.stringify(o));
  const base = ser();
  const reset = () => apply(clone(base));

  // 1. The app's own state round-trips exactly and reports nothing.
  {
    const r = apply(clone(base));
    ok(`own state reports nothing lost (got ${JSON.stringify(r)})`, r.dropped.length === 0 && r.notes.length === 0);
    ok('serialize → apply → serialize is idempotent', JSON.stringify(ser()) === JSON.stringify(base));
  }

  // 1b. ...in BOTH unit systems. The drift this harness found (every unit-bearing setting moving
  //     on each save/load — 275 → 275.013 m³) came from unit CONVERSION, so a round-trip run only
  //     in the default system would miss half the class.
  for (const sys of ['metric', 'us']) {
    W.eval('setUnitSystem')(sys);
    // setUnitSystem returns silently when Metric is gated off — which would make this half inert.
    ok(`the form really is in ${sys} units`, W.eval('APP_STATE').unitSystem === sys);
    const a = ser();
    apply(clone(a));
    const b = ser();
    const moved = Object.keys(a.fields).filter(k => JSON.stringify(a.fields[k]) !== JSON.stringify(b.fields[k]));
    ok(`a ${sys} save/load moves no setting (moved: ${JSON.stringify(moved.map(k => `${k} ${a.fields[k]}→${b.fields[k]}`))})`,
       moved.length === 0 && JSON.stringify(a) === JSON.stringify(b));
  }
  reset();

  // 2. An unknown flat id is REPORTED, and the fields around it still land.
  {
    const s = clone(base);
    s.fields.total_land = 123.5;
    s.fields.no_such_field_xyz = 7;
    const r = apply(s);
    ok('an unknown saved field is named in the report',
       r.dropped.some(d => d.includes('no_such_field_xyz')));
    ok('...and a known field beside it is still restored',
       Math.abs(Number(W.eval('readCanonical("total_land")')) - 123.5) < 1e-9);
    reset();
  }

  // 3. A rename migrates; a retirement is silent on purpose. Driven through the real table.
  {
    const R = W.eval('FORM_FIELD_RENAMES');
    R.old_land_id = 'total_land';
    R.retired_id = null;
    const s = clone(base);
    delete s.fields.total_land;
    s.fields.old_land_id = 77;
    s.fields.retired_id = 1;
    const r = apply(s);
    ok('a renamed id lands on its new field',
       Math.abs(Number(W.eval('readCanonical("total_land")')) - 77) < 1e-9);
    ok(`neither a migrated nor a retired id is reported as lost (got ${JSON.stringify(r.dropped)})`,
       !r.dropped.some(d => d.includes('old_land_id') || d.includes('retired_id')));
    delete R.old_land_id; delete R.retired_id;
    reset();
  }

  // 4. Collections: an unknown key on a row, and per-channel data for a channel that is gone.
  {
    const s = clone(base);
    const crop = s.crops[0];
    crop.mystery_crop_key = 5;
    crop.channels_data['Gone Channel'] = { price: 9, pkg: 0, demand_type: 'weekly_flat', demand_value: 1, demand_season: '' };
    s.labor[0].mystery_labor_key = 1;
    const r = apply(s);
    ok('an unknown crop key is reported, named by its crop',
       r.dropped.some(d => d.includes(`Crop "${crop.name}"`) && d.includes('mystery_crop_key')));
    ok('prices for a channel that no longer exists are reported',
       r.dropped.some(d => d.includes('Gone Channel')));
    ok('an unknown labour key is reported', r.dropped.some(d => d.includes('mystery_labor_key')));
    reset();
  }

  // 5. A row that cannot be restored at all is reported once, not as a list of its keys, and an
  //    unnamed row does not shift the blame onto the rows after it.
  {
    const s = clone(base);
    s.channels = [{ ...s.channels[0], name: '' }, ...s.channels];
    const r = apply(s);
    ok(`an unnamed channel row is reported once as a whole row (got ${JSON.stringify(r.dropped)})`,
       r.dropped.filter(d => d.startsWith('Channel')).length === 1 &&
       r.dropped.some(d => d.includes('(the whole row)')));
    // ...and it is the UNNAMED row that is blamed. Matching by position also reports exactly one
    // whole row — the LAST channel, shifted off the end — so a count alone passed (mutation m7).
    ok(`the blame lands on the unnamed row itself (got ${JSON.stringify(r.dropped)})`,
       r.dropped.some(d => d === 'Channel "row 1" (the whole row)'));
    reset();
  }

  // 6. Version stamps: newer and missing both produce a note; the current one does not.
  {
    const newer = clone(base); newer.version = 99;
    ok('a plan from a newer app says so', apply(newer).notes.some(n => n.includes('newer version')));
    const bare = clone(base); delete bare.version;
    ok('an unstamped plan says so', apply(bare).notes.some(n => n.includes('no version stamp')));
    reset();
  }

  // 6b. The chatbot's two write paths go through the same listener and drifted the same way:
  //     both write the EXACT canonical, then fire 'input'. In Metric, the old listener re-read the
  //     rounded hectare display and stored a hair off what the assistant proposed.
  {
    W.eval('setUnitSystem')('metric');
    const land = D.getElementById('total_land');
    W.eval('_chatPending = { fields: { total_land: 81 } }');   // NOT the default (80): a no-op must fail
    const pc = D.createElement('input');
    pc.type = 'checkbox'; pc.className = 'prop-check'; pc.checked = true;
    pc.setAttribute('data-field', 'total_land');
    const prop = D.getElementById('chat-proposal') || D.body.appendChild(Object.assign(D.createElement('div'), { id: 'chat-proposal' }));
    prop.appendChild(pc);
    try { W.eval('applyProposal')(); } catch (e) { /* UI chrome after the write is not under test */ }
    ok(`a chatbot-applied 81 acres stays exactly 81 in Metric (got ${land.dataset.canon})`,
       Number(land.dataset.canon) === 81);
    const crop = base.crops[0].name;
    W.eval('updateCropByName')(crop, { min_acreage_if_planted: 3.7 });
    const el = D.querySelector('#crop-list .crop-detail [data-f="min_acreage_if_planted"]');
    ok(`a chatbot crop update stays exact in Metric (got ${el.dataset.canon})`, Number(el.dataset.canon) === 3.7);
    W.eval('setUnitSystem')('us');
    reset();
  }

  // 9. /code-review fixes, each pinned.
  {
    // 9a. A REAL edit is never ignored. Type 10000.4 into a field that displays integers, then
    //     backspace to 10000: the solver must get 10000 (in canonical), not keep 10000.4. Comparing
    //     against the rounded display (the first version of the drift fix) kept 10000.4.
    const el = D.getElementById('harvest_storage_cap');
    const type = v => { el.value = v; el.dispatchEvent(new W.Event('input', { bubbles: true })); };
    type('10000.4'); type('10000');
    const want = W.eval('toCanonicalActive')(10000, W.eval('specForEl')(el));
    ok(`backspacing a typed value updates what the solver gets (canon ${el.dataset.canon}, want ${want})`,
       Math.abs(Number(el.dataset.canon) - want) < 1e-9);
    reset();

    // 9b. A value the form no longer has is KEPT through the next save, so autosave cannot turn
    //     the report into a loss.
    const s = clone(base); s.fields.no_such_field_xyz = 7;
    apply(s);
    ok('an unrestorable value survives the next save', ser().fields.no_such_field_xyz === 7);
    reset();
    ok('...and loading a clean plan clears it', !('no_such_field_xyz' in ser().fields));

    // 9c. A select option that no longer exists is reported, not silently blanked.
    const selId = W.eval('buildFieldRegistry()').find(f => f.kind === 'select').id;
    const s2 = clone(base); s2.fields[selId] = 'no_such_option';
    ok(`a dead select option is reported (${selId})`,
       apply(s2).dropped.some(d => d.includes(selId) && d.includes('no_such_option')));
    reset();

    // 9d. ...and the same for an option-like value inside a collection.
    const s3 = clone(base); s3.crops[0].planting_type = 'hydroponic_raft';
    ok('a dead crop option is reported', apply(s3).dropped.some(d => d.includes('hydroponic_raft')));
    reset();

    // 9e. A setting the plan PREDATES takes the app default, not the previous plan's value.
    const a = clone(base); a.fields.total_land = 123;
    apply(a);
    const b = clone(base); delete b.fields.total_land;
    const rb = apply(b);
    ok(`a predated setting reverts to the default (got ${W.eval('readCanonical("total_land")')}, default ${base.fields.total_land})`,
       Math.abs(W.eval('readCanonical("total_land")') - base.fields.total_land) < 1e-9);
    ok('...and the grower is told', rb.notes.some(n => n.includes('did not exist when this plan was saved') && n.includes('total_land')));
    reset();

    // 9f. An unnamed saved crop renders as 'Crop' and is restored — not reported as a lost row.
    const s4 = clone(base); delete s4.crops[0].name;
    ok('an unnamed crop is not falsely reported lost',
       !apply(s4).dropped.some(d => d.includes('(the whole row)')));
    reset();

    // 9g. Restoring a local DRAFT is a load, not an edit: it must not mark the plan dirty, or the
    //     autosave fires ~2 s later, wipes the report and saves the reduced plan over the original.
    W.localStorage.setItem('farm_local_draft', JSON.stringify({ savedAt: Date.now(), name: 'Draft', formState: clone(base) }));
    W.eval('_planDirty = false');
    W.eval('offerLocalDraft')();
    const btn = [...D.querySelectorAll('#save-status button')].find(x => x.textContent === 'Restore');
    ok('the draft offer renders a Restore button', !!btn);
    if (btn) btn.click();
    ok('restoring a draft does not mark the plan dirty (no autosave over it)', W.eval('_planDirty') === false);
    W.localStorage.removeItem('farm_local_draft');
    reset();
  }

  // 7. The status line the grower reads.
  {
    const txt = W.eval('loadReportText');
    ok('a clean load reads as the caller\'s OK text', txt({ dropped: [], notes: [] }, 'Saved ✓') === 'Saved ✓');
    const many = txt({ dropped: ['a', 'b', 'c', 'd', 'e'], notes: [] }, 'Saved ✓');
    ok(`a lossy load names the count and the first few (got ${JSON.stringify(many)})`,
       many.includes('5 saved values') && many.includes('a; b; c') && many.includes('2 more'));
  }

  // 8. SAVE-side completeness: every input on a crop card, a labour row and a channel row is
  //    captured by its serializer. Change it, re-serialize, require a difference.
  {
    const probe = (rows, serialize, label) => {
      const lost = [];
      const els = [...rows.querySelectorAll('input, select')].filter(e =>
        e.matches('[data-f], [data-lf]') || e.closest('.channel-row'));
      // Fields that only save as a pair are driven together, from the first of the pair.
      const pairs = { ch_season_start: 'ch_season_end' };
      const second = new Set(Object.values(pairs));
      for (const el of els) {
        const f = el.getAttribute('data-f');
        if (second.has(f)) continue;
        const before = JSON.stringify(serialize());
        const touched = [el];
        if (pairs[f]) touched.push(el.closest('.crop-channel-section').querySelector(`[data-f="${pairs[f]}"]`));
        const olds = touched.map(e => (e.type === 'checkbox' ? e.checked : e.value));
        touched.forEach((e, k) => {
          if (e.tagName === 'SELECT') { const o = [...e.options].find(o => o.value !== e.value); if (o) e.value = o.value; }
          else if (e.type === 'checkbox') e.checked = !e.checked;
          else e.value = e.type === 'number' ? String(7.25 + k) : 'Q7z';
          e.dispatchEvent(new W.Event('input', { bubbles: true }));
        });
        if (JSON.stringify(serialize()) === before) {
          lost.push(f || el.getAttribute('data-lf') || el.className || el.id);
        }
        touched.forEach((e, k) => { if (e.type === 'checkbox') e.checked = olds[k]; else e.value = olds[k]; });
      }
      ok(`every ${label} input is saved (never saved: ${JSON.stringify(lost)}, of ${els.length})`,
         lost.length === 0 && els.length > 0);
    };
    probe(D.querySelector('#crop-list .crop-detail'), () => W.eval('serializeCrops()'), 'crop-card');
    probe(D.querySelector('#labor-list .labor-row'), () => W.eval('serializeLabor()'), 'labour-row');
    probe(D.querySelector('#channel-list'), () => W.eval('getChannelDefs()'), 'channel-row');
    reset();
  }

  W.close();
  if (failures) { console.error(`form state (client): ${failures} FAILED`); process.exit(1); }
  console.log('form state (client): all checks passed (round-trip idempotent, nothing dropped silently, ' +
              'renames migrate, every collection input is saved)');
})().catch(e => { console.error(e); process.exit(1); });
