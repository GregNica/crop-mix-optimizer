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
   asymmetry. **The first fix escaped `<\/` and was WRONG IN BOTH DIRECTIONS** (`617cc53`):
   `</script` is not the only sequence the tokenizer acts on — an unterminated `<!--` plus a later
   `<script` reaches script-data-double-escaped, where the element's own `</script>` no longer
   closes it — and a raw `</script` is what EXITS that state, so neutralising it removed an
   accidental escape hatch (measured with parse5: page intact before, swallowed after). Now closed
   by construction — `sync_solver_blob.py` escapes **every `<`** as `\u003c` — with a fail-closed
   backstop in `tests/test_blob_sync.py` that reads the RAW line, plus a `TestBlobWriter` over a
   hostile fixture (the writer previously had NO test: no `farm_v2` module contains `<`, so
   deleting the escape left the suite green). All mutation-verified. **The lesson generalises
   twice: when you retire a guard because its mechanism moved, ask what the mechanism's CLASS is —
   and then check you have not drawn the class too narrowly. Escape the character class, not the
   sequence.**
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

## Batch 1 — Structural enablers (E2 + W8, then E5, then T4)

**1.1 · E2 — extract the Python adapter to `farm_v2/adapter.py`. ✅ DONE 2026-08-02.**
**✅ BROWSER-VERIFIED 2026-10-19 by the grower** on `54e8451` (wrangler, Edge): Pyodide boots with no
app errors in the console, Optimize solves, and the Profit Waterfall draws. Monte Carlo runs at
~7-8 s/draw in the foreground (faster than August's 12+ s). A BACKGROUNDED run measured ~3x slower
(~21-22 s/draw), NOT fixed by a timer-free hidden-tab yield nor by Edge's efficiency setting —
cause unknown, measurement snippet in BACKLOG Q3.
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
- ✅ ~~NOT verified: the Pyodide boot path.~~ Resolved twice: the grower's browser QA
  (2026-10-19: boot + a drawn waterfall) and T4 (`npm run test:smoke`, `930542a`), which boots
  the shipped page in a real browser and runs `from farm_v2.adapter import run_from_js` on every run.

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

**1.2 · W8 — totals summed from parts, in the same seam (one commit each):** ✅ **DONE 2026-10-19** — one commit, not two: (b) re-pins nothing, because every browser path already went through the adapter (measured). See BACKLOG W8.

(a) solver returns `total_cost` + `bought_capacity_split`; exporter iterates instead of
hand-naming three keys. (b) **move the `fixed_selling_cost` deduction from the adapter into the
solver** — every non-browser caller currently gets a profit that silently ignores channel fixed
selling; this re-pins direct-caller baselines → own commit, documented delta. (c) build
`channel_sales` first and derive `revenue` from it (turns two equal-today accumulations into one
by construction). (d) two `opReconcile`-shaped tripwires for the P&L's REVENUE and SELLING
sections (fail-closed per guardrail 9). Mutation-verify (b) and (d) only — they are money.

**1.3 · E5 — ONE field registry, keyed by what the payload carries.** 🟡 **E5a DONE 2026-10-19** (silent-drop impossible + the save/load unit drift it uncovered — see BACKLOG E5); ✅ **E5b DONE 2026-10-19** — see BACKLOG E5. ⚠️ **"version-added" is DROPPED from the DONE criteria, on purpose:** E5a's `applyFormState` already detects a field a saved plan predates by ABSENCE (and fills the default, with a note), which is everything a `since` tag would have bought; an unused tag on 52 entries would be decoration. Follow-ups filed as **E5c**.
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
✅ (resolved by E5b) The exemption-list worry is moot: `skip_charts` was deleted by E2, and
fields that are not farm facts are marked `unsent` in `public/fields.js`, so no separate list exists.
DONE = one source of truth, three views, versioned migration path, silent-drop impossible.

**1.4 · T4 — the headless-browser smoke test (scheduled 2026-08-29; BACKLOG row T4, previously ❓).** ✅ **DONE 2026-10-19** — `npm run test:smoke`. Two spec corrections, both measured: profit cannot match the pin 'to the dollar' (two correct HiGHS builds differ inside the MIP gap), and a real hidden tab cannot be produced headlessly (simulated instead, and said so). See BACKLOG T4/T8/T9.
WHY: **jsdom cannot run Pyodide**, and that single gap is why E2 sat "unverified in the browser"
for four weeks, why every batch boundary ends in a standing human QA ask, and why the
hidden-tab Monte Carlo stall (`0a3c15b`) reached a grower with 407 tests green. Guardrail 15 keeps
grower browser QA — this does not replace it; it stops the *mechanical* half of it (does it boot,
does it solve, does it draw, are there console errors) being a person's job on every batch.
The suite currently has three tiers — pytest over `farm_v2/`, jsdom over the client, blob/payload
sync — and **none of them executes the shipped artifact.**
ATTACK:
1. Playwright (or the `browse` skill's headless Chromium) against `npm run dev` on 8787 — the
   Worker, not `http.server`, so the gate and `/api/*` are the shipped ones. ⚠️ `ss -ltnp | grep
   878` first; a stale wrangler on 8787 means QA'ing old code (documented incident 2026-07-31).
2. Assert, in one run: Pyodide boots; `from farm_v2.adapter import run_from_js` is live; the demo
   farm solves; profit is a finite number matching `tests/test_golden_farm.py`'s pin to the dollar;
   the waterfall `<img>` has non-zero dimensions; **zero console errors**; and the in-page self-test
   suite reports its assertion count (which would have caught the `renderCropChannelHTML`
   ReferenceError that killed 34 lines of it silently).
3. One backgrounded-tab case: run a short Monte Carlo with the page hidden and assert it still
   completes. That is the regression `0a3c15b` fixed and nothing currently pins it.
GUARDS: the test IS the guard. Mutation-check it the cheap way — break the blob (`FARM_V2_FILES =
{}`), stub `paintYield`'s rAF to never fire, and blank the chart call; each must fail a distinct
assertion. ⚠️ **A smoke test that passes against a broken page is the tautology class this repo
has already shipped five times** (E2's `innerHTML` self-tests) — assert on *rendered state*, never
on page source.
SIZE: deliberately small. One spec file, under ~150 lines, not a UI-coverage project. If it grows
past that it has stopped being a smoke test.
DONE = one command that boots the real artifact and fails loudly when it does not work; the browser
QA ask at each batch boundary shrinks to judgement calls (does this number look right to a grower)
rather than "does it run".

---

## Parallel track — the toy model (comprehension, not a batch)

**Not a batch, and it does not take a slot in the sequence.** It exists because the grower
cannot read code, built the original Excel model themselves, and the four subsystems added since
have no Excel ancestor — which is exactly where the last six months of money defects lived. The
process is imported from `SOLVER-REVIEW-PLAYBOOK.md` (the grower's own write-up of running this
on another solver-backed app).

**✅ v1 — spine + storage. DONE 2026-08-29, grower-reviewed and corrected twice. SUPERSEDED by v2** (files deleted; recoverable from git at `240c976`).** `toy_models/farm_toy_v1_spine_storage.xlsx`,
generated by `toy_models/build_toy_v1.py`. 3 crops (Spinach + Kale cold, Garlic ambient),
5 plantings, 52 weeks, no solver — the grower types acres and everything downstream is arithmetic
they can follow. Teaches the one counter-intuitive thing about C4b: **closing stock is zero in
every week and the cooler is still 66.6 m³ full**, because a cooler is sized by throughput, not by
what sleeps in it. Three guided experiments ship with their expected numbers.

Carry forward:
- **The generator reads the app, nothing is retyped** — crop constants from the golden payload,
  planting calendar from `generate_successions`. A retyped sheet cannot be an independent check on
  the app's arithmetic, which is the whole point of it.
- `tests/test_toy_model.py` (11 tests) pins **drift** (constants and harvest weeks still equal the
  app's) and that **the formulas say what their labels say**. Three mutations verified: room
  occupancy reading carried-OUT stock, a crop constant drifting 10%, and garlic silently joining
  the cold pool — all die. The first is the real defect the app shipped for months, and it is
  invisible in a rendered spreadsheet.
- ⚠️ **The grower found a frozen derived column within a minute of opening it** (`lb/harvest wk`,
  five typed numbers beside the live harvest rows they describe) and drew the right inference:
  a stale value at the top means check all of them. That drove `toy_models/verify_toy_v1.py`,
  which **CALCULATES** the workbook with a formula engine and checks three things — values
  against an independent simulator, that every input propagates, and that no number is frozen.
  Run in the suite as a subprocess (the engine cannot install into the system interpreter pytest
  uses, PEP 668; a check that silently skips is not a check).
- ⚠️ **TWO CONFIGURATIONS, and the second is not optional.** At the shipped defaults shrink is 0
  and sell rates are effectively infinite, so a class of sign errors is INERT — `opening - 0 +
  harvest` and `opening + 0 + harvest` agree exactly. Measured: flipping the shrink sign passed
  the value check until a stressed configuration was added. **A guard that only ever runs the
  default fixture is a guard with a hole the size of every optional feature.**
- ⚠️ **The static and evaluating layers catch different things, proved by mutation.** Deleting
  the sell-rate cap entirely passes ALL 17 static guards and fails the evaluating check 9 times.
  Reading a formula as text can only tell you it is well-formed.
- ⚠️ **`formulas` is CASE-SENSITIVE on the filename** in its cell keys. An override posted with an
  uppercased name does not error — it creates a NEW orphan node, the real cell keeps its value,
  and reading the key back returns what was just injected, so the check confirms itself. Cost an
  hour; `calc()` now asserts every override landed. Same family as the E2 `innerHTML` tautology.
- ⚠️ **The `Sold` row uses `MIN()`, which is NOT LINEAR.** Documented on the sheet as a finding
  rather than a shortcut: it is precisely why the real model makes pounds-sold a decision variable
  bounded by a constraint instead of computing it. When the spreadsheet cannot express something,
  that is usually true about the solver.
- ⚠️ **Scale warning, on the sheet itself:** small models are TIGHT, large ones LOOSE. The toy
  teaches MECHANISM; `capacity_series` on the real farm teaches INCIDENCE. No conclusion drawn on
  3 crops becomes a backlog row without re-measurement against the golden farm.

**✅ v2 — loss + storage. DONE 2026-08-29. SUPERSEDED by v3** (files deleted; git `0ab70e3`).** `toy_models/farm_toy_v2_loss_and_storage.xlsx`,
generated by `build_toy_v2.py`, checked by `verify_toy_v2.py`. **Supersedes v1; v1's files are
deleted** (git `240c976`) rather than kept alongside, because two toys drift exactly as two
planning documents do.

v2 implements DECISIONS **E1** — `pack_out_fraction` before the store, `sell_through_fraction`
after it — as a working demonstration ahead of the app change. The comparison is built INTO the
sheet rather than shipped as a second file: set pack-out 0.85 / sell-through 1.00 and it
reproduces v1 (and today's app) exactly. **Same loss, same pounds sold, same money, 17.6%
different cooler.** Pinned as a third configuration in the verifier so the demonstration cannot
quietly stop being true.

Carry forward:
- **The READ ME now COMPUTES the numbers it promises.** Three shipped 0.1 out because I rounded by
  hand while writing prose. Same class as the frozen column and the hard-coded coordinates — a
  figure written beside its source. Verifier section D closes the loop: what the document promises
  must equal what the workbook computes.
- ⚠️ **Delimit repeated blocks by the NEXT header, never by a row count.** A fixed window that is
  too narrow drops rows loudly; too wide it reads the NEXT crop's rows under this crop's names, so
  every comparison is wrong while every lookup succeeds — it presented as twelve real defects.
- ⚠️ **A `str.replace` that matches nothing returns success — assert on it.** Hit twice in one
  session: once patching a helper whose parameter was `ws` not `model`, once posting a `formulas`
  override with the wrong filename case. The playbook names this trap and I still walked into it.
  Every scripted edit in this session now asserts its pattern exists first.

**✅ v3 — channels + demand. DONE 2026-08-30. SUPERSEDED by v4** (files deleted; git `487bddc`).** `toy_models/farm_toy_v3_channels_and_demand.xlsx`,
generated by `build_toy_v3.py`, checked by `verify_toy_v3.py`. **Supersedes v2; v2's files are
deleted.** Two channels with the app's real caps — pulled through its own `build_demand_table` /
`build_annual_caps`, so the weekly-vs-annual split is the app's and not my reading of it — and
**the grower's 2026-08-29 ruling built in: sell-through is per crop x channel**, with a companion
`returns to store` on the same row.

Carry forward:
- **The sheet reproduces the W6 subtlety by construction.** Garlic/Farmers Market fills a small
  share of its annual appetite while sitting at its weekly ceiling in every week it can sell,
  because its W22–W35 window opens before the crop is out of the ground. Both numbers are true.
- ⚠️ **Allocation between channels is a DECISION a calculator cannot make.** With two channels
  competing for one crop's stock, something must choose. The sheet fills the higher-priced channel
  first and SAYS SO on the READ ME. Measured consequence at the defaults: Wholesale's 30,000 lb/wk
  cap drains the garlic in two weeks, so Farmers Market sells 4,000 lb of a 12,000 lb window. That
  gap is the argument for switching the solver on, which is v4.
- ⚠️ **Sell-through has NO physical effect where `returns to store` = 1.0** — `consumed = offered −
  returned = offered × st = sold`, so the loss is purely a delay and fully recovered. That is the
  model being right, and it makes such a cell untestable by a directional nudge. Found by a
  propagation test failing; the fix was to test the axis on a pair where returns < 1.
- **Fewer, stricter checks ran faster.** Five directional propagation nudges were replaced by one
  extra exact configuration (`geometry`) plus dropping four already covered by `stressed`:
  **99s → 57s with strictly stronger coverage**, since an exact row-by-row comparison subsumes a
  "did the number move" assertion. Section B now holds only what section A genuinely cannot see —
  a cap TYPE (a string), shelf life (not simulated), and the three constraint right-hand sides.
  Three mutations verified to die: returns ignored (22 failures), sell-through ignored on the sale
  (37), annual cap not deducting prior sales (5).

**✅ v4 — THE OPTIMIZER. DONE 2026-08-30. SUPERSEDED by v5** (files deleted; git `c35d74b`).** `toy_models/farm_toy_v4_optimizer.xlsx` +
`build_toy_v4.py` + `toy_v4_lp.py` + `verify_toy_v4.py`. **Supersedes v3; v3's files are deleted.**
**The first version that needs LibreOffice** — 317 decision cells and ~780 constraints against
Excel Solver's 200/100 ceiling. Setup recipe is on the Model sheet (16 entries; the 780 rows
collapse into ranges).

Two changes made it solvable, and both were the point: **every `MIN()` is gone** — `offered` is a
decision cell bounded by constraints, exactly as the real model makes pounds-sold a variable
bounded by C6/C6b — and **there is money**, since an optimizer needs an objective (prices per
crop×channel + growing cost per acre, both from the app).

⭐ **THE MEASUREMENT THAT JUSTIFIES THE WHOLE TRACK.** Holding acres at 6 per planting and changing
nothing but who decides the allocation: the fixed fill rule earns **$344,478**, optimal allocation
of the same stock earns **$469,198 (+36%)**. And the optimizer sells **13,200 lb FEWER** while
earning more. The rule served the expensive channel first — the obvious right priority — and still
lost, because the real choice is not only *who* to serve but *whether to serve anyone this week at
all*. A greedy rule cannot decide to wait. **No fixed heuristic recovers this**, which is the
argument for the app having an optimizer, demonstrated rather than asserted.

Carry forward:
- **`toy_v4_lp.py` is the oracle**: the same model as an LP, solved with `scipy.milp` — the HiGHS
  wrapper `farm_v2/solver.py` itself uses. Verifier section **E** writes its solution into the
  sheet's decision cells and requires the sheet's own PROFIT cell to reproduce the optimum
  ($1,094,830.96, exact to the cent), then checks that solution is feasible on the sheet's own
  constraint rows. **That is what proves the spreadsheet and the optimizer are the same problem** —
  without it, CoinMP agreeing with HiGHS would be coincidence rather than evidence.
- The READ ME's promised numbers are all computed from that LP, so the prose cannot promise an
  optimum the model does not produce.
- ⚠️ Profit reads absurdly high ($1.09M) because costs are seed/transplant per acre ONLY — no
  labour, water, packaging, storage or overhead, and no cash constraint. **That is the M1 problem
  reproduced in miniature** and it is stated on the sheet rather than hidden.
- Two propagation predicates were wrong and had to be measured, not reasoned: the cold pool is
  dominated by Kale so a Spinach-only change cannot move it 15% (assert on the crop's own row);
  and Spinach/Wholesale is capped across all 52 weeks, so Weekly and Annual render an identical
  ceiling row and the cap-TYPE test proved nothing.

⚠️ **THE GROWER FOUND THE TWO BIGGEST GAPS ON FIRST READING, AND BOTH WERE MISSING FROM THE
"does not carry" LIST** — the section whose entire job is preventing that surprise. Measured
after the fact:
- **v4 does not choose WHEN to plant.** The app offers 68 successions for these 3 crops (132
  across the real 7) and allocates across all of them; v4 offers 5, hand-picked. Freeing it:
  **$1,094,831 → $2,493,974, +128%** — larger than every missing cost line combined. It plants
  **42 of 68**, staggered, because spreading harvest is what lets a WEEKLY demand cap be served
  continuously. **That is succession planting, and a fixed-calendar toy cannot express the thing
  the practice exists for.**
- **v4 has no plant/don't-plant binary**, so it is an LP where the app is a MILP (y[i], C9, C10).
  It plants 0.48-acre slivers: **10 of the 42 fall below the app's own 2-acre minimum**, 12.7
  acres' worth.
- The two pull in OPPOSITE directions, so neither is quotable alone. **RULE: when listing what a
  simplification omits, list what the model DECIDES, not only what it CHARGES.** Every omission I
  did record was a cost line; both omissions I missed were decision variables.

**✅ v5 — THE FULL CALENDAR (a MILP). DONE 2026-08-30. SUPERSEDED by v6** (files deleted).** `farm_toy_v5_full_calendar.xlsx` +
`build_toy_v5.py` + `toy_v5_lp.py` + `verify_toy_v5.py`. **Supersedes v4; v4's files are deleted.**
All **68** successions on the sheet, plus a binary per planting wired to acres by the app's own
**C9/C10** — so it now decides *when* to plant and *whether* to plant, not just how much.
**448 decision cells** (68 acres + 68 binaries + 312 offered), 19 recipe entries, CoinMP required.

**The two changes measured, and they pull opposite ways:**

| | profit | plantings |
|---|---|---|
| v4, five hand-picked | $1,094,831 | 5 |
| v5 without minimum acreage (LP relaxation) | $2,493,974 | 42 |
| **v5 as it ships (MILP)** | **$2,490,411** | **29** |

Choosing the weeks more than doubles profit; the minimum-acreage rule then costs only **$3,563**
while removing 13 sliver plantings. **A fixed calendar understates, a missing minimum overstates
— which is exactly why the app is a MILP and not an LP.**

Carry forward:
- **29 of 68, staggered** — that is succession planting, and the sheet now shows *why* it pays:
  spreading harvest is what lets a WEEKLY demand cap be served continuously instead of one big
  harvest hitting the ceiling. **A fixed-calendar model cannot express the thing the practice
  exists for.**
- **Structural: one row per succession, not two.** The per-crop harvest is a `SUMPRODUCT` across
  the calendar table rather than a stack of per-succession rows — 136 rows became 68, and the
  verifier got *faster* (57s → 23s) despite 13× the successions.
- ⚠️ **Week columns moved C→E** to make room for the two per-succession decision cells, and
  every test that hard-coded `D` for week 2 broke at once. They now **derive** the offset from a
  week-header strip (`_week_cols`), so the next move costs nothing. **Same lesson as the READ ME
  coordinates: a position written down is a position that will drift.**
- Mutations verified: shipping only 5 successions (the exact v4 defect) is caught by **two**
  independent guards; a decorative min-acreage helper by a third.

**✅ v6 — REAL COSTS AND THE CASH FLOOR. DONE 2026-08-30. SUPERSEDED by v7** (files deleted).** `farm_toy_v6_cash.xlsx` +
`build_toy_v6.py` + `toy_v6_lp.py` + `verify_toy_v6.py`. **Supersedes v5.** Costs are now TIMED —
seed in the planting week, fertiliser and fuel every week in the ground at that phase's rate,
packaging per lb in the week of sale — plus weekly fixed cost and overhead, and the app's C13
cash floor over a cumulative cash row.

| | v5 | v6 |
|---|---|---|
| profit | $2,384,231 | **$1,654,922** |
| net margin | — | **64.7%** |
| growing / packaging / fixed / overhead | seed only | 217,302 / 203,693 / 73,514 / 409,415 |

⚠️ **THE CASH FLOOR BARELY BINDS, AND THE SHEET SAYS SO.** Measured: at $50k opening + $250k
credit the deepest cash position is **+$6,585** against a floor of −$300,000 — headroom of
$306,585. It only bites near $10k + $10k. **Because labour is missing**: wages are ~90% of fixed
cost on the real farm ($855,150/yr against the $73,514 this sheet charges). The mechanism is real
and verified; the farm it checks is not paying anybody yet. **That is v7, and it is what makes
cash mean anything.**

Carry forward:
- **Water is deliberately absent from the cost stack** — the app prices on-farm water at $0
  (backlog W10). Inventing a price in the toy would make it disagree with the thing it checks.
- ⚠️ **The whole cash section shipped compared against NOTHING** until it was caught in the same
  session — the third time (ceiling row, shelf-life row, now the money rows). **A new block of
  rows needs its comparison in the same commit**, not the next one.
- ⚠️ **Rounding the stored phase costs to cents moved profit $2.38** off the LP on a $1.65M
  objective. Store full precision, format for display. Section E is the check that tells "the
  same model" from "nearly the same model", and $2.38 is enough to fail it.
- ⚠️ `_crop_blocks` matched the recipe's "Constraint — cold store" as a crop block — latent since
  v5, harmless while every caller named the three crops, and surfaced the moment a test iterated
  blocks instead of naming them. **Now requires the first token to be a crop.**

**✅ v7 — LABOUR. DONE 2026-08-30.** `farm_toy_v7_labour.xlsx` + `build_toy_v7.py` +
`toy_v7_lp.py` + `verify_toy_v7.py`. **Supersedes v6.** The crew roster is the app's own (1
manager, 2 operators, 12 seasonal field crew wk 10-42, 8 harvest crew wk 14-40, 25% payroll
load), and it reproduces the app's documented figures **exactly** — $4,884/wk winter, $24,484/wk
peak, **$855,150** for the year. That equality is the check that this is the app's crew model and
not a paraphrase.

Labour is **two things at once**, which is the lesson: a **committed cost** (W12 — no per-acre
labour charge anywhere; the marginal crop hour is free) and a **capacity limit** (C2).

| | v6 | v7 |
|---|---:|---:|
| profit | $1,654,922 | **$389,170** |
| revenue | $2,558,846 | **$1,912,071** |
| net margin | 64.7% | **20.4%** |

⭐ **Revenue FALLS, and that is the important half.** Labour does not merely tax the plan, it
RESHAPES it — C2 binds in **22 of 52 weeks**, peak crop hours land exactly on the 908 h/wk
ceiling, and acres the land would happily carry are not worth planting because nobody can pick
them. Net margin finally lands in the same postcode as a real diversified-veg farm.

⭐ **COMMITTED WAGES CREATE A MINIMUM CASH REQUIREMENT NO PLAN CAN AVOID.** $4,884/wk from January
with nothing to sell until spring = **$56,676 out before a dollar comes in**. Measured: below
roughly **$80–100k** of opening cash plus credit there is **NO feasible plan at all** — not a
worse one, none. And above that threshold profit is IDENTICAL at every cash level. **Cash decides
whether you may have a plan; it does not shape the one you get.** Those are different questions
and a single profit figure hides which is being asked.

Carry forward:
- ⚠️ The tight-cash verification case from v6 ($10k+$10k) became INFEASIBLE — correctly. Retuned
  to $50k+$50k, the tightest level that still solves, where the deepest position lands at
  −$48,099 against a −$50,000 floor.
- ⚠️ **The dead-input guard fired a FALSE POSITIVE** on the crew table: those cells are read only
  as RANGES (`$B$27:$B$30`), and the guard matched individual references only, so every row
  between the corners looked dead. Now it checks range containment. **Naming a false defect is as
  damaging as missing a real one — it teaches you to ignore the guard.**
- Mutations verified: charging labour per acre (undoing W12) and flattening crew capacity to a
  constant both die, the second on 6 verifier checks as well as its own guard.

⚠️ **Grower's first read of v7: six notes, three real** (`4f87cf7`). Labour hours were baked into
the C2 formula as literals; the payroll load only LOOKED like it skipped salary (it never did, but
a formula that must be parsed to be believed will be misread); interest was absent. The other
three — overtime, solver-chosen labour, storage access space — are answered in `BACKLOG.md` under
"Grower questions on toy v7", with the storage one filed as **G4**.

⚠️ v7 is **SUPERSEDED by v8** (files deleted; recoverable from git at `5ab7b9f`).

---

**✅ v8 — LABOUR FLEX (hours become a DECISION). DONE 2026-08-30.** `farm_toy_v8_flex.xlsx` +
`build_toy_v8.py` + `toy_v8_lp.py` + `verify_toy_v8.py`. **Supersedes v7.** Two new green decision
rows — OVERTIME hours and HIRED hours, per week — each with its own rate row, and C2 now measures
crop hours against **Hours available** (crew + whatever the solver chose to buy) instead of the
standing crew.

| | v7 | v8 |
|---|---:|---:|
| profit | $388,786 | **$514,774** |
| revenue | $1,912,071 | **$2,390,515** |
| bought hours | — | **6,964 hired, 0 overtime** ($174,106) |

⭐ **THE SOLVER BUYS 6,964 HOURS AND ZERO OVERTIME — AND THAT IS A PRICED CHOICE, NOT A DEFAULT.**
Overtime costs **$37.84/hr** here (the crew's hourly blend × 1.25 payroll load × 1.5 multiplier)
against **$25.00/hr** hired, so hire wins everywhere. Raise the hired wage from $20 to $40/hr and
the plan **flips entirely to overtime**. That is W15 demonstrated rather than asserted: collapsing
the two to a single rate would make "hire is cheaper" a property of the model instead of a
consequence of the prices, and it is false above roughly $30/hr.

⭐ **The +$125,988 is mostly REVENUE, not saved cost** — $1.91M → $2.39M. v7's C2 ceiling was
leaving acres unplanted because nobody could pick them; being able to buy hours turns that
foregone revenue back on, and the plan pays $174k to unlock $478k of it.

Carry forward:
- **W12b is the guard that matters here: bought hours cost their FULL rate**, not the premium
  above base pay. The committed wage bill pays the crew's *stated* hours; these are hours beyond
  it, so charging only the increment leaves the base wage charged nowhere. Mutation-tested — the
  premium-only form dies.
- ⚠️ **A GUARD I WROTE FOR W15 SHIPPED INERT, AND ONLY MUTATION FOUND IT.** It asserted the two
  rate formulas differed *as text*. Aliasing the hired rate to `=AH409` — the overtime-rate cell —
  is textually different and numerically identical, i.e. exactly the defect, and it sailed
  through. Rewritten to parse each formula into the set of cells it READS and assert the hired
  rate reads the hired wage, does not read the overtime multiplier, and does not point at the
  overtime row. **Six mutations, six caught, after the rewrite.**
- ⚠️ **`_refs()` now parses formulas instead of grepping them.** Substring matching on cell
  references is how guards die twice over: `B32` matches inside `B320`, and `AH131` fails to match
  `AH$131` — the second one broke a brand-new check the moment it ran. Parse, do not grep.
- ⚠️ **THE DEAD-INPUT GUARD CALLED A LIVE CELL DEAD.** "Max overtime hrs/week" is read *only by
  the Solver*, as a constraint bound — no formula on the sheet touches it. A formulas-only scan
  therefore condemns it. The guard now counts the solver-recipe text as a reader. Same family as
  v7's crew-table false positive: **the guard's model of "used" was narrower than the sheet's.**
- ⚠️ **Three tests broke purely because five input rows shifted the layout** — a header scan
  hard-coded `range(1, 40)` and the Succession header moved to row 42. Now scanned to `max_row`.
  Third instance of the recorded rule: *a position written down is a position that will drift.*
- ⚠️ A stale verifier check compared crop hours against **Crew capacity**; with flex on, crop
  hours *should* exceed the standing crew, and it flagged four weeks as violations. Repointed at
  Hours available. **A check written for the previous version is a check written against the
  wrong model.**
- The verifier now proves the flex layer is **not inert**: 23 weeks exceed the standing crew, and
  C2 still binds in 32 of 52. A slack capacity row would prove nothing.

**Next: the toy now has every mechanism the app has except water (priced at $0 — W10), and the
wizard.** Interest arrived in v7/v8 (sheet $333.84 = LP $333.84, peak borrowing $46,461).

Original ordering note: ~~demand caps~~ (v3), ~~cash~~ (v6), ~~labour~~ (v7), ~~labour flex~~ (v8).

Original ordering note: ~~demand caps~~ (done
in v3), then cash (C13, the one with no Excel ancestor at all), then labour (committed vs bought),
then **v4 — switch the solver on**, which is what makes allocation a result rather than my rule.

Original ordering note: demand caps (weekly
vs annual — the Garlic/Farmers-Market 50%-vs-100% split), then cash (C13, the one with no Excel
ancestor at all), then labour (committed vs bought). Each is a block of rows on the SAME spine
with a toggle, not a new workbook — four workbooks would drift from each other and from the app,
which is the failure this project already has a rule about.

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

**2.6 · Re-pin.** ➡️ **RULED 2026-10-21: Option B in DOLLARS, moved to 3.5 (lands with Batch 3's re-pin) — DECISIONS GROUP H.** Was: ⛔ **HELD 2026-10-19 — the measurement contradicts this step's premise: decomposing overhead moves margin UP (25.4% → 33–37%), because the explicit lines total ~$62–82k against a $386k overhead. Decision with the grower: `DECISIONS.md` GROUP H.** 2.1 R8, 2.2 R7, 2.3 R1 and 2.4 W10 are DONE as mechanisms ($0 defaults); 2.5 W17 SKIPPED (conflicts with GROUP F L8). Original: One commit. Expect margin to fall from 20.1% toward the 5–15% band; assert
direction; document every line's delta. If it falls BELOW ~5%, stop and re-examine defaults
before shipping (over-charging is the mirror error; four fixes moved margin wrong by over- or
mis-charging).

---

## Batch L — The labour batch (grower ruling 2026-10-21; runs NEXT, before Batch FX)

**Spec: `SPEC_batchL.md` — ✅ RULED 2026-10-21: all six questions as recommended (overtime enters
the MAIN plan → golden re-pin in L.2), and build order L.1 → L.5 → L.2 → L.3 → L.4.**

One batch for everything that touches the roster, because it all rewrites the same rows and the
same money path (R10 found GROUP F was never scheduled). Spec first, then build; guardrails 2–5,
10, 12; a **labour-flex-ON golden fixture in the same commit as L.2** (GROUP F sequencing note —
the shipped golden farm has flex OFF, so without it none of this has a baseline that can fail).

**L.1 · GROUP F3** — the labour section as named rows (publish the per-role weekly arrays).
**L.2 · GROUP F2 + F4** — overtime per role, priced at that role's wage × load × multiplier, and
the overtime CAP derived from the roster. Fixes **L2** (flat 200 h/wk cap > the whole crew's hours
in 15 of 52 weeks). Ruled 2026-10-21: the allowance is set **per role**, as a cap on TOTAL weekly
hours relative to regular hours — default **125% = 40 regular + 10 overtime (a 50-hour week)** for
hourly/seasonal, 100% (none) for salaried. ⚠️ Label it so it cannot be read as 125% ON TOP of
regular (the grower's first reading: that would be 90 h/wk). Overtime pay multiplier default
**1.0×** (federal FLSA exempts farm work), tooltip: set 1.5× where state law requires ag overtime.
**L.3 · GROUP F1 (grower's design)** — `Hire more?` / `Max more` / `EXTRA HIRED` on each roster row.
**L.4 · GROUP I2/I2a** — task tags (field / post-harvest / selling) per row, default all on; Field %
→ **Admin %** (inverse) with the load-time migration.
**L.5 · GROUP I2b** — payroll load split (all-pay FICA 7.65%; straight-time rate sourced), with the
load-time migration of the single 25%.
NOT here: piece rate (GROUP F5) → Batch 6 (ruled 2026-10-21). Post-harvest hours (3.6) build ON
L.4's tags and stay in Batch 3 with their research (3.7).

---

## Batch W — Water mode (scheduled 2026-10-23; right AFTER Batch L, before Batch FX)

BACKLOG **BC4** as ruled 2026-10-23 (grower: option C; absorbs `/code-review max` #15). One
up-front question in the Water section: **Irrigated** (tick ≥1 source, as today) / **Rain-fed
only** / **Don't limit by water**. Nothing ticked AND no mode chosen stays refused.

Why: rain offsets 65% of crop water need whatever is ticked, so "no source" means "rain only" —
the golden farm solves identically with every source off, and today's refusal makes a rain-fed
farm enter a fictitious well. Small, but it goes before Batch 3, whose re-pin runs many solves
where water settings matter.

Steps: (1) one-page spec for the grower — the two traps: "Don't limit by water" must drop the
water limit AND its cost without reopening D11's "nothing ticked" hole, and "Rain-fed only" must
SAY the plan assumes rain alone; (2) build on its own branch; (3) `/simplify` + a `/code-review`
(not max — small diff); (4) into the next combined browser check.

---

## Batch FX — The fixed layer (scheduled 2026-10-19; after Batch 2, before Batch 3)

**WHY.** The grower's first page of January (`SPEC_product.md` prompt 1): *"what do you know you
need to plant? This absorbs the big blocks and then the rest gets filled in with extras."* The app
has no first page — it optimises every acre from zero. This batch is the **"absorb the big blocks
first"** half: things the grower has already decided, owes, or physically has, which CONSTRAIN
the plan before the optimiser fills what is left for profit. Ranked #1 missing primitive in July,
then parked as P1 with no batch. Rulings and evidence: `DECISIONS.md` **GROUP G**.

Placed before Batch 3 because it is what a grower meets first; placed after Batch 2 because a
with/without delta ("this contract costs you $X") is only honest once the cost model is complete.

**FX.0 · Prototype in the toy first (v12).** Same pattern as labour: prove the shapes against an
independent oracle on a hand-checkable sheet before touching the guarded money path.
✅ BUILT 2026-10-24 — `toy_models/farm_toy_v12_fixed_layer.xlsx`; measurements and the app design
are in **`SPEC_batchFX.md`** (§2 findings, §5 six questions awaiting the grower). Settled there:
must-plant ships in BOTH forms (30 ac kale: annual $0, standing $49,240), and C15 folds into the
standing form.

**FX.1 · Must-plant floors — UNCONDITIONAL.** "I need N acres of X." `min_acreage_if_planted` is
NOT this: it is conditional on the plant binary, so the solver escapes it by dropping the crop
(measured: a 14-ac garlic floor → 0 ac, −$344k). A must-plant floor forces the crop in. ⚠️ Open
design point, decide in the toy: floor on STANDING acreage (C15's lesson — a floor on the annual
sum of plantings was satisfied with eighteen 1-acre slivers and reserved nothing) vs. on total
acres planted across the year (legitimate for a multi-succession crop like lettuce). Probably
both, named differently.

**FX.2 · Carry-ins — overwintering AND perennials (grower ruling: "committed" covers both).**
- *Overwintering* exists: `overwinters` flag + C15 committed acres. Fold it under the same
  "already in the ground" heading in the UI rather than leaving it a flag on a crop card.
- *Perennials* (asparagus, cane fruit, bushes) are **new**: `calendar.py:114` rejects any cycle
  > 52 weeks. Model as committed ground standing all 52 weeks — no plant decision, a harvest
  window, annual maintenance costs, and establishment cost on the OWN→depreciate basis
  (the locked cost-accounting basis), never charged as this year's seed. Its land is unavailable to
  everything else.

**FX.3 · Contract delivery floors (P1).** `v[c,ch,w] ≥ floor` per crop × channel × week, with a
**shortfall slack priced at a penalty** (grower ruling — an unmeetable contract must surface as
a reported shortfall, never as "no feasible plan"). Ship with the with/without delta so the tool
PRICES the obligation. ⚠️ Interacts with GROUP E (shelf life): today Tomatoes/Basil have L=1, so a
weekly floor in a non-harvest week can only be met by shortfall. The slack makes FX safe to build
before E lands; re-check the shortfall report after E.

**FX.4 · Zones (amends the plot non-goal — grower sign-off 2026-10-19).** No geometry, no map:
named land pools ("2 ac high tunnel, 6 ac part sun, 10 ac open field") and a crop × zone
eligibility table. Acres split by zone; C1 land becomes per zone per week. Variable count grows
by ×zones — fine at 3–5.
✅ BUILT 2026-10-25 (solver/validate/adapter; UI with the FX UI step) — see `SPEC_batchFX.md` §3
"FX.4 as built". Golden unchanged to the cent; a 2-ac tunnel fixture binds (tomatoes 5 → 2 ac,
−$42,593); 11/11 targeted mutants caught.

**FX.5 · Zone-specific growing behaviour = a separate crop name (grower ruling).** "Tomatoes" vs
"High-tunnel Tomatoes", each with its own windows/yield/costs, eligible only in its zone — no
per-zone yield modifiers. ⚠️ **TRAP: demand caps are keyed by crop name**, so two variants selling
to the same market would each get the full cap and double it. Variants need a shared demand
identity (`sells_as: "Tomatoes"`); same bug family as W1's duplicate-name defect. Guard it with a
test that two variants of one crop cannot together exceed one cap.

**FX.6 · Templates for common variants** (high-tunnel tomatoes/peppers/cucumbers/greens,
part-shade greens, perennials such as asparagus) — sourced values only, under Batch 3's data
discipline. **And the wizard instruction** (lands in Batch 7, recorded here so it is not lost):
when a grower declares a zone that changes growing behaviour and a crop in it has no variant,
PROMPT for one.

**FX.7 · Re-pin / guards.** ⚠️ The golden farm uses none of this, so everything can ship with the
baseline unchanged — the L4 / "defaulting a feature off leaves it unguarded" trap. A golden
fixture with a zone, a perennial, a must-plant and a contract floor goes in **the same commit** as
the feature.

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
protocol as 2.6 — and that one re-pin INCLUDES 3.5 and 3.6, so the headline moves once.

**3.5 · Overhead in dollars (from 2.6; grower ruling 2026-10-21, DECISIONS GROUP H).** Replace
`overhead_pct_of_revenue` with an "everything else" **$/yr** input (sourced default ~4% of a
typical farm's sales expressed in dollars, or $/acre + $/farm); prefill W10 utilities, R7
insurance and carrying cost from the GROUP H research (utilities ~3–4%, insurance ~1.7% of
sales → dollars); show every rate-based line's $ result. Migration: saved plans carrying a %
convert to dollars on load and say so (E5 load report). ⚠️ This also removes overhead from the
per-pound objective (it was a 16% sales tax on every lb) — expect the plan, not just the total, to
move; measure and record both. Prerequisites: 3.6 and the M2 revenue sweep.

**3.6 · R9 — post-harvest labour (wash/grade/pack, market staffing, delivery).** Grower-raised
2026-10-21; design RULED in DECISIONS GROUP I (I1 throughput input + the "put 0 if your harvest
hours already include it" tooltip; I2 labour task tags field/post-harvest/selling on each roster
row, default all on; I3 channel staffing hours + selling cost relabelled as buyer fees). Spec
first (I2 touches the labour money path and GROUP F's roster), then build. Must land BEFORE 3.5 —
it is the largest known-missing cost the 16% may have been silently absorbing.

**3.7 · Research — post-harvest throughput and selling staffing defaults (GROUP I4).** Sourced
per-crop wash/pack rates (lb per person-hour) and typical market/delivery staffing, to the GROUP H
research standard (cite, state the basis, flag what could not be verified). Feeds 3.6's defaults.

**3.8 · GROUP E — loss, storage and shelf life (E3 → E1 → E2; RULED 2026-10-21).** E3: a per-crop
storage-loss %/week form field wired to the existing `storage_loss_frac_per_week` (sourced
defaults). E1: sell-through + returns-to-store per crop × channel, market loss occupying storage,
`market_loss_lbs` reported; defaults 100% until sourced; NO pack-out field (yield = marketable,
relabel the yield box). E2: per-crop `shelf_life_weeks` with sourced defaults and the +1 week
correction. Shares Batch 3's single re-pin. Naming of sell-through still open (GROUP E ruling 5).
Also ships here: the interim headline disclaimer (GROUP I5) if it has not already gone out.

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
**4.4 · C9 — the headline carries the range** (grower ruled the goal 2026-10-21, GROUP I5: the
main solve stays as is; the range fills in afterwards from 4.1's frozen-plan draws, with an
instant analytic band as the fallback if those are too slow; interim disclaimer ships earlier) ("$X projected — typical range $Y–$Z" from frozen
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

Tier 7 (until a second user is imminent — grower confirms not deployed); plot-level MAPPING (zones with eligibility are IN scope — Batch FX),
weather prediction, price/demand research (locked non-goals, unchallenged); P1/P2/P5–P12 beyond
the Batch-5 slice (bet ① sequencing, grower-gated); E6 (rides the wizard); the M1 number itself —
**never chase it directly; it is the scoreboard, not the work** (grower posture, evidence in
DECISIONS).
