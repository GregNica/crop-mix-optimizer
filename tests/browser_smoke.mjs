/* THE SHIPPED ARTIFACT, BOOTED IN A REAL BROWSER (PLAN 1.4 / T4).
 *
 * Every other tier — pytest over farm_v2/, jsdom over the client, blob/payload sync — runs a
 * PIECE of the app. jsdom cannot run Pyodide, which is why E2 sat "unverified in the browser" for
 * four weeks and the hidden-tab Monte Carlo stall reached a grower with 407 tests green. This
 * starts the real Worker (wrangler, on its own port, gate bypassed for localhost only — see
 * worker/smoke.ts), opens the page in headless Chromium and requires, in run order:
 *
 *   1. Pyodide boots and `run_from_js` is the farm_v2.adapter module (the E2 boot path);
 *   2. the demo farm's OPERATING profit — what HiGHS optimises — matches the golden pin
 *      (tests/test_golden_farm.py) within the solver's own optimality gap, NOT to the dollar:
 *      Pyodide's HiGHS and native SciPy's both stop within mip_rel_gap = 1e-4 and land on different
 *      near-optimal plans (measured 2026-10-19 on a byte-identical payload: operating $22 apart,
 *      net $32 — the BROWSER finds the better plan). Net profit is not bounded by that gap (overhead
 *      and interest are charged after the solve), so it is checked by its IDENTITY instead, and
 *      both deltas are printed every run;
 *   3. the waterfall image actually decoded (non-zero natural size);
 *   4. Monte Carlo completes while the page reports hidden AND requestAnimationFrame never fires —
 *      what Chromium does to a background tab, so this pins 0a3c15b (a frame-only yield stalled
 *      dead). SIMULATED: headless Chromium, old or new mode, never hides a background tab
 *      (measured). It does NOT cover background TIMER throttling (the 2026-10-19 change): headless
 *      does not throttle, so a timer-based yield passes here too;
 *   5. the in-page self-tests (window._testWhatIf, ~650 console.asserts) reach their end marker
 *      and add NO NEW failure. They had never run automatically; 34 were already failing silently
 *      when this first ran. KNOWN_FAILING is a strict RATCHET (BACKLOG T8): a new failure fails,
 *      and so does a known one that starts passing — strike it — except ids listed as FLAKY.
 *      They get their own freshly booted page: they rewrite the form and globals, a solve after
 *      them hangs, and seven more fail after a solve;
 *   6. ZERO console errors / uncaught exceptions on either page, and every 401 is an /api/* call —
 *      the bypass deliberately does not cover the API (it needs a real user).
 *
 * Assertions are on RENDERED STATE, never on page source — a smoke test that greps the HTML
 * passes against a broken page (E2's innerHTML self-tests, five times).
 *
 * Run: npm run test:smoke   (needs network for the Pyodide CDN; ~2 min. First run on a fresh
 *      checkout: npx playwright install chromium)
 */
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';

const PORT = Number(process.env.SMOKE_PORT || 8799);
const BASE = `http://localhost:${PORT}`;
// The `profit` line of the GOLDEN dict specifically — not the first "profit": in the file.
const GOLDEN_SRC = fs.readFileSync(new URL('./test_golden_farm.py', import.meta.url), 'utf8')
  .match(/^GOLDEN = \{[^}]*\}/m)[0];
const pin = key => Number(GOLDEN_SRC.match(new RegExp(`"${key}":\\s*([\\d_.]+)`))[1].replace(/_/g, ''));
const PIN = pin('profit'), PIN_OP = pin('operating_profit');

// Pre-existing in-page self-test failures (unique ids) — BACKLOG T8. Strike an id when it heals.
const KNOWN_FAILING = new Set(['T34d', 'T57b', 'T88b', 'T88e', 'T110a', 'T114b', 'T116a', 'T116b', 'T116c',
  'T116e', 'T120d', 'T124a', 'T126b', 'T126d', 'T131d', 'T133d', 'T133e', 'T143e', 'T144a', 'T150c', 'T152a',
  'T160d', 'T167b', 'T167c', 'T167e', 'T170a', 'T170b', 'T170c', 'T176a', 'T178', 'T179a', 'T184a', 'T184c',
  'T185b']);
