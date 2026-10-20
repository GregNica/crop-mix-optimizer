/* USER-TYPED NAMES ARE NOT MARKUP — every render surface, driven in a real DOM (E7).
 *
 * WHAT THIS GUARDS. Crop names, channel names and labor position names are free text the grower
 * types, and the app renders them by building HTML strings. Interpolated raw, a name containing
 * markup becomes DOM: an element, an attribute, an event handler. The same class as the XSS
 * found in the CSV-error sink during /code-review — that one was fixed; this file is the sweep.
 *
 * HOW IT MEASURES, and why it is not a grep. `escHtml` was used 15 times against 88 `innerHTML`
 * assignments, and counting call sites cannot tell you which of them see user data. So the
 * hostile name is pushed through the app's real render functions and the DOM is then asked a
 * question with one answer: did an ELEMENT appear? Script execution is not needed and not
 * relied on — jsdom parsing the string into a node IS the defect.
 *
 * TWO PAYLOADS, because they reach different sinks and the first one alone reports "clean" on
 * code that is not:
 *   * TEXT context  — `<img src=x data-xss=1>` lands where a name is written between tags.
 *   * ATTRIBUTE context — `" data-xss="1` needs a quote to break out of `value="…"`, so the
 *     text payload sails through the form untouched. Measured at E7: the text payload found 8
 *     surfaces, the attribute payload found 2 MORE that it could not see — and the attribute
 *     ones are the input form itself, so a hostile name typed once persists into saved plans.
 *
 * MEASURED BEFORE THE FIX (10 surfaces, 36 elements): renderAllCrops, renderExecutiveSummary,
 * renderSummaryPane, renderGanttCalendar, renderWhatIfCard, renderResultSections,
 * renderUnitBearingResults, renderScenarioHistory (text) + applyCrops, applyChannels (attribute).
 *
 * THE MIRROR DEFECT IS ALSO PINNED. Over-escaping is a real failure, not a safe one: a grower
 * who names a crop "Tom's Beets & Co" must not read "Tom&#39;s Beets &amp; Co" anywhere, and the
 * name must survive a round-trip through the form input unchanged. Escaping twice is the
 * classic follow-on bug and it is invisible to any test that only looks for markup.
 *
 * Run: node tests/escaping_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { bootApp, mkWeeks } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };
const ok = (name, cond) => { if (!cond) fail(name); };

const TEXT_PAYLOAD = '<img src=x data-xss=1>Beet';
const ATTR_PAYLOAD = '" data-xss="1';
const BENIGN       = "Tom's Beets & Co";


/** The fixture, parameterised by the name under test — the point is that one name flows into
 *  every collection the render surfaces read: crops, channels, employees, and the solver's own
 *  per-crop and per-channel result maps. */
function fixtures(NAME) {
  const RES = {
    revenue: 100000, variable_cost: 21000, fixed_cost: 22400, operating_profit: 55600,
    overhead_cost: 5000, interest_cost: 400, fixed_selling_cost: 1200, profit: 49000,
    peak_borrowing: 9000,
    bought_capacity_split: { city_water: 300, overtime: 700, hire: 0 }, overhead_covers: ['admin'],   // W8: iterated, not named
    fixed_selling_split: { [NAME]: 1200 },
    crop_names: [NAME],
    variable_cost_split: { water: 1500, fertilizer: 2500, fuel: 900, seed: 8100, packaging: 8000 },
    fixed_cost_split: { harvest_storage: 4000, wages: 5000 },
    channel_sales: { [NAME]: { lbs_sold: 900, revenue: 100000, by_crop: {
      [NAME]: { lbs_sold: 600, revenue: 60000, weekly_lbs: mkWeeks({ 20: 400 }) } } } },
    // WEEK 20 ON PURPOSE. The pie charts read the week slider, whose default is 20, and drawPie
    // short-circuits to "No activity." when the week it is handed is empty. With activity only
    // in weeks 10-12 this harness DROVE updatePieChart and scanned a pie that had rendered
    // nothing — the surface counted as covered and clean while three legend entries were in fact
    // unescaped. A fixture that misses the surface it is aimed at is the inert-guard mode this
    // repo keeps rediscovering; keep these weeks aligned with the slider default.
    succession_schedule: [
      { crop: NAME, acres: 10, weeks: [19, 20, 21], phases: [0, 1, 2], name: 'S W19' },
      // Name with NO trailing digits on purpose: succLabel returns the number when the name ends
      // in one and falls back to the RAW name otherwise. With only 'S W19' in the fixture the
      // fallback never ran, so its escaping was unpinned — reverting it left this harness green.
      { crop: NAME, acres: 4, weeks: [19, 20], phases: [0, 2], name: NAME }],
    weekly_land_frac: new Array(52).fill(0.2),
    weekly_harvest_vol: new Array(52).fill(10),
    weekly_labor_used: new Array(52).fill(50),
    weekly_labor_supply: new Array(52).fill(100),
    weekly_water_used: new Array(52).fill(5),
    weekly_water_supply: new Array(52).fill(10),
    demand_at_cap_threshold: 0.95,
    demand_saturation: { [NAME]: { [NAME]: {
      basis: 'weekly', cap_lbs: 28000, sold_lbs: 14000, fill: 0.5,
      peak_week_frac: 1.0, peak_week_cap_lbs: 2000, weeks_at_cap: [29, 30], binding: 1.0 } } },
    unplanted: [{ crop: NAME, reason: 'demand' }],
    warnings: [`${NAME} was not planted`],
    // Every field renderContributionMargins reads. A partial map makes it throw, and a surface
    // that throws has rendered nothing — which the loop below reports rather than scoring as
    // covered, because a clean scan of an empty container proves nothing.
    channel_margins: { [NAME]: { [NAME]: {
      margin_pct: 20, margin_per_acre_day: 3, margin_per_acre_cycle: 210,
      labor_hours_per_acre: 10, revenue_per_acre: 500, sold_lbs_per_acre: 4000,
      gross_price_per_lb: 4, occupancy_days: 70, cost_per_acre: {
        water: 10, fertilizer: 20, fuel: 5, seed: 30, crop_protection: 25, packaging: 40, overhead: 15,
        total: 145 } } } },
    crop_contribution: { [NAME]: { contribution: 5000, acres_planted: 10 } },
  };
  const PARAMS = {
    operating_weeks: 52, total_land: 80, opening_cash: 0, credit_line: 0,
    harvest_storage_cap: 500,
    channels: [{ name: NAME, fixed_selling_cost_per_wk: 5 }],
    // EVERY field carries the payload, not just `position`. These are numeric boxes in normal
    // use, but applyLabor's source is a SAVED PLAN — user-supplied JSON that can hold a string
    // where a number belongs — and each one is interpolated into `value="…"`. Driving only
    // `position` left five of those attributes escaped but unpinned; with the payload in `wage`
    // alone, the summary pane still swallowed it (fmtN turns it into NaN → '—').
    employees: [{ position: NAME, type: 'seasonal', count: NAME, wage: NAME,
                  hours_per_week: NAME, field_time_pct: NAME,
                  start_week: NAME, end_week: NAME }],
    crops: [{ name: NAME, yield_per_acre: 5000, harvest_weeks: 1,
              channels_data: { [NAME]: { price: 4.0, demand_value: 99999 } },
              channels: { [NAME]: { price_per_lb: '4', demand_cap_type: 'annual',
                                    annual_demand_lbs: '99999' } } }],
  };
  return { RES, PARAMS };
}

