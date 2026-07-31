# Open Decisions — the grower's rulings, with evidence and consequences

**Purpose.** `BACKLOG.md` is the list of WORK. This file is the list of **DECISIONS**. Rulings
below are the grower's, recorded 2026-07-31 in their own framing; the analysis under each is mine
and is what an audit should attack.

**State of the build.** Branch `feat/server-llm-expansion`, 399 pytest + 9 node harnesses green,
browser-QA'd 2026-07-31. Labour money path closed and heavily guarded (W9/W12/W14/W15/W16 + an
8-lens adversarial review, a red-team pass, and mutation-verified guards).

**The golden farm's real cost structure** — the anchor for most decisions below:

| | $/yr | % revenue |
|---|---|---|
| Revenue | 2,134,530 | — |
| **Wages** (committed) | 855,150 | 40.1% |
| Overhead (flat 16%) | 341,525 | 16.0% |
| Seed / transplants | 194,973 | 9.1% |
| Packaging | 170,187 | 8.0% |
| Machinery | 52,000 | 2.4% |
| Fertiliser | 25,454 | 1.2% |
| Storage + irrigation (5 lines) | 42,347 | 2.0% |
| Fuel | 8,244 | 0.4% |
| **Water** | **0** | **0.0%** |
| Land rent | **0** | **0.0%** |
| **Profit** | **428,547** | **20.1%** |

220.6 acre-plantings, 7 crops, 198,034,968 L of water pumped per year.

**M1 posture (grower, 2026-07-31): do NOT chase the net-margin gap directly.** Fix the pieces;
margin follows. Evidence supports it — four of the five fixes that moved margin the wrong way were
reporting fixes aimed at margin-adjacent code, and the one that moved it right (W12, −16.8 points)
was aimed at correctness elsewhere.

### ⚠️ CORRECTION (2026-07-31, later the same day): my sizing estimate was WRONG, and the grower's posture is better supported than I argued

I estimated the uncharged costs at **1–3 points** against the ~5 needed, and concluded the
remainder was probably on the revenue side. **The rent-vs-own research plus a code check overturned
that.** The model is missing far more cost than I counted:

| Missing cost | Status in model | Plausible $/yr | Margin points |
|---|---|---|---|
| **Land rent** | field exists, reads **$0** | 19,600 (NASS irrigated avg $245/ac × 80) → 32,000–64,000 (realistic veg ground) | **0.9 – 3.0** |
| **Repairs / maintenance** | **does not exist** | machinery + structures, typically a large share of ownership cost | **~1 – 2** |
| **Interest on capital** | **does not exist** (only interest on operating borrowing) | opportunity cost on undepreciated balances | ~0.5 – 1 |
| **Property / personal-property tax** | **does not exist** | on owned land, structures, equipment | ~0.3 – 1 |
| **Insurance** (R2) | **does not exist** | farm-level | ~0.2 – 0.9 |
| **Crop protection** (R1) | **does not exist** | ~fertiliser order of magnitude ($25,454) | **~1.2** |
| **Water / electricity** (W10) | field missing, charges **$0** | ~4,000 | ~0.2 |

**Verified in code:** six `depreciation_*_years` inputs exist and there is **zero** occurrence of
repairs, property tax, or interest-on-capital anywhere in `farm_v2/`.

**The DIRTI finding.** Standard farm-management practice costs an owned asset as **D**epreciation +
**I**nterest + **R**epairs + **T**axes + **I**nsurance — and *"DIRTI can be 50%+ of a machine's
total lifecycle expense"* (MU Extension G435). **Our model has the D and none of the I-R-T-I.**
Two consequences: (1) ownership is systematically under-costed, which is a direct M1 contributor;
(2) any future rent-vs-own toggle would **report a false answer in favour of owning**, because a
rent quote already bundles the lessor's interest, tax and insurance.

**So the pieces plausibly total 4–9 margin points — enough to close M1 on their own.** That
vindicates the grower's instinct and retires my "the rest must be on the revenue side" claim as
unsupported. The revenue side is still unaudited (revenue per acre-planting is **$9,676**, and
Tier 2 M2/M3 have never checked the prices or yields), but it is no longer the leading suspect.

---

