# SPEC_product — the I/O contract (the step-back track)

**Opened 2026-07-28 at the user's instigation: "what are we asking for and what are we providing
and is it worth it... What actually matters to a farmer when they're planning sales outlets?"**
This track outranks the agronomy audit (SPEC_agronomy) because it can change the shape the
audit's data feeds. It converges with two existing artifacts pointing the same direction: the
July audit's persona verdict ("weak on the decision the persona was promised: what do I commit
to which buyer, in which week, with what margin of safety") and the near-optimal-alternatives
decision (2026-07-27, decided/unbuilt).

## The thesis to test

**The app models sales *capacity*; a farmer plans sales *relationships*.** The solver's entire
channel vocabulary is `price_per_lb`, `packaging_cost_per_lb`, and a demand *ceiling* (verified
2026-07-28: no floors, no consistency requirement, no payment timing — revenue books the week of
sale, so C13's cash realism is fed fiction for exactly the channel where timing bites). Three
parameters are load-bearing proxies for missing concepts, which is why their "right values" feel
unpinnable: `crop_diversity_max` (rotation + stand variety + risk, three jobs), demand caps (a
ceiling standing in for commitment floors — the cause of the What-If land flapping), and
`sell_through_fraction` (deliberate overplanting-as-insurance modeled as passive shrinkage).

## Method

1. **User one-pager** — answers to the eight prompts (recorded below), written from a real farm,
   app closed. In flight.
2. **The diff** — page vs app: what the page contains that the app never asks = missing
   parameters; what the app asks that the page never mentions = arbitrary parameters; prompt 7's
   three questions = the output contract; prompt 7's credibility-killer = a "farms like a farm"
   acceptance test.
3. **Then** decide what changes shape (channel semantics? output tiers? input triage) vs what is
   confirmed as-is. Only after that do SPEC_agronomy Phases B–D spend research effort on fields
   that survive.

## The eight prompts (issued 2026-07-28)

1. **The first page of January** — planning order of operations; when do crops first get named?
2. **A promise you've seen** — what one real outlet was promised; consequences of under- and
   over-delivery.
3. **The outlet that wasn't worth it** — mix drivers beyond price; what a kept-despite-mediocre-
   price outlet was buying.
4. **The pad** — overplant sizing, per crop or per outlet; where surplus goes.
5. **A Wednesday in July** — allocation under shortage and glut; who gets shorted first.
6. **When the money lands** — payment timing per outlet; a decision it changed.
7. **The advisor test** — the three questions a plan should answer; the credibility-killer.
8. **What only the farmer knows** — vs what they wish someone could tell them.
(9 optional — the persona and what they're bad at.)

## Answers (user, 2026-07-28) — verbatim

**1. First page of January.** "The first question is what do you know you need to plant? This
absorbs the big blocks and then the rest gets filled in with extras. This is informed by channel
demand (CSA, diverse offerings at retail, past years sales, committed wholesale contracts) and
sometimes by what grew well, what infrastructure do we have that requires certain crops, what crop
rotation needs there are, and what perennials/carry-overs from the year before are there. Once you
have the necessities mapped out you can start thinking about what is going to make me the most
money outside of that."

**2. Promises.** "CSA and restaurant contracts are the ones I've seen the most of. Restaurant
contracts tend to be informal and not formally committed sales, but could be a boon if you have a
steady demand of a certain crop (for bigger farms… institutions like schools or hospitals). CSA is
based on past years' data on what customers preferred and didn't, but also based on what you can
pawn off on them while still providing value (…giving them something they didn't know they wanted,
but makes sense for you to grow is a great way to provide value both ways and **this is the
diversity piece**)." *(User flagged limited direct experience here.)*

**3. Not worth it.** "Direct relationships with retails have usually not been worth it for me.
Sometimes niche novelty works out for a one time sale, but reliable week to week sales it's hard to
compete with prices of large purveyors that use cheap labor and large scale production methods."

**4. The pad.** "The 'extra' usually comes from a great harvest from weather variables. One year my
onions and arugula grew insanely well and I was fighting to find outlets and the next year they
didn't. This usually comes with changes in pricing etc, but maybe is too much to try to predict for
a model like this."

**5. A Wednesday in July.** "For us, the farm store got short listed, because it had the
lowest/least reliable demand. The channel could change, but the logic probably doesn't for others.
**You send the produce to the place where there is the most at stake.** A contract or CSA renewal,
or restaurant quality, or buyer relationship."

**6. When the money lands.** "For wholesale, terms should typically be a month and markets or your
own store is immediate. CSA is the most funky because it's based on presales which is actually the
point… you should be giving a discount for the quality/quantity because people are paying upfront
and provides you the credit/cash flow to get by the early season months."

**7. Advisor test.** "Buy or make questions are critical (resale from other farm, transplants vs.
growing seedlings, infrastructure purchases, renting land). Cost cutting is also very important…
where can we save money? What has the best margins and how can we sell more of it (which channels
are doing well and how can we move more there). And biggest is just **what should I plant because I
need to start planning now**."

**8. What only the farmer knows.** "Every plot has different soil health, pest pressure, flood
pressure, sunlight, and a million other variables… This model is plot agnostic so it leaves that up
to the farmer (it would require mapping to model which would be a whole other app in and of
itself), but this is a critical piece the farmer is always thinking about."

---

## THE DIFF

### The headline: the app inverts the planning process

**Farmer:** obligations first — they "absorb the big blocks" — *then* optimise the leftover for
money. **App:** optimise the entire farm for money, with demand as *ceilings* the optimiser may
ignore. There is no "must plant" primitive anywhere in the model.

This single inversion explains a cluster of symptoms we have been treating separately:
- demand caps feel like the wrong object — they are ceilings where the farmer's first pass is
  **floors**;
- the What-If land swings (and the margin-hurdle crutch built to damp them) happen because nothing
  anchors the plan — in reality the big blocks are pinned before optimisation starts;
- `crop_diversity_max` is overloaded because it is the only available proxy for "I must be able to
  fill a box / a stall every week";
- the near-optimal-alternatives decision is really about the *remainder*, not the whole farm.

**It is fixable without a rewrite.** The machinery exists (`min_acreage_if_planted` is already a
per-succession floor; C6 already indexes crop×channel×week). Obligations = committed plantings
and/or committed weekly deliveries entered as floors; the optimiser then does what the farmer
actually does second. This is the "tweak direction, not reroute" change.

### Missing primitives, ranked by leverage

1. **Obligations / must-plant floors** (prompt 1). The first thing on the page; absent from the app.
2. **Allocation by STAKE, not margin** (prompt 5). "Send it where the most is at stake" — contract,
   CSA renewal, restaurant quality, buyer relationship. The model allocates every scarce pound by
   price. A per-channel stake/priority ranking, distinct from price, is a small addition with a
   large behavioural effect, and it is the farmer's *stated* rule.
3. **Payment terms per channel** (prompt 6). Wholesale ~net-30, market/store immediate, CSA
   **prepaid before the season**. Revenue currently books the week of sale, so C13's cash floor and
   the interest line — machinery that already exists — are being fed fiction.
4. **CSA as a financing instrument, not a channel** (prompt 6). Prepayment "is actually the point":
   it funds early-season months, and the discount is a *rational trade of margin for capital*. The
   model sees only a low price and will under-weight it. This is the clearest case where the app
   would give actively bad advice.
5. **Weekly variety requirement** (prompt 2). The CSA box needs N distinct items each week — that
   is what diversity means operationally; the acreage-fraction cap is a poor proxy for it. Also the
   "pawn off / provide value" insight: variety is a two-way value creator, not a constraint to
   minimise.
6. **Channel formality spectrum** (prompt 2). Informal restaurant ↔ committed wholesale ↔ CSA
   subscription. One demand object cannot express commitment strength, which is what decides both
   floors (2) and consequences.
7. **Sustained-vs-one-off channel viability** (prompt 3). Niche novelty works once; week-to-week
   direct retail loses to purveyors on price. Steady-state weekly caps cannot say this.
8. **Buy-vs-make decisions** (prompt 7) — resale from other farms, transplants vs. own seedlings,
   infrastructure purchase, land rent. These are the questions the advisor is *for*, and the app
   currently treats each as a fixed input.
9. **Channel growth advice** (prompt 7) — "which channels are doing well and how can I move more
   there." The app ranks crops, never outlets.
10. **Past-year sales as the demand basis** (prompts 1, 2). The uploader exists; demand is still
    entered as caps rather than derived from history.
11. **Perennials / carry-overs** (prompt 1) — plus garlic and June-bearing strawberries from the
    agronomy side. The cyclic single year cannot hold them.
12. **Infrastructure-driven crop requirements** (prompt 1) — "infrastructure we have that requires
    certain crops." A greenhouse pins crops; the model has capacity but no such coupling.

### My hypothesis that the one-pager REFUTED

I proposed that `sell_through_fraction` passively encodes deliberate overplanting-as-insurance.
**Wrong** (prompt 4): the surplus comes from **weather-driven yield variance**, not a planned pad —
"one year my onions and arugula grew insanely well and I was fighting to find outlets." Two
consequences: the Monte Carlo yield-variance feature is aimed at the right thing, and the real
unmet need is **glut handling** (where does surplus go, and prices move with it) rather than a pad
parameter. User's own judgement: predicting the weather side is "too much for a model like this" —
so the target is the *response*, not the forecast.

### Arbitrary — the app asks, the page never mentions

Per-phase water/fert/fuel per acre per week; `lbs_per_tote`; `crop_diversity_max` as a tunable
number; `days_to_maturity` as a user-facing scalar; most of the ~300 controls. Note this does NOT
mean the values are unimportant (a vacuous water constraint is still a defect) — it means they
should be *derived and disclosed*, never *asked*.

### Confirmed boundaries (non-goals, now with the user's own reasoning)

- **Plot-agnostic** — soil health, pest and flood pressure, sunlight vary per plot and are "a
  critical piece the farmer is always thinking about", but modelling it "would require mapping…
  a whole other app". Accepted boundary, and it argues for *disclosing* the assumption rather than
  approximating it. (Also validates keeping rotation out of scope; `crop_family` stays a label.)
- **Weather/yield prediction** — out (prompt 4).

### Output contract (prompt 7), against what the app delivers today

| The farmer wants | Today |
|---|---|
| **What should I plant — I need to start planning now** | ✅ the app's core competence |
| Buy or make: transplants vs seedlings, resale, infrastructure, land rent | ❌ all fixed inputs |
| Where can I cut cost | 🟡 bottlenecks and cost lines exist; no "here is your saving" |
| Which channels are working, and how do I move more there | ❌ crops are ranked; outlets never |

**Acceptance test for any future results screen:** it must answer #1 *and* speak to the other
three, in the farmer's order — obligations before optimisation.

## Status

- Phase A of SPEC_agronomy proceeds in parallel (shape-agnostic plumbing).
- SPEC_agronomy Phases B–D and the D3 holding-cost build are HELD until the diff exists.
