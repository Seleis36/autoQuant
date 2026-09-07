# autoQuant deployment harness

Turns quant-research pull requests into running paper-trading daemons.

```
  every 30 min                      headless Claude session              detached daemon
┌────────────────┐   PR #n   ┌───────────────────────────┐   merge   ┌──────────────────┐
│ poll_prs.sh    ├──────────►│ deploy_agent.sh           ├──────────►│ live/<asset>/    │
│ open PRs, no   │           │  └─ claude -p              │           │   <name>/        │
│ terminal label │           │       /deploy-strategy n   │  or       │     runner.py    │
└────────────────┘           └───────────────────────────┘  invalid  └──────────────────┘
```

## Dashboard

```bash
./harness/dashboard.sh start      # http://127.0.0.1:8787
./harness/dashboard.sh status
```

Running strategies with live-vs-backtest metrics, equity sparklines against buy-&-hold, the
PR queue, a research-agent launcher, Claude usage, venue health and a kill switch. Start,
stop, restart, flatten and requeue are all driven from the page.

**Reaching it from your phone.** The dashboard binds loopback plus this host's tailnet
address, and nothing else — the API can place orders and spend money, so it must never land
on a public Wi-Fi interface. Under WSL's default NAT the Tailscale address belongs to
Windows and is not bindable from inside WSL, so `.wslconfig` has been set to
`networkingMode=mirrored`. Apply it once from PowerShell:

```powershell
wsl --shutdown          # stops every WSL process; restart the daemons afterwards
```

After that, with Tailscale connected on the phone:

```
http://desktop-h0g6rel.taila3b4ab.ts.net:8787      (MagicDNS)
http://100.77.199.114:8787                          (tailnet IP)
```

Verify the bind took with `./harness/dashboard.sh restart` — it prints every address it
listened on, and warns if no tailnet address was bindable.

## Running it

```bash
./harness/poll_prs.sh --start     # detached poller, sweeps every 30 min
./harness/poll_prs.sh --status    # poller + every deployed strategy
./harness/poll_prs.sh --stop
./harness/poll_prs.sh --once      # one sweep; use this form from cron
./harness/deploy_agent.sh 7       # process a single PR by hand
```

To run it from cron instead of as a daemon:

```cron
*/30 * * * * ./harness/poll_prs.sh --once >> harness/logs/cron.log 2>&1
```

Research agents can be launched directly (the dashboard does this for you):

```bash
./harness/launch_research.sh spot-btc                       # pick its own idea
./harness/launch_research.sh fx-majors "carry around NFP"   # with a seed
```

Live strategies are managed independently of the poller:

```bash
./harness/launch_live.sh start   spot-btc/bult
./harness/launch_live.sh status
./harness/launch_live.sh logs    spot-btc/bult
./harness/launch_live.sh stop    spot-btc/bult
```

## What the agent does

`.claude/commands/deploy-strategy.md` is the agent's brief. Per PR it reviews the research,
then either:

* **deploys** — writes `live/<asset-class>/<short-name>/runner.py`, validates it with
  `--check`, commits it to the PR branch, merges the PR into `main` (which closes it),
  labels it `deployed`, and starts the daemon; or
* **flags it invalid** — labels the PR `invalid`, comments with the blocking reasons, and
  leaves it open for the researcher to fix. Nothing is merged.

Every sweep also runs a **watchdog** that restarts any strategy registered but dead, and the
dashboard if it died. Nothing restarts the poller itself — that is systemd's job, and until
those units exist a dead poller stays dead.

Labels are the state machine, so a PR is never processed twice and the poller survives
restarts. `harness:processing` marks an in-flight PR, `harness:failed` a PR the agent could
not finish in `DEPLOY_AGENT_MAX_ATTEMPTS` (3) tries. Clear a label to have the PR retried.

The agent reviews in a `git worktree`, never by checking out a branch in the main working
tree — a branch missing another strategy's `live/` directory would delete it out from under
a running daemon.

## Venue

Everything trades on the **Binance spot testnet** (`https://testnet.binance.vision`) —
spot, long/flat, unlevered. A strategy's weight is the fraction of equity held in the base
asset, in `[0, 1]`.

