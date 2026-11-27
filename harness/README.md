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
        │            needs-revision            archive
        │                     │                    │
        │          ┌──────────▼───────────┐   merged as a
        └──────────┤ revise_agent.sh      │   research record,
        re-review  │  └─ /revise-strategy │   nothing in live/
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

`autoquant-ticks.service` rides along: whenever WSL comes up it mounts the D: tick disk
(through the elevated "autoQuant ticks disk" Windows task, so no UAC prompt) and keeps
`code/shared/tick_backfill.sh --foreground` running — resuming the backfill, then fetching
new data every 6 h. Its log is `harness/logs/ticks.log`; the jobs' own logs are in
`data/ticks/logs/`. See `code/shared/DATA.md` §4.

`launch_live.sh` and the dashboard buttons keep working unchanged: they detect a systemd unit
and delegate `start`/`stop`/`restart` to `systemctl --user`.

This starts at **logon**, not at boot. If you want the harness running while the machine sits
at the lock screen, `harness/windows_autostart_task.ps1` registers a real at-startup task —
it needs an elevated PowerShell, which is why the installer cannot do it for you.

On a **native Linux host** (no WSL) the installer skips the Windows hook and the tick store —
there is no D: disk, and the tick backfill would pull ~330 GB onto the system disk. Linger
alone starts the user manager at boot, so everything is up before anyone logs in.

```bash
systemctl --user status 'autoquant*'
journalctl --user -u autoquant-poller -f
```

### After an outage: backfilling the sim books

A daemon that was down does not trade. On restart it resumes its ledger and acts on the
current bar, so the journal draws a straight line over the outage and every rebalance in
between is lost. For a `sim` book that is unnecessary — its fills are modelled — so replay the
missed bars **before** restarting it:

```bash
.venv/bin/python harness/backfill.py <asset>/<name> --dry-run   # what it would write
.venv/bin/python harness/backfill.py <asset>/<name>
```

It runs the runner's own `compute_weight(s)` once with today's data, keeps the full weight
series the strategy's signal function returned, and refuses unless the series' last row
reproduces the live weight. Each missed bar is then filled through the runner's own broker at
that bar's close (session markets) or at the boundary price (continuous ones). Replayed rows
carry `"backfill": true`. A `backfill` event records the range, and the pre-replay journal,
ledger and state are copied to `harness/state/backfill/`. The inputs are today's vintage of
the data. Venue books are refused: the testnet never filled those orders, so their outage
stays a gap. One strategy per process, daemon stopped.

## Two hosts: the desk and the research host

Since Nov 2026 the harness runs on two machines, chosen by `AQ_ROLE` in each one's `.env`:

| | desk (`AQ_ROLE=desk`) | research host (`AQ_ROLE=research`) |
|---|---|---|
| Machine | the VPS, always on, small disk, runs as root | desktop-h0g6rel (WSL), on some of the time, tick disk on D: |
| Trades | every live strategy, systemd units, watchdog | nothing -- never start a runner here |
| Agents | none: every launcher exits 5 (`no_agents_on_desk`) | research (once a day at most), deploy review, revision |
| Poller | `desk_launch.sh` + `remote_inbox.sh publish` | the review and revision queues, no watchdog |
| Dashboard | served here, behind Cloudflare Access | not run |

Unset means the old single host doing both, which is what the tests run as.

**Deploying across the two.** The deployment agent on the research host reviews, writes the
runner and `meta.json`, validates with `--check`, merges and labels `deployed`. It does not
start anything. On the desk's next sweep `harness/desk_launch.sh` pulls `main`
(fast-forward only), reserves `capital_usdt` in `meta.json`'s `book`, enables and starts the
unit, checks it is RUNNING and labels the PR `vps:launched`. On failure it labels
`vps:launch-failed` and comments why; remove that label to retry. Only PRs merged after
`AQ_DESK_SINCE` are considered, because everything older was already running.

