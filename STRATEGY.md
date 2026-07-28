# STRATEGY — what we are building, for whom, in what order

**One page above the plans.** It exists because for three weeks the project's direction was
re-derived from whichever prompt came last: each move locally defensible, the sequence a lurch.
The July audit had already written down the product-shape problem ("weak on the decision the
persona was promised: what do I commit to which buyer, in which week") and it sat unused because
nothing forced new work to be checked against it. Plans describe work. This describes *why that
work and not other work* — and it changes only by the rule at the bottom.

## The product

A **season-planning advisor for small/mid diversified vegetable farms** (reference zone 7; US and
Korea pilots). It turns a farm's obligations, outlets and resources into a plantable, cash-honest
season plan — and answers the four questions a grower brings to a winter planning session:

| The grower's question (their words) | Status |
|---|---|
| **"What should I plant — I need to start planning now"** | the core competence; works |
| Buy or make: transplants vs seedlings, resale, infrastructure, land rent | absent |
| Where can I cut cost | partial (bottlenecks, cost lines; no "here is your saving") |
| Which channels are working, how do I move more there | absent (crops are ranked; outlets never) |
| **When do I run out of cash?** | machinery exists (C13, interest); not asked or answered |
| **Can my crew actually do this plan?** | labor constraint exists; peak-week feasibility never surfaced |

The last two were added by review, not by the grower — the prompt set contained no cash or labor
question, so their absence from the one-pager is absence of prompting, not absence of concern. An
advisor's first artifact in a real planning session is a monthly cash calendar.

**The deliverable test:** "what should I plant" terminates physically in a seed order and a
transplant/greenhouse schedule with dates. A plan that cannot be printed and handed to a crew is
a report, not a plan.

**The organising insight** (grower one-pager 2026-07-28, as amended by adversarial review):
**the app cannot express a commitment, and therefore cannot price one.** Demand is ceilings only;
there is no must-plant primitive anywhere (verified in code).

The earlier, larger claim — that the app "inverts the planning process" and that this single
inversion explains the What-If land swings, the margin hurdle and `crop_diversity_max`'s
overloading — was **refuted** and is not to be revived. Land never binds on the shipped farm
(peak utilisation 0.847), so there are no "big blocks absorbing land"; the swings and the hurdle
have a documented, different cause (near-break-even LP indifference) with decided fixes already
recorded. Keep the narrow, verified version: no commitment object exists.

**Consequence for design:** the unconstrained solve stays the advisory baseline, because pricing
an obligation — "your CSA commitment costs $X against the free plan" — is the one thing this tool
can do that a pencil cannot. A floors-only build turns the advisor into a compliance calculator.

**Who it is for:** a grower planning ~20–150 acres of mixed vegetables across several outlets,
who knows their accounts, their crew and their ground far better than any benchmark does, and who
needs arithmetic they can trust — not agronomy lessons.

## Foundation — landed, and independent of every open bet

Solver correctness through B.3 (inventory core; storage measured as room occupancy; two storage
pools); the money-path guards and mutation discipline; the unit system; persistence and boot
robustness; no-phantom-farms; the demo derived from one canonical template library. **This work
does not get revisited by anything below.**

## The three open bets, in order

**① Product shape** — does the model of *selling* match how farms actually sell?
Evidence in `SPEC_product.md`. Ranked by what review showed actually moves outputs:
**payment terms** (C13 and the interest line are fed fiction today), **CSA as a financing
instrument** (the actively-bad-advice case), **per-channel cost-to-serve** (the primitive under
both "retail wasn't worth it" and "which channels are working"), and **allocation by stake**.
Commitment floors come *with* a with/without delta so the tool prices the obligation instead of
merely obeying it.

⚠️ Review finding to respect: on the shipped farm, obligation floors at realistic economics are
**slack** — the optimiser already plants to fill profitable demand, and a channel keeps being
served down to ~−85% price because serving costs only marginal cost once ground is planted. So
floors alone would mostly reproduce today's plans. The output-changing levers are the other three.
Floors are built to make commitments *expressible and priceable*, not because they change the
answer. Also: build them as floors on weekly deliveries `v[c,ch,w]`, **not** as acreage floors —
`min_acreage_if_planted` is conditional on the plant/no-plant binary, so the optimiser escapes it
by abandoning the crop (measured: floor ≥14 ac deletes garlic entirely, −$344k).

**② Model truth** — are the numbers and the crop logic right? (`SPEC_agronomy.md`.)
Proceeds regardless of ①: a vacuous water constraint and a mixed-basis DTM are wrong under every
product shape. ① adjusts its *emphasis* by degrees — demand and price defaults matter less than we
assumed; channel-adjacent fields matter more.

**The hold on Phases B–D is narrowed** (it had expired by its own terms — its condition was "until
the diff exists", and the diff exists). Held: the channel-adjacent slice only (demand/price
laugh-test, per-channel fields, sell-through emphasis). **Not held, start now:** exiting the B.3
stranded state (holding cost → storable shelf lives → re-pin, 2–4 days, no decision required), the
zero-research consistency sweep, water, and fertiliser.

**③ Delivery** — server, LLM chatbot, pilot hardening (`~/.claude/plans/eager-petting-hare.md`
Phases C–G). Waits behind both: shipping a shape we are about to change is how the July plan's
own Phase C came to sit unexecuted.

## Locked decisions (do not re-litigate without new evidence)

| Date | Decision |
|---|---|
| 2026-07-24 | Cost accounting: own→depreciate, consume→meter, diffuse→overhead |
| 2026-07-24 | Solver owns money; the UI renders and never recomputes |
| 2026-07-27 | Review workflow: `/simplify` before commit, `+/code-review` before landing |
| 2026-07-28 | `CROP_TEMPLATES` canonical; demo derives from it |
| 2026-07-28 | Model-generated values are never entered as data; models find sources and refute |
| 2026-07-28 | Potatoes cold; zone 7 with disclosure; holding cost before honest shelf lives |
| 2026-07-28 | Strict shelf life: weeks sellable *including* the harvest week |

## Non-goals — decided, not forgotten

Plot-level modelling (soil, pest, flood, sunlight vary per plot and are what the grower thinks
about hardest — but it needs mapping and is a different app; **disclose the assumption, do not
approximate it**); weather/yield prediction; volume/pack basis; a third storage regime;
researching prices and demand (farm-specific by nature).

## The anti-lurch rule

Every finding is classified before it changes anything:

- **value** — a number is wrong → fix it in the relevant phase.
- **defect** — code contradicts a specified semantic (a clamp that silently overrides data, a
  loader that drops a field, a constraint that never binds) → fix + guard + re-pin in one commit,
  no consultation. **This class has done more damage here than any wrong number**, and the first
  version of this rule had no slot for it.
- **phase** — an ordering issue inside a track → reorder and say so.
- **track** — changes a plan's scope → amend that spec, note it here.
- **strategy** — changes what we are building or the bet order → **requires the user's sign-off
  and a separate session on a different day.** Not "a review pass": the enforceable version is
  that no single conversation, however persuasive, can reorder the bets.

Note the honest version of roles: there is one person plus agents, so "the track lead decides"
resolves to the same human every time. The rule's only real content is the strategy-tier brake.

**Watch for the cascade:** a finding can be several tiers at once (52 diverged demo fields looked
like 52 *value* findings; the right response was one *track* finding — make the demo derived).
When many value-findings share a mechanism, classify the mechanism.

Corollary: **default values are starting places.** Their correctness never outranks field
semantics or product shape. A number that is wrong but disclosed is a smaller problem than a
number that means something other than what its name says.

## Operating rules (added by review, 2026-07-28)

- **No stranded semantics.** A behaviour-changing semantics change lands in the same phase as the
  data that makes it honest, or behind a payload flag, or its downward re-pin carries a dated
  recovery ticket named *here*. B.3 is the standing example: strict shelf life shipped with no
  off-switch, 27 of 29 templates fell to the strictest reading, and the only record is a comment
  in two test files while the suite stays green over a knowingly-degraded model.
- **One open semantics change at a time.** Parallelism is how a solo project accumulates
  half-finished states.
- **Constraint bindingness is monitored.** "Present but never binds" is how the water constraint
  went unnoticed; a fixture asserting each constraint family binds in at least one canonical
  scenario is the standing guard.
- **Definition of done for the product:** N real growers produce a season plan they would act on.
  Until that number is set, bet ③ has phases but the product has no finish line — which is how the
  July plan's Phase C came to sit unexecuted.

## Current state

Bet ① has its input (the one-pager) and needs a decision on what to build. Bet ② is mid-Phase A
(plumbing; shape-agnostic; safe to continue). Bet ③ is untouched by design.
