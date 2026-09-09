# autoQuant deployment harness

Turns quant-research pull requests into running paper-trading daemons.

```
  every 30 min                  headless Claude session               detached daemon
┌────────────────┐  PR #n  ┌──────────────────────────┐  merge   ┌──────────────────┐
│ poll_prs.sh    ├────────►│ deploy_agent.sh          ├─────────►│ live/<asset>/    │
│ review queue   │         │  └─ /deploy-strategy n   │          │   <name>/        │
└────────────────┘         └────────────┬─────────────┘          │     runner.py    │
        ▲                               │ invalid                └──────────────────┘
        │                     ┌─────────┴──────────┐
        │                     │                    │
        │            needs-revision            wontfix
        │                     │                    │
        │          ┌──────────▼───────────┐   (terminal, PR
        └──────────┤ revise_agent.sh      │    stays open for
        re-review  │  └─ /revise-strategy │    a human)
                   └──────────────────────┘
```

The loop closes at `needs-revision`: the deployment agent's rejection comment becomes the
revision agent's brief, it does the research work to fix the blocker, pushes to the same
branch and clears the label — which puts the PR back in the review queue. Two rounds, then
`harness:exhausted`.

## Dashboard

```bash
./harness/dashboard.sh start      # http://127.0.0.1:8788
./harness/dashboard.sh status
```

Running strategies with live-vs-backtest metrics, equity sparklines against buy-&-hold, the
PR queue, a research-agent launcher, Claude usage, venue health and a kill switch. Start,
stop, restart, flatten and requeue are all driven from the page.

**Reaching it from your phone.** The dashboard binds loopback plus this host's tailnet
address, and nothing else — the API can place orders and spend money, so it must never land
on a public Wi-Fi interface (verified: it answers on `100.x`, refuses on the LAN address).
This works because `.wslconfig` sets `networkingMode=mirrored`; under WSL's default NAT the
Tailscale address belongs to Windows and is not bindable from inside WSL.

With Tailscale connected on the phone:

```
http://desktop-h0g6rel.taila3b4ab.ts.net:8788      (MagicDNS)
http://100.77.199.114:8788                          (tailnet IP)
```

Verify the bind took with `./harness/dashboard.sh restart` — it prints every address it
listened on, and warns if no tailnet address was bindable.

## Surviving a reboot

```bash
./harness/install_autostart.sh              # systemd units + Windows logon hook
./harness/install_autostart.sh --uninstall
```

Two halves, because neither works alone:

1. **systemd user units** supervise the dashboard, the poller and every strategy with
   `Restart=always`, and `loginctl enable-linger` lets them run with no login session open.
   systemd notices a crash in seconds; the poller's watchdog would take up to 30 minutes, so
   the watchdog now skips anything systemd owns rather than racing it.
2. **A `.vbs` in the Windows Startup folder** boots the WSL distro at logon — WSL does not
   start when Windows boots, so without this nothing comes up until you open a terminal.

`launch_live.sh` and the dashboard buttons keep working unchanged: they detect a systemd unit
and delegate `start`/`stop`/`restart` to `systemctl --user`.

This starts at **logon**, not at boot. If you want the harness running while the machine sits
at the lock screen, `harness/windows_autostart_task.ps1` registers a real at-startup task —
it needs an elevated PowerShell, which is why the installer cannot do it for you.

```bash
systemctl --user status 'autoquant*'
journalctl --user -u autoquant-poller -f
```

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
./harness/launch_research.sh spot-btc "" --require "OOS Sharpe >= 2.0 after 10bp/side"
```

### Seeds vs. acceptance criteria

These are different things and conflating them is how PR #3 happened. It was launched with the
seed `"2+ sharpe strat"`, but the brief tells the agent `$ARGUMENTS` is *"the starting idea,
theme or paper"* — where to look, not a bar to clear. The agent shipped Sharpe 1.63 and said so
in its own log. It was following its instructions; nothing in the pipeline knew a bar existed.

`--require` passes a real gate. It lands in the PR body as a filled-in `## Acceptance criteria`
block, and the deployment agent checks it: `Met: YES` with numbers that miss, or a large
`Variants tried` count with no accounting for selection, is a `needs-revision` blocker — which
routes straight back to the revision agent.

**The PR gate is where this is enforced.** The criteria travel in the prompt and land in the
PR body; the deployment agent is what actually checks them against the report's own numbers.
That ordering is deliberate — an in-session check can only judge what the agent says about its
own results, and this is a domain where the agent is already tempted to overfit.

The briefs also give the researcher explicit licence to fail. A bar that cannot be failed is a
specification for overfitting: the cheapest way to make a number appear is to tune until it
does. So an honest **Failed** write-up satisfies the criteria as fully as clearing them, and
the briefs enumerate what may not be done to reach a number — re-picking splits after seeing
results, dropping periods, relaxing costs, reporting best-of-N as if it were the only run.

`CLAUDE_BIN` selects the binary every agent runs on, so a shell difference between the poller,
systemd and an interactive terminal cannot silently change what the agents are.

There is no spend cap — this runs on a Claude subscription, not metered API credit. The
4-hour timeout is a hang reaper, not a budget.

**One global slot gate** covers research, deploy and revise agents alike (`AGENT_MAX_CONCURRENT`,
default 2): they share a single subscription and each one makes work for the others, so a
per-script counter cannot hold the line. Research is barred from the *last* free slot on
purpose — revision and deployment drain the PR queue and end in a running strategy, while new
research only fills it, so when capacity is tight finishing outranks starting. The slot is an
`flock` held by the agent process itself, so it is released by the kernel when the agent dies,
including on a crash or a reboot. There is no slot cleanup path, by design.

