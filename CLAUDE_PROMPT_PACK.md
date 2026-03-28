# Claude Code Prompt Pack: Farm Optimization UI Roadmap

Use these prompts one phase at a time. Do not combine phases in one run.

---

## How To Use

1. Run one phase prompt.
2. Wait for Claude Code to finish.
3. Validate scope + tests.
4. Only then run the next phase prompt.

---

## Shared Guardrails (prepend to every phase prompt)

```text
Implement only this phase.
Do not modify solver math, constraints, or objective.
Do not start later phases.
Keep changes incremental and backward-compatible.
Run tests and report exact pass/fail results.
List deferred items explicitly.
```

---

## Phase 1 Prompt — Hub UI + Executive Summary + Advanced Toggle

```text
You are implementing Phase 1 of a farm optimization web app redesign.

Goals:
1. Replace dense single-flow input UI with a hub-based navigation layout optimized for laptop use.
2. Keep solver behavior unchanged.
3. Add an executive summary as the first result section.
4. Hide Monte Carlo and Sensitivity under an Advanced toggle (default off).

Constraints:
1. Do not change optimization math or core solver outputs.
2. Preserve existing parameter schema and existing tests.
3. Keep implementation incremental and backward-compatible.
4. Do not remove existing result charts/tables; reorganize visibility and priority.
5. Keep accessibility and keyboard navigation reasonable.

Required UI behavior:
1. Hub navigation with section cards and completion states:
- Farm Basics
- Water
- Labor and Channels
- Crops
- Review and Run
2. Returning users can jump to any section.
3. First-time flow still guides users through required sections.
4. Executive summary appears first on results:
- Top recommendation sentence
- Highest margin crop
- Most pressing binding constraint
- One suggested next action
5. Advanced toggle controls visibility of Monte Carlo and Sensitivity tabs.
6. Add short explanatory text for advanced tools.

Implementation notes:
1. Prefer additive refactor over full rewrite.
2. Keep existing data extraction logic working during transition.
3. Add small state object for:
- current section
- section completion
- defaults applied
- advanced enabled
4. Add clear comments around new state and summary generation logic.

Acceptance criteria:
1. App runs end-to-end in browser with unchanged optimization outputs.
2. Existing tests still pass.
3. User can navigate via hub and run optimization.
4. Executive summary displays after solve.
5. Advanced tabs are hidden until toggled on.

At the end, provide:
1. Files changed
2. What was intentionally deferred
3. Any risks or follow-up items
```

---

## Phase 2 Prompt — Bottleneck-Triggered What-If Sensitivity

```text
Implement Phase 2: convert sensitivity into bottleneck-triggered what-if analysis.

Goals:
1. After baseline solve, identify top binding constraint from existing utilization outputs.
2. Show contextual CTA:
- If water binds: Test more water
- If labor binds: Test more labor
- If land binds: Test more land
- If budget/cash binds: Test more budget
3. Run targeted what-if scenarios from result screen and display deltas.

Constraints:
1. Keep core optimization model unchanged.
2. Reuse existing solve pipeline for scenario reruns.
3. Keep advanced tools behind Advanced toggle.
4. Do not add Monte Carlo redesign yet.

Required behavior:
1. Baseline results include bottleneck card with reason and confidence.
2. Clicking CTA runs predefined scenario set for that bottleneck:
- Example: +10%, +20%, +40% on the constrained resource
3. Show scenario comparison table:
- Profit delta
- Constraint utilization change
- Crop mix change summary
4. Keep baseline result pinned for side-by-side comparison.

Acceptance criteria:
1. Bottleneck identification is deterministic and explainable.
2. Scenario runs are reproducible and do not mutate baseline unexpectedly.
3. Existing tests pass; add tests for bottleneck selection and delta calculation.
4. UI clearly distinguishes baseline vs scenario outputs.

At the end, report:
1. Exact heuristic rules used
2. Any false-positive/edge-case risks
3. Recommended next improvements
```

---

## Phase 2.1 Patch — Multi-Bottleneck Sensitivity + Scenario Persistence

