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
  // data-tip attributes, minus the embedded Python blob.
  const html = doc.documentElement.outerHTML.replace(/const FARM_V2_FILES[\s\S]*?`;/, '');
  const deadPhrases = [
    ['hired labor (up to your cap) first',       'the pre-W15 fill order (hire first)'],
    ['hiring then overtime',                     'the pre-W15 fill order'],
    ['Overtime is used beyond the hiring cap',   'the pre-W15 fill order (overtime as overflow)'],
    ['not tracked against crop-phase demand',    'salaried hours DO feed weekly labor capacity'],
    ['perfectly divisible — fractional headcount-weeks', 'the retired usage-billed labor model'],
  ];
  for (const [phrase, why] of deadPhrases) {
    if (html.includes(phrase)) {
      fail(`dead copy is back: "${phrase}" — this describes ${why}, which the solver does not do`);
    }
  }

  // 6 — readHiredWageBox is THE definition of blank-vs-typed for the hired wage (a typed $0
  // was silently reinterpreted as blank once; that bug shipped). Pin the classification.
  const hwBox = doc.getElementById('hired_wage_per_hr');
  const hwSaved = hwBox.value;
  hwBox.value = '';
  let hw = w.readHiredWageBox();
  if (!hw.blank) fail('readHiredWageBox: an empty box must classify as blank (= infer)');
  hwBox.value = '19';
  hw = w.readHiredWageBox();
  if (hw.blank || hw.wage !== 19) fail(`readHiredWageBox: typed 19 gave blank=${hw.blank} wage=${hw.wage}`);
  hwBox.value = '0';
  hw = w.readHiredWageBox();
  if (hw.blank || hw.wage !== 0) {
    fail(`readHiredWageBox: typed 0 gave blank=${hw.blank} wage=${hw.wage} — a typed 0 is a `
       + `refusable VALUE, not blank; classifying it blank is the silent-reinterpretation bug`);
  }
  hwBox.value = hwSaved;

  // 7 — the printed bought-hour price must weight hours against the RIGHT weeks. The hour
  // series is 1-indexed (53 entries) and the rate arrays 0-indexed (52) — an off-by-one
  // would print a wrong dollar figure to the grower with everything green. Synthetic plan:
  // 10 hrs at $20 (week 1) + 30 hrs at $40 (week 52) → weighted $35.00; zero OT hours →
  // fallback to the annual mean of the OT rate array ($30.00).
  const hireHours = new Array(53).fill(0); hireHours[1] = 10; hireHours[52] = 30;
  const hireRates = new Array(52).fill(0); hireRates[0] = 20; hireRates[51] = 40;
  const sr = {
    profit: 120000,
    hired_hours_weekly: hireHours, overtime_hours_weekly: new Array(53).fill(0),
    hire_rate_full_weekly: hireRates, overtime_rate_full_weekly: new Array(52).fill(30),
  };
  const planHtml = w.renderLaborPlan(sr, { profit: 100000 },
    { hire_wage_markup: 0, overtime_rate_multiplier: 1.5, payroll_load_pct: 0.25, hired_wage_per_hr: null });
  if (!planHtml.includes('$35.00')) {
    fail(`renderLaborPlan priced 10h@$20 + 30h@$40 as something other than $35.00 — the `
       + `1-indexed hours / 0-indexed rates offset is wrong (got: `
       + `${(planHtml.match(/~\$[\d.]+\/hr/g) || []).join(', ')})`);
  }
  if (!planHtml.includes('$30.00')) {
    fail('renderLaborPlan: with zero OT hours the OT price must fall back to the annual mean ($30.00)');
  }

  if (failures) { console.error(`labor_ui_client: ${failures} FAILURE(S)`); process.exit(1); }
  console.log('labor UI (client): all checks passed (count visible on every row type, blank wage refused, typed 0 legal)');
  process.exit(0);
}).catch(e => { console.error('labor_ui_client crashed:', e); process.exit(1); });
