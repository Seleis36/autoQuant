/*
 * Tests for the dashboard's action dispatch (harness/web/index.html).
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
  style: {}, options: { length: 1 }, dataset: {}, onclick: null,
  classList: { add() {}, remove() {} },
  closest: () => null,
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
         actKey:   typeof actKey   !== 'undefined' ? actKey   : null,
         INFLIGHT: typeof INFLIGHT !== 'undefined' ? INFLIGHT : new Set(),
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

console.log('ok - dashboard action dispatch (7 groups)');
