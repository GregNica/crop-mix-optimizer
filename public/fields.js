/* fields.js — THE field registry (E5b). One entry per input a grower can set, and one per key the
 * solver payload carries. Everything else that used to keep its own list is a VIEW over this:
 *
 *   units.js  FIELD_REGISTRY / DATA_F_REGISTRY  ← form[id].units / crop[f].units
 *   index.html BENCHMARK_DEFAULTS                ← form[id].benchmark
 *   worker/grounding.ts CHATBOT_FIELDS / CROP_DETAIL_FIELDS ← form[id].chat / crop[f].chat
 *
 * Six hand-kept lists used to describe overlapping sets of the same fields, and nothing failed when
 * one drifted (measured 2026-10-19: no drift YET — this makes it impossible rather than lucky).
 * tests/field_registry_client.cjs and tests/test_field_registry.py pin it in both directions: every
 * input the form renders has an entry and every entry is rendered; every key the adapter reads is in
 * `payload` and every `payload` key is read.
 *
 * WHY A PLAIN SCRIPT AND NOT JSON. Three runtimes read it — the page (a classic <script>, no build
 * step), the Node harnesses (a vm sandbox, like units.js) and the Worker (bundled by wrangler via a
 * side-effect import) — and the provenance research behind each benchmark lives in its COMMENTS,
 * which JSON cannot carry. It attaches to globalThis and nothing else.
 *
 * NOT HERE, on purpose: CROP_PROVENANCE (index.html). It is keyed by crop TEMPLATE (Arugula, Basil …)
 * — sourced values for each template — not by field, so it is template data, not field metadata.
 *
 * Shape:  form[id]   — flat inputs, keyed by element id, in form order.
 *           units     — canonical⇄display spec (see units.js); absent = never converted
 *           benchmark — the sourced default written into the field (values are CANONICAL);
 *                       confidence: high = peer-reviewed/govt survey, medium = industry
 *                       survey, low = rough estimate. Irrigation, equipment-storage and
 *                       fuel-storage RATES carry none on purpose: they are derived from capital
 *                       cost ÷ useful life (the cost-accounting basis), not entered.
 *           chat      — how the setup assistant describes it; units are CANONICAL. WHETHER
 *                       the assistant may propose it is decided by the ordered allowlist in
 *                       worker/grounding.ts, where a change to its powers is reviewed.
 *           ui        — a disclosure toggle, not a farm fact (never reaches the payload;
 *                       a switch that GATES payload keys, like pd-cash, is not ui)
 *         crop[f]    — per-crop / per-channel inputs, keyed by data-f (units, chat as above)
 *         payload[k] — every top-level key run_from_js reads:
 *           from      — the form ids it is built from ('@labor' / '@channels' / '@crops' = a collection)
 *           sentBy    — sent only by one tool, not the main solve (what-if, monte-carlo)
 *           unsent    — read by the adapter but sent by NOTHING; the reason must say why
 */
