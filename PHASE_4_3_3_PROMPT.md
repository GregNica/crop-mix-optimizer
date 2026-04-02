# Phase 4.3.3 Prompt — Progressive Disclosure Refinement + Depreciation Model

**Implement Phase 4.3.3 immediately after Phase 4.3.2 completion.**

## User Feedback (11 Items)

Your task is to address all 11 feedback items from the Phase 4.3.2 user test. These are UX/feature refinements that improve usability and correct model parameter handling.

---

## 1. Toggle Defaults — All Unchecked by Default

**Current State**: All progressive disclosure checkboxes (`pd-cash`, `pd-machinery`, `pd-harvest-storage`, etc.) are checked by default.

**Required**: All toggles should be **unchecked** by default, with fields initially hidden.

**Changes**:
- Remove `checked` attribute from these elements:
  - `#pd-cash`
  - `#pd-machinery`
  - `#pd-harvest-storage`
  - `#pd-irrig-fert`
  - `#pd-machinery-rates`
  - `#pd-ch-vardetail` (already unchecked — keep as is)
  - `#pd-phase-detail` (already unchecked — keep as is)

**Test**: T201 — All toggles unchecked on fresh load; fields hidden until toggled ON

---

## 2. Harvest Storage Move + Grouping (Item 1)

**Current State**: "Harvest Storage (m³)" is a standalone field in Farm Infrastructure.

**Required**: Move to a toggle-controlled group with the question: "Account for harvest storage and refrigeration costs?"

**Details**:
- Move the existing `#harvest_storage_cap` input to be revealed by `#pd-harvest-storage` toggle
- Add a new `#depreciation_harvest_years` field (default: 25 years)
- Add a new `#harvest_storage_cost_per_m3` field ($/m³ capital cost, not $/m³/week)
- Update tooltip to explain depreciation approach (capital cost ÷ years ÷ 52 weeks = weekly cost)
- Keep the toggle in the "Fixed Cost Rates" section
- Ensure when toggle is OFF, these fields are omitted from the params JSON sent to solver

**Test**: T202 — Toggle controls field visibility; params JSON omits these fields when toggle is OFF

---

## 3. Water Tank Depreciation Model (Item 2)

**Current State**: Water tank uses a simple `rate_water_storage` ($/L/week) in Fixed Cost Rates section.

**Required**: Move to Water section; change to depreciation model (capital cost + depreciation years).

**Changes**:
- **In Water Section**, add a new card or group:
  - `#water_tank_capacity_L` (liters, default: 50,000)
  - `#water_tank_cost_per_L` ($/L capital cost, default: ~$2)
  - `#depreciation_water_years` (years, default: 20)
- Display formula helper: "Weekly cost = (Capacity × Cost/L) ÷ (Depreciation Years × 52)"
- Update tooltip to explain: typical tank sizes, depreciation rationale (20-year lifespan for concrete/poly), note about catchment details in this section
- **Solver**: Calculate weekly cost as `(water_tank_capacity_L * water_tank_cost_per_L) / (depreciation_water_years * 52)` and include in `fixed_cost`
- Keep old `rate_water_storage` field in Farm Basics for backward compat (but deprioritize or hide it)

**Test**: T203 — Water tank depreciation calculation is correct; weekly cost = (10,000L × $2/L) / (20 × 52) ≈ $19.23/week

---

## 4. Irrigation, Equipment Storage, Fuel Storage Depreciation (Item 3)

**Current State**: All use simple $/unit/week rates.

**Required**: Change to capital cost + depreciation model for all four storage types.

**Changes**:
- **Irrigation** (Water section):
  - `#irrigation_cost_per_acre` ($/acre capital cost, default: ~$350)
  - `#depreciation_irrigation_years` (years, default: 18)
  - Weekly cost = (total_land × cost_per_acre) / (depreciation_years × 52)

- **Equipment Storage** (Farm Basics, machinery toggle):
  - Rename `#equip_storage` label (if needed for clarity)
  - `#equip_storage_cost_per_m3` ($/m³ capital cost, default: ~$50)
  - `#depreciation_equip_years` (years, default: 30)
  - Weekly cost = (equip_storage × cost_per_m3) / (depreciation_years × 52)

- **Fuel Storage** (Farm Basics, machinery toggle):
  - Rename `#fuel_storage` label (if needed for clarity)
  - `#fuel_storage_cost_per_L` ($/L capital cost, default: ~$0.50)
  - `#depreciation_fuel_years` (years, default: 12)
  - Weekly cost = (fuel_storage × cost_per_L) / (depreciation_years × 52)

- **Solver**: Update `fixed_cost` formula to use all four depreciation calculations:
  ```python
  harvest_weekly = (harvest_storage_cost_per_m3 * harvest_storage_cap) / (depreciation_harvest_years * 52)
  irrigation_weekly = (irrigation_cost_per_acre * total_land) / (depreciation_irrigation_years * 52)
  equip_weekly = (equip_storage_cost_per_m3 * equip_storage) / (depreciation_equip_years * 52)
  fuel_weekly = (fuel_storage_cost_per_L * fuel_storage) / (depreciation_fuel_years * 52)
  water_weekly = (water_tank_cost_per_L * water_tank_capacity_L) / (depreciation_water_years * 52)
  
  fixed_cost = (harvest_weekly + irrigation_weekly + equip_weekly + fuel_weekly + water_weekly) * operating_weeks + ...existing terms...
  ```