const FLAKY = new Set(['T144a']);   // passed in one measured run, failed in the next

let failures = 0;
const ok = (name, cond, detail = '') => {
  console.log(`${cond ? '  ✓' : '  ✗'} ${name}${cond ? '' : ` — ${detail}`}`);
  if (!cond) failures++;
};

// A stale server on the port means testing OLD code (the 2026-07-31 incident) — refuse.
const free = await new Promise(r => { const s = net.createServer().once('error', () => r(false))
  .once('listening', () => s.close(() => r(true))).listen(PORT, '127.0.0.1'); });
if (!free) { console.error(`port ${PORT} is busy — stop whatever holds it first`); process.exit(2); }

const wrangler = spawn('npx', ['wrangler', 'dev', '--port', String(PORT), '--var', 'SMOKE_TEST_BYPASS:1'],
                       { stdio: ['ignore', 'pipe', 'pipe'], detached: true });
// wrangler runs in its OWN process group (so one kill takes npx and workerd with it), which also
// means Ctrl-C never reaches it — and an orphan would keep serving an UNGATED app on this port.
const stop = () => { try { process.kill(-wrangler.pid, 'SIGTERM'); } catch {} };
process.on('exit', stop);
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { stop(); process.exit(130); });
let log = '';
await new Promise((resolve, reject) => {
  const t = setTimeout(() => reject(new Error(`wrangler did not start in 90s:\n${log.slice(-800)}`)), 90_000);
  const watch = d => { log += d; if (/Ready on/.test(d)) { clearTimeout(t); resolve(); } };
  wrangler.stdout.on('data', watch); wrangler.stderr.on('data', watch);
  wrangler.on('error', e => { clearTimeout(t); reject(e); });
  wrangler.on('exit', code => { clearTimeout(t); reject(new Error(`wrangler exited (${code}):\n${log.slice(-800)}`)); });
}).catch(e => { console.error(String(e.message)); stop(); process.exit(2); });

const browser = await chromium.launch();
const api401 = [];
/** Open a page that records its own console errors, failed asserts and log lines. A 401 console
 *  line is dropped here; the response listener below checks every 401 BY URL instead. */
async function openPage(ctx) {
  const p = await ctx.newPage();
  const rec = { errors: [], asserts: [], logs: [] };
  p.on('console', m => {
    const text = m.text();
    if (m.type() === 'assert') rec.asserts.push(text);
    else if (m.type() === 'error') { if (!/status of 401/.test(text)) rec.errors.push(text.slice(0, 200)); }
    else rec.logs.push(text);
  });
  p.on('pageerror', e => rec.errors.push(`[uncaught] ${e.message}`.slice(0, 200)));
  p.on('response', r => { if (r.status() === 401) api401.push(new URL(r.url()).pathname); });
  await p.goto(`${BASE}/`);
  // Checked BEFORE waiting on Pyodide: a broken gate serves the sign-in page, which never sets
  // pyReady, and would otherwise surface as a 3-minute "Pyodide" timeout that names the wrong thing.
  if (/Sign in/.test(await p.title())) throw new Error('the gate served the sign-in page — the smoke bypass is not active');
  await p.waitForFunction(() => window.pyReady === true, null, { timeout: 180_000 })
    .catch(e => { throw new Error(`Pyodide never became ready (${e.message.split('\n')[0]})`); });
  return { p, rec };
}

