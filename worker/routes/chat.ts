import { json } from "../http";
import type { Env } from "../index";
import { buildSetFormFieldsTool, buildCropTools, buildSystemPrompt, validateFieldUpdates, validateCropDetail, fieldMeta } from "../grounding";

/**
 * Setup-assistant chat proxy (Phase 1, input role). Provider-agnostic — speaks the
 * OpenAI-compatible /chat/completions interface, so it works with Upstage SolarPro 3
 * (default), Gemini's OpenAI endpoint, Groq, etc. by swapping LLM_BASE_URL/MODEL/KEY.
 *
 * The LLM key never reaches the browser; this runs in the Worker and is auth-gated by
 * the caller (handleApi checks the session before routing here).
 *
 * Request:  { messages: [{role,content}], formState }
 * Response: { reply: string, fieldUpdates: {id: value} }  — the client confirms before applying.
 */
export async function handleChat(request: Request, env: Env): Promise<Response> {
  if (request.method !== "POST") return json({ error: "Method not allowed" }, 405);
  if (!env.LLM_API_KEY) return json({ error: "The assistant isn't configured yet (no LLM key set)." }, 503);

  const body = (await request.json().catch(() => null)) as { messages?: unknown; formState?: unknown; cropTemplates?: unknown } | null;
  const rawMessages = Array.isArray(body?.messages) ? body!.messages : [];
  const cropTemplates = Array.isArray(body?.cropTemplates)
    ? (body!.cropTemplates as unknown[]).filter((t): t is string => typeof t === "string")
    : [];
  const convo = (rawMessages as any[])
    .filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string")
    .slice(-20)
    .map((m) => ({ role: m.role, content: m.content }));
  if (!convo.length) return json({ error: "No message provided." }, 400);

  const payload = {
    model: env.LLM_MODEL,
    messages: [{ role: "system", content: buildSystemPrompt(body?.formState, cropTemplates) }, ...convo],
    tools: [buildSetFormFieldsTool(), ...buildCropTools(cropTemplates)],
    tool_choice: "auto",
    max_tokens: 1200,
    stream: false,
  };

  // Bound the request so a slow/oversized model response returns a clean message, not a 500.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 40000);
  try {
    let res!: Response;
    for (let attempt = 0; attempt < 3; attempt++) {
      res = await fetch(`${env.LLM_BASE_URL}/chat/completions`, {
        method: "POST",
        headers: { authorization: `Bearer ${env.LLM_API_KEY}`, "content-type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      // Retry transient overload/rate-limit (common on free tiers); break on success or a real client error.
      if (res.status < 500 && res.status !== 429) break;
      // 429 is a per-minute quota, so back off harder than a transient 5xx.
      if (attempt < 2) await new Promise((r) => setTimeout(r, (res.status === 429 ? 3000 : 1200) * (attempt + 1)));
    }
    if (res.status === 429) {
      return json({ error: "The assistant is briefly rate-limited (free tier). Wait a few seconds and try again." }, 429);
    }
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      return json({ error: `Assistant provider error (${res.status})`, detail: detail.slice(0, 300) }, 502);
    }
    const data = (await res.json()) as any;
    const msg = data?.choices?.[0]?.message ?? {};
    let reply = typeof msg.content === "string" ? msg.content : "";
    const proposed: Record<string, string | boolean> = {};
    const cropOps: Array<{ op: "add" | "remove" | "update"; template?: string; name?: string; fields?: Record<string, string> }> = [];
    const allowedTemplates = new Set([...cropTemplates, "New Crop"]);
    for (const call of Array.isArray(msg.tool_calls) ? msg.tool_calls : []) {
      const fnName = call?.function?.name;
      let args: any = {};
      try { args = JSON.parse(call?.function?.arguments || "{}"); } catch { /* ignore malformed args */ }
      if (!reply && typeof args.message === "string") reply = args.message;
      if (fnName === "set_form_fields") {
        Object.assign(proposed, validateFieldUpdates(args)); // `message` isn't an allowlisted field, so it's dropped here
      } else if (fnName === "add_crop") {
        if (typeof args.template === "string" && allowedTemplates.has(args.template)) {
          cropOps.push({ op: "add", template: args.template, name: typeof args.name === "string" && args.name.trim() ? args.name.trim() : undefined });
        }
      } else if (fnName === "remove_crop") {
        if (typeof args.name === "string" && args.name.trim()) cropOps.push({ op: "remove", name: args.name.trim() });
      } else if (fnName === "update_crop") {
        if (typeof args.name === "string" && args.name.trim()) {
          const fields = validateCropDetail(args);
          if (Object.keys(fields).length) cropOps.push({ op: "update", name: args.name.trim(), fields });
        }
      }
    }
    // Drop no-ops: don't surface a field the model just echoed at its current value (that reads as "assuming" defaults).
    const current = (body?.formState && typeof body.formState === "object" && (body.formState as any).fields) || {};
    const fieldUpdates: Record<string, string | boolean> = {};
    for (const [id, val] of Object.entries(proposed)) {
      const cur = (current as Record<string, unknown>)[id];
      const unchanged = typeof val === "boolean" ? cur === val : cur !== undefined && String(cur) === String(val);
      if (!unchanged) fieldUpdates[id] = val;
    }
    if (!reply) {
      const parts: string[] = [];
      const adds = cropOps.filter((o) => o.op === "add").map((o) => o.name || o.template);
      const rems = cropOps.filter((o) => o.op === "remove").map((o) => o.name);
      const upds = cropOps.filter((o) => o.op === "update").map((o) => o.name);
      if (adds.length) parts.push(`add ${adds.join(", ")}`);
      if (rems.length) parts.push(`remove ${rems.join(", ")}`);
      if (upds.length) parts.push(`update ${upds.join(", ")}`);
      if (Object.keys(fieldUpdates).length) parts.push("change some settings");
      reply = parts.length ? `Sure — I'll ${parts.join(" and ")}. Review and apply below.` : "Got it. What would you like to set up next?";
    }
    const meta: Record<string, { label: string; unit?: string }> = {};
    for (const id of Object.keys(fieldUpdates)) {
      const m = fieldMeta(id);
      if (m) meta[id] = m;
    }
    return json({ reply, fieldUpdates, fieldMeta: meta, cropOps });
  } catch (e: any) {
    if (e?.name === "AbortError") {
      return json({ error: "The assistant took too long to respond — try a shorter or simpler message." }, 504);
    }
    return json({ error: "Could not reach the assistant.", detail: String(e?.message || e) }, 502);
  } finally {
    clearTimeout(timer);
  }
}
