# RESEARCH BRIEF — practice coverage for a small/medium mixed-vegetable planning model

Written 2026-07-29. Intended for an external research model. Self-contained: you do not need
the application source. Everything about the model's current capability is stated in §4 and §5.

Deliverable: a prevalence-ranked practice table (§6). Not a survey essay.

---

## 1. TASK

Determine **which real-world farming practices are common among small/medium mixed-vegetable
farms**, and for each one, whether the planning model described in §4 can express it.

The motivating observation from the product's grower-advisor: a small/medium farm is not a
scaled-down large farm, but it does **selectively adopt individual large-farm practices for
individual crops or operations**. Examples given verbatim:

- contract/custom labour hired for strawberries and nothing else
- a U-pick operation alongside conventional sales
- a water-wheel transplanter *rented* just for field cabbage and brassicas
- a potato digger brought in only for the potato harvest

The hypothesis to test and extend: **these are not farm-wide settings.** They attach to a
(crop × operation) pair and carry a cost basis of own / rent / contract. Confirm, refute, or
complicate this with evidence, and find the practices we have not thought of.

## 2. THE FARM WE ARE BUILDING FOR — do not drift from this

- Mixed/diversified **vegetables**. Not commodity row crops, not orchards, not livestock.
- **Small to medium.** Roughly 20–150 acres in cultivation is the current design assumption.
  Test that assumption against the data; report the actual size distribution.
- Some amount of **manual labour**, **crop rotation**, and **crop diversity**.
- **Local/direct sales channels** — wholesale, farmers market, CSA, restaurants, farm store.
- The grower knows their accounts, their crew and their ground far better than any benchmark.

We are **not** retargeting to large-scale farms. The question is which large-farm practices show
up *inside* this population, and how often.

## 3. SCOPE

- **Geography:** United States is the primary evidence base. USDA hardiness **zone 7** is the
  reference zone (mid-US). South Korea is a secondary pilot geography — include Korean evidence
  where it exists and is findable, but do not block on it, and keep it in a clearly separate
  section. Do not generalise US practice data to Korea.
- **Out of scope:** market sizing, willingness to pay, pricing, competitor analysis. Do not
  research who would buy the software.
- **Out of scope:** plot/field-level modelling (soil type, pest pressure, drainage, sunlight per
  plot). This is a deliberate product non-goal. You may note where a practice *requires* it, but
  do not recommend building it.

## 4. WHAT THE MODEL CAN EXPRESS TODAY — the exact input schema

This is the complete set of inputs. If a practice cannot be described using these fields, it is
**not expressible**, and that is a finding. Field names are given verbatim.

### 4.1 Farm-level scalars

```
total_land, climate_zone, sell_through_fraction, overhead_pct_of_revenue,
interest_rate_apr, other_debt_service_per_week, min_viable_margin_pct, payroll_load_pct,
cost_fert_per_lb, cost_fuel_per_L,
harvest_storage_cap, rate_harvest_storage,
ambient_storage_cap, rate_ambient_storage,
equip_storage, rate_equip_storage,
fuel_storage, rate_fuel_storage,
water_storage_capacity, rate_water_storage,
rate_irrigation, rate_machinery, rate_property_mortgage_rent,
well_enabled, well_weekly_cap_L,
city_water_enabled, city_water_cost_per_L,
catchment_enabled, catchment_surface_area_m2
```

Plus opening cash and a credit line. Each `rate_*` for a physical asset is derived from a capital
cost and a depreciation life — i.e. **every asset is modelled as owned and depreciated.** The only
rental concept in the entire model is `rate_property_mortgage_rent`, a single weekly figure for
land occupancy.

### 4.2 Per-crop

```
name, days_to_maturity, planting_weeks, harvest_weeks, seasons[],
yield_per_acre, min_acreage_if_planted, crop_diversity_max,
planting_type ("seed" | "transplant"), seed_transplant_cost_per_acre,
labor_plant, labor_grow, labor_harv,
water_plant, water_grow, water_harv,
fert_plant, fert_grow, fert_harv,
fuel_plant, fuel_grow, fuel_harv,
sales_spread_weeks (shelf life), cold_storage (bool), crop_size_m3_per_lb,
channels{}
```

