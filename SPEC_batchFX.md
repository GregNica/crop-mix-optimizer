# SPEC — Batch FX: the fixed layer

**Status:** RULED 2026-10-25 (§5). FX.0 (the toy prototype) is BUILT:
`toy_models/farm_toy_v12_fixed_layer.xlsx` + `toy_v12_lp.py` (oracle) + `verify_toy_v12.py`.
Source: PLAN "Batch FX", DECISIONS **GROUP G** (rulings 2026-10-19), memory `fixed-layer-batch-fx`.

**Why:** the grower's first page of January — *"what do you know you need to plant? This absorbs
the big blocks and then the rest gets filled in with extras."* The app optimises every acre from
zero. This batch adds what is already decided, owed, or physically there.

---

## 1. Where the app is today (refs)

| Thing | Today |
|---|---|
| Decision | `x[i]` = FRACTION of `total_land` for succession i; `y[i]` plant binary (`solver.py` C9/C10 ~1476–1545) |
| Land (C1) | ONE row per week: Σ standing x ≤ 1 (`solver.py` ~1200) — no zones |
| Demand caps | keyed by **crop index** (`demand.py` `build_demand_table`, `build_annual_caps`; C6/C6b ~1409–1440) — a second crop name is a second market |
| Diversity (C8) | per crop index, annual acre-weeks (`solver.py` ~1461) |
| Must-plant | none. `min_acreage_if_planted` is CONDITIONAL on y — escaped by not planting (measured: 14-ac garlic floor → 0 ac, −$344k) |
| Carry-in | `overwinters` flag + C15 `committed_acres` = floor on acres standing in week 1 (`solver.py` ~1483) |
| Perennials | refused: `calendar.py` ~114 raises on any cycle > 52 weeks |
| Contracts | none (BACKLOG P1) |
| Duplicate names | refused by `validate.py` (~202) — so a variant MUST be a new name |

## 2. What the toy measured (FX.0)

Toy v12 = v11 (3 crops, labour by role) + a 2-ac **High tunnel** zone, **Tunnel Spinach**
(`sells_as` Spinach, longer windows, 0.25-ac minimum), **Asparagus** (3 ac perennial, toy data
sourced where possible), two **standing** floors (garlic carry-in 18.3 ac in week 1; kale 8 ac in
weeks 10–20), one **annual** floor (kale 45 ac), two **contracts** (kale and spinach wholesale,
$0.50/lb short penalty). Each floor binds alone — but they INTERACT: with the kale floors on,
garlic rises to its ~18.6-ac ceiling unasked, so the carry-in is slack at the full default. The
sheet reproduces the oracle to the cent.
Optimum **$480,439** (margin 22.3%).

| Finding | Measured | Consequence for the app |
|---|---|---|
| **Variant trap is real** | keyed by name, the two spinaches sell 11,000 lb/wk into a 6,000 lb FM and "earn" **$32,318** that does not exist | caps (C6/C6b) and contracts keyed by IDENTITY; guard test that two names cannot exceed one cap AND that they do when keyed by name |
| **Standing ≠ annual** | 30 ac kale ANNUAL costs **$0** (already plants more); 30 ac STANDING wks 10–20 costs **$49,240** | ship BOTH, named differently |
| Carry-in = standing floor | garlic carry-in is a standing floor with window [1,1] — the same row as C15 | fold C15 into the standing-floor mechanism; no second code path |
| **Infeasible floors have non-land causes** | garlic's ceiling ~18.6 ac is set by the 108-h winter crew (planting) AND the 150 m³ barn (harvest) *together*; relaxing either alone stays infeasible | the refusal must name labour/storage, not "check your land"; diagnose by elastic re-solve |
| **Shortfall: fact vs choice** | penalty $0.50→$5: kale stays 3,000 lb short (no harvest possible wks 36–37 — a FACT); spinach 8,000→4,000 (tunnel fills wks 33–34 — a CHOICE) | report each shortfall with its kind; the penalty default decides contracts — the grower's number |
| Deltas must use the objective | a floor that did not bind "raised" profit $45 with the objective identical — interest is post-solve | the "this costs you $X" delta = objective difference, not profit |
| Absent-zone leak (caught in the toy) | removing a zone left its plantings with NO land row → unbounded; "+$91k" | plantings in a zone the farm lacks are pinned to 0 |
| Dead eligibility (caught by the guard) | a Y/N for a zone with no plantings is read by nothing | eligibility can only withdraw; granting = generating rows |
| Costs (toy) | contracts $6,521 · standing floors $4,780 · annual floor $3,761 · perennial $15,308 (3 ac, placeholder data) · tunnel EARNS $27,909 | the with/without readout works and is legible |

