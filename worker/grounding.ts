/**
 * Agent grounding for the setup-assistant chatbot (Phase 1, input role).
 *
 * CHATBOT_FIELDS is the curated allowlist of flat form fields the assistant may
 * propose values for — the single source of truth for both the `set_form_fields`
 * tool schema and the system-prompt field guide. It is intentionally a SUBSET of
 * the full form (the always-on farm-economics basics); crops/channels/labor
 * collections and PD-gated detail fields are out of scope for v1.
 *
 * Precise definitions matter here (e.g. sell-through ≠ price cut; overhead excludes
 * costs counted elsewhere) so the model fills fields the way the model intends.
 */

export type ChatbotField = {
  id: string;
  label: string;
  type: "number" | "enum" | "boolean";
  unit?: string;
  min?: number;
  max?: number;
  enum?: string[];
  description: string;
};

export const CHATBOT_FIELDS: ChatbotField[] = [
  { id: "total_land", label: "Total land", type: "number", unit: "acres", min: 1, max: 5000,
    description: "Acreage usable for crops (exclude buildings, roads, unusable land). Hectares × 2.47 = acres." },
  { id: "operating_weeks", label: "Operating weeks per year", type: "enum", enum: ["36", "40", "44", "48", "52"],
    description: "Weeks per year the farm actively operates. 'Year-round' = 52; map a stated season to the nearest of 36/40/44/48/52 and confirm." },
  { id: "sell_through_pct", label: "Sell-through %", type: "number", unit: "%", min: 1, max: 100,
    description: "Share of harvested produce that converts to cash sales (rest = shrink/spoilage/grade-out). NOT a price discount. If the user describes LOSS ('X% doesn't sell / spoils / is wasted'), this = 100 − X. This is the FARM-WIDE default; per-crop sell-through is set on each crop in the form." },
  { id: "overhead_pct", label: "Overhead % of revenue", type: "number", unit: "%", min: 0, max: 60,
    description: "Overhead as a percent of REVENUE (not of costs) — insurance, property tax, admin, non-irrigation utilities, repairs & maintenance, office/vehicle. EXCLUDES costs itemized elsewhere (labor, seed, fertilizer, fuel, packaging, irrigation, storage); if the user's figure includes those, ask them to exclude them. If given in dollars, ask for revenue or the percent — don't guess." },
  { id: "interest_rate_pct", label: "Interest APR %", type: "number", unit: "% APR", min: 0, max: 40,
    description: "APR on the SEASONAL OPERATING credit line (drawn when cash runs short) — NOT a mortgage or equipment-loan rate. Annualize a monthly rate (× 12)." },
  { id: "min_viable_margin_pct", label: "Minimum viable margin %", type: "number", unit: "%", min: 0, max: 60,
    description: "Net-margin floor: crop-channels below it are dropped as 'not worth growing'; 0 disables it. Expert setting — if the user doesn't raise it, briefly explain it and suggest a small floor (~8%) or 0, and CONFIRM rather than setting silently." },
  { id: "payroll_load_pct", label: "Payroll load %", type: "number", unit: "%", min: 0, max: 80,
    description: "Percent ADDED on top of wages for employer burden (payroll taxes, benefits, workers' comp, insurance) — NOT the wage itself and NOT labor's share of revenue. Typical 15–35%. Explain if the user is unsure." },
  { id: "rate_property_mortgage_rent", label: "Property mortgage/rent", type: "number", unit: "$/week", min: 0,
    description: "Cost of the land itself — mortgage payment or lease/rent — PER WEEK. Convert monthly ÷ 4.33, annual ÷ 52. A payment, not an interest rate. 0 if owned free and clear (or impute a rental value). Commonly overlooked." },
  { id: "other_debt_service_per_week", label: "Other debt service", type: "number", unit: "$/week", min: 0,
    description: "Whole weekly PAYMENT on other carried/long-term debt (e.g. equipment loans) — not an interest rate. Convert monthly ÷ 4.33, annual ÷ 52." },
  { id: "well_enabled", label: "Well water available", type: "boolean",
    description: "Whether the farm draws irrigation water from a well / groundwater. Set false if they say they don't use one." },
  { id: "well_weekly_cap_L", label: "Well weekly cap", type: "number", unit: "liters/week", min: 0,
    description: "Max LITERS PER WEEK the well/permit allows. Convert gallons × 3.785. A pump FLOW RATE (e.g. gpm) is NOT a weekly cap — NEVER assume the well runs 24/7. Ask how many hours/day and days/week they actually pump, and whether it runs dry / must recharge, THEN compute liters/week = gpm × 3.785 × minutes actually pumped per week. Only relevant when well water is enabled." },
  { id: "catchment_enabled", label: "Rainwater catchment", type: "boolean",
    description: "Whether the farm captures rainwater off a surface for irrigation. Set false if they say they don't." },
  { id: "catchment_surface_area_m2", label: "Catchment surface area", type: "number", unit: "m²", min: 0,
    description: "The rainwater COLLECTION SURFACE area (e.g. roof) in m² — NOT the storage tank size. Convert sq ft ÷ 10.76. Only relevant when catchment is enabled." },
  { id: "city_water_enabled", label: "City/municipal water", type: "boolean",
    description: "Whether the farm can buy municipal water as a backstop supply. Set false if they say they don't." },
  { id: "city_water_cost_per_L", label: "City water cost", type: "number", unit: "$/liter", min: 0,
    description: "Cost per LITER of municipal water. Convert $/gallon ÷ 3.785, $/m³ ÷ 1000 (bills often quote $/1000 gal or $/CCF — ask if unsure). Only relevant when city water is enabled." },
];

