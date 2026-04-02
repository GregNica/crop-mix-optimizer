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

## Phase 3.1 Patch — MC-Scope Template Alignment + Section Assumptions Boxes

```text
Implement a focused Phase 3.1 correction pass after Phase 3.

Primary goals:
1. Align import-template scope to Monte Carlo-relevant uncertainty inputs only.
2. Upgrade template delivery from CSV to XLSX with explicit Instructions guidance.
3. Add static, collapsible assumptions/limitations boxes to each hub section page.

Scope constraints:
1. Do not modify optimization math, objective, or constraints.
2. Do not redesign full Monte Carlo engine in this phase.
3. Do not add labor-as-decision-variable in this phase.
4. Keep manual form-entry path fully backward-compatible.

Required updates:

1. Template scope alignment (Monte Carlo inputs only):
- Restrict template data fields to uncertainty inputs only:
  a) yield,
  b) demand,
  c) price (selected third variable).
- Do not include broad crop-setup/infrastructure fields in this template pass.
- Keep existing crop-form/manual workflows unchanged.

2. XLSX template with strict structure:
- Provide downloadable XLSX template (preferred over CSV).
- Include at minimum two sheets:
  a) Instructions,
  b) Data.
- Instructions sheet must specify strict formatting requirements:
  a) required columns,
  b) allowed value formats and categorical values,
  c) units,
  d) examples,
  e) common validation failures and fixes.
- Data sheet parser must enforce strict schema and reject malformed uploads.
- Maintain row-level and field-level error reporting with actionable messages.

3. Assumptions/limitations boxes on section pages:
- Add a static assumptions/limitations box on each hub section page:
  a) Farm Basics,
  b) Water,
  c) Labor and Channels,
  d) Crops.
- Box must be collapsible (collapsed/expanded state clearly indicated).
- Content can be static text in this phase (no dynamic generation required).
- Include practical assumptions and limits relevant to each section.
- Write assumptions in plain, farmer-friendly language; avoid heavy technical jargon.
- Keep assumptions interpretable and decision-useful from an operator perspective.
- Include this water-model caveat explicitly (or equivalent plain-language wording):
  "Rainfall inputs for both field demand offset and catchment supply are based on average historical rainfall, so short-term seasonal swings and storm timing are not fully captured."
- Optional styling pattern: mirror benchmark-source presentation style where it improves readability.

Implementation notes:
1. Keep XLSX import parsing logic isolated from solver logic.
2. Map validated data into existing app parameter structures only after validation passes.
3. Keep existing benchmark defaults/provenance behavior intact.
4. Preserve existing tests and add focused tests for this patch.

Testing requirements:
1. XLSX template generation includes Instructions and Data sheets.
2. Instructions sheet content includes strict formatting rules and accepted values.
3. Parser happy path for valid XLSX imports.
4. Parser failure tests for schema/type/value violations.
5. Assumptions/limitations box exists on each hub section and is collapsible.
6. Assumptions/limitations copy test: text is plain-language, user-interpretable, and includes rainfall-average caveat.

Acceptance criteria:
1. Users can download an XLSX template with a clear Instructions sheet.
2. Uploaded XLSX with valid Yield/Demand/Price rows is accepted and mapped correctly.
3. Invalid XLSX produces specific row/field validation feedback.
4. Each hub section page shows a collapsible static assumptions/limitations box.
5. Assumptions/limitations text is plain-language and farmer-interpretable (including rainfall-average caveat).
6. No solver math, objective, or constraint changes.
7. Existing tests pass; new tests cover this patch behavior.

At the end, provide:
1. Files changed
2. XLSX data dictionary (Data sheet columns + allowed values)
3. Assumptions/limitations text used per section
4. Known limitations and deferred improvements
```

---

## Phase 3.2 Patch — Placement UX + Readability + Provenance Relayout + Weekly Sales Breakdown

```text
Implement a focused Phase 3.2 refinement after Phase 3.1.

Primary goals:
1. Improve placement/usability of uncertainty uploads so controls are near the parameters they affect.
2. Improve readability and trust UX for assumptions and benchmark sources.
3. Expand Weekly Crop Mix into a channel-aware weekly sales breakdown with export.
4. Add historical rainfall upload path for Monte Carlo (with clear data-source instructions).

Scope constraints:
1. Keep core optimization model math unchanged in this phase.
2. Do not implement full inventory state-tracking in this phase.
3. Keep existing manual form-entry behavior backward-compatible.

Required updates:

1. Move/duplicate uncertainty upload controls adjacent to related sections:
- Crops section: place Yield uncertainty template/upload affordance near crop-level yield controls.
- Labor and Channels section: place Price + Demand uncertainty template/upload affordance near channel pricing/demand controls.
- Water section: after rainfall caveat text, add rainfall historical XLSX upload affordance labeled as optional for higher-fidelity weather input.
- Maintain one coherent parser pathway; avoid inconsistent duplicate logic.

2. Historical rainfall XLSX input for Monte Carlo:
- Add/download a strict rainfall-history XLSX template with Instructions + Data sheets.
- Data should support weekly rainfall history for approximately 25-50 years.
- Instructions must direct users to credible US government data portals (for example NOAA/NCEI) and explain required weekly formatting.
- Validation must enforce required columns, numeric types, week bounds, and year coverage.
- Integrate uploaded rainfall history into Monte Carlo weather variability handling (empirical/bootstrapped weekly variability is acceptable).
- Keep deterministic baseline behavior clear (if no rainfall upload, use existing baseline rainfall defaults).

3. Assumptions/limitations readability fix:
- Improve contrast and legibility of assumptions/limitations boxes (background, font color, and emphasis hierarchy).
- Preserve collapsible behavior.
- Keep language plain and farmer-interpretable.

4. Benchmark source presentation redesign:
- Remove inline per-field source badges from each form item.
- Add a collapsible "Benchmark Sources" block at the bottom of each relevant section (parallel to assumptions style).
- In each source block, list source entries by parameter so users can see source-to-parameter mapping clearly.
- Do not place benchmark defaults/source table inside Executive Summary results card.

5. Labor guidance clarification:
- Update labor guidance copy to explicitly state that hourly-rate entry applies to seasonal designation in this workflow.
- Ensure wording in both section guidance and helper text is consistent.

6. Crop template provenance verification + surfacing:
- Audit crop template benchmark dataset for source metadata coverage.
- If missing, add source metadata for crop template benchmarks.
- Surface crop-template sources in collapsible source blocks (not inline badges).

7. Weekly Crop Mix expansion to Weekly Crop Breakdown:
- Rename section to "Weekly Crop Breakdown".
- Keep week slider behavior.
- Add one pie chart per sales channel for selected week.
- Each channel pie:
  a) slices are crops sold in that channel that week,
  b) slice label includes lbs sold,
  c) percentage basis = crop lbs / total lbs sold in that channel that week.
- Keep existing land-based weekly crop visualization if practical, but clearly label land vs sales views to avoid ambiguity.

8. Sales export from Weekly Crop Breakdown:
- Add CSV export button in this section.
- Export schema: week, crop, channel, lbs_sold (at minimum), with stable column ordering and clear headers.

9. Inventory assumption disclosure (no full inventory engine yet):
- Add explicit assumption text that sales are currently treated as sold in harvest week and inventory carry is not modelled.
- Add plain-language workaround note in assumptions (proxy succession approach), with caveats about harvest storage accuracy.
- Do not implement full inventory accounting in this phase.

Testing requirements:
1. P0 bugfix: MC XLSX apply path correctly targets existing crop DOM structure (no selector mismatch such as .crop-card vs .crop-detail).
2. Section-adjacent upload controls exist and trigger intended parsers.
3. Rainfall-history XLSX happy path and validation failures are covered.
4. Assumptions/source collapsibles are present and readable.
5. Inline benchmark badges removed; collapsible source mapping present.
6. Executive summary no longer shows benchmark defaults table.
7. Weekly Crop Breakdown renders per-channel pies with lbs + % by channel total.
8. Sales CSV export includes crop-channel-week rows with valid data.

Acceptance criteria:
1. P0 bugfix is resolved: MC XLSX upload applies updates to the intended crop cards/fields in the current UI structure.
2. Uncertainty upload actions are placed near relevant parameter sections.
3. Rainfall-history upload path is available with government-source instructions and strict validation.
4. Assumptions blocks are readable and farmer-friendly.
5. Benchmark sources are shown in collapsible bottom sections, mapped by parameter.
6. Labor guidance clearly states hourly-rate availability rule for seasonal designation.
7. Crop template benchmark source coverage is explicit.
8. Weekly Crop Breakdown includes channel-specific pie charts and sales CSV export.
9. Inventory limitation is explicitly disclosed; no full inventory model added.
10. Existing tests pass; new tests cover this patch.

At the end, provide:
1. Files changed
2. Rainfall XLSX data dictionary + validation rules
3. Benchmark source mapping format used in collapsible blocks
4. Weekly sales export schema
5. Known limitations and deferred items
```

---

## Phase 3.3 Patch — Weekly Breakdown + Rainfall MC Wiring Stabilization

```text
Implement a focused Phase 3.3 stabilization patch after Phase 3.2.

Primary goals:
1. Fix Weekly Crop Breakdown sales rendering regressions (per-channel pies showing no harvest activity when harvest exists).
2. Lock weekly sales export schema and headers to the agreed format.
3. Ensure rainfall-history uncertainty is actually propagated into Monte Carlo scenario solves through the water-side pathway.
4. Keep all changes backward-compatible with existing/legacy input schemas.

Scope constraints:
1. Keep optimization model math unchanged.
2. Do not implement full inventory carry state-tracking.
3. Do not alter deterministic baseline behavior except where needed to preserve explicit fallback semantics.
4. Keep existing manual and template workflows compatible.

Required updates:

1. Weekly Crop Breakdown sales computation hardening:
- In weekly sales estimation logic, support both legacy and current crop/channel key shapes (for example channel fields and demand/price fields).
- Support robust harvest-phase detection for numeric and string encodings (for example 2, "2", "H", "harvest"), not only one strict encoding.
- Prevent false all-zero weeks when harvest phases are present.
- Keep weekly land-view logic intact; only harden sales-view computation.

2. Per-channel pie rendering correctness:
- Ensure each channel pie receives non-empty data when that channel has weekly sold lbs.
- Ensure percentages are based on channel-week total sold lbs.
- Keep "no harvest activity" messaging only for true zero-sales weeks.

3. Weekly sales CSV schema lock:
- Export header/order must be stable and include:
  week, crop, channel, lbs_sold
- Remove/avoid alternate header names (for example lbs_sold_est) in this path.

4. Rainfall-history MC propagation check:
- Ensure each Monte Carlo run can pass rainfall-week variability inputs (52-week vector) into the solve payload.
- In the solver bridge, apply rainfall multipliers to rainfall-side inputs used by water constraints/capacity calculations.
- Keep deterministic fallback explicit: if no rainfall-history upload exists, use baseline/default rainfall behavior.
- Keep rainfall impact on water-side resource pathway only (no direct yield mutation in this patch).

5. Rainfall-history validation threshold alignment:
- Enforce a practical minimum-history threshold suitable for weekly bootstrap stability.
- Keep stronger-history recommendation messaging (for example, recommended years) separate from hard reject threshold.

6. Runtime UX verification points:
- Verify week slider traverses harvest weeks and shows populated channel pies where expected.
- Verify export output contains crop-channel-week rows with non-zero lbs where appropriate.
- Verify Monte Carlo outputs shift when rainfall-history upload is present vs absent.

Testing requirements:
1. Weekly sales estimator tests for mixed schema compatibility (legacy + current field names).
2. Harvest-phase decoding tests for numeric and string variants.
3. Pie-data tests ensuring channel totals and percentages are correct.
4. CSV export header/order test: week,crop,channel,lbs_sold.
5. Rainfall MC payload propagation test (weekly multipliers included per scenario).
6. Rainfall bridge application test (water-side rainfall array modified by multipliers when provided).
7. No-regression test confirming deterministic baseline remains valid without rainfall-history upload.

Acceptance criteria:
1. Weekly Crop Breakdown channel pies render correctly for harvest weeks (no false global "no harvest" states).
2. Sales export uses stable schema with lbs_sold header.
3. Rainfall-history Monte Carlo path materially affects scenario water-side behavior when upload is provided.
4. Baseline behavior remains unchanged when rainfall-history upload is absent.
5. Existing tests pass and new tests cover stabilization fixes.

At the end, provide:
1. Files changed
2. Weekly sales estimator compatibility rules implemented
3. Rainfall multiplier data flow summary (UI -> payload -> solver bridge)
4. Final weekly CSV schema
5. Known limitations and deferred items
```

