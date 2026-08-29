# Playbook: reviewing a solver-backed app for a non-coding stakeholder

**Give this to a fresh Claude Code session in the target project.** It encodes what worked —
and what went wrong — in a four-day review of a university course-scheduling MILP. The
domain examples are scheduling; the process is general to any app with a solver
(optimisation, routing, allocation, matching, rostering, pricing).

**The goal is not "audit the code".** It is: *the people who own this app can no longer
explain how it works, and need to be able to reason about it well enough to give
direction.* You are producing three things:

1. A **written review** — problems, a proposal, and the decisions being asked for.
2. An **HTML walkthrough** the stakeholder reads.
3. A **runnable spreadsheet toy** they can open in Excel and solve themselves.

The spreadsheet is not a garnish. It is the only artefact that lets a non-coder *test*
your claims rather than take them on trust, and it will catch your errors — it caught
several of mine.

---

## Phase 0 — Establish the frame before touching anything

- **Ask what the stakeholder already understands.** Mine understood Excel Solver well
  (objective, decision cells, constraints) and no code at all. That single fact determined
  every explanation choice downstream. Do not guess it.
- **Find the real complaint.** Not "is there a bug" but the sentence the stakeholder
  actually said. Mine was *"neither of us can explain how the solver works any more."*
  That is a claim about **legibility**, and it makes "this formulation is smaller" a
  non-answer unless it is also *simpler to reason about*.
- **Ask what they are willing to trade.** Mine said explicitly: *a larger model is fine if
  it is simpler.* I then spent a day optimising variable count anyway and had to be pulled
  back. Write their stated preference down and check your recommendations against it.

---

## Phase 1 — Read the model back to source

Produce a factual map before any opinion:

- **Count variables by family.** Not "the model is big" — *"11,928 of 13,333 variables are
  one soft term."* That single number reframed the whole review.
- **Read every objective weight and compare them to each other.** Look for terms that
  cannot win: mine priced a four-hour gap at 1.0 against a room preference at 4.0. A soft
  term cheaper than the solver's optimality gap is decoration.
- **Check the optimality gap against the smallest meaningful term.** If the solve stops
  within 1% and 1% of the objective exceeds an entire soft term's value, that term can be
  discarded without the solver registering a loss. Easy to miss, easy to check.
- **Ask what the model literally cannot express.** This is where the structural findings
  are. Mine: the model was *told* which period a course ran in, so it could never decide
  *which weeks* — and an entire second subsystem (~1,000 lines) existed to work around
  that one gap.
- **Grep for special-case flags threading through the constraint builder.** Count them and
  name the files. A high count usually means one missing capability is being patched in
  many places — find the missing capability, not the patches.
- **Verify the app's own diagnostics.** Mine had a panel reporting "0 constraints" of a
  type that had simply been renamed, and a status line reporting a timeout after a 1.2s
  success. When the instruments lie, losing confidence in the solver is the *correct*
  reading of the evidence — say so.

---

## Phase 2 — Measure at the scope the app actually runs at. Do this EARLY.

**This is the single most expensive mistake I made.** I measured a small, clean slice
(11 courses) for days, built a proposal on it, and reached a confident conclusion that
**completely reversed** when I finally ran the real concurrent workload (83 courses). The
reversal came from a stakeholder question, not from me.

- **Find the real unit of work by reading the data, not the code.** I assumed programs
  could be solved independently; the stakeholder pointed out that shared staff and shared
  rooms mean everything overlapping in time must solve together. One query over date
  ranges would have told me that on day one.
- **Small models are TIGHT; large ones are LOOSE.** A technique that finds nothing to
  improve on a 5-item toy can transform a 100-item real instance, and a technique that
  proves optimality in 1.4s at small scale can return *nothing at all* at real scale.
  Neither direction is predictable from the other.
- **Always report: variables, wall-clock, whether optimality was PROVED, and the quality
  metric.** "Fast" without "proved" is not a result. Some of my early numbers were
  proved-optimal on a measure that turned out to be the wrong measure.

