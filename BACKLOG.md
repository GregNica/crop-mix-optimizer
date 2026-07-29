# BACKLOG — one list, everything open

**Why this exists.** The open work was spread across the July-20 audit
(`~/.claude/plans/eager-petting-hare.md`), `SPEC_agronomy.md`, `SPEC_product.md`, `SPEC_v3.md`,
`STRATEGY.md` and memory. That is how Phase B came to look closed while five of its eight items
were still live. One list, one place, checked against the code.

**Built 2026-07-29.** Status marks mean:

| Mark | Meaning |
|---|---|
| ✅ | verified **done** against the code on 2026-07-29 |
| ⛔ | verified **open** against the code on 2026-07-29 (file:line given) |
| ❓ | from a source document, **not re-verified** — confirm before scheduling |

**Class** uses `STRATEGY.md`'s anti-lurch tiers: `defect` (code contradicts a specified
semantic — fix + guard + re-pin, no consultation), `value` (a number is wrong), `phase`
(ordering inside a track), `track` (changes a plan's scope), `strategy` (needs the grower's
sign-off in its own session).

**D1–D10** are the grower's ranked deliverables (2026-07-29):

| | Deliverable | |
|---|---|---|
| **D1** | Crop calendar | ✅ exists |
| **D2** | Seeding calendar for transplants (if grown onsite) | blocked |
| **D3** | Yield projection calendar | close |
| **D4** | Committed sales calendar by channel | data exists, **wrong number shipping** |
| **D5** | Seed ordering list | needs a new input |
| **D6** | Risk mapping tool | partial |
| **D7** | P&L that maps uncertainty | partial |
| **D8** | Explanation of the crop plan | data exists |
| **D9** | Labor calendar (capacity used / needed) | data exists |
| **D10** | Optimization recommendations (crops, channels, constraints, fixed costs, benchmark deviation) | mostly data exists |

---

## Tier 0 — Silent failures: the model does the wrong thing and says nothing

Every item here shares one shape, and it is the shape that has cost this project the most.
All are `defect` class — they need no consultation.

