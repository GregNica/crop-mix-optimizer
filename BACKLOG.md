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
| ⛔ **S1** | **`validate.py` is never called by the app.** The whole 330-line guard layer is imported only by pytest and the notebook builder. A broken template produces 0 acres and no warning. Its own gaps: `_check_positive` uses `val <= 0`, which is False for NaN; crop names are never checked for uniqueness, and the chatbot's `remove_crop`/`update_crop` tools address crops *by name* | 0 call sites in `farm_v2/solver.py` or `public/index.html` | defect | D8, D10 |
| ⛔ **S2** | **No explanation for a zero-acre crop.** A crop can hit zero from at least four causes (margin hurdle, zero demand, C7/min-acreage conflict, diversity or land binding) and only the hurdle has a banner. The `diagnostics` system validates *inputs*, never explains a *result*. The audit calls this "the single highest-value trust feature in the list" | `index.html:6065-6122` are all input checks | defect | **D8**, D10 |
| ⛔ **S3** | **B4 — annual demand cap enforced as `annual/52` every week.** A grower reads it as a contract volume. Reproduced: `annual_demand_lbs=52,000` → a flat 1,000 lb/wk ceiling, so a crop harvesting in 10 weeks can sell 10,000 lb of a 52,000 lb contract | `farm_v2/utils/demand.py:88` | defect | **D4**, D3 |
| ⛔ **S4** | **B5 — season windows must contain the whole crop cycle**, but growers enter them as *planting* windows. Winter Squash and Melon still generate **zero successions**, silently | `farm_v2/utils/calendar.py:106` | defect | **D1**, D3 |
| ⛔ **S5** | **B6 — no year-wrapping seasons.** Nothing plantable after ~week 45; overwintering is impossible; land is structurally idle Nov–Dec. **Same root gap as the agronomy audit's fabricated garlic window** — real garlic goes in Sept–Nov and overwinters. Garlic is ~32% of farm contribution | no wrap logic in `calendar.py` | defect | **D1**, D2, D3 |
| ⛔ **S6** | **B7 — water storage is billed but banks nothing.** `water_storage_capacity` appears only as a fixed-cost multiplier. A tank costs money every week and stores no water | `farm_v2/solver.py:443` | defect | D10 |
| ⛔ **S7** | **B8 — overlapping demand ranges overwrite rather than accumulate** (`=` not `+=`), order-dependently. Two overlapping contracts yield the *lower* cap | `farm_v2/utils/demand.py:100` | defect | **D4** |
| ⛔ **S8** | **What-If and Monte Carlo bypass `validateParams` entirely.** Five solver entry points; only `runOptimizer` is guarded. Lower severity than it sounds (What-If *scales* rather than zeroes), but no non-form path is checked. Altitude-correct fix is a warnings channel in the solver result | `index.html` — `run_from_js` called at 5 sites past the guard | defect | D6, D10 |
| ✅ **S9** | ~~Four visible, editable rate inputs are dead~~ — **RESOLVED** by the locked cost-accounting basis. All four have zero form fields now; they survive only as solver params fed by depreciation | 0 hits for `id="rate_*"` | — | — |
| ⛔ **S10** | **Renaming a sales channel wipes every crop's price, packaging and demand for it.** Confirmed live: the snapshot is written as `prev[ch]` where `ch` is the **old** name from `data-ch`, and read as `prev[ch.name]` from the **new** channel object. Rename → miss → every per-channel value falls back to blank | `index.html:2275` vs `:2284` | defect | D4 |
| ❓ **S11** | `deleteCrop()` renumbers card ids but not the template `<select>`'s baked index — after a mid-list delete, loading a template writes into the wrong crop card | audit 1.4 | defect | — |
| ❓ **S12** | `min_guaranteed_hours` computed and thrown away; `operating_weeks` only rescales fixed costs rather than shortening the horizon as its tooltip claims; `y[i]` binaries never given `ub=1` | audit 1.4 | defect | D9 |

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
| **X1** | **Persona: does this serve larger farms too?** Raised 2026-07-29 as "maybe the biggest thing missing". Larger-farm reality — low diversity, single crop per field per season, seasonal/contract labor, buy-not-make transplants, mechanization, herbicides/pesticides, insurance, loss, land renting. This collides with a **locked non-goal** (plot-level modelling), needs **two entirely missing cost categories** (chemicals, insurance), needs the tabled mechanisation axis (M5), and needs P13 (rent/buy). ⚠️ Trade to weigh: the small-farm persona is the one the grower can smell-test from experience; a larger-farm persona would be modelled from research with no one to check it — and this project's most expensive errors have all been numbers nobody could sanity-check |
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