## 3. The design (app)

⚠️ **Read with §6.** Where this section puts a floor, contract or perennial ON a crop, §6
supersedes it: they ship as farm-level `commitments[]` entries with ids, so a future co-pilot can
own them. The constraint maths below is unchanged.

**FX.4 Zones.** `zones: [{name, acres}]` (absent = one zone "Whole farm" = `total_land` → golden
unchanged). Crop gains `zones: [names]` (absent = all). Successions are generated per eligible
zone (`x[i,z]`); C1 becomes one row per zone per week, RHS `acres_z/total_land`. Variables grow
×(eligible zones) — fine at 3–5 zones. A planting in a zone not on the farm is not generated.

**FX.4 as built (2026-10-25).** `farm_v2/utils/zones.py` (`resolve_zones`, `crop_zone_names`),
shared by validation and the solver. Decisions taken in the build, open to the grower:
- **One zone may leave acres blank and take the rest** ("2 ac tunnel, the rest open field", the
  toy's remainder zone); otherwise zones must add up to `total_land` exactly — a gap is refused,
  never left as land the plan cannot use. Acres must be a real number > 0 (bool/str refused).
- **Eligibility can only name the farm's zones.** An unknown name or an empty list is REFUSED,
  never skipped (the toy's absent-zone leak). The solver re-resolves zones itself, so a crashed
  pre-flight guard (Step 0 fails open) still cannot let one through.
- **Slot names carry the zone whenever the FARM has >1 zone** ("Kale W10 · High tunnel"), not
  per crop, so editing one crop's eligibility renames nothing. Identity = (crop, start_week, zone).
- Result: `zones: [{name, acres, used_acres[52]}]` (not in `capacity_series`, which the
  unplanted-crop diagnosis scans farm-wide); schedule rows carry `zone`; `weekly_land_frac` is now
  summed from it instead of re-walked in the adapter.
- ⚠️ **OPEN — C10 `min_acreage_if_planted` now applies per (start week, ZONE) slot**, i.e. per zone
  separately, and y binaries grow ×zones. Fine for a variant pinned to one zone (the toy's 0.25-ac
  tunnel minimum); for a crop in two zones the grower may mean the minimum of the planting as a
  whole. Raise with FX.5.
- Measured: splitting land every crop may use changes nothing (objective identical at gap 1e-9;
  ~$20 apart at the shipped 1e-4 gap — tolerance, not an effect).
- **Minimum acres: PER ZONE — grower ruling 2026-10-25.** The "overall planting" option is
  BACKLOG X8. Zone limits = the crop × zone tick grid; attribute matching that pre-ticks it = X9.

**`/code-review high` on `2befe7a` (2026-10-25): 10 findings, all reproduced before acting.**
Fixed: (1) the Gantt label and its CSV parsed the start week off the END of the name, which a zone
suffix broke ("Kale W10 · Tunnel 2" → "2"); the schedule now carries `start_week`. (2) A
non-list `zones` raised AttributeError → a traceback; now refused by name. (3) A minimum planting
larger than every eligible zone left the crop "outcompeted"; now refused (larger than SOME zone →
warning). (4) Commitments overfilling one zone TOGETHER (each fits alone) gave a bare HiGHS
"infeasible"; now refused by Hall's condition over zone groups (a per-zone sum would wrongly
refuse a crop that may spill into another zone — mutant N3 pins that).
Deferred, on the record:
- **(6) Rain falls on the tunnel → BUILT (grower, 2026-10-25: "if it's easy").** Rain offset
  was farm-wide, so a covered zone's crops got rain credit they cannot receive. Zone gains
  `covered: true` (default false). The solver builds ONE per-succession rain fraction (0 when
  covered) and both rain readers take it — `compute_net_water_rates` (C3, water cost, Rain-fed
  plantability) and `rain_coverage` (the refusal wording); water.py stays zone-agnostic, and a
  partial-rain zone (shade cloth) would later need only a per-zone fraction, not new plumbing.
  Measured: covering the 2-ac tunnel adds 3,390,856 L of irrigation, matching a hand rebuild
  from the crop's phase needs to rounding; same plan. 5/5 targeted mutants caught.
- (5) A crop eligible in N zones gets N identical copies of each slot (symmetry): measured 3.3 s →
  5.9 s on the golden farm with two all-eligible zones. Watch it on FX.7's fixture; symmetry-break
  or aggregate unrestricted crops if solves near the time limit.
- (7) What-If land scaling multiplies `total_land` but not zones → refused / remainder takes it
  all. Latent until the zones card; fix in the UI step (scale fixed zones, or scale the remainder).
- (8) A full zone is invisible to the bottleneck ranking and the unplanted-crop diagnosis (both
  farm-wide). UI step: name the binding zone; diagnose zone-limited crops by their zones.
- Skipped: (9) `weekly_land_frac` now sums sub-1e-6 x values the old loop skipped — 4th-decimal,
  nothing pins it, the full suite agrees; (10) validation + solver both generate successions —
  pre-existing, now ×zones; revisit with the Step 0 fail-open question.

**FX.5 Variants.** Crop gains optional `sells_as: "<crop name>"` (must name a crop that exists; no
chains). Demand caps, contract floors and **channel reporting** key on the identity. Each name keeps
its own windows/yield/costs. Diversity: see Q3.

**FX.5 as built (2026-10-25).** `farm_v2/utils/variants.py` (`resolve_variants`, `identity_of`),
run by the solver before Step 0 (validation needs the inherited fields present).
- **Measured first, in the app** (golden + a covered 2-ac tunnel + a year-round Tunnel Spinach):
  keyed by name the two sold **12,000 lb/wk into Farmers Market's 6,000 in 10 weeks**, profit
  $757,459. With one market per identity: FM peaks at exactly 6,000, profit **$705,841**. Golden
  unchanged at $652,876 (no variants → identical row set).
- **Inherited** (`INHERITED_KEYS`): channels (prices, packaging, caps), `crop_diversity_max`,
  labour (plant/grow/harv), and — not named in the ruling, taken because it is the same pound in
  the same cooler — `cold_storage`, `crop_size_m3_per_lb`, shelf life / spread, storage loss.
  Omitted → the parent's; sent equal → fine; sent DIFFERENT → refused by name ("make it its own
  crop") — the payload twin of ruling 3's "price or cap edit → prompt for a new card".
  ⚠️ Open to the grower: **`sell_through_fraction` stays the variant's own** (grade-out is a
  property of how it was grown), as do `committed_acres` and `overwinters`.