---

## Phase 3.4 Patch — Weekly Breakdown Corrections + Input Mode Clarity + MC Template Redesign

```text
Implement a focused Phase 3.4 correction patch after Phase 3.3 to resolve remaining weekly-breakdown defects and Monte Carlo input UX/data-template issues.

Primary issues to fix:
1. Weekly Crop Breakdown channel pies are incorrect/incomplete (Farmers Market missing or showing only one crop).
2. Weekly sales CSV structure is not decision-useful for channel comparison.
3. Monte Carlo upload controls on the initial screen are misleading.
4. "My Farm Data" mode behavior is too similar to Benchmark Defaults.
5. Required-field signaling is insufficient.
6. Rainfall historical XLSX structure is not optimized for copy/paste multi-year user data.
7. Yield/Price/Demand MC XLSX structure and file separation are not practical for partial data availability.

Scope constraints:
1. Keep optimization model math unchanged (objective/constraints unchanged).
2. Keep deterministic baseline behavior unchanged except for UI/input-path corrections.
3. Keep existing manual workflows backward-compatible.
4. Do not implement full inventory carryover/accounting in this phase.

Required updates:

1. Weekly Crop Breakdown correctness pass:
- Fix per-channel sales allocation/rendering so Farmers Market and Wholesale pies both populate when channel sales exist.
- Ensure channel slices include all crops with non-zero sold lbs for that week (not only one crop due to key/filter mismatch).
- Preserve no-harvest messaging only for true zero-sales channel-week.
- Keep land-use pie behavior unchanged.

2. Weekly sales CSV format update:
- Replace long format export with a wide comparison-friendly layout.
- Required columns:
  week,
  crop,
  lbs_sold_wholesale,
  lbs_sold_farmers_market
- Keep stable header order.
- For compatibility, allow optional additional channel columns if more channels exist (deterministic naming: lbs_sold_<channel_slug>).

3. Monte Carlo upload placement cleanup:
- Remove/hide MC upload widget from the initial screen to avoid implying it is required before setup.
- Keep MC uncertainty uploads only in relevant section-adjacent locations (Water, Crops, Labor and Channels).

4. "My Farm Data" mode behavior correction:
- Benchmark Defaults mode: keep existing benchmark prefill behavior.
- My Farm Data mode: clear benchmark-provided editable inputs (farm/labor/channel/crop numeric fields), while preserving:
  a) default crop card shells/templates,
  b) rainfall/climate zone selector defaults.
- Make mode behavior explicit in helper copy so users understand what is retained vs cleared.

5. Required-field indicators:
- Add visible red asterisk markers to required labels/controls across sections.
- Ensure required markers align with actual solve validation requirements.
- Add/adjust helper text to avoid marking optional MC inputs as required.

6. Rainfall historical XLSX redesign:
- Redesign rainfall template Data sheet to be matrix-style for easy paste from historical records:
  rows: week (1..52)
  columns: Year_1 ... Year_50 (user may delete unused year columns)
- Add auto-calculated columns in template:
  avg_rainfall,
  stddev_rainfall
- Parser behavior:
  a) accept variable number of year columns,
  b) tolerate missing years/gaps,
  c) compute/verify mean and std dev from provided yearly values (do not require user formulas),
  d) treat each year column as one historical scenario for MC rainfall sampling.

7. Yield/Price/Demand MC template redesign and separation:
- Support partial-data workflows by splitting templates so one dataset can be uploaded without requiring the others.
- Implement separate XLSX templates and upload paths:
  a) Yield uncertainty template (rows by crop; columns by year + optional avg/stddev),
  b) Price uncertainty template (rows by crop/channel; columns by year + optional avg/stddev),
  c) Demand uncertainty template (rows by crop/channel; columns by year + optional avg/stddev).
- If keeping a combined price-demand workflow for backward compatibility, place price and demand on separate tabs and do not require both tabs to be populated.
- Allow users to delete irrelevant year columns; parser must accept remaining year columns and compute distribution stats from what is provided.

Testing requirements:
1. Weekly pie regression tests:
- Farmers Market pie shows data when non-zero FM sales exist.
- Multiple crops can appear in the same channel pie in harvest weeks.
2. Weekly CSV export test for required wide schema and stable header order.
3. Initial-screen UX test confirming MC upload controls are not shown there.
4. Data-mode behavior tests:
- Benchmark mode applies defaults.
- My Farm mode clears benchmark-editable values while preserving crop shells and rainfall/climate defaults.
5. Required-marker tests for key required controls and optional MC controls.
6. Rainfall template/parser tests for:
- week x year matrix format,
- variable year-column count,
- avg/stddev compute/validation behavior.
7. Yield/Price/Demand template/parser tests for:
- independent uploads,
- missing companion files tolerated,
- per-row yearly sampling arrays built from available columns.
8. No-regression tests for deterministic solve path with no MC uploads.

Acceptance criteria:
1. Weekly channel pies correctly show both channels and all qualifying crops by week.
2. Weekly CSV export uses wide per-channel sold-lbs columns with stable naming/order.
3. MC upload is not shown on initial screen and remains available near relevant sections.
4. My Farm mode is behaviorally distinct from Benchmark mode and clearly documented in UI copy.
5. Required fields are visibly marked with red asterisks and align with validation rules.
6. Rainfall template supports week x multi-year columns with transparent avg/stddev handling.
7. Yield, Price, and Demand MC uploads can run independently with separate templates.
8. Existing tests pass and new tests cover the correction set.

At the end, provide:
1. Files changed
2. Weekly sales pie/root-cause summary and fix rules
3. Final weekly CSV schema (exact headers)
4. My Farm vs Benchmark behavior matrix
5. Rainfall + Yield/Price/Demand template data dictionaries and parser rules
6. Known limitations and deferred items
```

---

## Phase 3.4.1 Hotfix — Weekly Pie + CSV Lock (Only)

```text
Implement a strict Phase 3.4.1 hotfix that addresses only the original first three unresolved items from post-3.3 feedback.

Primary goals (do not expand beyond these):
1. Fix Weekly Crop Breakdown channel-pie rendering (Farmers Market missing/empty when sales exist).
2. Fix Farmers Market crop composition so it is not incorrectly limited to Napa Cabbage only.
3. Lock weekly sales CSV to the agreed per-week/per-crop wide channel columns.

Hard scope guardrails:
1. Do not implement or modify items 4-9 from the broader Phase 3.4 list in this hotfix.
2. Do not change optimization model math, constraints, or objective.
3. Do not alter My Farm/Benchmark mode behavior in this hotfix.
4. Do not alter MC template architecture in this hotfix.

Required updates:
1. Weekly pie-channel data pipeline correction:
- Ensure channel-level pie inputs are populated from the same sold-lbs source used by weekly breakdown logic.
- Ensure both default channels (Wholesale, Farmers Market) render when non-zero sold lbs exist.
- Ensure no channel is silently filtered out due to key-shape mismatch, case mismatch, or fallback-path mismatch.

2. Farmers Market crop slice correctness:
- Ensure Farmers Market slices include all crops with non-zero Farmers Market sold lbs for selected week.
- Prevent collapse to a single crop due to aggregation, overwrite, or stale object reuse.
- Keep percentage basis = crop lbs / channel-week total lbs.

3. Weekly CSV schema lock (hotfix target schema):
- Export must be wide format with stable headers:
  week,
  crop,
  lbs_sold_wholesale,
  lbs_sold_farmers_market
- Preserve deterministic row ordering (week asc, then crop asc).
- Keep optional extensibility for extra channels only if it does not break required default columns above.

Mandatory evidence and verification (must provide):
1. Before vs after evidence for one known harvest week in default demo:
- channel totals for Wholesale and Farmers Market,
- crop list present in each channel pie.
2. Explicit assertion that Farmers Market includes more than one crop when data supports it.
3. Exact exported CSV header line and first 5 data rows.
4. Root-cause explanation naming the exact broken mapping/filter path fixed.

Testing requirements:
1. Pie rendering test: Farmers Market pie non-empty when Farmers Market sold lbs > 0.
2. Pie composition test: Farmers Market can contain multiple crop slices in harvest week.
3. Channel parity test: if Wholesale and Farmers Market both have non-zero sales, both pies render.
4. CSV schema test: exact header match to
   week,crop,lbs_sold_wholesale,lbs_sold_farmers_market
5. CSV ordering test: week asc, crop asc.
6. No-regression test: weekly land-use pie remains unchanged.

Acceptance criteria:
1. Default demo run no longer shows false-empty Farmers Market pie when data exists.
2. Farmers Market section no longer collapses to Napa Cabbage only when other crops have non-zero FM sales.
3. Exported CSV uses required wide schema and stable ordering.
4. Existing tests pass plus new hotfix tests above.

At the end, provide:
1. Files changed
2. Exact root cause fixed for pie-channel bug
3. Exact CSV schema and sample rows
4. Test list with pass/fail
5. Deferred items explicitly listed (confirming 4-9 were not changed)
```

---

## Phase 3.4.2 Hotfix — Constraint Export + P&L Channel Revenue + Pie 100% + My Farm Clearing

```text
Implement a strict Phase 3.4.2 hotfix that addresses exactly the five post-3.4.1 feedback items below.

Primary goals:
1. Constraint utilization export must include week-level cap-hit and near-hit evidence.
2. P&L export must stop showing "N/A" for Revenue by channel.
3. Margin % presentation must remove denominator confusion and explain negative cases correctly.
4. Weekly crop/channel pie must render correctly when one crop is 100% of a pie.
5. My Farm mode must clear benchmarked values in Labor/Channels and Crops while preserving explicit template selectors.

Hard scope guardrails:
1. Do not modify optimization objective, constraints, or solver feasibility behavior.
2. Do not implement inventory carryover, storage aging, or demand model redesign in this hotfix.
3. Do not redesign page layout or section navigation.
4. Keep all changes backward-compatible with existing saved/default demo inputs.

Required updates:
1. Constraint export detail enhancement:
- Extend the constraint CSV schema to include per-constraint week evidence fields.
- At minimum include: peak_util_pct, weeks_at_cap_count, weeks_within_10pct_count, and representative week lists.
- Definitions:
  - at cap: utilization >= 100%
  - within 10%: utilization >= 90%
- Apply to time-series constraints (land, labor, water, storage, cash where meaningful). For demand constraints, document non-weekly basis clearly.

2. P&L "Revenue by channel" NA fix:
- Eliminate NA for channels when enough data exists to compute channel revenue.
- If solver payload does not provide channel_revenue, compute fallback from existing weekly sold-lbs/channel structures and channel prices.
- Keep method explicit in comments/UI note: reported per-channel revenue is computed basis (or exact solver basis when provided).
- Only show NA when channel truly has no computable basis.

3. Margin % clarification and consistency:
- Ensure displayed margin percent is consistently:
  contribution_margin / gross_revenue * 100.
- Add concise tooltip/copy that negative margin is valid when total variable cost exceeds gross revenue for that crop-channel row.
- Ensure terminology distinguishes margin % (of revenue) vs markup % (of cost).
- Add one deterministic validation row/example in tests where VC < revenue => margin % must be non-negative.

4. Pie rendering edge case (100% single slice):
- Fix SVG pie draw logic so a full-share single slice renders as a full circle instead of disappearing.
- Keep multi-slice behavior unchanged.
- Guard against floating-point edge cases near 100% and near 0%.

5. My Farm mode clearing behavior:
- On switch to My Farm mode, clear benchmark-applied editable values in Labor/Channels and Crops sections (not just BENCHMARK_DEFAULTS keys).
- Preserve explicit template/selector defaults that should remain by design (e.g., climate zone, crop card shells, structural dropdowns).
- Ensure benchmark badges/override state remains consistent after mode switch.

Mandatory evidence and verification (must provide):
1. Updated constraint CSV header and 5 sample lines showing week evidence fields populated.
2. P&L CSV sample showing non-NA per-channel revenue for default demo channels.
3. Margin % proof cases:
- one row with VC < revenue and positive margin %,
- one row with VC > revenue and negative margin %.
4. Weekly pie screenshot/data proof for a week where one channel has exactly one crop slice at 100%.
5. My Farm mode before/after field matrix for Farm Basics, Labor/Channels, Crops.

Testing requirements:
1. Constraint export test: week evidence columns exist and counts are numerically consistent with utilization arrays.
2. P&L export test: Revenue by channel is computed (not NA) when channel sales and prices exist.
3. Margin test: denominator uses revenue; sign behavior matches margin arithmetic.
4. Pie rendering test: 100% single-slice pie produces visible filled circle.
5. Mode-switch test: My Farm clears benchmarked editable fields across all relevant sections while preserving allowed template selectors.
6. Regression test: benchmark mode still re-applies benchmark defaults correctly.

Acceptance criteria:
1. Constraint export includes week-level cap-hit/near-hit evidence fields.
2. Revenue by channel no longer defaults to NA in normal solvable runs.
3. Margin % behavior and labels are mathematically and semantically consistent.
4. Weekly pie renders correctly for 100% single-crop composition.
5. My Farm mode behavior matches user expectation: editable benchmark values cleared across sections, template selectors preserved.
6. Existing tests pass and new hotfix tests cover all five items.

At the end, provide:
1. Files changed
2. Root cause + fix summary for each of the 5 items
3. Updated CSV schemas (constraint + P&L)
4. Test list with pass/fail
5. Deferred items explicitly listed
```