**Test**: T204 — All four storage types depreciate correctly; sum matches expected fixed cost

---

## 5. Optimize Button Relocation to Top (Item 5)

**Current State**: `.section-optimize-footer` button appears at the bottom of each section.

**Required**: Move to the top, just below the section stepper/nav area.

**Changes**:
- Move `.section-optimize-footer` div from end of `#section-cards-grid` to beginning (after section nav/stepper)
- Keep lock-state gating behavior identical
- Optionally keep a secondary (grayed-out) footer at bottom for confirmation only

**Test**: T205 — Optimize button visible at top of section when scrolling in

---

## 6. Sales Channel Field Hiding (Item 6)

**Current State**: `#pd-ch-vardetail` toggle is unchecked by default (correct), but the channel cost fields are still visible.

**Required**: Hide the channel variable/fixed cost fields when toggle is OFF.

**Changes**:
- Find the fields revealed by `#pd-ch-vardetail` (packaging_cost, fixed_channel_cost, etc.)
- Wrap them in a div with id `pd-ch-vardetail-fields` and class `pd-revealed`
- Ensure `togglePD('pd-ch-vardetail', 'pd-ch-vardetail-fields', ...)` is called correctly
- Add `pd-hidden` class to these fields by default
- Test that toggling reveals/hides fields AND omits them from params when OFF

**Test**: T206 — Channel cost fields hidden by default; toggling ON/OFF shows/hides and updates params

---

## 7. Crop Section: Two Toggle Questions (Item 7)

**Current State**: One toggle `#pd-phase-detail` for phase-specific resource usage.

**Required**: Add a second toggle for crop variable costs; both toggles unchecked by default.

**Changes**:
- **Toggle 1: Crop Variable Costs** (unchecked by default)
  - Question: "Add crop specific variable costs (fertilizer, pesticide/herbicide, fuel)?"
  - `#pd-crop-var-costs` checkbox
  - Reveals: per-crop fields for `fert_lb_per_acre`, `pesticide_cost_per_acre`, `fuel_L_per_acre`
  - Helper text: "Crop-specific variable costs are set to defaults. Enable to customize fertilizer, pesticide, and fuel usage per crop."

- **Toggle 2: Phase-Specific Resource Usage** (unchecked by default)
  - Question: "Add phase specific resource usage (planting / growing / harvesting splits)?"
  - `#pd-phase-detail` checkbox (renamed/updated)
  - Reveals: phase splits for labor, water, fertilizer, fuel across planting/growing/harvesting
  - Helper text: "Resource usage is split across growing phases. Enable to customize labor, water, fertilizer, and fuel separately for each phase."
  - **Always include**: labor and water (at minimum one parameter set for each)

- **Solver**: Only include optional crop variable costs in params if toggle is ON; only include phase-specific splits if toggle is ON

**Test**: T207a — Both toggles unchecked by default; fields hidden  
**Test**: T207b — Toggling each reveals correct sub-fields  
**Test**: T207c — Labor and water always present; others only if toggled ON

---

## 8. Monte Carlo: Historical Yield/Price/Demand Naming (Item 8)

**Current State**: Section labeled "Monte Carlo: Yield uncertainty"

**Required**: Rename to "Historical crop data to account for uncertainty"

**Changes**:
- Update section text in Crops area where MC inputs are shown
- Reflects broader scope (yield, price, demand all have uncertainty)
- More user-friendly than technical "yield uncertainty"

**Test**: T208 — MC section displays new name

---

## 9. Uncertainty Pills Next to Demand/Price/Yield (Item 9)

**Current State**: No indication users can add MC data for specific crops.

**Required**: Add small pill/badge next to demand, price, and yield fields suggesting MC upload.

**Changes**:
- Add small pill/indicator (e.g., "📊 Add to Historical data" or similar wording)
- Show near demand, price, and yield inputs in crop form
- Clicking pill or link opens/highlights MC upload section
- Non-intrusive; optional feature suggestion

**Test**: T209 — Pills appear next to demand/price/yield; clicking opens MC upload

---

## 10. Parameter Omission When Toggles are OFF (Item 10)

**Critical**: Defaults must be actually omitted from solver params when toggles are OFF, not just hidden.

**Current Issue**: With benchmark mode pre-filling defaults, hidden fields might still be included in solver params JSON, causing model to still charge costs.

**Required**:
- In `run_from_js()`, use conditional spreads to omit fields based on toggle state:
  ```javascript
  const params = {
    // Always required
    total_land: ...,
    operating_weeks: ...,
    crops: ...,
    channels: ...,
    
    // Conditional: only if toggle is ON
    ...(document.getElementById('pd-cash').checked && {
      opening_cash: ...,
      credit_line: ...,
    }),
    
    ...(document.getElementById('pd-machinery').checked && {
      equip_storage: ...,
      fuel_storage: ...,
      equip_storage_cost_per_m3: ...,
      depreciation_equip_years: ...,
      fuel_storage_cost_per_L: ...,
      depreciation_fuel_years: ...,
    }),
    
    // ...etc for all other toggles
  };
  ```