```text
Implement a focused Phase 2.1 refinement of the sensitivity workflow.

Goals:
1. Reduce redundancy between bottleneck, executive summary, and constraint utilization sections.
2. Improve sensitivity usefulness for cases where multiple constraints are near-binding.
3. Preserve solver/math scope while improving decision support.

Scope constraints:
1. Keep optimization model unchanged (no objective/constraint reformulation).
2. Keep Monte Carlo redesign out of scope.
3. Keep labor-as-decision-variable out of scope.
4. Do not present MILP shadow prices as exact values.

Required updates:
1. Refactor section roles to avoid redundancy:
- Keep Constraint Utilization Summary as a compact diagnostic view (state only).
- Keep Executive Summary short (top recommendation only).
- Use Sensitivity Analysis as the action section (what happens if constraints are loosened).

2. Multi-bottleneck ranking and scenarios:
- Rank active/near-active constraints by utilization and persistence (example threshold >= 90%).
- Include market-side demand caps in near-binding checks so demand limits are surfaced.
- Run scenario tests for top 2-3 active constraints, not just the single top constraint.
- If two constraints are simultaneously near-binding, add one combined scenario to show interaction effects.

3. Custom scenario controls:
- Keep quick presets (+10, +20, +40).
- Add user-entered custom percentage input with validation and safe bounds.
- Allow users to apply custom changes to selected active constraints.

4. Persist scenario comparisons:
- Keep baseline pinned.
- Persist last N scenario runs in the UI so reruns do not erase all prior comparison context.
- If practical, persist in local browser storage; otherwise keep in session with clear messaging.

5. Shadow-price caveat handling:
- If adding any marginal-value panel, label values as approximate only.
- Prefer scenario delta interpretation as primary.
- If LP-relaxation duals are shown, explicitly label as LP-relaxation estimates, not exact MILP shadow prices.

Acceptance criteria:
1. Sensitivity section reports on active/near-binding constraints with actionable what-if outputs.
2. Multi-bottleneck and combined scenarios are available when appropriate.
3. Demand-cap constraints can appear in sensitivity candidates.
4. Scenario history persists for comparison (baseline + last N scenarios).
5. No claims of exact shadow prices for MILP integer solution.
6. Existing tests pass; add/adjust tests for ranking, custom input validation, and scenario persistence.

At the end, report:
1. Ranking heuristics and thresholds used
2. Persistence approach used (session/local)
3. Any mathematical caveats shown to users
```

---

## Phase 2.2 Patch — Demand-Cap Granularity + Results Priority

```text
Implement a focused Phase 2.2 correction for scenario analysis relevance and layout priority.

Primary issues to fix:
1. Scenario analysis currently treats demand caps too coarsely; demand sensitivity should be per crop/channel pair, consistent with constraint utilization reporting.
2. Scenario analysis is too low in the results layout; it should be moved up because it carries key actionable guidance.

Scope constraints:
1. Keep optimization model unchanged.
2. Keep Monte Carlo redesign out of scope.
3. Keep labor-as-decision-variable out of scope.
4. Do not add exact MILP shadow-price claims.

Required updates:
1. Demand-cap sensitivity at crop/channel granularity:
- Build demand-cap candidates as crop+channel constraints (not only aggregate demand signals).
- Rank near-binding demand caps using per crop/channel utilization from baseline results.
- Include these demand-cap candidates in scenario actions and recommendations.
- Ensure output messages name both crop and channel (example: "Spinach / Farmers Market at 94% cap").

2. Scenario panel layout priority:
- Move Scenario Analysis / Sensitivity Analysis section higher in results-main.
- Place it near the top so users see actionable next-step analysis before lower-priority detail panels.
- Keep Executive Summary compact and non-duplicative.

3. Actionable reporting format:
- For each active candidate (including demand-cap candidates), show:
  a) baseline utilization
  b) scenario deltas (profit and utilization)
  c) short plain-language interpretation
- Keep baseline pinned for comparison.

4. Redundancy reduction:
- Constraint Utilization Summary remains diagnostic (state table).
- Scenario/Sensitivity section remains intervention-oriented (what-if outcomes).
- Avoid repeating identical text between executive summary and sensitivity cards.

Acceptance criteria:
1. Demand-cap scenarios are generated and reported per crop/channel basis.
2. At least one near-binding demand-cap candidate can appear when applicable in default/demo runs.
3. Scenario/Sensitivity section appears above lower-priority analysis panels in results order.
4. Results remain consistent with existing solver outputs and constraints.
5. Existing tests pass; add/adjust tests for crop/channel demand candidate ranking and panel ordering.

At the end, report:
1. Crop/channel demand-cap ranking logic used
2. New results section order
3. Any known edge cases where demand caps are absent or non-binding
```

---