---

## Phase 3.4.3 Hotfix — What-If Baseline Integrity + Scenario Solver State Verification

```text
Implement a focused Phase 3.4.3 diagnostic hotfix to validate baseline optimization and scenario solver consistency.

**User-Reported Issue (Economically Implausible):**
When running What-If scenarios from benchmark demo:
- Baseline land utilization: 67.1% (≈100.6 acres used of 150 total)
- User scaled demand cap for Spinach/Farmers Market by +10%
- Result: Land utilization jumps to 100% (≈50 additional acres suddenly planted)
- Profit improves only +$55,220 (2.15% gain on 50% more land use)

**Economic Red Flag:**
- Using 50 additional acres should yield significantly more than 2.15% profit
- This implies the new plantings are very low-margin OR the baseline was not actually optimized
- If the farm is truly optimized at 67% utilization, why are 50 profitable acres sitting unused?
- If those 50 acres ARE profitable, the baseline is suboptimal (bug in baseline initialization)

**Root Cause Hypotheses (Must Test):**

1. **Baseline was never fully optimized:**
   - Benchmark baseline computed with partial constraints or wrong solver mode
   - When What-If re-solves with full constraint set, it finds optimal (67% → 100%)
   - Test: Re-solve baseline with NO scaling — does land stay at 67% or jump to 100%?

2. **Solver state difference:**
   - Baseline computed with different solver parameters, precision, or initialization than scenario
   - Scenario solver finds a dormant local optimum not discovered in baseline
   - Test: Run baseline solve twice with identical params — are results identical? (should be yes)

3. **Baseline constraint subset:**
   - Baseline uses a subset of constraints (e.g., missing a resource cap)
   - Scenario run applies full constraint set, revealing previously hidden capacity
   - Test: Inspect which constraints were active in baseline vs scenario

4. **Profit margin calculation error:**
   - The +$55k profit gain is real but applied to wrong land fraction
   - Model thinks 50 new acres are planted when actually less were planted
   - Test: Decompose profit delta (revenue from new plantings - costs = $55k)

**Required Fixes & Verification:**

1. **Baseline Replay Test:**
   - Store baseline params/constraints that were used to compute 67% utilization baseline
   - Re-run solver with IDENTICAL params/constraints
   - Assert that result land utilization ≈ 67.1% ± 0.5pp
   - If result differs: baseline is not reproducible (solver state bug)
   - If result matches: good news, baseline was reproducible; question is why it's suboptimal

2. **Baseline Optimality Check:**
   - Verify that the benchmark baseline params include ALL constraints (land, labor, water, storage, demand caps, etc.)
   - If any constraint is disabled/missing in baseline: that's the bug
   - Test: Enable the missing constraint and re-solve — does it change land utilization?

3. **Scenario Solver Consistency:**
   - When What-If scales a constraint and re-solves, does it:
     a) Use identical solver parameters as baseline?
     b) Use identical initialization/seed?
     c) Use identical constraint set?
   - If NO to any: document the difference
   - Test: Run scenario 3 times with same params — do results match? (should be deterministic)

4. **Profit Delta Decomposition:**
   - Break down the +$55k profit gain:
     - Revenue from new Spinach/FM units sold: +$X
     - Revenue lost from crops displaced: -$Y
     - Net revenue: +$Z
     - Variable costs for new plantings: -$C
     - Net profit gain: +$Z - $C = $55k
   - Expected: If 50 acres are newly planted, revenue change should be ~50 * (yield/acre * price)
   - Reality: Is revenue change proportional to land change? Or does profit come from inefficient reblending?
   - Test: Verify profit delta calculation is correct and proportional

5. **Baseline Cropping Plan:**
   - Export the baseline cropping plan (acres per crop): Spinach #1–#5, Cucumbers, Corn, Cabbage, Peppers, Garlic
   - Export the scenario +10% cropping plan
   - Compare: which crops increased/decreased? Is the reallocation sensible?
   - Test: Verify that only low-margin crops decreased, high-margin crops increased

6. **Unused Land Hypothesis:**
   - In baseline at 67% utilization: which land is UNUSED and WHY?
   - Is it unused because:
     a) Labor constraint prevents planting (too busy harvest weeks)?
     b) Water constraint prevents planting (dry weeks)?
     c) Storage constraint prevents planting (can't store extra harvest)?
     d) Budget constraint prevents planting (not enough capital)?
     e) Demand caps prevent planting (no market for that crop)?
     f) Model initialization bug (land was never added to solver variables)?
   - Test: For each constraint type, check "binding at baseline" vs "slack"
   - If land constraint is slack at 67%, then large unused land IS available and should be used — baseline is suboptimal

**Mandatory Evidence & Verification:**

1. Baseline reproducibility: re-solve baseline → should get 67.1% ± 0.5pp
2. Constraint completeness: all 6 constraint types active in baseline
3. Solver consistency: scenario run is deterministic (multiple runs → same result)
4. Profit delta decomposition: +$55k accounted for by crop mix change
5. Unused land root cause: constraint type that's binding (preventing planting)
6. Cropping plan diff: which crops drove the 67% → 100% change

**Acceptance Criteria:**

1. Baseline reproducibility confirmed or root cause identified
2. Baseline params/constraints fully specified and verified
3. Solver produces deterministic results (same input → same output)
4. Profit delta is economically sensible given land change (profit ≥ expected ROI)
5. Unused land in baseline is constrained by an identified binding constraint
6. If baseline is truly suboptimal: explain why it was initialized suboptimally
7. If baseline is optimal: explain why +10% demand suddenly enables 50% more land (should be impossible if constrained)

**At the End, Provide:**

1. Files changed (if any)
2. Baseline reproducibility test result: PASS/FAIL + evidence
3. Constraint completeness audit: which constraints are active in baseline vs scenario
4. Solver state consistency check: deterministic results? Different parameters?
5. Profit delta breakdown: sources of +$55k gain
6. Cropping plan comparison: baseline vs scenario (+10% demand scenario)
7. Root cause determination: is this baseline init bug, solver state bug, or economically valid?
8. If bug: precise fix location and type
9. If economically valid: explanation for why 50% land increase from 10% demand increase is feasible
```

---

## Phase 3.4.4 Forensic Audit — What-If Land Jump With Unchanged Top-Crop Acreage

```text
Run a strict evidence-first forensic audit focused on the persistent What-If anomaly where land use jumps from ~67% to ~100% after +10% on nearly any constraint, while top crops/acreage appear unchanged.

Primary anomaly to validate:
1. Baseline run uses about 67% of land.
2. Applying +10% to different constraints causes ~100% land use.
3. Reported top crops remain effectively the same (example: Spinach ~109 ac, Napa Cabbage ~51 ac, Sweet Corn ~29 ac), suggesting no proportional crop-mix reorientation despite the large land jump.
4. This behavior appears economically inconsistent and may indicate scenario accounting, visualization, or state carryover defects.

Hard guardrails:
1. Do not modify solver objective, constraints, or model coefficients in this audit.
2. Do not implement fixes until evidence confirms root cause.
3. Do not rely on high-level explanations alone (for example, generic cascade effects).
4. Produce reproducible traces from baseline and scenario runs with explicit parameter vectors.

Audit objectives:
1. Determine whether the anomaly is real in solver outputs, only in UI aggregation, or due to stale/cached result blending.
2. Prove whether acreage allocation vectors actually change between baseline and +10% scenarios.
3. Explain how land utilization can increase materially with apparently unchanged top-crop acreage.
4. Identify the exact component at fault if mismatch exists:
  a) scenario parameter application,
  b) baseline pinning/state mutation,
  c) result summarization (top-crop rollup),
  d) utilization computation,
  e) rendering layer.

Required checks (must complete all):

1. Baseline reproducibility and immutability:
- Re-run baseline multiple times with identical inputs and confirm deterministic land utilization, profit, and crop-acre vector.
- Confirm baseline state object remains unchanged after any scenario execution.

2. Scenario application parity:
- For each tested +10% scenario, log exact applied scaling map and confirm only intended constraints changed.
- Verify no hidden carryover from previously selected constraints.
- Compare run labels vs applied scaling vectors.

3. Acreage-vector diff (P0):
- Export full acreage by crop and succession for:
  a) baseline,
  b) +10% labor,
  c) +10% water,
  d) +10% land,
  e) +10% demand candidate (if present).
- Compute delta table and verify whether "same top crops" is:
  a) truly same acres,
  b) small top-line changes hiding large within-crop succession shifts,
  c) UI rounding/aggregation artifact.

4. Land-utilization computation basis audit:
- Trace exact formula/path used to display "land utilization %" in:
  a) baseline cards,
  b) What-If scenario rows,
  c) any summary badges.
- Confirm all three use identical numerator/denominator definitions.
- Verify no double-counting across overlapping weeks or successions in displayed utilization.

5. Top-crop summary integrity audit:
- Trace logic that generates "top crops" labels and acreage values.
- Validate whether values are recomputed per scenario or reused from baseline cache.
- Verify rounding/truncation does not hide meaningful differences.

6. Profit-delta decomposition:
- For each +10% scenario, decompose delta profit into:
  a) gross revenue change by crop/channel,
  b) variable cost change,
  c) fixed-cost change (if any in reporting layer),
  d) net profit delta.
- Confirm decomposition reconciles exactly to displayed profit delta.

7. Constraint-binding consistency:
- Compare binding/near-binding constraint sets baseline vs scenario.
- If land jumps to ~100%, identify which constraints relaxed enough to allow that jump and quantify slack changes.
- If top crops appear unchanged, explain where added land went (additional successions, channel reallocation, or reporting defect).

Mandatory evidence output format:
1. Table A: Run ID | Constraint change | Land % | Profit | Top crops summary.
2. Table B: Full crop-acreage vector diffs (baseline vs each scenario).
3. Table C: Applied scaling map vs displayed scenario label parity.
4. Table D: Land-utilization formula/path by UI location with source code references.
5. Table E: Profit delta decomposition reconciliation.

Root-cause verdict:
1. Provide one primary root cause and confidence (high/medium/low).
2. Classify as:
  a) solver behavior valid,
  b) scenario application bug,
  c) UI/reporting bug,
  d) mixed.
3. If no solver bug, explicitly explain why identical top crops can coexist with large land-use change using measured acreage-vector evidence.

Follow-up patch plan (only after verdict):
1. P0 correctness fixes.
2. P1 interpretation/labeling fixes.
3. P2 optional UX clarifications.

Acceptance criteria:
1. Baseline reproducibility is proven or failed with documented evidence.
2. Scenario label/application parity is proven.
3. Acreage-vector changes are explicitly quantified (not inferred).
4. Land-utilization display basis is consistent across views or mismatch is identified.
5. Profit deltas reconcile to component changes.
6. A clear go-forward fix plan is provided only for confirmed defects.

At the end, report:
1. Files inspected
2. Whether anomaly is real model behavior or reporting/state defect
3. Exact root cause location
4. Minimal fix plan with risk level
5. Any remaining unknowns requiring instrumentation
```

---

## Phase 3.4.5 Hotfix — What-If Peak Util Labeling + Scenario Land Util Column