| ID | Item | Evidence | Class | Unblocks |
|---|---|---|---|---|
| ✅ **S1** | ~~`validate.py` is never called by the app~~ — **FIXED 2026-07-29, and MOVED into `solve_farm_v2` (Step 0) on 2026-07-29 after review.** It first went into the Python adapter, which looked like the convergence point only while the app was browser-only — the server path would have bypassed it, and it was reachable by pytest only by string-slicing a JS template literal. It now sits where every caller converges: Optimize, What-If, sensitivity, Monte Carlo, the tests, and the server. Errors return as `status: invalid_input` with reasons; warnings ride back on every solve. The guard fails OPEN but LOUD — a crash costs the check, not the plan, and says so | `farm_v2/solver.py` Step 0 | defect | D8, D10 |
| ✅ **S2** | ~~No explanation for a zero-acre crop~~ — **FIXED 2026-07-29.** `unplanted_crops` names a cause per absent crop: `no_plantable_window` (calendar, and it names `overwinters` as the fix), `no_demand`, `all_channels_excluded` (margin hurdle), or `outcompeted`. **`outcompeted` is deliberately the conservative default** — an LP declines a bundle at these prices, it does not reject a crop for one reason, so naming a binding constraint as THE cause would be a story. It adds which resource was tightest only when that is above 95%. Rendered in a banner; each branch pinned separately, and mutation-tested against collapsing to one generic answer | `farm_v2/solver.py` | defect | **D8**, D10 |
| ✅ **S3** | ~~B4 — annual demand cap enforced as `annual/52` every week~~ — **FIXED 2026-07-29.** An annual cap is now a yearly TOTAL with its own constraint row (C6b), and the weekly rows are skipped for those channels. Verified the row BINDS and is never exceeded: on the 29-crop fixture Spinach/Wholesale sells exactly 1,200,000 lb against its 1,200,000 lb cap, zero violations. Golden farm unchanged (its annual caps were not binding); fixture revenue +26%. Mutation-tested both directions. Bonus: the suite got FASTER (68s → 50s) — each annual channel now costs 1 row instead of 52 | `farm_v2/utils/demand.py`, `solver.py` C6b | defect | **D4**, D3 |
| ✅ **S4** | ~~B5 — season windows must contain the whole crop cycle~~ — **FIXED 2026-07-29 (`9cc2b7c`).** Windows are PLANTING windows: any start week inside the window is valid and the cycle runs from there. Winter Squash and Melon generate successions again instead of silently vanishing from every plan | `farm_v2/utils/calendar.py` | defect | **D1**, D3 |
| ✅ **S5** | ~~B6 — no year-wrapping seasons~~ — **FIXED 2026-07-29 (`9cc2b7c`), opt-in.** A cycle may run past week 52 only when the crop sets `overwinters`; universal wrap was measured first at +63% profit and rejected, because every window was authored under the old meaning and reading them as planting windows let frost-tender crops be planted in autumn. Garlic is the one crop that sets it, with a grower-sourced late-November window | `farm_v2/utils/calendar.py` | defect | **D1**, D2, D3 |
| ✅ **S6** | ~~B7 — water storage is billed but banks nothing~~ — **FIXED 2026-07-29.** A `wstore[w]` level now carries between weeks: `wstore[w] ≤ wstore[w-1] + inflow + city − use`, bounded by `water_storage_capacity` and anchored empty at week 0 (same discipline as the inventory balance). The inequality is what allows spill, so no spill variable is needed. **It subsumes the old row rather than sitting beside it** — at capacity 0 every level pins to 0 and it collapses to exactly the old C3. Reported water cap now includes the tank's opening level, so what is published still equals what is enforced. Mutation-tested | `farm_v2/solver.py` C3 | defect | D10 |
| ✅ **S7** | ~~B8 — overlapping demand ranges overwrite rather than accumulate~~ — **FIXED 2026-07-29** (`+=`). A W1–W20 contract plus a W10–W15 top-up now sums across the overlap and is order-independent. Two pytest cases, mutation-verified. Golden farm bit-identical — the demo has no overlapping ranges | `farm_v2/utils/demand.py` | defect | **D4** |
| ✅ **S8** | ~~What-If and Monte Carlo bypass `validateParams` entirely~~ — **FIXED 2026-07-29 by S1's placement.** Validation lives in the adapter where all five solver entry points converge, so the sweep, the sensitivity runs and Monte Carlo are all covered without touching any of them | `public/index.html` adapter | defect | D6, D10 |
| ✅ **S9** | ~~Four visible, editable rate inputs are dead~~ — **RESOLVED** by the locked cost-accounting basis. All four have zero form fields now; they survive only as solver params fed by depreciation | 0 hits for `id="rate_*"` | — | — |
| ✅ **S10** | ~~Renaming a sales channel wipes every crop's price, packaging and demand~~ — **FIXED 2026-07-29.** `prev` now carries a positional shadow; a miss falls back to position **only when the channel count is unchanged** (channels cannot be reordered, so a miss with an equal count is a rename). An add/remove gets no fallback, so a new channel cannot inherit a neighbour's numbers. Pinned in `canon_flows.cjs`, mutation-verified in both directions | `index.html` `updateCropChannels` | defect | D4 |
| ✅ **S11** | ~~`deleteCrop()` renumbers card ids but not the template `<select>`~~ — **CONFIRMED AND FIXED 2026-07-29.** After deleting crop 1, Garlic's card still called `loadCropTemplate(5)` and Basil's `loadCropTemplate(6)`, so choosing a template overwrote a different crop. `renderCrop` bakes exactly two indices and both are now renumbered; the test asserts no card holds a stale index and that the survivors are the right crops in order | `index.html` `deleteCrop` | defect | — |
| ✅ **S12** | **Two of three were already fixed; the third is done.** `min_guaranteed_hours` **is** used (`labor.py:151`, `guaranteed_hrs = count × min(min_hrs, hrs)`). `operating_weeks` is now explicitly deprecated, has no form field, and scales nothing — the cost-accounting basis settled it (ownership does not pause off-season). `y[i]` **was** unbounded: `integrality` alone makes it an integer, and with `min_acreage_if_planted = 0` (a value the form accepts) C10 collapses to `0 ≤ x` and y goes free. Now `ub = 1`. ⚠️ **Honest note: no test catches this mutation** — HiGHS returns a binary y on every fixture anyway, so this is semantic hygiene, not a behaviour change. The two tests added pin the contracts that *are* observable | `farm_v2/solver.py` Step 7 | defect | D9 |
| ✅ **S13** | ~~`y` is not a reliable planted flag at `min_acreage_if_planted = 0`~~ — **FIXED 2026-07-29** with a `PLANT_FLAG_TIE_BREAK` of 1e-6 in the objective, mirroring the existing inventory tie-break. Minimum-y is now strictly optimal, so y tracks x in every case. Bounded by a test: planting all ~155 successions costs under a fifth of a cent. Done ahead of S2, which wants a trustworthy "was this considered and rejected" signal | `farm_v2/solver.py` | defect | D8 |