## Phase 2.3 Patch — What-If UX Simplification + Results Cleanup

```text
Implement a focused Phase 2.3 refinement that simplifies the What-If experience, removes redundant result panels, and applies targeted quality fixes.

Primary goals:
1. Reduce input-page friction (remove low-value Review & Run as a required stop).
2. Make What-If the primary intervention surface.
3. Support multi-constraint what-if runs in one scenario execution.
4. Clean up duplicate or low-quality visuals on the results page.

Scope constraints:
1. Keep optimization model unchanged (objective/constraints/math untouched).
2. Keep Monte Carlo redesign out of scope.
3. Keep labor-as-decision-variable out of scope.
4. Keep existing parameter schema backward-compatible.

Required updates:

1. Hub flow and Optimize gating:
- Remove the dedicated "Review and Run" section/page from required workflow.
- Keep hub cards for Farm Basics, Water, Labor and Channels, Crops.
- A section receives a green check only after user has visited that section at least once.
- Optimize button remains disabled/grayed out until all required sections have been visited.
- Add clear opening-page guidance: defaults are preloaded, but user should visit each section to customize.
- Keep keyboard and accessibility behavior reasonable.

2. Constraint summary replacement and export:
- Remove/hide the standalone Constraint Utilization Summary card from default results view.
- Add an "Export Constraint Utilization CSV" action within the What-If Scenario Analysis card.
- Export should include baseline utilization metrics currently used for ranking.
- Keep data available for diagnostics/export even if panel is removed.

3. What-If controls simplification:
- Keep the current table-style What-If output (baseline pinned + scenario rows with deltas and updated utilization context).
- When a user clicks/selects a constraint, automatically run a predefined scenario set (for example +10%, +20%, +40%) without requiring separate preset button clicks.
- Keep custom percentage input and a single explicit "Run Custom" action.
- Remove manual preset selection buttons (do not show separate +10/+20/+40/+30 controls).
- Keep constraint pills/toggles for selecting which constraints are active in analysis.
- Ensure bottleneck severity remains visible (active/near-binding context).

4. Multi-change scenarios in one run:
- Allow selecting multiple constraints simultaneously and run a combined scenario in one solve.
- Combined scenario should apply all selected changes together and report one net outcome vs baseline.
- Scenario label should explicitly list all applied changes (example: "+20% Labor AND +10% Water AND +10% Spinach/Farmers Market demand").
- Keep baseline pinned.
- Keep scenario history behavior.

5. What-If ranking and correctness fixes:
- Fix combined-scenario candidate filtering so demand_single constraints are handled intentionally (no accidental inclusion/exclusion due to type mismatch).
- Improve demand-cap candidate saturation logic so per crop/channel ranking is not artificially inflated by reusing total crop harvest independently for every channel.
- Keep per crop/channel messaging explicit.
- IMPORTANT user preference: Land must always appear in the What-If candidate list even when below normal visibility threshold.

6. Results-page cleanup/aesthetics:
- Remove duplicate Peak Borrowing display if shown both in executive summary and elsewhere; keep one clear location.
- Move Export P&L action into the Profit Waterfall card header area.
- Improve waterfall chart presentation:
  a) wider layout on desktop,
  b) responsive sizing on mobile,
  c) cleaner visual styling while preserving data values.
- Add concise explanatory copy in Unit Contribution Margins section describing formula/components behind unit margins.

Acceptance criteria:
1. Optimize button is disabled until all required hub sections have been visited at least once.
2. Review-and-run gating is removed without breaking solve flow.
3. Constraint Utilization Summary panel is removed from default results, and CSV export is available in What-If.
4. What-If uses bar-style presets with no custom % textbox.
4. What-If auto-runs a predefined percent set when a constraint is selected.
5. User can run a multi-constraint combined scenario in a single solve and see one combined delta.
6. Land is always visible in What-If candidate list.
7. Demand-cap ranking remains per crop/channel and avoids overstated saturation artifacts.
8. No solver-model math changes.
9. Existing tests pass; add/adjust tests for:
   - visit-based optimize gating,
   - land always visible in What-If,
   - combined multi-constraint scenario labeling/application,
   - demand candidate ranking logic,
   - removal/replacement of constraint panel with CSV export,
   - updated results panel order and duplicate Peak Borrowing removal.

At the end, report:
1. New hub completion/optimize gating logic
2. What-If auto-run scenario set behavior (which percentages and when they trigger) and multi-constraint execution flow
3. Demand-cap ranking formula used
4. New results section order and export action locations
5. Any known edge cases (especially for no-demand-cap or low-utilization farms)
```