## GROUP A — Labour and UI

### A1 · U1 — What the base plan assumes about hiring
**RULING: DEFER.** *"We're going to overhaul the UI with a wizard chatbot driving what the user
sees and reads."*

**Agreed, with one caveat.** Deferring the design is right — a chatbot-driven UI surfaces hiring as
a question it asks, not a form section, so designing the form now is work we would throw away.

⚠️ **But deferring leaves a control in the setup form that does nothing on a normal solve** — the
exact say-do gap that tripped the grower in QA. **Recommended 10-minute interim: remove the
labour-flexibility block from setup and surface those three inputs inside the What-If panel that
actually consumes them.** That is option (b) from the original framing, it costs nothing, it
removes the confusion today, and it does not prejudge the wizard. Also unblocks U1a (validation
naming a hidden control) and lets the dead exec-summary block at `index.html:~6907` be deleted.

**Depends on:** E5 (field registry) — the backlog says it must precede any UI overhaul, and the
grower has agreed to do E5 "before we build too much more". Sequencing is consistent.

---

### A2 · U2 — Wording of the two labour levers
**Folded into U1's deferral** — same panel. The two measured sentences are banked for the redesign:
*"Optimize labor buys hours that pay for themselves"* (+$110K measured) /
*"Labor availability hires people whether they pay for themselves or not"* (−$167K measured).

---

### A3 · W17 — The hired-wage inference
**PENDING — needs one number from the grower: what a field hand actually costs locally, per hour,
before payroll load.** The app now prints its inference (~$25.71/hr all-in on the demo crew) so the
comparison is finally possible. Recommendation stands: prefill a defensible regional default,
label it as an estimate to correct, and make blank an explicit choice rather than a hidden
inference. Three inference rules have shipped and all three were the same category error.

---

## GROUP B — What the model charges

### B1 · W10 — Irrigation water
**RULING: model it as an ENTERED ELECTRICITY COST, not a computed pumping cost.** *"If a farmer
knows their electricity bills and can enter that parameter it's a lot more real than calculating
pump costs."*

**Agreed, and it is the better answer for a reason worth recording:** a farmer can verify a number
they read off a bill; nobody can verify a pumping calculation with head height and pump efficiency
in it, so a computed figure would be precision without accuracy.

**Sizing (mine, estimate):** 198M L lifted ~30 m at typical efficiency ≈ 27,000 kWh ≈ **$4,000/yr**
— 0.19% of revenue. So this is worth about **one-fifth of a margin point**. Close it for honesty,
not for M1.

⚠️ **Watch the double-count:** the locked cost-accounting basis already routes pump energy to
overhead (currently a flat 16% of revenue = $341,525). If we add an entered electricity cost, it
must come OUT of the overhead assumption or the farm pays twice. **This is the real work in W10 —
not the input, the de-duplication.**

**Open sub-question:** an electric bill is farm-wide (pumps, coolers, packhouse, lights). Do we
want the whole bill as a fixed cost, or the irrigation share only? Whole-bill is more verifiable;
irrigation-share is what makes water cost per crop meaningful.

---

### B2 · R1 — Crop protection
**RULING: BUILD IT, modelled like fertiliser.** *"Most crops will have a recommended application
amount per chemical."*

**Agreed, and the research supports the shape.** NASS 2022 (22 crops, 17 states): which chemical
class dominates **flips by crop** — squash is fungicide-led (69% of acres), sweet corn
herbicide-led (82%) — so a farm-wide rate would be wrong for most crops. Per-crop, like fertiliser,
is right.

**The grower's framing sharpens it further:** application *rate* per chemical × price, rather than a
flat $/acre, matches how a label and a spray plan actually read, and it makes the number auditable
against an extension guide. It also mirrors what the model already does for fertiliser.

**Anchor:** fertiliser costs this farm $25,454/yr (1.2% of revenue) across 220 acre-plantings.
Crop protection should land in the same order of magnitude — call it **~1 margin point**.

**The work is the DATA, not the mechanism.** After W4's refactor a sixth variable-cost category is
one edit; sourcing defensible per-crop application rates for 7+ crops is agronomy (M2/M3 territory).

---

