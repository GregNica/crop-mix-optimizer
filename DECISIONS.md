# Open Decisions — what needs the grower's call, and what hinges on each

**Purpose.** `BACKLOG.md` is the single list of WORK. This file is the list of **DECISIONS** —
the subset of that work which cannot proceed until a human chooses, plus the decisions that were
already made and never executed. Written 2026-07-31 for a deep-model audit of the plan.

**How to read an entry.** Each carries: the question in one sentence, why it is open, the
*evidence* (measured numbers where they exist — estimates are labelled), the options with their
consequences, a recommendation, and what it blocks. Recommendations are mine and are the thing
the audit should attack hardest.

**State of the build.** Branch `feat/server-llm-expansion`, 399 pytest + 9 node harnesses green,
blob and golden payload in sync, browser-QA'd by the grower today. The labour money path
(W9/W12/W14/W15/W16 + the 2026-07-31 adversarial review and its fix arc) is closed and heavily
guarded. Golden farm: revenue $2,134,530, profit $428,547, **net margin 20.1%**.

**A standing note on M1 (the net-margin problem).** Real diversified-veg net margin is 5–15%; the
model says 20.1%. The grower's position, 2026-07-31, is **not to chase M1 directly** — the
reasoning being that fixing the other pieces may resolve it as a side effect. The evidence
supports that: of the five fixes that moved margin, the four that moved it the WRONG way were all
reporting fixes aimed at margin-adjacent code, and the one that moved it right (W12, −16.8 points)
was aimed at correctness elsewhere. Several decisions below (B1, B2, B3, B5) each move M1 as a
by-product. **Sizing caution:** my rough estimate is that the named uncharged costs total 1–3
points, not the ~5 needed, so if M1 is the target the revenue side (crop prices and yields, never
audited — Tier 2 M2/M3) probably holds the rest. That estimate is not measured.

---

## GROUP A — Blocking work right now

### A1 · U1 — What does the base plan assume about hiring, and where do its controls live?

**Question.** Should the main Optimize be allowed to buy labour, or is hiring always a separate
What-If?

**Why open.** The "Labor flexibility assumptions" toggle sits in the setup form, but the main
payload builder never sends `labor_flex_enabled` — so a normal Optimize always solves with fixed
staff no matter how the toggle is set. That is deliberate and documented. The grower's ruling
after browser QA: *"confusing and redundant… we need a better way to communicate this and select
it in the UI."* So the current arrangement is rejected; what replaces it is undecided.

**Evidence (verified 2026-07-31).** `labor_flex_enabled` appears in `public/index.html` at the
form control (~1598), the adapter (~7301), the What-If builder `buildLaborFlexParams` (~10165) and
the result forwarding (~7672) — **and nowhere in the main payload builder.** Related dead code:
the exec-summary "Bought Labor (optimized)" block (~6907) is gated on `res.labor_flex_enabled`,
which is never true on the path that renders it, so that block is unreachable.

**Options.**
- **(a) Main payload sends it.** The toggle means what it looks like. ⚠️ Consequence: the headline
  plan becomes "what I'd do if I could hire" — the headline profit changes, and the plan is no
  longer executable with the crew the grower listed.
- **(b) Delete it from setup; the What-If owns hiring entirely.** The cost inputs (cap, markup,
  wage) move into the What-If panel where they are actually consumed. Nothing is lost — the main
  solve never read them. Setup gets shorter.
- **(c) Keep both, but make the split a visible choice** — e.g. a two-state control at the top of
  Results: "Plan with my current crew" / "Let the plan hire". Costs a design.

**Recommendation: (b).** The base plan should be executable with the crew you actually listed, and
(b) is the only option that removes the say-do gap without moving the headline number. But this is
genuinely a product decision about what the headline plan *means*, which is why it is here.

**Blocks.** U1a (validation gating — do not close it by making a typed value silently ignored;
that was the W15 defect), U2 (below), the dead exec-summary block, and the labour half of C7.

**Cost / reversibility.** (b) is small and reversible — DOM moves, no solver change.

---

### A2 · U2 — Wording for the two labour levers

**Question.** Approve or redraft the relabelling of "Optimize labor" and "Labor Availability" as
hiring decisions.

