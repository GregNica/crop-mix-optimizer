/* units.js — canonical ⇄ display unit conversion.
 *
 * The engine behind the app-wide metric ⇄ US-customary toggle (see SPEC_units.md). Its
 * field registries are VIEWS over public/fields.js (E5b), which must load first.
 *
 * Core invariant: the MILP solver ALWAYS runs in CANONICAL units. Canonical is
 * simply the solver's existing unit per dimension (acre, lb, L, m³, m², mm) — an
 * internal choice, so cross-dimension "consistency" is irrelevant; only the
 * conversion factors need to be right. The UI holds DISPLAY values and converts
 * to canonical at the payload boundary.
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
    length:     { canonical: 'mm',   us: { unit: 'in',   perDisplay: 25.4 },      metric: { unit: 'mm', perDisplay: 1 } },
    // labor time — same in both systems; only its per-area denominator converts (hr/acre ⇄ hr/ha)
    time:       { canonical: 'hr',   us: { unit: 'hr',   perDisplay: 1 },         metric: { unit: 'hr', perDisplay: 1 } }
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
    if (spec.num && spec.den) return u(spec.num) + '/' + u(spec.den) + (spec.perWeek ? '/wk' : '');
    if (spec.inverse)        return '$/' + u(spec.measure) + (spec.perWeek ? '/wk' : '');
    return u(spec.measure) + (spec.perWeek ? '/wk' : '');
  }

  /* Declarative field registry — VIEWS over public/fields.js (E5b), which must load first.
   * Keys are DOM input ids (FIELD_REGISTRY) and data-f attributes (DATA_F_REGISTRY). Only
   * UNIT-BEARING fields appear; unitless fields (counts, %, years, $ currency, $/wk flat) are
   * intentionally absent and never converted (currency is out of scope — SPEC_units §1/§9).
   * The specs themselves, with their comments, live in fields.js under each field's `units`.
   */
  var FF = globalThis.FARM_FIELDS;   // fields.js attaches here, in the page and every harness
  // Loud, not silent: without the registry no field converts and the page LOOKS fine in US mode.
  if (!FF) throw new Error('units.js: FARM_FIELDS is missing — load fields.js before units.js');
  var FIELD_REGISTRY  = FF.view('form', 'units');
  var DATA_F_REGISTRY = FF.view('crop', 'units');

  /* Opt-in audit (?units-audit): numeric inputs whose label LOOKS unit-bearing but carry no
   * `units` spec in fields.js, and rendered data-f keys the registry does not know. The strict
   * both-directions checks (every rendered input registered, every entry rendered) moved to CI in
   * E5b — tests/field_registry_client.cjs — so nothing runs on a normal page load any more. */
  function assertFieldRegistry() {
    if (typeof document === 'undefined') return { unregistered: [], unknownDataF: [] };
    var unregistered = [];
    var UNIT_HINT = /\b(acre|acres|ha|hectare|lb|lbs|kg|gal|gallon|liter|litre|\/l\b|m³|m3|ft³|ft3|m²|m2|ft²|ft2|\/acre|\/m3|\/m³|\/lb)\b/i;
    Array.prototype.forEach.call(document.querySelectorAll('input[type="number"][id]'), function (el) {
      if (FIELD_REGISTRY[el.id]) return;
      var grp = el.closest('.form-group');
      var text = (grp ? grp.textContent : '') + ' ' + el.id;
      if (UNIT_HINT.test(text) && !/\$\/wk|per week|\byears?\b|%/.test(text)) unregistered.push(el.id);
    });
    var unknownF = [];
    Array.prototype.forEach.call(document.querySelectorAll('[data-f]'), function (el) {
      var f = el.getAttribute('data-f');
      if (!DATA_F_REGISTRY[f] && unknownF.indexOf(f) < 0) unknownF.push(f);
    });
    if (unregistered.length) console.warn('[units] unit-looking inputs NOT in registry:', unregistered);
    if (unknownF.length) console.warn('[units] rendered data-f keys with no units spec:', unknownF);
    return { unregistered: unregistered, unknownDataF: unknownF };
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

  // Opt-in audit only (?units-audit). Deferred past the app's own DOMContentLoaded handler, which
  // builds the crop/channel rows the data-f half reads.
  if (typeof document !== 'undefined' && typeof window !== 'undefined' &&
      /[?&]units-audit\b/.test(window.location ? window.location.search : '')) {
    var runDeferred = function () { setTimeout(assertFieldRegistry, 0); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', runDeferred);
    else runDeferred();
  }
})(typeof window !== 'undefined' ? window : null);