### B3 · R2 — Insurance
**RULING: BUILD IT.** Grower asked: *"Is insurance booked differently from an accounting
perspective? Is there some sort of depreciation treatment we should be thinking about?"*

**Answer: no depreciation, and the distinction is worth stating precisely.**

Depreciation applies to **capital assets you own and consume over years** — you capitalise the
purchase and expense it across its useful life. Insurance buys **coverage over a window of time**,
so it is a **period operating expense**, expensed as the coverage elapses.

The one accounting wrinkle is **prepaid insurance**: pay a 12-month premium up front and accrual
accounting books it as a current *asset* (prepaid expense), then amortises it monthly as coverage
is consumed. **For our model that wrinkle collapses** — we are already a 52-week model, so
spreading an annual premium across the weeks it covers *is* the amortisation. No new machinery.

⚠️ **Where it genuinely does matter: CASH TIMING.** Premiums are typically due at or before
planting (crop-insurance sales-closing dates), not smeared evenly. A lump payment in week 8 hits
the C13 weekly cash floor very differently from $X/week flat. **This is exactly the W12 lesson** —
committed wages were the first fixed line that was not flat, and flattening it mis-stated the burn
in both directions. So model insurance as a fixed cost **with an optional payment week**, not just
a weekly rate.

⚠️ **A second, deeper point to disclose:** crop-insurance **indemnities are revenue in a bad year**,
and our model has no bad years (deterministic yields, no crop failure). So insurance will always
look like pure cost with no benefit — it can only ever reduce modelled profit. That is honest only
if we say so. **It links directly to W2/C4 below: insurance pays for itself in the tail, and we do
not model tails.**

⚠️ **Third, and it enlarges this item:** insurance is not only a farm-level line — it is the final
**I** of the **DIRTI** ownership cost (Depreciation, Interest, Repairs, Taxes, Insurance). Our
assets carry depreciation *only*. So R2 should be built as **part of a complete asset-ownership
cost**, alongside the missing repairs, interest-on-capital and property tax, rather than as a
standalone premium field. See the M1 correction above — together those four are a larger margin
item than everything else on this page.

---

### B4 · W5 — The diversity knob
**RULING: possibly BOTH.** *"Would it make sense for this to be both acre-weeks and total acres
planted at any given time?"*

**Yes — and they are genuinely different questions, so both is the right answer.**

- **Peak standing share** — "no more than 60% of my ground in garlic *at any one time*." A land and
  risk **concentration** limit. This is what the current label reads like.
- **Acre-weeks share** — "garlic does not occupy more than 60% of my land-*time* across the year."
  A **rotational intensity** limit. This is what the knob currently does.

A crop can pass one and fail the other, and the backlog's own example is exactly that case: garlic
at 100% of the farm for 31 weeks is **100% peak standing** (fails a 60% peak limit) but
**31/52 = 60% acre-weeks** (passes a 60% acre-weeks limit).

**Feasibility: cheap.** The model already accounts for land per week (C1). A per-crop peak-standing
row is `Σ x[i] standing in week w ≤ frac × total_land`, for each crop × week — about
**7 × 52 = 364 extra rows** on this farm, negligible against the existing model.

⚠️ **Adding a binding constraint changes plans**, so ship the peak-standing knob **defaulted to
permissive (100%)** and let the grower tighten it, or the golden farm moves for a reason unrelated
to any defect.

---

### B5 · M9 — The volume basis
**RULING: keep `lbs_per_tote` as the input** (most intuitive for a grower to enter), but
**research what the industry actually does.** — *research commissioned, results in the appendix.*

---

### B6 · W13 — The margin hurdle
**RULING: hide it; surface only if the user asks.** *"In the new UI this will become something if
the user asks for it and otherwise does not need to be seen."*

**Agreed, with two conditions.**
1. It must stay **default-off** (it is: `min_viable_margin_pct` value="0").
2. ⚠️ **The underlying defect must be fixed BEFORE the assistant can set it.** The hurdle drops
   crop-channels *before* the solve using a per-crop labour cost the objective no longer charges
   (W12 made wages committed). Hidden-in-a-form is safe because nobody sets it; **reachable-by-chat
   is not**, because the assistant could silently drop channels using arithmetic the solver
   disagrees with. Fix the basis, or do not wire it to the chatbot.

