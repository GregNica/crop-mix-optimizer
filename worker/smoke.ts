/**
 * Local smoke-test access (PLAN 1.4 / T4). The app is gated behind Google sign-in, which a
 * headless browser cannot complete, so the smoke test needs a way past the gate for the STATIC
 * app — and only that, and only on a developer's machine.
 *
 * Both conditions are required:
 *   1. SMOKE_TEST_BYPASS is exactly "1". It is never in .dev.vars or wrangler config: the smoke
 *      test passes it on the command line (`wrangler dev --var SMOKE_TEST_BYPASS:1`), so a plain
 *      `npm run dev` keeps the gate.
 *   2. The request is addressed to localhost. A deployed Worker is never reached as localhost, so
 *      even a mistakenly-set variable in production opens nothing.
 * /api/* is NOT covered — it needs a real user, and the smoke test asserts on its 401s instead.
 * tests/test_smoke_bypass.py pins every combination.
 */
export function smokeBypassActive(env: { SMOKE_TEST_BYPASS?: string }, url: URL): boolean {
  return env.SMOKE_TEST_BYPASS === "1" && (url.hostname === "localhost" || url.hostname === "127.0.0.1");
}
