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

**FX.5 as built (2026-10-25).** `farm_v2/utils/variants.py` (`resolve_variants`, `identity_groups`),
run by the adapter before it normalises and by the solver before Step 0 (validation needs the
inherited fields present); the solver is where a bad variant is refused.
- **Measured first, in the app** (golden + a covered 2-ac tunnel + a year-round Tunnel Spinach):
  keyed by name the two sold **12,000 lb/wk into Farmers Market's 6,000 in 10 weeks**, profit
  $757,459. With one market per identity: FM peaks at exactly 6,000, profit **$705,841**. Golden
  unchanged at $652,876 (no variants → identical row set).
- **Inherited** (`INHERITED_KEYS`): channels (prices, packaging, caps), `crop_diversity_max`,
  labour (plant/grow/harv), and — not named in the ruling, taken because it is the same pound in
  the same cooler — `cold_storage`, `crop_size_m3_per_lb`, shelf life / spread, storage loss.
  Omitted → the parent's; sent equal → fine; sent DIFFERENT → refused by name ("make it its own
  crop") — the payload twin of ruling 3's "price or cap edit → prompt for a new card".
  **Grower ruling 2026-10-25 (accepted as recommended): `sell_through_fraction` stays the
  variant's own** (grade-out is a property of how it was grown), as do `committed_acres` and
  `overwinters`. The three `/code-review` deferrals below are accepted for the UI step.
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
- **Adapter.** Resolves variants BEFORE normalising, so parent and variant get the same adjusted
  prices and defaults for every inherited key (an earlier per-key skip covered 2 of 10). A variant
  it cannot resolve goes through as sent; the solver refuses it as `invalid_input`.
- Guards: `tests/test_variants.py` (26), incl. the hurdle × variant case (66% floor drops
  Spinach/Wholesale at 65.5%, keeps Tunnel Spinach at 67.5%). `/simplify` (4 lenses) folded the
  per-crop + shared row pairs into one loop per identity. **13 targeted mutants, 13 caught** after
  one survivor: saturation's weekly series read off the parent alone passed, because Spinach alone
  reaches the cap in some week — `test_weeks_at_cap_count_both_names` rebuilds the at-cap weeks
  from the sales (31 together vs 24 alone). 13 s wall in parallel repo copies.
- Contracts keyed by identity arrive with FX.3.
- **`/code-review high` on `1a50f42` (2026-10-25): 9 findings, the money/refusal ones reproduced.**
  Fixed: (1) an unnamed crop became a KeyError traceback (identity grouping ran before
  validation) — now validation's refusal again; (2) commitments of a crop + its variant each fit
  the per-name diversity check but not the shared C8 row → bare HiGHS infeasible (Garlic + Hardneck
  at 33.6 ac each vs 48) — now refused by name; (4) the adapter skipped defaults for 2 of the 10
  inherited keys → it now resolves before normalising; (5) duplicate names let a variant find the
  wrong parent → refused first; (8) one `_sales_col` for every v-column site; (9) stale
  `identity_of` name. Deferred to the UI step, on the record:
  - (3)/(6) `demand_saturation` is keyed by the parent's name, so it shows "Spinach / FM n%" when
    only Tunnel Spinach sold — beside an unplanted-Spinach banner, or beside Spinach/Wholesale in
    `excluded_channels`. The number is right (it is Spinach's MARKET); the label must say so
    ("Spinach market — sold by Tunnel Spinach"). Needs a members field → the saturation key set.
  - (4b) A What-If that scales one crop's channels must scale the parent only and send the
    variant WITHOUT inherited keys, or the re-solve is refused. Payload-builder contract.
  - (7) `"4"` vs `4` on a sent inherited key is refused as a second value — only if a caller
    sends both raw and differently typed; the form sends numbers.

**FX.2 Perennials.** Crop gains `perennial: {acres, zone, harvest_weeks, upkeep_per_acre_yr,
establish_per_acre, life_years}`. Not passed to `generate_successions`: injected as one pinned
pseudo-succession standing weeks 1–52 (phase G, H in the harvest window), `x` fixed at
acres/total_land, `y` = 1. Cost lines: upkeep (this year) + establishment ÷ life (depreciation,
OWN→depreciate — never seed). Its harvest flows through inventory and channels like any crop.

**FX.2 as built (2026-10-25).** `farm_v2/utils/perennials.py` (`resolve_perennial_blocks`,
`perennial_successions`), read by validation and the solver alike. Measured first: the app
refused any perennial outright (`calendar.py`, "cycle is 113 weeks … exceeds the 52-week year").
- **Shape.** The crop card is flagged `perennial: true` and describes the PRODUCT (channels,
  storage, shelf life, and grow/harvest-phase labour, water, fertiliser and fuel rates, plus crop
  protection); it needs none of an annual's calendar keys. Each BLOCK (one planting, "patch") is
  a farm-level `commitments[]` entry (§6.1): `{id, kind: "perennial", source, crop, acres, zone,
  planted_year, yield_per_acre, harvest_from_week, harvest_to_week, extra_cost_per_acre?,
  labor_grow?, labor_harv?}`. Yield is THIS year's and REQUIRED (no default). Yield 0 =
  establishing: all grow, no harvest weeks. Stage is reported from the harvest, never stored. A
  harvest window may wrap the year. **Labour override per block KEPT (grower, 2026-10-25).**
- **The pin.** One pseudo-succession per block, weeks 1–52, phase G with H in its harvest weeks,
  appended AFTER the generated slots (so every annual index is unchanged → golden identical). Its
  x is bounded lb = ub = acres/total_land and y = 1, so C1/C2/C3/C4/C12/C13 see it as any planting.
  **C8 diversity and C10 minimum skip it** (committed ground is not a rotation or lot-size choice;
  in either row it could only produce a bare infeasible). The pin is generic: the solver core
  reads PLANTING properties, never "is this a perennial" — `pinned_acres` (bounds, C8, C10),
  `commitment_id`, and overrides under the card's own keys (`yield_per_acre`, `labor_grow/harv`,
  seed 0) via `calendar.planting_value`, plus `extra_cost_per_acre`. A hand-placed annual pin
  (§6.2) would be one more source of the same dict; no payload kind exposes it yet.