```text
Implement a strict Phase 3.4.5 UI correctness hotfix immediately after Phase 3.4.4 forensic results.

Context from 3.4.4:
1. Baseline row currently shows land utilization in the Peak Util column.
2. Scenario rows currently show selected-constraint utilization in the same Peak Util column.
3. This mixed semantic column causes false reading like "67% land -> 100% land" even when scenario 100% may be labor/water/demand util.
4. Scenario land utilization already exists in data (`scenLandPct`) but is not surfaced as a first-class column.

Primary goals:
1. Fix Peak Util labeling so each scenario clearly states which resource utilization is being shown.
2. Add an explicit Scenario Land Util column so land-to-land comparison is visible and changes with each scenario.
3. Keep solver/model behavior unchanged.

Hard scope guardrails:
1. Do not modify solver objective, constraints, feasibility, or scenario math.
2. Do not alter scaling rules or candidate ranking in this phase.
3. Do not redesign the whole What-If panel; this is a table semantics/clarity hotfix.

Required updates (must include all):

1. Peak Util semantic labeling (P0):
- In What-If history table rendering, keep Peak Util value but append resource label for every row.
- Required display format examples:
  - `67% land` (baseline)
  - `100% labor`
  - `98% water`
  - `100% demand`
  - `92% storage`
  - `85% cash`
- Ensure the label comes from the actual `primary.type`/scenario type used for that row, not hardcoded text.

2. Add Scenario Land Util column (P0):
- Add a dedicated column showing peak weekly land utilization for each row.
- Baseline row uses baseline land peak (%).
- Scenario rows use per-scenario `scenLandPct` (%).
- Format consistently (rounded integer or one decimal, but same rule for all rows).
- This column must update as constraints change and should enable direct baseline-vs-scenario land comparison.

3. Column naming and ordering:
- Keep table compact but explicit.
- Recommended order:
  a) Scenario/Run label
  b) Constraint change
  c) Profit delta
  d) Peak Util (labeled with resource)
  e) Land Util (new explicit column)
- If exact current order differs, preserve existing structure where possible while adding clear headers.

4. Debug reference fix from forensic findings:
- Remove/rework any debug log path that references out-of-scope baseline variables (for example `basePeakLand` from wrong scope).
- Recompute needed baseline values locally in the function where debug output is emitted.
- Ensure `window._whatifDebug = true` no longer throws reference errors.

5. Inline explanatory copy (small, non-intrusive):
- Add one concise note near the table header:
  "Peak Util shows the selected constraint's utilization; Land Util shows peak land use for that run."
- Keep copy short and farmer-readable.

Testing requirements:
1. Semantic-label test:
- Scenario rows must render labeled Peak Util values (for example `% labor`, `% water`, `% demand`).
- Baseline row must remain labeled `% land`.

2. Land-column correctness test:
- New Land Util column exists and displays baseline + scenario land percentages.
- Values change across scenarios when land usage changes.
- Land column is not reused from Peak Util values.

3. Mixed-column regression test:
- Verify no row in Peak Util column is unlabeled.
- Verify users can distinguish constraint util vs land util at a glance.

4. Debug-scope test:
- With `window._whatifDebug = true`, running scenarios does not throw ReferenceError.

5. No-math-change regression test:
- Baseline deterministic solve unchanged.
- Scenario profit deltas and optimization outputs unchanged from pre-hotfix runs (display-only correction).

Acceptance criteria:
1. Peak Util values are explicitly labeled by resource on every row.
2. A separate Land Util column is present and scenario-responsive.
3. The prior "67% -> 100%" land ambiguity is removed in table semantics.
4. Debug logging works without scope-related runtime errors.
5. Existing tests and new hotfix tests pass.

At the end, report:
1. Files changed
2. Final Peak Util label mapping rule
3. Final Land Util column formula/source
4. Debug-scope fix summary
5. Test summary (labeling + land-column + regression)
```

---

## Phase 3.5 Patch — Margin % Label Correction + Inventory-Lite Feasibility Gate

```text
Implement two focused items in Phase 3.5:

### A. Margin % Label Correction (Sneak Fix)

**Issue:**
The Contribution Margin section footer at line ~4628 incorrectly states:
  "Red margin = negative contribution — optimizer will de-prioritize this crop/channel combination."

But the actual red styling is applied when `margin % < 20%`, which includes **positive margins** like 15% (healthy but below the 20% "watch" threshold).

**Required fix:**
Replace the footer explanation to accurately describe margin % color scheme:
- Red (#dc2626): margin % < 20% (low margin — watch; can be negative or positive)
- Orange (#d97706): margin % 20–50% (moderate margin)
- Green (#059669): margin % ≥ 50% (healthy margin)

Updated text should read:
  "Red & orange indicate low-margin opportunities (< 50%); optimizer still uses them if constrained. Green indicates healthy margins (≥ 50%). **Negative margins** (when VC > revenue) are mathematically valid but economically unattractive — optimizer will naturally de-prioritize."

This clarification removes the misleading "red = negative" conflation and correctly explains low-margin vs negative-margin cases.

**Testing:**
1. Verify text in footer matches updated terminology.
2. Verify color legend matches percentages: red < 20%, orange 20–50%, green ≥ 50%.
3. Ensure negative margin examples (if any) are visibly red with >0% label (not literally negative due to rounding).

**Acceptance criterion:**
Margin % footer text no longer implies red = negative; instead clearly distinguishes low-margin (red) from negative-margin (subset of red).

---

### B. Inventory-Lite Sales Spread (Decision Gate)

Implement a focused Phase 3.5 feasibility gate for an inventory-lite workaround before full implementation.

Objective:
Evaluate whether a low-complexity per-crop "sales spread weeks" option can add practical value without full inventory state tracking.

Hard guardrails:
1. Do not implement full inventory carryover, age tracking, spoilage, or storage accounting in this patch.
2. If implementation risk is high, return a no-go recommendation with rationale.

Evaluate this candidate approach:
1. Add optional per-crop parameter: sales_spread_weeks (default 1; off by default).
2. If >1, distribute harvest-available sellable volume evenly across that many weeks for sales-cap matching.
3. Do not extend field occupancy for this post-harvest sale-spread period.
4. Explicitly flag that harvest storage and true inventory accounting become approximate under this mode.

Required output:
1. Complexity assessment (low/medium/high) with exact touched model components.
2. Behavioral risks and likely user confusion points.
3. Recommended path:
  a) go for lightweight implementation in a later patch, or
  b) no-go (keep as documented limitation only).
4. If go: provide minimal implementation plan with test plan and warning copy.
5. If no-go: provide best non-implementation workaround guidance for users.

Acceptance criteria:
1. Clear go/no-go recommendation with evidence.
2. No accidental full-inventory scope expansion.
3. Explicit user-facing caveat language drafted.
```

---

## Phase 3.5.1 Patch — C5 Sales-Spread Window (Inventory-Lite, No Full Inventory Engine)

```text
Implement a focused Phase 3.5.1 follow-up after the Phase 3.5 decision gate.

Primary objective:
Add an optional per-crop sales-spread control that changes only the C5 sales linkage so harvest can be sold over multiple post-harvest weeks, without extending field occupancy and without implementing a full inventory state engine.

Root cause validated in prior diagnosis:
1. Current C5 behavior ties sales to harvest week only:
  - If crop is not in harvest phase in week w, then sales in week w are forced to zero.
2. This blocks shelf-stable crops (example: garlic) from selling across multiple weeks of demand cap.
3. Land occupancy (C1) is already modeled correctly and must remain unchanged.

Hard scope guardrails:
1. Do not implement full inventory carryover state variables.
2. Do not implement age tracking, spoilage, FIFO/LIFO, or storage aging.
3. Do not change objective coefficients or demand-cap math (C6) semantics.
4. Do not change field occupancy calendar logic.
5. Keep default behavior backward-compatible when sales_spread_weeks = 1.

Required model behavior:
1. New optional crop-level parameter:
  - sales_spread_weeks (integer, default 1, allowed range 1-8)
2. C1 (land/field occupancy):
  - No change. Crop leaves field according to existing phase calendar.
3. C5 (sales vs harvest linkage):
  - For spread=1: preserve current behavior exactly.
  - For spread>1: replace per-week harvest-only sales cap with a cumulative window cap:
    For each succession i with final harvest week H and spread S,
    total sales across weeks H..H+S-1 (bounded by horizon) <= total harvest volume from that succession.
4. C6 (weekly demand caps):
  - No change. Weekly channel caps still apply and now naturally govern how spread sales clear over time.
5. C13 (cash flow):
  - No structural change. Revenue continues to accrue in the week sales occur.

Storage caveat handling (C4):
1. Keep existing C4 implementation unchanged in this patch.
2. Add explicit caveat in code comments and UI copy:
  - With spread>1, harvest storage is enforced at harvest week only.
  - Users must set harvest storage cap high enough to hold full harvest volume for spread crops.
3. Do not add inventory balance equations in this patch.

Implementation guidance (minimum touch points):
1. solver.py:
  - Parse per-succession spread value from crop config.
  - Modify C5 row generation:
    a) spread=1 path: current per-harvest-week rows unchanged.
    b) spread>1 path: one cumulative window row per succession anchored at last harvest week.
2. JS bridge (run_from_js payload path):
  - Accept and pass sales_spread_weeks to solver payload.
3. UI crop form/card:
  - Add optional numeric input: Sales Spread Weeks (default blank->1, min=1, max=8).
  - Add tooltip text clarifying post-harvest sales window and storage caveat.
4. Results/alerts:
  - If any crop has spread>1, show info banner with storage approximation warning.

Testing requirements:
1. Backward compatibility:
  - spread=1 produces same optimization outputs as pre-patch for a fixed seed/input set.
2. Garlic spread sanity:
  - With spread=4 and weekly FM cap binding, solver can sell across up to 4 weeks (instead of only harvest week).
3. Land occupancy invariance:
  - Spread weeks do not keep land occupied; C1 profile unchanged.
4. Determinism:
  - Two runs with identical inputs and spread settings return identical results.
5. UI wiring:
  - Input value reaches solver payload.
  - Warning banner appears when any spread>1.

Acceptance criteria:
1. C5 supports optional multi-week post-harvest sales windows by crop.
2. Default spread=1 is fully backward-compatible.
3. Land occupancy remains phase-driven only (no extension from spread).
4. Storage approximation is clearly disclosed in UI and comments.
5. No full inventory scope expansion occurred.
6. Existing tests pass and new spread-specific tests pass.

At the end, provide:
1. Files changed
2. Exact C5 before/after constraint form (concise)
3. Backward-compatibility evidence for spread=1
4. Garlic spread test evidence (sales shifting over multiple weeks)
5. Final user-facing caveat text
6. Deferred items list for full inventory engine (explicitly out of scope)
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

## Phase 4.1 Patch — MC Interpretability + Decision-Focused Outputs

```text
Implement a focused Phase 4.1 hotfix/refinement that fixes Monte Carlo interpretability and uncertainty-input wiring for farmer users.

Primary goals:
1. Fix MC uncertainty behavior so uploaded historical std dev data actually drives MC variability by default.
2. Remove confusing CV% manual workflow as the primary path.
3. Reduce result-page overload to only high-insight outputs.
4. Add plain-language explanation support throughout MC outputs.
5. Simplify upload UX and remove duplicated/illogical upload locations.

Scope constraints:
1. Keep deterministic baseline optimizer behavior unchanged.
2. Keep core solver objective/constraints unchanged.
3. Do not implement full stochastic/robust MILP in this patch.
4. Keep changes backward-compatible with existing saved inputs where possible.

Required updates (must include all):

1. Uncertainty wiring hotfix (P0):
- Current bug/issue: MC variance is primarily driven by manual CV inputs, while uploaded std dev fields do not clearly drive scenario spread.
- Required behavior:
  a) When XLSX uncertainty data exists, use uploaded std dev values as the default MC variance source.
  b) If no uploaded std dev is available for a field/crop/channel, use a documented fallback.
  c) Manual overrides can remain optional, but must not silently dominate uploaded values.
- Add explicit UI status line: "MC variance source: Uploaded historical std dev" (or fallback reason).

2. Remove upload block from Labor and Channels section:
- Delete/hide the MC uncertainty upload subsection in Labor and Channels.
- Keep uncertainty upload in Crops section and add a second upload entry point on Results (see item 4).
- Ensure no broken handlers/references remain.

3. Post-upload summary report in parameter sections:
- After MC uncertainty upload and after rainfall upload, show a compact summary panel with computed stats:
  a) crop/channel rows recognized
  b) means used
  c) standard deviations used
  d) rows skipped + reasons (if any)
- This panel must confirm to users that upload was parsed and applied.
- Keep copy plain-language (avoid statistical jargon where possible).

4. Add results-page upload entry point above Monte Carlo:
- Add "Upload/Update Uncertainty Data" block above MC results controls.
- Allow users to upload MC uncertainty and rainfall files from results page if missed in inputs flow.
- Recompute and refresh summary report + MC readiness state after upload.