**Logs and transcripts come back over rsync, not git** (the repo is public, and transcripts
contain everything an agent read). The research host pushes over the tailnet as the
unprivileged user `aqsync`, whose key is pinned to `rrsync -munge /var/lib/autoquant-remote`.
That user can read and write files in that directory and has no shell. Setup and keys:
`sudo harness/remote_inbox.sh setup`, `sudo harness/remote_inbox.sh add-key '<pubkey>'`.

    /var/lib/autoquant-remote/desktop/   logs/ sessions/ transcripts/ heartbeat.json   (pushed)
    /var/lib/autoquant-remote/outbox/    allocations.json desk.json requests/          (pulled)

The dashboard merges the synced registry, logs and transcripts into its own lists. Rows are
tagged `desktop`. A synced session marked `running` shows as `aborted · host_offline` once the
heartbeat is older than 10 minutes. The header chip shows whether the research host is on.
On the desk, **Launch** and **Resume** do not run anything locally. They write a request to
`outbox/requests/`, and the research host acts on it at its next sync.

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
./harness/launch_research.sh sector-etf "" --model sonnet
```

### Choosing the model

`--model` takes a **model alias** — `opus` (the default), `sonnet` or `fable` — and the
dashboard's picker offers exactly those three. The dashboard validates against that
allowlist, so the picker cannot ask for something the launcher would refuse. A full id
(`claude-opus-5-5`) still works from the command line.

Aliases, so a new model is picked up without editing the repo: the CLI resolves `opus` to
the newest Opus **it knows about**. That makes the CLI version the thing that decides how
current the agents are. Until 2026-09-24 this machine ran a root-owned npm install that could
not update itself; it sat on 2.1.269 after Opus 5.5 shipped, kept resolving `opus` to Opus 5,
and rejected `claude-opus-5-5` outright. So:

- `CLAUDE_BIN` (session_lib.sh) prefers the user-owned native install at
  `~/.local/bin/claude` (`claude install`), which updates itself without sudo;
- the nightly batch runs `claude update` before launching anything;
- the registry records the model each alias **actually resolved to**, read back from the
  run's result JSON. The sessions table shows it, and the picker shows what each alias last
  ran as, so "latest" can be checked rather than assumed.

**Fable costs real money.** It is not covered by the Claude subscription the rest of this
harness runs on — it bills purchased usage credits, so a four-hour research session on it is a
metered spend where the same session on Opus or Sonnet is not. The picker marks it `($)` and
it is never the default. It also needs Claude Code >= 2.1.251; on an older binary the
dashboard shows it disabled with the version it found and refuses to launch onto it, rather
than letting a detached agent die on its first API call. Running out of credits ("You're out
of usage credits…") is classified as a usage limit, so the session parks as resumable.

All three agents — research, deploy and revise — default to `opus`, overridable with
`RESEARCH_AGENT_MODEL` / `DEPLOY_AGENT_MODEL` / `REVISE_AGENT_MODEL`.

### Nightly research

`autoquant-nightly.timer` runs `nightly_research.sh` at 01:00 local time: two asset classes
per night, **one after the other**. Research holds one of the `AGENT_MAX_CONCURRENT` slots and
a second concurrent launch is refused by design, so deploy/revise work can always start.
Running back to back also spreads the night's usage across the subscription's rolling window.

- **Rotation** — least recently researched first, judged by the newest
  `logs/research-<class>-*.log`. A class you launch by hand counts as its turn; with 11
  classes and two a night, each comes round about every six days.
- **Guards** — skips the night when `NIGHTLY_MAX_OPEN_PRS` (4) PRs are already open; launches
  nothing new after `NIGHTLY_DEADLINE_H` (10) hours; each run keeps the 4h agent timeout.
- **Stranded-work check** — a run the registry calls `done` can still have left its work
  uncommitted or its branch unpushed. The batch log (`logs/nightly-<ts>.log`) says so with a
  `WARNING stranded work` line.
- Knobs: `NIGHTLY_COUNT`, `NIGHTLY_CLASSES`, `NIGHTLY_MODEL` (e.g. `sonnet` to go easier on
  the weekly limit).

```bash
./harness/nightly_research.sh --dry-run                 # what tonight would run
systemctl --user list-timers autoquant-nightly.timer    # when
systemctl --user disable --now autoquant-nightly.timer  # pause it
```

`Persistent=true` means a night missed because the PC was off or asleep runs at the next
start. The timer only fires while WSL is up — the Windows logon hook keeps it up after logon.

### Effort floor on research sessions

Left alone, a research agent would pick one idea, grid it, write it up as Failed and stop —
the first nightly batch produced two PRs 6 and 17 minutes into the run. Two things now push
back, applied by `agent_exec.sh` to every research session, resumes included:

- **`--effort xhigh`** (`RESEARCH_AGENT_EFFORT`). Deploy and revise agents run at `--effort medium`
  (`DEPLOY_AGENT_EFFORT`, `REVISE_AGENT_EFFORT`) so the usage goes to research.
- **A Stop hook**, `research_stop_hook.py`. It refuses to let the session end until
  `RESEARCH_MIN_IDEAS` (5) distinct short names have been worked on, and gives up after
  `RESEARCH_MAX_STOP_BLOCKS` (5) refusals so an agent with nothing left can still finish. An
  idea counts once anything under `code/<class>/<name>/` or `past_research/<class>/<name>/`
  was written since launch — in the working tree, or committed on a local branch. Refusals
  are counted in `state/sessions/<uuid>.stop_blocks`.

The command files say the same thing in words: a shortlist of five ideas up front, and
Failed is a result for one idea, not for the session.

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

which is what makes `claude --resume <uuid>` a recovery mechanism instead of a guess. It
is also what the dashboard's **convo** links read: the launcher's log has only the opening
prompt and the final answer, while the `.jsonl` has every message, tool call and tool output
in between. `transcript.py` renders it (`/api/transcript?session=<uuid>`), with tool output
and thinking folded and anything very long clipped — the full file stays on disk.

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

The only limit wording observed on this machine so far is Fable's "You're out of usage
credits" (2026-09-24); the subscription-limit patterns are still educated guesses and should
be corrected the first time one lands. Layer 3 is what makes the
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
* **sends it back** — comments with the blocking reasons quoted line by line, labels the PR
  `invalid` + `needs-revision`, and merges nothing. `revise_agent.sh` picks it up; or
* **archives it** — merges the research with **nothing in `live/`**, labelled `archived`
  (plus `wontfix` when a Working strategy was structurally undeployable).

**Why a rejected PR still merges.** A research agent's first act is to read
`past_research/<asset-class>/all_ideas.md` on `main` so it does not repeat what has been tried.
Research that never merges is invisible there, so the next agent burns a whole session
rediscovering the same dead end — which is the one thing a negative result exists to prevent.
Closing a PR instead of merging it destroys exactly the output that was worth keeping. So a
Failed write-up, a structurally undeployable strategy, and a blocker that outlived its
revision rounds all merge; only the research record lands, never a runner.

When a **Working** strategy is not deployed, the reviewer marks its `all_ideas.md` row
`**Working — not deployed**` with the reason and appends a `## Deployment review` section to
the report. Without that the next researcher reads "Working", sees nothing live, and has no
idea why.