Critical semantics:

- The crop cycle is **three phases**: plant → grow → harvest. Every resource rate is
  **per acre per week of its phase**, charged once for each week that phase occupies. A crop with
  `planting_weeks: 2` is charged its planting rate twice.
- Total field occupancy is `ceil(days_to_maturity / 7)` weeks. `planting_weeks` does **not** extend
  it — it only moves weeks from the grow bucket into the plant bucket, re-pricing them.
- **Labour is hours × wage only.** There is no other way to express a labour cost.
- `planting_type` exists on every crop and is **read by nothing** in the solver. The
  seed-vs-transplant distinction currently changes no arithmetic.
- `seed_transplant_cost_per_acre` is a **cost**, never a quantity. Seed volume/plant counts are
  not modelled.

### 4.3 Per-channel and per-crop-channel

```
channel:      name, variable_selling_cost_per_lb, fixed_selling_cost_per_wk
crop×channel: price_per_lb, packaging_cost_per_lb, demand_cap_type, weekly_demand_lbs,
              demand season window
```

`demand_cap_type` is `annual | weekly_flat | weekly_varying`. Demand is a **ceiling only** — there
is no way to express an obligation, a commitment, or a must-deliver floor.

**There is no per-channel labour.** `labor_harv` is a crop attribute charged on the crop's entire
harvest regardless of which channel the produce goes to.

### 4.4 Labour

Crew positions, each with:

```
position, type ("salaried" | "hourly"), count, wage, hours_per_week, field_time_pct
```

Plus farm-wide toggles for **overtime** and for **hiring additional hourly labour**, and a
payroll load percentage. Salaried staff are charged their full contract; hourly staff are priced
by hours used. Weekly labour supply is a constraint the plan must fit inside.

### 4.5 The constraint set

Land (weekly), labour (weekly), water (weekly, with rainfall offset), cold storage and ambient
storage (weekly room occupancy), per-crop-channel demand ceilings, crop diversity caps, an
inventory balance with shelf life and waste, minimum acreage if planted, and a weekly cash/credit
constraint with interest.

## 5. KNOWN GAPS — verify these are real gaps, and find the ones not listed

Each of these is believed unexpressible today. For each, tell us **how common the practice is**.
That is the number that decides whether we build it.

1. **No mechanisation level anywhere.** Labour numbers silently mix hand, walk-behind and tractor
   work. There is no field describing how a farm performs an operation.
2. **No establishment method in the math** (`planting_type` unread) — direct-seeded vs
   transplanted changes nothing.
3. **No nursery/propagation** — raising your own transplants (midwinter seeding, heated
   greenhouse, winter fuel, seeding labour, raising loss) has no representation, so "raise your
   own" would read as nearly free.
4. **No contract or custom work priced per unit.** A custom harvest quoted per carton, per ton or
   per acre cannot be entered. Only hours × wage.
5. **No per-channel labour** — U-pick, where the customer performs the harvest, is unexpressible.
6. **No rent-vs-own choice per asset.** Everything is owned and depreciated. Renting a
   transplanter for three weeks, or a potato digger for one, cannot be said.
7. **No herbicide or pesticide cost category.** Fertiliser and fuel exist; crop protection does not.
8. **No insurance** of any kind (crop insurance, liability, equipment).
9. **No year-wrapping seasons.** Nothing can be planted after ~week 45 and overwintering is
   impossible — so fall-planted garlic, overwintered alliums, and cover-crop rotation cannot be
   expressed.
10. **No perennials or carry-over crops** (asparagus, rhubarb, June-bearing strawberries).
11. **Deterministic yields; no crop failure or weather loss** in the plan itself.
12. **No commitment/obligation primitive** — demand is ceilings only, so a signed contract, a CSA
    subscription and an informal restaurant order are all the same object.
13. **No payment terms** — revenue books in the week of sale. Net-30 wholesale, immediate market
    cash, and prepaid CSA are indistinguishable.
14. **No land tenure detail** beyond one weekly rent/mortgage figure — no share-cropping, no
    per-parcel leases, no leased ground with different terms.
