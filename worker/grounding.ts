/**
 * Agent grounding for the setup-assistant chatbot (Phase 1, input role).
 *
 * CHATBOT_FIELDS is the curated allowlist of flat form fields the assistant may
 * propose values for — it drives both the `set_form_fields` tool schema and the
 * system-prompt field guide. Since E5b it is a VIEW over public/fields.js: every form
 * field there that declares a `chat` block (CROP_DETAIL_FIELDS likewise, from the crop
 * section). It is intentionally a SUBSET of the full form (the always-on farm-economics
 * basics); crops/channels/labor collections and PD-gated detail fields are out of
 * scope for v1.
 *
 * Precise definitions matter here (e.g. sell-through ≠ price cut; overhead excludes
 * costs counted elsewhere) so the model fills fields the way the model intends.
 */

// The field metadata lives in public/fields.js (E5b) — one registry the page, its tests and this
// Worker all read, so a renamed or re-unit-ed field cannot drift between the form and the
// assistant. It attaches to globalThis; this side-effect import is what wrangler bundles.
import "../public/fields.js";

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

type ChatSpec = Omit<ChatbotField, "id">;
const FARM_FIELDS = (globalThis as unknown as {
  FARM_FIELDS: { view(section: "form" | "crop", part: "chat"): Record<string, ChatSpec> };
}).FARM_FIELDS;

// THE ALLOWLIST — which fields the assistant may propose values for, in the order its field
// guide presents them. It lives HERE, not in fields.js, so that widening what the LLM may set is
// an edit to the Worker that review sees; fields.js only says how each field is described.
// tests/test_field_registry.py requires each list to name exactly the fields with a `chat` block.
const CHAT_ALLOWLIST = {
  form: ["total_land", "sell_through_pct", "overhead_pct", "interest_rate_pct", "min_viable_margin_pct",
         "fica_pct", "straight_time_load_pct", "rate_property_mortgage_rent", "other_debt_service_per_week",
         // Batch 2 (R7, W10): the overhead description tells the model to take these OUT of
         // overhead, so it must be able to set them — or they are charged nowhere.
         "rented_acres", "cash_rent_per_acre_yr", "ownership_carrying_pct", "insurance_premium_per_yr",
         "utilities_cost_per_yr",
         "well_enabled", "well_weekly_cap_L", "catchment_enabled", "catchment_surface_area_m2",
         "city_water_enabled", "city_water_cost_per_L"],
  crop: ["yield_per_acre", "days_to_maturity", "planting_weeks", "harvest_weeks", "min_acreage_if_planted",
         "sell_through_pct", "sales_spread_weeks", "seed_transplant_cost_per_acre", "lbs_per_tote",
         "planting_type",
         // R1: the overhead description tells the model crop protection is EXCLUDED from overhead,
         // so it must be able to set it per crop — or the spray bill is charged nowhere.
         "crop_protection_cost_per_acre"],
} as const;

/** The allowlisted fields of one section, described by fields.js. Throws at load if one has no
 *  description there — an allowlisted field the model cannot be told about is a broken tool. */
function chatView(section: "form" | "crop"): ChatbotField[] {
  const specs = FARM_FIELDS.view(section, "chat");
  return CHAT_ALLOWLIST[section].map((id) => {
    if (!specs[id]) throw new Error(`grounding: allowlisted field "${id}" has no chat spec in fields.js`);
    return { id, ...specs[id] };
  });
}

export const CHATBOT_FIELDS: ChatbotField[] = chatView("form");

const FIELD_BY_ID = new Map(CHATBOT_FIELDS.map((f) => [f.id, f]));

/** Per-crop scalar fields the chatbot may update via update_crop. (Per-channel prices, seasons,
 *  and the land-share cap are still form-only for now — they need special widgets.) */
export const CROP_DETAIL_FIELDS: ChatbotField[] = chatView("crop");
const CROP_FIELD_BY_ID = new Map(CROP_DETAIL_FIELDS.map((f) => [f.id, f]));

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