---

## Phase 3 — Separate "the model is wrong" from "the data cannot say it"

**My largest practical finding was not a modelling problem at all.** A third of the
timetable would not solve. The causes:

- ~70% — a parameter typed per-category that was wrong for one context (a cadence assumed
  constant across term types). Fixed by deriving it instead of typing it.
- ~25% — **a feature that was fully implemented in the solver and switched off by an empty
  database column**, because no UI could set it. Correct code, correct comments, NULL on
  every row. Seven items unplaceable for want of a form field.
- ~5% — a genuine conflict, i.e. the thing the app exists to surface.

**Before concluding the model is at fault, check:** are the inputs expressible? Is there a
capability implemented but unreachable? Run a **pre-solve feasibility check** — required
resource vs available resource, pure arithmetic, milliseconds — and you will often find
the answer without a solver at all.

**Caveat that bit me:** make that check aware of the domain's exemptions. Mine counted
mutually-exclusive alternatives as if they were concurrent and reported 188% over capacity,
which would have sent people chasing a curriculum problem that did not exist.

---

## Phase 4 — Build the spreadsheet toy

**Hard limits (Excel Solver):** 200 decision cells, 100 constraints, and **everything must
be on the active worksheet** — objective, decision cells and constraints. Splitting them
across tabs makes Solver unusable; other tabs may hold inputs only. I shipped two
unusable versions before learning this.

**Simplex LP rejects non-linearity.** `MAX`, `MIN`, `IF` and products of decision-dependent
cells are all non-linear. My toy computed a quantity with `MAX()` and a triple product, fed
it to the objective, and Solver refused the model. **Constant subtrees are fine** —
`ROUNDUP`/`INDEX` that never depend on a decision cell will not break linearity — so verify
by testing *decision-dependence*, not by text-matching function names.

That failure became the best teaching moment in the document: *a linear solver has no MAX*
is exactly why the real app cannot search for that quantity either. **When the spreadsheet
cannot express something, that is usually a finding, not an obstacle.**

**Make both sides of the objective share a basis.** Mine scored one quantity once per
period and another once per week; over a four-week term that is a 4× thumb on the scale,
and the smallest possible weight already flipped the answer — the setting was a switch, not
a dial. The stakeholder caught it. Check: does each objective term answer "per what?" the
same way?

**The toy must demonstrate a trade-off, not just contain the mechanism.** Ship it so the
reader solves it, sees a specific undesirable outcome, changes one labelled cell, re-solves,
and watches the outcome change. Tell them the expected numbers so they know it worked.

**Include a case where the mechanism visibly fails without its input.** My strongest single
demonstration: two items ship correctly tagged and both fit; clear the tag, re-solve, and
one becomes unplaceable. That is the production bug in miniature, in two cells.

**Dump and read the generated formulas.** I shipped a workbook where every constraint of
one whole family was silently vacuous — it grouped on the wrong column, so the test was
never true — while the document claimed that family was doing important work. Verify a
constraint references what its label says.

**Keep a code twin.** I solved the same toy model in JS with a real MILP library. Whenever
the spreadsheet and the twin disagreed, one of them was wrong, and finding out which caught
several errors before delivery.

---

## Phase 5 — Write the document

**Structure it as problem → what's broken → proposal → how it works → what to do.** Not as
a narrative of your investigation. My first draft was ordered by the sequence in which I
learned things; the stakeholder correctly called it "messy and hard to follow" and said
sections read as thought-process. Cutting to that structure removed ~20% of the words and
lost nothing.

**Put the decisions at the very top, enumerated, each with: a recommendation, what it
depends on, and what it blocks.** "This asks for one decision" was wrong in my case —
there were five, including one I could not answer myself. Enumerating them exposed that gap.

**Lead with the finding that needs no decision.** Mine had an actionable data fix that
someone could do that week, independent of the whole design argument. It was ninth in the
draft. It should be second.

