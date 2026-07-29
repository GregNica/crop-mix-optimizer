# SPEC_agronomy — does the app farm like a farm?

**v2, 2026-07-28** — rewritten after three-agent review (adversarial / domain / execution). v1's
framing ("fix the shelf-life numbers") was too narrow and its delivery path was refuted: it wrote
52-week shelf lives into a store whose exits clamped at 8 and whose template loader dropped the
field. The clamps and loader are fixed and pinned (`3456c7d`); the scope is now stated properly.

**Scope: the crop data layer AND the agronomic logic it encodes, at three layers:**
1. **Values** — is the number right (yield, DTM, water, fert, labor, seed cost, shelf life)?
2. **Semantics** — does each field *mean* what farming means by it? (DTM vs field occupancy;
   season windows as planting-windows vs whole-cycle containment; even-split harvest; harvest
   weeks for a tomato vs a garlic; succession independence; overwintering.)
3. **Emergent behavior** — does the solved plan farm like a farm? (Garlic stacking was a layer-3
   symptom of a layer-2 defect wearing a layer-1 costume.)

Solver structure, UX, server work stay in the July plan (`~/.claude/plans/eager-petting-hare.md`).
The July audit reviewed the machine and *praised* the provenance system without opening the cited
documents; two citations have since failed. This audit opens the documents.

**Why now:** B.3's strict shelf-life semantics landed ahead of data (golden −7.8%, regression
fixture −55.6%); recovery is concentrated in ~8 storables, and the barn (`cold_storage` + ambient
pool) exists. Review also surfaced two live layer-1 disasters: **the water constraint is vacuous**
(crop rates ~8–10× low, so the 65% rainfall offset zeroes net irrigation everywhere — verified)
and **fertilizer quantities are ~20–50× low** (~$5/ac where budgets say $200–600) — the first
finding with headroom to push the 39% net margin *down*.

---

## Ruling 0 — one source of truth (user) — amended for executability

| Store | Disposition |
|---|---|
| `CROP_TEMPLATES` (29 crops + placeholder) | **CANONICAL.** All research lands here. |
| `CROP_DEFAULTS` (7) | Derived: `DEMO_CROPS.map(n => tpl(n)) ∘ OVERRIDES`. **Phase A ships a COMPLETE override map making the derived demo byte-identical to today** (golden untouched; truly mechanical). Phase C burns overrides to empty one adjudication at a time, re-pinning per batch. "Empty" is the *end state*. Note: 3 of the 5+1 divergences are **schema-shape** (annual vs weekly demand types), not value tweaks. |
| Python `CROPS` fallback (adapter, index.html ~6570/7039) | **DELETE; `crops` required → ValueError** (caught by run_from_js's error envelope — loud, not a crash). **Extended (review):** the adapter's phantom `CHANNELS` fallback and the phantom **28-person crew** (~7017–7029) go the same way — on the server path a silently-staffed farm is worse than phantom crops. |
| `tests/conftest.py::full_crops` | Keep, exempt: frozen synthetic fixture, claims no provenance. |

**Guards (all three legs, or drift reopens):**
- Derivation guard **plus an override-map snapshot** — without the snapshot the guard is true by
  construction (the SPEC_v3 tautology class); any new override must be a reviewed diff.
- **Golden-payload leg:** nothing today ties `tests/golden/default_farm_payload.json` to the live
  page. Phase A adds a jsdom capture script + a guard asserting payload.crops == derived demo in
  solver shape. Rule: payload re-captured and dollars re-pinned in the SAME commit as any
  template/demo change ([[money-path-guards]]).
- Template-loader schema guard: `loadCropTemplate`'s set-list == template schema (the field it
  silently dropped for months is exactly how layer-1 fixes die in transit).

## Ruling 1 — what "verified" means

Per-crop provenance lives in a **new `CROP_PROVENANCE[crop][field] = {source, vintage,
confidence}`** parallel structure with its own completeness test. (v1 said "extend
BENCHMARK_DEFAULTS" — unimplementable: that registry is keyed by DOM element id and five consumers
assume it; crop fields have no ids. Leave it and its T30 pin alone.)
- **high** = we opened the document and the number is in it, checkable by a stranger.
- **medium** = derived from a checkable source by a *stated rule* (unit conversion, range midpoint,
  the labor crosswalk below).
- **estimate** = judgment, and says so.
**Model-generated values are never entered.** Models find candidate sources, run consistency
sweeps, and refute finished batches. Sourced *candidate* tables (Appendix) are worklists, not data.