/** OpenAI-compatible tools for adding/removing crops (template-driven, so the model picks a name, not 20 fields). */
export function buildCropTools(cropTemplates: string[]) {
  const templates = [...cropTemplates, "New Crop"];
  return [
    {
      type: "function",
      function: {
        name: "add_crop",
        description:
          "Add a crop to the plan using the closest matching template (this fills realistic agronomy + default per-channel prices; the user fine-tunes in the form). Use 'New Crop' only if nothing matches.",
        parameters: {
          type: "object",
          properties: {
            template: { type: "string", enum: templates, description: "Closest matching crop template, or 'New Crop' for a blank one." },
            name: { type: "string", description: "Optional custom name (defaults to the template name)." },
          },
          required: ["template"],
          additionalProperties: false,
        },
      },
    },
    {
      type: "function",
      function: {
        name: "remove_crop",
        description: "Remove a crop from the plan by its exact current name.",
        parameters: {
          type: "object",
          properties: { name: { type: "string", description: "Exact name of the crop to remove." } },
          required: ["name"],
          additionalProperties: false,
        },
      },
    },
    {
      type: "function",
      function: {
        name: "update_crop",
        description: "Change one or more details of an existing crop (by name). Include ONLY the fields you're changing.",
        parameters: {
          type: "object",
          properties: (() => {
            const p: Record<string, unknown> = { name: { type: "string", description: "Exact current name of the crop to update." } };
            for (const f of CROP_DETAIL_FIELDS) {
              p[f.id] = f.type === "enum"
                ? { type: "string", enum: f.enum, description: f.description }
                : { type: "number", description: `${f.description}${f.unit ? ` Unit: ${f.unit}.` : ""}` };
            }
            return p;
          })(),
          required: ["name"],
          additionalProperties: false,
        },
      },
    },
  ];
}

/** Validate a update_crop tool call's detail fields (excludes `name`). */
export function validateCropDetail(input: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!input || typeof input !== "object") return out;
  for (const f of CROP_DETAIL_FIELDS) {
    const raw = (input as Record<string, unknown>)[f.id];
    if (raw === null || raw === undefined || raw === "") continue;
    if (f.type === "enum") {
      const s = String(raw);
      if (f.enum!.includes(s)) out[f.id] = s;
    } else {
      const n = Number(raw);
      if (!Number.isFinite(n)) continue;
      if (f.min !== undefined && n < f.min) continue;
      if (f.max !== undefined && n > f.max) continue;
      out[f.id] = String(n);
    }
  }
  return out;
}