- **Rows.** Every cap row is per IDENTITY (a crop with no variant is an identity of one, so the
  golden farm's rows are the same rows in the same order). The market's cap is the max of the
  members' copies — equal, since channels are inherited, until the margin hurdle zeroes one, which
  it does per NAME because a variant's costs (so margin) differ. A zeroed member gets a zero row
  of its own; the open members share one weekly row (C6) and one annual row (C6b). C8 diversity is
  one row per identity at the parent's allowance. Inventory and storage stay per crop (two stocks
  of the same pound in one cooler; selling is what is shared).
- **Reports.** `demand_saturation` is per identity, under the parent's name, summing both names'
  pounds (the cap belongs to the parent card). `channel_sales`, `crop_contribution` and the
  schedule stay per name — they are different plantings with different costs, and still sum to
  the headline revenue.
- **Adapter.** It defaults `cold_storage`/`sales_spread_weeks` on every crop; on a variant it
  normalises a SENT value like the parent's but never defaults one, or a Garlic variant (parent ambient) would read cold and be refused for a box
  never typed. Resolution and refusal live in the solver only (`invalid_input`, not a traceback).
- Guards: `tests/test_variants.py` (26), incl. the hurdle × variant case (66% floor drops
  Spinach/Wholesale at 65.5%, keeps Tunnel Spinach at 67.5%). `/simplify` (4 lenses) folded the
  per-crop + shared row pairs into one loop per identity. **13 targeted mutants, 13 caught** after
  one survivor: saturation's weekly series read off the parent alone passed, because Spinach alone
  reaches the cap in some week — `test_weeks_at_cap_count_both_names` rebuilds the at-cap weeks
  from the sales (31 together vs 24 alone). 13 s wall in parallel repo copies.
