/*
 * Tests for the dashboard's action dispatch and chart helpers (harness/web/index.html).
 *
 * Regression under test: a single module-level `busy` flag guarded act(), so while one
 * request was open every other button was a silent no-op. A restart holds the connection
 * for the whole stop/start cycle -- up to ~25s -- so restarting two different strategies
 * a few seconds apart ran only the first, with no error shown.
 *
 * The page is one HTML file with no build step and no module boundary, so the functions
 * are extracted from its <script> block and evaluated here.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, '..', 'harness', 'web', 'index.html'), 'utf8');
const script = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));

const stubEl = () => ({
  textContent: '', innerHTML: '', title: '', href: '', value: '', disabled: false,
  style: {}, options: { length: 1 }, dataset: {}, onclick: null, onclose: null,
  classList: { add() {}, remove() {} },
  closest: () => null, querySelector: stubEl, appendChild() {}, remove() {},
});

/* Evaluate the page script with a DOM stub, and hand back its internals. */
function loadPage(fetchImpl) {
  const src = script
    // Drop page bootstrap and the render pass: only dispatch is under test.
    .replace(/refresh\(\); setInterval\([^)]*\);\s*$/, '')
    .replace(/async function _refresh\(\)\s*\{[\s\S]*?\n\}/, 'async function _refresh(){}')
    // Tolerant export: against the pre-fix page (which had none of these) the tests
    // must still load and fail on the behavioural assertion, not on a ReferenceError.
    + `\nreturn {
         act,
         actKey:     typeof actKey     !== 'undefined' ? actKey     : null,
         INFLIGHT:   typeof INFLIGHT   !== 'undefined' ? INFLIGHT   : new Set(),
         runningPeak:typeof runningPeak!== 'undefined' ? runningPeak: null,
         indexRange: typeof indexRange !== 'undefined' ? indexRange : null,
         axisPct:    typeof axisPct    !== 'undefined' ? axisPct    : null,
         symLabel:   typeof symLabel   !== 'undefined' ? symLabel   : null,
         corrHeatmap:typeof corrHeatmap!== 'undefined' ? corrHeatmap: null,
         renderTranscript: typeof renderTranscript !== 'undefined' ? renderTranscript : null,
         renderFills:typeof renderFills!== 'undefined' ? renderFills: null,
         heldLegs:   typeof heldLegs   !== 'undefined' ? heldLegs   : null,
         isBasket:   typeof isBasket   !== 'undefined' ? isBasket   : null,
       };`;

  const document = {
    querySelector: stubEl,
    querySelectorAll: () => [],
    addEventListener: () => {},
  };
  return new Function('document', 'fetch', 'setTimeout', 'clearTimeout',
                      'setInterval', 'confirm', src)(
    document, fetchImpl, () => 0, () => {}, () => 0, () => true);
}

/* --- a request that stays open, so a second click lands mid-flight --------------- */
const pending = new Map();
function slowFetch(url, opts) {
  const body = JSON.parse(opts.body);
  const key = body.action + ':' + (body.strategy || body.pr || '');
  return new Promise(resolve => {
    pending.set(key, () => resolve({ json: async () => ({ ok: true, output: 'done' }) }));
  });
}

const page = loadPage(slowFetch);

/* 1. Two restarts on DIFFERENT strategies must both reach the server. */
const a = page.act({ action: 'restart', strategy: 'spot-btc/bult' }, 'restart a');
const b = page.act({ action: 'restart', strategy: 'spot-eth/eth-trend-filter' }, 'restart b');

assert.equal(pending.size, 2,
  'both restarts must be dispatched; the global busy flag dropped the second');
assert.ok(pending.has('restart:spot-btc/bult'));
assert.ok(pending.has('restart:spot-eth/eth-trend-filter'));

/* 2. A second restart of the SAME strategy while one is open must be refused. */
const dup = page.act({ action: 'restart', strategy: 'spot-btc/bult' }, 'restart a again');
assert.equal(pending.size, 2, 'a duplicate action on one strategy must not double-fire');

/* 3. Different actions on the same strategy are independent. */
page.act({ action: 'stop', strategy: 'spot-btc/bult' }, 'stop a');
assert.equal(pending.size, 3, 'stop and restart are different keys and must not collide');

/* 4. Settling frees the key so the same action can run again. */
pending.get('restart:spot-btc/bult')();
await a;
await dup;
assert.ok(!page.INFLIGHT.has('restart:spot-btc/bult'),
  'key must be released once the request settles');