- Verify params JSON does NOT include omitted fields when toggles are OFF
- Solver must accept missing optional parameters gracefully (with defaults where applicable)

**Test**: T210a — With pd-cash OFF, opening_cash/credit_line excluded from params  
**Test**: T210b — With pd-machinery OFF, machinery params excluded  
**Test**: T210c — Solver runs successfully and costs are lower when parameters omitted

---

## 11. Comprehensive Testing (Item 11)

**Test all combinations**: toggles ON/OFF/mixed, benchmark vs manual mode, existing solve vs new depreciation model.

**Test Matrix**:
- Baseline (all toggles ON): profit matches Phase 4.3.2 within $0.01
- All toggles OFF: solver runs; profit is lower (fewer constraints/costs)
- Mixed toggles: specific toggles ON/OFF in various combinations
- Depreciation years at edge cases (1 year, 100 years): should not crash
- Saved inputs from old phase load correctly in new phase

**Regression Tests**:
- Deterministic: same inputs → same output twice
- Existing exports work
- What-If and MC flows unchanged

---

## Acceptance Criteria

1. ✓ All toggles default to unchecked; hidden fields omitted from params
2. ✓ Harvest Storage moved and uses depreciation model
3. ✓ Water Tank moved to Water section; uses depreciation model
4. ✓ Irrigation, Equipment Storage, Fuel Storage all use depreciation model
5. ✓ Optimize button appears at top of section
6. ✓ Sales Channel fields hidden when toggle OFF
7. ✓ Crop section has two independent toggles (variable costs + phase splits)
8. ✓ MC section renamed to "Historical crop data..."
9. ✓ Uncertainty pills appear next to demand/price/yield
10. ✓ Parameters omitted from solver when toggles OFF (not just hidden)
11. ✓ All test combinations pass; optimizer works with any toggle state
12. ✓ Baseline solve matches Phase 4.3.2 profit (within $0.01)
13. ✓ No regressions in existing test suite

---

## Implementation Sequence (Recommended)

1. **Phase 4.3.3a**: Toggle defaults → unchecked (foundation)
2. **Phase 4.3.3i**: Parameter omission logic (critical for correctness)
3. **Phase 4.3.3b**: Harvest Storage move + depreciation
4. **Phase 4.3.3c**: Water depreciation model + solver update
5. **Phase 4.3.3d**: Irrigation/Equipment/Fuel depreciation
6. **Phase 4.3.3e**: Optimize button relocation
7. **Phase 4.3.3f**: Sales Channel field hiding
8. **Phase 4.3.3g**: Crop dual toggles
9. **Phase 4.3.3h**: MC naming + pills
10. **Phase 4.3.3j**: Comprehensive testing (all combinations, regressions)

---

## Critical Implementation Notes

### Solver Parameter Changes
Add these parameters to `solve_farm_v2()`:
- `depreciation_harvest_years`, `harvest_storage_cost_per_m3`
- `depreciation_water_years`, `water_tank_cost_per_L`, `water_tank_capacity_L`
- `depreciation_irrigation_years`, `irrigation_cost_per_acre`
- `depreciation_equip_years`, `equip_storage_cost_per_m3`
- `depreciation_fuel_years`, `fuel_storage_cost_per_L`

### Backward Compatibility
- Keep old `rate_*` parameters in solver signature for backward compat
- Old saved inputs should still load (or provide migration path)
- Default depreciation years should match typical asset lifespans

### Testing Strategy
- **Unit**: Each toggle ON/OFF individually
- **Integration**: Combinations (all ON, all OFF, mixed)
- **Regression**: Baseline solve, deterministic, exports
- **Edge Cases**: Depreciation years at extremes (1, 100), old saved inputs

---

## At the End, Report

1. Files changed (especially index.html sections, solver, JS param collection)
2. All 11 feedback items addressed (with confirmation for each)
3. New depreciation fields added (with defaults and tooltips)
4. Parameter omission logic implemented (conditional spreads in run_from_js)
5. Test results for all 11 items (T201–T210c + regression)
6. Baseline solve profit (should match Phase 4.3.2 within $0.01)
7. Any deferred items or edge cases found

---

## Files to Edit

- **index.html** (primary): Form fields, toggles, Optimize button relocation, parameter collection in `run_from_js()`
- **farm_v2/solver.py** (or equivalent): Add depreciation parameters; update `fixed_cost` formula; handle optional parameters
- **Possibly**: CLAUDE_PROMPT_PACK.md Phase 4.3.3 section (to document completion)

---

## Do Not

- Modify solver objective, constraints, or model structure (except for new optional parameters)
- Alter What-If or Monte Carlo sampling logic
- Change the deterministic baseline (all toggles ON should match Phase 4.3.2)
- Remove any existing required workflows or UI flows

---

**Execution Gate**: Do not deviate from this spec. All 11 items must be addressed. If you encounter model feasibility issues, document them and propose solutions; do not skip items.