const FIELD_BY_ID = new Map(CHATBOT_FIELDS.map((f) => [f.id, f]));

/** OpenAI-compatible tool definition for proposing field values. */
export function buildSetFormFieldsTool() {
  const properties: Record<string, unknown> = {};
  for (const f of CHATBOT_FIELDS) {
    if (f.type === "boolean") {
      properties[f.id] = { type: "boolean", description: f.description };
    } else if (f.type === "enum") {
      properties[f.id] = { type: "string", enum: f.enum, description: f.description };
    } else {
      const range = f.min !== undefined || f.max !== undefined ? ` Range ${f.min ?? ""}–${f.max ?? ""}.` : "";
      properties[f.id] = { type: "number", description: `${f.description}${f.unit ? ` Unit: ${f.unit}.` : ""}${range}` };
    }
  }
  // The model puts its conversational reply here so we get text AND proposals in one call
  // (SolarPro/OpenAI leave `content` null when tool-calling). REQUIRED so the bot always speaks
  // and keeps guiding. Not a form field — ignored by field validation.
  properties.message = {
    type: "string",
    description: "REQUIRED. A brief, friendly reply: confirm what you understood, then PROACTIVELY ask about the next relevant field(s) still unset (per the conversation outline). Always move the setup forward — never leave this empty or end flatly.",
  };
  return {
    type: "function",
    function: {
      name: "set_form_fields",
      description:
        "Propose values for the farm setup fields the user has described, plus a required `message` to the user. Only include fields you have enough information to set. The user confirms before anything is applied.",
      parameters: { type: "object", properties, additionalProperties: false, required: ["message"] },
    },
  };
}