5. Hide sensitivity analysis section and simplify MC output:
- Remove/hide the dedicated Sensitivity tab/section from default MC results.
- Keep only high-insight outputs by default:
  a) plain-language MC summary card
  b) profit range chart
  c) crop stability table (simple labels)
- If retaining any deep diagnostics, gate under a collapsed "Technical details" panel.

6. Remove Advanced toggle dependency for MC access:
- MC should be directly available in results without requiring Advanced toggle.
- Remove/hide Advanced toggle if it is now redundant.
- Ensure no regression for any remaining advanced-only sections.

7. Plain-language explanation pop-ups:
- Add "?" help pop-outs beside MC terms and metrics.
- Required terms to explain in simple language:
  a) Mean
  b) Median
  c) P10/P90 (bad year / good year framing)
  d) Crop stability
  e) Why results vary between scenarios
- Explain with practical farm decision wording, not statistical textbook language.

8. MC section intimidation reduction:
- Rename and restyle MC header/copy for confidence:
  e.g., "Risk Check: How your plan performs in good and bad years".
- Add one-sentence interpretation under each key metric.
- Keep layout compact and scan-friendly (avoid dense multi-tab clutter).

9. Reproducibility and runtime UX guardrails:
- Keep seed input visible and persist the last used seed for reruns/comparisons.
- Show progress during MC runs and keep cancel behavior responsive.
- Show simple runtime guidance near simulation count (example: "100 = faster check, 500 = more stable range").

10. Upload safety and mismatch handling:
- If uploaded crop/channel names do not match recognized app entities, show non-blocking warnings.
- Explicitly report when fallback variance rules were used due to missing/invalid upload rows.
- Do not silently ignore malformed upload rows.

11. Action-oriented decision framing:
- Add plain-language outcome badges/messages such as "Plan appears robust", "Watch downside risk", or "Fragile under bad-year conditions".
- Ensure each message ties to visible MC metrics (range, downside percentile, crop stability labels).

Testing requirements:
1. P0 wiring test:
- Upload two uncertainty files with materially different std dev values.
- Verify MC spread (e.g., std dev or P90-P10) changes in expected direction.
2. Upload summary test:
- Confirm summary panel displays computed means/std dev and recognized row counts.
3. Results upload test:
- Upload from results page and verify MC inputs refresh without full page reload.
4. UI cleanup test:
- Labor/Channels upload block removed.
- Sensitivity section hidden/removed from default output.
- Advanced toggle no longer required for MC access.
5. Explanation test:
- All key MC metrics have help pop-ups with non-empty plain-language copy.
6. Regression test:
- Deterministic baseline solve unchanged.
- Existing scenario/what-if tools still function.
7. Reproducibility/runtime test:
- Same seed and same inputs produce matching summary metrics.
- Different seed changes sampled distribution.
- Cancel stops an active run without stale loading state.
8. Upload mismatch test:
- Unknown crop/channel labels produce warnings and appear in skipped-row report.

Acceptance criteria:
1. Uploaded uncertainty std dev values visibly and measurably affect MC spread.
2. Users receive clear post-upload confirmation with means/std dev summary.
3. MC uncertainty upload is available in logical places (Crops + Results), not duplicated in Labor/Channels.
4. Results page is simpler: high-insight MC outputs only by default.
5. MC terminology is understandable for non-technical users.
6. Advanced toggle is removed/hid if no longer needed.
7. Existing tests pass and new hotfix tests pass.
8. Seed behavior is transparent and reproducible for user comparisons.
9. Upload mismatches are surfaced with warnings instead of silent fallback.
10. MC output includes explicit decision framing for non-technical users.

At the end, report:
1. Files changed
2. Exact uncertainty-source precedence rule implemented (uploaded vs fallback vs manual)
3. Before/after evidence that spread changes when uploaded std dev changes
4. Final visible MC sections and removed sections
5. Final plain-language glossary/help text
6. Any deferred technical items
```

---

## Phase 4.1.1 Polish & Refinement — Rainfall Visibility + Upload Tracking + Terminology

```text
Implement a focused Phase 4.1.1 refinement that addresses user feedback on MC upload tracking, parameter summaries, and plain-language terminology gaps.

Primary issues to fix (from post-4.1 user testing):
1. Rainfall upload status not visible in MC section (unlike yield/price/demand crops).
2. Rainfall parameter page has no summary explanation box (crop section has one; rainfall needs mirror).
3. Results MC section lacks upload file visibility/management (no way to see or delete/reupload files).
4. CV% derivation guidance missing for non-statisticians (what is CV%, how do you calculate it?).
5. Crop stability section unclear ("in plan" meaning, implications not explained).
6. Percentile explanation weak (P10/P90 need explicit bad-year/good-year framing).
7. Unit Contribution Margins don't account for time (Hot Peppers inflated due to long cycle; need flow-rate or annualized metric).

Hard scope guardrails:
1. Do not modify solver objective or constraints.
2. Do not add new solver variables in this patch.
3. Keep deterministic baseline unchanged.
4. Do not alter MC sampling or seed behavior.
5. Do not redesign results layout; only polish/enrich existing sections.

Required updates (must include all 7):

1. Rainfall upload status visibility:
- In the MC CV section (where seed, sim count are shown), add a compact row listing uploaded files:
  a) If mc_uncertainty XLSX uploaded: show "✓ MC Uncertainty: [filename]" with small delete button.
  b) If rainfall history XLSX uploaded: show "✓ Rainfall History: [filename]" with small delete button.
  c) If neither uploaded: show "No uploads yet" + link to "Upload files above" (in parameter sections) or "Upload now" (on results).
- Keep format consistent with existing CV% display.

2. Rainfall parameter page summary box:
- On the Water section (where rainfall parameters exist), after rainfall upload affordance, add a summary panel identical in style to Crop section summary:
  a) Title: "Rainfall Upload Summary" (or "Rainfall Data Applied").
  b) Content (only if upload exists):
     - Rows recognized: N weeks × M years.
     - Mean rainfall: X mm/week (avg across all weeks/years).
     - Std dev rainfall: Y mm/week.
     - Calculation note: "Mean and std dev computed from uploaded weekly history."
  c) If no upload: show "No rainfall history uploaded. Using default baseline patterns."
- Make it collapsible like the Crop section.

3. Results page MC upload file visibility and management:
- In the MC results section (before Profit Distribution chart), add a compact "Uploaded Data Files" panel:
  a) List each file type with name/upload date (or just name if date not available):
     - MC Uncertainty: [filename] — [small Delete button] — [small Replace button]
     - Rainfall: [filename] — [small Delete button] — [small Replace button]
  b) If a file is deleted: fallback to CV% / baseline rainfall immediately.
  c) If "Replace" clicked: show file picker to upload new file in same category.
  d) If neither file uploaded: show "Add uncertainty data to improve robustness →" with upload links.
- Keep this panel compact (2-3 lines max) so results page remains scannable.

4. CV% guidance with plain-language "?" pop-ups:
- In the Crops section MC uncertainty area, next to "CV %" label, add a "?" icon.
- Clicking "?" shows a pop-up with plain-language explanation:
  a) "What is CV%?": "Coefficient of Variation — a measure of how much a value typically varies. If yield CV is 15%, it means yields vary about ±15% from average in good/bad years."
  b) "How do I calculate it?": "If you have 10 years of data: (1) calculate average yield; (2) calculate how different each year is from average; (3) divide by average and multiply by 100."
  c) "Where can I get CV% for my crop?": "Farm records, university extension, or ag industry reports. Or use the default values here."
- Keep language practical, avoid statistics jargon.
- Same pop-up near Price CV% and Demand CV% labels.

5. Crop Stability explanation:
- In the Crop Stability section results tab, add a header explanation box before the table:
  a) "What is Crop Stability?"
  b) "Your plan is tested against 100+ scenarios (good years/bad years). This table shows how often each crop stayed in your plan across all scenarios."
  c) "Labels explained":
     - **Stable** (green): Remains in plan in ≥80% of scenarios (farmer can rely on this crop).
     - **Conditional** (yellow): In plan 40-80% of scenarios (might be fragile depending on weather/prices).
     - **Fragile** (red): In plan <40% of scenarios (risky choice; may disappear in bad years).
  d) Plain-language conclusion: "Consider Stable crops as your base. Fragile crops are riskier but may offer benefit in good years."

6. Percentile explanation enhancement:
- In the MC summary card (Profit Distribution heading), add a "?" icon beside "Profit Range" or similar.
- Clicking "?" shows:
  a) "What are P10, P50, P90?":
     - P10 (bad year): 1 in 10 chance profit falls below this (likely a bad weather or market year).
     - P50 (median): 50% chance profit is above/below this (typical year).
     - P90 (good year): 1 in 10 chance profit exceeds this (strong weather or market year).
  b) "What does this tell me?": "If your P10 is still profitable, your plan is robust. If P10 is negative, watch your downside risk."

7. Unit Contribution Margin time adjustment:
- In the Contribution Margin section, add an optional toggle or check-box: "Annualize for Days to Maturity".
- When toggled ON:
  a) Add new column: "Annualized Margin/Acre" = (margin per acre) × (365 / days_to_maturity).
  b) Append to each crop/channel row: "Annualized: $(value)/year/acre".
  c) Sorts primarily by this annualized column so fast-cycle crops surface correctly.
  d) Add helper text: "Annualized margin accounts for how quickly the crop cycles. Fast crops (Spinach 90 days) can be replanted multiple times/year."
- When toggled OFF: keep existing per-cycle margin view.
- Default: ON (so Hot Peppers' true low-annualized-margin is apparent).
- Add "?" beside toggle with explanation of annualization logic.

Testing requirements:
1. Upload visibility test:
- Rainfall uploaded: "✓ Rainfall History: [file]" appears in MC section.
- MC Uncertainty uploaded: "✓ MC Uncertainty: [file]" appears in MC section.
- Delete button removes file; fallback to defaults shown.
2. Rainfall summary test:
- Rainfall uploaded: summary box on Water page shows rows, mean, std dev.
- Rainfall not uploaded: summary box shows "not uploaded" message.
3. Results file panel test:
- Both files uploaded: both listed in file panel with delete/replace buttons.
- One file deleted: fallback to defaults; UI auto-refreshes without page reload.
4. CV% pop-up test:
- "?" beside CV% label is clickable and shows plain-language explanation.
- Same pop-up appears for Price CV% and Demand CV%.
5. Crop Stability explanation test:
- Explanation box appears above Stable/Conditional/Fragile table.
- Labels and percentages match (Stable ≥80%, etc.).
6. Percentile pop-up test:
- "?" beside P10/P50/P90 metric is clickable.
- Pop-up explains bad-year/good-year context.
7. Annualized margin test:
- Toggle ON: Hot Peppers margin is lower than it appeared before.
- Toggle OFF: original per-cycle margin view returns.
- Spinach Annualized margin = (margin_per_acre) × (365/90) ≈ 4× per-cycle.
- Toggle persists across result page refreshes (stored in APP_STATE or localStorage).
8. Regression test:
- Baseline solve output unchanged.
- MC sampling and seed behavior unchanged.
- Existing help pop-ups (Mean, Median, etc.) still present and working.

Acceptance criteria:
1. Rainfall and MC uploads are visible in MC section and results file panel.
2. Rainfall parameter page has summary explanation box mirror to Crops section.
3. Results MC section shows file names with delete/replace options.
4. CV%, Crop Stability, and Percentiles have plain-language "?" pop-up guidance.
5. Unit Contribution Margin shows annualized flow-rate by default (toggle to cycle-based if needed).
6. All 7 user feedback items addressed and testable.
7. Existing tests pass; new tests cover the 7 polish items.
8. No solver objective/constraints/sampling changes.

At the end, report:
1. Files changed
2. New "?" pop-up glossary entries added
3. Rainfall summary box format and content
4. Annualized margin formula used and sample calculations (Spinach, Hot Peppers)
5. File upload/delete/replace UX flow explained
6. Test summary (7 items × pass/fail)
7. Any deferred items
```

---

## Phase 4.1.2 Regression Fixes — Rainfall Stats + MC Nesting + Sensitivity Hide + Table Alignment

```text
Implement a focused Phase 4.1.2 regression-fix patch after Phase 4.1.1. This patch addresses exactly five user-reported UI/interpretability regressions.

Primary issues to fix:
1. Rainfall upload summary only emphasizes years/weeks; users need explicit computed mean and standard deviation values surfaced clearly.
2. Unit Contribution Margins table columns/cells are visually jumbled and appear misaligned (likely wrapping/overflow/layout behavior).
3. Sensitivity Analysis section has reappeared in results, but should remain hidden in this MC simplification track.
4. Results-page "Update Uncertainty Data" block should be nested inside the Monte Carlo card and use naming consistent with parameter upload sections (historical-data wording).
5. Rainfall CV/source row in MC setup does not show a clear uploaded-status checkmark like crop uncertainty rows do.

Hard scope guardrails:
1. Do not change solver objective, constraints, or MILP behavior.
2. Do not alter Monte Carlo sampling math, random seed behavior, or scenario generation logic.
3. Do not reintroduce broad redesign; limit to targeted UI/UX correctness fixes.
4. Keep backward compatibility with existing uploads and saved state where possible.

Required updates (must include all 5):

1. Rainfall summary clarity (mean/std prominently shown):
- In Water section rainfall summary box, keep years/weeks coverage but explicitly add computed metrics in first-class display lines:
  a) Mean weekly rainfall (mm/week)
  b) Standard deviation (mm/week)
  c) Optional CV% (derived from std/mean) as supporting value
