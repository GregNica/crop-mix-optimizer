/**
 * Screenshot the form in headless Chromium — the layout check jsdom cannot do.
 *
 * jsdom runs the page's JS but has no layout: a checkbox stretched to 100% width, a label clipped
 * in a narrow card or a heading that lost its grid span pass every node guard and are seen by the
 * grower first (2026-10-27: three such defects in one browser pass). This serves public/ on a free
 * port with the login gate bypassed, aborts the Pyodide CDN loads (the form renders before them),
 * and writes PNGs of the parts named in SHOTS to --out (default: /tmp/farm-shots).
 *
 *   node scripts/screenshot_form.mjs                 # all shots
 *   node scripts/screenshot_form.mjs --out ./shots   # elsewhere
 *
 * Open the PNGs (or have the assistant Read them) before asking the grower to look. Needs the
 * repo's Playwright (node_modules/playwright) and its Chromium (`npx playwright install chromium`).
 */
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { connect, createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outArg = process.argv.indexOf('--out');
const OUT = outArg > 0 ? path.resolve(process.argv[outArg + 1]) : '/tmp/farm-shots';
mkdirSync(OUT, { recursive: true });

/** Each shot: a name, page setup (run in the page), and the element to capture. */
const SHOTS = [
  { name: 'plots-card', setup: () => { showSection('farm-basics'); startPlots(); },
    target: () => document.getElementById('zone-list').parentElement },
  { name: 'crop-card', setup: () => { showSection('crops'); const c = document.querySelector('#crop-list .crop-detail'); c.open = true; },
    target: () => document.querySelector('#crop-list .crop-detail') },
  { name: 'perennial-commitments', setup: () => {
      const c = document.querySelectorAll('#crop-list .crop-detail')[1]; c.open = true;
      const box = c.querySelector('[data-f="perennial"]'); box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true }));
    },
    target: () => document.querySelectorAll('#crop-list .crop-detail')[1].querySelector('.crop-commitments-container') },
  { name: 'committed-dashboard', setup: () => {}, target: () => document.getElementById('committed-card') },
];

const freePort = () => new Promise(res => { const s = createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const port = await freePort();
const server = spawn('python3', ['-m', 'http.server', String(port), '-d', path.join(ROOT, 'public'), '--bind', '127.0.0.1'], { stdio: 'ignore' });
const up = () => new Promise(res => { const s = connect(port, '127.0.0.1'); s.once('connect', () => { s.destroy(); res(true); }); s.once('error', () => res(false)); });
for (let i = 0; i < 50 && !(await up()); i++) await new Promise(r => setTimeout(r, 100));

try {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route(/cdn\.jsdelivr|pyodide|cdnjs/, r => r.abort());
  await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);
  for (const shot of SHOTS) {
    await page.evaluate(shot.setup);
    await page.waitForTimeout(250);
    const handle = await page.evaluateHandle(shot.target);
    const el = handle.asElement();
    if (!el) { console.error(`${shot.name}: target not found`); continue; }
    await el.scrollIntoViewIfNeeded();
    await el.screenshot({ path: path.join(OUT, `${shot.name}.png`) });
    console.log(`${shot.name}.png`);
  }
  await browser.close();
} finally {
  server.kill();
}
console.log(`written to ${OUT}`);