**Why open.** Agreed in principle already; needs sign-off on words. The mechanism is right and the
framing is wrong — the two levers give opposite-signed answers and nothing on screen says why.

**Evidence (measured by the grower).** "Optimize labor" (10 extra workers, weeks 9–50) → **+$110K
profit**. "Labor availability +40%" → **−$167K**. Both correct: the first lets the solver *buy*
hours and it only buys an hour that pays for itself (an option you can decline is worth ≥ 0); the
second scales your **crew count**, a commitment you owe whether it is used or not (+40% of a ~$736K
bill ≈ +$295K of payroll against ~$127K of extra margin).

**Proposed wording.** *"Optimize labor buys hours that pay for themselves."* /
*"Labor availability hires people whether they pay for themselves or not."*

**Recommendation.** Ship those two sentences with U1's redesign, not before — the same panel is
being rebuilt.

---

### A3 · W17 — Stop inferring a market wage from your own payroll?

**Question.** When the hired-wage box is blank, what should the model do?

**Why open.** Three inference rules have shipped, each fixing the previous one's tail, and **all
three are the same category error: a statistic about the farm's own payroll is not a market
price.**

**Evidence.**
1. Average over all paid hours → dragged up by salaried staff; a manager-only farm priced a hired
   field hand at **$40.60/hr**.
2. Unweighted `min` over listed roles → dragged down to the least representative role; a single
   2 h/wk helper at $12 would price all 20,800 potential hired hours. ⚠️ This reversed the error
   into the **unsafe** direction — over-pricing merely refuses good hires, under-pricing makes the
   optimizer buy help the grower cannot actually get.
3. Current: hours-weighted over PAID hourly roles. The shipped test expects **$25.33** from one $40
   tractor operator plus two $18 field hands (`tests/test_committed_wages.py:334`) — a grower hiring
   a field hand pays $18. ⚠️ The all-salaried farm still reproduces defect (1) exactly: no hourly
   role means the fallback is the salaried average, so a $52k manager prices a hired field hand at
   $25.00/hr.

**New since this was tabled.** The app now **prints the number** — the What-If footer shows
"~$25.71/hr all-in" on the demo farm against your own harvest crew at $19 + 25% load = $23.75. You
can now see the inference and judge it, which you could not before.

**Options.**
- **(a) Prefill the field with a defensible regional default, label it "estimate — correct this",
  make blank impossible.** No hidden inference; the grower owns the number. Needs a sourced default
  (same treatment as the other benchmark defaults, with provenance).
- **(b) Keep blank-means-infer, but weight only SEASONAL/field roles** — the ones structurally
  comparable to a hire. Better statistic, same category error, cheapest.
- **(c) Require the field.** Honest, adds friction to the What-If.

**Recommendation: (a).** It is the only option that stops the model from asserting a market price
it cannot know. (b) is a reasonable interim if (a)'s default cannot be sourced defensibly.

**Cost.** Small-to-medium; the work is finding a defensible default, not wiring it.

---

## GROUP B — What the model charges, and what its knobs mean

### B1 · W10 — Is on-farm irrigation water free at the margin?

**Question.** Should pumping your own water cost the plan anything per litre?

**Evidence (verified 2026-07-31).** `well_cost_per_L` is a real solver parameter (default `0.0`,
`farm_v2/solver.py:265`) and is charged into the water cost (`:605`) — but **there is no form field
for it anywhere in the app**; the only occurrence in `index.html` is inside the generated solver
blob. So `variable_cost_split.water` is structurally **$0.00 on every farm**, and the P&L carries a
$0.00 line that looks like a bug.

**The subtlety.** The locked cost-accounting basis already routes pump **energy** to overhead. If
you also charge per litre, you double-count.

**Options.**
- **(a) It genuinely is free at the margin** (you own the well; the energy is in overhead) → keep
  $0 and make the label state the reason rather than implying a measurement.
- **(b) Add a pumping-cost input** and remove pump energy from overhead to avoid the double-count.

**Recommendation: (a)** unless you meter pumping separately and want it visible per crop.

**Cost.** Trivial either way. Worth closing just to remove a line that reads as broken.

---

### B2 · R1 — Crop protection: add the category, and at what granularity?

**Question.** Herbicide/insecticide/fungicide have no cost field while fertiliser does. Add one,
and is it per-crop or farm-wide?

