# SPEC — Batch W: water mode

**Status:** DRAFT 2026-10-24, built on the recommendations below (the grower asked for the batch to
run end-to-end; §2's one finding is flagged for a ruling at the next check). Source: BACKLOG
**BC4** (ruled 2026-10-23, option C), `/code-review max` #15, PLAN "Batch W".

---

## 1. Where the code is today (measured, with refs)

| Thing | Today |
|---|---|
| Sources | Three ticks: Well (`well_enabled`, cap L/wk), Catchment (`catchment_enabled`, roof m²), City (`city_water_enabled`, $/L). `index.html` Water section ~1505 |
| Refusal (D11) | Nothing ticked → refused in THREE places: `validate.py` §3, the solve gate `index.html` ~7708, the section check ~4885 |
| Rain | Never a source. It lowers demand: `net_water_rate = max(0, crop_need − 0.65 × rain)` per succession-week (`utils/water.py`) |
| C3 | `use[w] − city[w] + wstore[w] − wstore[w−1] ≤ free_water[w]` (well + catchment), 52 rows (`solver.py` ~1192) |
| Water money | city water $/L (variable, per litre bought) + city fixed fee (unused by the form) + on-farm `well_cost_per_L` (form never sends it; BC6) + tank and irrigation DEPRECIATION (owned assets — charged whatever is ticked) |

## 2. ⚠️ The ruling's premise is false — measured twice

BC4 says *"the golden farm solves IDENTICALLY ($612,944) with every source off"*. It does not —
at today's tip (`ecd734a`) or at the Batch 2 commit the claim was written against (`f04ccea`):

| Zone (golden farm) | Irrigated | Every source off (refusal bypassed) |
|---|---|---|
| Northeast (shipped) | $652,876 | **−$996,961 — grows nothing** |
| Midwest | $652,876 | −$996,961 |
| California Central Valley | $568,539 | −$996,961 |
| Southwest desert | $570,791 | −$996,961 |

Why: every shipped crop needs 85,000–163,000 L/acre/wk (≈ 0.8–1.6 in), and 65% of Northeast rain
offsets only 50,000–64,000. Net need is positive in **every active week of every succession in
every zone**, and the model has no soil-moisture buffer and no yield-under-deficit curve — a
succession is either fully watered or not grown. So with the model as it stands, a "rain-fed"
farm grows nothing on every built-in climate. −$996,961 "optimal" is exactly the hole D11 closed.

**What this batch does about it (recommended; the grower may overrule at the next check):** keep
all three modes as ruled — the QUESTION is still right, and custom rainfall or a low-need crop can
make rain-fed plantable — but make Rain-fed only honest:
- **Refused, with the reason, when rain alone cannot water ANY succession through its whole
  cycle** (the golden farm's case): *"Rain-fed only: rain alone never covers a whole crop cycle
  here — at best it covers N% of <crop>'s weekly need … Choose Irrigated or Don't limit by water."*
  This is not D11's hole reopened: it is a refusal that names the cause, not a silent grow-nothing.
- When some successions ARE rain-plantable: solve, and say the plan assumes rain alone.
- **Backlog, not this batch:** a real rain-fed model (deficit-yield response, soil buffer). That
  is an agronomy model change with a golden re-pin; it needs its own spec.

## 3. The design

**One question, top of the Water section:** *"How is this farm watered?"* — a select:
`Irrigated — from the sources ticked below` (default) / `Rain-fed only — no irrigation` /
`Don't limit by water`. Payload key **`water_mode`** ∈ `irrigated | rainfed | unlimited`;
ABSENT = `irrigated` (every saved plan, server caller and the golden payload unchanged).

| | Irrigated | Rain-fed only | Don't limit by water |
|---|---|---|---|
| Sources | as ticked; nothing ticked → **refused** (D11 kept) | ignored (adapter clears them) | ignored (adapter clears them) |
| C3 water rows | yes | yes, with supply 0 | **none** |
| City water $/L + fixed fee | if ticked | no | **no** |
| On-farm $/L (`well_cost_per_L`) | charged on net need | charged (0 — only zero-need successions grow) | charged on net need — water you pump still costs, the ask was to drop the LIMIT |
| Tank + irrigation depreciation | charged | charged | charged — owned assets are depreciated whether used or not (cost-accounting basis) |
| Pre-solve | — | refused if no succession is rain-plantable | — |
| Result | — | warning: "plan assumes rain alone" | warning: "water was not limited" |
| Water card / "+10% water" lever | shown | hidden (nothing to relieve) | hidden |

**The two traps (PLAN):**
1. *"Don't limit by water" must drop the limit AND its cost without reopening D11.* — D11's hole
   was an ACCIDENTAL untick solving as grow-nothing. The mode is an explicit choice from a select
   that defaults to Irrigated, so an accidental untick in Irrigated is still refused, in all three
   places, with a message that now names the modes. Direct callers passing a source with a
   non-irrigated mode are REFUSED by `validate.py` (ambiguous intent), never silently resolved;
   only the adapter — the form boundary, where the ticks are just remembered state — clears them.
2. *"Rain-fed only" must SAY the plan assumes rain alone.* — result `warnings` + the inputs
   summary line, and the refusal above when it cannot.

**Plumbing:** `fields.js` form + payload entries (+ a `chat` enum so the assistant can set it, and
the grounding allowlist); `getParams`; section check + solve gate; form-state save/restore
(select, so the existing machinery carries it); `solve_farm_v2(water_mode=…)` → result echoes
`water_mode`; blob + golden payload re-sync (golden payload gains `"water_mode": "irrigated"` —
byte-equal P&L).

## 4. Guards (after `/simplify`, mutation-tested)

- Golden farm: byte-equal with `water_mode` absent and `"irrigated"`.
- Unlimited on the golden farm, Southwest desert, **well cap shrunk until water binds**: profit ≥
  irrigated, no C3 rows, city water $0 even with city ticked in the payload, tank/irrigation
  depreciation unchanged. (Default fixture: water does not bind, so unlimited = irrigated and a
  dropped-C3 mutation would pass — the inert-guard trap; the shrunk well is what makes it bite.)
- Rain-fed on the golden farm: refused with the coverage message. Rain-fed with a custom wet
  rainfall array where SOME successions are plantable: solves, only those are planted, warning
  present. (Two conditions: rain high enough for one crop, not for all.)
- Irrigated + nothing ticked: refused (validate, gate, section check). Non-irrigated + a source
  in a DIRECT solver call: refused. Unknown mode: refused.
- Node: the select round-trips through form state; gate messages; water card hidden off-irrigated.
