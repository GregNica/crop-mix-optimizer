/**
 * The labor roster's money inputs stay on screen and blank never silently means $0.
 *
 * Two defects from the 2026-07-31 review, both of the silent-money class:
 *
 *   1. Count had class `seasonal-only`, so for Salary/Hourly rows it was display:none while
 *      getLaborFromForm still read it and W12 billed it — the default farm carried $67,600/yr
 *      of payroll on a field the grower could not see or edit, and switching a 12-person
 *      seasonal row to hourly kept its stale count billing invisibly.
 *
 *   2. A blank wage box was coerced to $0 by getLaborFromForm with no validator objecting —
 *      clearing one wage erased that role's entire payroll from the committed bill while its
 *      capacity kept counting. "My Farm Data" mode blanks every wage BY DESIGN, so this is a
 *      normal app state. Typed 0 stays legal (unpaid family is a real crew).
 */
'use strict';
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };

bootApp().then(({ window: w }) => {
  const doc = w.document;

  // 1 — Count is visible for EVERY row type. The default roster has salary, hourly and
  // seasonal rows, so if any type hides it this fails without needing computed style:
  // visibility is class-driven (`.seasonal-only { display:none }` outside seasonal rows).
  const rows = [...doc.querySelectorAll('#labor-list .labor-row')];
  if (rows.length < 3) fail(`expected the default roster's rows, got ${rows.length}`);
  rows.forEach(row => {
    const type = row.querySelector('[data-lf="type"]')?.value;
    const countDiv = row.querySelector('[data-lf="count"]')?.closest('div');
    if (!countDiv) { fail(`row (${type}) has no Count input at all`); return; }
    if (countDiv.classList.contains('seasonal-only')) {
      fail(`Count is hidden for a ${type} row but still multiplies the committed wage bill — `
         + `a money input must be on screen`);
    }
  });

  // 2 — one blank round, one typed-0 round, one restore. While the box is BLANK:
  // validateParams must refuse it naming the position, and the serializer must still read 0
  // (the validator is the guard; getLaborFromForm stays total so imports/saved plans work).
  const firstWage = doc.querySelector('#labor-list .labor-row [data-lf="wage"]');
  const firstPos  = doc.querySelector('#labor-list .labor-row [data-lf="position"]').value;
  const saved = firstWage.value;
  const validateWith = () => w.validateParams({ total_land: 80,
    employees: w.eval('getLaborFromForm()'), channels: [{ name: 'X' }], crops: [] });
  firstWage.value = '';
  const errs = validateWith();
  if (!errs.some(e => e.includes(firstPos) && /wage/i.test(e))) {
    fail(`blanking "${firstPos}"'s wage produced no validation error — the role would be `
       + `silently paid $0 (got: ${JSON.stringify(errs)})`);
  }
  const emp = w.eval('getLaborFromForm()')[0];
  if (emp.wage !== 0) fail(`getLaborFromForm turned a blank wage into ${emp.wage}, expected 0`);

  // ...while a typed 0 is a decision, not an omission, and passes the wage check.
  firstWage.value = '0';
  const errs0 = validateWith();
  if (errs0.some(e => e.includes(firstPos) && /wage/i.test(e))) {
    fail(`a typed $0 wage for "${firstPos}" was refused — 0 is a legal wage (unpaid family); `
       + `only BLANK must be refused`);
  }
  firstWage.value = saved;

  // 4 — the What-If labor lever must CHANGE the payload for small crews. Math.round made
  // +10/+20/+40% all no-ops on count-1 rows (and +10/+20 on count-2), so a 3-person farm
  // clicked "+20% Labor", solved an identical payload, and read "+$0.00 — labor isn't your
  // bottleneck". Scaling is fractional now, and salary rows stay untouched.
  const scaled = w.eval(`scaleParamsForScenario(
    { employees: [ { type:'hourly', count:1 }, { type:'seasonal', count:2 },
                   { type:'salary', count:1 } ], crops: [], channels: [] },
    { scaleType: 'labor' }, 1.2)`);
  const [h, s, sal] = scaled.employees;
  if (!(h.count > 1.19 && h.count < 1.21)) {
    fail(`+20% on a count-1 hourly row gave count=${h.count} — the small-crew no-op is back`);
  }
  if (!(s.count > 2.39 && s.count < 2.41)) {
    fail(`+20% on a count-2 seasonal row gave count=${s.count}, expected 2.4`);
  }
  if (sal.count !== 1) fail(`+20% labor scaled a SALARY row to count=${sal.count}`);

  // 5 — copy the code has outgrown must stay dead. Each phrase below described a mechanism
  // the solver no longer has (W15 removed the hire-then-overtime fill order; W12 made every
  // worker committed and capacity-counted), survived one fix pass in three tooltips, and
  // primes the grower to misread a correct result. Scan the whole document INCLUDING
  // data-tip attributes, minus the embedded Python. The first version stripped with
  // /FARM_V2_FILES[\s\S]*?`;/ — but the blob ends in };, not `;, so the non-greedy match ran
  // ~185KB past it to the first template literal's close, deleting renderLaborRow (the markup
  // this harness guards) from the scanned text. The blob is one LINE, so a line-anchored match
  // is the robust strip; it asserts it actually removed something, the same discipline
  // jsdom_app.cjs uses.
  //
  // ONE strip now, where there used to be two: E2 moved the adapter out of its own
  // `const PYTHON_CODE = ...` template literal and into farm_v2/adapter.py, so it travels
  // inside this same blob. The second strip would silently match nothing today, which is why
  // it is deleted rather than left in — a no-op strip guarded by a length check is a test that
  // fails for a reason unrelated to what it guards.
  const rawHtml = doc.documentElement.outerHTML;
  let html = rawHtml.replace(/const FARM_V2_FILES = .*/, '');
  if (html.length > rawHtml.length - 100000) {
    fail('blob strip removed almost nothing — FARM_V2_FILES is no longer one line, fix the strip');
  }
  const deadPhrases = [
    ['hired labor (up to your cap) first',       'the pre-W15 fill order (hire first)'],
    ['hiring then overtime',                     'the pre-W15 fill order'],
    ['Overtime is used beyond the hiring cap',   'the pre-W15 fill order (overtime as overflow)'],
    ['not tracked against crop-phase demand',    'salaried hours DO feed weekly labor capacity'],
    ['perfectly divisible — fractional headcount-weeks', 'the retired usage-billed labor model'],
    ['Hired wage',                               'the retired spot-market hire (L.3: a head inherits its row)'],
    ['hiring markup',                            'the retired spot-market hire (L.3)'],
    ['Max extra labor (hrs/week)',               'the retired spot-market hire (L.3)'],
  ];
  for (const [phrase, why] of deadPhrases) {
    if (html.includes(phrase)) {
      fail(`dead copy is back: "${phrase}" — this describes ${why}, which the solver does not do`);
    }
  }

  // 6b — overtime is entered as HOURS per person per week (grower ruling 2026-10-24; the old
  // '% of the week' read as on top). Live: typing into the row updates its readout.
  {
    const r10 = w.otReadout({ type: 'hourly', hours_per_week: 40, max_ot_hrs: 10 });
    if (!r10.includes('up to 50 h/wk') || !r10.includes('40 regular + 10 OT')) {
      fail(`otReadout(10 OT h on 40) printed "${r10}" — must read "up to 50 h/wk (40 regular + 10 OT)"`);
    }
    if (!/no overtime/.test(w.otReadout({ type: 'salary', hours_per_week: 45, max_ot_hrs: 10 }))) {
      fail('otReadout: a salaried row must say it gets no overtime');
    }
    if (!/no overtime/.test(w.otReadout({ type: 'hourly', hours_per_week: 40, max_ot_hrs: 0 }))) {
      fail('otReadout: 0 OT hours must say no overtime');
    }
    const row = w.document.querySelector('#labor-list .labor-row:nth-child(2)');
    const box = row && row.querySelector('[data-lf="max_ot_hrs"]');
    if (!box) fail('the roster row has no "Max OT hrs/wk" box');
    else {
      box.value = '20';
      box.dispatchEvent(new w.Event('input', { bubbles: true }));
      const txt = row.querySelector('.ot-readout').textContent;
      if (!txt.includes('up to 60 h/wk')) fail(`readout did not follow the box live: "${txt}"`);
      const sent = w.getLaborFromForm()[1].max_ot_hrs;
      if (sent !== 20) fail(`the payload carries max_ot_hrs=${sent}, typed 20`);
      box.value = '10'; box.dispatchEvent(new w.Event('input', { bubbles: true }));
    }
  }

  // 6c — a row restored with no saved overtime (a pre-L.2 plan) shows the OT_HRS_DEFAULT the
  // payload will send, not 'no overtime' (/code-review). A saved 'Max week %' is converted at
  // load by migrateFormState — pinned in form_state_client.cjs.
  {
    const old = { position: 'Old Crew', type: 'seasonal', count: 2, wage: 18, hours_per_week: 40, start_week: 10, end_week: 40 };
    if (!w.renderLaborRow(old, 99).includes('up to 50 h/wk')) fail('a row with no saved overtime reads "no overtime" while 10 h is sent');
    // A salaried row with no saved value shows 0, not the hourly default (it never gets overtime).
    if (!w.renderLaborRow({ ...old, type: 'salary' }, 99).includes('data-lf="max_ot_hrs" value="0"')) {
      fail('a salaried row with no saved overtime shows a non-zero OT box');
    }
  }

  // 6d — a blank FICA box is refused, not sent as 0 (/code-review).
  {
    const fb = doc.getElementById('fica_pct'), keep = fb.value;
    fb.value = '';
    const errs = w.validateParams(w.buildSolveParams());
    fb.value = keep;
    if (!errs.some(e => /Payroll taxes/.test(e))) fail('a blank payroll-taxes box was not refused');
  }

  // 7 — L.3: extra hires per roster row. The panel names each row's heads, prices them, offers the
  // round trip, and says WHY when the answer is zero (the shipped farm's answer — F1).
  {
    const sp = { hire_productivity_pct: 70 };
    const none = w.renderLaborPlan({ profit: 1, extra_hires: [] }, { profit: 1 }, sp);
    if (!/Hire more\?/.test(none)) fail('renderLaborPlan: with no row ticked it must say to tick "Hire more?"');
    const zeroRows = [{ position: 'Harvest Crew', row: 3, extra: 0, max_more: 5, cost_per_head: 26450, hours_per_head: 756 }];
    const zero = w.renderLaborPlan({ profit: 100, extra_hires: zeroRows }, { profit: 100 }, sp);
    if (!/No extra hire pays for itself/.test(zero) || !zero.includes('Harvest Crew') || !zero.includes('26,450')) {
      fail('renderLaborPlan: a zero answer must say no hire pays AND show each row\'s cost per head');
    }
    // The one-more-head figure: a loss is shown as the reason; a gain points at Max more.
    const lossHtml = w.renderLaborPlan({ profit: 100, extra_hires: [{ ...zeroRows[0], next_head_delta: -754 }] }, { profit: 100 }, sp);
    if (!/One more head would change profit by <strong>≈ −\$754/.test(lossHtml)) fail(`one-more-head loss not shown: ${lossHtml.slice(0, 400)}`);
    // Below Max more a small gain is the solver's tolerance, not a reason to raise the cap.
    const noiseHtml = w.renderLaborPlan({ profit: 100, extra_hires: [{ ...zeroRows[0], extra: 2, max_more: 5, next_head_delta: 60 }] }, { profit: 90 }, sp);
    if (/raise Max more/.test(noiseHtml) || !/≈ \$0/.test(noiseHtml)) fail('a +$60 figure below Max more must read ≈ $0, not "raise Max more"');
    const infHtml = w.renderLaborPlan({ profit: 100, extra_hires: [{ ...zeroRows[0], next_head_delta: null, next_head_status: 'infeasible' }] }, { profit: 100 }, sp);
    if (!/not affordable/.test(infHtml)) fail('an infeasible one-more-head must say it is not affordable');
    // A part-time row's default OT never exceeds its own hours (6 h/wk → 6, not 10).
    if (!w.renderLaborRow({ position: 'Helper', type: 'hourly', count: 1, wage: 18, hours_per_week: 6 }, 98).includes('data-lf="max_ot_hrs" value="6"')) {
      fail('a 6 h/wk row defaulted to more overtime hours than its regular hours');
    }
    const gainHtml = w.renderLaborPlan({ profit: 150, extra_hires: [{ ...zeroRows[0], extra: 5, next_head_delta: 1200 }] }, { profit: 100 }, sp);
    if (!/would ADD ≈ \$1,200/.test(gainHtml) || !/raise Max more/.test(gainHtml)) fail('a positive next-head figure must point at Max more');
    // A hostile position name must not become markup (escaping on the new surface).
    const evil = w.renderLaborPlan({ profit: 100, extra_hires: [{ ...zeroRows[0], position: '<img src=x onerror=1>' }] },
                                   { profit: 100 }, sp);
    if (evil.includes('<img')) fail('renderLaborPlan: a position name reached the page unescaped');
    // The round trip: +2 on the roster's 4th row → its Count goes up by 2.
    const rowEls = doc.querySelectorAll('#labor-list .labor-row');
    const countBox = rowEls[3].querySelector('[data-lf="count"]');
    const before = parseInt(countBox.value, 10);
    const took = [{ ...zeroRows[0], extra: 2 }];
    const yes = w.renderLaborPlan({ profit: 150, extra_hires: took }, { profit: 100 }, sp);
    if (!/\+2 Harvest Crew/.test(yes) || !/Add to roster/.test(yes)) fail('renderLaborPlan: taken heads must be named with an "Add to roster" action');
    w.addExtraToRoster(0);
    if (parseInt(countBox.value, 10) !== before + 2) {
      fail(`addExtraToRoster: Count went ${before} → ${countBox.value}, expected ${before + 2} (wrong row or no-op)`);
    }
    countBox.value = String(before);
    // The row's own hire columns reach the payload.
    const hm = rowEls[3].querySelector('[data-lf="hire_more"]'), mm = rowEls[3].querySelector('[data-lf="max_more"]');
    hm.checked = true; mm.value = '4';
    const e3 = w.getLaborFromForm()[3];
    if (e3.hire_more !== true || e3.max_more !== 4) fail(`getLaborFromForm: hire_more/max_more sent as ${e3.hire_more}/${e3.max_more}`);
    hm.checked = false; mm.value = '0';
  }

  if (failures) { console.error(`labor_ui_client: ${failures} FAILURE(S)`); process.exit(1); }
  console.log('labor UI (client): all checks passed (count visible on every row type, blank wage refused, typed 0 legal)');
  process.exit(0);
}).catch(e => { console.error('labor_ui_client crashed:', e); process.exit(1); });
