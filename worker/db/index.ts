import { drizzle } from "drizzle-orm/neon-http";
import { neon } from "@neondatabase/serverless";
import type { Env } from "../index";
import * as appSchema from "./schema/app";
import * as authSchema from "./schema/auth";

// Drizzle client over Neon's HTTP driver — stateless per query, which is exactly
// what a Worker wants (no pooled connections to manage). Schema includes both the
// app tables (scenarios) and the Better Auth tables (user/session/account/verification).
export function getDb(env: Env) {
  const sql = neon(env.DATABASE_URL);
  return drizzle(sql, { schema: { ...appSchema, ...authSchema } });
}