## Per-field disposition — revised where review refuted v1

| Field | Rule |
|---|---|
| yield/acre | Research (extension budgets). **Basis must be stated: cured, trimmed, marketable weight** — garlic loses 15–25% field→cured; a field-weight yield overstates revenue on top of every other error. |
| DTM | **Schema change, not a convention note** — see Semantics ruling S1. Record `dtm_source` (published days-to-first-harvest, citable) and `field_occupancy_weeks` (what the solver actually consumes) separately. |
| planting windows | Research **after S2 settles what a window means**; windows are currently whole-cycle containment, and that mismatch — not bad data — is why 3 templates plant zero acres. |
| shelf life + cold flag | Research (AH-66 / UC postharvest). Appendix A worklist. Enter the **conservative** end while holding is free (see Open decision D3). |
| **water per phase** | **RESEARCH — HIGH.** FAO-56 crop coefficients (Kc ini/mid/end × zone ETo) *are* a per-phase split, published for every crop here. v1 sent this to "estimate," which would have badge-blessed a vacuous constraint. Do first among values. |
| **fert per phase** | **RESEARCH.** Extension N/P/K recs split by standard preplant/sidedress timing. Currently ~20–50× low. |
| labor per phase | Research the **season total** (published: Penn State, UMass, Rutgers, Iowa AgDM…) = high; allocate by **one documented operation→phase crosswalk** = medium; divide by phase weeks. "Estimate" only where no budget exists. |
| fuel per phase | Estimate-labeled (the one array currently in the right order of magnitude). |
| seed/transplant $/ac | Research. **Systemic, not just garlic:** every transplanted crop is 2–5× low if plugs are purchased. Schema question: `seed_transplant_cost_basis: in-house | purchased_plugs`, settled once. |
| per-crop `sell_through_fraction` | **ADD** (solver already reads it; no template sets it). Cull/trim diverges hard by crop: tomatoes 15–30%, garlic 5–10%, greens 10–20%. Cheap and researchable. |
| `crop_family` | **ADD in Phase A** while touching the store — free, checkable, and the input any future rotation constraint needs. Not a constraint now. |
| `min_acreage_if_planted` | One line of rationale each (equipment-scale statements; undocumented drivers of the binary). |
| prices, demand, packaging | Not research targets (farm/market-specific) — but they get a **laugh-test pass by the user** (defaults are only ever checked by intuition). |
| `lbs_per_tote` / volume basis | LEAVE ALONE (two audits disagree on direction; future pack-efficiency work). |

## Semantics rulings — settle ONCE, before per-crop work

**S1 — DTM is field occupancy in this model.** `calendar.py` spends the number as
planting→last-harvest occupancy; every guide publishes days-to-*first*-harvest. The library holds
**three bases at once** (transplant→first: tomato 85…; seed→first: spinach 42…; true occupancy:
**Hot Peppers 147 — the only correct template, use it as the reference**). Error is one-directional:
land occupancy understated, acres freed. Tomato true occupancy ≈ 19 wk (85 → ~133 "days"); basil's
3 weekly cuts ignore ~3-wk regrowth (35 → ~91). Guards: `grow_weeks == 0` is always an error
(Cut Salad Greens today); `grow_weeks < 3` on a transplanted fruiting crop is always an error.