---

## Phase 2.3.1 Patch — What-If Regression Fixes + Margin % Correction + Executive Highlights

```text
Implement a focused Phase 2.3.1 correction pass for regressions introduced after Phase 2.3.

Primary issues to fix:
1. Market demand-cap candidates are no longer appearing in What-If.
2. What-If scenario deltas appear inconsistent/disproportionate for nearby % changes (example +20% vs +25% labor).
3. Unit margin % definition appears incorrect to users (showing >100% in ways that read as "profit margin").
4. Executive summary needs three additional operational highlights.

Scope constraints:
1. Keep optimization model unchanged.
2. Keep Monte Carlo redesign out of scope.
3. Keep labor-as-decision-variable out of scope.
4. Keep existing schema backward-compatible.

Required updates:

1. Restore demand-cap visibility in What-If:
- Ensure demand-side candidates can appear in the What-If candidate list when applicable.
- Do not let top-N truncation or visibility thresholds hide all demand entries in default/demo runs.
- Keep per crop/channel naming explicit.
- Keep user preference: Land always appears in What-If even when low utilization.
- Add a defensive fallback: if demand caps exist and none meet threshold, still show the top demand candidate(s) with "informational/low-pressure" styling.

2. Fix scenario consistency and labeling:
- Ensure scenario rows clearly record exactly which constraints were changed for each run.
- Prevent accidental multi-constraint application during single-constraint custom runs.
- Single-constraint auto-run (+10/+20/+40) should apply only that selected constraint.
- Combined runs should apply all selected constraints intentionally and be labeled as combined.
- Add validation logging/debug output (dev-only) for each scenario run:
  a) selected constraint list,
  b) scaling factors actually applied,
  c) resulting key utilization deltas.
- Keep baseline pinned and immutable.

3. Correct Unit Contribution Margin % semantics:
- If the column is intended as "margin %", compute it as:
  margin_pct = contribution_margin / gross_revenue * 100
  (not margin divided by total variable cost).
- If retaining margin/VC ratio, rename label to "Markup %" and explain explicitly.
- Update tooltip/explanatory copy so users can distinguish:
  a) contribution margin $/acre,
  b) margin % of revenue,
  c) markup % on cost (if shown).

4. Executive summary additions:
- Add "Lowest-Margin Option (annualized)" by crop/channel using same time-adjusted basis as highest-margin logic.
- Add "Peak Labor Week" including week number and utilization/value.
- Add "Peak Land Use Week" including week number and utilization/value.
- Keep summary compact and non-duplicative.

5. Clean acceptance/list consistency:
- Remove conflicting acceptance text from Phase 2.3 implementation outcome (no contradictory "no custom textbox" language).
- Keep custom % run path available as requested.

Acceptance criteria:
1. Demand-cap candidates appear in What-If when demand caps exist (including default/demo where applicable).
2. Scenario result labels exactly match applied constraints and percentages.
3. Single-constraint +20% and +25% runs are explainable/reproducible with no hidden extra constraints.
4. Margin % column matches its label semantics and explanatory text.
5. Executive summary shows:
   - lowest-margin option (annualized),
   - peak labor week,
   - peak land-use week.
6. Land always appears in What-If candidate list.
7. Existing tests pass; add/adjust tests for:
   - demand candidate visibility fallback,
   - single vs combined scenario application correctness,
   - scenario label/application parity,
   - margin % formula correctness,
   - executive peak-week metrics.

At the end, report:
1. Demand candidate inclusion logic and thresholds/fallbacks
2. Scenario application audit (single vs combined)
3. Final margin % formula used and why
4. Executive summary fields added and formulas
5. Any remaining edge cases requiring later-phase refinement
```

---

## Phase 2.3.2 Audit Prompt — Verify Root Cause Before Any Further Math/UI Changes