---

## Tier 1 — Wrong numbers currently shipping

| ID | Item | Evidence | Class | Unblocks |
|---|---|---|---|---|
| ⛔ **W1** | **Per-channel weekly sales are reconstructed in the client, not read from the solver.** `v` is now returned by Python and used by **nothing**. The client still splits gross harvest proportional to `demand × price`, ignoring sell-through (~18% overstatement), spread, caps and hurdle drops. This contaminates the pies, the sales CSV and the exported P&L's channel revenue lines, which **cannot reconcile to the headline revenue on the same page**. This is a correctness defect, not a missing report — and it is exactly **D4** | `v` in the result dict; reconstruction at `index.html:8761`, pinned by test T59 | defect | **D4**, D7 |
| ❓ **W2** | Monte Carlo **re-optimizes the crop mix on every draw** — perfect foresight, presented as a "1-in-10 bad year planning floor". Fix: freeze `x`/`y`, re-evaluate under each draw, let only sales allocation re-optimize. The gap between modes is itself the value of perfect foresight | audit Part 3 | defect | **D6**, D7 |
| ❓ **W3** | "Crop plan stability" labels crops **Fragile** based on selection frequency under re-optimization — an artifact of W2, not a risk measure | audit Part 3 | defect | D6 |
| ⛔ **W4** | P&L cost-breakdown rows permanently blank — the renderer asks for `res.cost_seed` / `cost_fert` / … which the solver never returns. `vc_split` (labor, water, fert, fuel, seed) exists internally and is not exported | audit 1.3; `vc_split` in `solver.py` | defect | **D7**, D10 |
| ❓ **W5** | `crop_diversity_max` is an acre-**weeks** share, not a land share. "0.60" reads as "at most 60% of my farm in garlic" but permits 100% of the farm in garlic for 31 weeks. Relabel with a worked example, or rescale | audit Part 3 | defect | D8 |

---

## Tier 2 — Model truth (bet ②, `SPEC_agronomy.md`)

| ID | Item | Class | Unblocks |
|---|---|---|---|
| ⛔ **M1** | **The 39% net-margin problem.** Real diversified-veg is 5–15%. Every honest fix so far has pushed it *up*. Unresolved, and it becomes trust-critical under the chatbot direction — the assistant's whole value is being believed | value | all |
| ⛔ **M2** | Agronomy audit **Phase C** — field-by-field in crop-impact order, garlic first (its calendar is the S5 gap) | value | D1, D3 |
| ⛔ **M3** | Agronomy audit **Phase D** — adversarial refutation + the grower's intuition pass + re-pin | value | all |
| ⛔ **M4** | **`planting_type` is read by nothing in `farm_v2`.** Carried on every template and in the form, dropped before the math | track | **D2** |
| ⛔ **M5** | **Labour establishment/mechanisation axis** — direct-seed vs transplant, bed prep, nursery time, mechanical harvest, contract labour. Tabled `SPEC_product`. Four of five planting-labour values are peer-anchored placeholders until it exists | track | D2, D9 |
| ⛔ **M6** | **Propagation/greenhouse infrastructure cost** — "raise your own" currently reads as almost free. Tabled `SPEC_product` | track | **D2** |
| ⛔ **M7** | **Seed/transplant quantity is not modelled** — only cost per acre. A seed order cannot be produced without a seeding rate or plant density | track | **D5** |
| ⛔ **M8** | Napa Cabbage and Melon `planting_type` are genuinely ambiguous; each is internally consistent as shipped. Money is in `seed_transplant_cost_per_acre` (Napa swings $160 → $1,089/acre), not `labor_plant` (~$20) | value | — |
| ❓ **M9** | Volume basis — `crop_size_m3_per_lb = TOTE_M3 / lbs_per_tote` where `lbs_per_tote` is an ergonomic lift weight, not a density. Two prior audits disagree on the direction of the error | value | D10 |
| ❓ **M10** | Dead templates — Snap/Snow Peas generates one succession; `validate.py` never runs on the app path (S1) so a broken template fails silently | defect | D1 |