---

## GROUP C — Product shape

### C1 · W7 — The hidden constraint panel
**Not separately ruled; folded into the UI overhaul.** The panel renders ~200 lines into a card
hardcoded `display:none` (`index.html:1930`) on every solve including all 100 Monte Carlo draws.
Under a chatbot-driven UI the answer is **delete** and let the assistant render these numbers on
request — consistent with the W13 ruling above. The numbers behind it are correct (W6), so nothing
is lost.

---

### C2 · P13 / R6 — Rent vs own
**RULING: build it, simply.** Assets named: **land, implements, tractors, greenhouse space, retail
space.** *"The simpler the better… what are the heavy hitters out of what we have so far?"* —
*research commissioned, results in the appendix.*

**Heavy hitters from what we model today** (answering the direct question): of $94,347 in non-wage
fixed costs, **machinery is $52,000 — 55% of it**, and everything else is small (fuel storage
$14,083, irrigation $8,889, cold storage $6,875, water storage $6,750, equipment storage $5,000,
ambient $750).

**RESEARCH VERDICT (sources in the appendix): build LAND first, then machinery as CUSTOM HIRE.**

- **Land is the biggest line by 2–8×, the most commonly rented asset in the country, and it reads
  $0 on our demo farm.** 2022 Census: **440,431 farms (23.2%) pay cash rent, $27.31B total, avg
  $62,010/farm** — the largest rented category by far. **39% of all US farmland acres are rented.**
  Rates: NASS 2025 irrigated cropland **$244–245/acre national** ($80 WY → $483 CA). ⚠️ **Vegetable
  ground is not commodity ground** — intensive veg leases run far above the row-crop average
  (Salinas Valley ~$2,000/acre), and **NASS publishes no vegetable-specific rent series**, which is
  the main data gap. On 80 acres: $19,600 at the national irrigated average, $32k–64k at realistic
  diversified-veg rates, $160k (7.5% of revenue) at coastal-CA rates.
- **Machinery second — but as CUSTOM HIRE per acre, not tractor rental.** Custom work is **3×
  more prevalent than machinery leasing** (391,283 farms / 20.6%, $10.05B, **up 33% since 2017**)
  and the operator comes with the machine, so it substitutes for labour as well as capital. It also
  plugs cleanly into a model that already counts acre-plantings. Whole-crop custom farming runs
  $150–168/acre (Iowa 2025); at 220 acre-plantings that is **$33k–37k**, against our $52,000
  owned-machinery line. ⚠️ Vegetable-specific custom rates are thin — the 2025 Maryland/Delaware
  survey *dropped* bed-forming, plastic-laying and transplanter lines for lack of responses.
- **Skip greenhouse and retail space** — both are small dollars at this scale (UNL greenhouse
  $0.53–1.35/ft²/month; farmers-market stalls $20–75/week, ~$400–800/season) and **neither has
  defensible national tenure data**; the Census has no line item for either.
- **High-value crops skew owner-operated** (fruit/tree-nut ~88%), so the 39%-rented headline is
  commodity-driven and should not be assumed for a diversified veg farm.

⚠️ **The caveat that applies to whichever asset we build (see the M1 correction above): we must add
interest, repairs, taxes and insurance to the OWNERSHIP side at the same time**, or the toggle
reports a false answer favouring ownership. Our six asset classes carry capital ÷ life — pure
depreciation — while a rent quote already bundles the rest.

---

### C3 · R3 / R4 / R5 — One mechanism
**RULING: ONE mechanism.** *"One mechanism, and see if there are any current solver functions that
can be collapsed or simplified in this same manner."*

**Agreed — and the second half of that instruction is the more valuable half.** The shape is *a
resource bought at a price, capped, charged per unit of some basis*. Candidates already in the
solver that fit it:

- **Overtime and hire** — flagged by review as ~7 copy-pasted block pairs (allocation, objective,
  bounds, C2, C13, extraction, cost, cash, capacity_series). A lever table collapses them.
