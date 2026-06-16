import { config } from "dotenv";
import { defineConfig } from "drizzle-kit";
import { neonConfig } from "@neondatabase/serverless";
import ws from "ws";

// Load secrets from .dev.vars (the same file `wrangler dev` reads) so `npm run db:push`
// gets DATABASE_URL without a separate .env file.
config({ path: ".dev.vars" });

// drizzle-kit runs in Node and uses the Neon serverless driver, which connects over a
// WebSocket. Node has no built-in WebSocket the driver will pick up, so wire one in —
// without this, `db:push` fails with "can only connect ... through a websocket".
// (The Worker runtime uses the HTTP driver and needs none of this.)
neonConfig.webSocketConstructor = ws;

export default defineConfig({
  // Picks up the app schema now, and the Better Auth schema once it's generated
  // into this directory (auth step).
  schema: "./worker/db/schema/*.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url: process.env.DATABASE_URL ?? "" },
});