try {
  const ctx = await browser.newContext();
  // 1. Boot.
  const { p: page, rec: main } = await openPage(ctx);
  ok('Pyodide boots and run_from_js is farm_v2.adapter',
     await page.evaluate(() => window.pyodide.runPythonAsync('run_from_js.__module__')) === 'farm_v2.adapter');

  // 2–3. Solve the shipped demo farm; the waterfall must decode.
  await page.evaluate(() => runOptimizer());
  await page.waitForFunction(() => window._lastRes && document.getElementById('chart-waterfall').complete
                                   && document.getElementById('chart-waterfall').naturalWidth > 0,
                             null, { timeout: 180_000 })
    .catch(e => { throw new Error(`the solve did not finish with a drawn waterfall (${e.message.split('\n')[0]})`); });
  const r = await page.evaluate(() => window._lastRes);
  const gap = 1e-4 * Math.abs(PIN_OP);   // HiGHS mip_rel_gap, on the quantity HiGHS optimises
  ok(`operating profit matches the golden pin within the MIP gap ` +
     `(delta $${(r.operating_profit - PIN_OP).toFixed(2)}, gap $${gap.toFixed(0)}; net delta $${(r.profit - PIN).toFixed(2)})`,
     Number.isFinite(r.operating_profit) && Math.abs(r.operating_profit - PIN_OP) <= gap, `got ${r.operating_profit}`);
  const net = r.operating_profit - r.overhead_cost - r.fixed_selling_cost - r.interest_cost;
  ok('net profit is operating profit less overhead, fixed selling and interest',
     Math.abs(r.profit - net) < 0.01, `profit ${r.profit} vs ${net}`);
  const [w, h] = await page.evaluate(() => {
    const i = document.getElementById('chart-waterfall'); return [i.naturalWidth, i.naturalHeight]; });
  ok('the waterfall image decoded', w > 0 && h > 0, `${w}x${h}`);

  // 4. Monte Carlo with the page HIDDEN and frames PAUSED (simulated — see the header).
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    window.requestAnimationFrame = () => 0;          // Chromium pauses rAF in a background tab
    document.dispatchEvent(new Event('visibilitychange'));
    const s = document.getElementById('mc-n-sims'); s.add(new Option('3', '3')); s.value = '3';
    runMonteCarlo();
  });
  // Read the RESULTS element, not document.body: the body holds the app's own <script>, whose
  // results template contains 'Scenarios run', so a body-wide search passed with every draw failed.
  await page.waitForFunction(() => !document.getElementById('btn-run-mc').disabled &&
                                   /Scenarios run\s*3\b/.test(document.getElementById('mc-results').textContent),
                             null, { timeout: 240_000 })
    .then(() => ok('Monte Carlo completes with the page hidden and frames paused', true),
          e => ok('Monte Carlo completes with the page hidden and frames paused', false, e.message));

  // 5. The in-page self-tests, on their own freshly booted page in a NEW context — the first page
  //    autosaved a draft to localStorage when it went 'hidden', and shared storage would make the
  //    ratchet depend on step order.
  const { p: testPage, rec: tests } = await openPage(await browser.newContext());
  await testPage.evaluate(() => window._testWhatIf());
  ok('the self-test suite reached its end marker (no swallowed throw cut it short)',
     tests.logs.includes('[self-test] what-if suite complete'));
  const failedIds = new Set(tests.asserts.map(a => a.split(':')[0]));
  const fresh = [...failedIds].filter(id => !KNOWN_FAILING.has(id));
  ok(`in-page self-tests: no NEW failure (${failedIds.size} known)`, fresh.length === 0,
     tests.asserts.filter(a => fresh.includes(a.split(':')[0])).slice(0, 4).join(' | '));
  const healed = [...KNOWN_FAILING].filter(id => !failedIds.has(id) && !FLAKY.has(id));
  ok('KNOWN_FAILING is current (strike healed ids)', healed.length === 0, healed.join(', '));

  // 6. Nothing else went wrong on either page.
  const errors = [...main.errors, ...tests.errors];
  ok(`zero console errors (${errors.length})`, errors.length === 0, errors.slice(0, 4).join(' | '));
  ok('every 401 was an /api/* call the bypass does not cover',
     api401.every(p => p.startsWith('/api/')), JSON.stringify(api401));
} catch (e) {
  // A timeout is a FAILED CHECK, reported like any other — not a stack trace the reader must decode.
  ok('the smoke run completed', false, String(e.message).split('\n')[0]);
} finally {
  await browser.close();
  stop();
}
console.log(failures ? `\nbrowser smoke: ${failures} FAILED` : '\nbrowser smoke: all checks passed');
process.exit(failures ? 1 : 0);
