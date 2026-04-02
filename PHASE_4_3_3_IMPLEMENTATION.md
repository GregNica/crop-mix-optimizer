# Phase 4.3.3 Implementation Guide: Progressive Disclosure + Depreciation Model

## Overview
This phase addresses 11 specific feedback items from the Phase 4.3.2 output:
- Toggle defaults and visibility behavior (Items 1, 4, 5, 6)
- Depreciation model for storage/water/fuel (Items 2, 3)
- Additional toggle for crop variable costs (Item 7)
- UI naming and guidance improvements (Items 8, 9)
- Parameter omission from solver (Item 10)
- Comprehensive testing (Item 11)

## Critical Architectural Changes

### 1. Depreciation Model
**Requested**: Replace $/unit/week rates with $/unit capital cost + straight-line depreciation

**Current Implementation**:
```javascript
// Old approach (still in use):
fixed_cost = harvest_storage_cap * rate_harvest_storage * operating_weeks
           + water_tank_capacity * rate_water_storage * operating_weeks
           + equip_storage * rate_equip_storage * operating_weeks
           + fuel_storage * rate_fuel_storage * operating_weeks
```

**New Approach**:
```javascript
// New depreciation-based calculation:
// Weekly cost = (capital_cost * capacity) / (depreciation_years * 52)
// Example: Water tank 10,000L @ $2/L, 20-year depreciation
//   = (10,000 * $2) / (20 * 52) = $20,000 / 1,040 = $19.23/week

fixed_cost = (harvest_storage_cost_per_m3 * harvest_storage_cap) / (depreciation_harvest_years * 52)
           + (water_tank_cost_per_L * water_tank_capacity_L) / (depreciation_water_years * 52)
           + (irrigation_cost_per_acre * total_land) / (depreciation_irrig_years * 52)
           + (equip_storage_cost_per_m3 * equip_storage) / (depreciation_equip_years * 52)
           + (fuel_storage_cost_per_L * fuel_storage) / (depreciation_fuel_years * 52)
           ...
```

**Solver Impact**:
- Add new parameters to `solve_farm_v2()`:
  - `depreciation_harvest_years`, `depreciation_irrigation_years`, `depreciation_equip_years`, `depreciation_water_years`, `depreciation_fuel_years`
  - `water_tank_cost_per_L`, `irrigation_cost_per_acre`, `equip_storage_cost_per_m3`, `fuel_storage_cost_per_L`, `harvest_storage_cost_per_m3`
- Keep existing `rate_*` parameters for backward compatibility (still used for constraints, not costs)
- Calculate weekly cost dynamically in solver

**Default Depreciation Years**:
- Water tank: 20 years (typical lifespan for concrete/poly tanks)
- Harvest storage: 25–30 years (building depreciation)
- Irrigation system: 15–20 years (typical for drip systems)
- Equipment storage: 30 years (building structure)
- Fuel storage: 10–15 years (tank replacement cycle)

### 2. Parameter Omission Logic
**Challenge**: When a toggle is OFF, its fields should not be included in the solver parameters

**Current Issue**: Defaults are pre-filled in HTML; hidden fields still contain values

**Solution Approach**:
```javascript
// In run_from_js(), before passing to solver:
const params = {
  // ... always-required fields ...
  
  // Conditional fields — only include if toggle is ON:
  ...(document.getElementById('pd-cash').checked && {
    opening_cash: parseFloat(g('opening_cash').value),
    credit_line: parseFloat(g('credit_line').value),
  }),
  
  ...(document.getElementById('pd-machinery').checked && {
    equip_storage: parseFloat(g('equip_storage').value),
    fuel_storage: parseFloat(g('fuel_storage').value),
  }),
  
  // Storage costs — only if toggle ON:
  ...(document.getElementById('pd-harvest-storage').checked && {
    rate_harvest_storage: parseFloat(g('rate_harvest_storage').value),
  }),
  
  // Crops-level: omit variable costs if toggle OFF:
  crops: crops.map(c => ({
    ...c,
    // Include crop variable costs only if enabled:
    ...(enableCropVariableCosts && {
      fert_lb_per_phase: c.fert_lb_per_phase,
      fuel_L_per_phase: c.fuel_L_per_phase,
      pesticide_cost_per_acre: c.pesticide_cost_per_acre,
    }),
    // Include phase splits only if enabled:
    ...(enablePhaseDetail && {
      labor_hours_plant: c.labor_hours_plant,
      labor_hours_grow: c.labor_hours_grow,
      labor_hours_harv: c.labor_hours_harv,
      water_L_per_phase: c.water_L_per_phase,
      // ...
    }),
  })),
};
```

