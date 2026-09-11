# autoQuant

A self-running quant research desk. Claude Code agents invent trading strategies, backtest
them, review each other's work, and put the survivors into live paper trading — on a loop,
without a human in the middle.

```
  /<asset>-quant-research        poll_prs.sh         /deploy-strategy
┌─────────────────────┐  PR  ┌──────────────┐ every ┌──────────────────┐ merge ┌──────────────┐
│  research agent     ├─────►│  PR queue    ├──────►│ deployment agent ├──────►│ live daemon  │
│  idea → backtest →  │      │              │ 30min │ review, runner.py│       │ paper trades │
│  report → PR        │      └──────▲───────┘       │ --check, merge   │       │ on testnet   │
└─────────────────────┘             │               └────────┬─────────┘       └──────────────┘
                                    │ re-review              │ sent back
                                    │        ┌───────────────▼──────────┐
                                    └────────┤ revision agent           │
                                             │ /revise-strategy         │
                                             └──────────────────────────┘
```

Strategies trade in one of two paper books: the **Binance spot testnet** — real orders,
real prices, fake money, but long/flat crypto only — or a **simulated book** that prices
anything the research covers (equities, ETFs, FX, rates, commodities, vol), takes shorts and
baskets, and is not rationed. Long/flat crypto goes to the testnet because real fills are
better evidence; everything else goes to the simulator.

## The two agents

**Researchers** (`/`<asset-class>`-quant-research`) run a full cycle on one asset class: read
what's already been tried, pick an idea, backtest it with vectorbt, hunt for lookahead bias,
test out-of-sample, write a report, and open a pull request. They can be given a hard
acceptance criterion (`--require "OOS Sharpe >= 2.0"`) that the reviewer then enforces —
with an explicit licence to fail it honestly, because a bar you cannot fail is just a
recipe for overfitting. Failures get written up too —
a documented negative result stops the next agent repeating it. Eleven asset classes exist,
from `spot-btc` to `fx-majors` to `vol-complex`.

**The deployment engineer** (`/deploy-strategy <pr>`) reviews each PR in an isolated git
worktree. It doesn't re-derive the science; it checks the claim is coherent and *executable
in one of the two books*. Its first judgement is which book — real fills for long/flat spot
crypto, the simulator for everything else. If it passes, the agent reserves capital from that
book, writes a `runner.py` that imports the researcher's own `strategy.py`, proves the live
weight matches the backtest weight bar-for-bar, merges, and starts the daemon. If it doesn't,
the PR gets labelled `invalid` with the blocking reasons quoted line by line.

Its bar is deliberately unfriendly, but it is a bar about the *research*: spec ambiguous,
numbers contradict the report, a lookahead defect, a signal we cannot obtain live. What is no
longer a rejection is being about the wrong asset class — shorting, leverage and non-crypto
instruments used to be automatic `wontfix`, and that verdict retired good research for the
sole reason that the desk only owned a crypto exchange.

**The revision agent** (`/revise-strategy <pr>`) picks up what the reviewer sent back. The
rejection comment is its brief: it fixes the quoted blocker, re-runs the whole validation
chain under the new constraint, rewrites every number that moved, and pushes to the same
branch — which puts the PR back in the review queue. Two rounds, then the PR is retired.

It is explicitly allowed to conclude that the fix kills the alpha. If capping leverage at 1×
takes Sharpe from 1.63 to 0.6, the honest outcome is to mark the idea **Failed** and close the
PR. An agent that can only succeed will manufacture success, and capital gets reserved on the
strength of these numbers.

## Layout

| Path | What's in it |
|---|---|
| `past_research/<asset>/<idea>/` | Research reports — including every variant that failed |
| `past_research/<asset>/all_ideas.md` | The per-asset index, one line per idea, Working or Failed |
| `alphas/<asset>/<idea>/` | The deployable spec and its figures |
| `code/<asset>/<idea>/` | Experiment scripts + `strategy.py`, the reusable signal function |
| `live/<asset>/<idea>/` | A deployed strategy: `runner.py`, `meta.json`, journal, ledger |
| `harness/` | The machinery — poller, agent launchers, execution runtime, dashboard |
| `harness/portfolio.py` | Cross-sectional execution, for strategies that trade a basket |
| `data/` | Flat shared cache of market data, named by instrument |

## Running it

```bash
./harness/install_autostart.sh      # systemd units + Windows logon hook; survives reboot
./harness/dashboard.sh start        # http://127.0.0.1:8788
./harness/poll_prs.sh --start       # PR poller, sweeps every 30 min
./harness/launch_research.sh spot-btc  "optional seed idea"
```

The **dashboard** is the control room: running strategies with live-vs-backtest metrics,
equity curves against buy-&-hold, the PR queue, a research-agent launcher, venue health and
a kill switch. It binds loopback plus the tailnet address only — the API can place orders, so
it never lands on a public interface. Reachable from a phone over Tailscale.

`harness/README.md` has the operational detail: capital allocation, the label state machine,
shadow-book mode, reboot survival, and how to write a runner by hand.

## Cost

Agents run as headless `claude -p` sessions on a Claude subscription, not metered API credit.
Timeouts are hang reapers, not budgets. One global gate caps concurrent agents of all three
kinds, and reserves a slot so that PR work can always start ahead of new research.

A session cut off by a usage limit is *parked*, not failed: its transcript holds everything it
had done, and `./harness/resume_aborted.sh` (or the dashboard button) continues it rather than
paying for the work twice.

## Caveat

Paper only, and the two books are not equally strong evidence.

On the testnet, klines are simulated and drift from the real market, so signals are always
computed from real Binance public data and only orders and balances touch the venue. In the
simulated book there is no order book at all — no rejection, no partial fill, no queue
position — so a fill there is an assumption, not an observation. The dashboard labels it
`simulated` for that reason, and the two are never spliced into one track.

Nothing here has traded a live dollar, and the strategies are found by machines that are very
good at finding patterns in noise — read the OOS column before believing anything.