15. **No seed/plant quantities**, so a seed order cannot be produced.
16. **Weekly variety requirements** (a CSA box needing N distinct items each week) cannot be stated.

**Actively wanted: gaps not on this list.** The list was assembled by people whose experience is
small-farm and hands-on. Practices common in this population that neither we nor this list
anticipate are the highest-value finding you can return.

## 6. OUTPUT FORMAT

A table, ranked by (prevalence × model impact). Then one record per practice. Do not write an
essay; do not summarise the literature narratively.

For **every** practice, answer all five:

| Field | Requirement |
|---|---|
| **Practice** | Name it concretely. "Custom potato harvest hired by the acre", not "mechanisation" |
| **Prevalence** | What share of the target population does this? **A number with a source.** If no data exists, say "no data found" — do not estimate |
| **Granularity** | Farm-wide, per-crop, per-operation, per-channel, or per-parcel? This determines whether it fits the (crop × operation) hypothesis in §1 |
| **What it changes** | A cost, a constraint, a calendar, or a yield? Be specific — e.g. "replaces labour hours with a per-acre fee in the harvest phase only" |
| **Expressible today?** | Using ONLY the fields in §4. Answer yes / no / partially, and if partially, say exactly what is missing |
| **Cost to ask** | What question would the software have to ask a grower, and could a typical grower answer it from memory? A farmer knows "do you contract your strawberry harvest?" — they do not know their per-acre custom rate off-hand |
| **Sources** | URL or full citation for every factual claim. Note confidence |

## 7. RULES

1. **Do not invent numbers.** Every prevalence figure, cost, or rate must carry a source. "No data
   found" is a valid and useful answer. Fabricated statistics are worse than absence here — this
   project has been burned repeatedly by numbers nobody could check.
2. **Prevalence is the deciding variable.** A fascinating practice done by 2% of farms is a lower
   priority than a dull one done by 60%. Rank accordingly.
3. **You are allowed and encouraged to SUBTRACT.** The application currently asks growers for
   roughly 300 inputs. If the evidence shows this population overwhelmingly does *not* do something
   we model, or could not answer a question we ask, say so explicitly in a separate
   "stop asking for this" section. This is as valuable as anything you add.
4. **Do not produce a practice catalogue.** A list of sixty practices all marked "should support"
   is a failed deliverable. Rank, and be willing to say a practice is not worth modelling.
5. **Distinguish "common" from "important".** Some rare practices dominate a farm's economics when
   present. Flag those separately rather than burying them by prevalence.
6. **Do not propose UI, screens, or wording.** Model semantics only.
7. Where a practice needs plot-level modelling, say so and stop — it is a stated non-goal.

## 8. SUGGESTED STARTING SOURCES

Not exhaustive; find better ones if they exist.

- **USDA Census of Agriculture (2022)** — farm size distribution, vegetable acreage, direct-to-
  consumer and direct-to-retail sales, hired vs contract labour expense, machinery ownership,
  land tenure (owned vs rented), and irrigation.
- **USDA ARMS (Agricultural Resource Management Survey)** — cost structures and input use.
- **USDA NASS Vegetables Annual Summary** — crop-level acreage and practice data.
- **SARE** (Sustainable Agriculture Research & Education) grower surveys and project reports —
  unusually good on diversified small-farm practice.
- **ATTRA / NCAT** — practice-level guidance aimed at exactly this farm size.
- **Cooperative Extension enterprise budgets** (Penn State, Cornell, UC, Rutgers, U. Minnesota)
  — these state assumed practices explicitly, including custom-hire lines and equipment
  assumptions, which is what we need.
- **National Agricultural Statistics Service custom rate surveys** (state-level, e.g. Iowa,
  Kansas, Nebraska) — for what operations are commonly custom-hired and at what basis.
- **Korea:** KREI (Korea Rural Economic Institute), Statistics Korea agricultural census.

## 9. WHAT WE WILL DO WITH THIS

The results are mapped back onto the model by the engineering side: which findings are already
expressible, which are one field away, which collapse into a shared (crop × operation × cost
basis) mechanism, and which need something genuinely new. You do not need to do that mapping —
but the more precisely §6's "expressible today?" and "granularity" columns are answered, the
better that mapping will be.