/** Every surface that renders a user-typed name, with the arguments it takes. */
function surfaces(W, RES, PARAMS) {
  return [
    ['applyCrops',               () => W.applyCrops(PARAMS.crops)],
    ['applyChannels',            () => W.applyChannels(PARAMS.channels)],
    ['applyLabor',               () => W.applyLabor(PARAMS.employees)],
    ['renderAllCrops',           () => W.renderAllCrops()],
    ['renderAllChannels',        () => W.renderAllChannels()],
    ['renderAllLabor',           () => W.renderAllLabor()],
    ['renderExecutiveSummary',   () => W.renderExecutiveSummary(RES, PARAMS)],
    ['renderUnplantedCrops',     () => W.renderUnplantedCrops(RES)],
    ['renderSummaryPane',        () => W.renderSummaryPane(PARAMS)],
    ['renderGanttCalendar',      () => W.renderGanttCalendar(RES)],
    ['renderWhatIfCard',         () => W.renderWhatIfCard(RES, PARAMS)],
    ['renderResultSections',     () => W.renderResultSections(PARAMS, RES)],
    ['renderUnitBearingResults', () => W.renderUnitBearingResults(PARAMS, RES)],
    ['renderContributionMargins', () => W.renderContributionMargins(PARAMS)],
    ['renderBackCheckPanel',     () => W.renderBackCheckPanel(RES)],
    // Only the BASELINE row of this table is reachable here: the history rows come from
    // WHATIF_STATE, a `const` in the app's inline script and so not addressable from the test
    // window. Their three cells (r.label / r.resourceDisplay / r.topCrops) are escaped but
    // UNPINNED — see BACKLOG S22 for the surfaces jsdom structurally cannot reach.
    ['renderScenarioHistory',    () => W.renderScenarioHistory(RES, PARAMS)],
    ['renderSensitivitySetup',   () => W.renderSensitivitySetup(PARAMS, RES)],
    ['renderCSVErrors',          () => W.renderCSVErrors(
                                        [{ row: 1, field: PARAMS.crops[0].name,
                                           msg: PARAMS.crops[0].name }])],
    ['renderHub',                () => W.renderHub()],
    ['renderStepper',            () => W.renderStepper()],
  ];
}

