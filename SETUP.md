# Farm Optimizer — Server Setup (Phase 1)

The app is a Cloudflare **Worker + Static Assets** project. The Worker serves the
static app (`public/index.html`) and handles `/api/*`. The MILP solver + Monte Carlo
still run **client-side** in the browser (Pyodide) — the Worker never solves.

This guide covers the **hosting slice** (what's built now) and the **accounts** you'll
need for the auth + database + chatbot steps that follow. You can start the signups in
parallel; none are required just to run the app locally.

---

## 1. Prerequisites

- Node.js 20+ and npm.
- Install dependencies:
  ```bash
  npm install
  ```

## 2. Run it locally (hosting slice — works with zero secrets)

```bash
npm run dev          # wrangler dev → http://localhost:8787
```

Verify:
- Open **http://localhost:8787** → the optimizer app loads (same as before).
- Open **http://localhost:8787/api/health** → `{"ok":true,"service":"farm-optimizer",...}`.
- `node tests/form_state_client.cjs` (part of `npm test`) passes — the save/load round-trip check that used to be the `_testFormState()` console helper.

That confirms the Worker serves the static app and routes `/api/*`. Auth, DB, and the
LLM proxy are **not** wired yet — they're the next Phase-1 steps.

## 3. Local secrets

Copy the template and fill in values as each step needs them:
```bash
cp .dev.vars.example .dev.vars        # .dev.vars is gitignored
```
For production, set each instead with `wrangler secret put <NAME>` (never commit them).

---

## 4. Accounts to create (for the upcoming auth/DB/chatbot steps)

You can do these now so we're unblocked when we wire them.

### a) Cloudflare
- A free Cloudflare account. Local `wrangler dev` needs **no login**; only deploying does
  (`npx wrangler login` when we're ready to ship).

### b) Neon (Postgres database — for save/resume)
1. Create a free project at neon.tech.
2. Copy the **pooled** connection string → `DATABASE_URL` in `.dev.vars`.

### c) Google OAuth (login)
1. Google Cloud Console → create/select a project.
2. Configure the **OAuth consent screen** (External; add your email as a test user).
3. Credentials → **Create OAuth client ID** → type **Web application**.
4. Authorized redirect URIs:
   - local: `http://localhost:8787/api/auth/callback/google`
   - prod (later): `https://<your-worker-domain>/api/auth/callback/google`
5. Copy the **Client ID** and **Client secret** → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
6. Generate an auth secret: `openssl rand -base64 32` → `BETTER_AUTH_SECRET`.

### d) Upstage (LLM — default for the chatbot step)
1. console.upstage.ai → create an **API key**.
2. → `LLM_API_KEY`. (`LLM_BASE_URL` and `LLM_MODEL` are already defaulted to SolarPro 3.)
   For free dev testing we can point `LLM_BASE_URL`/`LLM_MODEL` at Gemini's
   OpenAI-compatible endpoint instead to preserve the Upstage credit.

---

## 5. What's next (not wired yet)

In order:
1. **Database** — Drizzle schema (`scenarios` + Better Auth tables) on Neon:
   `npm run db:auth-schema` (generates auth tables) → `npm run db:push`.
2. **Auth** — Better Auth + Google login; gate the app behind login (pilot access).
3. **Chatbot** — the provider-agnostic `/api/chat` proxy (Upstage SolarPro 3 by default)
   with the `set_form_fields` tool + streaming, plus the chat widget.

## Project layout

```
public/index.html      the app (static; solver runs here in the browser)
worker/index.ts        Worker entry — routes /api/*, else serves public/
worker/db/             Drizzle schema + client (added with the DB step)
worker/routes/         API route handlers (added per step)
wrangler.jsonc         Worker + assets config (nodejs_compat enabled)
.dev.vars(.example)    local secrets
```