The merge — not the label — is what ends the job. `review_outcome` in `gh_lib.sh` treats
`archived` on an *open* PR as unfinished, so the poller hands it back and the agent completes
it. Merging is left to the agent rather than enforced by a script because the usual failure is
a conflict in `all_ideas.md`, where two PRs appended a row to one table; keeping both rows
takes judgement.

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
| `archived` (+ `wontfix`) | Merged as a research record; nothing deployed | terminal, PR merged |
| `harness:exhausted` | Two revision rounds spent | terminal |
| `harness:failed` | 3 genuine agent failures | terminal |
| `deployed` | Live | terminal, PR merged |

Clear a label to have the PR retried; the dashboard's requeue button does exactly that.

The agent reviews in a `git worktree`, never by checking out a branch in the main working
tree — a branch missing another strategy's `live/` directory would delete it out from under
a running daemon.

## The two books

A strategy is deployed into one of two books. They differ in what they can express and in
how strong the evidence they produce is.

| | `venue` | `sim` |
|---|---|---|
| What it is | Binance spot testnet, real orders | A self-contained simulated book |
| Instruments | Liquid crypto pairs only | Anything the daily cache prices |
| Direction | Long/flat, weight in `[0, 1]` | Long **and short** |
| Leverage | None | Capped by `max_gross` |
| Sizing | Exchange lot steps, 5 USDT minimum | Fractional |
| Capital | One shared $10k pool — **capped** | Uncapped |
| Broker | `PaperBroker` | `SimBroker` / `SimPortfolioBroker` |