- Ensure values come from uploaded historical rainfall dataset actually used by MC.
- If no rainfall upload exists, show a clear fallback message.

2. Unit Contribution table alignment hardening:
- Fix table layout so headers and cells stay aligned across desktop/laptop widths.
- Prevent long crop/channel text or helper content from breaking column alignment.
- Add explicit table-layout/width/overflow handling to avoid jumbled visuals.
- Keep existing column semantics and annualize toggle behavior.

3. Sensitivity section hidden again:
- Hide/remove the standalone Sensitivity Analysis card from default results flow.
- Keep What-If Scenario Analysis visible as the actionable section.
- If any sensitivity diagnostics are still needed for debugging, move them under a collapsed technical/details container (not in default visible path).

4. Results upload block placement + naming consistency:
- Move the results-page upload controls so they are nested within the Monte Carlo card (not as a separate sibling block above it).
- Rename labels/titles to match parameter-section wording style (historical data phrasing), for example:
  - "Upload Historical Uncertainty Data"
  - "Upload Historical Rainfall Data"
- Keep file management controls (view/delete/replace) but ensure they feel like part of the MC workflow.

5. Rainfall uploaded-status indicator in MC setup:
- In MC setup/source summary area, add rainfall-specific source status with checkmark when rainfall historical upload is active.
- Show both status channels clearly:
  a) Crop uncertainty source status (uploaded/default/mixed)
  b) Rainfall source status (uploaded historical vs rainfall CV fallback)
- Ensure rainfall checkmark updates immediately after upload/delete/replace actions.

Testing requirements:
1. Rainfall summary stats test:
- Upload rainfall XLSX and verify mean + std dev numeric values are shown in summary box.
- Verify values update when replacing rainfall file.
2. Rainfall source status test:
- With rainfall upload active, MC setup shows rainfall checkmark/status.
- After deleting rainfall upload, status reverts to fallback (no checkmark).
3. Contribution table layout test:
- At common laptop width (for example 1366x768), headers align with body cells.
- No overlapping or wrapped content that misaligns columns.
4. Sensitivity visibility test:
- Standalone Sensitivity Analysis card is hidden/removed in default results view.
- What-If section remains visible and functional.
5. MC nesting/title consistency test:
- Results upload controls are inside Monte Carlo card.
- Labels use historical-data terminology consistent with parameter sections.
6. Regression test:
- Baseline deterministic solve unchanged.
- Existing MC run, upload, delete, and replace flows still work.

Acceptance criteria:
1. Rainfall summary visibly includes computed mean and std dev outcomes.
2. Unit Contribution table is readable and consistently aligned.
3. Sensitivity card is no longer visible in default results path.
4. Results upload controls are nested within MC section and use consistent historical-data naming.
5. Rainfall upload status/checkmark is clearly displayed in MC setup/source summary.
6. Existing tests pass and new regression tests for these five items pass.
7. No solver/math/sampling changes.

At the end, report:
1. Files changed
2. Exact UI locations updated for rainfall summary, MC source status, and upload block nesting
3. Before/after explanation of contribution table alignment fix
4. Confirmation that standalone Sensitivity section is hidden and where any technical diagnostics moved
5. Test summary (5 issue areas × pass/fail)
6. Any deferred items
```

---

## Phase 4.1.3 Hotfix — Table Structure + Duplicate Upload Pills + Rainfall CV Wiring + Tooltip Clarity

```text
Implement a strict Phase 4.1.3 hotfix after Phase 4.1.2. Fix only the five remaining user-reported issues below.

Primary issues to fix:
1. Unit Contribution table rows still become structurally misaligned after first row (cells appear to shift into wrong columns).
2. Uploaded-file status pills are duplicated in Monte Carlo (one set inside historical-data card and one set outside).
3. Gray tooltip circles appear without visible ? marker, making affordance unclear.
4. Rainfall CV behavior appears incorrect:
   - uploaded rainfall does not visibly update/annotate rainfall CV field,
   - likely rainfall uncertainty in MC still relies on manual rainfall CV input instead of uploaded historical distribution.
5. Water section warning recommending 25–50 years should be removed/relaxed, since provided templates may contain fewer years.

Hard scope guardrails:
1. Do not modify solver objective, constraints, or deterministic baseline math.
2. Keep changes within UI + MC input-wiring layer only.
3. Do not redesign whole results layout; fix targeted defects only.
4. Preserve upload backward compatibility.

Required updates (must include all 5):

1. Unit Contribution table structural fix (P0 visual correctness):
- Eliminate row/cell column drift in all rows, not just first row.
- Ensure each row always renders exactly one cell per header in fixed order.
- If current rowspan grouping is causing structural breakage, replace with robust non-rowspan layout (repeat crop label per row is acceptable).
- Enforce stable column schema and consistent cell widths.
- Verify no wrapped content causes column index mismatch.

2. Remove duplicate upload status pills:
- Keep only one uploaded-files status area inside the Monte Carlo historical-data upload block.
- Remove second duplicate rendering outside/elsewhere in MC card.
- Ensure delete/replace actions still function from the retained location.

3. Tooltip icon clarity:
- Any tooltip trigger circle must show a visible ? glyph by default (not hover-only).
- Apply consistently to MC metric labels and other new help markers.
- Preserve existing tooltip hover behavior/content.

4. Rainfall CV/source wiring + notation (P0 functional):
- When rainfall historical data is uploaded:
  a) compute rainfall variability from uploaded history (std dev and optional derived CV%),
  b) use uploaded rainfall-derived uncertainty as the MC rainfall source by default,
  c) do not silently let manual rainfall CV dominate unless user explicitly overrides.
- In the rainfall CV field/row, display a checkmark/status indicator when value/source is auto-derived from uploaded data.
- Show clear source text near rainfall control, for example:
  "Rainfall uncertainty source: Uploaded historical rainfall" vs "Manual CV fallback".
- Ensure this status updates immediately after upload/delete/replace.

5. Water upload guidance copy adjustment:
- Remove strict recommendation popup/text that says users should provide 25–50 years.
- Replace with softer guidance compatible with provided templates (example: "Use as many years as you have; more years improve stability.").
- Keep validation practical and non-contradictory to shipped templates.

Testing requirements:
1. Table-structure test:
- Render Unit Contribution table with multiple crops/channels.
- Assert each body row has same number of cells as header schema (or expected mapping when crop label repeated).
- Verify no column drift at laptop width.
2. Duplicate-pill test:
- With both rainfall and uncertainty files uploaded, status pills appear exactly once in MC section.
- Delete/replace still works.
3. Tooltip-visibility test:
- Tooltip circles visibly show ? marker before hover.
4. Rainfall-wiring test (P0):
- Run MC with rainfall upload active and manual rainfall CV set to an extreme value.
- Verify run uses uploaded rainfall source by default (unless explicit override enabled).
- Verify rainfall source status/checkmark reflects uploaded mode.
5. Rainfall-CV-notation test:
- After rainfall upload, rainfall CV row indicates auto-derived status/checkmark.
- After deleting rainfall upload, indicator reverts to manual/fallback.
6. Guidance-copy test:
- Water section no longer shows rigid "25–50 years" recommendation.
7. Regression test:
- Baseline deterministic solve unchanged.
- Existing uncertainty upload and MC run flows remain functional.

Acceptance criteria:
1. Unit Contribution table is structurally aligned on every row.
2. Upload status pills are shown only once in MC section.
3. Tooltip circles show visible ? indicator by default.
4. Rainfall uploaded data is confirmed as MC rainfall uncertainty source by default and visibly annotated.
5. Rainfall CV control row clearly indicates auto-derived/uploaded status when applicable.
6. Water guidance copy no longer conflicts with available template year counts.
7. Existing tests pass and new hotfix tests pass.

At the end, report:
1. Files changed
2. Root cause of contribution-table column drift and exact fix applied
3. Which duplicate upload-pill render path was removed
4. Exact rainfall source precedence rule now implemented (uploaded vs manual fallback)
5. Evidence that uploaded rainfall affects MC sampling path
6. Final tooltip marker behavior
7. Updated water guidance copy text
8. Test summary (5 issue areas + regression)
```

---

## Phase 4.1.4 Micro-Polish — Sorting + Single Upload Status + Rainfall CV Sync + Label Cleanup

```text
Implement a strict Phase 4.1.4 micro-polish after Phase 4.1.3. Address only the five remaining fine-tuning issues below.

Primary issues to fix:
1. Unit Contribution rows should be ordered by crop first, then by channel (restore prior logical reading order).
2. MC uploaded-file indicators are still duplicated (now as duplicated text/check lines instead of duplicated pills).
3. Rainfall CV shown in MC control differs from rainfall summary in Water section after upload (suggesting sync/wiring mismatch).
4. Rainfall uploaded-state styling in MC should match crop uploaded-state style (green outline + green uploaded check treatment, not blue sentence style).
5. "Global uncertainty" label is confusing; break rainfall CV and variable-cost CV into explicit standalone lines/labels.

Hard scope guardrails:
1. Do not modify solver objective/constraints or deterministic baseline.
2. Keep MC sampling model unchanged except necessary source-sync/wiring correction for rainfall CV value handoff.
3. No broad layout redesign; targeted UI and data-binding polish only.

Required updates (must include all 5):

1. Unit Contribution ordering:
- Sort table rows with precedence:
  a) crop name ascending (or stable crop-definition order), then
  b) channel name ascending (or stable channel-definition order).
- Keep annualized column and existing calculations unchanged.

2. Single upload-status render source:
- Ensure uploaded file status/check indicators render in exactly one place in MC section.
- Remove duplicate text/check rendering path entirely.
- Keep delete/replace functionality from the retained status block.

3. Rainfall CV synchronization fix (P0):
- After rainfall historical upload, the MC rainfall CV display/control must reflect the CV derived from uploaded rainfall data (same basis shown in Water summary).
- Ensure one source of truth for derived rainfall stats used by:
  a) Water summary panel
  b) MC rainfall CV displayed value
  c) MC rainfall uncertainty sampling input
- If manual override exists, require explicit user action and clearly label when override is active.

4. Rainfall uploaded-state styling parity:
- Make rainfall uploaded indicator styling in MC consistent with crop uploaded indicators:
  a) green visual treatment,
  b) uploaded checkmark label,
  c) same style language as crop rows.
- Remove blue alternate-style sentence treatment.

5. Label cleanup for uncertainty controls:
- Replace ambiguous "Global uncertainty" heading with clear per-control labels.
- Present as separate explicit lines/rows, e.g.:
  - "Rainfall CV%"
  - "Variable Cost CV%"
- Keep helper tooltip text clear and practical.

Testing requirements:
1. Ordering test:
- Verify Unit Contribution rows are ordered by crop then channel.
2. Single-status test:
- With uploads present, status indicators appear once only.
3. Rainfall-CV sync test (P0):
- Upload rainfall file and verify MC rainfall CV equals derived CV shown in Water summary (same numeric basis/rounding rule).
- Run MC and verify uploaded rainfall path is used by default.
4. Styling parity test:
- Rainfall uploaded marker visually matches crop uploaded marker pattern (green + uploaded check style).
5. Label clarity test:
- No "Global uncertainty" label remains; separate rainfall and variable-cost lines are visible.
6. Regression test:
- Baseline deterministic solve unchanged.
- Existing upload/delete/replace flows still work.

Acceptance criteria:
1. Unit Contribution table ordering is crop -> channel.
2. MC upload-status indicator appears exactly once.
3. Rainfall CV displayed in MC is synchronized with uploaded-data-derived value.
4. Rainfall uploaded styling matches crop uploaded styling.
5. "Global uncertainty" label is removed and replaced with explicit control labels.
6. Existing tests and new micro-polish tests pass.