- **Costs — itemised (grower, 2026-10-25: "perennials still need those").** A block pays the
  card's fertiliser, fuel, metered water and crop protection exactly as any crop does, in their
  own P&L columns — and NEVER seed: establishment is sunk (ruling 6), so a seed figure on the card
  is ignored for blocks. `extra_cost_per_acre` (default 0) is what that patch alone costs this
  year (e.g. an establishing patch's extra work), its own VC column `perennial_extra`, flat over
  52 weeks. (First build had ONE all-in cost per block and charged no inputs — overruled.) Labour
  is wages as for any crop (W12). Overhead ledger: EXCLUDES "perennial"; tooltip, assistant
  description and P&L labels updated.
- **Margin kernel.** Per planting at its own yield; a perennial's per-crop rates use the
  acre-weighted yield of its BEARING blocks (an establishing block sells nothing, so carries no
  per-pound cost).
- **Refused by name:** unknown/non-perennial crop, acres ≤ 0 or non-numeric, missing yield/cost,
  bad harvest weeks, zone not on the farm or not eligible, no zone when the crop may stand in
  several, duplicate ids, unknown kind, the three FX.1/FX.3 kinds ("not supported yet"), a bad
  `source`, a perennial crop with no block, a perennial with `committed_acres` or `overwinters`.
  Blocks join the week-1 land check and FX.4's Hall's-condition zone check.
- **Result:** `perennial_blocks: [{id, source, crop, zone, name, acres, planted_year, stage,
  yield_per_acre, harvest_weeks, cost, sellable_lbs, labor_hours}]`; schedule rows carry
  `commitment_id` (None for chosen plantings).
- **Measured on the first build (golden + toy asparagus, 3 ac bearing + 1 ac establishing, one
  all-in cost):** upkeep $5,888 = 3×$1,296 + $2,000 exactly; 5,250 lb sellable, all sold (FM 300×8 + Wholesale 2,850); hours
  198 = 3×(44×0.5 + 8×5.5) and 26 = 52×0.5; profit $629,903 (−$22,974 vs golden: 4 ac taken from
  annuals all year). Golden unchanged at $652,876 with `commitments` absent or []. In a covered
  tunnel a block gets no rain credit (100,000 vs 42,800 L/ac in week 20) — and the FARM total
  can be identical when the same acreage sits in the tunnel either way (rain offset is per
  acre, not per crop): an explained coincidence, not a bug.
- **Suggestions do not bind (grower, 2026-10-25).** An entry with `source: "suggested"` is
  validated but left out of the plan; a co-pilot "try it" solve prices it by sending it as
  `accepted`. Mechanics only — the co-pilot itself is not designed (X5).
- **Guards:** `tests/test_perennials.py` (39). `/simplify` (4 lenses) made the pin generic (planting
  properties, `calendar.planting_value`; C8/C10 keyed on the PIN, not on "perennial"), derived
  stage, shared `utils/numbers.is_number` and `calendar.week_span`. **16 targeted mutants, 16
  caught** — after five were found INERT on the default farm before guards were written for
  them: the ceiling (the blocks lose money, so a floor-only pin passes), C8 and C10 (the card has
  no cap or minimum), the kernel's acre weighting (no test read a perennial margin), and the
  extra cost's flat spread (totals agree if charged in one week). Each guard forces the second
  condition. Two fast kills checked by hand: real (80 ac without the ceiling; presolve-infeasible).
- **`/code-review high` on `28210e2` (2026-10-25): 10 findings; the money/refusal ones reproduced.**
  Fixed: (1) a perennial's per-pound cost was the PLAIN mean of per-patch ratios — a 0.2-ac young
  patch at 100 lb/ac read $1.69/lb against a true $0.19, Wholesale at −26%, and a 5% hurdle would
  drop the channel and waste the forced harvest. ⚠️ **My own guard had pinned that wrong formula**,
  so mutation testing "confirmed" it: a mutant kill proves a guard is SENSITIVE, never that its
  oracle is right. Now one weighted kernel (annual: every slot, weight 1 — identical to before;
  perennial: bearing patches by acres) feeds per-pound cost, yield, hours and the split;
  (3) the margin tooltip did not reconcile for a perennial ($1,482 vs $1,872/ac — the split
  averaged in the establishing patch) — same fix; (2) a patch the crew/cooler/water/cash cannot
  hold returned a bare HiGHS "infeasible" — now one re-solve with the pins released, and if that
  solves the refusal NAMES the committed plantings (which limit binds = FX.1's elastic re-solve);
  (5) validation applied the card's minimum planting to perennial patches; (6) a perennial with
  only a suggested patch was diagnosed "no plantable window" — new reason `no_committed_block`
  (client wording added); (8) the money-input checks moved to `utils/numbers.py` (one copy);
  (9) the report no longer silently skips a pin without a `block`. 5/5 targeted mutants caught.
  Deferred, on the record:
  - **(4) Dormancy — BUILT (grower, 2026-10-25: "yes add the growing season").** Every
    non-harvest week had been a GROW week, so the card's grow rates were charged all 52 weeks,
    January included. The perennial card takes `growing_from_week` / `growing_to_week` (both or
    neither; absent = all year, i.e. the old behaviour; may wrap). Outside it a patch is in the
    new phase `DORMANT` (= 3, `calendar.py`): it holds its land (C1 counts every phase) and every
    per-phase rate reader skips it — labour, both water readers, fertiliser, fuel; crop
    protection already spreads over GROW weeks only. Harvest weeks outside the season are
    refused by name. Client: one `PHASE_CODE` table for the Gantt and its CSV ('D', grey) — both
    had mapped anything not 0/1 to 'H'. Measured (season W14–40): bearing patch 19 G + 8 H + 25
    D, labour 3×(19×0.5 + 8×5.5) h. 7 targeted mutants, 7 caught — after the rain-coverage
    guard was found INERT (a WET dormant week can only raise a minimum; the harm is a DRY one).
  - (7) `commitments` are forwarded as sent, outside the client's unit conversion — the UI step
    must convert a patch's acres/yield/cost with the crop card (the ×2.2046 family).
  - (10) Skipped: `planted_year` is not compared with `year`, because the app never sends a plan
    year — `year` is the 2024 calendar layout, and the check would refuse real 2025 patches.
- **Deferred:** the per-entry with/without delta (§6.3) to FX.3, built once for every kind.
  Hand-placed plantings of an annual (§6.2) stay unexposed: FX.1's floors cover "this crop is
  committed"; a fixed-date pin waits for the co-pilot work.

**FX.1 Must-plant.** Two lists on the crop (or a farm-level table, Q4):
`must_stand: [{acres, from_week, to_week}]` → Σ standing x of the identity ≥ acres/total_land in
every week of the window; `must_plant_annual: acres` → Σ x over the identity's plantings (perennial
excluded) ≥ acres/total_land. No y in either row. C15 becomes `must_stand {committed, 1, 1}`
(load-time migration of `committed_acres`; keep the overwintering requirement message). HARD:
infeasible → refusal naming which of land / labour / storage / cash binds (elastic re-solve).

**FX.1 as built (2026-10-25).** `farm_v2/utils/commitments.py` now owns what every commitment
kind shares (list shape, unique ids, `source`, known kinds, suggestions don't bind — moved out of
`perennials.py`) and resolves the floors; validation and the solver both read it.
- **Entries.** `{id, kind: "must_stand", crop, acres, from_week, to_week}` (window may wrap) and
  `{id, kind: "must_plant_annual", crop, acres}`. `crop` may name a parent or a variant; the floor is
  on the IDENTITY. Standing counts every planting in the ground that week, a perennial patch
  included; annual counts chosen plantings only (pins excluded; an annual floor on a perennial is
  refused by name).
- **C15 is the floor rows.** One row per standing week / one per annual floor, no y. The carry-in
  is generated from each crop card: `committed_acres` on an overwintering crop → `carry_in` with
  window [1] and **floor = ceiling**. Overwintering with 0 entered → pinned at 0 (no row needed when
  nothing could stand); validation warns, and the unplanted diagnosis says `no_carry_in`, not
  "outcompeted". A non-overwintering crop with acres keeps the old warning + refusal.
- **Demo farm (grower, 2026-10-25: "#1 is obvious"):** Garlic `committed_acres: 18`
  (`DEMO_OVERRIDES`). Measured: the free plan took 18.04 ac (shown as 18.1); pinned at 0 the farm
  loses its garlic (−$245,060 → $407,817); pinned at 18 → **$652,831.24 (−$45)**. ⚠️ Found on the
  way: a cliff between 18.03 ac ($652,854) and 18.06 ac ($642,759) — not the barn (binds on both
  sides; a 5% bigger barn keeps the cliff); a property of the model at that acreage, unexplained.
- **Refusals name the cause.** Pre-solve: the EXACT acres (patches + carry-in pins, all standing in
  week 1) against land and FX.4's Hall's condition, as before. Floors are not pre-checked — a
  second model of the land rows would have to stay in step with C1 (`/simplify`, altitude); the
  solve's diagnosis names land with its weeks instead. Post-solve, on infeasible: (1) re-solve
  with every commitment released — one registry by commitment id (`held`: the plantings whose
  bounds it pins, the rows it adds, its label), which FX.3's per-entry with/without delta reuses
  to release ONE; if a plan exists, (2) the **elastic re-solve**: every LIMIT row (land per zone, labour, water, cold and
  ambient storage, plant/harvest acres per week, cash, diversity) gets a slack in units of its
  limit's largest weekly capacity, commitments stay hard, Σ slack minimised. Result
  `binding_limits: [{limit, unit, weeks, max_over}]` (adapter forwards it) + one sentence. If even
  that is infeasible, the commitments contradict each other (e.g. a standing floor above an exact
  carry-in) and the message says so. Measured: **45 ac overwintered garlic needs the fall crew
  (weeks 29, 47–49, ≤176 h) AND the barn (weeks 29–31, ≤29.7 m³) together** — the toy's finding,
  reproduced in the app. 25 ac is refused for the crew in week 48 alone: the fall-replant check.
  Both diagnostic solves are capped at `DIAGNOSIS_TIME_LIMIT` (20 s) and skipped when the caller
  passes `diagnose_infeasible=False` — the one-more-head re-solves and Monte Carlo draws, which
  read only the status. (A draw that cannot solve is still SKIPPED by the client: BACKLOG X10.)
- **Lot size.** A carry-in pinned BELOW the crop's minimum planting has no C10 minimum (1 ac in
  the ground against a 2-ac lot is a fact; the old floor rounded it up to the lot, reserving a
  fall replant nobody asked for). At or above the lot the minimum stays: one planting meets it,
  and an unneeded exemption opened degenerate optima (measured: a covered-tunnel test's plan moved).

**`/code-review high` on `11b731a` (2026-10-25): 8 findings; #1 reproduced (every row read "error").**
Fixed: (1) `next_head_deltas` passed `diagnose_infeasible` a second time beside the adapter's own
kwargs → TypeError swallowed per row, so the one-more-head figure vanished in every What-If with
hires (every test stubbed that path) — now set in the kwargs dict; (2) only Monte Carlo skipped the
diagnosis — `solveForNumbers` now skips it by default and the labour-plan panel, which SHOWS the
refusal, opts in; (3) `.3g` printed "1.53e+04 L" — plain numbers; (4) a diagnosis that ran out of
time read as "they contradict each other" — `binding_limits_verdict` ∈ proved | unfinished |
contradiction (`_elastic_verdict`, unit-tested: an incumbent stopped by the clock is never
"proved"), and a RELEASE re-solve that times out now says so instead of a bare infeasible;
(6) a floor naming a VARIANT counted the parent's acres — it now counts that variant only (naming
the parent still counts both); (7) `carry-in:` ids are reserved; (8) a weekless limit (diversity)
no longer reads "up to". 13 targeted mutants on the changed code, 13 caught (N7 first survived —
fixed by extracting the verdict).
Deferred: (5) a limit with zero capacity everywhere is weighed in its raw unit, so between two
SUBSTITUTE limits the elastic may prefer the other — same root as M11 (the weighting only matters
for substitutes); one decision for both, with a fixture that has a substitute.