## Sessions, and resuming what got cut off

Every headless run gets a UUID that the harness **mints** and passes in with `--session-id`,
rather than working out afterwards which transcript belonged to which agent. That id joins
three things:

```
harness/state/sessions/<uuid>.json                       what the run was supposed to do
harness/logs/<kind>-<target>-<ts>.log                    what it printed
~/.claude/projects/-home-seleis-autoQuant/<uuid>.jsonl   the resumable conversation
```

which is what makes `claude --resume <uuid>` a recovery mechanism instead of a guess.

```bash
./harness/resume_aborted.sh --list     # what is parked, and why
./harness/resume_aborted.sh            # resume everything cut off by a usage limit
./harness/resume_aborted.sh --all      # ...including timeouts and unfinished runs
./harness/resume_aborted.sh <uuid>     # resume exactly one
```

The dashboard has the same thing as a button. **It is deliberately human-gated**: whether you
have subscription headroom cannot be known from outside an interactive session — the token
counts the dashboard shows are exact for this machine but are *not* your quota — so building
an automatic governor on that number would be worse than not having one. You check `/usage`
and press the button. A premature resume is cheap and self-correcting: it is cut off again in
seconds, goes back to `aborted`, and nothing is lost.

Resuming beats relaunching because a research agent killed at hour three has already pulled
its data, run its failed variants and written down its reasoning. That is all in the
transcript, and `--resume` reads it back.

**How an abort is detected**, strongest evidence first:

1. the structured `--output-format json` result — `is_error`, `subtype`, `terminal_reason`;
2. exit code plus the patterns in `harness/limit_signatures.txt`, a plain file so a newly
   observed wording can be added without touching code;
3. **the side-effect check** — the authoritative one, and the only layer that needs no
   knowledge of Anthropic's error strings. Every agent is *defined* by a side effect: a
   researcher opens a PR, a deployment agent applies a terminal label. Process gone + side
   effect absent = the run did not finish, whatever the log says.

No real usage-limit abort has been observed on this machine yet, so layer 2's patterns are
educated guesses and should be corrected the first time one lands. Layer 3 is what makes the
loop safe without them. A supervisor that is itself killed leaves an entry stuck at `running`;
that is reaped as `orphaned` on the next listing.

A run cut off this way **does not burn a deploy attempt** and the PR is parked with
`harness:paused` rather than released — previously a usage limit was indistinguishable from a
crash, so three limit collisions would permanently mark a healthy PR `harness:failed`.

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
* **sends it back** — labels the PR `invalid` plus either `needs-revision` (a blocker a
  researcher could fix with a keyboard and a backtest) or `wontfix` (structurally undeployable
  on this venue), comments with the blocking reasons quoted line by line, and merges nothing.
  A `needs-revision` PR goes to `revise_agent.sh`; a `wontfix` one waits for a human.

Every sweep also runs a **watchdog** for anything *not* under systemd. Once
`install_autostart.sh` has run, systemd is the supervisor — including of the poller itself —
and the watchdog stands down for those units.

Labels are the state machine, so a PR is never processed twice and the poller survives
restarts:

| Label | Meaning | Poller |
|---|---|---|
| *(none)* | New PR | picks up → deploy |
| `harness:processing` | Agent in flight | skip |
| `harness:paused` | Cut off by a usage limit | skip — the resume button clears it |
| `invalid` + `needs-revision` | Fixable blocker | picks up → revise |
| `revision:1` / `revision:2` | Round counter | — |
| `invalid` + `wontfix` | Structurally undeployable here | terminal |
| `harness:exhausted` | Two revision rounds spent | terminal |
| `harness:failed` | 3 genuine agent failures | terminal |
| `deployed` | Live | terminal, PR merged |

Clear a label to have the PR retried; the dashboard's requeue button does exactly that.

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
| `deploy_agent.sh` | Runs the deployment agent for one PR; claims, supervises, retries |
| `revise_agent.sh` | Runs the revision agent for one sent-back PR; two rounds max |
| `agent_exec.sh` | Runs one headless session and records how it ended (all launchers funnel here) |
| `session_lib.sh` | Session registry, abort classifier, slot gate |
| `gh_lib.sh` | PR label helpers (REST, never the broken `gh pr edit`) |
| `resume_aborted.sh` | Resume sessions that were cut off, rather than restarting them |
| `limit_signatures.txt` | Editable log patterns that mean "cut off by a usage limit" |
| `live_lib.py` | Execution runtime: `MarketData`, `PaperBroker`, `StrategyRunner` |
| `launch_live.sh` | Start/stop/status/logs for deployed daemons |
| `check_symbols.py` | Is this instrument tradable on the venue? (flags ticker collisions and dead listings) |
| `check_credentials.py` | Which Binance account do `.env`'s keys belong to? |
| `dashboard.py`, `dashboard.sh`, `web/` | The control dashboard |
| `metrics.py` | Journal → live Sharpe/CAGR/MaxDD/turnover, and the equity series |
| `launch_research.sh` | Start a quant-research agent, detached and uncapped |
| `install_autostart.sh`, `systemd/` | Reboot survival: systemd units + Windows logon hook |
| `windows_autostart_task.ps1` | Optional true at-boot task (needs elevation) |
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