At the end, report:
1. Files changed
2. Sort rule implemented for Unit Contribution rows
3. Which duplicate status-render path was removed
4. Exact rainfall CV source-of-truth flow (upload -> summary -> MC display -> MC sampling)
5. Styling parity details for rainfall vs crop uploaded indicators
6. Updated control labels replacing "Global uncertainty"
7. Test summary (5 issues + regression)
```

---

## Phase 4.1.5 Micro-Polish — Farm Basics Tooltips + Channel Guidance + Results Layout Refinement

```text
Implement a strict Phase 4.1.5 micro-polish after Phase 4.1.4. Address only the seven UI/UX refinements below.

Primary issues to fix:
1. Farm Basics "Operating Weeks" should default to 52 and include a clear ? help pop-out.
2. Farm Basics "Water Tank" should include a ? pop-out describing typical tank sizes and pointing users to Water section catchment details.
3. Farm Basics "Credit Line" and "Equipment Storage" need ? pop-outs clarifying meaning, usage, and limitations.
4. Sales Channels need a ? pop-out clarifying that detailed channel setup is completed under each crop.
5. Under crop/channel demand settings, when "Weekly cap + active season" is selected, show note: if more than one active season is needed, create another channel entry.
6. Executive summary metric squares should be reformatted into a 3x2 layout.
7. Profit waterfall should be more compact and visually aligned with page aesthetics (less pixelation, consistent color system, rounded bars).

Hard scope guardrails:
1. Do not modify solver objective/constraints or deterministic baseline.
2. Do not alter What-If or Monte Carlo sampling logic in this phase.
3. No broad navigation redesign; this is targeted polish only.

Required updates (must include all 7):

1. Operating Weeks default + help tooltip:
- In Farm Basics controls, set default selected value for Operating Weeks to 52.
- Add visible ? tooltip/help pop-out beside label explaining:
  a) what operating weeks means,
  b) how it impacts planning horizon and costs,
  c) when to use shorter seasons (for example, seasonal operations).

2. Water Tank tooltip in Farm Basics:
- Add ? tooltip on Water Tank field with practical guidance:
  a) typical tank size ranges,
  b) small/medium/large farm examples,
  c) note that catchment-system details and rainfall handling are configured in the Water section.

3. Credit Line + Equipment Storage tooltip clarity:
- Add ? tooltip for Credit Line describing:
  a) what borrowing capacity this represents,
  b) that it is a financing limit, not free profit,
  c) practical limitations/cost implications in planning context.
- Add ? tooltip for Equipment Storage describing:
  a) what assets/storage this covers,
  b) how it influences fixed-cost assumptions,
  c) that default values are acceptable unless user has audited capacity data.

4. Sales Channels tooltip guidance:
- In Labor & Channels section, add ? tooltip/help copy near Sales Channels header.
- Clarify that channel-level defaults are defined there, while crop-specific channel pricing/demand/cap details are entered under each crop card.

5. Weekly cap + active season note:
- In crop/channel demand-cap UI, when user selects "Weekly cap + active season" mode, show contextual note:
  "If you need more than one active season window, create another channel entry for that crop."
- Keep note concise and visible only for this mode.

6. Executive summary grid reformatted to 3x2:
- Reformat executive-summary metrics into 3 columns by 2 rows on desktop/laptop.
- Preserve responsive behavior for smaller screens (graceful stacking).
- Keep existing metric content unchanged unless layout requires label shortening.

7. Profit waterfall visual refinement:
- Reduce vertical space footprint while maintaining readability.
- Improve rendering quality:
  a) sharper chart output (avoid visibly pixelated appearance),
  b) rounded bar corners,
  c) color palette consistent with current page visual language,
  d) spacing/typography consistent with nearby result cards.
- Keep numerical values and ordering unchanged.

Testing requirements:
1. Operating Weeks default test:
- Fresh load shows 52 weeks selected by default.
- Tooltip appears and contains non-empty explanatory text.

2. Farm Basics tooltip coverage test:
- Water Tank, Credit Line, and Equipment Storage all show visible ? markers.
- Each tooltip contains practical explanation + limitations/context.

3. Sales Channels guidance test:
- Sales Channels ? tooltip exists and explicitly references crop-level channel detail entry.

4. Weekly-cap note test:
- Selecting "Weekly cap + active season" shows the multi-season note.
- Switching to other demand-cap modes hides the note.

5. Executive summary layout test:
- Desktop/laptop view renders a clear 3x2 summary grid.
- Mobile view remains readable without overlap.

6. Waterfall visual regression test:
- Waterfall renders with reduced footprint, rounded bars, and non-pixelated appearance.
- Values/labels remain correct and legible.

7. Regression test:
- Baseline deterministic solve unchanged.
- Existing results cards and export actions still function.

Acceptance criteria:
1. All requested ? help pop-outs are present with clear practical guidance.
2. Operating Weeks default is 52 on initial load.
3. "Weekly cap + active season" guidance note is conditionally shown as specified.
4. Executive summary renders in a 3x2 layout on desktop.
5. Waterfall chart is visually cleaner, smaller, and stylistically consistent.
6. Existing tests and new micro-polish tests pass.

At the end, report:
1. Files changed
2. Exact fields/tooltips added or updated
3. Executive summary grid CSS/layout changes
4. Waterfall rendering/styling changes
5. Test summary (7 issue areas + regression)
```

---

## Phase 4.2 Prompt — Hybrid Stepper + Benchmark-Strict Gating + Required-Field Clarity

```text
Implement a strict Phase 4.2 UX/navigation refinement after Phase 4.1.5.

Primary goals:
1. Introduce a hybrid navigation flow: stepper as primary path, hub as secondary jump navigation.
2. Enforce benchmark-strict run gating: all required sections visited + all required fields valid before Optimize unlocks.
3. Improve required vs optional signal strength without increasing visual clutter.
4. Keep solver/model behavior unchanged.

Hard scope guardrails:
1. Do not modify solver objective, constraints, coefficients, or deterministic baseline outputs.
2. Do not alter What-If scenario math, ranking logic, or Monte Carlo sampling logic in this phase.
3. Do not do full visual redesign in this phase; focus on navigation, validation, and flow clarity.

Required updates:

1. Hybrid navigation architecture:
- Keep the hub entry point and section cards.
- Add/enable a persistent top stepper for the input flow with ordered sections:
  a) Farm Basics
  b) Water
  c) Labor and Channels
  d) Crops
  e) Review and Run (if still present), otherwise equivalent run checkpoint state.
- Users can advance with Next/Back in stepper order.
- Users can still jump via hub cards at any time.
- Active section state must stay synchronized between stepper and hub.

2. Optimize unlock rule (benchmark-strict):
- Optimize remains disabled until BOTH are true:
  a) user has visited all required sections at least once,
  b) all required fields pass validation.
- If sections are visited but required fields fail, keep Optimize disabled and show concise reasons.
- Keep current defaults behavior (preloaded values still allowed), but benchmark mode still requires section visitation to unlock.

3. Required-field clarity improvements:
- Ensure every required field has a visible red asterisk on label.
- Optional fields keep existing optional marker style.
- Add one short required-input helper line per section header:
  - what must be filled,
  - what is optional,
  - what defaults are safe.
- Do not mark Monte Carlo uploads or advanced diagnostics as required.

4. Validation UX and error surfacing:
- Add section-level inline validation summary at top of each section when invalid.
- Add global unlock hint near Optimize button:
  "Complete required sections and required fields to unlock Optimize."
- On failed optimize click attempt (if any bypass path exists), focus/scroll to first invalid field.

5. Completion semantics:
- Section completion state must depend on:
  a) visited state, and
  b) required-field validity state.
- Recommended visual statuses:
  - unvisited,
  - visited-incomplete,
  - complete.
- Reflect these statuses in both hub cards and stepper indicators.

6. Keyboard/accessibility consistency:
- Stepper controls must be keyboard reachable.
- Disabled Optimize state must include aria-disabled semantics.
- Required-field error text must be screen-reader friendly (simple descriptive text, no icon-only messaging).

Testing requirements:
1. Hybrid nav sync test:
- Navigating via stepper updates active hub state.
- Jumping via hub updates stepper active step.

2. Strict unlock gate test:
- Fresh load: Optimize disabled.
- After visiting all required sections but leaving one required field invalid: still disabled.
- After all required fields valid: enabled.

3. Required marker test:
- Required fields show red asterisk.
- Optional and advanced inputs are not marked required.

4. Validation summary test:
- Invalid section shows concise summary.
- Fixing fields clears summary and updates completion status.

5. Completion-state test:
- Hub and stepper both show unvisited/visited-incomplete/complete consistently.

6. Regression test:
- Baseline deterministic solve unchanged.
- Existing What-If and MC behaviors still function.

Acceptance criteria:
1. Hybrid stepper + hub flow works with synchronized section state.
2. Optimize unlock follows strict AND rule (visited + required valid).
3. Required/optional distinctions are clear and consistent.
4. Users receive clear invalid-input guidance before run.
5. Existing solver outputs and advanced analytics remain unchanged.

At the end, report:
1. Files changed
2. Final unlock/gating rule implementation
3. Section completion-state model used
4. Required-field and validation UX changes
5. Test summary (6 issue areas + regression)
```

---

## Phase 4.3 Prompt — Information Architecture + Farmers-Market Editorial Visual Pass

```text
Implement a strict Phase 4.3 IA/aesthetic pass after Phase 4.2.

Primary goals:
1. Improve scanability and confidence for first-time farm users via cleaner information hierarchy.
2. Apply a cohesive farmers-market editorial visual language across input and results.
3. Keep all calculations and model behavior unchanged.

Hard scope guardrails:
1. Do not modify solver objective, constraints, coefficients, or deterministic outputs.
2. Do not alter What-If scenario math, Monte Carlo sampling math, or run ordering logic.
3. Do not remove existing major result modules; re-prioritize and restyle only.

Scope boundary note:
1. Guided parameter walkthrough behavior, progressive-disclosure field toggles, and friendly title/subtitle onboarding copy are implemented in Phase 4.3.2.
2. Keep Phase 4.3 focused on IA ordering, editorial visual language, readability, motion polish, and responsive presentation.

Required updates:

1. IA restructuring (content hierarchy only):
- Input pages:
  a) elevate section purpose + required/optional cues above controls,
  b) group controls into "Core Inputs" vs "Advanced/Optional" blocks,
  c) reduce repeated explanatory text.
- Results page:
  a) executive summary first,
  b) decision-action cards next (What-If, key risks),
  c) diagnostic/detail cards after.
- Remove redundant repeated copy across adjacent cards.

2. Farmers-market editorial visual direction:
- Define a restrained, earthy design system (CSS variables) with:
  - produce-forward greens + warm neutrals,
  - one accent color for warnings/actions,
  - consistent card surfaces and border tones.
- Typography:
  - use a distinctive editorial heading style paired with readable body text,
  - consistent scale for h1/h2/h3/body/caption.
- Card rhythm:
  - tighter spacing hierarchy,
  - consistent corner radius,
  - subtle depth with low-noise shadows.

3. Results readability polish:
- Executive summary metrics:
  - preserve current content,
  - improve visual rhythm and label/value contrast,
  - maintain 3x2 desktop behavior and mobile stacking.
- What-If table:
  - improve row legibility and header contrast,
  - maintain current semantics from Phase 3.4.5 (Peak Util labeled + Land Util column).
- Profit waterfall card:
  - keep compact footprint,
  - align typography and spacing with updated card language.

4. Motion and interaction polish (subtle):
- Add lightweight purposeful motion only where useful:
  a) section enter fade/slide,
  b) card reveal stagger after solve,
  c) hover emphasis on actionable cards.
- Avoid heavy animation; prioritize performance and clarity.

5. Copy tone normalization:
- Keep plain-language farmer-facing tone.
- Replace jargon-heavy phrasing with operational wording.
- Ensure tooltip tone is practical, concise, and consistent.

6. Responsive behavior and density:
- Desktop/laptop: optimized scanning with balanced multi-column card flow.
- Tablet/mobile: graceful single-column collapse with no overlap/truncation.
- Ensure tables/charts remain readable at narrower widths.

Testing requirements:
1. IA order test:
- Results order reflects summary -> action -> diagnostics.
- Duplicate explanatory copy reduced.

2. Design system test:
- CSS variables used for major color/spacing/typography tokens.
- Cards/components consume shared tokens consistently.

