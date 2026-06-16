import { pgTable, text, jsonb, timestamp, uuid, uniqueIndex } from "drizzle-orm/pg-core";

/**
 * A saved scenario = the serialized form state (INPUTS ONLY — results re-solve
 * client-side, so we don't store them). Shape matches serializeFormState() from
 * public/index.html.
 *
 * `userId` links to the Better Auth `user` table (added in the auth step). It's kept
 * as plain text here so this app schema stays independent of the generated auth
 * schema; every query scopes by the authenticated userId.
 */
export const scenarios = pgTable(
  "scenarios",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id").notNull(),
    name: text("name").notNull(),
    formState: jsonb("form_state").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow().notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => [uniqueIndex("scenarios_user_name_unique").on(t.userId, t.name)],
);