**FX.3 Contracts.** Farm-level `contracts: [{sells_as, channel, lb_per_week, from_week, to_week,
penalty_per_lb}]` → `Σ v[identity,ch,w] + short[k,w] ≥ lb`, `0 ≤ short ≤ lb`, penalty in the
objective and the P&L — ⚠️ **NOT in the C13 weekly cash floor**: charged there, an unavoidable
shortfall at a big penalty made the toy INFEASIBLE (measured at $200/lb), which G3 forbids. It is
settled with the buyer after the season, like interest is post-solve. Result: per contract lb short by week, $ penalty, its KIND
(fact/choice — re-solve at a high penalty; fact if it does not move), and the with/without delta
on the objective. Validate: lb ≤ the identity's cap on that channel (else refuse — a contract
above the market is a typo).

**FX.3 as built (2026-10-26).** `farm_v2/utils/commitments.py` `resolve_contracts` (shape and
identity: crop, channel, `lb_per_week`, `from_week`/`to_week` (may wrap), `mode` REQUIRED ∈
`deliver | penalty`, `penalty_per_lb` > 0 for penalty and refused on deliver); the market check
lives in the SOLVER against the cap table C6/C6b enforce (after the hurdle): a week the channel
takes nothing, a weekly cap below the pounds, an annual cap below the window's total, and a
channel the hurdle dropped are each refused by name. Entries: `{id, kind: "contract", crop,
channel, lb_per_week, from_week, to_week, mode, penalty_per_lb}`; `crop` names a parent (the
identity delivers — a Tunnel Spinach fills a Spinach contract) or a variant (that variant only).
- **Rows C16**: Σ identity sales on the channel (+ `short[k,w]`, penalty mode) ≥ lb, one row per
  window week. `short` ≤ lb; the penalty is in the OBJECTIVE and the P&L
  (`bought_capacity_split["contract_shortfall"]`, inside operating profit) and NOT in C13 nor the
  weekly cash curve — settled after the season. Guard: $2.4M of unavoidable penalty against a
  credit line just above peak borrowing still solves, same plan, same cash curve (⚠️ the golden
  farm's cash floor is OFF — the first version of that guard was inert on the C13 half).
- **Deliver mode** has no slack. A window week nothing can SELL in — no harvest reaches it even
  held to the end of its shelf life (`calendar.sell_weeks_of`, h … h+L−1; C4c is still built
  from the inverse relation, recorded) — is refused by name pre-solve; a contract the crew /
  barn / land cannot carry goes through FX.1's release → elastic path and is named with the
  limit (measured: 20,000 lb/wk of kale weeks 38–50 → labour, weeks 43–50, proved).
- **Shortfall kind.** Each short week is a FACT or a CHOICE: a dead week is a fact outright; for
  the rest ONE probe re-solve at `CONTRACT_PROBE_PENALTY_PER_LB` ($1,000/lb), a week still short
  then being one no plan delivers. Skipped with `diagnose_infeasible=False` → `"unknown"`.
  Measured on the demo: kale on Wholesale 2,000 lb/wk weeks 8–40 at $0.50 → weeks 8–13 and
  **36–37 are facts** (no kale harvest before week 14 and none in 36–37 — the toy's finding,
  reproduced); 4,000 lb/wk weeks 14–35 at 1¢ → 83,500 lb short, all CHOICE; at $0.50 → 298 lb.
  Penalty contracts are `soft` in the `held` registry: released for their delta, never named as
  a refusal's cause.
- **§6.3 per-entry delta — built once for every kind.** `commitment_deltas=True` (opt-in; one
  re-solve per entry, ~4.5 s native / ~18 s in Pyodide each — a total budget is BACKLOG X13)
  returns per id `{label, delta, tolerance, status}`: `delta` = objective WITHOUT − WITH (what
  it costs; a paying patch is negative), `tolerance` = both solves' MIP-gap noise (~$320 on the
  demo; the carry-in read −$71 once). "Without" = pinned planting REMOVED, rows opened both ways
  (a carry-in freed only below stays capped at its pin — measured: pinned at 10 ac the delta is
  $80,189, i.e. the cost of being held to 10). One `_solve(c, released, time_limit)` serves the
  FX.1 release, the probe and the deltas.