```text
Run an evidence-only forensic audit for the current Phase 2.3.1 implementation.

Hard guardrails:
1. Do not modify any files.
2. Do not change formulas, labels, or solver behavior.
3. Do not run formatting/refactor commands that alter files.
4. Collect evidence first; propose fixes only if data proves a mismatch.

Current baseline observations to verify (do not assume):
1. Demand-candidate saturation appears harvest-based in the current code path.
2. Unit-margin and executive annualized-margin displays may not include channel variable selling cost.
3. Scenario labels/application were recently adjusted and must be re-validated for single vs combined runs.

Audit objectives:
1. Verify why seemingly negative channel margins can coexist with optimizer recommendations.
2. Determine whether the issue is:
   a) display semantics mismatch,
   b) utilization calculation mismatch,
   c) expected optimization behavior under shared constraints,
   d) or an actual bug.
3. Explicitly test the fixed-cost hypothesis:
   - confirm whether fixed costs are (or are not) being incorrectly used in incremental unit/channel margin logic.

Required checks:
1. Current-state fingerprint (before analysis):
- Report exact file locations and formulas currently used for:
  a) demand saturation for What-If ranking,
  b) Unit Contribution Margin/ac display,
  c) Executive Summary annualized margin ranking.
- Include one short snippet per formula path to prove current baseline.

2. Solver economics traceability:
- Locate exact solver-side definitions for channel net price/revenue and variable costs (including packaging and variable selling costs).
- Show the exact formulas used in optimization for contribution at decision time.
- Confirm whether fixed costs are treated only at whole-plan level (not channel-level incremental margin ranking).

3. UI economics traceability:
- Locate formulas used by Unit Contribution Margins and Executive Summary annualized margin ranking.
- Confirm whether UI formulas match solver economics for:
  a) contribution margin numerator,
  b) margin % denominator,
  c) any channel variable selling cost handling.

4. Constraint utilization basis validation:
- For demand-side crop/channel candidates, compare:
  a) sold/cap utilization,
  b) any harvest-based proxy utilization.
- Identify exactly which basis is used in:
  a) Constraint Utilization summary,
  b) What-If ranking.
- Explain any discrepancy that could make channels look "binding" or "unattractive" incorrectly.

5. Repro checks for suspicious examples:
- Use baseline/default/demo run data and inspect at least:
  a) Spinach / Wholesale,
  b) Garlic / Wholesale,
  c) Cucumbers / Wholesale.
- For each, report:
  a) sold volume,
  b) demand cap,
  c) displayed unit margin,
  d) solver-consistent unit contribution,
  e) whether recommendation pressure came from that channel directly or from coupled crop/farm constraints.

6. Scenario consistency sanity check:
- Verify single-constraint custom runs (+20% vs +25% labor) apply exactly one intended constraint.
- Confirm no hidden multi-constraint carry-over.
- Report applied scaling vector per scenario.

Evidence output format (mandatory):
1. Findings table: Component | Formula/Rule | Source location | Current value | Matches solver? (Y/N)
2. Root-cause verdict with confidence (high/medium/low)
3. Fixed-cost hypothesis verdict (supported/rejected) with proof
4. Minimal patch plan ONLY if needed, prioritized by risk:
   - P0: must-fix correctness mismatch
   - P1: interpretation/labeling mismatch
   - P2: optional UX clarification
5. If no correctness bug is found, explicitly state:
   - "No math change recommended; interpretation/UI copy clarification only."

Acceptance criteria:
1. No files changed.
2. Current-state formulas documented before diagnosis.
3. Fixed-cost hypothesis explicitly resolved.
4. Clear go/no-go recommendation for any follow-up edits.
```

---

## Phase 2.3.3 Patch — Custom What-If Scope Fix (No Math Changes)

```text
Implement a focused Phase 2.3.3 correctness patch for custom What-If scenario scope behavior.

Primary issue to fix:
1. Custom What-If runs are applying multiple selected constraints during single-constraint execution paths, causing label/application mismatch and inconsistent deltas.

Scope constraints:
1. Keep optimization model unchanged.
2. Do not modify solver objective, constraints, or core economics formulas.
3. Do not change margin logic, demand ranking formulas, or fixed-cost accounting in this phase.
4. Keep existing parameter schema backward-compatible.

Required updates:
1. Single-constraint custom runs must apply exactly one intended constraint.
2. Combined runs must apply all selected constraints intentionally and only when user explicitly runs combined mode.
3. Scenario labels must exactly match the applied scaling vector and constraint set.
4. Prevent hidden constraint carry-over between runs.
5. Keep baseline pinned and immutable across reruns.
6. Add lightweight run-level diagnostics (dev-only) that record:
- selected constraints
- applied scaling factors
- baseline vs scenario utilization deltas for changed constraints

Acceptance criteria:
1. Single-constraint custom runs modify only the intended constraint.
2. Combined runs modify exactly the selected set and no extras.
3. Scenario labels are in parity with applied changes for every run row.
4. Nearby-value reproducibility is explainable and stable (example: +20% vs +25% labor).
5. Baseline values remain unchanged after any scenario sequence.
6. Existing tests pass; add or adjust tests for:
- single vs combined application correctness
- label/application parity
- no carry-over between runs
- baseline immutability

At the end, report:
1. Files changed
2. Exact tests run with pass/fail results
3. Any deferred follow-up items outside this phase scope
```

