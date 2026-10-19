/**
 * Cloudflare Worker entry — Farm Optimizer.
 *
 * Routing model (Workers + Static Assets):
 *   /api/auth/*  → Better Auth handler (Google sign-in, callback, session, sign-out)
 *   /api/*       → app API (health, scenarios, chat)
 *   else         → the static app (public/), gated behind login
 *
 * The solver + Monte Carlo run client-side in the browser (Pyodide); this Worker
 * only does I/O-bound work (DB, auth, LLM proxy), which keeps it on free/cheap tiers.
 */
import { createAuth } from "./auth";
import { handleScenarios } from "./routes/scenarios";
import { handleChat } from "./routes/chat";
import { json } from "./http";
import { smokeBypassActive } from "./smoke";

export interface Env {
  // Static assets binding (public/).
  ASSETS: Fetcher;
  // Secrets — set in .dev.vars (local) / `wrangler secret put` (prod).
  DATABASE_URL: string; // Neon Postgres connection string
  BETTER_AUTH_SECRET: string; // openssl rand -base64 32
  BETTER_AUTH_URL: string; // http://localhost:8787 (local) / deployed origin (prod)
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  // LLM proxy (chatbot step). Default = Upstage SolarPro 3.
  LLM_BASE_URL: string;
  LLM_MODEL: string;
  LLM_API_KEY: string;
  // Local smoke test only — see worker/smoke.ts. Never set in .dev.vars or in production.
  SMOKE_TEST_BYPASS?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const auth = createAuth(env);

    // Better Auth owns everything under /api/auth/*.
    if (url.pathname.startsWith("/api/auth/")) {
      return auth.handler(request);
    }

    // App API.
    if (url.pathname.startsWith("/api/")) {
      return handleApi(request, env, url, auth);
    }

    // Static app — gated behind login (pilot access control + protects the app).
    if (smokeBypassActive(env, url)) return env.ASSETS.fetch(request);
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session) return loginPage();
    return env.ASSETS.fetch(request);
  },
};

async function handleApi(
  request: Request,
  env: Env,
  url: URL,
  auth: ReturnType<typeof createAuth>,
): Promise<Response> {
  // Public — confirms the Worker is running (no auth required).
  if (url.pathname === "/api/health" && request.method === "GET") {
    return json({ ok: true, service: "farm-optimizer", ts: Date.now() });
  }

  // Everything below requires a logged-in user.
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) return json({ error: "Unauthorized" }, 401);

  if (url.pathname === "/api/scenarios") {
    return handleScenarios(request, env, session.user.id, url);
  }
  if (url.pathname === "/api/chat") {
    return handleChat(request, env);
  }

  return json({ error: "Not found" }, 404);
}

/** Minimal login screen served to unauthenticated visitors. */
function loginPage(): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Farm Optimizer — Sign in</title>
  <style>
    body { margin:0; min-height:100vh; display:grid; place-items:center;
      font-family: system-ui, -apple-system, sans-serif; background:#f4f1ea; color:#1f2937; }
    .card { background:#fff; padding:2.5rem 2.75rem; border-radius:14px; max-width:380px;
      box-shadow:0 10px 30px rgba(0,0,0,.08); text-align:center; }
    h1 { font-size:1.4rem; margin:0 0 .4rem; }
    p { color:#6b7280; margin:0 0 1.6rem; font-size:.95rem; }
    button { display:inline-flex; align-items:center; gap:.6rem; cursor:pointer;
      border:1px solid #d1d5db; background:#fff; color:#1f2937; font-size:1rem;
      padding:.7rem 1.2rem; border-radius:10px; font-weight:600; }
    button:hover { background:#f9fafb; }
    .err { color:#b91c1c; font-size:.85rem; margin-top:1rem; min-height:1rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Farm Crop-Mix Optimizer</h1>
    <p>Private pilot — sign in to continue.</p>
    <button id="go" onclick="signIn()">
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path fill="#4285F4" d="M17.6 9.2c0-.6-.1-1.2-.2-1.7H9v3.4h4.8a4.1 4.1 0 0 1-1.8 2.7v2.2h2.9c1.7-1.6 2.7-3.9 2.7-6.6z"/><path fill="#34A853" d="M9 18c2.4 0 4.5-.8 6-2.2l-2.9-2.2c-.8.5-1.8.9-3.1.9-2.4 0-4.4-1.6-5.1-3.8H.9v2.3A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.9 10.7a5.4 5.4 0 0 1 0-3.4V5H.9a9 9 0 0 0 0 8z"/><path fill="#EA4335" d="M9 3.6c1.3 0 2.5.5 3.4 1.3l2.6-2.6A9 9 0 0 0 .9 5l3 2.3C4.6 5.2 6.6 3.6 9 3.6z"/></svg>
      Sign in with Google
    </button>
    <div class="err" id="err"></div>
  </div>
  <script>
    async function signIn() {
      const btn = document.getElementById('go'); btn.disabled = true;
      try {
        const res = await fetch('/api/auth/sign-in/social', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ provider: 'google', callbackURL: '/' })
        });
        const data = await res.json();
        if (data && data.url) { window.location.href = data.url; return; }
        throw new Error(data && data.message ? data.message : 'Sign-in failed');
      } catch (e) {
        document.getElementById('err').textContent = String(e.message || e);
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
}
