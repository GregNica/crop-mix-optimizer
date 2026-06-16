import { and, eq, desc } from "drizzle-orm";
import { getDb } from "../db";
import { scenarios } from "../db/schema/app";
import { json } from "../http";
import type { Env } from "../index";

/**
 * Saved scenarios, always scoped to the authenticated user.
 *   GET    /api/scenarios            → list {id, name, createdAt, updatedAt}
 *   GET    /api/scenarios?name=...    → load one (full form_state)
 *   POST   /api/scenarios            → upsert {name, formState} on (userId, name)
 *   DELETE /api/scenarios?name=...    → delete one
 */
export async function handleScenarios(
  request: Request,
  env: Env,
  userId: string,
  url: URL,
): Promise<Response> {
  const db = getDb(env);

  if (request.method === "GET") {
    const name = url.searchParams.get("name");
    if (name) {
      const rows = await db
        .select()
        .from(scenarios)
        .where(and(eq(scenarios.userId, userId), eq(scenarios.name, name)))
        .limit(1);
      if (rows.length === 0) return json({ error: "Not found" }, 404);
      return json({ scenario: rows[0] });
    }
    const rows = await db
      .select({
        id: scenarios.id,
        name: scenarios.name,
        createdAt: scenarios.createdAt,
        updatedAt: scenarios.updatedAt,
      })
      .from(scenarios)
      .where(eq(scenarios.userId, userId))
      .orderBy(desc(scenarios.updatedAt));
    return json({ scenarios: rows });
  }

  if (request.method === "POST") {
    const body = (await request.json().catch(() => null)) as
      | { name?: unknown; formState?: unknown }
      | null;
    const name = typeof body?.name === "string" ? body.name.trim() : "";
    if (!name || body?.formState == null) {
      return json({ error: "name and formState are required" }, 400);
    }
    await db
      .insert(scenarios)
      .values({ userId, name, formState: body.formState })
      .onConflictDoUpdate({
        target: [scenarios.userId, scenarios.name],
        set: { formState: body.formState, updatedAt: new Date() },
      });
    return json({ ok: true, name });
  }

  if (request.method === "DELETE") {
    const name = url.searchParams.get("name");
    if (!name) return json({ error: "name is required" }, 400);
    await db
      .delete(scenarios)
      .where(and(eq(scenarios.userId, userId), eq(scenarios.name, name)));
    return json({ ok: true });
  }

  return json({ error: "Method not allowed" }, 405);
}
