// CLI-only entry for `npx @better-auth/cli generate` (schema generation). It reuses the
// runtime factory in worker/auth.ts with process.env, so the auth config has a single
// source of truth. Not imported by the Worker at runtime.
import { config } from "dotenv";
config({ path: ".dev.vars" });

import { createAuth } from "./worker/auth";
import type { Env } from "./worker/index";

export const auth = createAuth(process.env as unknown as Env);