pending.delete('restart:spot-btc/bult');
page.act({ action: 'restart', strategy: 'spot-btc/bult' }, 'restart a once more');
assert.ok(pending.has('restart:spot-btc/bult'), 'dispatchable again after settling');

/* 5. A rejected request must still release its key, or the button jams forever. */
const page2 = loadPage(() => Promise.reject(new Error('offline')));
await page2.act({ action: 'restart', strategy: 'spot-btc/bult' }, 'restart');
assert.ok(!page2.INFLIGHT.has('restart:spot-btc/bult'),
  'a failed request must not leave the action permanently blocked');

/* 6. A non-ok JSON body must not throw while building the toast. */
const page3 = loadPage(async () => ({ json: async () => ({ ok: false, error: null }) }));
await page3.act({ action: 'stop', strategy: 'spot-btc/bult' }, 'stop');
assert.ok(!page3.INFLIGHT.has('stop:spot-btc/bult'));

/* 7. Keys distinguish PR and session targets, not just strategies. */
const k = page.actKey;
assert.notEqual(k({ action: 'requeue_pr', pr: 3 }), k({ action: 'requeue_pr', pr: 4 }));
assert.notEqual(k({ action: 'resume_session', session: 'x' }),
                k({ action: 'resume_session', session: 'y' }));
assert.equal(k({ action: 'poller_start' }), k({ action: 'poller_start' }));
assert.notEqual(k({ action: 'stop', strategy: 'a/b' }), k({ action: 'start', strategy: 'a/b' }));

/* --- chart helpers -------------------------------------------------------------
 * These are the pure parts of the chart layer: the scale clamp that stops every
 * curve being auto-fitted to the same amplitude, the drawdown baseline, the axis
 * formatter, and the correlation matrix. They run without uPlot or a canvas.
 */
const P = page;

/* 8. The y scale never auto-fits a quiet book to the full box. */
{
  const [lo, hi] = P.indexRange(99.9, 100.1);
  assert.ok(hi - lo >= 6, 'a flat book must still be drawn against a >=6pt range, '
    + `got ${hi - lo}`);
  const [wlo, whi] = P.indexRange(96.5, 109.6);
  assert.ok(whi - wlo > hi - lo,
    'a book that moved 13 points must occupy a wider range than one that moved 0.2');
}

/* 9. The start-of-book baseline is always on screen, however far the curve ran. */
for (const [lo, hi] of [[100, 140], [60, 100], [99.99, 100.01], [101, 110]]) {
  const [a, b] = P.indexRange(lo, hi);
  assert.ok(a < 100 && b > 100, `100 must stay inside [${a}, ${b}]`);
}

/* 10. The running peak is monotone, and a gap does not reset it. */
{
  assert.deepEqual(P.runningPeak([100, 105, 102, 108, 103]), [100, 105, 105, 108, 108]);
  assert.deepEqual(P.runningPeak([100, null, 90]), [100, 100, 100]);
  assert.equal(P.runningPeak([null, 100])[0], null, 'a leading gap has no peak yet');
}

/* 11. Axis ticks carry a decimal only when they need one. */
{
  assert.equal(P.axisPct(100), '+0%');
  assert.equal(P.axisPct(102.5), '+2.5%');
  assert.equal(P.axisPct(110), '+10%');
  assert.equal(P.axisPct(97.5), '-2.5%');
}

/* 12. A basket's 521-character symbol string is summarised, not printed. */
{
  assert.equal(P.symLabel({ symbol: 'BTCUSDT' }), 'BTCUSDT');
  const legs = Array.from({ length: 62 }, (_, i) => `C${i}-USD`);
  assert.equal(P.symLabel({ symbol: legs.join('+'), symbols: legs }), '62 instruments');
  assert.equal(P.symLabel({ symbol: legs.join('+') }), '62 instruments',
    'the count must still be derived when meta.json carries no symbols list');
}