**S2 — season windows: containment vs planting-window, settled WITH frost.** Templates are
authored as planting windows; `calendar.py` requires the whole cycle inside the window. That
mismatch kills Winter Squash/Melon (0 successions) and silently truncates late plantings of
everything (Kale's "plant through Dec 1" stops at W40). **Trap found in review: containment is
accidentally doing frost's job** — switch to planting-window semantics without adding a
last-harvest/frost date and zucchini gets harvested in November. Fix the convention and frost
together, then the three dead templates fix themselves. Record
`window_basis: "USDA zone ___, last frost ~__, first frost ~__"` on the template set —
**zone 7 per D2 (decided; disclosure required)**. Nothing in the codebase currently says what climate the
windows describe, while rainfall zones are selectable — Phoenix rain + Philadelphia windows solves
happily today.

**S3 — overwintering.** Garlic (fall-planted; spring-planted garlic doesn't vernalize → rounds at
~half yield, so the template's Jan-window + 10,000 lb/ac fall-planted yield contradict each other)
AND **June-bearing strawberries** (plant year 1, pick year 2 — same shape). Decide the modeling
convention (e.g. "overwintered crops enter the year as established stands; occupancy starts W1"),
document it on each affected template. No solver work invented here.

**S4 — recorded limitations (non-goals with names):** even-split harvest understates the peak
week — exactly the week that sizes cooler and crew (C2/C4b under-stressed); cut-and-come-again
regrowth gaps inexpressible; no season-of-planting yield decay (late successions at full yield =
known unpriced optimism — note on each template that yield is for the main slot); no
rotation/family constraint; ethylene incompatibility (one sentence: producers and sensitives share
rooms; matters only if cucumbers/peppers ever go ambient with tomatoes).

## Phases

**A — plumbing (mechanical, ZERO adjudication).** Derivation + complete override map
(byte-identical demo) + all three guards; delete the three phantom fallbacks; CSV columns for
`sales_spread_weeks`/`cold_storage`/`sell_through_pct` (today the CSV round-trip strips them and
reimports strict-1-week — re-creating the B.3 regression through the side door); `cold_storage`
into `worker/grounding.ts` CROP_DETAIL_FIELDS; saved-plan rule stated once (missing keys default
cold=true/spread=1 forever; **no retroactive +1** — B.2 migrated 1:1 deliberately and the golden
was re-pinned accepting it; the +1 note in the Sellable-Weeks tooltip is the user-facing remedy);
`crop_family` field; CROP_PROVENANCE skeleton. ~~Clamps + template loader + grounding max~~ —
**done, `3456c7d`.**

**B0 — internal-consistency sweep (zero research, run before any sourcing).** Cross-template
ratio checks on same-operation fields. Already caught by review: direct-seed labor Spinach 15 vs
Baby Spinach 2 (identical operation, 7.5×); Cucumbers 15 vs Zucchini 3; transplant Hot Peppers 10
vs Bell 4.6 (and demo 8.0 — a 6th divergence); **Napa (seeded) 8 vs Cabbage (transplanted) 3.5 —
inverted**, transplanting always costs more; corn dearer than beans; `grow_weeks` smells (S1).

**B — water & fert & shelf/cold, all 29.** PREREQUISITE (D3): `storage_loss_pct_per_week`
lands in the solver first — holding must cost something before honest shelf lives are entered,
or long-keeping crops become pure upside. Water first (constraint currently vacuous), fert
second (margin ↓ headroom), then shelf lives + cold flags off Appendix A, conservative end.
Falsifiable prediction, recorded in advance: **the strict-semantics recovery concentrates in 8
crops** (garlic 16, onions 16, potatoes 12, squash 12, carrots 12, beets 12, napa 10, cabbage 6);
21 templates are 1–3 wk. If recovery shows up spread across the library, suspect the model, not
the data. Also check whether B.2's +$48,970 was mostly garlic. **Coupling warning:** flipping any
crop ambient requires `ambient_storage_cap > 0` (validation now refuses, `912c814`) — Phase B's
executor sizes the barn default alongside the flags or every ambient crop fails loudly.

**C — crop-by-crop, impact order.** Garlic first (seed cost 10–25× low: 800–1,200 lb/ac cloves at
$4–8/lb = $3,200–9,600 vs $380; fabricated window; overwinter S3; 32% of contribution), then the
demo 7 (burning the override map, incl. the three demand-shape divergences), storables, tail. The
three dead templates get fixed by S2, not by editing their windows first. Labor totals are roughly
right (tomato 301 h/ac ✓) but splits carry copy errors (B0) and two totals are ~2× low in the
profit-flattering direction: strawberry harvest 400 vs 600–1,000 real; garlic plant 20 vs 40–100,
harvest "75 in one week" vs 100–250 including cure handling.

**D — adjudication + wire-in.** Adversarial refutation of finished batches (refute, don't
generate). **User intuition pass, scheduled:** each batch ships with a solved demo plan; the user
writes/checks "how this crop actually works" narratives as acceptance criteria. Land the audit's
verified ranges as warnings in `validate.py` **and wire it into the adapter** (330 lines currently
dead on the app path — without this, the next hand-edit is unchecked and the 10× class recurs);
re-sync blob. Re-capture payload + re-pin golden & regression per batch with reasons; re-measure
the 39% margin thesis.

## Decisions — RESOLVED by the user, 2026-07-28

- **D1 Potatoes → COLD** (reversed from the earlier ambient ruling): the Sept–Oct barn error
  (sprouting, shrink) is worse than the cooler's sweetening, which matters for frying stock only.
- **D2 Reference zone → USDA zone 7** (mid-US / mid-Korea — deliberately covers both pilot
  geographies). **Disclosure is part of the ruling:** `window_basis` recorded on the template set
  AND stated in the user-visible assumptions panel, so nobody audits a window against an unstated
  climate again.
- **D3 Holding cost → build `storage_loss_pct_per_week` (SPEC_v3 §3.4) BEFORE Phase B enters
  shelf lives.** Small solver change; also retires the 1e-6 tie-break's job honestly. Phase B's
  header gains this as a hard prerequisite.
- **D4 Basil → accepted:** its protection is `shelf_life = 1`; the regime flag follows operational
  truth and carries little weight either way.

## Two model gaps the transplant work surfaced (grower, 2026-07-29) — NOT data problems

**1. No propagation greenhouse.** Raising your own transplants means seeding in midwinter, which
needs a heated GREENHOUSE, not a high tunnel — a building, winter heat, and the labour to run it.
The model has no such cost line, so "raise your own instead of buying plugs" would read as almost
free. This is the ambient-barn error in a new place: a choice looks cheap because the asset that
makes it possible is not charged. Until the line exists, purchased plugs is the only honest basis
the app can ship, and `seed_transplant_cost_basis` cannot become a real user choice — offering
"own propagation" as an option would be offering a saving the model invents.

**2. Transplant timing quality is invisible, and it is not small.** Yield is one number per crop,
so the model cannot express that a transplant set at its prime massively outproduces the same
seeding set a week later under stress — the grower reports that difference persisting through the
entire life of the plant. Every transplanted crop in the library is implicitly priced as if set at
its prime, which is the optimistic end. Related: buying finished transplants removes raising loss
(you receive only survivors) but surrenders that timing control, so the two options differ in
RISK and YIELD, not just in cost per plant — and the model can currently see only the cost.

## Done when

29 templates carry provenance-tagged values, cold flags, families, sell-through, stated bases
(yield/seed-cost/DTM/window); S1–S3 rulings encoded with guards; demo derives with a snapshotted
override map burned to empty or justified; phantom fallbacks gone; payload-capture guard live;
validate.py wired; baselines re-pinned per batch; water constraint non-vacuous; margin re-measured
and the 39% thesis updated. **Non-goals (decided, not forgotten):** S4 list, volume basis,
price/demand research, third storage regime.

---

## Appendix A — shelf-life CANDIDATES (domain review, 2026-07-28). Sources to OPEN, not data.

Strict semantics (weeks sellable incl. harvest week). Conservative-end values shown.
Cold pool unless noted. †= regime compromise noted on template.

| Template | Wks | Conf | Source to open | Note |
|---|---|---|---|---|
| Spinach, Baby Spinach, Cut Greens, Kale, Chard, Arugula | 2 | med–high | AH-66 / UC Produce Facts | greens |
| Lettuce (Head) | 3 | high | AH-66 lettuce | crisphead reading |
| Broccoli | 2 | high | AH-66 | assumes icing the model lacks; else 1 |
| Cabbage | 6 | med | AH-66 | fresh green; storage variety = different template |
| Napa Cabbage | 10 | med | AH-66 Chinese cabbage | cold storable |
| Carrots / Beets | 12 | med/est | AH-66 | **topped vs bunched fork the model can't express — biggest judgment call; document the 26-vs-2 spread** |
| Radishes | 3 | med | AH-66 | topped |
| Garlic | 16 | med | AH-66; UVM/UMaine | ambient = BARN number (3–5 mo @60–65°F), not the 6–7-mo cooler number |
| Onions | 16 | med | AH-66 | pungent storage type; sweet = 4 — verify which the template is |
| Tomatoes | 1 | high | AH-66 | field-ripe for market; generosity here is expensive and wrong † |
| Bell / Hot Peppers | 2 | high/med | AH-66 | cool+damp†; hot = FRESH chile (dried = different product, 52 ambient) |
| Cucumbers, Eggplant, Zucchini, Green Beans | 1 | med–high | AH-66 | cool+damp† (cukes 2 at true optimum; 38°F cooler costs the week) |
| Snap/Snow Peas | 2 | med | AH-66 | |
| Winter Squash | 12 | med/high | AH-66 | AFTER 10–14 d cure @80–85°F; ambient |
| Melon (Cantaloupe) | 1 | med | AH-66 muskmelon | full-slip; call is **name-dependent** — honeydew/watermelon differ |
| Sweet Corn, Strawberries | 1 | high | AH-66 | unambiguous |
| Basil | 1 | high | UC Produce Facts | see D4 |
| Potatoes | 12 | med | AH-66 | after curing; COLD per D1 (decided) |