3. Executive summary layout test:
- 3x2 desktop grid preserved.
- Mobile stack remains legible.

4. What-If semantics regression test:
- Peak Util labels and Land Util column remain intact and unchanged semantically.

5. Motion/performance test:
- New animations run without blocking interactions.
- No major repaint/jank on section switch or result render.

6. Responsive test:
- Key pages and cards remain readable at common laptop and mobile widths.

7. Regression test:
- Baseline deterministic solve unchanged.
- Existing exports and actions remain functional.

Acceptance criteria:
1. App presents a coherent farmers-market editorial visual language.
2. Information hierarchy is clearer and faster to scan.
3. Decision-critical outputs are visually prioritized.
4. Existing math and scenario engines remain unchanged.
5. Existing tests and new IA/visual tests pass.

At the end, report:
1. Files changed
2. IA/order changes made
3. Design-system tokens introduced/updated
4. Visual polish changes by section/card
5. Motion + responsive behavior summary
6. Test summary (7 issue areas + regression)
```

---

## Phase 4.3.1 Patch — Add Property Mortgage/Rent Fixed Cost

```text
Implement a focused Phase 4.3.1 financial-model patch after Phase 4.3.

Primary goal:
1. Add a new fixed-cost input for property occupancy cost (Mortgage or Rent) and carry it through solver inputs, fixed-cost accounting, and results reporting.

Scope constraints:
1. Do not change solver constraints structure, crop calendars, or What-If/MC logic.
2. Do not alter objective coefficient logic for decision variables except adding the new fixed-cost term to whole-plan accounting.
3. Keep all existing parameter names backward-compatible; this is additive.
4. Keep guided walkthrough, onboarding copy, and progressive-disclosure implementation scoped to Phase 4.3.2 only.

Required updates:

1. New Farm Basics input (UI):
- Add field in Farm Basics / Fixed Cost Rates area:
  - Label: Property Mortgage/Rent ($/wk)
  - Type: numeric, min 0, reasonable step (for example 100)
  - Include a concise ? tooltip explaining this is weekly property occupancy cost.
- Include this field in Benchmark defaults/provenance map with a practical default and source placeholder style consistent with existing entries.

2. Parameter wiring (JS -> Python bridge):
- Add the new field to params collected in run flow.
- Parse it in run_from_js() with safe default when omitted.
- Pass it through to solve_farm_v2().

3. Solver fixed-cost integration:
- In solve_farm_v2(), add new argument (for example rate_property_mortgage_rent).
- Include it in fixed cost total as:
  property_cost = rate_property_mortgage_rent * operating_weeks
- Ensure it is included in:
  a) fixed_cost summary,
  b) weekly fixed-cost spread used by cash-flow floor.
- Keep deterministic backward compatibility when value is 0.

4. Results and export breakdown:
- Add the new line item to fixed-cost breakdown outputs where fixed components are displayed/exported.
- Ensure total fixed cost in UI/P&L reconciles with solver fixed_cost including the new property component.

5. Regression and invariance expectations:
- With Mortgage/Rent = 0, outputs should match pre-patch behavior (within floating tolerance).
- With positive Mortgage/Rent, profit and cash-flow metrics should update consistently.

6. Weekly-season note clarity carry-forward:
- In crop/channel demand-cap UI, when "Weekly cap + active season" is selected, ensure helper copy explicitly routes users to Labor & Channels to add another sales-window channel entry.
- Use this exact note text:
  "Need more than one active season window? Return to Labor & Channels and create a separate channel entry for that crop and sales window."
- Keep this note visible only for the "Weekly cap + active season" mode.

7. Unit Contribution default comparator carry-forward:
- In the Unit Contribution Margin table, set default comparator metric to:
  $/ac/week planted = contribution_margin_per_acre / planting_weeks
- Keep annualized and other comparator views available if they already exist, but make $/ac/week planted the default displayed/sort basis.
- Add concise helper text clarifying that this comparator normalizes contribution by planting-duration intensity.

Testing requirements:
1. UI wiring test:
- Field is present, accepts numeric values, and is included in params payload.

2. Solver accounting test:
- fixed_cost increases by exactly (mortgage_rent_per_week * operating_weeks).

3. Cash-flow consistency test:
- weekly cash floor/peak borrowing reflects the added weekly property cost.

4. P&L/export test:
- Fixed-cost breakdown includes Property Mortgage/Rent line and totals reconcile.

5. Backward compatibility test:
- Setting Mortgage/Rent to 0 reproduces baseline results from before patch.

6. Weekly-season note routing test:
- Selecting "Weekly cap + active season" shows the exact updated note text.
- Switching to any other demand-cap mode hides that note.

7. Unit Contribution comparator default test:
- Default Unit Contribution view uses $/ac/week planted.
- Formula verification: displayed default metric equals contribution_margin_per_acre / planting_weeks.
- If alternate comparator toggles exist, switching away and back restores $/ac/week planted as default.

Acceptance criteria:
1. Property Mortgage/Rent is configurable in UI and fully wired to solver.
2. Fixed-cost and cash-flow reporting include the new cost consistently.
3. Existing behavior is unchanged when the new field is left at 0.
4. Weekly-season note copy clearly directs users to Labor & Channels for additional sales windows.
5. Unit Contribution default comparator is $/ac/week planted (contribution margin per acre divided by planting weeks).
6. Existing tests pass; new focused tests for this patch pass.

At the end, report:
1. Files changed
2. New parameter name and default used
3. Fixed-cost formula update (exact expression)
4. P&L/export line-item updates
5. Weekly-season note copy update confirmation
6. Unit Contribution default comparator update confirmation
7. Test summary (7 issue areas + regression)
```

---

## Phase 4.3.2 Prompt — Guided Parameter Walkthrough + Progressive Disclosure

```text
Implement a strict Phase 4.3.2 usability pass immediately after Phase 4.3 (or 4.3.1 if already in progress).

Execution gate (avoid duplicate implementation):
1. Phase 4.3.1 is intentionally scoped to the financial-model patch and does not implement guided walkthrough, friendly onboarding copy, or progressive-disclosure toggles.
2. Execute the full Phase 4.3.2 implementation scope below as the single source of truth for those usability behaviors.

Primary goals:
1. Add a clear, guided parameter-entry flow so first-time users can complete setup without guessing.
2. Improve product framing with user-friendly title/subtitle copy.
3. Reduce cognitive load via progressive disclosure: show advanced fields only when users opt in.
4. Keep solver/model behavior unchanged.

Hard scope guardrails:
1. Do not modify solver objective, constraints, coefficients, or deterministic outputs.
2. Do not alter What-If or Monte Carlo sampling math.
3. Keep all changes backward-compatible with existing saved/default inputs.

Required updates:

1. Guided navigation flow refinement (carry-forward from earlier planning):
- Keep home page as hub entry.
- Once user enters parameter flow, show top progress stepper for exactly four sections:
  a) Farm Basics
  b) Water
  c) Labor and Channels
  d) Crops
- Show clear "step X of 4" state and completion checkmarks.
- Replace hub-back style navigation inside the flow with side-to-side Next/Back navigation between these four sections.
- Keep Optimize visible in the top area and disabled until completion criteria are met.
- Add an Optimize button affordance in each of the four parameter sections (Farm Basics, Water, Labor and Channels, Crops) so users can run from their current context.
- All Optimize buttons must share one lock state and remain grayed out/disabled until BOTH are true:
  a) all required sections have been viewed at least once,
  b) all required fields are valid.
- Disabled state copy should be consistent across section-level and top-level Optimize buttons.

2. Friendly product framing copy:
- Update app title/subtitle to plain-language, farmer-friendly framing.
- Example direction:
  Title: "Vegetable Farm Optimizer"
  Subtitle: "Plan your plantings, channels, labor, and profits in minutes."
- Final wording can vary, but must be descriptive of outcomes (what it helps users do), not internal architecture.

3. Progressive-disclosure controls for advanced parameter groups:
- Add explicit yes/no toggles (or equivalent controls) that reveal/hide related advanced sub-fields.
- Required progressive-disclosure groups to implement:
  a) "Is cash a constraint?"
    Reveal: Opening Cash, Credit Line
  b) "Do you want machinery and fuel to be a constraint?"
    Reveal: Fuel price/storage, harvest storage price/space, equipment storage price/space, machinery price
  c) "Do you have variable-cost detail by crop/channel?"
    Reveal: fertilizer/fuel by crop, packaging/selling cost by channel
  d) "Do you want phase-specific resource usage by crop?"
    Reveal: planting/growing/harvesting splits for labor, fuel, fertilizer, water
  e) "Do you want to account for harvest storage/refrigeration constraints?"
    Reveal: harvest storage price/space, lbs per tote (or equivalent crop storage conversion field)
  f) "Do you want to account for irrigation and fertilizer costs?"
    Reveal: irrigation cost, fertilizer use/cost controls
- Hidden fields must not be visually noisy when disabled; show short helper copy clarifying assumptions when toggles are off.

4. Required minimum setup clarity and enforcement:
- Add concise "Required to run" checklist copy across the relevant sections so users know what must be provided.
- Enforce these minimums before Optimize unlock:
  a) Significant per-crop info (yield, days to maturity, season dates, planting/growing/harvesting weeks, max land fraction, labor hours)
  b) At least one channel with fixed cost, variable selling cost, and crop-level channel data
  c) At least one laborer profile with full operating-week coverage
  d) Farm basics minimums: total land, operating weeks, irrigation cost
- Keep required vs optional styling clear and consistent with existing red-asterisk behavior.

5. Intro guidance and trust UX:
- Add short section-intro text that explains what each section controls and what defaults are safe.
- Add one optional intro panel/modal (non-blocking) summarizing what the optimizer does and how long setup typically takes.
- Keep this lightweight and dismissible; do not add heavy onboarding friction.

6. Unit Contribution comparator cleanup (carry-forward from 4.3.1):
- Keep $/ac/week planted as the primary and only default comparator in Unit Contribution.
- Remove annual $/ac as a visible default column/comparator in this phase (and remove related default annualize toggle state if present).
- If annualized calculations are retained internally for diagnostics, keep them out of the default user-facing Unit Contribution table in 4.3.2.
- Add concise helper text that confirms ranking is based on contribution intensity per planted week ($/ac/week planted).

Testing requirements:
1. Guided flow test:
- Entering parameter flow shows 4-step progress state with checkmarks.
- Next/Back navigation moves between all four sections in order.

2. Optimize gate test:
- Optimize remains disabled until required section completion + required field validity criteria are satisfied.

2b. Per-section Optimize presence and lock-state parity test:
- Each parameter section shows an Optimize button.
- Section-level and top-level Optimize buttons are all disabled/enabled in sync.
- Clicking a disabled section-level Optimize button surfaces the same unlock guidance as top-level.

3. Progressive-disclosure toggle test:
- Each of the six advanced toggles shows/hides the correct sub-fields.
- Hidden groups do not block optimize unless explicitly enabled and then left invalid.

4. Required-minimum test:
- Missing any required-minimum category keeps Optimize disabled with clear guidance.

5. Copy and framing test:
- Title/subtitle are user-friendly and action-oriented.
- Intro/help copy is present and non-technical.

6. Regression test:
- Baseline deterministic solve unchanged.
- Existing What-If, MC, and export flows remain functional.

7. Unit Contribution comparator cleanup test:
- Unit Contribution default view shows $/ac/week planted comparator.
- Annual $/ac is not shown as a default visible comparator/column in 4.3.2.
- Sort basis remains $/ac/week planted.

Acceptance criteria:
1. Users are guided through a clear 4-step parameter workflow with completion status.
2. Friendly title/subtitle and intro copy reduce first-time ambiguity.
3. Advanced fields are progressively disclosed via explicit opt-in toggles.
4. Required minimums are clear and enforceable before Optimize unlock.
5. Existing solver behavior remains unchanged.
6. Existing tests pass and new usability tests pass.
7. Optimize is available in each parameter section but remains grayed out until required views + required fields are complete.
8. Unit Contribution no longer defaults to annual $/ac display; $/ac/week planted is the user-facing default comparator.
7. Phase 4.3.2 is the canonical implementation phase for this scope; report full implementation outcomes.

At the end, report:
1. Files changed
2. Final title/subtitle copy used
3. Progressive-disclosure groups implemented (6 groups) and revealed fields
4. Required-minimum unlock rule implemented
5. Confirmation this phase was executed as the canonical guided-walkthrough/progressive-disclosure implementation
6. Unit Contribution comparator visibility/sort behavior implemented
7. Test summary (7 issue areas + regression)
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