**Testing Requirement**: Verify that omitted parameters don't cause solver errors or invalid defaults

### 3. UI Structure Changes

#### 3a. Toggle Defaults (Items 1, 4, 5, 6, 7)
```html
<!-- BEFORE: All checked -->
<input type="checkbox" id="pd-cash" checked>

<!-- AFTER: All unchecked by default -->
<input type="checkbox" id="pd-cash">
```

#### 3b. Harvest Storage Move (Item 1)
```html
<!-- BEFORE: Standalone in Farm Infrastructure -->
<div class="form-group">
  <label>Harvest Storage (m³)...</label>
  <input ... id="harvest_storage_cap" ...>
</div>

<!-- AFTER: Grouped under storage toggle -->
<!-- Now grouped with "Account for storage constraints" toggle -->
<label class="pd-toggle-row" for="pd-harvest-storage">
  <input type="checkbox" id="pd-harvest-storage">
  Account for harvest storage and refrigeration costs?
</label>
<div id="pd-harvest-storage-fields" class="pd-revealed pd-hidden">
  <div class="form-group">
    <label>Harvest Storage Capacity (m³)...</label>
    <input ... id="harvest_storage_cap" ...>
  </div>
  <div class="form-group">
    <label>Harvest Storage Cost ($/m³)...</label>
    <input type="number" id="harvest_storage_cost_per_m3">
  </div>
  <div class="form-group">
    <label>Depreciation Period (years)...</label>
    <input type="number" id="depreciation_harvest_years" value="25">
  </div>
</div>
```

#### 3c. Water Section Depreciation Model (Item 2)
```html
<!-- NEW: In Water section (move from Farm Basics) -->
<div class="water-cost-card">
  <h3>Water Tank Storage Cost</h3>
  <div class="form-grid">
    <div class="form-group">
      <label>Water Tank Capacity (L)...</label>
      <input type="number" id="water_tank_capacity_L" value="50000">
    </div>
    <div class="form-group">
      <label>Tank Cost per Liter ($/L)...</label>
      <input type="number" id="water_tank_cost_per_L" value="2.00" step="0.05">
      <span class="tip" data-tip="Capital cost of water storage infrastructure. At $2/L depreciated over 20 years = ~$0.0192/L/week">?</span>
    </div>
    <div class="form-group">
      <label>Depreciation Period (years)...</label>
      <input type="number" id="depreciation_water_years" value="20">
    </div>
    <div style="background:#f0faf4;padding:0.5rem;border-radius:5px;font-size:0.75rem;color:#374151">
      Weekly cost = (Tank Capacity × Cost/L) ÷ (Depreciation Years × 52 weeks)
    </div>
  </div>
</div>
```

#### 3d. Optimize Button Relocation (Item 5)
```html
<!-- BEFORE: At bottom of section -->
<div id="section-cards-grid"><!-- form cards --></div>
<div class="section-optimize-footer"><!-- Optimize button --></div>

<!-- AFTER: At top of section -->
<div class="section-optimize-footer">
  <button class="btn-opt section-opt-btn">Optimize</button>
  <span class="opt-gate-hint">Complete all 4 sections...</span>
</div>
<div id="section-cards-grid"><!-- form cards --></div>
<div class="section-optimize-footer" style="opacity:0.6">
  <!-- Optional: confirmation-only footer -->
</div>
```

#### 3e. Crop Section Dual Toggles (Item 7)
```html
<!-- REMOVED: Single toggle -->
<label class="pd-toggle-row" for="pd-phase-detail">
  Add phase-specific resource usage?
</label>

<!-- ADDED: Two separate toggles -->
<label class="pd-toggle-row" for="pd-crop-var-costs">
  <input type="checkbox" id="pd-crop-var-costs">
  Add crop specific variable costs (fertilizer, pesticide/herbicide, fuel)?
</label>
<div id="pd-crop-var-costs-helper" class="pd-helper">
  Crop-specific variable costs are set to defaults. Enable to customize fertilizer, pesticide, and fuel usage per crop.
</div>
<div id="pd-crop-var-costs-fields" class="pd-revealed pd-hidden">
  <!-- revealed when checked: fertilizer, pesticide, fuel inputs... -->
</div>

<label class="pd-toggle-row" for="pd-phase-detail">
  <input type="checkbox" id="pd-phase-detail">
  Add phase specific resource usage (planting / growing / harvesting splits)?
</label>
<div id="pd-phase-detail-helper" class="pd-helper">
  Resource usage is split across growing phases. Enable to customize labor, water, fertilizer, and fuel separately for each phase.
</div>
<div id="pd-phase-detail-fields" class="pd-revealed pd-hidden">
  <!-- revealed when checked: plant/grow/harv splits for labor, water, fert, fuel -->
</div>
```