---

## Phase 2.3.4 Patch — Demand Saturation Basis Alignment (UI Consistency Only)

```text
Implement a focused Phase 2.3.4 consistency patch for demand saturation reporting across results panels.

Primary issue to fix:
1. Constraint Summary and What-If card currently use different demand saturation bases (annual aggregate vs per-channel top-1), creating interpretation drift.

Scope constraints:
1. Keep optimization model unchanged.
2. Do not modify solver objective, constraints, or core economics formulas.
3. Do not change scenario application logic fixed in Phase 2.3.3.
4. Keep existing parameter schema backward-compatible.
5. Treat this as UI/interpretation consistency only.

Required updates:
1. Choose one demand saturation basis and apply it consistently in both:
- Constraint Summary demand utilization
- What-If demand candidate utilization/ranking display
2. Keep crop/channel labeling explicit in both panels.
3. Align helper text/tooltips so users can understand the exact basis used.
4. Ensure exported/utilization context reflects the same chosen basis where applicable.
5. Preserve baseline pinned behavior and existing scenario history behavior.

Decision rule guidance:
1. Preferred default: per crop/channel sold-to-cap utilization for panel-level comparability.
2. If aggregate context is retained, explicitly label it as aggregate and do not mix with per-channel percentages in the same ranked view.

Acceptance criteria:
1. Constraint Summary and What-If display the same demand saturation basis for comparable entries.
2. No mixed-basis percentages appear in the same recommendation/ranking flow.
3. Labels/tooltips clearly state the basis.
4. No solver math, objective, or constraints changed.
5. Existing tests pass; add or adjust tests for:
- cross-panel basis parity
- demand utilization label correctness
- stable ranking interpretation under the chosen basis

At the end, report:
1. Which basis was selected and why
2. Files changed
3. Exact tests run with pass/fail results
4. Any remaining non-blocking UX follow-ups
```

---

## Phase 3 Prompt — Defaults Provenance + CSV Template Import

```text
Implement Phase 3 with two deliverables:
A) Better default values with provenance
B) Strict CSV template import path

Goals:
1. Reduce cognitive load for users who do not have all farm-specific data.
2. Allow users to start from benchmark defaults and override selectively.
3. Support structured CSV upload using a strict template with strong validation.

Scope constraints:
1. Do not modify optimization math, objective, or constraints.
2. Do not implement robust Monte Carlo redesign here.
3. Do not add labor-as-decision-variable here.
4. Keep behavior backward-compatible for manual form entry.

Defaults with provenance:
1. Add two user modes:
- Benchmark Defaults
- My Farm Data
2. In Benchmark Defaults mode, prefill selected fields from a local defaults map.
3. For every defaulted field, display:
- source label
- vintage/date
- confidence level (high/medium/low)
4. In Review and Run, show a Defaults Applied panel listing all auto-filled values.
5. Users must be able to override any default value manually.

CSV template import:
1. Add downloadable CSV template(s) with fixed schema and units.
2. Add upload control and parser for the strict template only.
3. Validate required columns, types, units, and accepted categorical values.
4. Show row-level and field-level validation errors with clear messages.
5. Reject malformed files with actionable instructions.
6. Do not support arbitrary spreadsheet parsing in this phase.

Implementation notes:
1. Keep parser isolated from solver.
2. Map CSV fields into existing parameter schema only after validation.
3. Preserve existing manual entry path fully.
4. Add tests for:
- defaults application and override behavior
- provenance rendering
- CSV happy path
- CSV validation failures

Acceptance criteria:
1. Users can run the app with benchmark defaults and minimal manual input.
2. Users can override any default and see it reflected in Review.
3. Users can download template, upload valid CSV, and run optimization.
4. Invalid CSV produces clear, specific error output.
5. Existing tests remain passing; new tests cover phase features.

At the end, provide:
1. Files changed
2. Data dictionary for CSV columns
3. Known limitations and deferred improvements
```