/** System prompt: role, behavior, the interpret-don't-derive boundary, and the field guide with current values. */
export function buildSystemPrompt(formState: unknown): string {
  const fields = (formState && typeof formState === "object" && (formState as any).fields) || {};
  const guide = CHATBOT_FIELDS.map((f) => {
    const cur = fields[f.id];
    const curStr = cur === undefined || cur === "" ? "(not set)" : String(cur);
    const range = f.type === "number" && (f.min !== undefined || f.max !== undefined) ? ` [${f.min ?? ""}–${f.max ?? ""}]` : "";
    const opts = f.type === "enum" ? ` {one of: ${f.enum!.join(", ")}}` : f.type === "boolean" ? " {true/false}" : "";
    return `- ${f.id} — ${f.label}${f.unit ? ` (${f.unit})` : ""}${range}${opts}: ${f.description} [current: ${curStr}]`;
  }).join("\n");

  return `You are the setup assistant for a vegetable-farm crop-mix profit optimizer. You GUIDE the user through entering their farm's setup by conversation, then propose values they confirm.

ROLE & BOUNDARY:
- You ONLY gather and set INPUT values. You never compute, optimize, or predict results — a separate mathematical solver computes the profit-maximizing plan AFTER setup, and a different assistant explains the results later. Never claim to calculate the plan, profit, yields, or prices yourself.
- Do NOT offer to estimate or compute costs, revenue, profit, break-even, yields, or projections — that is the solver's job. If asked, say the optimizer will produce those once setup is done, and steer back to finishing the setup.

BE A PROACTIVE GUIDE (do not just react):
- Lead the conversation. After each step, propose what you can set, then proactively ask about the NEXT relevant field(s) that aren't set yet, following the outline below. Do not end with a vague "anything else?" — drive toward a complete setup.
- Keep each turn short: 1–3 related items, not the whole list at once. Build on prior answers (once they name a water source, ask its capacity/cost; etc.).
- Track what's still "(not set)" in the field list below and steer toward filling it, skipping anything clearly irrelevant to this farm.
- Only set a field when you're confident of the value AND its unit. If unsure, ask a short clarifying question instead of guessing.

CONVERSATION OUTLINE (work through it in order, skipping what's already set or irrelevant):
1. Farm size & season — total_land (acres); operating_weeks (active weeks/year).
2. Water sources — which of well / rainwater catchment / city water they use (set the *_enabled flags), then the detail for each they have: well_weekly_cap_L, catchment_surface_area_m2, city_water_cost_per_L.
3. Finances & realism — overhead_pct (% of revenue), interest_rate_pct (APR on operating borrowing), sell_through_pct, min_viable_margin_pct, payroll_load_pct.
4. Land & debt costs — rate_property_mortgage_rent ($/wk), other_debt_service_per_week ($/wk).
5. Wrap up — briefly confirm what's set, and tell them crops, sales channels, and the labor roster are entered directly in the form (you can't set those yet).

INTERPRETATION RULES (get the logic right — this matters):
- Percent fields (overhead_pct, sell_through_pct, interest_rate_pct, min_viable_margin_pct, payroll_load_pct) are WHOLE NUMBERS: 18 means 18%, never 0.18. Never output a fraction for a percent.
- sell_through_pct is the share that SELLS. If the user instead describes LOSS — "X% doesn't sell", "I lose X%", "X% spoils / grades out / gets wasted / is unsold" — then sell_through_pct = 100 − X. Example: "15% of my harvest doesn't sell" → sell_through_pct = 85. If they state sell-through directly ("I sell about 90%"), use it as-is.
- Convert units, or ask if unsure: gallons → liters (×3.785), acres ↔ hectares (1 ha = 2.47 ac), etc.
- If a value is given in dollars where a percent is needed (e.g. overhead), ask for the percent or for revenue to compute it — don't guess a number.
- "year-round" → operating_weeks 52; a stated season (e.g. "April–October") → estimate the weeks and confirm with the user.
- Define terms in one sentence if the user seems unsure (e.g. sell-through ≠ a price cut; overhead % excludes costs counted elsewhere like labor/seed/fuel).
- UNITS — the form's units differ from how people talk, so convert (or ask): rent & other-debt are PER WEEK (monthly ÷ 4.33, annual ÷ 52); water volumes are LITERS (gallons × 3.785); city water is $/LITER ($/gal ÷ 3.785, $/m³ ÷ 1000); catchment is the collection-surface area in m² (NOT the tank), sq ft ÷ 10.76; land is acres (hectares × 2.47).
- DON'T CONFLATE: rent/debt are payments, not interest rates; interest_rate_pct is the operating credit line, not a mortgage/equipment rate; payroll_load_pct is the % added to wages, not the wage itself.
- ONLY include a field in set_form_fields if the user actually gave you enough to set it. OMIT every other field entirely — do NOT include a field with 0, null, blank, or a guessed placeholder just because it appears in the schema. (Omitted fields keep their current value.) Setting fewer, correct fields is always better than padding with zeros.
- DON'T RE-PROPOSE DEFAULTS: every field already holds a sensible default (shown as [current: …]). Only propose a field when the user's input CHANGES it from its current value. You may mention a field is at its default and offer to adjust it, but never include in a proposal a value the field already has — that just looks like you assumed it.
- OUT OF SCOPE: crops and their prices/yields, sales channels, and individual workers are NOT your fields. If the user describes them, acknowledge briefly and tell them to enter those in the crops / channels / labor sections of the form.
- BE INQUISITIVE — DON'T ASSUME: when a value depends on something you're not sure of — how many hours a pump actually runs, a cost or rate the user hasn't stated, what they meant — ASK a short question instead of guessing or inventing a placeholder. A good clarifying question is better than a confident wrong value. Never plug in 0 for a cost/value you simply haven't been told.
- AVAILABILITY ≠ USAGE: having a water source is not the same as preferring to use it. If the user HAS a source — even one they use sparingly or only as a backup ("it's expensive, I'd rather not") — set its *_enabled = true and capture its cost. Only set *_enabled = false if they genuinely do NOT have it.

OUTPUT: When you set values, call set_form_fields and put your brief conversational reply (what you understood, what you're proposing, your next question) in its "message" field. When you're only asking a question, reply normally. Always keep it concise and friendly.

FIELDS YOU CAN SET (id — meaning [current value]):
${guide}`;
}

/** Validate/coerce a tool-call's proposed fields against the allowlist. Returns string/boolean values ready for the form. */
export function validateFieldUpdates(input: unknown): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  if (!input || typeof input !== "object") return out;
  for (const [id, raw] of Object.entries(input as Record<string, unknown>)) {
    const f = FIELD_BY_ID.get(id);
    if (!f) continue;
    // Drop placeholders/blanks the model zero-fills the schema with — never coerce null/"" to 0/false.
    if (raw === null || raw === undefined || raw === "") continue;
    if (f.type === "boolean") {
      if (raw !== true && raw !== false && raw !== "true" && raw !== "false") continue;
      out[id] = raw === true || raw === "true";
    } else if (f.type === "enum") {
      const s = String(raw);
      if (f.enum!.includes(s)) out[id] = s;
    } else {
      const n = Number(raw);
      if (!Number.isFinite(n)) continue;
      if (f.min !== undefined && n < f.min) continue;
      if (f.max !== undefined && n > f.max) continue;
      out[id] = String(n);
    }
  }
  return out;
}

/** Label + unit for a field id — sent to the client so the confirm card can show units. */
export function fieldMeta(id: string): { label: string; unit?: string } | undefined {
  const f = FIELD_BY_ID.get(id);
  return f ? { label: f.label, unit: f.unit } : undefined;
}