#### 3f. MC Naming & Pill (Items 8, 9)
```html
<!-- BEFORE -->
Monte Carlo: Yield uncertainty

<!-- AFTER -->
Historical crop data to account for uncertainty
<!-- added pill/badge next to demand/price/yield fields: 📊 Add to Historical data -->
```

## Detailed Implementation Tasks

### Phase 4.3.3a: Toggle Defaults & Visibility
**Priority**: P0 (foundational for all other changes)

**Changes**:
1. Find all `checked` attributes on `.pd-toggle-row` checkboxes → remove them
2. Find all `.pd-revealed` divs that are not hidden → add `pd-hidden` class by default
3. Update `togglePD()` function to ensure proper show/hide behavior
4. Test that all toggles start unchecked and fields hidden

**Files**:
- `index.html`: Lines ~938–1000 (style definitions), lines ~1100–1200 (Farm Basics), lines ~1383–1450 (Labor & Channels), lines ~1452–1527 (Crops)

**Tests**:
- T4.3.3a-1: All toggles start unchecked on page load
- T4.3.3a-2: Toggling ON reveals fields; toggling OFF hides them
- T4.3.3a-3: Hidden fields do not break form submission

---

### Phase 4.3.3b: Harvest Storage Move to Toggle
**Priority**: P1 (prerequisite for depreciation model)

**Changes**:
1. Remove `harvest_storage_cap` from standalone Farm Infrastructure position
2. Group with new storage/constraint toggle (alongside cash/machinery toggles)
3. Add depreciation fields for harvest storage
4. Add helper text and tooltips

**Files**:
- `index.html`: Lines ~1100–1150 (Farm Basics form structure)

**Solver Changes**:
- None immediate (keep using existing `harvest_storage_cap` parameter)
- Later: add `depreciation_harvest_years`, `harvest_storage_cost_per_m3`

**Tests**:
- T4.3.3b-1: Harvest Storage toggle controls visibility of capacity + depreciation fields
- T4.3.3b-2: With toggle OFF, harvest_storage_cap is omitted from params

---

### Phase 4.3.3c: Water Depreciation Model
**Priority**: P1 (architectural change to solver)

**Changes**:
1. **Solver**: Add depreciation calculation logic to `solve_farm_v2()`
   ```python
   # Pseudocode for solver
   water_tank_weekly_cost = (water_tank_capacity_L * water_tank_cost_per_L) / (depreciation_water_years * 52)
   fixed_cost += water_tank_weekly_cost * operating_weeks
   ```

2. **UI**: Add depreciation fields to Water section:
   - `water_tank_capacity_L` (capacity in liters)
   - `water_tank_cost_per_L` (capital cost per liter)
   - `depreciation_water_years` (default 20)

3. **Backward Compat**: Keep old `rate_water_storage` field but deprecate it (show migration hint)

**Files**:
- `index.html`: Lines ~1200–1350 (Water section)
- Python solver: `farm_v2/solver.py` or equivalent

**Tests**:
- T4.3.3c-1: Water tank depreciation calculation is correct
- T4.3.3c-2: Changing tank size and cost changes weekly cost proportionally
- T4.3.3c-3: With baseline depreciation (20yrs), solve matches old $/wk approach within ±5%

---

### Phase 4.3.3d: Harvest + Irrigation + Equipment + Fuel Depreciation
**Priority**: P2 (extends P1 pattern)

**Changes**:
1. **Solver**: Extend depreciation logic for all four storage types
2. **UI**: Add depreciation fields for each (move to appropriate sections):
   - Harvest Storage: Farm Basics (already moved in P4.3.3b)
   - Irrigation: Water section
   - Equipment Storage: Farm Basics (with machinery toggle)
   - Fuel Storage: Farm Basics (with machinery toggle)