/* 13. A pair with no shared bars is hatched, never reported as a correlation of 0. */
{
  const tk = { panel2: '#1c2029', line: '#262c37', pos: '#d03b3b', neg: '#3987e5' };
  const html = P.corrHeatmap({
    'spot-btc/x|spot-btc/y': { corr: 0.7, n: 20 },
    'spot-btc/x|spot-eth/z': { corr: -0.4, n: 20 },
  }, tk);
  assert.ok(html.includes('0.70') && html.includes('-0.40'), 'both pairs are drawn');
  assert.ok(!/>0\.00</.test(html), 'an absent pair must not be drawn as zero');
  const hatched = (html.match(/url\(#nohatch\)/g) || []).length;
  assert.equal(hatched, 2, 'y<->z is unmeasured, so both of its cells are hatched');
  assert.equal(P.corrHeatmap({}, tk), '', 'no pairs at all renders nothing');
}

/* 14. An agent transcript is escaped, folds tool output, and flags failed calls. */
{
  const out = P.renderTranscript({
    kind: 'research', target: 'spot-btc', status: 'done', model: 'claude-opus-5-5', bytes: 2e6,
    entries: [
      { kind: 'user', text: '/spot-btc-quant-research', ts: '2026-09-12T06:31:01Z' },
      { kind: 'assistant', text: 'Plan: <script>alert(1)</script>' },
      { kind: 'tool_use', tool: 'Bash', text: 'ls' },
      { kind: 'tool_result', tool: 'Bash', text: 'a\nb\nc' },
      { kind: 'tool_result', tool: 'Bash', text: 'boom', error: true },
    ] }, '070f152b-1e09-4c67-879d-d5e6ababad96');
  assert.ok(!out.includes('<script>alert'), 'agent text must be escaped, not rendered');
  assert.ok(out.includes('&lt;script&gt;'));
  assert.ok(out.includes('3 lines'), 'tool output is folded behind a line count');
  assert.ok(/<details open><summary>1 line<\/summary>/.test(out), 'a failed call is unfolded');
  assert.ok(out.includes('1 tool call'), 'header counts tool calls');
  assert.ok(out.includes('claude-opus-5-5'), 'header shows the model that actually ran');
  assert.ok(out.includes('data-transcript="070f152b-1e09-4c67-879d-d5e6ababad96"'), 'reload link');
  assert.ok(P.renderTranscript({ error: 'no transcript' }, 'x').includes('no transcript'));
}

/* 15. Trades: a basket fill is a summary line with its legs, never a blank row. The panel
       drew every fill as one instrument's side/qty/price, which a basket rebalance has
       none of, so nine books listed their trades as empty lines. */
{
  assert.ok(P.renderFills, 'renderFills must exist');
  const single = P.renderFills({ total: 3, fills: [
    { ts: '2026-10-22T09:28:10+00:00', side: 'BUY', qty: 0.00196, price: 81756.86,
      weight: 0.25, fee: 0.16, equity: 2499.13 }] });
  assert.ok(single.includes('BUY') && single.includes('81756.86'), 'a fill shows side and price');
  assert.ok(single.includes('latest 1 of 3 fills'), 'says when older fills are not shown');

  const basket = P.renderFills({ total: 1, fills: [
    { ts: '2026-10-22T00:30:00+00:00', side: 'REBAL', legs_total: 23, buys: 9, sells: 14,
      turnover_usdt: 811.14, gross: 1.31, net: 0.334, fee: 0.81, equity: 2514.52,
      backfill: true,
      legs: [{ symbol: 'SHIB-USD', side: 'BUY', qty: 5706407.59, price: 4.99e-6,
               notional: 28.47, target_weight: 0.087 }] }] });
  assert.ok(basket.includes('23 legs') && basket.includes('9 buy') && basket.includes('14 sell'));
  assert.ok(basket.includes('811.14'), 'the rebalance shows its turnover');
  assert.ok(basket.includes('gross 1.31') && basket.includes('net +0.33'));
  assert.ok(basket.includes('SHIB-USD') && basket.includes('5706408'), 'legs, sized readably');
  assert.ok(basket.includes('largest 1 of 23 legs'), 'says the leg list is truncated');
  assert.ok(basket.includes('backfill'), 'a replayed fill is labelled as such');

  assert.ok(P.renderFills({ total: 0, fills: [] }).includes('no fills yet'));
  assert.ok(P.renderFills({ error: 'bad strategy' }).includes('bad strategy'));
}

/* 16. A basket's held legs are its non-zero positions, not the size of its universe. */
{
  const s = { symbols: ['A', 'B', 'C', 'D'], live: { basket: true },
              state: { positions: { A: 1.5, B: 0, C: -2, D: 0 } } };
  assert.equal(P.heldLegs(s), 2);
  assert.equal(P.isBasket(s), true);
  assert.equal(P.isBasket({ symbol: 'BTCUSDT', live: {} }), false);
  assert.equal(P.heldLegs({ ledger: { positions: { A: 0 } } }), 0, 'falls back to the ledger');
}

console.log('ok - dashboard action dispatch + chart helpers (16 groups)');