- Contracts keyed by identity arrive with FX.3.

**FX.2 Perennials.** Crop gains `perennial: {acres, zone, harvest_weeks, upkeep_per_acre_yr,
establish_per_acre, life_years}`. Not passed to `generate_successions`: injected as one pinned
pseudo-succession standing weeks 1–52 (phase G, H in the harvest window), `x` fixed at
acres/total_land, `y` = 1. Cost lines: upkeep (this year) + establishment ÷ life (depreciation,
OWN→depreciate — never seed). Its harvest flows through inventory and channels like any crop.

**FX.1 Must-plant.** Two lists on the crop (or a farm-level table, Q4):
`must_stand: [{acres, from_week, to_week}]` → Σ standing x of the identity ≥ acres/total_land in
every week of the window; `must_plant_annual: acres` → Σ x over the identity's plantings (perennial
excluded) ≥ acres/total_land. No y in either row. C15 becomes `must_stand {committed, 1, 1}`
(load-time migration of `committed_acres`; keep the overwintering requirement message). HARD:
infeasible → refusal naming which of land / labour / storage / cash binds (elastic re-solve).

**FX.3 Contracts.** Farm-level `contracts: [{sells_as, channel, lb_per_week, from_week, to_week,
penalty_per_lb}]` → `Σ v[identity,ch,w] + short[k,w] ≥ lb`, `0 ≤ short ≤ lb`, penalty in the
objective and the P&L — ⚠️ **NOT in the C13 weekly cash floor**: charged there, an unavoidable
shortfall at a big penalty made the toy INFEASIBLE (measured at $200/lb), which G3 forbids. It is
settled with the buyer after the season, like interest is post-solve. Result: per contract lb short by week, $ penalty, its KIND
(fact/choice — re-solve at a high penalty; fact if it does not move), and the with/without delta
on the objective. Validate: lb ≤ the identity's cap on that channel (else refuse — a contract
above the market is a typo).

**FX.7 Guards (same commits).** A golden FIXTURE farm with a zone, a variant, a perennial, both
floor kinds and a contract (the L4 trap: the shipped golden uses none of it, so it can stay
unchanged at $652,876 — and is then blind to all of this). Mutation-tested per the CLAUDE.md order
(working code → `/simplify` → guards). Toy-vs-app cross-check on the fixture where shapes allow.

## 4. Build order

FX.4 zones → FX.5 variants (needs zones to be meaningful) → FX.2 perennials → FX.1 floors (+ C15
migration) → FX.3 contracts (+ shortfall report) → FX.7 fixture and guards → UI (zones card, crop
card eligibility/`sells_as`/perennial, a "Committed" section, a contracts table) → `/simplify` →
`/code-review max` (money path) → browser check. FX.6 templates stay in Batch 3 (sourced data).

## 5. Grower rulings (2026-10-25) — full text in DECISIONS GROUP G

1. **Overwintered crops are a pre-commitment, PINNED at the carried-in acres** (floor = ceiling).
   The cyclic year makes the same pin reserve this fall's replant, so a plan with no room for it is
   refused with its cause. No decisions about next year. Separating the two → BACKLOG X7.
2. **Each contract requires a mode: Must deliver** (hard; a refusal names the contract + weeks)
   **or Pay a penalty** (amount required). No default. Amends GROUP G ruling 3.
3. **Variants are a sub-section of the crop card.** Inherit channels, prices, caps, contracts,
   diversity (C8 per IDENTITY) and labour; edit windows/days to maturity, yield, seed + per-acre
   costs, zones, min acres. Price or cap edits → prompt for a new card. Labour classes → BC10.