(async () => {
  const W = await bootApp();
  const D = W.document;

  /** Seed the app's globals for one name and hand back the surfaces to drive. */
  const drive = NAME => {
    const { RES, PARAMS } = fixtures(NAME);
    W._lastRes = RES; W._lastParams = PARAMS; W._ganttRes = RES;
    return { RES, PARAMS, list: surfaces(W, RES, PARAMS) };
  };

  // Pre-flight, once: the page cannot change between payloads, so checking existence inside the
  // payload loop just asserts the same 20 things twice. A NAMED count instead of a bare floor —
  // `>= 15` against a 20-entry list would let five entries be deleted in silence, and the
  // closing log would still claim to have covered them.
  const SURFACE_NAMES = drive(BENIGN).list.map(([label]) => label);
  const EXPECTED_SURFACES = SURFACE_NAMES.length;
  for (const label of SURFACE_NAMES) {
    ok(`${label} is gone from the page — this guard silently stopped covering it`,
       typeof W[label] === 'function');
  }

  for (const [payloadName, PAYLOAD] of [['text', TEXT_PAYLOAD], ['attribute', ATTR_PAYLOAD]]) {
    let drivenCount = 0;
    for (const [label, run] of drive(PAYLOAD).list) {
      // A surface that throws has rendered nothing, so a clean scan below would mean nothing.
      // Report it rather than counting it as covered.
      let returned;
      try { returned = run(); drivenCount++; }
      catch (e) { fail(`${payloadName}: ${label} threw, so it is NOT covered — ${String(e.message).slice(0, 70)}`); }

      // Some surfaces RETURN markup instead of writing it (renderCSVErrors builds the error
      // list its caller inserts). Calling one of those and scanning the document finds nothing,
      // so the entry sat in this list looking like coverage while its escaping was unpinned —
      // measured: reverting either escHtml in renderCSVErrors left this harness green. Park the
      // returned string in the DOM so the same question can be asked of it.
      if (typeof returned === 'string' && returned.includes('<')) {
        const sink = D.createElement('div');
        sink.innerHTML = returned;
        D.body.appendChild(sink);
      }

      const hits = D.querySelectorAll('[data-xss]');
      ok(`${payloadName} payload: ${label} rendered a user-typed name as LIVE MARKUP `
         + `(${hits.length} element${hits.length === 1 ? '' : 's'})`, hits.length === 0);
      hits.forEach(h => h.remove());   // so the next surface reports independently
    }
    ok(`${payloadName}: every surface drove (${drivenCount} of ${EXPECTED_SURFACES})`,
       drivenCount === EXPECTED_SURFACES);
  }

  // ── The mirror defect: escaping must not be VISIBLE ────────────────────────
  // Over-escaping is a defect too, and one no markup-hunting assertion can see. A grower whose
  // crop is "Tom's Beets & Co" must read that, not "Tom&#39;s Beets &amp; Co".
  {
    const { PARAMS, list } = drive(BENIGN);
    for (const [, run] of list) { try { run(); } catch (e) { /* covered above */ } }

    // jsdom counts the app's own inline <script> in body.textContent, and that source contains
    // both the escHtml entity table and every "&amp;" in static page copy. Strip scripts, and
    // scope the check to entities adjacent to OUR name, or this asserts on the page's own prose.
    const clone = D.body.cloneNode(true);
    clone.querySelectorAll('script').forEach(n => n.remove());
    const txt = clone.textContent;
    ok('the benign name renders somewhere at all (else this check proves nothing)',
       txt.includes(BENIGN));
    const leak = txt.match(/Tom(&#39;|&amp;|&quot;)|Beets\s*&amp;/);
    ok(`escaping is visible to the grower — double-escaped: ${JSON.stringify(leak && leak[0])}`,
       !leak);

    // Re-applied here on purpose: the loop above ends with renderAllCrops(), which repaints the
    // card list from the app's own state and would leave the demo's "Spinach" in the box. The
    // property under test is the FORM path — applyCrops writes the name into a value attribute,
    // which is the sink the attribute payload proved was open.
    W.applyCrops(PARAMS.crops);
    const input = D.querySelector('.crop-name-inline');
    ok('a crop name input still exists', !!input);
    ok(`the name round-trips through the form input unchanged (got ${JSON.stringify(input && input.value)})`,
       !!input && input.value === BENIGN);
  }

  // R1 — the margin table's cost tooltip lists EVERY category the solver puts in cost_per_acre.
  // It used to hand-name them and missed crop protection the commit it was added, so its lines
  // summed short of the Total VC printed beside them. (Here because this harness already renders
  // the table with a full fixture.)
  {
    const { RES, PARAMS } = drive(BENIGN);
    W.renderContributionMargins(PARAMS);
    const cell = [...D.querySelectorAll('[title]')].find(e => e.getAttribute('title').includes('Total VC'));
    const tip = cell ? cell.getAttribute('title') : '';
    const cats = Object.keys(Object.values(Object.values(RES.channel_margins)[0])[0].cost_per_acre).filter(k => k !== 'total');
    const missing = cats.filter(k => !tip.includes(`${W.eval('VC_TOOLTIP_LABELS')[k] || k}: $`));
    ok(`the margin-table cost tooltip lists every cost category (missing: ${JSON.stringify(missing)})`,
       !!cell && missing.length === 0);
  }

  if (failures) {
    console.error(`\nescaping_client: ${failures} failure(s)`);
    process.exit(1);
  }
  console.log(`escaping (client): all checks passed (${EXPECTED_SURFACES} surfaces `
    + `x text + attribute payloads, no double-escaping)`);
})().catch(e => { console.error(e); process.exit(1); });
