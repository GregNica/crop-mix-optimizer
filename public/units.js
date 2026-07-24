/* units.js — canonical ⇄ display unit conversion + declarative field registry.
 *
 * Foundation for the app-wide metric ⇄ US-customary toggle (see SPEC_units.md).
 * ROLLOUT STEP 1: this defines the module, the field registry, and a boot-time
 * self-check. NOTHING here is wired into the payload builder, the form, or the
 * toggle yet (steps 2+). Loading this file must not change any behavior.
 *
 * Core invariant: the MILP solver ALWAYS runs in CANONICAL units. Canonical is
 * simply the solver's existing unit per dimension (acre, lb, L, m³, m², mm) — an
 * internal choice, so cross-dimension "consistency" is irrelevant; only the
 * conversion factors need to be right. The UI holds DISPLAY values and converts
 * to canonical at the payload boundary (a later step).
 */
(function (root) {
  'use strict';

  // Base physical dimensions.
  //   perDisplay = how many CANONICAL units are in ONE display unit of that system.
  //   The canonical system's perDisplay is exactly 1 (it IS the canonical unit).
  var DIMENSIONS = {
    // area of land (fields) — canonical acre
    area_land:  { canonical: 'acre', us: { unit: 'acre', perDisplay: 1 },         metric: { unit: 'ha', perDisplay: 2.47105 } },
    // area of a floor/roof (catchment, sheds) — canonical m²
    area_floor: { canonical: 'm²',   us: { unit: 'ft²',  perDisplay: 0.09290304 },metric: { unit: 'm²', perDisplay: 1 } },
    // produce mass — canonical lb
    mass:       { canonical: 'lb',   us: { unit: 'lb',   perDisplay: 1 },         metric: { unit: 'kg', perDisplay: 2.2046226 } },
    // liquid volume (water, fuel) — canonical liter
    vol_liquid: { canonical: 'L',    us: { unit: 'gal',  perDisplay: 3.7854118 }, metric: { unit: 'L',  perDisplay: 1 } },
    // bulk/storage volume (produce cold storage) — canonical m³
    vol_bulk:   { canonical: 'm³',   us: { unit: 'ft³',  perDisplay: 0.02831685 },metric: { unit: 'm³', perDisplay: 1 } },
    // rainfall / length — canonical mm
    length:     { canonical: 'mm',   us: { unit: 'in',   perDisplay: 25.4 },      metric: { unit: 'mm', perDisplay: 1 } }
  };

  var SYSTEMS = ['us', 'metric'];

  function factor(measure, system) {
    var d = DIMENSIONS[measure];
    if (!d) throw new Error('units: unknown dimension "' + measure + '"');
    if (!d[system]) throw new Error('units: unknown system "' + system + '"');
    return d[system].perDisplay;
  }

  /* A registry field is one of:
   *   - a QUANTITY of a dimension            (e.g. total_land = acres)          → { measure }
   *   - a PER-unit price/rate of a dimension (e.g. $/acre, $/m³/wk)             → { measure, inverse:true }
   *   - a COMPOUND quantity num/den          (e.g. yield lb/acre = mass/area)   → { num, den }
   * `inverse` flips the factor because $/acre → $/ha multiplies (fewer, bigger
   * units) while a quantity of acres → ha divides. Time (/wk) is unitless, so a
   * rate converts exactly like a price.
   */
  function toDisplay(canonicalValue, spec, system) {
    if (canonicalValue == null || isNaN(canonicalValue)) return canonicalValue;
    if (system === 'canonical') return canonicalValue;   // identity: DOM already holds canonical
    if (spec.num && spec.den) {
      // compound quantity: display = canonical × (den.perDisplay / num.perDisplay)
      return canonicalValue * (factor(spec.den, system) / factor(spec.num, system));
    }
    var f = factor(spec.measure, system);
    return spec.inverse ? canonicalValue * f : canonicalValue / f;
  }

  function toCanonical(displayValue, spec, system) {
    if (displayValue == null || isNaN(displayValue)) return displayValue;
    if (system === 'canonical') return displayValue;   // identity: value already canonical
    if (spec.num && spec.den) {
      return displayValue / (factor(spec.den, system) / factor(spec.num, system));
    }
    var f = factor(spec.measure, system);
    return spec.inverse ? displayValue / f : displayValue * f;
  }

  // Human-readable unit string for a field's spec in a system (for labels/tooltips).
  function unitLabel(spec, system) {
    function u(m) { return system === 'canonical' ? DIMENSIONS[m].canonical : DIMENSIONS[m][system].unit; }
    if (spec.num && spec.den) return u(spec.num) + '/' + u(spec.den);
    if (spec.inverse)        return '$/' + u(spec.measure) + (spec.perWeek ? '/wk' : '');
    return u(spec.measure) + (spec.perWeek ? '/wk' : '');
  }

  /* Declarative field registry — the E5 substrate.
   * Keys are DOM input ids. Only UNIT-BEARING fields appear here; unitless fields
   * (counts, %, years, $ currency, $/wk flat) are intentionally absent and never
   * converted (currency is out of scope — SPEC_units §1/§9).
   */
  var FIELD_REGISTRY = {
    // --- area (land) ---
    total_land:                 { measure: 'area_land' },
    irrigation_cost_per_acre:   { measure: 'area_land', inverse: true },   // $/acre (capital)
    // --- area (floor) ---
    catchment_surface_area_m2:  { measure: 'area_floor' },
    // --- bulk / storage volume ---
    equip_storage:              { measure: 'vol_bulk' },
    harvest_storage_cap:        { measure: 'vol_bulk' },
    equip_storage_cost_per_m3:  { measure: 'vol_bulk', inverse: true },    // $/m³ (capital)
    harvest_storage_cost_per_m3:{ measure: 'vol_bulk', inverse: true },    // $/m³ (capital)
    rate_harvest_storage:       { measure: 'vol_bulk', inverse: true, perWeek: true }, // hidden derived rate
    // --- liquid volume ---
    fuel_storage:               { measure: 'vol_liquid' },
    water_tank_capacity_L:      { measure: 'vol_liquid' },
    water_storage_capacity:     { measure: 'vol_liquid' },
    well_weekly_cap_L:          { measure: 'vol_liquid', perWeek: true },  // L/wk quantity
    city_water_cost_per_L:      { measure: 'vol_liquid', inverse: true },  // $/L
    water_tank_cost_per_L:      { measure: 'vol_liquid', inverse: true },  // $/L (capital)
    fuel_storage_cost_per_L:    { measure: 'vol_liquid', inverse: true },  // $/L (capital)
    cost_fuel_per_L:            { measure: 'vol_liquid', inverse: true },  // $/L (metered)
    rate_water_storage:         { measure: 'vol_liquid', inverse: true, perWeek: true },
    // --- mass ---
    cost_fert_per_lb:           { measure: 'mass', inverse: true }         // $/lb (metered)
  };

  /* Dynamic per-crop / per-channel fields, keyed by their data-f attribute (they
   * render inside crop/channel rows, not by id). Wired in a later step; declared
   * now so the registry is authoritative. */
  var DATA_F_REGISTRY = {
    yield_per_acre:              { num: 'mass', den: 'area_land' },  // lb/acre
    ch_price:                    { measure: 'mass', inverse: true }, // $/lb
    ch_pkg:                      { measure: 'mass', inverse: true }, // $/lb packaging
    ch_demand_value:            { measure: 'mass' },                 // lbs (a capacity quantity)
    lbs_per_tote:               { measure: 'mass' },                 // lbs
    min_acreage_if_planted:     { measure: 'area_land' },            // acres
    seed_transplant_cost_per_acre: { measure: 'area_land', inverse: true } // $/acre
    // DEFERRED (per-acre resource rates behind pd-phase-detail): water/fuel _plant/grow/harv
    // are L/acre (vol_liquid/area_land), fert_* are lb/acre (mass/area_land), labor_* are
    // hrs/acre (a non-currency numerator). These need a per-area rate form and are wired with
    // the crop panel pass, not step 1.
  };

  /* Boot self-check (dev only): every registry id must exist in the DOM, and no
   * unit-bearing-looking numeric input should be missing from the registry.
   * Logs to console; never throws in production. Call after DOMContentLoaded. */
  function assertFieldRegistry(opts) {
    if (typeof document === 'undefined') return { ok: true, missing: [], unregistered: [] };
    opts = opts || {};
    var missing = [];
    Object.keys(FIELD_REGISTRY).forEach(function (id) {
      if (!document.getElementById(id)) missing.push(id);
    });
    // Heuristic: numeric inputs whose label/id implies a physical unit but aren't registered.
    var unregistered = [];
    var UNIT_HINT = /\b(acre|acres|ha|hectare|lb|lbs|kg|gal|gallon|liter|litre|\/l\b|m³|m3|ft³|ft3|m²|m2|ft²|ft2|\/acre|\/m3|\/m³|\/lb)\b/i;
    Array.prototype.forEach.call(document.querySelectorAll('input[type="number"][id]'), function (el) {
      var id = el.id;
      if (FIELD_REGISTRY[id]) return;
      var grp = el.closest('.form-group');
      var text = (grp ? grp.textContent : '') + ' ' + id;
      if (UNIT_HINT.test(text) && !/\$\/wk|per week|\byears?\b|%/.test(text)) unregistered.push(id);
    });
    if (missing.length) console.warn('[units] registry ids missing from DOM (form drift):', missing);
    // The unregistered-field heuristic stays opt-in (?units-audit) until the dynamic
    // crop/channel registry is complete — otherwise deferred per-acre fields false-positive.
    if (opts.audit && unregistered.length) console.warn('[units] unit-looking inputs NOT in registry:', unregistered);
    if (opts.verbose && !missing.length) console.log('[units] field registry ✓ (' + Object.keys(FIELD_REGISTRY).length + ' fields)');
    return { ok: !missing.length, missing: missing, unregistered: unregistered };
  }

  var API = {
    DIMENSIONS: DIMENSIONS,
    SYSTEMS: SYSTEMS,
    FIELD_REGISTRY: FIELD_REGISTRY,
    DATA_F_REGISTRY: DATA_F_REGISTRY,
    factor: factor,
    toDisplay: toDisplay,
    toCanonical: toCanonical,
    unitLabel: unitLabel,
    assertFieldRegistry: assertFieldRegistry
  };

  if (root) root.UNITS = API;                       // browser: window.UNITS
  if (typeof module !== 'undefined' && module.exports) module.exports = API;  // node: tests

  // Boot self-check: verify the registry hasn't drifted from the DOM (quiet unless it has).
  // The heavier unregistered-field audit is opt-in via ?units-audit. Neither changes behavior.
  if (typeof document !== 'undefined' && typeof window !== 'undefined') {
    var run = function () {
      var audit = /[?&]units-audit\b/.test(window.location ? window.location.search : '');
      assertFieldRegistry({ audit: audit, verbose: audit });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
    else run();
  }
})(typeof window !== 'undefined' ? window : null);
