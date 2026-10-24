/**
 * Re-capture the golden payload's crops from the SHIPPED demo.
 *
 * The golden payload is a frozen snapshot of what the browser sends. Nothing tied it to the live
 * page, so once the demo became derived from CROP_TEMPLATES, a template edit could silently make
 * the golden test pin a farm that no longer ships — green while testing the wrong thing.
 *
 * Run after any change to CROP_TEMPLATES / DEMO_OVERRIDES / the storage params, in the SAME
 * commit as the golden P&L re-pin (see money-path-guards).
 *
 *   node scripts/capture_golden_payload.cjs [--check]
 *
 * --check exits 1 on drift without writing, for CI.
 */
const fs = require('fs');
const path = require('path');
const { bootApp } = require('../tests/jsdom_app.cjs');

const ROOT = path.join(__dirname, '..');
const PAYLOAD = path.join(ROOT, 'tests/golden/default_farm_payload.json');
const CHECK = process.argv.includes('--check');

// Only the keys this capture owns. The rest of the payload (labor, channels, cash, rates) was
// captured from a real browser session and is not regenerated here — narrow, so a bug in this
// script cannot quietly rewrite the whole farm.
// storage_loss_frac_per_week is deliberately NOT here: runOptimizer does not emit it, so
// capturing it would put a key in the golden payload that the browser never sends — the exact
// staleness this script exists to prevent.
const OWNED = ['crops', 'ambient_storage_cap', 'rate_ambient_storage',
               'harvest_storage_cap', 'rate_harvest_storage', 'well_weekly_cap_L',
               'climate_zone',
               // R7/W10 — every solve sends them, so the golden farm must too (/code-review max #12),
               // or the Batch 3 re-pin that switches their defaults on moves nothing here.
               'rented_acres', 'cash_rent_per_acre_yr', 'ownership_carrying_rate', 'capital_cost_per_unit',
               'insurance_premium_per_yr', 'insurance_payment_week', 'utilities_cost_per_yr',
               // L.5 — the split payroll load (replaces payroll_load_pct, dropped below).
               'fica_pct', 'straight_time_load_pct',
               // Batch L — the roster rows now carry max_ot_hrs, hire_more/max_more, admin_pct
               // and task tags; pin the roster the form actually sends, not a July capture.
               'employees', 'overtime_rate_multiplier'];

bootApp().then(({ window: w }) => {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD, 'utf8'));
  // Read straight off the app's own payload builder (buildSolveParams, E5b) — not a mirror of
  // pieces of it. This used to re-call rateFromCapital with hand-copied arguments, and broke the
  // moment that function's signature changed (R7).
  const built = w.eval('buildSolveParams()');
  const fresh = Object.fromEntries(OWNED.map(k => [k, built[k]]));

  const before = JSON.stringify(OWNED.map(k => payload[k]));
  OWNED.forEach(k => { payload[k] = fresh[k]; });
  delete payload.payroll_load_pct;   // retired by L.5; the split keys above carry it
  const after = JSON.stringify(OWNED.map(k => payload[k]));

  if (before === after) { console.log('golden payload: already current'); process.exit(0); }
  if (CHECK) {
    console.error('golden payload is STALE — it pins a farm the app no longer ships.');
    console.error('Run: node scripts/capture_golden_payload.cjs, and re-pin the P&L in the same commit.');
    process.exit(1);
  }
  fs.writeFileSync(PAYLOAD, JSON.stringify(payload, null, 1) + '\n');
  const g = fresh.crops.find(c => c.name === 'Garlic') || {};
  console.log(`golden payload re-captured: ${fresh.crops.length} crops, `
            + `barn ${fresh.ambient_storage_cap} m3, garlic spread=${g.sales_spread_weeks} `
            + `cold=${g.cold_storage}`);
  process.exit(0);
}).catch(e => { console.error('FATAL:', e.message); process.exit(1); });