- **City water** — same shape exactly: a bought resource, priced per litre, capped per week.
- **Cold and ambient storage** — two capped pools with identical structure and separate hand-wiring.
- **Then the new ones land in the same table**: contract labour (per acre/bin/ton — **R4**, ~45% of
  US farms that employ anyone also buy labour by contract), U-pick harvest-labour offsets (**R5**),
  equipment rental, custom work.

⚠️ **`piece_rate_per_lb` already exists on seasonal employees, computes into `piece_rate_workers`,
and is read by NOTHING** — piece rate looks supported and is inert. It should be either the first
consumer of the new mechanism or deleted.

**This is the largest structural bet on the list and deserves its own spec.** It also partly depends
on the grower's answers to R4/R5 (do you hire crews by the job? do you sell U-pick?), which are
still open.

---

### C4 · C5 — Which reports first
**RULING: deferred to me,** weighted by *"which ones actually benefit us to build earlier by diving
into potentially buggy territory."*

**Recommendation: (1) labor calendar, (2) contract commitment schedule.**

- **Labor calendar (C7)** first. `capacity_series.labor {used, cap}`, `hired_hours_weekly` and
  `overtime_hours_weekly` all exist; there is no view. It is a view over the **most recently
  verified data in the repo**, and it makes the single biggest cost line legible — right now the
  grower sees an $855,150 wage number and has no picture of *which weeks they are short-handed or
  idle*. That turns 40% of revenue into a decision instead of a total.
- **Commitment schedule (C2)** second — deliverable D4, ranked 4th by the grower, sitting on
  `channel_sales`, which reconciles to the cent since W1.

**On "buggy territory": the riskiest report is benchmark deviation (C8)**, because it renders
`CROP_PROVENANCE` against crop numbers that have **never been audited** (M2/M3). It would surface
data-quality gaps — genuinely valuable, but it is agronomy work wearing a reporting costume, and it
should be scheduled as such. **Yield projection (C6)** needs a derived series that does not exist
yet, so it is more new code than the other two.

---

### C5 · W2 — Monte Carlo: can it move pre-solve?
**GROWER'S QUESTION:** *"Is there a way to bring the Monte Carlo pre-solve rather than post-solve?
I guess this would mean the solver is not just working off means of parameters, but an adjusted
mean based on the CV… I'm not sure I'm thinking about the math right. Would that benefit the model
or overly complicate it?"*

**The instinct is right, the math is nearly right, and there is a real modelling gain here — not
just a reporting fix.** Four options, in increasing cost:

**(a) What we do now — re-optimise on every draw.** Wrong: each draw's plan knew that season's
weather in advance. It reports the value of clairvoyance and labels it a planning floor. W3's
"crop stability" labels are an artifact of this, not a risk measure.

**(b) Freeze and evaluate.** Solve once, then score that ONE plan under N draws. Cheap (N
evaluations, no re-solves), and it answers the question a grower actually has: *how does the plan I
am about to execute hold up across seasons?* **This is the minimum honest fix.**

**(c) What you are proposing — plan on adjusted parameters.** Shift yields/prices by some function
of their CV before solving (e.g. plan at the 30th percentile instead of the mean). **This is a
legitimate, well-established technique** — a practical form of chance-constrained programming, and
it is what growers do intuitively when they "plan for a bad year". Implementation is genuinely
small: one knob, a parameter transform, **no new variables and no solve-time cost.**

**(d) Two-stage stochastic programming** — the textbook answer. Choose planting (`x`,`y`) once;
let sales allocation (`v`) adapt per scenario; maximise expected profit across all scenarios in a
single program. ⚠️ Cost: the `v` block (crops × channels × 52) multiplies by the scenario count. At
20 scenarios that is 20× the largest variable block on a solve already taking ~5s against a 75s
wall. **Real risk of hitting the time limit.**

**The correction to your reasoning, and it strengthens your case:** optimising on means is
systematically **optimistic** even after the foresight bug is fixed. The optimizer packs the plan
right up against constraints — storage, demand caps, cash — that only hold *on average*; in any
real season some bind harder and the plan underdelivers. So the expected profit of the mean-optimal
plan is *below* the profit computed at the mean. Your "adjusted mean" is a direct and legible way
to buy that optimism back.