(function (root) {
  'use strict';

  var form = {
    total_land: {
      units: { measure: 'area_land' },
      benchmark: { value: 80,       label: 'Total Land',           source: 'USDA NASS CA vegetable census',      vintage: '2022', confidence: 'medium' },
      chat: { label: "Total land", type: "number", unit: "acres", min: 1, max: 5000,
        description: "Acreage usable for crops (exclude buildings, roads, unusable land). Hectares × 2.47 = acres." },
    },
    // NOT a ui toggle: it decides whether opening_cash/credit_line are sent at all, which is what
    // switches the C13 cash floor on in the adapter (/code-review).
    'pd-cash': {},
    opening_cash: {
      benchmark: { value: 300000,   label: 'Opening Cash',         source: 'Farm Bureau operating capital guide', vintage: '2023', confidence: 'medium' },
    },
    credit_line: {
      benchmark: { value: 800000,   label: 'Credit Line',          source: 'AgriBank farm credit survey',         vintage: '2022', confidence: 'low'    },
    },
    'pd-machinery': {
      ui: true,
    },
    equip_storage: {
      units: { measure: 'vol_bulk' },
    },
    fuel_storage: {
      units: { measure: 'vol_liquid' },
    },
    rate_property_mortgage_rent: {
      benchmark: { value: 0, label: 'Property Mortgage/Rent ($/wk)', source: 'USDA ERS land value survey — user override recommended', vintage: '2023', confidence: 'low' },
      chat: { label: "Property mortgage/rent", type: "number", unit: "$/week", min: 0,
        description: "Cost of the land itself — mortgage payment or another fixed land/facility payment — PER WEEK. Convert monthly ÷ 4.33, annual ÷ 52. A payment, not an interest rate. 0 if owned free and clear. NOT per-acre cash rent on rented ground: that is a separate field (rented acres × rent per acre), so never put it here too." },
    },
    other_debt_service_per_week: {
      chat: { label: "Other debt service", type: "number", unit: "$/week", min: 0,
        description: "Whole weekly PAYMENT on other carried/long-term debt (e.g. equipment loans) — not an interest rate. Convert monthly ÷ 4.33, annual ÷ 52." },
    },
    // R7 (Batch 2.2) — land tenure, ownership carrying, insurance. With `chat` blocks (W10 review):
    // the overhead description tells the assistant to take these OUT of overhead, so it must be
    // able to put them somewhere, or a chat-driven setup charges them nowhere.
    rented_acres: {
      units: { measure: 'area_land' },
      chat: { label: "Rented acres", type: "number", unit: "acres", min: 0,
        description: "How much of the farm's land is RENTED (cash rent). 0 if they own all of it. Never more than total land. Hectares × 2.47 = acres." },
    },
    cash_rent_per_acre_yr: {
      units: { measure: 'area_land', inverse: true },   // $/acre/yr
      chat: { label: "Rent per rented acre", type: "number", unit: "$/acre/year", min: 0,
        description: "Rent paid per rented acre per YEAR. Convert $/ha ÷ 2.47; a monthly figure × 12. This is NOT the mortgage — that is the property mortgage/rent field (per week) for owned land." },
    },
    ownership_carrying_pct: {
      chat: { label: "Ownership carrying %", type: "number", unit: "% of installed cost per year", min: 0, max: 30,
        description: "Interest + repairs + property tax on owned buildings, storage, tanks and irrigation, as a percent of their installed cost per year (NOT depreciation, NOT insurance, NOT machinery). Extension rules of thumb: repairs 1–1.5% + property tax 1–1.5% + interest at their borrowing rate on about half the cost. If unsure, explain and suggest ~6%, and CONFIRM rather than setting silently." },
    },
    insurance_premium_per_yr: {
      chat: { label: "Farm insurance", type: "number", unit: "$/year", min: 0,
        description: "TOTAL insurance premiums per YEAR — crop, liability and property (including buildings and equipment). Convert monthly × 12. If their overhead % already includes insurance, it must come out of the overhead figure." },
    },
    insurance_payment_week: {},
    utilities_cost_per_yr: {                           // W10
      chat: { label: "Utilities (electricity)", type: "number", unit: "$/year", min: 0,
        description: "The farm's whole ELECTRICITY bill per YEAR (plus propane/heating fuel if any) — cooling, irrigation pumps, buildings. NOT city water (its own field). Convert monthly × 12. If their overhead % already includes it, it must come out of the overhead figure." },
    },
    'pd-harvest-storage': {
      ui: true,
    },
    // 80 ac × 120 ft³/ac (CIAS Grower to Grower Table 2, range 50–250) = 272 m³. Sanity-checked
    // against this plan's own physics: peak weekly sellable harvest is 139 m³, ÷0.75 for
    // aisles/racking/airflow = 185 m³ of room, so 275 leaves ~1.5× headroom — the right shape
    // for a building you commit to before you know the year's crop mix. The previous 5,000 m³
    // was a scaled-down echo of the legacy Excel model's arbitrary 24,000, and cited a Cornell
    // "sizing guide" that does not exist — Cornell's actual resource is a temp/humidity chart.
    // Note this is a cost driver as well as a cap: every m³ bills depreciation, used or not.
    // 275 m3 covers room occupancy: that week's harvest plus anything carried over. B.3 closed
    // the held-stock gap this note used to describe.
    harvest_storage_cap: {
      units: { measure: 'vol_bulk' },
      benchmark: { value: 275,      label: 'Harvest Storage',      source: 'CIAS/UW-Madison Grower to Grower survey (120 ft³/acre)', vintage: '2008', confidence: 'medium' },
    },
    harvest_storage_cost_per_m3: {
      units: { measure: 'vol_bulk', inverse: true },   // $/m³ (capital)
    },
    depreciation_harvest_years: {},
    ambient_storage_cap: {
      units: { measure: 'vol_bulk' },
    },
    ambient_storage_cost_per_m3: {
      units: { measure: 'vol_bulk', inverse: true },   // $/m³ (capital)
    },
    depreciation_ambient_years: {},
    'pd-irrig-fert': {
      ui: true,
    },
    irrigation_cost_per_acre: {
      units: { measure: 'area_land', inverse: true },   // $/acre (capital)
    },
    depreciation_irrigation_years: {},
    cost_fert_per_lb: {
      units: { measure: 'mass', inverse: true },   // $/lb (metered)
      benchmark: { value: 0.82,     label: 'Fertilizer Rate',      source: 'USDA NASS fertilizer price survey',   vintage: '2023', confidence: 'high'   },
    },
    'pd-machinery-rates': {
      ui: true,
    },
    rate_machinery: {
      benchmark: { value: 1000,     label: 'Machinery ($/wk)',     source: 'USDA ERS machinery ownership model',  vintage: '2022', confidence: 'medium' },
    },
    cost_fuel_per_L: {
      units: { measure: 'vol_liquid', inverse: true },   // $/L (metered)
      benchmark: { value: 1.25,     label: 'Fuel Rate ($/L)',      source: 'EIA diesel fuel CA avg',              vintage: '2023', confidence: 'medium' },
    },
    equip_storage_cost_per_m3: {
      units: { measure: 'vol_bulk', inverse: true },   // $/m³ (capital)
    },
    depreciation_equip_years: {},
    fuel_storage_cost_per_L: {
      units: { measure: 'vol_liquid', inverse: true },   // $/L (capital)
    },
    depreciation_fuel_years: {},
    sell_through_pct: {
      chat: { label: "Sell-through %", type: "number", unit: "%", min: 1, max: 100,
        description: "Of what is TAKEN TO MARKET, the share that converts to cash — losses between field and sale only: display shrink at a stall, samples, damage in transit, a rejected load (grower ruling, DECISIONS E1). NOT grade-out at harvest (that belongs in the yield figure — never lower both), NOT spoilage in storage (the app has no input for that yet — say so rather than putting it here), NOT a price discount. Defaults to 100%: deliveries against an order and crops that store lose nothing here. Only if the user describes loss AT MARKET ('X% of what I bring to market doesn't sell') is it 100 − X. FARM-WIDE default; per-crop values are set on each crop." },
    },
    overhead_pct: {
      chat: { label: "Overhead % of revenue", type: "number", unit: "%", min: 0, max: 60,
        description: "Overhead as a percent of REVENUE (not of costs) — land taxes, admin (incl. phone & internet), office/vehicle. EXCLUDES costs itemized elsewhere (land rent/mortgage, the machinery line, labor, seed, water, fertilizer, fuel, packaging, crop protection, irrigation, storage, channel selling costs, other debt service, interest on operating borrowing, city water, farm insurance, utilities (electricity incl. cooling and pump energy), and the interest, repairs and property tax on owned buildings, storage and irrigation); if the user's figure includes those, ask them to exclude them. If given in dollars, ask for revenue or the percent — don't guess." },
    },
    interest_rate_pct: {
      chat: { label: "Interest APR %", type: "number", unit: "% APR", min: 0, max: 40,
        description: "APR on the SEASONAL OPERATING credit line (drawn when cash runs short) — NOT a mortgage or equipment-loan rate. Annualize a monthly rate (× 12)." },
    },
    min_viable_margin_pct: {
      chat: { label: "Minimum viable margin %", type: "number", unit: "%", min: 0, max: 60,
        description: "Net-margin floor: crop-channels below it are dropped as 'not worth growing'; 0 disables it. Expert setting — if the user doesn't raise it, briefly explain it and suggest a small floor (~8%) or 0, and CONFIRM rather than setting silently." },
    },
    climate_zone: {},
    well_enabled: {
      chat: { label: "Well water available", type: "boolean",
        description: "Whether the farm draws irrigation water from a well / groundwater. Set false if they say they don't use one." },
    },
    well_weekly_cap_L: {
      units: { measure: 'vol_liquid', perWeek: true },   // L/wk quantity
      benchmark: { value: 8700000,  label: 'Well Weekly Cap',      source: 'UW-Madison Extension: 8 gpm/irrigated acre x 80 ac x 60 h/wk (= 1.06 in/ac/wk; cross-checks against the 1-1.5 in/wk peak need)', vintage: '2016', confidence: 'medium' },
      chat: { label: "Well weekly cap", type: "number", unit: "liters/week", min: 0,
        description: "Max LITERS PER WEEK the well/permit allows. Convert gallons × 3.785. A pump FLOW RATE (e.g. gpm) is NOT a weekly cap — NEVER assume the well runs 24/7. Ask how many hours/day and days/week they actually pump, and whether it runs dry / must recharge, THEN compute liters/week = gpm × 3.785 × minutes actually pumped per week. Only relevant when well water is enabled." },
    },
    catchment_enabled: {
      chat: { label: "Rainwater catchment", type: "boolean",
        description: "Whether the farm captures rainwater off a surface for irrigation. Set false if they say they don't." },
    },
    catchment_surface_area_m2: {
      units: { measure: 'area_floor' },
      chat: { label: "Catchment surface area", type: "number", unit: "m²", min: 0,
        description: "The rainwater COLLECTION SURFACE area (e.g. roof) in m² — NOT the storage tank size. Convert sq ft ÷ 10.76. Only relevant when catchment is enabled." },
    },
    water_storage_capacity: {
      units: { measure: 'vol_liquid' },
    },
    city_water_enabled: {
      chat: { label: "City/municipal water", type: "boolean",
        description: "Whether the farm can buy municipal water as a backstop supply. Set false if they say they don't." },
    },
    city_water_cost_per_L: {
      units: { measure: 'vol_liquid', inverse: true },   // $/L
      chat: { label: "City water cost", type: "number", unit: "$/liter", min: 0,
        description: "Cost per LITER of municipal water. Convert $/gallon ÷ 3.785, $/m³ ÷ 1000 (bills often quote $/1000 gal or $/CCF — ask if unsure). Only relevant when city water is enabled." },
    },
    water_tank_cost_per_L: {
      units: { measure: 'vol_liquid', inverse: true },   // $/L (capital)
    },
    depreciation_water_years: {},
    payroll_load_pct: {
      chat: { label: "Payroll load %", type: "number", unit: "%", min: 0, max: 80,
        description: "Percent ADDED on top of wages for employer burden (payroll taxes, benefits, workers' comp, insurance) — NOT the wage itself and NOT labor's share of revenue. Typical 15–35%. Explain if the user is unsure." },
    },
    labor_flex_enabled: {
      ui: true,
    },
    labor_flex_hire: {},
    max_hire_hrs_per_week: {},
    hired_wage_per_hr: {},
    hire_wage_markup_pct: {},
    labor_flex_overtime: {},
    overtime_rate_multiplier: {},
    max_overtime_hrs_per_week: {},
    'pd-ch-vardetail': {
      ui: true,
    },
    'pd-phase-detail': {
      ui: true,
    },
  };

  var crop = {
    ch_default_pkg: {
      units: { measure: 'mass', inverse: true },   // $/lb default packaging
    },
    ch_var_sell: {
      units: { measure: 'mass', inverse: true },   // $/lb variable selling cost
    },
    days_to_maturity: {
      chat: { label: "Days to maturity", type: "number", unit: "days", min: 7, description: "Days from planting to first harvest." },
    },
    planting_weeks: {
      chat: { label: "Planting weeks", type: "number", min: 1, max: 8, description: "Weeks spent in the planting phase." },
    },
    harvest_weeks: {
      chat: { label: "Harvest weeks", type: "number", min: 1, max: 20, description: "Weeks the crop yields harvestable produce." },
    },
    min_acreage_if_planted: {
      units: { measure: 'area_land' },   // acres
      chat: { label: "Min acreage if planted", type: "number", unit: "acres", min: 0, description: "Minimum acres to commit if this crop is planted at all." },
    },
    committed_acres: {
      units: { measure: 'area_land' },   // acres
    },
    sell_through_pct: {
      chat: { label: "Per-crop sell-through %", type: "number", unit: "%", min: 1, max: 100, description: "For THIS crop, of what is taken to market, the share that converts to cash (overrides the farm default). Market losses only — not grade-out (that is in yield), not storage spoilage (no input yet). A crop that stores or is delivered against an order stays at 100: what does not sell comes home and sells later. '15% of what I bring to market doesn't sell' => 85." },
    },
    sales_spread_weeks: {
      chat: { label: "Sellable weeks", type: "number", min: 1, max: 52, description: "Weeks the crop can be sold in, counting the harvest week (1 = must sell the week it is picked)." },
    },
    cold_storage: {},
    overwinters: {},
    planting_type: {
      chat: { label: "Planting type", type: "enum", enum: ["seed", "transplant"], description: "Direct-seeded or transplanted." },
    },
    seed_transplant_cost_per_acre: {
      units: { measure: 'area_land', inverse: true },   // $/acre
      chat: { label: "Seed/transplant cost", type: "number", unit: "$/acre", min: 0, description: "Seed or transplant cost per acre." },
    },
    crop_protection_cost_per_acre: {
      units: { measure: 'area_land', inverse: true },   // $/acre per planting (R1)
      chat: { label: "Crop protection cost", type: "number", unit: "$/acre per planting", min: 0,
        description: "Sprays, biologicals, row covers and other pest & disease control, per acre per planting. Excluded from overhead — if their overhead % included it, it must come out." },
    },
    yield_per_acre: {
      units: { num: 'mass', den: 'area_land' },   // lb/acre
      chat: { label: "Yield per acre", type: "number", unit: "lbs/acre", min: 1, description: "Expected pounds harvested per acre per planting." },
    },
    crop_diversity_max: {},
    lbs_per_tote: {
      units: { measure: 'mass' },   // lbs
      chat: { label: "Lbs per tote", type: "number", min: 1, description: "Pounds per 18-gallon harvest tote (storage sizing)." },
    },
    s1_start_m: {},
    s1_start_d: {},
    s1_end_m: {},
    s1_end_d: {},
    s2_start_m: {},
    s2_start_d: {},
    s2_end_m: {},
    s2_end_d: {},
    // Per-phase resource rates (behind pd-phase-detail) — per-area rates, /wk. The denominator
    // (area_land) converts acre⇄ha; the numerator converts by its own dimension (labor's is
    // time, which is system-invariant, so only the /area factor applies).
    labor_plant: {
      units: { num: 'time',       den: 'area_land', perWeek: true },   // hr/acre/wk
    },
    labor_grow: {
      units: { num: 'time',       den: 'area_land', perWeek: true },
    },
    labor_harv: {
      units: { num: 'time',       den: 'area_land', perWeek: true },
    },
    water_plant: {
      units: { num: 'vol_liquid', den: 'area_land', perWeek: true },   // L/acre/wk
    },
    water_grow: {
      units: { num: 'vol_liquid', den: 'area_land', perWeek: true },
    },
    water_harv: {
      units: { num: 'vol_liquid', den: 'area_land', perWeek: true },
    },
    fert_plant: {
      units: { num: 'mass',       den: 'area_land', perWeek: true },   // lb/acre/wk
    },
    fert_grow: {
      units: { num: 'mass',       den: 'area_land', perWeek: true },
    },
    fert_harv: {
      units: { num: 'mass',       den: 'area_land', perWeek: true },
    },
    fuel_plant: {
      units: { num: 'vol_liquid', den: 'area_land', perWeek: true },   // L/acre/wk
    },
    fuel_grow: {
      units: { num: 'vol_liquid', den: 'area_land', perWeek: true },
    },
    fuel_harv: {
      units: { num: 'vol_liquid', den: 'area_land', perWeek: true },
    },
    ch_price: {
      units: { measure: 'mass', inverse: true },   // $/lb
    },
    ch_pkg: {
      units: { measure: 'mass', inverse: true },   // $/lb packaging
    },
    ch_demand_type: {},
    ch_demand_value: {
      units: { measure: 'mass' },   // lbs (a capacity quantity)
    },
    ch_season_start: {},
    ch_season_end: {},
  };

  var payload = {
    total_land:                  { from: ['total_land'] },
    water_storage_capacity:      { from: ['water_storage_capacity'] },
    rate_water_storage:          { from: ['water_tank_cost_per_L', 'depreciation_water_years'] },
    rate_machinery:              { from: ['rate_machinery'] },
    rate_property_mortgage_rent: { from: ['rate_property_mortgage_rent'] },
    other_debt_service_per_week: { from: ['other_debt_service_per_week'] },
    sell_through_fraction:       { from: ['sell_through_pct'] },
    overhead_pct_of_revenue:     { from: ['overhead_pct'] },
    interest_rate_apr:           { from: ['interest_rate_pct'] },
    climate_zone:                { from: ['climate_zone'] },
    well_enabled:                { from: ['well_enabled'] },
    well_weekly_cap_L:           { from: ['well_weekly_cap_L'] },
    catchment_enabled:           { from: ['catchment_enabled'] },
    catchment_surface_area_m2:   { from: ['catchment_surface_area_m2'] },
    city_water_enabled:          { from: ['city_water_enabled'] },
    city_water_cost_per_L:       { from: ['city_water_cost_per_L'] },
    employees:                   { from: ['@labor'] },
    payroll_load_pct:            { from: ['payroll_load_pct'] },
    channels:                    { from: ['@channels'] },
    crops:                       { from: ['@crops'] },
    harvest_storage_cap:         { from: ['harvest_storage_cap'] },
    rate_harvest_storage:        { from: ['harvest_storage_cost_per_m3', 'depreciation_harvest_years'] },
    ambient_storage_cap:         { from: ['ambient_storage_cap'] },
    rate_ambient_storage:        { from: ['ambient_storage_cost_per_m3', 'depreciation_ambient_years'] },
    equip_storage:               { from: ['equip_storage'] },
    fuel_storage:                { from: ['fuel_storage'] },
    rate_irrigation:             { from: ['irrigation_cost_per_acre', 'depreciation_irrigation_years'] },
    cost_fert_per_lb:            { from: ['cost_fert_per_lb'] },
    rate_equip_storage:          { from: ['equip_storage_cost_per_m3', 'depreciation_equip_years'] },
    rate_fuel_storage:           { from: ['fuel_storage_cost_per_L', 'depreciation_fuel_years'] },
    cost_fuel_per_L:             { from: ['cost_fuel_per_L'] },
    opening_cash:                { from: ['opening_cash', 'pd-cash'] },   // sent only while pd-cash is on
    credit_line:                 { from: ['credit_line', 'pd-cash'] },
    min_viable_margin_pct:       { from: ['min_viable_margin_pct'] },
    rented_acres:                { from: ['rented_acres'] },
    cash_rent_per_acre_yr:       { from: ['cash_rent_per_acre_yr'] },
    ownership_carrying_rate:     { from: ['ownership_carrying_pct'] },   // a FRACTION (pct / 100)
    insurance_premium_per_yr:    { from: ['insurance_premium_per_yr'] },
    insurance_payment_week:      { from: ['insurance_payment_week'] },
    utilities_cost_per_yr:       { from: ['utilities_cost_per_yr'] },
    // The installed cost per unit of each owned asset class — the base ownership carrying is
    // charged on (the solver multiplies by the capacity it already has).
    capital_cost_per_unit:       { from: ['harvest_storage_cost_per_m3', 'ambient_storage_cost_per_m3',
                                          'water_tank_cost_per_L', 'irrigation_cost_per_acre',
                                          'equip_storage_cost_per_m3', 'fuel_storage_cost_per_L'] },
    // The What-If "Plan optimal labor" tool (buildLaborFlexParams) — never the main solve.
    labor_flex_enabled:          { sentBy: 'what-if', from: [] },
    hire_enabled:                { sentBy: 'what-if', from: ['labor_flex_hire'] },
    max_hire_hrs_per_week:       { sentBy: 'what-if', from: ['max_hire_hrs_per_week'] },
    hire_wage_markup:            { sentBy: 'what-if', from: ['hire_wage_markup_pct'] },
    hired_wage_per_hr:           { sentBy: 'what-if', from: ['hired_wage_per_hr'] },
    overtime_enabled:            { sentBy: 'what-if', from: ['labor_flex_overtime'] },
    overtime_rate_multiplier:    { sentBy: 'what-if', from: ['overtime_rate_multiplier'] },
    max_overtime_hrs_per_week:   { sentBy: 'what-if', from: ['max_overtime_hrs_per_week'] },
    rainfall_weekly_multipliers: { sentBy: 'monte-carlo', from: [] },
    // Read by the adapter, sent by nothing. Each is a decision, not an oversight — say which.
    operating_weeks:             { unsent: 'deprecated; the solver ignores it (cost-accounting basis)' },
    storage_loss_frac_per_week:  { unsent: 'solver supports in-store shrink; no input yet — DECISIONS GROUP E3' },
    city_water_fixed_fee_per_week: { unsent: 'solver + P&L carry a city-water standing charge; no input yet (found by E5b)' },
  };

  /** { id: entry[part] } for every entry in `section` that declares `part`, in registry order —
   *  the ONE projection every view uses (units.js, BENCHMARK_DEFAULTS, the Worker). */
  function view(section, part) {
    var src = section === 'form' ? form : crop, out = {};
    Object.keys(src).forEach(function (id) { if (src[id][part]) out[id] = src[id][part]; });
    return out;
  }

  root.FARM_FIELDS = { form: form, crop: crop, payload: payload, view: view };
})(typeof globalThis !== 'undefined' ? globalThis : this);