/** System prompt: role, behavior, the interpret-don't-derive boundary, and the field guide with current values. */
export function buildSystemPrompt(formState: unknown, cropTemplates: string[] = []): string {
  const fs = formState && typeof formState === "object" ? (formState as any) : {};
  const fields = fs.fields || {};
  const currentCrops = Array.isArray(fs.crops) ? fs.crops.map((c: any) => c && c.name).filter(Boolean) : [];
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

COACH — SANITY-CHECK VALUES (you are an expert advisor, not a passive form-filler):
- When the user gives a numeric value — a field OR a crop detail (yield, days-to-maturity, a percent, a cost) — judge whether it's realistic using your agronomic/economic knowledge for THAT specific crop or item.
- If it looks unusual — outside, or at the edge of, the typical real-world range — FLAG it in your message: state the typical range, note that their figure is high or low, and ask them to confirm (e.g. "Field tomato yields usually run ~20,000–40,000 lb/acre; 60,000 is very high — is that right, or did you mean a greenhouse/per-plant figure?").
- Still propose the value anyway (the confirmation card lets them adjust or uncheck it). Coaching means flagging and double-checking, NOT refusing or withholding the proposal. But never silently accept a figure that looks wrong.
- This complements ACT IMMEDIATELY below: you still call the tool in the same turn — you just add the sanity note to your message.

CONVERSATION OUTLINE (work through it in order, skipping what's already set or irrelevant):
1. Farm size — total_land (acres). This is the single most important input; get it first.
2. Water sources — which of well / rainwater catchment / city water they use (set the *_enabled flags), then the detail for each they have: well_weekly_cap_L, catchment_surface_area_m2, city_water_cost_per_L.
3. Finances & realism — overhead_pct (% of revenue), interest_rate_pct (APR on operating borrowing), sell_through_pct, min_viable_margin_pct, payroll_load_pct.
4. Land, ownership & bills — rate_property_mortgage_rent ($/wk), other_debt_service_per_week ($/wk), rented_acres + cash_rent_per_acre_yr ($/acre/YEAR), ownership_carrying_pct, insurance_premium_per_yr ($/YEAR), utilities_cost_per_yr ($/YEAR). Any of these they enter must come OUT of their overhead_pct.
5. Wrap up — briefly confirm what's set, and tell them crops, sales channels, and the labor roster are entered directly in the form (you can't set those yet).

INTERPRETATION RULES (get the logic right — this matters):
- Percent fields (overhead_pct, sell_through_pct, interest_rate_pct, min_viable_margin_pct, fica_pct, straight_time_load_pct, ownership_carrying_pct) are WHOLE NUMBERS: 18 means 18%, never 0.18. Never output a fraction for a percent.
- sell_through_pct is, of what is TAKEN TO MARKET, the share that converts to cash — losses between field and sale ONLY (stall display shrink, samples, transit damage, rejected loads). It is NOT grade-out at harvest (that belongs in yield; lowering both double-counts it) and NOT spoilage in storage (the app has no input for that yet — tell the user so instead of putting it here). Default 100%. Only when the user describes loss AT MARKET — "X% of what I bring to market doesn't sell" — is sell_through_pct = 100 − X. If they state sell-through directly ("I sell about 90% of what I bring"), use it as-is.
- Convert units, or ask if unsure: gallons → liters (×3.785), acres ↔ hectares (1 ha = 2.47 ac), etc.
- If a value is given in dollars where a percent is needed (e.g. overhead), ask for the percent or for revenue to compute it — don't guess a number.
- Define terms in one sentence if the user seems unsure (e.g. sell-through ≠ a price cut; overhead % excludes costs counted elsewhere like labor/seed/fuel).
- UNITS — the form's units differ from how people talk, so convert (or ask): rate_property_mortgage_rent & other-debt are PER WEEK (monthly ÷ 4.33, annual ÷ 52), but cash_rent_per_acre_yr, insurance_premium_per_yr and utilities_cost_per_yr are PER YEAR (monthly × 12) — never ÷ 52 those; water volumes are LITERS (gallons × 3.785); city water is $/LITER ($/gal ÷ 3.785, $/m³ ÷ 1000); catchment is the collection-surface area in m² (NOT the tank), sq ft ÷ 10.76; land is acres (hectares × 2.47).
- DON'T CONFLATE: rent/debt are payments, not interest rates; interest_rate_pct is the operating credit line, not a mortgage/equipment rate; payroll_load_pct is the % added to wages, not the wage itself.
- ONLY include a field in set_form_fields if the user actually gave you enough to set it. OMIT every other field entirely — do NOT include a field with 0, null, blank, or a guessed placeholder just because it appears in the schema. (Omitted fields keep their current value.) Setting fewer, correct fields is always better than padding with zeros.
- DON'T RE-PROPOSE DEFAULTS: every field already holds a sensible default (shown as [current: …]). Only propose a field when the user's input CHANGES it from its current value. You may mention a field is at its default and offer to adjust it, but never include in a proposal a value the field already has — that just looks like you assumed it.
- Sales channels and the labor roster are still entered in the form — you can't edit those yet, so if the user brings them up, say so. (Crops you CAN add and remove — see the CROPS section below.)
- BE INQUISITIVE — DON'T ASSUME: when a value depends on something you're not sure of — how many hours a pump actually runs, a cost or rate the user hasn't stated, what they meant — ASK a short question instead of guessing or inventing a placeholder. A good clarifying question is better than a confident wrong value. Never plug in 0 for a cost/value you simply haven't been told.
- AVAILABILITY ≠ USAGE: having a water source is not the same as preferring to use it. If the user HAS a source — even one they use sparingly or only as a backup ("it's expensive, I'd rather not") — set its *_enabled = true and capture its cost. Only set *_enabled = false if they genuinely do NOT have it.

OUTPUT: When you set values, call set_form_fields and put your brief conversational reply (what you understood, what you're proposing, your next question) in its "message" field. When you're only asking a question, reply normally. Always keep it concise and friendly.

FIELDS YOU CAN SET (id — meaning [current value]):
${guide}

CROPS — you can ADD, REMOVE, and UPDATE crops (channels and labor are still done in the form):
- The farm STARTS with default crops (listed below as "Current crops"). When the user tells you which crops they grow, RECONCILE against that list: add_crop any they grow that aren't already present; and OFFER (via remove_crop) to remove current crops they did NOT mention. Don't silently keep defaults they don't grow, and don't add a crop that's already there.
- ACT IMMEDIATELY: when the user asks to add, remove, or change a crop, call the matching tool right away IN THE SAME TURN. The review card the user then sees IS the confirmation — do NOT ask "are you sure?" or wait for a "yes" first. NEVER describe a crop change in prose without also making the tool call — if you mention adding/removing/changing a crop, the matching tool call MUST accompany it that turn, or no card appears and nothing happens.
- ALWAYS KEEP TALKING after a crop action: in the SAME turn, also call set_form_fields with just your "message" (and no other fields) to confirm what you did and ask the next relevant question. A crop action must never end the turn silently or with a flat reply — stay a proactive guide.
- add_crop: closest matching template (fills agronomy + default per-channel prices the user can fine-tune in the form); use "New Crop" only if nothing fits.
- remove_crop: by exact current name.
- update_crop: change a crop's details by name — yield, days to maturity, planting/harvest weeks, min acreage, per-crop sell-through, sales-spread weeks, seed cost, lbs per tote, planting type. Include only the fields being changed. (Per-channel prices, planting seasons, and the land-share cap are still set in the form for now — say so if asked.)
- Never invent agronomy you weren't given — for adds, the template provides it.
- Current crops: ${currentCrops.length ? currentCrops.join(", ") : "(none)"}.
- Available templates: ${cropTemplates.length ? cropTemplates.join(", ") : "(none provided)"}.`;
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
