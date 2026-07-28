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

## Answers

*(pending — paste the one-pager here verbatim when it arrives, then write the diff below it)*

## Status

- Phase A of SPEC_agronomy proceeds in parallel (shape-agnostic plumbing).
- SPEC_agronomy Phases B–D and the D3 holding-cost build are HELD until the diff exists.
