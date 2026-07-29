# Phase 4 Monte Carlo Validation Runbook

This runbook verifies that Phase 4 Monte Carlo is working end-to-end beyond unit tests.

## Files In This Pack

- `validation/phase4_mc_pack/mc_uncertainty_low_variance.xlsx`
- `validation/phase4_mc_pack/mc_uncertainty_spinach_fm_shock.xlsx`
- `validation/phase4_mc_pack/rainfall_history_stable.xlsx`
- `validation/phase4_mc_pack/rainfall_history_volatile.xlsx`

## Pre-Checks

1. Open the app and run one deterministic baseline solve.
2. Open Advanced and ensure Monte Carlo controls are visible.
3. Set simulation count to `100`.

## Test A: Seed Determinism

Goal: prove reproducibility.

1. Set seed to `12345`.
2. Run Monte Carlo with current settings.
3. Record mean, p10, p50, p90 profit.
4. Run again with the same seed and settings.
5. Compare values.

Expected:
- Metrics are identical (or effectively identical if rounded in UI).

Fail if:
- Any output changes with same seed and unchanged inputs.

## Test B: Seed Sensitivity

Goal: prove seed actually controls random sampling.

1. Keep all inputs fixed.
2. Run with seed `12345`.
3. Run with seed `98765`.

Expected:
- Distribution shifts slightly (not identical), while still plausible.

Fail if:
- Outputs are exactly identical across different seeds.

## Test C: Low-Variance Import (Tight Distribution)

Goal: prove import wiring and narrow spread behavior.

1. Upload `mc_uncertainty_low_variance.xlsx` in the MC uncertainty uploader.
2. Upload `rainfall_history_stable.xlsx` in Water section rainfall uploader.
3. Set seed to `12345`; run Monte Carlo.

Expected:
- Profit distribution is relatively tight (smaller p90-p10 gap).
- Crop Stability shows more "Stable" labels than fragile.
- Sensitivity chart shows no extreme outlier driver.

Fail if:
- Import reports success but distribution remains obviously noisy/wide.
- Crop/channel names in workbook are ignored without warnings.

## Test D: Shock Import (Clear Driver Emerges)

Goal: prove uncertainty influences ranking and sensitivity.

1. Upload `mc_uncertainty_spinach_fm_shock.xlsx`.
2. Keep rainfall on `rainfall_history_stable.xlsx`.
3. Set seed to `12345`; run Monte Carlo.

Expected:
- Distribution widens vs Test C.
- Sensitivity top drivers include Spinach/Farmers Market price/demand related multipliers.
- Crop stability may downgrade some crops from Stable to Conditional/Fragile.

Fail if:
- Sensitivity ranking does not materially change from low-variance setup.
- Shocked crop/channel does not appear in top drivers.

## Test E: Rainfall Effect Isolation

Goal: verify rainfall history affects MC outcomes.

1. Keep uncertainty workbook from Test C (low variance) loaded.
2. Run once with `rainfall_history_stable.xlsx`.
3. Run once with `rainfall_history_volatile.xlsx`.
4. Use the same seed and same simulation count for both runs.

Expected:
- Volatile rainfall case shows wider distribution and/or shifted downside tail.
- Sensitivity should give rainfall-related factors more influence under volatile rainfall.

Fail if:
- Stable and volatile rainfall runs are effectively identical.

## Test F: Cancel + UI Responsiveness

Goal: verify runtime controls.

1. Set simulation count to `500`.
2. Start Monte Carlo.
3. Click Cancel mid-run.

Expected:
- Run stops promptly.
- UI remains responsive.
- No stale loading state left behind.

Fail if:
- Cancel does not stop run.
- UI hangs or requires full page reload.

## Optional Evidence Capture

Capture screenshots of:

1. Profit Distribution (low variance vs shock).
2. Crop Stability tab (classification changes).
3. Sensitivity tab (top driver changes).

This gives quick change evidence for release notes.

## Practical Acceptance Gate

Treat Phase 4 as validated if all are true:

1. Deterministic repeatability with fixed seed.
2. Different-seed non-identity.
3. Import files alter MC outputs in expected direction.
4. Rainfall volatility changes outcomes.
5. Cancel and progress behavior are usable.
