/* A HIDDEN TAB MUST NOT THROTTLE A SWEEP — and a VISIBLE one must still paint (Q3 follow-up).
 *
 * WHAT THIS GUARDS. `paintYield` runs once per sweep solve (100 per Monte Carlo). `0a3c15b` raced
 * rAF against a 50 ms timer so a hidden tab no longer STOPPED; but Chromium throttles hidden-tab
 * timers (>= 1 s, then one wake-up per MINUTE after ~5 min hidden), so it CRAWLED instead. When
 * hidden it now yields a MessageChannel task, which timer throttling does not touch.
 *
 * BOTH DIRECTIONS ARE PINNED, because the obvious "fix" for the first breaks the second:
 *   * hidden  — must resolve with rAF AND every timer dead. Any timer arm reintroduces the crawl.
 *   * visible — must NOT resolve while rAF and timers are both dead. A MessageChannel arm raced
 *     in a visible tab resolves at once, beats rAF, and the "Solving…" frame never paints before
 *     the solve freezes the thread.
 * Plus runMonteCarlo's own per-5-draws yield, which was a bare setTimeout.
 *
 * jsdom has no MessageChannel; Node's is supplied, which is the real primitive, not a stub.
 *
 * Run: node tests/yield_client.cjs   (or via pytest: test_node_guards.py)
 */
'use strict';
const { MessageChannel } = require('worker_threads');
const { bootApp } = require('./jsdom_app.cjs');

let failures = 0;
const fail = m => { failures++; console.error('  x ' + m); };

/** Resolve 'resolved' or 'pending' — a real Node timer, outside the window being stubbed. */
const settle = (p, ms = 300) => Promise.race([
  p.then(() => 'resolved'),
  new Promise(r => setTimeout(() => r('pending'), ms)),
]);

(async () => {
  const dom = await bootApp();
  const w = dom.window;
  w.MessageChannel = MessageChannel;

  let hidden = false;
  Object.defineProperty(w.document, 'hidden', { configurable: true, get: () => hidden });
  // Dead rAF and dead timers: nothing the browser could throttle is allowed to fire.
  let timersAsked = 0;
  w.requestAnimationFrame = () => 0;
  w.setTimeout = () => { timersAsked++; return 0; };

  const paintYield = w.eval('paintYield');

  hidden = true;
  const h = await settle(paintYield());
  if (h !== 'resolved')
    fail('hidden tab: paintYield never resolved with rAF and timers dead — a backgrounded '
         + 'Monte Carlo would crawl at one draw per throttled timer');
  if (timersAsked)
    fail(`hidden tab: paintYield armed ${timersAsked} timer(s) — timers are what Chromium throttles`);

  hidden = false;
  const v = await settle(paintYield());
  if (v !== 'pending')
    fail('visible tab: paintYield resolved with no frame and no timer — the spinner frame '
         + 'would never paint before the solve blocks the thread');

  const mc = w.eval('runMonteCarlo').toString();
  if (/setTimeout\s*\(/.test(mc))
    fail('runMonteCarlo yields with setTimeout again — throttled in a hidden tab; use paintYield');
  if (!/await\s+paintYield\(\)/.test(mc))
    fail('runMonteCarlo no longer yields through paintYield between draws');

  w.close();
  if (failures) { console.error(`yield_client: ${failures} failure(s)`); process.exit(1); }
  console.log('yield_client: OK (hidden resolves timer-free, visible waits for a frame, MC loop uses paintYield)');
})().catch(e => { console.error(e); process.exit(1); });