---

| ⛔ **S14** | **Already-planted crops are modelled as a free decision.** Raised by the grower 2026-07-29 on seeing the year-wrap land: *"crop planning like this would happen in the winter months after garlic was already planted in November."* The cyclic year makes the annual arithmetic self-consistent, but the optimiser can still choose **zero acres of garlic** — which in reality means abandoning a crop already in the ground and paid for. A pre-committed planting is a **floor with a sunk cost**, not a choice. Overlaps P1 (must-plant floors) and P11 (perennials/carry-overs), and the grower listed it in the original one-pager: *"what perennials/carry-overs from the year before are there"* is one of the first things they establish when planning | `farm_v2/utils/calendar.py` + no input exists | track | D1, D2, D7 |

---

| ⚠️ **S15** | **BROWSER-MEASURED 2026-07-29: the default farm solves in ~5 seconds**, against 4.5s native — so Pyodide is roughly at parity here, not the several-× penalty assumed, and there is real headroom against the 75s wall. **No longer urgent.** The analysis stands for larger farms: only `x[i]`/`y[i]` scale with succession count, and branch-and-bound is exponential in binaries, so a farm with year-long planting windows (306 successions) already hits the wall natively. The `succession_spacing_weeks` knob remains the identified mitigation, still unbuilt — 5s does not justify coarsening the planting grid. What 5s DID justify was fixing the progress bar (done) | `farm_v2/utils/calendar.py` | phase | all |

---

| ⚠️ **S16** | **DOWNGRADED 2026-07-29 by the grower: the specific instance is plausible.** They grew in zone 6 where late October was the latest pepper harvest; the reference zone is 7, where early November "could fly". So `Hot Peppers W25` harvesting to week 45 is not a defect and the +3.8% revenue stands. **The structural point is unchanged and stays open:** every shipped window's END date was authored to mean "the cycle finishes by then" and now bounds only the PLANTING, and the model has no temperature in it — so nothing would catch a window that *is* wrong. This is a review item for agronomy Phase C (re-author the 29 windows as true planting windows), not a bug to fix now | `farm_v2/utils/calendar.py` | value | D1, D3 |

---

## Tier 2b — Practice coverage (from the 2026-07-29 research, evidence in `STRATEGY.md`)

The external survey plus an own-research pass that filled its gaps. Two new cost categories, one
confirmed mechanism, and three proposed subtractions with verdicts.

| ID | Item | Evidence | Class | Unblocks |
|---|---|---|---|---|
| ⛔ **R1** | **No crop-protection cost category.** Herbicide/insecticide/fungicide have no field; fertiliser and fuel do. ⚠️ The ">90% of farms" claim is **unsupported for any single class** — NASS 2022 (22 crops, 17 states) gives max 82% of planted acres for any one class. **The finding is the variance:** which class dominates flips by crop (squash fungicide-led 69%, sweet corn herbicide-led 82%). So this is a **per-crop cost like fertiliser**, not a farm-wide rate or an overhead line | NASS 2022 Ag Chemical Use — Vegetables | track | D7, D10 |
| ⛔ **R2** | **No insurance of any kind** — crop, liability, equipment. Historically low on small farms but rising; the USDA Micro Farm Program now covers diversified revenue to $350k. Farm-level fixed cost; interacts with the deterministic-yield gap | external survey, *medium* confidence | track | D6, D7 |
| ✅ **R3** | **The (crop × operation × cost basis) hypothesis is CONFIRMED** by an independent pass: contract labour and short-term equipment rental both came back tagged Crop × Operation, unprompted. **Grounds for building ONE mechanism instead of five features** — M4, M5, M6, P8 and P13 collapse into it | external survey | track | D2, D9 |
| ⛔ **R4** | **Contract/custom work priced per unit** (per acre, carton, ton) is unexpressible — labour is hours × wage only. **195,000 US farms report contract-labour expense against 437,000 reporting hired labour**, so ~45% of farms that employ anyone also buy labour by contract. Not a specialty curiosity | USDA ERS Farm Labor Expenses 1997-2022 | track | D9 |
| ⛔ **R5** | **U-pick / customer-harvest channels** zero out `labor_harv` for the volume sold that way. Unexpressible: harvest labour is a crop attribute charged on all volume regardless of destination. This is the per-channel cost-to-serve primitive, not a new practice flag | external survey | track | D4 |
| ⛔ **R6** | **Rent vs own has a real constituency: 28% of US farms operate partly or entirely on rented land, and 39% of all acres are leased.** Strengthens P13, which was parked as a design question | AFBF/ERS on the 2022 Census | track | D7, D10 |