**Evidence.** NASS 2022 Ag Chemical Use (22 crops, 17 states). ⚠️ The commonly cited ">90% of
farms" figure is **unsupported for any single class** — the max is 82% of planted acres for one
class. **The real finding is the variance: which class dominates flips by crop** (squash is
fungicide-led at 69%, sweet corn herbicide-led at 82%). That argues for a **per-crop cost like
fertiliser**, not a farm-wide rate or an overhead line.

**Options.** (a) per-crop $/acre category — mirrors fertiliser, and after W4's refactor a sixth
variable-cost category is one edit; (b) farm-wide rate; (c) fold into overhead %; (d) don't model,
disclose the omission.

**Recommendation: (a).** Note the mechanism is cheap and **the per-crop default values are the
actual work** — that is agronomy (M2/M3), not plumbing.

**Moves M1** in the right direction (a real cost currently charged at zero).

---

### B3 · R2 — Insurance

**Question.** Crop / liability / equipment insurance is not modelled at all. Add a farm-level fixed
cost, fold into overhead, or disclose?

**Evidence.** Historically low on small farms but rising; the USDA Micro Farm Program now covers
diversified revenue to $350k. Interacts with the deterministic-yield gap — the model has no crop
failure, so insurance has nothing to insure against inside the model.

**Recommendation.** A single farm-level fixed-cost field, or an explicit line in the overhead
definition. Cheap. **Moves M1** the right way.

---

### B4 · W5 — What does `crop_diversity_max` promise?

**Question.** The knob is an acre-**weeks** share, but "0.60" reads as "at most 60% of my farm in
garlic". It actually permits **100% of the farm in garlic for 31 weeks**.

**Options.** (a) relabel with a worked example; (b) rescale it to a true land share; (c) both.

**Recommendation.** Decide what you want it to *mean* first — (b) changes plans, (a) does not. This
is a decision about the promise, not the code.

---

### B5 · M9 — The volume basis

**Question.** `crop_size_m3_per_lb = TOTE_M3 / lbs_per_tote`, where `lbs_per_tote` is an **ergonomic
lift weight, not a density**. Two prior audits disagree on the direction of the error.

**Why it matters.** It sets storage occupancy, so it feeds the cold/ambient capacity constraints —
it can change the plan, not just a report.

**Recommendation.** This needs a **measurement**, not an opinion: weigh and measure a filled tote
for two or three representative crops. Until then any "fix" is a coin flip between two audits.
**Moves M1** in an unknown direction.

---

### B6 · W13 — The margin hurdle

**Question.** `min_viable_margin_pct` drops crop-channels **before the solve**, using a per-crop
labour cost the objective no longer charges (W12 made wages committed). Keep, replace, or delete?

**Evidence (verified).** Default is `0` = off (`index.html:1414`), so this is **latent, not
shipping**. On the demo farm nothing scores below ~22%, so any single-digit floor is now a no-op.

**Options** (recorded previously): (a) delete it; (b) replace with an explicit per-channel "exclude"
checkbox; (c) rebase it on per-lb contribution.

**Recommendation: (a) or (b).** A hurdle that drops channels before the solve using a *different*
cost model than the solver is the app disagreeing with its own optimizer — and using the
disagreement to change the plan. If it stays, it must read the solver's own margin.

---

## GROUP C — Product shape

### C1 · W7 — The hidden constraint panel: surface or delete?

**Evidence (verified).** `#constraint-summary-card` is hardcoded `style="display:none"`
(`index.html:1930`) and no code path ever unhides it; an in-page test asserts it stays hidden. So
~200 lines of money-adjacent rendering run on **every solve, including all 100 Monte Carlo draws**,
into a card nobody can see.

**Interactions.** The Market Demand Satisfaction table inside it is the natural home for **C2** (the
contract commitment schedule, deliverable D4). The standing interface direction says *don't build
UI panels* — which argues for delete-and-let-the-assistant-render.

**Options.** (a) surface it; (b) delete it, and let C2 build its own surface; (c) delete it and
render through the assistant.

**Recommendation.** (b) or (c). The numbers behind it are correct now (W6), so nothing is lost by
deleting the view.

---

### C2 · P13 + R6 — Rent vs buy, per asset