**State plainly what your prototype does NOT carry.** Mine omitted several real features.
Saying so up front is the difference between a reviewer trusting the rest and discovering
the gap themselves. Frame headline comparisons narrowly: *the parts I reimplemented got
easier; the parts I did not are the open risk.*

**Every hole you name must get an answer.** My recommendations section fixed the data
problems and left one structural hole with no action item and another unmentioned. Include
a table mapping each problem → what closes it → whether it depends on the big decision.

**Reversals: keep the lesson, drop the diary.** I reversed twice on one recommendation.
The useful residue is a short rule ("two formulations permitting identical answers can
differ by 100× and you cannot see it by reading"), placed where it does work — as the
reason to *test* rather than trust. A section narrating my mistakes added length and no
decisions; it was cut.

---

## Phase 6 — Expect the stakeholder to find real errors

Mine caught, in order: an outdated version reference; a section that contradicted its own
conclusion; the Simplex LP failure; the units mismatch; a demonstration that demonstrated
nothing; and two sections that did not earn their place. **Every one was correct.**

When challenged, **go and measure rather than defend.** Two of those challenges reversed a
recommendation. If a challenge turns out to be mistaken, say so plainly with the evidence —
but check first.

---

## The traps, as a checklist

**Modelling**
- [ ] Two constraints permitting identical integer answers can differ enormously. `2z ≤ u + w`
      (one row) vs `z ≤ u` and `z ≤ w` (two rows): **no answer in 120s vs proved in 1.3s.**
      The compact form lets the fractional relaxation hold half-scheduled states, so nothing
      prunes. **Fewer rows is not a better model.**
- [ ] Any big-M or "large constant" switch is a red flag; expect a cliff a few items in.
- [ ] **If the objective can push a variable the wrong way, it needs BOTH bounds.** I omitted
      an upper bound on a helper variable reasoning "the objective pushes it down" — true for
      two of three variables, false for the one the rule subtracted. The solver then declared
      every slot occupied, owed no penalty, and reported a flawless result it had not found.
      **A whole round of measurements read "zero problems everywhere" and measured nothing.**
- [ ] **Index on the thing you actually mean.** I aggregated across a dimension (weeks) that
      mattered, which penalised interactions between items that never coexisted and let the
      model "prove" an optimum an independent count disagreed with.
- [ ] Check whether a soft term is worth less than the optimality gap.

**Measurement**
- [ ] **Score every result against something the model did not produce.** Three measurement
      errors here were caught only that way, and **the two that survived longest both looked
      like good news.** A model asked to grade its own homework will pass.
- [ ] Report proved-vs-unproved every time.
- [ ] Re-measure at real scope before concluding anything.

**Mechanical (these produced confident wrong statements more than once)**
- [ ] A string replace that matches nothing **returns success**. Assert the pattern exists,
      then verify the *effect* — rebuild and grep the output, or re-run the measurement and
      check the number moved. I once believed a no-op for two full runs and started blaming
      the data.
- [ ] `git commit --amend` takes only **staged** changes. Stage first, then check
      `git status` after.
- [ ] After editing a generated artefact's builder, rebuild and inspect the artefact.

---

## Suggested opening prompt for the new session

> Review the solver in this app. I understand Excel Solver but not code. Produce three
> things: a written review, an HTML walkthrough, and a runnable Excel toy model I can solve
> myself.
>
> Before proposing anything: map the model (variables by family, every objective weight,
> what it cannot express), then measure at the scope the app actually runs at in production —
> find that scope from the data, not from assumptions. Separate "the model is wrong" from
> "the inputs cannot say it"; check for capabilities implemented in code but unreachable
> through the UI or empty in the database.
>
> Keep the Excel model under 200 decision cells and 100 constraints, all on one sheet, and
> linear enough for Simplex LP. Make it demonstrate a trade-off I can change and re-solve.
> State plainly what your prototype does not carry. Put the decisions you need from me at
> the top of the write-up, each with a recommendation and what it depends on.