---

## Phase 4 Prompt — Monte Carlo Redesign (Randomize Inputs, Then Optimize)

```text
Implement Phase 4: robust Monte Carlo workflow where uncertain parameters are sampled first, then optimization is run per scenario.

Goals:
1. Replace post-optimization randomization with pre-optimization scenario sampling.
2. Start with n=100 scenarios.
3. Keep Monte Carlo in Advanced section.
4. Produce decision-useful robustness outputs.

Scope constraints:
1. Keep baseline deterministic solve unchanged.
2. Monte Carlo must be optional and isolated from core run path.
3. No labor-as-decision-variable changes in this phase.

Required behavior:
1. Define uncertainty config for selected parameters (e.g., rainfall, yield, labor availability, input costs).
2. Sample n=100 scenarios with reproducible seed control.
3. Run optimization for each scenario.
4. Aggregate and display:
- profit distribution (mean, p10, p50, p90)
- crop/succession selection frequency
- robust recommendations (stable winners vs fragile choices)
- top parameter-profit sensitivity indicators
5. Add explanatory copy on interpretation and limitations.

Performance constraints:
1. Keep UI responsive (progress indicator and cancel option if feasible).
2. If runtime is high, apply staged optimization strategy and report tradeoffs.

Testing:
1. Add tests for scenario generation reproducibility.
2. Add tests for aggregation correctness.
3. Ensure baseline deterministic mode remains unaffected.

Acceptance criteria:
1. Monte Carlo runs at n=100 and returns interpretable aggregate outputs.
2. Baseline solve path remains unchanged.
3. Advanced tab gating remains in place.

At the end, report:
1. Runtime profile and bottlenecks
2. Statistical assumptions used
3. Recommended next optimization steps
```

---

## Phase 5 Prompt — Optional Labor Flex as Decision Variable

```text
Implement Phase 5 as an optional advanced mode: labor flexibility as decision variable.

Goals:
1. Keep default behavior as current labor-input constraints.
2. Add optional labor-flex mode that allows optimizer to purchase additional labor within realistic bounds.
3. Keep model explainable and computationally stable.

Scope constraints:
1. Start with continuous labor-flex variable(s) only.
2. Do not add new binary staffing activation variables in this phase.
3. Keep labor-flex mode off by default and clearly labeled Advanced.

Required behavior:
1. Add advanced controls for:
- overtime/additional labor cost per hour
- max additional labor capacity by period
2. Add solver variables/constraints needed for continuous labor flex.
3. In results, show:
- additional labor used
- incremental labor cost
- net profit impact
- changes to bottleneck ranking
4. Add clear interpretation text and caveats.

Testing:
1. Add tests verifying baseline mode is unchanged.
2. Add tests for labor-flex mode feasibility and accounting.
3. Add regression checks for objective components with labor-flex enabled.

Acceptance criteria:
1. Baseline mode unchanged and passing existing tests.
2. Labor-flex mode runs and reports transparent tradeoffs.
3. UI clearly distinguishes input-constrained vs optimized-labor runs.

At the end, report:
1. Mathematical formulation added
2. Performance impact
3. Recommended future enhancements (if binary staffing is desired)
```

---

## Phase 1 Patch — Bug Fixes + Wizard Cleanup + Hub Help Text