3. **Fields to Add**:
   - `harvest_storage_cost_per_m3`, `depreciation_harvest_years` (25yr default)
   - `irrigation_cost_per_acre`, `depreciation_irrigation_years` (18yr default)
   - `equip_storage_cost_per_m3`, `depreciation_equip_years` (30yr default)
   - `fuel_storage_cost_per_L`, `depreciation_fuel_years` (12yr default)

**Files**:
- `index.html`: Multiple sections
- Python solver: depreciation calculations

**Tests**:
- T4.3.3d-1–4: Each storage type depreciates correctly
- T4.3.3d-5: Sum of depreciated storage costs matches expected fixed_cost increase
- T4.3.3d-6: With all depreciation years at 1, costs are highest; with all at 50, costs are lowest

---

### Phase 4.3.3e: Optimize Button Relocation
**Priority**: P1 (UI polish, no solver impact)

**Changes**:
1. Find all `.section-optimize-footer` divs
2. Move from end of `#section-cards-grid` to beginning (after nav/stepper)
3. Keep lock-state gating behavior identical
4. Optionally keep a secondary footer for confirmation only (grayed out)

**Files**:
- `index.html`: Multiple sections (~1200, ~1383, ~1452)

**Tests**:
- T4.3.3e-1: Optimize button appears at top of each section
- T4.3.3e-2: Button remains disabled/enabled in sync with top-level Optimize
- T4.3.3e-3: Scrolling to top of section shows Optimize immediately

---

### Phase 4.3.3f: Sales Channel Field Hiding
**Priority**: P1 (fix existing bug)

**Changes**:
1. Find `setPDChannelVarDetail()` function
2. Verify it properly hides/shows channel cost fields
3. Add `pd-hidden` class to cost fields when toggle is OFF
4. Test that hiding persists through form re-renders

**Files**:
- `index.html`: Lines ~1400–1430 (Sales Channels card)
- JavaScript: `setPDChannelVarDetail()` function

**Tests**:
- T4.3.3f-1: Sales channel toggle unchecked by default
- T4.3.3f-2: Toggling ON reveals variable + fixed selling cost fields
- T4.3.3f-3: Toggling OFF hides fields and removes them from params

---

### Phase 4.3.3g: Crop Section Dual Toggles
**Priority**: P2 (requires model changes for parameter omission)

**Changes**:
1. Replace single `pd-phase-detail` toggle with two toggles:
   - `pd-crop-var-costs`: reveals fertilizer, pesticide, fuel per-crop fields
   - `pd-phase-detail`: reveals labor/water/fert/fuel phase splits
2. Labor and water are always included (at least one parameter set)
3. Conditional rendering based on toggles

**Files**:
- `index.html`: Lines ~1452–1527 (Crops section), crop-entry HTML/JS

**Solver Changes**:
- Need to handle omitted per-crop variable costs gracefully
- See Item 10 (Parameter Omission) for details

**Tests**:
- T4.3.3g-1: Both toggles unchecked by default
- T4.3.3g-2: Variable costs toggle reveals fert/pesticide/fuel fields
- T4.3.3g-3: Phase detail toggle reveals plant/grow/harv splits
- T4.3.3g-4: Labor and water always present (even if other toggles off)
- T4.3.3g-5: With both toggles off, only crop name, yield, season, and channels visible

---

### Phase 4.3.3h: MC Naming + Uncertainty Pills
**Priority**: P2 (UX improvement, no solver impact)

**Changes**:
1. Rename "Monte Carlo: Yield uncertainty" → "Historical crop data to account for uncertainty"
2. Add small pill/badge next to demand, price, yield fields suggesting MC upload
3. Link pill to MC upload section or form

**Files**:
- `index.html`: Lines ~1452–1527 (Crops section)

**Tests**:
- T4.3.3h-1: MC section renamed
- T4.3.3h-2: Pills appear next to demand/price/yield
- T4.3.3h-3: Clicking pill opens or highlights MC upload area

---

### Phase 4.3.3i: Parameter Omission Logic
**Priority**: P0 (critical for correctness)

**Changes**:
1. In `run_from_js()`, modify parameter collection to use conditional spreads (see architecture section)
2. Only include fields in params if their toggle is checked
3. Test that solver receives omitted parameters gracefully

**Files**:
- `index.html`: Lines ~4300–4400 (`run_from_js()` function)

**Solver Changes**:
- Possibly add default handling for optional parameters
- Ensure omitted parameters don't cause validation errors

