# SPEC — Unit System (metric ⇄ imperial) + Declarative Field Registry

**Status:** draft for sign-off (2026-07-24). Pairs with the rent/buy cost-panel redesign, which is built *on top of* this and specced separately. Prereq for that work (audit "A + C" sequencing: foundation first, panels second).

## 0. Goal & scope

A global **metric ⇄ imperial** toggle where every unit-bearing input, tooltip "typical range," result figure, and CSV export responds. Fixes the app's current incoherent hybrid (acres + m³ + liters + lb + mm) and serves metric pilot users (Korea).

**The MILP solver, its payload contract, and the pytest suite DO NOT change.** They stay in fixed *canonical* units; only a thin presentation/conversion layer flips. This pass also delivers the audit's **E5 declarative field registry** as its substrate and unblocks the unit-aware rent/buy panels.

## 1. Canonical units — internal source of truth

Chosen = the solver's **current** units, so nothing below the display layer changes (canonical is internal; cross-dimension "consistency" is irrelevant — only conversion correctness matters):

| Dimension | Canonical | Used by |
|---|---|---|
| Land area | **acre** | C1 land, diversity, irrigation rate |
| Produce mass | **lb** | yields, prices, packaging, demand caps |
| Liquid volume (water, fuel) | **liter** | water supply/caps, fuel |
| Bulk/storage volume | **m³** | harvest/equip/fuel storage capacity + rates |
| Rainfall / length | **mm** | catchment/rainfall |

Currency (`$`) is **orthogonal** and out of scope (a future currency/locale feature — don't conflate with units).

## 2. Display units by system

**Base dimensions:**

| Dimension | Canonical | US / Imperial | Metric | Factor (canonical per display) |
|---|---|---|---|---|
| Land area | acre | acre | hectare | 1 ha = 2.47105 ac |
| Produce mass | lb | lb | kg | 1 kg = 2.20462 lb |
| Liquid volume | liter | US gallon | liter | 1 gal = 3.78541 L |
| Bulk volume | m³ | ft³ *(D1)* | m³ | 1 m³ = 35.3147 ft³ |
| Length | mm | inch | mm | 1 in = 25.4 mm |

**Compound units** (composed from the base factors — one `UNITS` module holds the factors, never hard-code the compounds):

| Field kind | Canonical | Imperial | Metric |
|---|---|---|---|
| Yield | lb/acre | lb/acre | kg/ha (×1.1209) |
| Price / packaging | $/lb | $/lb | $/kg (×2.20462) |
| Irrigation rate | $/acre/wk | $/acre/wk | $/ha/wk |
| Storage rate | $/m³/wk | $/ft³/wk | $/m³/wk |
| Water/fuel rate | $/L | $/gal | $/L |
| Water caps | L/wk | gal/wk | L/wk |
| Storage capacity | m³ | ft³ | m³ |

## 3. Field registry (audit E5)

Replace the DOM-introspecting `buildFieldRegistry()` with a **static `FIELD_REGISTRY`**: each field → `{ id, dimension, canonicalUnit, label, ... }`. `dimension:null` = unitless (counts, %, years, weeks, $/wk fixed). Display unit + factor derive from `(dimension × activeSystem)`. **Boot assert**: every unit-bearing DOM input has a registry entry and vice-versa — catches markup drift and closes the `FORM_STATE_VERSION`-never-read silent-field-drop the audit flagged.

## 4. Data flow — canonical is the source of truth

- **DOM inputs hold DISPLAY values** (natural input UX — the user types in their own unit).
- **Payload build:** convert each field display→canonical via the registry. The solver always receives canonical. *One* conversion point; solver untouched.
- **Unit toggle:** for each unit-bearing field, convert DOM value old→new display (round sensibly), re-render its label + tooltip range; persist `activeSystem` in `APP_STATE` + settings.
- **Serialize:** convert display→canonical, store **canonical** + a `unitSystem` marker; bump `FORM_STATE_VERSION`. **Apply:** convert canonical→current display. → a plan saved in metric loads correctly in imperial. Legacy plans (no marker) = assume today's hybrid = canonical.
- **Results & exports:** convert canonical→display at the render/export boundary; labels and CSV headers carry the display unit.

## 5. Tooltips & "typical range" copy

Labels auto-derive their unit suffix from the registry. The fiddly part is the numeric "typical: $6–15/acre/wk" ranges. Two options: **(a)** tag each range-bearing tooltip with `{value, dimension}` tokens so they convert; **(b)** pragmatic v1 — keep ranges in canonical with a "(benchmark in <canonical unit>)" note, convert later. **Recommend:** token-template the ~15 high-traffic cost tooltips; note-and-defer the rest.

## 6. Chatbot grounding

Send `unitSystem` in the `/api/chat` payload. Server grounding then (a) tells the LLM the active system + display units so it reads "30 ha" / "5 gal/min" correctly, and (b) converts LLM-proposed display values → canonical **before** `validateFieldUpdates`/`validateCropDetail` (which run in canonical). `CHATBOT_FIELDS` gains a `dimension` per field mirroring the registry. Preserves the interpret-don't-derive boundary.

## 7. Rollout (incremental; each step shippable)

1. **`UNITS` module** (factors + `convert(value, dimension, from, to)`) + **`FIELD_REGISTRY`** with canonical units + boot assert. No behavior change.
2. **Payload build reads via the registry** (still emits canonical) — a no-op refactor; pytest + in-browser parity unchanged. *This is where A2's `params` object gets registry-driven.*
3. **Add the toggle** (Settings / header): converts DOM + labels live; default per D2.
4. **Serialize/apply canonicalization** + version bump + legacy handling.
5. **Results + exports** convert.
6. **Tooltip ranges** (token or note).
7. **Chatbot `unitSystem`** wiring.
8. **THEN** the rent/buy cost panels, built unit-aware on this registry (separate pass).

## 8. Decisions (resolved 2026-07-24)

- **D1 — RESOLVED. Area has two granularities** (same physical dimension, different customary units by scale):
  - `area_land` (fields, irrigation) → **acre** ⇄ hectare.
  - `area_floor` (catchment surface; equipment storage once reframed) → **ft²** ⇄ m².
  - Liquid tanks (fuel, water) → **US gallon** ⇄ liter (`vol_liquid`).
  - Harvest storage → **volume** (`vol_bulk`: ft³ ⇄ m³) for now. Physical note: it's the C4 operational cap on *stored produce volume*; floor area can't bound it without an arbitrary stacking height. Revisit in the panel redesign — likely reframe to **pallet positions** or **weight (lb/kg)** it holds (how cold storage is actually sold). Equipment storage → reframe to `area_floor` in that same panel pass (it's a cost-only line, so no constraint impact).
- **D2 — RESOLVED: default = US customary.** Pilot users are mostly US. Ship two clean systems (US customary = acre/lb/gal/ft³/in/ft²; Metric = ha/kg/L/m³/mm/m²), Metric one click away. The current app shows liters/m³ for water/storage, so on the first load after this lands those display in US units (gal/ft³) — acceptable and expected.

## 9. Non-goals (this pass)

Currency conversion; temperature (no field uses it); per-field unit overrides; area sub-units (sq ft / m²); locale number formatting (thousands separators, decimal comma).