**Question.** Every asset is modelled as owned. Should a farm be able to say it leases its cooler,
rents equipment, or crops rented ground?

**Evidence.** Depreciation shipped (6 assets, each with capital cost + life). The rent/buy half
never started; there is one weekly Property Mortgage/Rent field for land and nothing else.
**28% of US farms operate partly or entirely on rented land; 39% of all acres are leased**
(AFBF/ERS on the 2022 Census). The grower has raised this twice.

**Options.** (a) per-asset own/rent toggle; (b) leave as is and document; (c) fold into C3's general
mechanism below.

**Recommendation.** Decide C3 first — if the general mechanism is built, this comes with it.

---

### C3 · R3 / R4 / R5 — One mechanism, or five features? ⭐ the biggest structural call here

**Question.** An independent research pass confirmed the **(crop × operation × cost basis)**
hypothesis — contract labour and short-term equipment rental both came back tagged that shape,
unprompted. Building that ONE mechanism would collapse **M4, M5, M6, P8 and P13** into it.

**What is unexpressible today.**
- **R4 — contract/custom work priced per unit** (per acre, bin, carton, ton). Labour is hours × wage
  only. **195,000 US farms report contract-labour expense against 437,000 reporting hired labour**
  — ~45% of farms that employ anyone also buy labour by contract. Not a specialty case.
  ⚠️ `piece_rate_per_lb` already exists on seasonal employees, is computed into `piece_rate_workers`,
  and is **read by nothing** — piece rate *looks* supported and is inert.
- **R5 — U-pick / customer-harvest channels** should zero `labor_harv` for the volume sold that way.
  Harvest labour is currently a crop attribute charged on all volume regardless of destination.
  This is the per-channel cost-to-serve primitive.

**Options.** (a) commit to the general mechanism; (b) keep bolting on individual features;
(c) defer both and document the gaps.

**Recommendation: (a), but not immediately** — it is the highest-leverage structural bet on this
list and it wants a spec of its own. Worth the audit's attention specifically.

---

### C4 · W2 / W3 — Monte Carlo has perfect foresight

**Question.** Monte Carlo **re-optimizes the crop mix on every draw**, then presents the result as a
"1-in-10 bad year planning floor". That is a plan that knew the weather in advance.

**Consequence.** W3 ("crop plan stability" labelling crops Fragile by selection frequency) is an
artifact of this, not a risk measure.

**Fix shape.** Freeze `x`/`y`, re-evaluate under each draw, let only sales allocation re-optimize.
The gap between the two modes is itself worth reporting — it *is* the value of perfect foresight.

**Recommendation.** Do it before shipping any risk claim (deliverables D6/D7 depend on it).

---

### C5 · Which deliverables next?