**Tests** (Critical):
- T4.3.3i-1: With pd-cash OFF, opening_cash and credit_line omitted from params
- T4.3.3i-2: With pd-machinery OFF, equip/fuel storage omitted
- T4.3.3i-3: Solver runs successfully with partial parameter sets
- T4.3.3i-4: Results change appropriately when parameters omitted (costs drop to 0)

---

### Phase 4.3.3j: Comprehensive Testing
**Priority**: P0 (validation of all changes)

**Test Strategy**:

1. **Unit Tests** (each toggle independently):
   - Cash Toggle ON/OFF: opening_cash and credit_line change
   - Machinery Toggle ON/OFF: equip/fuel storage and costs change
   - Harvest Storage Toggle ON/OFF: harvest capacity and costs change
   - Irrigation Toggle ON/OFF: irrigation cost changes
   - Crop Var Costs Toggle ON/OFF: crop-specific fert/pesticide/fuel change
   - Phase Detail Toggle ON/OFF: phase splits for labor/water/fert/fuel change

2. **Integration Tests** (combinations):
   - All toggles ON: full featured mode
   - All toggles OFF: minimal mode, only required parameters
   - Benchmarks mode: all ON by default
   - Manual mode: all OFF by default

3. **Regression Tests**:
   - Baseline solve (all toggles ON) matches previous phase ($6.2M profit)
   - Deterministic: running same inputs twice gives identical results
   - Export: P&L breakdown and all outputs correct

4. **Edge Cases**:
   - Toggles changed mid-entry (e.g., turn machinery ON/OFF while viewing form)
   - Saved inputs with old toggle states loaded in new version
   - Depreciation years set to 0 or 1 (should not crash)

**Test Output Validation**:
```
Test: Cash OFF, Machinery ON, Harvest ON, Irrig ON, Crops Var Costs OFF, Phase Detail OFF
Expected:
- opening_cash and credit_line not in params
- machinery, equip_storage, fuel_storage NOT in params
- harvest_storage_cap and depreciation fields IN params
- irrigation_cost_per_acre IN params
- crop variable costs NOT in params
- labor/water/fert/fuel phase splits NOT in params
- Solver completes successfully
- Profit is lower than baseline (fewer constraints/costs enabled)
```

---

## Implementation Sequence

**Recommended order** (to minimize risk and enable testing at each stage):

1. **Phase 4.3.3a**: Toggle defaults & visibility (foundation)
2. **Phase 4.3.3i**: Parameter omission logic (critical for correctness)
3. **Phase 4.3.3b**: Harvest storage move
4. **Phase 4.3.3c**: Water depreciation model + solver update
5. **Phase 4.3.3d**: Extend depreciation to all storage types
6. **Phase 4.3.3e**: Optimize button relocation
7. **Phase 4.3.3f**: Sales channel field hiding
8. **Phase 4.3.3g**: Crop dual toggles
9. **Phase 4.3.3h**: MC naming + pills
10. **Phase 4.3.3j**: Comprehensive testing

## Risk Mitigation

### Risk: Model Feasibility with Omitted Parameters
**Mitigation**: 
- Always-required: total_land, operating_weeks, crops array, channels array
- Test with minimal parameter set (only required fields)
- Add pre-solve validation to catch infeasibility early

### Risk: Backward Compatibility
**Mitigation**:
- Keep old parameter names in solver signature (use defaults)
- Old saved inputs should still load (map old fields to new depreciation fields)
- Provide migration path in UI (e.g., "We've updated to a depreciation-based model; your settings have been converted")

### Risk: User Confusion (Too Many Toggles)
**Mitigation**:
- Clear helper text on each toggle (what's included/excluded)
- Color-coded sections (enabled vs disabled)
- Optional intro/onboarding explaining toggle model

### Risk: Solver Parameter Validation Errors
**Mitigation**:
- Comprehensive validation in `validate_params()` for optional parameters
- Clear error messages if validation fails
- Test solver with each parameter omitted individually

## Success Criteria
- ✓ All 11 feedback items implemented
- ✓ Toggle defaults are unchecked, fields hidden
- ✓ Harvesting/irrigation/storage use depreciation model
- ✓ Parameters omitted when toggles are off (verified in params JSON)
- ✓ Optimizer completes successfully with toggles ON/OFF/mixed
- ✓ Baseline solve (all ON) matches Phase 4.3.2 profit within $0.01
- ✓ All 7 test groups pass
- ✓ No regressions in existing test suite