- **Result**: `contracts: [{id, source, crop, channel, mode, lb_per_week, weeks, penalty_per_lb,
  owed_lbs, delivered_lbs, short_lbs, penalty_cost, short_kind ∈ fact|choice|mixed|unknown|None,
  by_week: [{week, owed, delivered, short, kind}]}]`, `commitment_deltas` (None unless asked).
  Adapter forwards both; `fields.js` declares `commitment_deltas` (unsent until the UI step).
  Overhead ledger EXCLUDES the shortfall line; P&L label added (it renders under "Bought
  Capacity" — a group label is the UI step's, X12).
- **Guards:** `tests/test_contracts.py` (36). `/simplify` (4 lenses) moved the market check out of
  the resolver and into the solver against the enforced table, folded three `milp` calls into
  `_solve`, one `weeks_text` for every week list, dead weeks classified without the probe, shared
  `commitments_farm`/`weekly` test helpers. **22 targeted mutants, 22 caught** after two
  survivors: the cash-floor guard above, and a penalty-sign mutant mapped to a guard that could
  not see it. Golden unchanged (no contracts → no columns, no rows).
- Deferred, recorded: `diagnose_infeasible` now also gates the probe — a rename-with-alias (X11);
  P&L group label (X12); a total budget for the deltas (X13); C4c built from `sell_weeks_of`.
- **`/code-review high` on `3e68faa` (2026-10-26): 8 findings, 6 fixed, 1 recorded, 1 skipped.**
  Fixed: (1) `next_head_deltas` forwarded the adapter's `commitment_deltas` — every one-more-head
  re-solve would have run one 45 s re-solve per commitment and thrown it away (the FX.1
  `diagnose_infeasible` omission, repeated); now set off there and in the client's
  `solveForNumbers`. (4) Two contracts on ONE market (a parent's and a variant's, two kale
  buyers) each fit the cap alone and not together → was a bare elastic "contradiction"; now
  checked jointly per identity × channel × week and per year, refused naming both. (5) Dead
  weeks counted plantings the model had bounded to 0 (a crop with no carry-in) — a deliver
  contract on it now refused by name. (6) HiGHS status 3/4 on a delta re-solve read
  "time_limit"; now "error". (7) The probe priced every contract at $1,000 at once, so a week the
  crew cannot fill for two contracts read "fact" for one although dropping the other delivers
  it — now one probe PER contract, the others at the grower's price. (2) `SHORT_TOL_LB` 0.01 →
  1 lb (one MIP gap at the probe price is 0.06 lb); at the grower's price the reported shortfall
  is the plan's real slack, kept. Recorded: (3) a sub-lot carry-in's C10 exemption survives its
  "without" re-solve → **X14**. Skipped: (8) `resolve_contracts` runs in validation and the
  solver — the deliberate fail-open pattern floors and blocks already use. 4 new mutants + 8
  re-run on touched code: 12/12 caught (26 in all).

**FX.7 Guards (same commits).** A golden FIXTURE farm with a zone, a variant, a perennial, both
floor kinds and a contract (the L4 trap: the shipped golden uses none of it, so it can stay
unchanged at $652,831.24 — FX.1's carry-in pin is the one FX change it saw — and is then blind to all of this). Mutation-tested per the CLAUDE.md order
(working code → `/simplify` → guards). Toy-vs-app cross-check on the fixture where shapes allow.

**FX.7 as built (2026-10-26).** `tests/helpers.py` `fx_farm()` + `FX_COMMITMENTS` (the shared
fixture data — the asparagus card and blocks, the kale annual floor, `variant_of`, the pin
tolerances and `assert_pnl_line`/`assert_pnl_identities` — now live there, imported by the golden,
perennial, variant, commitment, contract and zone tests); `tests/test_fx_farm.py` (17 guards).
The farm: golden + a covered 2-ac tunnel (every crop confined to the open field, kale in both — the
toy's one split crop — the variant in the tunnel) + the toy's Tunnel Spinach + asparagus 3 ac
bearing / 1 ac establishing + kale `must_stand` 8 ac **weeks 24–30** + `must_plant_annual` 45 +
the toy's three contracts (kale WS 1,500 lb/wk W20–40 and spinach WS 2,000 W28–36 at $0.50;
asparagus WS 500 W18–25 deliver) + garlic's 18-ac carry-in. **Pinned profit $619,491.10**
(golden unchanged, $652,831.24); ~6 s vs 3 s (only kale's slots double — deferral 5 watched).
- **Measured first, each piece removed:** zones → tunnel spinach 6.8→73.9 ac; variant −$35,902;
  perennial +$35,200; floors +$34,962 (annual $31,801, standing $512 vs $318 noise); contracts
  +$10,625 ($6,500 penalty). Kale short in **36–37**, spinach in **35–36** — the toy's two dead
  windows, reproduced; the asparagus must-deliver binds every week.
- **The toy's kale standing floor (W10–20) was INERT here** — the annual floor already stands
  19–24 ac of kale there (own delta $44). A fall window (W40–44 / W42–46) is REFUSED: kale's
  harvest crew collides with garlic's replant in week 48 — the FX.1 fall-crew check, working.
  Weeks 24–30 stand 6.0 ac without the floor and exactly 8.0 with it. Liveness guards pin each
  piece to BIND (floors met exactly, deliver filled exactly, tunnel at its acres, both spinaches
  at the shared cap in one week), so the pin cannot go quiet the way the golden's did.
- **Toy-vs-app cross-check (the one shape allows):** the asparagus must-deliver is the same
  card, block and contract in both models and nothing else touches asparagus, so its with/without
  cost is self-contained — toy **$2,001.00** = hand derivation (1,150 lb diverted × $2.25 gap ×
  (1 − 16% overhead) − 1,150 × $0.15 packaging) to the cent; app $1,953–2,049 ± $318 MIP noise.
  Three legs, so two models agreeing on a wrong number cannot pass (FX.2's lesson).
- **Finding → BACKLOG X15:** removing the bearing patch is INFEASIBLE in the delta table (c3
  depends on it) — honest, unexplained; the UI step needs wording and the diagnosis.
- **Mutation run — the L4 proof (9 mutants, ~45 s wall, repo copies):** zone RHS → whole farm,
  tunnel gets rain, caps keyed by name, perennial extra free, patch may grow, floors dropped,
  penalty free, contracts don't bind: **FX CAUGHT 8/8, plain golden SURVIVED 8/8**; the carry-in
  ceiling control is caught by both. `/simplify` (4 lenses) ran BEFORE the mutants per the
  CLAUDE.md order: it folded four copies of `standing`/`planted` (two keyed on the name, two on the
  crop field), two toy loaders, the pin assertion and the identities into helpers.
- **`/code-review high` on the diff (2026-10-26): 9 findings, all applied.** The two that mattered,
  reproduced: (1) the kale annual-floor guard summed NINE schedule rows each rounded to 0.1 ac
  against a 0.15 tolerance — it landed on 45.0 by luck; `planted()` now reads the solver's own
  `crop_contribution[…]["acres_planted"]` (unrounded, exact to 1e-6) for every caller; (2) the
  shared FM-cap constant read the golden payload at IMPORT of helpers, so a missing payload would
  have broken every module at collection instead of skipping — now a function. Also: SPEC said
  "unchanged at $652,876" beside the new $652,831.24 (FX.1 moved it −$45); the pin's $24,460 of
  overtime recorded beside the $6,500 penalty (a ~$24k break can be the overtime price); one
  name-keyed garlic filter switched to the crop field; `TUNNEL_AND_FIELD` named for what both
  tests mean; importorskip before the module-level payload build; two lint blanks. Skipped:
  caching the payload reads (measured 0.04 ms each). Re-ran the two touched mutants: caught.

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