```text
Fix three issues in Phase 1 implementation:

1. Fix Executive Summary bugs:
   - In renderExecutiveSummary() function, line where profit is read:
     Change: res.total_profit
     To: res.profit
   - In renderExecutiveSummary() function, where crop channel data is accessed:
     Change: crop.channels_data
     To: crop.channels
   These should be one-line fixes. Run a quick test to verify executive summary displays correctly after solving.

2. Simplify the wizard to reduce friction:
   - Delete the wizard prompt modal entirely (id='wizard-prompt').
   - Delete startWizard(), dismissWizardPrompt(), wizardNext(), wizardPrev() functions.
   - Delete wizard-related state tracking (APP_STATE.wizardMode, related logic).
   - Keep the hub cards and hub navigation intact — no changes to core hub behavior.
   - Users should still be able to click hub cards and navigate sections normally.

3. Add contextual help text to hub section cards:
   - Before each section gets rendered by renderHub(), add a brief introductory sentence to the hub card description.
   - Look at SECTION_META in the code — expand the "desc" field for each section to be more instructional.
   - Examples:
     'farm-basics': "Tell us about your farm size, budget, and storage infrastructure — this sets your constraints."
     'water': "Configure your water sources: well, catchment, or city supply. We'll calculate weekly availability."
     'labor-channels': "Define your workforce and sales channels — labor availability and market access drive profit."
     'crops': "Add your crop varieties with planting dates, yields, and pricing per channel."
     'review': "Review all your parameters and run the optimizer."
   - These descriptions should appear in the hub card's hub-card-desc element.

Goals:
- Executive summary now displays correctly on first solve (not showing "—")
- Wizard removed to reduce complexity and first-time friction
- Hub descriptions give users immediate context for what each section does
- No changes to solver, parameters schema, or core logic

Acceptance criteria:
1. Executive summary shows profit and highest-margin crop after solve
2. Wizard code is completely removed; no dangling references
3. Hub cards display updated descriptive text
4. App still runs end-to-end without errors
5. Tests still pass

At the end, provide:
1. Files changed
2. Lines/functions removed (wizard-related)
3. Any edge cases or warnings discovered
```

---

## Phase 1.1 Patch — Results Consolidation + Annualized Margin + Demand-Aware Insights

```text
Make a focused polish pass on the current Phase 1 results and executive summary.

Primary issues to fix:
1. Profit displayed in executive summary differs from "Net Profit" KPI widget (redundancy + confusion).
2. Highest-margin calculation does not account for crop cycle time.
3. Recommendation text is generic and not decision-useful (missing demand-side insight).
4. Some sections do not clearly explain what is required, optional, or safe to leave at defaults.

Scope constraints:
1. Keep solver math unchanged.
2. Keep parameter schema unchanged.
3. Do not start Phase 2 scenario runner work in this patch.
4. Defer crop-level toggleability (enable/disable) to Phase 3.

Required updates:
1. Consolidate profit display in results:
- Delete the "Net Profit" KPI widget from the results pane (currently shows res.profit - sum(channel fixed costs)).
- Add "Peak Borrowing" metric to the executive summary grid instead.
- Use res.profit consistently as the canonical profit figure (direct from solver).

2. Replace simple margin calculation with annualized margin per acre:
- Current logic: margin = yield_per_acre × price - variable_cost_per_acre (penalizes fast-cycle crops)
- New logic: annualized_margin = (yield × price - vc) × (365 / days_to_maturity)
  Example: Spinach 90-day, $500/ac → $500 × (365/90) = $2,028/year
  Example: Garlic 210-day, $800/ac → $800 × (365/210) = $1,390/year
- Display as: "Spinach (Farmers Market) — $2,028/year per acre"
- This favors high-velocity crops correctly.

3. Improve section-level guidance for input optionality:
- Add concise helper text in each section panel that states:
  a) What is required to run the optimizer
  b) What can be left at defaults
  c) Which toggles disable related fields
- Add a visible note in Review and Run: "All unfilled optional fields will use defaults. Adjust any values above if you have actual farm data."

4. Add demand-aware secondary insight to recommendation:
- Keep one primary bottleneck line (land/labor/water/storage).
- Add a second line identifying market-side constraint:
  a) If top crop/channel is at >80% demand cap: "Spinach demand on Farmers Market at 85% cap — room for $X more profit if you can expand market."
  b) If no demand cap binds strongly: "Demand caps provide headroom across all crops and channels — production constraints are primary."
- Use percentage-based utilization messages so users can interpret market pressure.

Acceptance criteria:
1. "Net Profit" widget is deleted; "Peak Borrowing" appears in executive summary.
2. Highest-margin option uses annualized margin formula and displays yearly rate.
3. Executive summary includes both bottleneck and demand-side insight lines.
4. Section panels clearly communicate required vs optional/defaulted inputs.
5. App runs end-to-end without solver/schema changes.
6. Tests still pass.

At the end, provide:
1. Files changed
2. Key logic changes in executive summary and results layout
3. Any assumptions used for annualized margin and demand-utilization interpretation
```

---

## Overreach Stop Prompt (use immediately if needed)

```text
Scope correction required.

You are overreaching beyond the current phase. Stop adding new features.

Do this now:
1. Re-scope to the current phase only.
2. Revert any work that belongs to later phases.
3. Keep solver math unchanged unless explicitly required by current phase.
4. Run tests and report exact pass/fail.
5. Provide a concise list of what was kept vs deferred.
```
