import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { getDb } from "./db";
import type { Env } from "./index";

/**
 * Per-request Better Auth factory. A Worker has no process.env, so we build the auth
 * instance from the request's env bindings each time (cheap — no network at construction).
 * Google is the only sign-in method; email/password is off. The handler lives at the
 * default basePath /api/auth/*.
 */
export function createAuth(env: Env) {
  return betterAuth({
    database: drizzleAdapter(getDb(env), { provider: "pg" }),
    secret: env.BETTER_AUTH_SECRET,
    baseURL: env.BETTER_AUTH_URL,
    trustedOrigins: [env.BETTER_AUTH_URL],
    emailAndPassword: { enabled: false },
    socialProviders: {
      google: {
        clientId: env.GOOGLE_CLIENT_ID,
        clientSecret: env.GOOGLE_CLIENT_SECRET,
      },
    },
  });
}