### Proposed subtractions — verdicts, so they are not silently adopted later

| Proposal | Verdict |
|---|---|
| **Delete `planting_type`** ("changes no arithmetic") | **REJECTED.** The reasoning is right and the conclusion is backwards — seed-vs-transplant is the input D2 (seeding calendar, the grower's #2 deliverable) is built on. It came from a brief that never mentioned D1-D10; our omission, not the researcher's error |
| **Add `marketable_yield_pct`** (claims the model assumes 100% marketable yield) | **CHALLENGED — probably a duplicate.** `sell_through_fraction` (farm) and `sell_through_pct` (per crop) already mean "share of harvest that converts to cash: shrink, grade-out, spoilage", and both were in the brief. There may be a real distinction between field-level cull and post-harvest loss; a second knob for the same quantity is how two numbers come to disagree |
| **Leave seed quantities out; keep cost only** | **REFUTED BY THE COMPETITIVE SCAN.** The argument was good — irregular catalogue package sizes, non-linear pricing — but **VeggieCropper ships seed and bed-spacing calculation as a core feature.** A direct competitor does it and the grower ranked it D5. It also misreads `crop_size_m3_per_lb` (produce storage volume per lb) as a seed field |

**Null results worth recording:** the survey found **no practices we had not already listed**,
despite the brief naming that as the highest-value possible finding. It returned **nothing on
payment terms, CSA prepayment, or land tenure** — the last of which the Census reports directly
and own-research filled in (R6).

---

## Tier 3 — Product shape (bet ①, `SPEC_product.md`)

Ranked as in the spec. All `track` or `strategy` class — none proceed without a decision.

| ID | Item | Unblocks |
|---|---|---|
| **P1** | Obligations / must-plant floors — build as floors on weekly deliveries `v[c,ch,w]`, **not** acreage floors (a floor ≥14 ac deletes garlic entirely, −$344k). Ship with a with/without delta so the tool *prices* the obligation | D4 |
| **P2** | Allocation by **stake**, not margin — the farmer's stated rule; the model allocates every scarce pound by price | D4, D10 |
| **P3** | **Payment terms per channel** — wholesale net-30, market immediate, CSA prepaid. C13's cash floor and the interest line are fed fiction today | D7 |
| **P4** | **CSA as a financing instrument** — the clearest case where the app gives actively bad advice | D7 |
| **P5** | Weekly variety requirement — what diversity means operationally; the acreage cap is a poor proxy | D8 |
| **P6** | Channel formality spectrum; **P7** sustained-vs-one-off channel viability; **P8** buy-vs-make (transplants, resale, infrastructure, **land rent**); **P9** channel growth advice; **P10** past-year sales as the demand basis; **P11** perennials/carry-overs (needs S5); **P12** infrastructure-driven crop requirements | D4, D8, D10 |
| ⛔ **P13** | **Rent vs buy, per asset.** Depreciation ✅ landed (6 assets: harvest, ambient, equipment, irrigation, water, fuel — each with a capital cost and a life). The **rent/buy half never started** — parked as "design decisions, do WITH user". Today every asset is owned; there is one weekly Property Mortgage/Rent field for land and nothing else. A farm that leases its cooler or rents equipment cannot say so | D7, D10 |

---

## Tier 4 — The deliverable (audit Phase C)

This is where D1–D10 actually get produced. Note W1 sits underneath D4.

| ID | Item | Unblocks |
|---|---|---|
| **C1** | Season plan table — crop / acres / planting weeks / harvest window / lbs / $ by channel, **printable**. Today the plan is a 52-column Gantt of acreages | D1 |
| **C2** | Contract commitment schedule — weeks × channels of committable lbs from the real `v`, with a confidence dial ("commit at 80% of plan") | **D4** |
| **C3** | Break-even price per crop-channel — what you quote when a buyer pushes, and when to walk | D10 |
| **C4** | Marginal value per constraint (shadow prices from the LP relaxation) | D10 |
| **C5** | **Downside** What-If — today it only loosens (+10/+20/+40%, custom validated 1–200 as an increase). "What if my wholesale buyer halves their order" is literally unaskable. Make it bidirectional with named scenarios | D6 |
| **C6** | Yield projection series by crop by week — derivable from `x` + phase table; not currently returned | **D3** |
| **C7** | Labor calendar view — `capacity_series.labor {used, cap}`, `hired_hours_weekly`, `overtime_hours_weekly` all exist; no view | **D9** |
| **C8** | Benchmark-deviation report — `CROP_PROVENANCE` exists and **renders nowhere**. This is a report, not a badge panel | **D10** |
| **C9** | Risk into the main flow — headline reads "$172k projected — typical range $118k–$214k"; crops Assumptions box (deterministic yields and no crop failure are disclosed nowhere) | D6, D7 |

---

## Tier 5 — Structural (audit Phase E)

| ID | Item | Status |
|---|---|---|
| **E1** | Tests out of `index.html` — a 3,425-line console-assert function (25% of the file) ships to every user, never runs automatically, prints "All what-if tests passed" unconditionally, **crashes at T143 with a ReferenceError**, leaves 49 T-blocks dead, and corrupts live app state on crash | ⛔ open |
| **E2** | `run_from_js` out of the template literal into `farm_v2/adapter.py` — makes ~340 lines of money-affecting Python pytest-testable | ⛔ open |
| **E3** | Solver blob out of the JS literal | partial — sync script + `test_blob_sync` now enforce it ✅ |
| **E4** | Unify the margin kernel | ✅ done (solver owns money; hurdle runs in Python) |
| ⛔ **E5** | **Declarative, versioned field registry.** Promoted by the interface direction from hygiene to *substrate*: there are now **three** partial registries — `DATA_F_REGISTRY` (units), `CROP_PROVENANCE` (sources), `CHATBOT_FIELDS` (hand-curated chat descriptions, a subset excluding crops/channels/labor). They overlap and will drift. `FORM_STATE_VERSION` is stamped but never read, and `applyFormState` skips ids it can't find, so any markup rename silently drops fields from saved plans | **must precede any UI overhaul** |
| **E6** | Extract pure leaves to ES modules; replace the auto-save monkey-patch with an `app:navigate` CustomEvent — the hook the assistant needs for section awareness | ⛔ open |
| **E7** | Route user strings through `escHtml` at the render boundary (used 11 times of ~30 sites) | ❓ |
| **E8** | Matplotlib waterfall rendered and discarded on every solve, including all 100 Monte Carlo draws | ❓ perf |

---

## Tier 6 — Interface (audit Phase F — largely SUPERSEDED)

`STRATEGY.md`'s interface direction replaces most of this. **Do not build:** the hand-rolled
wizard, progressive-disclosure toggle machinery, a provenance badge panel, a zero-acre explanation
panel (emit reasons instead — S2), tooltip expansion as a UI project.

**Survives, because the assistant needs it:** E5 (registry), E6 (`app:navigate`), addressable
views, and a solver that explains itself (S2, C4).

**Also survives on its own merits:** print is broken for the one thing print is for (the Executive
Summary prints white-on-white with Chrome defaults) — and D1–D5 are all artifacts a grower prints.
Mobile has confirmed horizontal overflow at 375px. Both ❓, from the audit's browser pass.

---

## Tier 7 — Pilot hardening (audit Phase G) — gated on a real user

Pull the whole of this forward **the moment a pilot user is imminent**. These are about other
people's data, not model quality.

| ID | Item |
|---|---|
| **G1** | **No account allowlist.** Google sign-in has no allowlist, domain restriction or invite table — "private pilot" currently means anyone with a Google account who finds the URL |
| **G2** | No per-user rate limiting or payload cap on `/api/chat`; each call fans out to 3 provider requests and the quota is farm-wide |
| **G3** | A DB blip returns a bare 500 for `/` itself — `getSession()` is un-caught and `run_worker_first: true` runs it for every request, though the solver is entirely client-side |
| **G4** | **The privacy promise is false.** The hub says "All calculations run in your browser. No data is sent anywhere." The assistant POSTs the entire form state — farm size, cash, credit line, wages, prices — to a third-party LLM, and plans persist to Neon |
| **G5** | Scenario identity by uuid with a revision column (two tabs clobber silently); Origin/CSRF; fence client-derived text in the system prompt as data; cap the form-state blob |
| **G6** | Close the assistant's **say-do gap** — validators silently drop out-of-range values, truncated tool-call JSON becomes a cheerful no-op, unmatched crop names no-op invisibly, so the assistant claims changes that never happened. Make validation *report* |

---

## Tier 8 — Testing

Much of the audit's Part 7 has landed: **CI exists** (`.github/workflows/ci.yml`), `npm test`
exists, the blob-sync check exists, and the suite is **226 tests + 6 node harnesses**, up from 131.
`test_binding.py` exists — the constraint-bindingness guard the audit asked for.

Still open:

| ID | Item |
|---|---|
| ⛔ **T1** | The in-page browser suite (E1) — crashes, false-green, corrupts app state |
| ❓ **T2** | `test_regression.py` pins a March-2026 baseline that no longer matches; red by design. Rebaseline with recorded provenance or delete it — a permanently red test trains everyone to ignore failures |
| ❓ **T3** | Vitest for `worker/` — the LLM validators are the trust boundary between untrusted tool-call JSON and the user's form, and they are pure functions |
| ❓ **T4** | Playwright smoke: load, solve with defaults, assert a numeric profit and no console errors |
| **T5** | **A standing rule worth adopting:** four times on this branch a *working* guard produced no visible effect (the ambient guard writing to a hidden view being the latest). A guard is not done until something asserts a human would see it fire |

---

## Strategy-tier — needs the grower's sign-off, in its own session

| ID | Question |
|---|---|
| ✅ **X1** | ~~Persona: does this serve larger farms too?~~ — **RESOLVED 2026-07-29, and it was never a persona change.** The grower's clarification: the persona stands (mixed vegetable, small/medium, manual labour, rotation, diversity, local channels); these farms *selectively adopt individual large-farm practices for individual crops* — contract labour for strawberries only, a rented water wheel for brassicas only, a potato digger for potatoes only, U-pick alongside conventional sales. That is `track` class, not `strategy`, so it needed no separate session. The research confirmed the shape: see **R3**. Remaining coverage work is R1–R6 |
| **X2** | **The finish line.** `STRATEGY.md`: "N real growers produce a season plan they would act on. Until that number is set, bet ③ has phases but the product has no finish line." N, who, and roughly when |
| **X3** | **Bet order after the interface direction.** ①②③ predates it. Phase C got more important, E5 got promoted, Phase F partly evaporated |
| **X4** | **The crop CSV pipeline — a live contradiction.** The July audit recommended **deleting** it as ~230 lines of unreachable code. On 2026-07-29 it was **wired up instead**, after the grower went looking for it. Bulk crop import also serves the larger-farm persona (X1). Decide: keep and maintain, or delete |

---

## What this list says about sequencing

Three observations that fall out of the mapping, offered as input to X3 rather than as a decision:

1. **Tier 0 is almost entirely `defect` class**, which under the anti-lurch rule needs no
   consultation — it can proceed while the strategy questions are open.
2. **S5 (year-wrap) is the highest-leverage single item.** It unblocks D1, D2 and D3, it is the
   same root gap as garlic's fabricated calendar, and garlic is ~32% of farm contribution. We have
   corrected garlic's seed cost, nitrogen, shelf life and labour while its *calendar* remains
   impossible to express.
3. **D4 is a defect, not a feature.** W1 is a wrong number on screen today. Building the sales
   calendar is deleting a reconstruction and reading a variable we already return.