```bash
.venv/bin/python harness/check_credentials.py            # whose account are .env's keys?
.venv/bin/python harness/check_symbols.py --book venue BTC-USD ETH-USD
.venv/bin/python harness/check_symbols.py --book sim   XLK XLE TLT EURUSD=X
```

**Why two.** Paper trading was defined as "the Binance spot testnet account", and three
separable things were welded to it: price discovery, fill simulation, and capital accounting.
Only the last genuinely needs the account. Splitting them is what lifted both limits at once —
the four-strategy ceiling was the shared pool, and the crypto-only ceiling was the venue's
instrument list. Neither applies to a book that has no account behind it.

**What `sim` is not.** There is no order book, no rejection, no partial fill and no queue
position. A simulated track is weaker evidence than a venue-executed one, and the dashboard
labels it `simulated` rather than folding it in with `shadow`. Do not read a `sim` Sharpe as
though it had cleared a real exchange.

What it *is* good at: a simulated fill happens at the close of the bar the signal was computed
on, which is the bar `research_lib.backtest` charges turnover at — so it matches its backtest's
own assumption more closely than a live crypto market order matches its.

### Markets that are not open 24/7

There is no market calendar here, on purpose. Each quote source reports the identity of the
bar its price came from, and the runner rebalances only when that changes. A weekend, a
holiday, a half-day and a data vendor running an hour late are then all the same non-event:
nothing to encode, nothing to keep up to date, and nothing to get wrong. A continuous market
reports no bar identity and trades on every boundary, exactly as it always did.

### The venue book in detail

Spot, long/flat, unlevered. A strategy's weight is the fraction of its own capital held in
the base asset, in `[0, 1]`.

Credentials are `BINANCE_SPOT_API_KEY_PAPER` / `BINANCE_SPOT_SECRET_KEY_PAPER` in `.env`,
minted at https://testnet.binance.vision (GitHub login → *Generate HMAC_SHA256 Key*).
Binance runs spot testnet, futures testnet and production as **separate account databases**:
a key from one does not exist on the others, and the "Enable Spot & Margin Trading" checkbox
applies only within the site that issued it. `check_credentials.py` reports which host
recognises a key, so this is never a guess.

Three constraints shape what the agent will accept *in this book* — each of them a routing
decision now rather than a rejection, since the `sim` book has none of them:

* **Liquid crypto pairs only.** No ETFs, bonds, commodity futures or volatility products. The
  venue does list vestigial tokenized-stock pairs (`AAPLBUSDT`, `SPYBUSDT`) with a handful of
  trades a day — dead listings, never a proxy for the equity. Non-traded *signal* inputs
  (HYG, ^GSPC, DX-Y.NYB) are unaffected; they come from yfinance.