**The caveat:** CV alone does not tell you *how much* to adjust. The right shift depends on how
costly each parameter's uncertainty is, which depends on which constraints bind — and that varies
by crop and channel. So a single "plan at the 30th percentile" knob is a **good heuristic, not a
derivation**, and should be labelled as a conservatism dial rather than presented as optimal.

**Recommendation: (b) then (c) — they compose, and neither is a rewrite.** Fix the foresight bug
first because it is currently making a false claim; then add the conservatism dial; then evaluate
the conservative plan under (b)'s draws. The product sentence becomes: *"here is your plan, built
to survive a 1-in-3 bad year, and here is how it performed across 100 simulated seasons."* Skip (d)
unless solve time stops mattering.

**Does it over-complicate? No — (c) arguably SIMPLIFIES the story**, because Monte Carlo stops
being a separate mysterious mode and becomes a dial on the main plan.

---

## GROUP D — Engineering

### D1 · E2 — Extract the adapter from the HTML template literal
**RULING: yes, important priority.** ~340 lines of money-affecting Python inside a JS template
literal, testable only by regex-extracting it from a string. It produced two of the defects caught
in yesterday's review, and a backtick inside a Python comment can break the entire page. On the
critical path for the server work this branch is named after.

### D2 · E1 — The in-page test suite
**RULING: yes, but not urgent.** 3,425 lines (25% of `index.html`) shipping to every user, crashing
on load, printing "All what-if tests passed" unconditionally; measured 18 assertion failures on a
fresh load, 25 after a solve. **Approach: port the blocks with real coverage into the jsdom
harnesses and delete the rest** — that migration is already two-thirds done (9 `.cjs` harnesses).

### D3 · E5 — The field registry
**RULING: yes, and do it before building much more.** Three overlapping registries keyed by
form-field id; `FORM_STATE_VERSION` stamped but never read; `applyFormState` silently skips ids it
cannot find, so a markup rename **silently drops fields from saved plans**. Correctly sequenced
ahead of the UI overhaul that U1 is deferred into.

### D4 · G4 — The false privacy promise
**RULING: fix the copy now**, and *"we do need to spend some more time thinking about what makes
sense about the data."* The hub says *"All calculations run in your browser. No data is sent
anywhere"* while the assistant POSTs the entire form state — farm size, cash, credit line, wages,
prices — to a third-party LLM, and plans persist to Neon. **Copy fix is immediate; the data-policy
question is recorded as open** (what should be sent, what should stay local, what should be
retained and for how long).

### D5 · X2 — Is it live on the internet?
**GROWER'S QUESTION:** *"Right now this is not live on the internet is it? If so we need to address
this soon."*

**Evidence says NO — not deployed.** No `wrangler deploy` in any of 24 local wrangler logs, no
deployment artifacts, and no deploy step in CI (`.github/workflows/` has none). `wrangler.jsonc`
defines the Worker but secrets are documented as local-only (`.dev.vars`).

⚠️ **I cannot prove it from this machine** — verifying requires Cloudflare auth. **Definitive
10-second check:** log in at dash.cloudflare.com → Workers & Pages → look for `farm-optimizer`; or
run `npx wrangler deployments list` in an authenticated terminal. **If it IS deployed, Tier 7
becomes urgent immediately** — Google sign-in currently has no allowlist, domain restriction or
invite table, so "private" would mean anyone with a Google account who finds the URL.

---

## Still needed from the grower

1. **W17** — what a field hand actually costs locally, $/hr before payroll load.
2. **R1** — do you spray, what, on which crops, roughly what per acre? (If not: say so and we
   disclose rather than model.)
3. **R2** — do you carry insurance, and roughly what per year?
4. **R4** — do you ever hire a crew by the job (custom harvest/planting)? Priced how?
5. **R5** — do you sell any volume U-pick?
6. **M9** — can you weigh and measure one full tote for two or three crops?
7. **W10** — is your pumping cost separable from your general electric bill?
8. **X2** — confirm the Cloudflare dashboard shows no deployment.

---

## Appendix — commissioned research

*Two research briefs were commissioned 2026-07-31 and are recorded in the following sections:
(1) how the produce industry actually expresses storage volume (M9), and (2) what farms of this
size rent vs own, with dollar magnitudes (P13/R6). Results appended on completion.*
