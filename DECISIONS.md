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
**research what the industry actually does.**

**RESEARCH VERDICT: the input is intuitive and the DERIVATION is wrong — in two ways, which is
exactly why two prior audits disagreed about the direction. There is no single direction.**

**Defect 1 — scale, ~2× across the board.** `lbs_per_tote` is a hand-lift weight (the library runs
12–57 lb) divided by an 18-gallon tote (`TOTE_M3 = 0.068137` m³ = **2.406 ft³**, `index.html:2447`)
that nobody fills to that weight. The whole library implies **5.0–23.7 lb/ft³** where industry pack
weights imply **14–48 lb/ft³**. An 18-gal tote of cucumbers at a real 38 lb/ft³ would weigh ~91 lb —
well past the [NIOSH 51 lb load constant](https://www.cdc.gov/niosh/docs/2007-131/pdfs/2007-131.pdf),
which is the ~50 lb convention hiding inside every hand-handled container spec.

**Defect 2 — the rank order is SIGN-FLIPPED on the exact pair the concern named.** Verified across
all 29 templates:

| | model implies | industry (KSU pack weights) |
|---|---|---|
| Spinach | **12.9 lb/ft³** | 16–20 |
| Cucumbers | **9.6 lb/ft³** | 36–44 |

**The model has spinach denser than cucumbers; reality has cucumbers 2.0–2.5× denser than
spinach — a relative error of ~3–3.4× in the wrong direction on that pair.**

⚠️⚠️ **URGENCY CORRECTED (same day, before the grower acted on it). My first write-up said this was
"shaping the plan right now". It is NOT — it is latent.** Measured:

| pool | peak / cap | binds? | crops |
|---|---|---|---|
| cold | 135 / 275 m³ = **49.3%** | no | Spinach, Cucumbers, Kale, Tomatoes, Hot Peppers |
| ambient | 136 / 150 m³ = **90.5%** | **no** — no week reaches 100% | Garlic, Basil |

Three things I got wrong and am correcting: (a) **neither pool binds**, so nothing is being
rationed; (b) the ambient crops are **Garlic and Basil**, not the "cured alliums and winter squash"
I wrote, and **garlic's 23.7 lb/ft³ is one of the values the research marked roughly RIGHT**
(~25–30); (c) **basil is a herb and the research table does not cover herbs** — fresh herbs are
genuinely very bulky, so its 5.0 lb/ft³ may be near-correct. Correcting the densities would loosen
both pools, so today's plan would not change.

**What that means for scheduling:** the defect is real and worth fixing (correctness, and it bites
any farm with tighter storage than the demo), but it is **credibility work, not plan-changing
work** — the low-priority tail of the crop-data batch, not its headline. This correction is the
"verify the axis the fix does not mention" rule applied to my own finding.

**Negative finding worth recording** (it saves the next person the search): **USDA Agriculture
Handbook 66 does NOT contain bulk densities.** All 38,822 lines were pulled and grepped — zero hits
for "bulk density", "lb/ft³" or "kg/m³". AH-66 is temperature / RH / ethylene / shelf life. The
usable substitute is bushel-denominated pack weights ÷ the container's exact legal volume
(1 US bushel = 2,150.42 in³ = **1.2445 ft³**), which cross-checks internally (greens at two box
sizes agree; winter squash carton and bulk bin agree).

**Recommendation — keep the container idea, fix what it means.**
1. **Make the input a container PICKER**, not a free-text weight: 1-1/9 bu carton (1.383 ft³) /
   bushel box (1.2445) / RPC field lug (1.006) / 18-gal tote (2.406) / 48×48×28 bulk bin (28.7) /
   50-lb sack. The container then supplies the volume **exactly**, and `lb per container` becomes an
   optional override.
2. **Ship per-crop default bulk densities** from the pack-weight table.
3. **Add a fail-CLOSED tripwire**: warn when an entered weight implies a density more than ~1.5×
   outside the published range. ⚠️ Given this repo's history of tripwires failing open on NaN
   (the P&L reconciliation guard), guard the non-finite branch explicitly.
4. ⚠️ **Separately expose the room derate.** Product occupies only ~35–40% of gross room volume once
   bins, pallets, aisles and airflow are counted (USDA NASS reports 82% *usable* of gross for racked
   warehouses — a different derate, and the industry conflates the two). That factor is currently
   smeared into the per-crop densities, which is part of why they all read ~2× low. **It is a
   property of the room, not the crop, and belongs in the capacity input.**
5. **Do NOT switch to bins-per-acre** — it re-encodes yield, which the model already has, and
   growers cannot estimate it for a crop they have not grown.

**Grower action still useful:** weighing one full tote of two or three crops would validate the
derate in (4), which is the least well-sourced number in this section.

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

## GROUP E — Loss, storage and shelf life (proposals, 2026-08-29; awaiting the grower)

Raised by the grower reading toy v1: *"does 85% mean the other 15% is not sellable, or that it
couldn't find sales? If it's the latter, shouldn't that get factored into storage?"* Backlog rows
**G1/G2/G3**. All three measured before proposing. **They ship as one batch or not at all** —
E1 makes holding physically honest, E3 makes it cost something, and E2 sets the honest durations;
any one alone moves the plan the wrong way.

### E1 · G1 — split `sell_through_fraction` in two, because it is two things

**The finding.** The form defines sell-through as *"after spoilage, grade-outs, returns, and
unsold perishables"*. The solver implements grade-out at harvest only: `succ_weekly_sellable_lbs`
= `st x land x yield / n_harv` feeds C4a's inventory inflow, C4b's room occupancy, C4c's shelf
life and the waste report, so the missing 15% never occupies a cooler. Returns came back from a
buyer, unsold perishables sat in the room, spoilage largely happens IN store. All were cooled.

**Measured, golden farm:** room occupancy understated by 1/0.85 = **17.6%**. Ambient barn
**90.5% → 106.5% of capacity** — the shipped default plan is infeasible on the disclosed reading
of its own input. Cold 49.3% → 58.0%.

**Why the obvious fix is wrong, and this is the part worth reading.** My first recommendation was
"narrow sell-through to grade-out and let demand caps + waste carry the rest." **That is wrong.**
Measured: 8 of 14 crop-channel rows sit at 100% of their weekly ceiling and `waste` is 0 lb across
all seven crops. The optimizer grows exactly what it can sell, so **the model never has
systematically unsold product** — the cap already prevents it existing. Demand caps carry the
deterministic CEILING; they carry no variance below it. Narrowing sell-through to field cull would
delete the only representation of "you brought it and it did not sell" and make the farm more
profitable and less realistic — the direction every mis-fix here has moved.

**The grower cannot supply the split** (asked directly: *"highly variable"*). That is not a gap in
their knowledge, it is evidence the two things are different quantities and need different names.

**PROPOSAL — two fractions, applied on opposite sides of the store:**

| name | meaning | applied | today |
|---|---|---|---|
| `pack_out_fraction` | gross harvest → marketable product leaving the field/packhouse. Culls, off-grade, damage. **Never enters the cooler.** | at harvest, before inventory | this is what `st` silently does |
| `sell_through_fraction` | marketable product OFFERED → actually sold. Returns, unsold at market, rejected loads. **Was cooled, shipped, and did not come back.** | at the sale, after storage | not modelled at all |

Both are standard produce terms and neither is a coinage.

**Mechanism.** `v[c,ch,w]` stays pounds SOLD — demand caps and revenue are untouched. The
inventory drawdown becomes `v / sell_through`: to sell 85 lb you shipped 100. Linear (a constant
coefficient), so nothing about the LP changes shape. Then:
- C4a inflow uses `pack_out x H` — culls never enter the room ✓
- C4b room occupancy rises, because product now passes through the store before being lost ✓
- the lost portion leaves inventory and never returns — the grower's own point, *perishables do
  not go back in the cooler* ✓
- report `market_loss_lbs` beside `waste_by_crop`, per this repo's rule that an invisible number
  is an unauditable one

**DEFAULTS — the one real decision.** Preserving today's economics needs
`pack_out x sell_through = 0.85`, and the split is unknown. Three options:
1. `pack_out=1.0, sell_through=0.85` — all loss downstream. **Conservative for sizing** (the barn
   goes infeasible, which is the honest reading of today's tooltip) and it makes the existing copy
   true. **Recommended interim.**
2. `pack_out=0.85, sell_through=1.0` — today's behaviour exactly. Zero movement, and the tooltip
   stays false.
3. Per-crop sourced pack-out rates from extension budgets (published for vegetables, typically
   70–95%). **The right end state, and it is Batch 3 crop-data work**, not this fix.

Recommend shipping (1) with the mechanism, then (3) with the crop sweep. ⚠️ (1) re-pins the golden
farm and will need the Batch protocol: own commit, assert the direction, document per-line deltas.

**COMPLEXITY TEST:** passes. "What share of what you pick is packable?" and "what share of what
you take to market comes home?" are both things a grower has a feel for; "sell-through" as a
single blended number is not.

---

#### ⭐ GROWER RULING, 2026-08-29 — sell-through is PER CROP x CHANNEL

> *"It depends per crop whether or not product can be brought back from market. To me this says
> that the sell-through needs to be specific to crop AND channel. In the current app's UI, this
> means it should not fall under market channel or crop, but under the parameters within each
> channel on each crop."*

**Accepted, and it supersedes the farm-wide field.** The reasoning that got here, in the grower's
own steps: a wholesaler orders, you deliver, you invoice — **there is no unsold portion**, so
sell-through is ~1.0 by construction. At a market stall you bring a full display because you
cannot sell from an empty table, so you always offer more than you sell — and whether the
remainder is *lost* or merely *delayed* depends on the crop, not the channel.

So the quantity is **channel x storability**, and only a crop-channel cell can hold it.

**Placement is already correct in the data model:** `crop["channels"][name]` holds `price_per_lb`,
`packaging_cost_per_lb` and the demand cap. `sell_through_fraction` belongs beside them. Today the
solver has a farm-wide default plus a per-CROP override and **no channel dimension at all**
(`solver.py` Step 3b / C4a), so this is a new axis, not a move.

#### ⚠️ CORRECTION (2026-08-30): I ACCEPTED "SELL-THROUGH IS THE VARIANCE" AND IT IS INCOHERENT

I wrote here that the grower's reframing — *"the demand cap is the demand projection, and
sell-through is the variance in that"* — was "sharper than anything previously written down."
**It is wrong, and the model cannot mean it.** Retracted, with the reasoning, because the framing
had already reached the toy's documentation.

**Why it cannot mean variance. The demand cap is a HARD ceiling** — `solver.py` C6 emits
`add_row([(v, 1.0)], -inf, cap_w)`. So at a 6,000 lb cap and 0.85 sell-through: to sell 6,000 you
must offer 7,059 and lose 1,059 — **every week, including the best Saturday of the year, because
the model will never let you sell 6,001.** That is the entire downside of bringing extra with none
of the upside. It is not a model of uncertainty; it is a one-sided penalty. Under a genuine
variance story the whole point is that some weeks demand exceeds the plan and the extra stock
*earns* — which a fixed right-hand side structurally forbids.

**What the model actually implements is a DISPLAY REQUIREMENT.** A picked-over stall sells less
than a full one, so moving 6,000 lb needs visibly more than 6,000 lb on the table. That is
deterministic and it is an INPUT REQUIREMENT, like seed: you need ~7,059 lb of *presence* to
convert 6,000 lb of *sales*. Coherent, linear, and it belongs exactly where the grower ruled it
belongs.

**THE DEFENSIBLE DEFINITION, narrowed:**

> **Sell-through** = the deterministic, non-recoverable share of what you take to market that does
> not convert — display shrink on a stall, damage in transit, a rejected load. **Not uncertainty.**

⚠️ **The app's tooltip is worse than imprecise: it mixes both stories.** "after spoilage,
grade-outs, returns, and unsold perishables" spans a display requirement, a storage loss, a
returns process and a variance story. Rewriting it to the narrow definition is part of E1.

| | cap means | sell-through | why |
|---|---|---|---|
| Wholesale / contract | a purchase order | ~1.0 | you deliver the order — there is no table to fill and no unsold portion |
| CSA | pre-sold shares | ~1.0 | paid before it is planted |
| Market, perishable | a hard ceiling | < 1.0 | the table must be fuller than the sale; unsold is compost |
| Market, storable | a hard ceiling | **no physical effect** | everything unsold comes home — measured: at returns = 1.0, `consumed = offered − returned = offered × st = sold`, so it is a pure delay |

**WHERE GENUINE VARIANCE HAS TO GO — and it is not here.** What the variance story describes is
the **newsvendor problem**: choose *q* before knowing demand *D*, sell `min(q, D)`, and the optimal
overstock depends on the ratio of margin-lost-by-understocking to cost-eaten-by-overstocking. Three
things follow that no flat fraction can express: the right overstock differs **by crop and
channel** (garlic at $6/lb that goes back in the barn should be overstocked heavily; spinach that
becomes compost barely at all — one number gets both wrong in opposite directions); it should
**respond to price**; and it needs the cap to **stop being a hard ceiling**, since the upside
requires demand to sometimes exceed its planning figure.

A deterministic LP with fixed right-hand sides has nowhere to put that. It needs either a
distribution over demand with a chosen service level, or a deterministic plan stress-tested
against demand draws. ⚠️ **And the app's existing risk machinery is not that second thing either:
Monte Carlo re-optimises the crop mix on every draw (backlog W2), so it answers "what would I have
planted if I had known" rather than "how does this plan hold up in a bad week." There is no
working home for the variance story today.** It is a Batch 4 RISK question, not a cost-model one.

⚠️ **NAMING IS STILL OPEN, and the grower flagged it first** (*"I'm not sure that we're calling
this the right thing"*). In retail, "sell-through" means the share of received stock sold in a
period — which is closer to the variance story we just rejected. Under the narrow definition the
quantity is a *display/attrition requirement*. Candidate rename: **`market_overage`**, stated the
way a grower can actually say it — *"I bring about 15% more than I expect to sell"* — rather than
a fraction they must invert.

⚠️ **If it is renamed that way the arithmetic changes and it is a live trap:** bringing 15% MORE
than you sell is `offered = 1.15 × sold`, i.e. sell-through `1/1.15 = 0.87` and a loss of **13% of
what you brought** — not 15%. "Bring 15% more" and "lose 15%" are different numbers. Whichever
form ships, the label must say which one it is.

**MEASURED SIZE OF THE ERROR.** On the golden farm **57% of pounds move through Wholesale**
(726,987 lb, 40% of revenue). A farm-wide 0.85 charges a market-stall haircut to every one of
them: **128,292 lb** grown, cooled, stored and discarded on a channel that would have had a signed
order.

⚠️ **DIRECTION WARNING, stated before it is built.** Wholesale at ~1.0 drops the farm's blended
loss from 15% to roughly 6–7%, so the farm grows less, spends less, and **net margin goes UP** —
the wrong way for M1, which is already too high at 20.1%. Partly offset by storage rising. This
project has a documented pattern of correct fixes moving margin the wrong way (four of them); the
answer is to model the market-day overage honestly, not to keep a wrong number because its sign is
convenient.

**A SECOND FIELD FOLLOWS FROM THE RULING.** "Brought back from market" needs somewhere to live.
Proposed as a per-crop-channel `returns_to_store_fraction`: 0 for perishables at a stall, ~1 for
cured storables, irrelevant where sell-through is 1.0. Alternative shape — a single per-crop "can
be re-offered" flag — is simpler but cannot express the same crop behaving differently at two
outlets, which is precisely the distinction the ruling turns on. **Recommend the crop-channel
fraction; flagging it as the one place this ruling adds a knob rather than moving one.**

⚠️ Sourcing is OPEN: the ranges above (wholesale 97–99%, market perishables 70–90% per market day,
CSA ~100%) are my characterisation and carry **no citation yet**. Per this project's own rule a
number no stranger can check does not ship — these need extension/market-survey sources before
they become defaults. Rides Batch 3 with the crop-data sweep.

### E2 · G2 — every shipped shelf life comes from a deprecated field

`shelf_life_weeks` appears **once** in `index.html`, inside the embedded solver blob. No UI writes
it, so all seven crops fall through `c.get("shelf_life_weeks", c.get("sales_spread_weeks", 1))` to
the old field. A sales WINDOW is not a shelf life. Live: Spinach 2, Cucumbers 2, Kale 2, Tomatoes
1, Hot Peppers 2, Garlic 16, Basil 1. Garlic's real storage life is 26–35 weeks.

⚠️ Compounded: the 2026-07-28 ruling made `L` COUNT the harvest week and its own note says
*"anything relying on the old reading needs its value raised by one."* The values were never
raised, so every crop authored under the old reading has one week LESS selling time than intended,
and `L=1` (Tomatoes, Basil) now means "hold nothing at all."

**PROPOSAL:** a per-crop `shelf_life_weeks` field with sourced defaults (USDA Handbook 66, the
same source the crop library already cites for storage), the +1 correction applied crop by crop
with its reasoning recorded, and `sales_spread_weeks` retained as an IMPORT alias only.
**Blocked by E3** — see below. Ride Batch 3.

### E3 · G3 — holding is free, and that blocks E2

`storage_loss_frac_per_week` is fully implemented in the solver (it is the `(1-loss)` coefficient
in C4a and the decay weighting in C4c) and **defaults to 0 with no form field anywhere** — the
adapter reads a payload key nothing ever sends. This is the playbook's Phase-3 class exactly: *a
feature implemented in the solver and switched off by an empty column.*

Consequence: a long shelf life is pure upside. Raising garlic to a truthful 30 weeks (E2) without
this makes hoarding strictly better, which is why SPEC_v3 §3.4 names it a hard prerequisite.

**PROPOSAL:** wire the existing parameter to a per-crop field with sourced defaults (a few tenths
of a percent per week for cured alliums, several percent for leafy greens). No solver change is
needed — the mechanism is already there and already guarded. This is the cheapest of the three and
it unblocks E2.

**ORDER: E3 → E1 → E2, one re-pin at the end.**

---

## Rulings on the audit's three open questions (2026-07-31, all resolved)

**M9 — volume basis: proceed with the recommended scope.** `STRATEGY.md`'s "volume/pack basis"
non-goal is **narrowly amended at the lock** (see that file). Scope: correct the 29 template
densities **and** pull the room derate out of them into the capacity input — coupled, never one
without the other. Container picker and any per-buyer research stay non-goals. Scheduled as the
**last item of Batch 3**, droppable if the batch runs long, because it changes no current plan.

**U1 labour controls: no interim change — the wizard handles it.** Grower: *"For the UI, we will
handle that with the wizard."* The setup toggle keeps doing nothing on a normal Optimize until
Batch 7. Recorded as a **deliberately accepted say-do gap**, so it is not re-reported as a defect
by the next review pass.

**N (definition of done): deferred, on the record.** Grower: *"I'm not really thinking about the
pilot yet."* The consequence is stated in `PLAN.md` Batch 7 — while N is unset, no batch may be
re-scoped on pilot-readiness grounds; if pilot timing ever starts driving a decision, set N first.

---

## Useful from the grower — but NOT blocking (grower: *"extras if I have comments"*)

**Nothing here gates execution.** Each item ships with a sourced benchmark default and a disclosed
provenance; a grower answer replaces a default, it does not unblock a batch. Recorded so the
answers land somewhere if they arrive.

1. **W17** — what a field hand actually costs locally, $/hr before payroll load. *(Default: NASS
   Farm Labor regional field-worker wage.)*
2. **R1** — do you spray, what, on which crops, roughly what per acre? *(Default: 0 with an honest
   label until Batch 3 sources extension figures.)*
3. **R2** — do you carry insurance, roughly what per year? *(Default: benchmark premium; the
   payment-week input matters more than the amount for C13.)*
4. **R4 / R5** — do you hire crews by the job? Sell any volume U-pick? *(Shapes Batch 6's spec
   priorities; the mechanism gets built either way.)*
5. **M9** — weigh and measure one full tote for 2–3 crops. *(Validates the room derate, the
   least-sourced number in that fix.)*
6. **W10** — is pumping separable from your general electric bill? *(Default: whole bill, disclosed.)*
7. **X2** — confirm the Cloudflare dashboard shows no deployment. *(Evidence already says none;
   this is the only item with a security consequence if the evidence is wrong.)*

---

## Appendix — commissioned research (2026-07-31)

Both briefs are folded into B5 (M9) and C2 (P13/R6) above. Primary sources, for audit:

**Volume basis (M9).**
[USDA Agriculture Handbook 66](https://www.ars.usda.gov/ARSUserFiles/oc/np/CommercialStorage/CommercialStorage.pdf)
(bushel conversion p. 8; **contains no bulk densities** — verified by full-text grep) ·
[KSU MF-979 container/pack weights](http://okfarmtoschool.com/wp-content/uploads/containers-and-packaging.pdf) ·
[UGA C780 weights & processed yields](https://fieldreport.caes.uga.edu/publications/C780/weights-and-processed-yields-of-fruits-and-vegetables/) ·
[NC State, Produce Packaging Ch. 9](https://content.ces.ncsu.edu/introduction-to-the-postharvest-engineering-for-fresh-fruits-and-vegetables/9-produce-packaging) ·
[USDA NASS Capacity of Refrigerated Warehouses, Feb 2026](https://esmis.nal.usda.gov/sites/default/release-files/795764/rfwh0126.pdf) ·
[NIOSH 51 lb load constant](https://www.cdc.gov/niosh/docs/2007-131/pdfs/2007-131.pdf) ·
[Rehrig 6413 RPC spec](https://www.rehrigpacific.com/supply-chain/products-and-solutions/6413-rpc) ·
[MacroBin 26FV](https://palletsandbins.com/products/48x48x28-vented-agricultural-harvest-bin-california-standard)

**Rent vs own (P13/R6).**
[2022 Census of Agriculture, Table 3 — Farm Production Expenses](https://www.nass.usda.gov/Publications/AgCensus/2022/Full_Report/Volume_1,_Chapter_2_US_State_Level/st99_2_003_003.pdf) ·
[ERS: 39% of farmland rented](https://www.ers.usda.gov/data-products/charts-of-note/chart-detail?chartId=109182) ·
[ERS Farmland Ownership and Tenure](https://www.ers.usda.gov/topics/farm-economy/land-use-land-value-tenure/farmland-ownership-and-tenure) ·
[NASS 2025 Land Values and Cash Rents](https://www.nass.usda.gov/Publications/Highlights/2025/2025LandValuesCashRents_FINAL.pdf) ·
[MU Extension G435 — the DIRTI five](https://extension.missouri.edu/publications/g435) ·
[Iowa State, Acquiring Farm Machinery Services](https://www.extension.iastate.edu/agdm/crops/html/a3-21.html) ·
[UNL custom rates 2025](https://cap.unl.edu/news/custom-rates-2025-field-operations/)

⚠️ **Data gaps both briefs flagged, worth carrying:** NASS publishes **no vegetable-specific cash
rent series** (row-crop averages badly understate intensive veg ground), **no national tenure data
for greenhouse or retail space**, and the 2025 Maryland/Delaware custom-rate survey **dropped
vegetable-specific lines** (bed-forming, plastic-laying, transplanting) for lack of responses. Where
this file cites a vegetable figure it is inference from adjacent data, not a published series.

---

## Appendix — commissioned research: seasonal farm labour (2026-08-31)

Commissioned for **GROUP F / L1** after the grower asked how hiring migrant harvesters and
seasonal pickers actually works — contracts, lead time and cost. **The headline finding is that no
path is a spot market**, which is what condemns the per-week hire variable.

**Path A — H-2A (formal guest-worker programme).**

| step | lead time before start |
|---|---|
| Job order (ETA-790) to the State Workforce Agency | **60–75 days** |
| DOL application (ETA-9142A) via FLAG | 45 days |
| Complete file for a certification decision | 30 days |
| Workers may enter the US | 3 days |

An emergency filing path exists under 45 days. Wages moved to a **two-tier skill-based AEWR** on
2025-10-02, replacing the single statewide rate: FY2026 Skill Level I averages **$12.31/hr**
nationally and Level II **$16.07/hr**, updated rates effective 2026-08-03, with wide state spread
(California L-II $18.60, Oregon $15.13) and some states up 21%.

**Non-wage cost dominates: ~$10,000/worker minimum (USDA).** Housing **$9,000–13,000/worker** is
the largest line; inbound transport $400–650; subsistence $16.78/day without receipts (to $68 with);
agent fees $1,500–3,500/application plus $100–250/worker recruitment; filing fees ≥$1,350.

⭐ **The three-fourths guarantee** — the employer must *offer* at least 75% of the workdays' hours
in the contract period (10 weeks x 40 h = 400 h → guarantee 300 h) or pay them regardless. Breach
means back wages, civil penalties and 1–5 year debarment. **This is a minimum-commitment
constraint written into federal regulation, and it is the mechanism the model has no
representation of.**

**Path B — local direct hire** (what an ~80-acre diversified veg farm actually does). Recruit
**8–10 weeks** ahead; experienced seasonal workers book their season months in advance. Average
hired farmworker wage **$18.13/hr** (ERS, 2024); NASS gross **$19.52/hr** (April 2025 reference
week). Demand spikes at spring planting (Apr–May) and harvest (Aug–Oct). Availability is not
assured — Purdue survey respondents reporting "some or a lot of difficulty" hiring rose from ~30%
(2020) to ~66% (2021).

**Path C — farm labour contractor.** The FLC assembles crews of 30–40 and is the workers'
employer, so payroll tax, comp and benefits sit with them; the farm pays a billing rate above the
wage. ⚠️ **No ag-specific markup figure was found.** The 1.2–1.5x commonly quoted is from general
contracting, not agriculture — treat it as an order of magnitude, not a sourced number. If this
path becomes load-bearing, source it properly first.

**Ruling implied for the app (recommendation, not yet the grower's):** do **not** model H-2A. At
80 diversified acres the ~$10k/worker non-wage floor and 75-day lead rule it out; it is a
large-monoculture instrument. One sentence in the assumptions box, not a feature. **Do** change
the shape of the hire decision to a committed block — which `employees[]` already expresses.

⚠️ **Scale caveat.** Programme-level figures (AEWR, ¾ guarantee, the $10k floor) are firm and
sourced. The FLC markup is not. The 8–10 week domestic lead time is trade-press guidance rather
than a survey statistic — directionally reliable, not a number to compute against.

**Sources.** DOL processing times <https://flag.dol.gov/processingtimes> · farmers.gov H-2A
<https://www.farmers.gov/working-with-us/h2a-visa-program> · DOL AEWR data
<https://www.flag.dol.gov/wage-data/adverse-effect-wage-rates> · Cornell Agricultural Workforce
Development, new AEWR methodology
<https://agworkforce.cals.cornell.edu/2025/10/10/major-h-2a-wage-changes-overview-of-new-aewr-methodology/>
· CRS IF12408 <https://www.congress.gov/crs-product/IF12408> · DOL WHD Fact Sheet 26E, three-fourths
guarantee <https://www.dol.gov/agencies/whd/fact-sheets/26e-job-hours-three-fourths-guarantee-H-2A>
· AFBF Market Intel, H-2A application costs
<https://www.fb.org/market-intel/snail-mail-and-government-bills-h-2a-application-costs> · USA Farm
Labor cost breakdown <https://www.usafarmlabor.com/blog/detailed-breakdown-of-h2a-visa-program-costs>
· USDA ERS Farm Labor <https://www.ers.usda.gov/topics/farm-economy/farm-labor> · USDA NASS Farm
Labor <https://esmis.nal.usda.gov/sites/default/release-files/x920fw89s/0v839z45n/gt54nm405/fmla0525.pdf>