* **No shorting and no margin.** A strategy needing a negative weight or leverage > 1× goes
  to `sim`.
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
| `live_lib.py` | Execution runtime: `MarketData`, quote sources, `LedgerBroker`/`PaperBroker`/`SimBroker`, `StrategyRunner` |
| `portfolio.py` | Cross-sectional execution: `SimPortfolioBroker`, `PortfolioRunner` |
| `launch_live.sh` | Start/stop/status/logs for deployed daemons |
| `check_symbols.py` | Is this instrument tradable in a given book? (`--book venue\|sim`) |
| `check_credentials.py` | Which Binance account do `.env`'s keys belong to? |
| `dashboard.py`, `dashboard.sh`, `web/` | The control dashboard |
| `metrics.py` | Journal → live Sharpe/CAGR/MaxDD/turnover, and the equity series |
| `launch_research.sh` | Start a quant-research agent, detached and uncapped |
| `nightly_research.sh` | The nightly batch: rotate through asset classes, two a night, sequentially |
| `transcript.py` | Renders an agent's full Claude Code transcript for the dashboard |
| `install_autostart.sh`, `systemd/` | Reboot survival: systemd units + Windows logon hook |
| `windows_autostart_task.ps1` | Optional true at-boot task (needs elevation) |
| `state/`, `logs/` | Bookkeeping and session logs (gitignored) |
| `../tests/` | The test suite (see below) |

## Tests

```bash
.venv/bin/python -m pytest              # everything, ~45s
.venv/bin/python -m pytest tests/test_metrics.py -q
```

`pytest` and `node` are the only requirements (`uv pip install pytest`). Nothing in the
suite touches the network, GitHub, systemd or the venue: the broker is driven through a
stubbed HTTP layer, and the shell tests build a throwaway repo under `tmp_path` with a
stand-in daemon rather than driving the real one.

| File | Covers |
|---|---|
| `test_dashboard_api.py` | The JSON API over a real socket: query decoding, validation, traversal |
| `test_dashboard_actions.py` | `POST /api/action` — validation, bulk actions, request limits |
| `test_process_uptime.py` | `/proc` parsing and uptime arithmetic |
| `test_metrics.py` | Segmentation, live statistics, the equity series, correlation |
| `test_live_lib.py` | Ledger arithmetic, commission accounting, bar scheduling, history assembly |
| `test_shell_scripts.py` | Argument handling and the dashboard's process discovery and locking |
| `test_allocation_books.py` | Book migration, per-book caps, and that `sim` is not rationed |
| `test_sim_broker.py` | The simulated single-instrument book: fills, shorts, exits, quote sources |
| `test_portfolio.py` | Cross-sectional execution: leverage caps, sell-before-buy, restart safety |
| `test_runner_bars.py` | Bar-advance gating, state merging, rebuilding a broker from `meta.json` |
| `test_data_cache.py` | The shared `data/` cache: one name per series, atomic writes, depth floor |
| `test_systemd_units.py` | Unit files, including directives systemd ignores rather than rejects |
| `test_frontend.py` → `test_dashboard_ui.mjs` | The page's action dispatch, run under node |

The browser-side suite extracts the `<script>` block from `web/index.html` and evaluates it
against a DOM stub, because the page has no build step and no module boundary to import.

## Capital

Each strategy gets its own **ledger** — a private base/quote book seeded from an allocated
`capital_usdt` — so many strategies share one testnet account without fighting over it, and
the faucet endowment sitting in that account never inflates anyone's position sizing.

Capital is *allocated, not divided*: deploying or retiring a strategy never resizes the
others, because dividing account equity by the live strategy count would make every strategy
churn its whole position each time an unrelated one came or went.

Allocation is **per book**, which is what removed the four-strategy ceiling:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'harness'); \
  from live_lib import allocate; print(allocate('sector-etf/momo', 2500.0, book='sim'))"
```

* `venue` holds a real $10k pool. Those ledgers are backed by an actual shared testnet
  balance, so they must add up to something the account can fund; `allocate()` refuses to
  oversubscribe it, and that refusal is a real constraint.
* `sim` is uncapped. Two simulated books share nothing — no account, no balance, no
  instrument inventory — so rationing them would be inventing a scarcity that does not exist.

`harness/state/allocations.json` holds both. A pre-books file migrates on read: its single
top-level pool becomes the `venue` pool and every strategy in it is `venue`-backed, because
those ledgers *are* covered by a live account and reading them as simulated would silently
uncap it.

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