```bash
.venv/bin/python harness/check_credentials.py   # which account do .env's keys belong to?
.venv/bin/python harness/check_symbols.py BTC-USD ETH-USD
```

Credentials are `BINANCE_SPOT_API_KEY_PAPER` / `BINANCE_SPOT_SECRET_KEY_PAPER` in `.env`,
minted at https://testnet.binance.vision (GitHub login → *Generate HMAC_SHA256 Key*).
Binance runs spot testnet, futures testnet and production as **separate account databases**:
a key from one does not exist on the others, and the "Enable Spot & Margin Trading" checkbox
applies only within the site that issued it. `check_credentials.py` reports which host
recognises a key, so this is never a guess.

Three constraints shape what the agent will accept:

* **Liquid crypto pairs only.** No ETFs, bonds, commodity futures or volatility products, so
  equity/FX/rates/commodity strategies are flagged invalid. The venue does list vestigial
  tokenized-stock pairs (`AAPLBUSDT`, `SPYBUSDT`) with a handful of trades a day — dead
  listings, never a proxy for the equity. Non-traded *signal* inputs (HYG, ^GSPC, DX-Y.NYB)
  are unaffected; they come from yfinance.
* **No shorting and no margin.** A strategy needing a negative weight or leverage > 1× cannot
  be deployed.
* **Testnet klines are simulated** and drift ~1% from the real market. Signals are computed
  from real Binance endpoints (`MarketData(source="public")`) while orders and balances use
  the venue. `MarketData` warns if you ask it for testnet prices.

Market orders pay the taker fee (~10 bp/side), which is usually worse than a research
backtest assumes. The agent reports the gap on the PR rather than blocking on it.

If the account is unfunded or `.env` has no valid spot key, `PaperBroker` degrades to a
**shadow book**: it simulates fills at the live price, persists across restarts, and keeps
the strategy producing a verifiable track. Every journal line and `status` output says which
mode produced it.

## Files

| Path | Role |
|---|---|
| `poll_prs.sh` | 30-minute poller; picks eligible PRs, one sweep at a time via `flock` |
| `deploy_agent.sh` | Runs the headless Claude session for one PR; claims, supervises, retries |
| `live_lib.py` | Execution runtime: `MarketData`, `PaperBroker`, `StrategyRunner` |
| `launch_live.sh` | Start/stop/status/logs for deployed daemons |
| `check_symbols.py` | Is this instrument tradable on the venue? (flags ticker collisions and dead listings) |
| `check_credentials.py` | Which Binance account do `.env`'s keys belong to? |
| `dashboard.py`, `dashboard.sh`, `web/` | The control dashboard |
| `metrics.py` | Journal → live Sharpe/CAGR/MaxDD/turnover, and the equity series |
| `launch_research.sh` | Start a quant-research agent, detached, capped at $10 |
| `state/`, `logs/` | Bookkeeping and session logs (gitignored) |

## Capital

Each strategy gets its own **ledger** — a private base/quote book seeded from an allocated
`capital_usdt` — so many strategies share one testnet account without fighting over it, and
the faucet endowment sitting in that account never inflates anyone's position sizing.

Capital is *allocated, not divided*: deploying or retiring a strategy never resizes the
others, because dividing account equity by the live strategy count would make every strategy
churn its whole position each time an unrelated one came or went. `harness/state/allocations.json`
holds the pool and what is committed; `live_lib.allocate()` refuses to oversubscribe it.

`PaperBroker.reconcile()` compares a ledger against the exchange. Persistent drift means
fills that were not recorded.

## Writing a runner by hand

`live/spot-btc/bult/runner.py` is the reference. A runner supplies `compute_weight(now)` —
returning a target weight in [0, 1] as a fraction of equity — and `StrategyRunner` does the
rest: bar-boundary scheduling, closed-bar-only data, order sizing against exchange filters,
JSONL journalling, restart-safe state, graceful SIGTERM.

```bash
.venv/bin/python live/spot-btc/bult/runner.py --check   # one weight, no orders
.venv/bin/python live/spot-btc/bult/runner.py --once    # one rebalance, then exit
.venv/bin/python live/spot-btc/bult/runner.py           # daemon loop
```

Import the research `strategy.py` rather than restating its signal, and always confirm the
runner's `--check` weight matches the backtest's weight for the same bar before deploying.