4. **One top-of-form commitments table.**
5. **Zone structures are sunk.** No cost line in FX; no optimiser investment choice (BACKLOG X6).
6. **A perennial is a planting card per block, always committed:** acres, year planted, this
   year's yield (0 while establishing), this year's costs + labour, harvest weeks. Establishment
   of a mature block is SUNK (overrides OWN→depreciate for now). No yield-ramp model.

**What the rulings change in §3:** FX.1 — C15 becomes a PIN (`must_stand` with an equal ceiling)
for committed overwintering crops, and an uncommitted overwintering crop cannot be planted.
FX.2 — the perennial block takes `{acres, planted_year, yield_this_year, cost_this_year,
labour, harvest_weeks}`; no `establish_per_acre`/`life_years`, no depreciation line. FX.3 — a
contract gains `mode: "deliver" | "penalty"`; `deliver` has no short variable, and its
infeasibility is diagnosed by the elastic re-solve. FX.5 — the variant inherits labour.
The toy (v12) is updated to these before FX.4 starts.

## 6. Forward compatibility — the plan-first co-pilot (BACKLOG **X5**, tag `COPILOT`, tabled)

**The idea (grower, 2026-10-24):** reverse the interaction, Tend-style. The grower enters the
parameters, then BUILDS the plan: the fixed layer first, then undecided crops. An AI co-pilot runs
micro-solves, what-ifs and Monte Carlo in the background, suggests options and answers questions.
The grower decides; the tool advises. Not scheduled. **This batch must not paint it into a corner.**

**What FX ships differently because of it (design constraints, adopted now):**
1. **Every fixed-layer item is a plan ENTRY**, not a field scattered on a crop card. One farm-level
   `commitments: [{id, kind, ...}]` list, `kind` ∈ `must_stand | must_plant_annual | contract |
   perennial`, each with a stable `id` and a `source` ∈ `user | suggested | accepted`. A co-pilot
   suggestion the grower accepts becomes the same object a typed commitment is. (Settles Q4 toward
   the top-level table.)
2. **One pinning mechanism.** The perennial already enters the solver as a PINNED planting
   (acres fixed, outside the decisions). Generalise it to `pinned_plantings: [{crop, start_week,
   zone, acres}]` so a planting the grower places by hand (Tend-style) is a pin, and "fill in the
   rest" is the solver working around the pins. The perennial becomes one pin with a cost line.
3. **Every entry reports what it costs.** The with/without delta on the OBJECTIVE (built in the
   toy for each piece) is returned per entry id. That is the co-pilot's main "why" primitive: "this
   contract costs you $6,521, and the spinach half is a choice you could undo".
4. **Refusals and shortfalls name their cause.** Elastic re-solve → which limits bind (the garlic
   ceiling took the crew AND the barn together); shortfall labelled fact vs choice. Prose built on
   these, never on reading one solution.
5. **Ids survive re-solves**, so the UI and a chat transcript can refer to "entry 3" across edits.

**The two risks, answered as far as the toy lets us:**
- *Can the AI explain the solver?* Not by reading a solution: a MILP plan says what, not why. It
  CAN interrogate the solver, which is auditable in the ways that matter: with/without deltas per
  entry (§2), binding-constraint slack (every room-left row), marginal values from the LP with the
  binaries fixed (what an extra tunnel acre or crew hour in week 30 is worth), and counterfactual
  re-solves ("what if 5 more ac of kale?"). The toy showed why explanations must come from
  re-solves: single-toggle reasoning got the garlic ceiling wrong, and my own reasoned claim about
  which shortfall was a choice came out BACKWARDS until measured. The LLM should narrate computed
  facts, never infer reasons.
- *Are micro-solves useful early?* The toy confirms the worry: commitments INTERACT (the kale
  floors pushed garlic up to its ceiling unasked). Mitigations: (i) the hard limits — land, zones,
  crew, storage, water, cash — are parameters entered BEFORE planning, so early solves already see
  them; (ii) suggestions carry their own stability: near-optimal alternatives (memory
  `near-optimal-alternative-plans`, decided, not built) and "holds unless…" thresholds from
  re-solves; (iii) a suggestion that flips when an entry is added is itself worth showing ("adding
  that contract changes the best use of the tunnel"). Open: whether solves are fast enough
  in-browser for this cadence (toy: ~3–5 s per solve at 140 plantings).