**Evidence.** Of the grower's 10 ranked deliverables, **7 are reporting problems** — the solver
computes the data and discards it: yield projection by week (C6), labor calendar (C7 —
`capacity_series.labor {used, cap}`, `hired_hours_weekly`, `overtime_hours_weekly` all exist with no
view), contract commitment schedule (C2 — now on W1's honest per-channel numbers), season plan table
(C1), benchmark deviation (C8 — `CROP_PROVENANCE` renders nowhere).

**Blocked on modelling, not reporting:** the seeding calendar (D2) needs `planting_type` wired —
**M4**, it is carried on every template and dropped before the math; seed ordering (D5) needs a
seeding rate or plant density — **M7**, the model has cost per acre but never quantity.

**Competitive note.** D1/D2/D5/D9 are **table stakes competitors already ship** (VeggieCropper
calculates seeds, bed spacing and seeding dates). D3/D6/D7/D8/D10 are category-of-one — no
competitor decides what to plant.

**Decision.** Pick the next 2–3. My order would be **C7 (labor calendar) → C2 (commitment schedule)
→ C6 (yield series)**: all three are views over data that already exists and reconciles.

---

### C6 · ⚠️ Near-optimal alternative plans — DECIDED, NEVER BUILT, NOT IN THE BACKLOG

**Status.** Decided 2026-07-27: summarise close-profit alternative plans and let the grower choose;
build the Python side, defer the UI. It replaces the margin-hurdle crutch honestly. **It was never
built and it is not in `BACKLOG.md`** — it exists only in session memory.

**Why this is flagged as a decision.** A decided item that fell out of the list is exactly how Phase
B came to look finished while B4–B8 were open. Either put it in the backlog or retire it explicitly.

---

## GROUP D — Structural and process

### D1 · E2 — Extract `run_from_js` from the HTML template literal?

**Evidence.** ~340 lines of money-affecting Python live inside a JS template literal in
`index.html`, testable only by regex-extracting them from a string. Today alone: the adapter
produced two of the defects the review caught (a dropped `gap_note`, and `_num` inventing capacity
defaults), and a **backtick inside a Python comment terminated the literal and broke the page** —
a class of failure that cannot exist once the file is a file. It is also on the critical path for
the server/LLM work this branch is named after: a second adapter author is the exact scenario that
made the payroll-load relocation urgent.

**Options.** (a) now; (b) when the server work starts; (c) never.

**Recommendation: (a) or (b), and say which.** This is cheap insurance on the path we are already
committed to.

---

### D2 · E1 — The in-page test suite

**Evidence.** A 3,425-line console-assert function — **25% of `index.html`** — ships to every user,
never runs automatically, prints "All what-if tests passed" unconditionally, **crashes with a
ReferenceError**, leaves the remaining blocks dead, and corrupts live app state on crash. Measured
in a real browser (Chromium + Pyodide): **18 assertion failures on a fresh load, 25 after a solve.**

**Options.** (a) delete it; (b) port the blocks that carry real coverage into jsdom harnesses and
delete the rest; (c) fix in place.

**Recommendation: (b).** We are already doing this incrementally — there are 9 `.cjs` harnesses now,
and each new guard has gone there rather than in-page. This just finishes it.

---

### D3 · E5 — The field registry

**Evidence.** Three partial registries keyed by form-field id (`DATA_F_REGISTRY` units,
`CROP_PROVENANCE` sources, `CHATBOT_FIELDS` chat descriptions) that overlap and will drift.
`FORM_STATE_VERSION` is stamped but **never read**, and `applyFormState` silently skips ids it
cannot find — so any markup rename **silently drops fields from saved plans**. The backlog says this
"must precede any UI overhaul".

**Decision.** Do it before U1's redesign, or accept the drift and the silent-drop risk knowingly.

---

## GROUP E — Deferred, but should be explicit

### E1 · G4 — The privacy promise is currently false

**Evidence.** The hub says *"All calculations run in your browser. No data is sent anywhere."* The
assistant POSTs the **entire form state** — farm size, cash, credit line, wages, prices — to a
third-party LLM, and plans persist to Neon.

**Recommendation.** Fix the copy **now**. It is a statement about user data, it costs nothing to
correct, and it is the one Tier 7 item that is wrong even with a single user (you).

---

### E2 · X2 — Who sees this, and when?

**Status.** Deferred twice. The grower has said to work at a flexible pace and not prioritise by
when someone will see it — so Phase G (account allowlist, rate limiting on `/api/chat`, Origin/CSRF,
scenario-identity races) stays parked.

**The decision to make explicit.** That parking is correct **only while nobody else has the URL**.
Google sign-in currently has no allowlist, domain restriction, or invite table — "private pilot"
today means anyone with a Google account who finds the URL. Confirm that holds, or pull Tier 7
forward.

---

## Where I would point the audit hardest

1. **C3 (one mechanism vs five features)** — the highest-leverage structural bet, and the one I am
   least able to size alone.
2. **A1 (what the base plan assumes about hiring)** — my recommendation (b) is a product judgement
   about what the headline number means, and reasonable people could pick (c).
3. **The M1 sizing estimate** in the header — I claim the uncharged costs are worth 1–3 points and
   the rest is on the revenue side. That is an estimate, not a measurement, and if it is wrong the
   whole "don't chase M1 directly" posture should be re-examined.
4. **B5 (volume basis)** — two prior audits disagree; a third opinion without a physical measurement
   adds nothing, and the audit should say so rather than pick a side.

**Where I would NOT spend audit effort:** the labour money path (W9/W12/W15/W16 and today's fix arc)
— it has had `/simplify`, `/code-review`, an 8-lens adversarial review, a red-team pass and
mutation-verified guards within the last two days, and is the most-reviewed code in the repo.
