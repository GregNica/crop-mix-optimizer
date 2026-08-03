# PLAN — the execution sequence (Fable audit, 2026-07-31)

**What this is.** `BACKLOG.md` stays the ledger of everything open. `DECISIONS.md` records the
grower's rulings with evidence. **This file is the SEQUENCE** — what to build, in what order, with
an attack plan per item, written so an executor (Opus) can run a batch end-to-end without
re-deriving the reasoning. When this plan and the backlog disagree, fix the disagreement in the
same commit that discovers it; divergence between lists is how Phase B failed.

**Audit verdict in one paragraph.** The project is not lost in the weeds — the guard-heavy work of
the last week was aimed at the code with the worst defect record and it caught real money errors
same-day. But the backlog under-states the three things that now matter most: (1) the **cost model
is incomplete in one coherent way** (no land rent, no DIRTI ownership costs, no crop protection, a
16% overhead guess covering all of it) — five scattered rows are really one project worth 4–9
margin points; (2) **cash timing is fiction** everywhere except wages — and `STRATEGY.md`'s own
bet-① ranking says payment terms are the output-moving lever; (3) the **wizard interface is the
declared direction with no work item anywhere**. Meanwhile several rows are stale (W13's defect
half is already resolved by W12; T2's premise expired), one locked non-goal (volume basis) is
contradicted by a new measurement, and the product still has **no finish line: N growers is unset**.

---

## Standing guardrails — read before every batch

These are the compressed lessons of the last two weeks. Each one is paid for.

1. **Verify first, and measure the axis the fix does not mention.** A backlog row naming a fix is
   a hypothesis (W6's prescribed fix was wrong on both axes; W4's twice).
2. **Order: working code → `/simplify` → mutation-verified guards → browser QA last.** Guards
   written before `/simplify` get re-derived (measured cost: a full cycle, twice).
3. **Mutation-test the money path; do NOT gold-plate reports/views with mutation harnesses.**
   Reports get ordinary jsdom/pytest coverage. Money = objective, constraints, cost splits,
   adapter forwarding of money keys.
4. **Run the mutation, never trust the reasoning.** Five inert guards shipped in one day; two C13
   fixtures were inert in ways only running the mutation exposed (bought hours outside the binding
   prefix; an equal-profit cash plateau).
5. **File-copy backup for mutation testing — never `git restore`/`checkout`** (destroyed
   uncommitted work twice in this repo's history).
6. **After editing `farm_v2/`**: `python3 scripts/sync_solver_blob.py`, and run
   `npm run test:blob && npm run test:payload`.
7. **Embedded Python must not break out of its JS container.** ~~No backticks inside
   `PYTHON_CODE`~~ — retired 2026-08-02 by E2: there is no template literal any more, and a
   backtick inside the blob's double-quoted JSON is an ordinary character. **The CLASS moved
   rather than died**, which the retirement nearly missed: the blob sits in an inline `<script>`
   and `json.dumps` does *not* escape `/`, so a `</script` in any `farm_v2/*.py` would close the
   tag early and blank the page — invisibly to every Python test, exactly the backtick
   asymmetry. Now closed by construction (`sync_solver_blob.py` writes `<\/`) with a fail-closed
   backstop in `tests/test_blob_sync.py`, both mutation-verified. **The lesson generalises: when
   you retire a guard because its mechanism moved, ask what the mechanism's CLASS is.**
8. **When you kill a coercion idiom, grep the pipeline for the IDIOM, not the field** —
   `parseFloat(x) || d` and present-None-defaults each resurfaced one layer away, same day they
   were "fixed".
9. **Every `Math.abs(x) > tol` / `x > 0` guard is a NaN-fails-open candidate.** New tripwires fail
   CLOSED: `!Number.isFinite(v) || Math.abs(v) > tol`.
10. **Solver owns money; the UI renders and never recomputes** (locked). New outputs = solver
    returns → adapter forwards → UI reads. The adapter-forwarding step is the recurring
    false-green (4 instances); every new money key gets an adapter-executing test.
11. **One open semantics change at a time** (locked operating rule). A batch below = one semantics
    change; do not interleave batches.
12. **Golden re-pin protocol.** Re-pin once per batch, at the end, in its own commit: assert the
    DIRECTION (net margin must move DOWN toward 5–15% for B2; document the per-line deltas in the
    commit message; if `profit` moves but `operating_profit` does not, suspect tie-break
    degeneracy before a defect (measured precedent: $5.30 interest from float ordering).
13. **New inputs pass the complexity test** (locked): "what information does a farmer have readily
    available and is ready to give?" — not most-accurate, not simplest.
14. **Anti-lurch:** classify each finding (defect/value/phase/track/strategy) before acting;
    strategy-tier waits for the grower in a separate session.
15. **Browser QA by the grower at every batch boundary that touches the UI.** The last two
    sessions' worst defects were found there, not by the suite.

---

## Batch 0 — Hygiene and stale-row closure (no semantics changes, no re-pin)

Small, independent, safe to do in any order. Clears the decks.

**0.1 · X1 — one `downloadCSV(rows, filename)` for all five exporters. ✅ DONE 2026-07-31.**
Five call sites, one implementation, new `tests/csv_safety_client.cjs` covering all five with
hostile names, registered in both runners. **The attack plan below was wrong on both live
instances** — measuring the real exports is what showed it, and the fix differs accordingly:
the gantt wrote 3 risky cells (the `--- Crop ---` separator fires for BENIGN names, every export)
while the P&L wrote ZERO, because U+00A0 indentation already shields it — the *guard* was the
thing at fault there, `^\s*[=+@]` matching U+00A0 and calling a correct file broken. Two
mutations that should have died didn't: an over-strict `\s` survived the first pass, and
`/simplify` silently deleted the negative-amounts guard along with a genuinely subsumed block.
New rows: **S21** (delete the gantt separator — the only everyday neutralisation). Detail in
`BACKLOG.md`'s X1 entry.

Original attack plan, for history:
Five sites (`index.html` ~4826/8214/8324/9140/9418 at last verification — re-grep) inline
byte-identical quote-escaping + BOM + anchor, and only the P&L knows the formula-prefix rule.
Attack: one helper owning escaping, BOM, anchor, and neutralising a leading `=`/`+`/`@` on
non-numeric cells — **must NOT ban a leading `-`** (amount columns). Live instances to fix by
using it: the gantt's `--- ${cropName} ---` row; P&L labels built from user-typed channel names
(`+Market` reintroduces the defect today). Then point the per-cell assertion in
`tests/cost_splits_client.cjs` at all five exports. DONE = five call sites, one implementation,
harness covers all five.

**0.2 · E7 — `escHtml` at every render boundary that interpolates user strings. ✅ DONE 2026-08-01.**
Measured rather than counted: a jsdom probe pushed a hostile name through the real render
functions and asked whether an ELEMENT appeared. **10 surfaces, 36 elements**; `escHtml` 15 → 35.
Two things worth carrying forward:
- **ONE HOSTILE FIXTURE IS NOT ENOUGH — this row's attack plan would have missed the worst of
  it.** A text payload (`<img …>`) finds text sinks; it sails through `value="…"` untouched. The
  attribute-breaking payload (`" data-xss="1`) found two more surfaces the first structurally
  could not see, and they are `applyCrops`/`applyChannels` — the **input form**, where a hostile
  name typed once persists into every saved plan. Any future injection sweep uses both.
- **The deepest fix was a render primitive, not a sink.** The summary pane's `kv(k, v)` is what
  every row goes through; escaping inside it replaced ~20 call-site edits. Look for that shape
  first.
- **"Five mutations, all die" was the wrong measurement, and saying so is the point.** That was
  true of the five run and overstated the guard badly. Unwrapping EVERY `escHtml` in the file —
  60 sites, one at a time — found ~34 surviving. Chasing the reachable ones found two more real
  defects: `renderCSVErrors` RETURNS markup instead of writing it, so driving it and scanning the
  document proved nothing (an inert entry that read as coverage), and `renderLaborRow` puts
  `count`/`wage`/`hours` into `value="…"` unescaped — reachable because a saved plan is
  user-supplied JSON. **Mutation-test the guard's COVERAGE, not a sample of it.**
The mirror defect (over-escaping, invisible to a markup-hunting test) is pinned in the same
harness. `tests/escaping_client.cjs`, registered in both runners; the ~30 escapes that remain
unpinned are mapped by cause in BACKLOG **S22** rather than left as a vague caveat.

**0.3 · E8 — stop rendering the matplotlib waterfall on sweep solves. ✅ DONE 2026-07-31.**
`skip_charts` payload flag, ABSENT = draw (a caller that does not know the flag keeps its image);
five sweep paths — What-If labour, What-If scaling, diagnostic replay, sensitivity, Monte Carlo —
now share one `solveForNumbers()` that stamps it. What the measurement actually found:

- **The bigger waste was not the one this row named.** `make_heatmap_chart` (~119 ms) ran on
  every solve *including the main render* and was never put in the result dict at all — no
  consumer could exist. Deleted. Two result keys were dead the same way (`successions_table`,
  `storage_cap_m3`): −5,683 bytes, **14.6% of the non-chart payload**, crossing the Pyodide
  boundary on every solve.
- **Honest figures.** Waterfall ~49 ms median over 20 warm calls (47–72 ms). A cProfile of a
  2.9 s golden solve puts *all* Python-level adapter work at ~27 ms — the chart alone was more
  than twice everything else combined, which is the real argument. Per sweep solve the result
  JSON goes 81,615 → 33,340 bytes; profit identical to the cent.
- ⚠️ **The DONE criterion asked for MC wall-clock in the BROWSER and that is NOT measured.**
  Everything above is CPython. Pyodide is slower, so the browser saves more — but that is an
  extrapolation, and this plan's own rule says an extrapolation is a hypothesis. **Capture one
  before/after MC run at the grower's next browser QA** and record it here.
- Deliberately NOT fixed, recorded as **BACKLOG S20**: the five sweep paths have no solver
  timeout (only `runOptimizer` does), so one pathological Monte Carlo draw hangs the tab.
  Pre-existing; adding a timeout aborts work that completes today, which is a behaviour change.
  `solveForNumbers` is now the single place to put one.

**0.4 · W7 — delete the hidden constraint panel. ✅ DONE 2026-07-31.**
Card + `renderConstraintSummary` + T18a deleted; `demand_saturation` still flows to the pills and
the CSV. Net −281 lines. Three things worth carrying forward:
- **The guard, not the deletion, was the work.** The jsdom harness drove the panel in five
  sections. Re-pointing them at the export needed a decision per assertion, not a move: two moved
  (one strengthened — the at-cap threshold is now driven at a non-default 0.80), one was
  **retired** (row order from params — the export ranks by binding, so there was nothing to point
  it at), and one was **dropped by my first pass and caught by review**: "an annual contract has
  no weekly ceiling", which the panel showed as a blank cell. The export was printing the annual
  fill under "Peak Util %" — the `annual/52` fiction class, back for the third time. Fixed in the
  export, pinned in §2, mutation-verified.
- **A fabricated number went with it.** The panel's diversity rows read `ci.diversity_fraction`,
  a key that exists nowhere, so every row fell through to `1/numCrops`. New row **S19**: C8 is the
  one constraint no surface reports, and the exec-summary tooltip claimed otherwise (copy fixed).
- Five mutations run, five dead. `/simplify` found the harness had grown its own `captureCSV` —
  the duplication `jsdom_app.cjs` was created at W4 to end.

**Consequence now live:** C2 (D4's committed-sales view) has no home to render into; it builds its
own surface, or the assistant renders it. That was flagged in the W7 row and is recorded here so
it is not rediscovered.

**0.5 · Stale rows — close or rescope in `BACKLOG.md`. ✅ ALREADY DONE** by the audit session
itself (`53a1c44`/`ca4f446`) — verified 2026-07-31, no work needed. All three below are applied:
- **W13**: verified 2026-07-31 — post-W12 the margin kernel carries `labor_hours_per_acre`
  (physical) and no labour dollars, so the "hurdle uses a labour cost the objective no longer
  charges" defect is **gone**. Rescope the row to what remains: the *instrument* question
  (delete / per-channel exclude checkbox / keep as-is), plus the standing rule that the chatbot
  must not set it until the instrument question is settled. Default stays 0 = off.
- **T2**: the regression suite is green and rebaselined; the row's premise ("permanently red,
  pins a March baseline") expired. Close it.
- **W8 row**: annotate that (a)–(d) are scheduled inside Batch 1 (E2), so the row and the plan
  cannot drift.

**0.6 · U1-interim — RESOLVED 2026-07-31: DO NOT DO IT.** Grower ruling: *"For the UI, we will
handle that with the wizard."* No interim move, no pointer, no relabel. The labour-flex controls
stay exactly where they are until Batch 7 redesigns them. ⚠️ **Consequence to hold consciously:
the setup toggle continues to do nothing on a normal Optimize — a known say-do gap, accepted
deliberately rather than overlooked.** It is Batch 7's first input, not a defect to re-report.
The unreachable exec-summary "Bought Labor" block stays too (it is dead code, not a wrong number);
delete it when the panel is rebuilt.

---

## Batch 1 — Structural enablers (E2 + W8, then E5)

**1.1 · E2 — extract the Python adapter to `farm_v2/adapter.py`. ✅ DONE 2026-08-02.**
568 lines left `index.html`; `farm_v2/adapter.py` (493) + `farm_v2/charts.py` (107). **Proved
equivalent BEFORE the page was touched, and again after `/simplify`:** same result-dict key set,
zero value diffs, profit identical to the last digit ($428,546.6374901873), and the waterfall PNG
byte-identical (same SHA, 42,592 B). 407 pytest / 11 harnesses / blob + payload green.

Carry forward:
- **`skip_charts` is DELETED, not moved.** Once drawing is a separate call the flag has no work
  to do, and a sixth sweep path cannot forget a flag that does not exist. E8's saving is now
  structural. Its two flag tests became four sharper ones, incl. a SUBPROCESS check that
  importing the adapter pulls in no matplotlib — an in-process `sys.modules` check could not
  fail, since pytest may have imported it already.
- **The blob-sync trap fired and the guard caught it**, exactly as this plan predicted: the sync
  script reported both new modules "on disk but NOT embedded" before they were added.
- ⚠️ **`/simplify` found FIVE in-page self-tests that were TAUTOLOGIES** (T162c, T189a/b/c, and
  T145 partly). They grep `document.documentElement.innerHTML`, which contains the assertion's
  own source — and four checked for `p.get('rate_irrigation'`-style strings the adapter has
  NEVER contained (it uses `_num`). They would pass with `FARM_V2_FILES = {}`. Pre-existing, not
  E2's doing, and my own first check was fooled the same way (the string IS in the page — in the
  test). Re-pointed at the parsed blob, where the haystack cannot contain the needle. **Any
  in-page source grep must read `pySrc(file)`, never `innerHTML`.**
- One behaviour improvement, deliberate and not a pure move: a chart failure used to hit the
  adapter's blanket `except` and cost the grower the whole plan; it now costs the drawing.
  Plus a `requestAnimationFrame` yield before the draw — `stopProgress` had already marked the
  bar complete, so without it the grower saw a finished bar over a frozen tab.
- ⚠️ **NOT verified: the Pyodide boot path.** pytest proves the module imports under CPython and
  the blob check proves it ships, but nothing executes `from farm_v2.adapter import run_from_js`
  in a browser — jsdom cannot run Pyodide. **Browser QA must confirm boot + a drawn waterfall.**

Original attack plan, for history:
WHY: ~340 lines of money-affecting Python in a JS template literal, testable only by regex
extraction; produced two reviewed defects and one page-breaking backtick this week; prerequisite
for the server path (bet ③) and for any second caller.
ATTACK:
1. Move `PYTHON_CODE`'s body to `farm_v2/adapter.py` (`run_from_js(params_json)` unchanged
   signature). The page loads it through the same `FARM_V2_FILES` blob mechanism the solver
   already uses (sync script extends to the new file; the template literal shrinks to a loader).
2. Re-point `tests/test_committed_wages.py::_run_from_js` / `_adapter_code()` and
   `tests/test_adapter_contract.py` at a plain import. Delete the regex extraction and the
   backtick tripwires (obsolete by construction — note that in the commit).
   ⚠️ **Added by E8, collect it here:** `test_only_the_rendering_path_calls_the_solver_without_
   skip_charts` counts `runPythonAsync(\`run_from_js` sites in `index.html`. After this move it
   keeps PASSING while its docstring reasons about a layout that no longer exists — quiet
   staleness, not a loud break, which is the worse failure. Re-point or retire it in this step.
3. **Take the chart out of the adapter while it moves** (E8 finding). Every argument
   `make_waterfall_chart` takes is already in the result dict, so a separate `chart_from_js
   (result_json)` the render path calls after the solve is a pure move — and it deletes the
   `skip_charts` flag, its default question, the source-level test above, and the matplotlib
   strip/stub hacks in three test modules. Otherwise `farm_v2/adapter.py` imports matplotlib at
   module scope and **the server path has to ship matplotlib to run the money adapter.**
3. `tests/test_golden_farm.py`'s extractor likewise.
GUARDS: the existing adapter-contract suite IS the guard; it must pass unmodified except for the
import mechanics. Blob-sync test extends to the new file.
TRAP: the blob write path — `sync_solver_blob.py` must treat `adapter.py` like the other
`farm_v2/` files or the browser runs a stale adapter while pytest runs the fresh one (the exact
false-green class this repo documents).
DONE = no `PYTHON_CODE` literal (or a one-line loader), all 399+ tests green with imports instead
of regex, blob check covers the adapter.

**1.2 · W8 — totals summed from parts, in the same seam (one commit each):**
(a) solver returns `total_cost` + `bought_capacity_split`; exporter iterates instead of
hand-naming three keys. (b) **move the `fixed_selling_cost` deduction from the adapter into the
solver** — every non-browser caller currently gets a profit that silently ignores channel fixed
selling; this re-pins direct-caller baselines → own commit, documented delta. (c) build
`channel_sales` first and derive `revenue` from it (turns two equal-today accumulations into one
by construction). (d) two `opReconcile`-shaped tripwires for the P&L's REVENUE and SELLING
sections (fail-closed per guardrail 9). Mutation-verify (b) and (d) only — they are money.

**1.3 · E5 — ONE field registry, keyed by what the payload carries.**
WHY: three overlapping registries drift; `FORM_STATE_VERSION` is stamped and never read;
`applyFormState` silently drops renamed ids from saved plans. Must precede the wizard; grower
approved "before we build much more".
ATTACK: single registry entry per field: payload key, form id, unit spec, provenance/benchmark,
chat description, version-added. `DATA_F_REGISTRY` / `CROP_PROVENANCE` / `CHATBOT_FIELDS` become
views over it (delete what becomes redundant). `applyFormState` reads `FORM_STATE_VERSION`, runs
explicit migrations, and **reports** unknown ids (G6's say-do rule) instead of skipping.
GUARDS: round-trip test: save under version N−1 fixture → load → every field lands or is loudly
listed. A completeness assert: every payload key the adapter reads has a registry entry (the
E5b concern — solver-vocabulary keys — is satisfied by keying on payload, per the E5b row).
⚠️ That assert needs an exemption list for payload keys that are not farm facts: `skip_charts`
(E8) is the first, and asking "what does a farmer have readily available" of it is a category
error. If the exemption list grows past a couple of entries, that is the signal the payload is
carrying two different kinds of thing and wants splitting.
DONE = one source of truth, three views, versioned migration path, silent-drop impossible.

---

## Batch 2 — Cost completeness (the M1 batch; ONE semantics change; ONE re-pin at the end)

The audit's central finding: these five rows are one project. Missing pieces plausibly total
**4–9 margin points** (land 0.9–3.0, repairs 1–2, interest-on-capital 0.5–1, property tax 0.3–1,
insurance 0.2–0.9, crop protection ~1.2, electricity ~0.2 — evidence in `DECISIONS.md`). Order
inside the batch matters; the overhead ledger comes FIRST or every later line double-counts.

**2.1 · R8 — the overhead decomposition ledger (NEW row; do first).**
WHY: `overhead_pct_of_revenue` = 16% flat = **$341,525**, the second-largest cost line, and it is
a placeholder that *by its own definition* contains insurance, taxes, repairs, utilities, admin.
Every explicit cost added below must decrement it or the farm pays twice — the W10 electricity
double-count warning, generalised.
ATTACK: give overhead an explicit composition. Implementation shape: keep ONE
`overhead_pct_of_revenue` input but pair it with an itemised list of named lines the model now
charges explicitly (each new line from 2.2–2.5 registers itself); render the P&L's overhead row
as "Overhead (excl.: insurance, property tax, repairs, utilities — itemised above)". Ship a
benchmark default for the residual (research: what does a diversified-veg budget put in
"office/admin/misc" once the big lines are explicit — typically 3–6% of revenue, source it).
The grower re-enters their own overhead % once, told exactly what it should now exclude.
COMPLEXITY TEST: passes — farmers know their bills; nobody knows "16% of revenue".
GUARDS: a reconciliation test: itemised lines + residual = the old total within tolerance on the
golden farm at defaults (documents the decomposition), plus the P&L tripwire already in place.
DONE = overhead is a defined residual, not a bucket hiding the batch's own additions.

**2.2 · R7 — land rent + complete ownership cost (DIRTI) (NEW row).**
WHY: land rent reads $0 (23.2% of US farms pay cash rent; largest rented line); the six owned
asset classes carry depreciation ONLY — no Interest, Repairs, Taxes, Insurance — so ownership is
systematically under-costed and any rent-vs-own comparison is rigged toward owning.
ATTACK (respecting the complexity test — do NOT ask per-asset DIRTI questions):
1. **Land**: `land_owned_acres` / `land_rented_acres` + `cash_rent_per_acre_yr` (benchmark
   default: NASS 2025 irrigated $245/ac, disclosed as a row-crop average that understates veg
   ground — sources in DECISIONS appendix). Charged as a weekly fixed line with the existing
   property/mortgage field folded in coherently.
2. **Owned-asset carrying costs**: per asset class, compute I-R-T-I as simple percentages of
   undepreciated capital with sourced defaults (extension figures: repairs ~2–4%/yr of new cost
   for machinery, taxes+insurance ~1–2%, interest = rate × average investment). ONE farm-level
   override knob ("ownership carrying %"), not five fields per asset.
3. **Insurance (R2)** rides here: one farm-level premium field with an optional **payment week**
   (lump hits C13 in that week — the W12 seasonal-wages lesson; flat only if week unset).
   Disclose in the assumptions box: indemnities are revenue in bad years and the model has no bad
   years (deterministic yields), so insurance reads as pure cost by construction.
4. Each line registers in 2.1's ledger.
GUARDS: money-path — mutation-verify the C13 payment-week timing and the carrying-cost charge.
DONE = ownership costed as D+I+R+T+I, land tenure expressible, insurance timed.

**2.3 · R1 — crop-protection cost category (mechanism now; defaults in Batch 3).**
ATTACK: sixth variable-cost category `crop_protection`, charged like fertiliser (per-acre by
phase). After W4's refactor this is one edit in `vc_weekly_split` + `VC_CATEGORIES` + a form
field per crop + P&L row (which appears automatically — the exporter iterates). Ship with 0
defaults and the label honest about it ("$0 until entered — defaults arrive with the crop-data
sweep"); Batch 3 fills per-crop defaults from extension budgets. The grower's rate×price
granularity is a later refinement via the C3 mechanism — do not build two shapes now.
GUARDS: the existing split-reconciliation tests extend by construction; one keyword-wins assert
already guards `dict(zip(VC_CATEGORIES,...))`.

**2.4 · W10 — electricity as an entered cost (inside the ledger).**
Grower ruling: an entered bill beats a computed pump cost. One `utilities_cost_per_year` (or
/week) field, registered in the 2.1 ledger (i.e., stated as excluded from the overhead residual),
and the P&L water row relabelled to say why it is $0 at the margin ("on-farm supply; pumping
energy in Utilities"). Sub-question for the grower recorded in DECISIONS (whole bill vs
irrigation share) — ship whole-bill, disclosed.

**2.5 · W17 — prefill the hired wage.**
Source a defensible regional default (USDA NASS Farm Labor survey field-worker wage for the
region; same provenance treatment as other benchmarks), prefill the field labelled "estimate —
correct this", make blank an explicit "infer from my crew" choice rather than the silent default.
Inference stays as the labelled fallback. Update the $25.33 expectation tests to the new contract.

**2.6 · Re-pin.** One commit. Expect margin to fall from 20.1% toward the 5–15% band; assert
direction; document every line's delta. If it falls BELOW ~5%, stop and re-examine defaults
before shipping (over-charging is the mirror error; four fixes moved margin wrong by over- or
mis-charging).

---

## Batch 3 — Crop data truth (M2/M9/M4/M7/M10 + C8; ONE re-pin)

The library's 29 templates feed everything and have never been audited (the July audit "reviewed
the machine, never the numbers fed into it"). Strategy sanctions this now EXCEPT the
channel-adjacent slice (demand/price laugh-test is held pending bet ①; prices are user-owned
farm-specific inputs by locked non-goal — audit their PROVENANCE, not their truth).

**3.1 · M9 — the volume basis (⚠️ amends a locked non-goal; get the grower's one-line sign-off).**

⚠️ **URGENCY CORRECTED 2026-07-31, after this plan's first draft. M9 is LATENT, not active — it is
not changing today's plan, and my earlier "rationing the largest crop" claim was wrong.** Measured:

| pool | peak / cap | binds? | crops in it |
|---|---|---|---|
| cold | 135 / 275 m³ = **49.3%** | no | Spinach, Cucumbers, Kale, Tomatoes, Hot Peppers |
| ambient | 136 / 150 m³ = **90.5%** | **no** — never reaches 100% in any week | Garlic, Basil |

Three corrections to the first draft: (a) **neither constraint binds**, so nothing is being
rationed by these numbers today; (b) the ambient crops are **Garlic and Basil**, not "cured alliums
and winter squash", and garlic's 23.7 lb/ft³ is one of the values the research marked as roughly
RIGHT (~25–30); (c) **basil is not covered by the research table** — it covers greens/roots/fruits,
not herbs, and fresh herbs are genuinely very bulky, so basil's 5.0 lb/ft³ may be closer to correct
than the general ~2× pattern implies. **Do not assume basil is wrong without a source.**
Correcting the densities would make both pools *looser*, so the plan would not move.

The defect is still real (scale ~2× low across the covered crops; spinach/cucumbers rank order
flipped ~3×) and still worth fixing for correctness and for farms with smaller storage than the
demo — but it is **credibility work, not plan-changing work**.

**✅ SIGN-OFF OBTAINED 2026-07-31** — the non-goal is narrowly amended in `STRATEGY.md` (amendment
recorded there, at the lock). **Scope is exactly two things, done together, at the TAIL of this
batch:**
1. Correct the 29 template density values against the pack-weight table.
2. Pull the **room derate** (~35–40% product-to-gross) out of the per-crop densities and into the
   capacity input, defaulted and disclosed.

They are **coupled — do not ship one without the other.** Fixing densities alone roughly halves
occupancy and leaves the demo's 275/150 m³ capacities looking oversized; the derate is where the
missing ~2× actually lives.

**Explicitly OUT of scope** (do not expand into these): the container-picker input — that is
wizard-era input design, deferred to Batch 7; researching pack basis per buyer or region; any
further precision. The fail-closed implied-density tripwire is worth keeping as a cheap guard, but
it is optional if it grows past a few lines.

**Priority: last item in the batch.** If Batch 3 runs long, this is the piece to drop — it changes
no current plan. Re-check bindingness after the batch's other work: if the crop-data sweep moves
yields enough to make either pool bind, promote this immediately.
ATTACK: (a) container PICKER (1-1/9 bu carton 1.383 ft³ / bushel 1.2445 / RPC lug 1.006 / 18-gal
tote 2.406 / bulk bin 28.7 / 50-lb sack) — container supplies volume exactly; `lb per container`
becomes an optional override. (b) per-crop default densities from the pack-weight table.
(c) fail-CLOSED tripwire on implied density >1.5× outside the published range. (d) **pull the
room derate out of the crop numbers**: product-to-gross ~35–40% as a property of the capacity
input, defaulted and disclosed — this is why every current density reads ~2× low. (e) grower's
tote measurement (2–3 crops) validates (d) when it arrives; do not block on it.
GUARDS: storage is money-adjacent (it binds) — mutation-verify the derate and one density path.

**3.2 · M2 — the per-crop sweep** (crop-impact order, garlic first): yields and windows against
extension sources; water/fert continuation; **M7** seeding rate / plant density per crop (needed
for D5, and VeggieCropper parity); **M4** wire `planting_type` into the math it was always meant
to feed (D2's blocker; M8's Napa/Melon ambiguity resolves here); R1 protection defaults land
here. Record provenance per field in the E5 registry — **C8 (benchmark-deviation report) then
falls out as a structured export**, not a panel.

**3.3 · M10** — fix the Snap/Snow Peas single-succession template while in the file.

**3.4 · M3 — adversarial refutation pass** over the refreshed library (agents attack the values;
the grower's intuition pass on the survivors), then **re-pin once** with the same direction
protocol as 2.6.

---

## Batch 4 — Honest risk (W2/W3/C9/C5/P14)

**4.1 · W2(b) — freeze-and-evaluate.** Solve once; fix `x`/`y` (bound to solution); re-solve the
LP (sales allocation only, no binaries) per draw. This is both the honesty fix AND a large MC
speed-up (LP evals vs MILP solves — measure and record). The gap between clairvoyant mode and
frozen mode is itself reportable: the value of perfect foresight.
**4.2 · W2(c) — the conservatism dial.** Plan at an adjusted percentile of yields/prices
(parameter transform; no new variables). Label as a conservatism dial, NOT an optimum — CV alone
does not derive the right shift (DECISIONS C5 records the math discussion with the grower).
**4.3 · W3 — retire the "Fragile/stability" labels** (artifacts of clairvoyance) in the same
commit as 4.1, replaced by frozen-plan spread.
**4.4 · C9 — the headline carries the range** ("$X projected — typical range $Y–$Z" from frozen
draws) + the assumptions box finally discloses deterministic yields / no crop failure.
**4.5 · C5 — downside What-Ifs** (−10/−20/−40% and named scenarios like "wholesale halves");
the scaling machinery already exists, factors just refuse <1 today.
**4.6 · P14 — near-optimal alternative plans (restored decided-item).** Python side only (the
2026-07-27 decision): enumerate near-optimal plans (solution pool via repeated solves with
no-good cuts or objective-gap constraint), summarise deltas. Defer any UI; the assistant renders.

---

## Batch 5 — Cash reality (bet ①'s output-moving slice; spec-first)

`STRATEGY.md` ranks payment terms and CSA financing as the levers that actually change outputs
(C13 and the interest line "are fed fiction today"). This batch upgrades D7 from itemised to
honest-in-time. **Write the small spec first and confirm shapes with the grower** — strategy
class requires it.

**5.1 · P3 — payment terms per channel** (net-N shifting revenue weeks in C13; market immediate).
**5.2 · P4 — CSA prepayment as financing** (cash in early weeks against delivery obligations).
**5.3** · Sweep the remaining flat-timing fictions: insurance week (done in 2.2), fixed selling
annual vs weekly, any deposit-style costs. C13's cash floor and `interest_cost` become the
deliverable D7 claims to be.
GUARDS: C13 timing is money — mutation-verify against the tight-cash fixtures from
`test_cash_floor_guards.py` (extend, don't duplicate).

---

## Batch 6 — The C3 mechanism (spec → grower review → implement)

Grower ruling: ONE mechanism, and collapse existing solver machinery into it. The shape: **a
bought resource with a price, a basis (hour / acre / bin / ton / lb / week), a cap, and a scope
(farm or crop × operation)**.

**6.1 · Spec** (a real document): the lever table. Existing occupants to consolidate: overtime,
hire (the ~7 copy-pasted block pairs already flagged by review), city water, cold + ambient
storage pools. New occupants: contract/custom work per acre-bin-ton (R4), U-pick harvest-labour
offset per channel (R5), equipment rental / custom hire (research says custom-hire beats tractor
rental for this size), M5 establishment operations, M6 propagation, P8/P13-machinery. State
explicitly what `piece_rate_per_lb` becomes: **first consumer of the mechanism, or deleted** —
it is currently computed and read by nothing.
**6.2 · Grower reviews the spec** (track-class scope change).
**6.3 · Implement** — this rewires the guarded money path: full discipline (guardrails 2–5, 10,
12), and the C13/capacity guards must survive or be consciously re-derived.

---

## Batch 7 — The wizard (design WITH the grower; not for solo execution)

Gated on E5 + E2 (both land in Batch 1). This is where U1/U1a/U2 (labour controls), W13's
exposure rule, W7's assistant-rendered constraint views, G4's data policy ("what is sent, what is
retained"), and G6's say-do reporting all land. The seeded assets: `worker/grounding.ts`,
`CHATBOT_FIELDS` (absorbed by E5), the propose-then-confirm flow. **Do not start this solo** —
it is the product's face and every open UI decision was deliberately deferred INTO it.

Also in this horizon, not before: Tier 7 pilot hardening (the moment anyone else gets the URL),
and **setting N** — the definition of done ("N real growers produce a season plan they would act
on") still has no N.

**✅ DEFERRED 2026-07-31 by grower ruling** — *"I'm not really thinking about the pilot yet and we
can address that later."* This is a conscious deferral, not the oversight it was before: N was
unset for months without anyone noticing, and that is what left the July plan's Phase C
unexecuted. It is now deferred **on the record, with the consequence stated**: while N is unset,
Batches 2–6 have no external forcing function and will be paced by model quality alone, which is
the correct posture *only* while no pilot is intended. ⚠️ **Executor rule: do not silently
re-scope any batch on pilot-readiness grounds** — if pilot timing starts driving a decision, that
is the signal to go back and set N first. Revisit when the wizard (Batch 7) is in view, since a
usable interface is the precondition for anyone outside this project producing a plan at all.

---

## Deliverables placement (so they are not orphaned)

Per the interface direction, deliverables ship as **structured solver returns + CSV/exports the
assistant can render**, not new panels. C7 (labor calendar) and C2 (commitment schedule) are the
first two — both are views over data that already reconciles; schedule them as the *validation
step* of Batch 2 (C7 makes the $855k wage line legible week-by-week — the natural check on the
cost batch) and Batch 5 (C2 is what payment terms make honest), rather than as a separate batch.
C6 (yield series) falls out of Batch 3's library work. C1 (printable season plan) and C3/C4
(break-even, shadow prices) queue behind the wizard's rendering surface.

## Explicitly parked (so silence is not drift)

Tier 7 (until a second user is imminent — grower confirms not deployed); plot-level modelling,
weather prediction, price/demand research (locked non-goals, unchallenged); P1/P2/P5–P12 beyond
the Batch-5 slice (bet ① sequencing, grower-gated); E6 (rides the wizard); the M1 number itself —
**never chase it directly; it is the scoreboard, not the work** (grower posture, evidence in
DECISIONS).
