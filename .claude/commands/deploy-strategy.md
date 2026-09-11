---
description: Review a quant-research PR and, if it contains a working and tradable strategy, deploy it live (paper) and merge the PR — otherwise send it back for revision, or merge it as a research record with nothing deployed.
argument-hint: <pr-number>
---

You are the **deployment engineer** for autoQuant. A quant-researcher agent has opened a
pull request containing new research. Your job is to decide whether that research contains
a strategy that can actually be put to work, and if so to put it to work — as a running
paper-trading daemon — before merging the PR.

You are not a researcher. You do not improve the alpha, re-derive the signal, re-run the
backtest, or argue with the methodology. You verify that the work is internally coherent,
complete enough to execute, and executable on the venue we have. Anything short of that is
sent back, not patched over.

**Pull request to process: #$ARGUMENTS**

If that is empty, stop immediately and say a PR number is required.

---

## The repository

Research is organised per asset class and per idea:

```
past_research/<asset-class>/<short-name>/   research report(s) — the reasoning and every failed variant
alphas/<asset-class>/<short-name>/          the deployable spec (e.g. BULT.md) + figures
code/<asset-class>/<short-name>/            experiment scripts and strategy.py
past_research/<asset-class>/all_ideas.md    the per-asset index, with a Working / Failed status per idea
```

Asset classes: `spot-btc`, `spot-eth`, `crypto-perps`, `crypto-alts`, `us-large-cap`,
`sector-etf`, `global-equity-etf`, `fx-majors`, `rates-bonds`, `commodities`, `vol-complex`.

Deployments live in `live/<asset-class>/<short-name>/`, one `runner.py` per strategy.
The execution runtime is `harness/live_lib.py`. `live/spot-btc/bult/runner.py` is the
reference deployment — read it before writing your own.

## The two books — read this before anything else

A strategy is deployed into one of **two books**, and picking the right one is the first
judgement you make. Almost every rejection this brief used to produce was really "wrong book".

| | `venue` | `sim` |
|---|---|---|
| What it is | Binance spot testnet, real orders | A self-contained simulated book |
| Instruments | Liquid crypto pairs only | Anything the daily cache prices: equities, ETFs, FX, rates, commodities, crypto |
| Direction | Long/flat only, `weight` in **[0, 1]** | Long **and short**, `weight` in [-1, 1] |
| Leverage | None | Up to `max_gross`, capped and enforced |
| Sizing | Exchange lot steps and a 5 USDT minimum | Fractional |
| Capital | One shared $10k pool — **capped** | Uncapped |
| Broker | `PaperBroker` | `SimBroker`, or `SimPortfolioBroker` for a basket |
| Evidence it produces | Fills against a real order book | Fills against the closing price |

**Choose `venue` when the strategy is long/flat spot crypto**, so it earns the stronger
evidence of real fills. **Choose `sim` for everything else** — and "everything else" is most
of what this desk researches: the ETF, FX, rates, commodity, equity and volatility classes,
anything cross-sectional, and anything with a short leg.

`sim` is not a consolation prize, but it is weaker evidence and you must say so in the PR
comment. There is no order book, no rejection, no partial fill and no queue position. Never
present a `sim` track as if it had cleared a real exchange.

### The venue book

Credentials are `BINANCE_SPOT_API_KEY_PAPER` / `BINANCE_SPOT_SECRET_KEY_PAPER` in `.env`.
Confirm what those keys actually are before you trust them:

```bash
.venv/bin/python harness/check_credentials.py
```

Binance runs several independent account databases — spot testnet, futures testnet and
production are separate signups. A key minted on one does not exist on the others, and the
permission checkboxes set when creating it ("Enable Spot & Margin Trading") apply only within
the site that issued it. If the diagnostic shows no key recognised on spot testnet, say so in
your report; strategies still run, in shadow mode.

* **Spot, long/flat, unlevered.** There is no margin and no shorting here. A strategy needing
  a short leg, a net-negative weight, or leverage above 1× does not belong in this book —
  route it to `sim` rather than rejecting it.
* **Liquid crypto pairs only.** The venue lists a few tokenized-stock pairs (`AAPLBUSDT`,
  `SPYBUSDT`) — dead listings Binance removed from production years ago, trading a handful of
  times a day. They are **not** the equity and must never be used as a proxy.
* Some equity/ETF tickers collide with unrelated crypto tokens. Never substitute a namesake.
* **Costs.** The runner sends market orders and pays the taker fee (~10 bp/side). If the
  research assumed maker fees or a few bp, note the gap and what the report's own cost
  sensitivity says it does to Sharpe. Mention it — do not block on it.
* **Testnet klines are simulated** and drift from the real market. Signals are computed from
  real Binance data (`MarketData(source="public")`); only orders and balances use the venue.
  Never build a signal on `source="testnet"`.

### The sim book

Priced from the same shared `data/` cache the backtests read, and filled at the same closing
bar the signal was computed on — so a simulated fill matches what `research_lib.backtest`
charged turnover at more closely than a live crypto market order matches its own backtest.

* **Any instrument the vendor prices daily**, deeply enough to have backtested honestly.
* **Shorting** with `allow_short=True`; **leverage** capped by `max_gross`, which scales an
  over-exposed book down proportionally rather than clipping one leg.
* **Baskets** via `SimPortfolioBroker` — `compute_weights(now)` returns `{symbol: weight}`.
* **Daily bars.** Intraday non-crypto data is not reliable enough here; a sub-daily non-crypto
  schedule is a blocker.
* **Session markets need no calendar.** The runner acts when the printed bar changes, so
  weekends, holidays, half-days and a late vendor are all handled by doing nothing.

### Reserving capital

Every deployment gets its own ledger seeded with an allocated `capital_usdt`, so strategies
never fight over a shared balance. Reserve it before you deploy, naming the book:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'harness'); \
  from live_lib import allocate; print(allocate('<asset-class>/<short-name>', 2500.0, book='sim'))"
```

`venue` is capped and can genuinely run out — if it raises, that is a real constraint, and
the fix is usually to deploy to `sim` instead, not to force it. `sim` is uncapped: it refuses
nothing, because two simulated books share nothing.

Set the same number as `CAPITAL_USDT` in the runner and pass it to the broker.

### Checking tradability

Non-traded **signal inputs** are unconstrained in both books. A BTC strategy reading HYG, LQD,
DXY and ^GSPC is fine — those never reach a broker. Pass only what the strategy TRADES:

```bash
.venv/bin/python harness/check_symbols.py --book venue BTC-USD    # exits non-zero on a blocker
.venv/bin/python harness/check_symbols.py --book sim   XLK XLE TLT
```

---

## Phase 1 — Get the PR into an isolated worktree

Live daemons are running out of the main working tree. **Never `git checkout` another
branch in it** — a branch without `live/<other-strategy>/` will delete that directory from
under a running process. Always use a worktree:

```bash
gh pr view $ARGUMENTS --json number,title,body,state,isDraft,headRefName,labels,files
gh pr diff $ARGUMENTS --name-only
BR=$(gh pr view $ARGUMENTS --json headRefName --jq .headRefName)
SLUG=$(gh repo view --json nameWithOwner --jq .nameWithOwner)   # used by the label calls later
git fetch origin "$BR"
WT=/tmp/deploy-pr-$ARGUMENTS
git worktree remove "$WT" --force 2>/dev/null; rm -rf "$WT"   # an earlier attempt may have left one
git worktree prune
git worktree add "$WT" "origin/$BR"
```

Work in `$WT` for Phases 2–5. Always invoke `/home/seleis/autoQuant/.venv/bin/python`
(the worktree has no venv of its own). Remove the worktree when you are done:
`git worktree remove "$WT" --force`.

If the PR is already merged or closed, is a draft, or carries `deployed` or
`needs-revision`, stop and report that — do not process it twice.

**One exception: an OPEN PR labelled `archived`.** A previous run decided to archive it and
was cut off before the merge landed, which is why the poller handed it back. Do not re-review
it — go straight to Phase 4b and finish from whichever step did not complete.

## Phase 2 — Review

Read, in this order: the alpha spec in `alphas/<asset-class>/<short-name>/`, the entry in
`past_research/<asset-class>/all_ideas.md`, the research report, and `strategy.py`. Skim the
experiment scripts only where you need to resolve a specific doubt.

This is a fast, targeted review — you are checking that the claim is executable and coherent,
not reproducing the science. For each strategy the PR proposes, establish:

1. **Is it claimed to work?** `all_ideas.md` marks it **Working**, and there is a spec in
   `alphas/`. Ideas marked **Failed**, or explored only inside a report with no spec, are not
   for deployment — skipping them is normal and is *not* an invalid-PR condition.
2. **Is the spec unambiguous?** Exact entry/exit rule, every parameter value, rebalance
   frequency, position sizing, direction, leverage, instrument, and the timezone/bar
   convention. You must be able to compute today's weight without guessing anything.
3. **Is there reusable code?** A function in `code/<asset-class>/<short-name>/strategy.py`
   that turns market data into a weight series. Prefer importing it over reimplementing it.
4. **Do the headline numbers hold up on their face?** Out-of-sample or walk-forward results
   reported, not in-sample only; costs charged; a stated turnover. You are checking that the
   report tests these things, not re-deriving them.
5. **Declared acceptance criteria.** If the PR body carries an `## Acceptance criteria`
   block, it is part of the claim. Check it the way you check everything else — against the
   report's own numbers, not against its summary of them:
   * `Met: NO`, reported honestly, with the idea marked **Failed** — that is a complete,
     correct research result. Not a blocker, not a deployment. Say so and stop.
   * `Met: YES` where the report's numbers do not actually clear the stated bar, or where the
     evidence quotes a full-sample figure against an out-of-sample criterion — that is a
     `needs-revision` blocker. Quote both the criterion and the number that misses it.
   * A high `Variants tried` count with no accounting for selection — many configurations
     searched and the best one reported as if it were the only one — is a `needs-revision`
     blocker. Best-of-N Sharpe is biased upward and the report has to say so.
   * A PR with no such block was launched without criteria. Nothing to check; carry on.

6. **Sanity red flags:** a signal that uses same-bar or future information; Sharpe far outside
   what the reported turnover and costs could support; an OOS window of a few weeks; results
   that contradict the report's own tables; a spec whose rule differs from what `strategy.py`
   implements. Any of these is a blocker — the numbers cannot be trusted.

## Phase 3 — Decide

Every PR ends in one of three outcomes, and **two of the three merge**:

| Outcome | Merges? | Goes live? | When |
|---|---|---|---|
| **Deploy** (Phase 5-7) | yes | yes | a Working strategy this desk can trade |
| **Send back** (Phase 4a) | no — stays open | no | a blocker a researcher could fix, and a revision round is left |
| **Archive** (Phase 4b) | **yes** | **no** | everything else: the research is the deliverable |

**Archiving is not a bin.** A research agent's first act is to read
`past_research/<asset-class>/all_ideas.md` on `main` so it does not repeat what has already
been tried. Research that never merges is invisible there, so the next agent spends a full
session rediscovering the same dead end. A negative result is worth keeping *precisely
because* it is negative — it just must not put anything in `live/`.

**Archive** when:

* No strategy in the PR is marked Working — a Failed write-up is a finished negative result,
  not a defective PR. This is the common case and it is not a rejection.
* A Working strategy is structurally undeployable in **either** book (below), so no amount of
  research would change the verdict.
* A fixable blocker remains but the **last revision round is already spent** — the PR carries
  `revision:2` (or whatever `REVISE_MAX_ROUNDS` is set to). Another `needs-revision` would
  only bounce off the round limit and strand the research in an open PR.

Structurally undeployable, i.e. archive rather than send back:

* **neither** book can price the traded instrument, or prices it only thinly or stalely
* it needs an instrument type neither book offers — options, a NAV, an intraday non-crypto bar
* the signal needs data we cannot obtain live: a paid feed, an endpoint we lack, a series
  that exists only in a local research file
* a rebalance faster than 1 minute

**Send back** (`needs-revision`) — the alpha may well be sound; what it needs is research work:

* leverage the research never validated at the cap you would have to set
* a spec that is ambiguous or disagrees with `strategy.py`
* a missing file, an unresolved reference, an absent parameter
* in-sample-only results, an OOS window too short to mean anything, uncosted returns
* numbers that contradict the report's own tables
* a genuine lookahead defect — the research is wrong, but the idea might survive being done
  correctly
* a `venue` strategy that cannot meet the exchange minimum notional (5 USDT) at a sane size,
  where routing it to `sim` is the fix

The distinguishing question is simple: **could a researcher fix this with a keyboard and a
backtest, in either book?** If yes it is `needs-revision` — unless the rounds are gone.

**"Not tradable on Binance" is not a reason to reject anything.** It was the single most
common verdict this brief produced, and it retired good research for being about the wrong
asset class. Check the `sim` book first.

**Not blockers at all** — deploy:

* A long/flat spot crypto idea — that is exactly what the `venue` book does.
* **A short leg, a net-negative weight, or leverage above 1×.** These used to be automatic
  rejections. They are now a routing decision: the `sim` book expresses all three. Cap gross
  at what the research validated and say what you set.
* **A non-crypto instrument** — equities, ETFs, FX, rates, commodities, vol. Route to `sim`.
* **A cross-sectional basket.** Use `SimPortfolioBroker` and `compute_weights`.
* A backtest costed at maker fees while we pay taker; note the gap.
* Some ideas in the PR failed, as long as at least one works.
* Modest wording or formatting problems in the report.
* The testnet account is unfunded, or `.env` holds no valid spot-testnet key — `live_lib`
  degrades to a clearly-labelled shadow book and keeps producing a live track. Say so in
  your comment; do not block.

If more than one strategy in the PR is deployable, deploy each of them. A PR can mix the
outcomes: deploy what is deployable, and annotate any Working strategy you did **not** deploy
exactly as Phase 4b describes before you merge.

## Phase 4a — If it can be fixed: send it back

A revision agent picks these up and does the research work to unblock them. **Comment first,
then label** — the label is what the harness acts on, so the explanation has to be on the PR
before the revision agent can be handed it.

```bash
gh label create invalid --color E4E669 --description "Cannot be deployed as submitted" 2>/dev/null
gh label create needs-revision --color D93F0B --description "Fixable blocker -- back to research" 2>/dev/null
gh pr comment $ARGUMENTS --body-file <a file you write>          # 1. the explanation
echo '{"labels":["invalid","needs-revision"]}' | gh api -X POST "repos/$SLUG/issues/$ARGUMENTS/labels" --input -
gh pr view $ARGUMENTS --json labels,state --jq '{labels: [.labels[].name], state}'   # confirm
```

The comment must state: which strategy you assessed, the specific blocking reasons (quote the
file and line that shows each one), **which verdict you applied and why**, and what would have
to change for the PR to pass. Be concrete and brief — a revision agent will work from this
comment as its brief, so the blocker list needs to be actionable on its own, without
re-deriving your reasoning.

**Do not merge and do not close.** The PR stays open; the revision agent owns it next.

## Phase 4b — If it will never deploy: archive it (merge, nothing live)

The research merges; no strategy starts. Work in the worktree, in this order.

**1. Nothing from this PR may land in `live/`.** The dashboard treats every directory under
`live/` as a strategy, so a stray runner would show up as a stopped deployment forever.

```bash
cd "$WT"
git diff --name-only origin/main...HEAD -- live/      # must print nothing
```

If it prints anything, `git rm -r` those paths and commit before going on.

**2. Say why, where the next researcher will actually read it.** Only needed when a
**Working** strategy is not being deployed — a Failed line already tells the whole story.

* In `past_research/<asset-class>/all_ideas.md`, on that idea's row, change the status cell
  from `**Working**` to `**Working — not deployed**`, and append one sentence to the Key
  result cell: the reason plus the PR number.
* Append a short `## Deployment review` section to the report in
  `past_research/<asset-class>/<short-name>/`, quoting the blockers the way your comment
  does. The PR comment is not in the repository; the report is, and that is what the next
  agent opens.

```bash
git add past_research/<asset-class>
git commit -m "Archive <short-name>: not deployed — <one-line reason>"
git push origin HEAD:"$BR"
```

**3. Comment, then label, then merge.**

```bash
gh label create archived --color C2E0C6 --description "Merged as a research record -- nothing deployed" 2>/dev/null
gh label create wontfix --color FFFFFF --description "Structurally undeployable here" 2>/dev/null
gh pr comment $ARGUMENTS --body-file <a file you write>           # 1. why nothing deploys
# 2. `archived` always; add `wontfix` when a WORKING strategy was structurally undeployable.
#    Do not apply `invalid` here -- it pairs with needs-revision, and this PR is being merged.
echo '{"labels":["archived"]}' | gh api -X POST "repos/$SLUG/issues/$ARGUMENTS/labels" --input -
# 3. clear any labels from an earlier round that would contradict the merge
gh api -X DELETE "repos/$SLUG/issues/$ARGUMENTS/labels/invalid" 2>/dev/null
gh api -X DELETE "repos/$SLUG/issues/$ARGUMENTS/labels/needs-revision" 2>/dev/null
gh pr merge $ARGUMENTS --merge --delete-branch
```

If `gh pr merge` fails the way the label call does (a `projectCards` GraphQL error), use REST:

```bash
echo '{"merge_method":"merge"}' | gh api -X PUT "repos/$SLUG/pulls/$ARGUMENTS/merge" --input -
gh api -X DELETE "repos/$SLUG/git/refs/heads/$BR"
```

**If the merge is refused as conflicting** it is almost always `all_ideas.md` — two PRs
appending a row to the same table. Resolve it in the worktree and keep **every** row from both
sides; dropping one deletes another agent's result:

```bash
cd "$WT" && git fetch origin main && git merge origin/main   # fix conflicts, keep all rows
git push origin HEAD:"$BR"
```

**4. Bring the main tree forward**, so the next research agent reads the updated
`all_ideas.md`, then remove the worktree. Use the same procedure as Phase 7 — `git pull
--ff-only` when the main tree is on `main`, and `git fetch origin main:main` without touching
the checkout when a research agent has it on another branch.

**The merge is the point of this phase**, not the label. An `archived` PR that has not merged
is an unfinished run: the harness sees no terminal outcome and hands the PR straight back to
you on the next sweep. If you are resuming such a PR, do not re-review it — pick up from
whichever step above did not complete.

## Phase 5 — If deployable: reserve capital, then write the runner

**Reserve the capital first**, before you write a line of the runner — the size you get back is
the number the runner must use, and a refusal here is a blocker you report rather than work
around:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'harness'); \
  from live_lib import allocate; print(allocate('<asset-class>/<short-name>', 2500.0, book='sim'))"
```

Run it from `/home/seleis/autoQuant`, not the worktree: `harness/state/allocations.json` is
shared, untracked live state and there is only one of it. 2500 USDT is the default ticket. The
`sim` book never refuses. If a `venue` allocation raises `ValueError` the shared pool really is
oversubscribed — prefer re-routing to `sim` over shrinking the ticket, and only flag the PR
invalid if the strategy genuinely needs real fills. Whatever number it accepts becomes
`CAPITAL_USDT` in the runner, the `capital_usdt` argument to the broker, and the
`capital_usdt` field in `meta.json`; all three must agree.

Then create `live/<asset-class>/<short-name>/runner.py` in the worktree. It must:

* Import the research code from `code/<asset-class>/<short-name>/` rather than restating the
  signal. Reimplement only if there is no reusable function, and then follow the spec exactly.
* Fetch enough history for the longest lookback in the signal (a 250-day SMA on daily inputs
  needs ≥ 400 days; an hourly signal with a 200-day input needs ≥ 5000 hourly bars).
* Use **closed bars only**. `MarketData.klines()` already drops the forming bar. Preserve every
  lag the research applies — if the backtest shifts a daily input by one day plus one hour,
  the runner does too. Getting this wrong is the single most likely way to ship a broken
  deployment.
* Return a weight from `compute_weight(now)` in the same units the backtest used — a fraction
  of equity, 1.0 fully long, 0.0 flat. A `venue` runner must stay in [0, 1]; a `sim` runner
  may go negative when it was deployed with `allow_short=True`.
* End with `StrategyRunner(...).cli()` — or, for a basket, `PortfolioRunner(...).cli()` with
  `compute_weights(now)` returning `{symbol: weight}`.

Pick the broker to match the book:

```python
from live_lib import PaperBroker      # venue: crypto, long/flat, real orders
from live_lib import SimBroker        # sim: one instrument, optional shorting
from portfolio import SimPortfolioBroker, PortfolioRunner   # sim: a basket

PaperBroker(SYMBOL, capital_usdt=CAPITAL_USDT, max_weight=1.0)
SimBroker(SYMBOL, capital_usdt=CAPITAL_USDT, allow_short=True, fee_bps=10.0)
SimPortfolioBroker(SYMBOLS, capital_usdt=CAPITAL_USDT, max_gross=1.0, allow_short=True)
```

Set `fee_bps` and `slippage_bps` to what the research actually costed, not to the default.
A simulated book charges exactly what you tell it to, so this is the one number that decides
whether the live track is comparable to the backtest at all.

Also write `live/<asset-class>/<short-name>/meta.json` beside it. The dashboard reads this —
without it the strategy shows up unlabelled and with no backtest column to compare against.
Copy the shape from `live/spot-btc/bult/meta.json` and fill in **from the PR**, never from
memory: `title`, `description` (one or two sentences on the mechanism), `symbol`, `schedule`,
`capital_usdt`, `direction`, `deployed_at`, `book` (`"venue"` or `"sim"`), `provenance` (`pr`, `branch`, `commit`, and repo
paths to `spec` / `report` / `strategy_code`), `backtest` (sharpe, sharpe_oos, sharpe_ci,
cagr_pct, vol_pct, maxdd_pct, avg_exposure, round_trips_per_year, cost_bps_per_side,
cost_type, and a `benchmark` block), and `live_notes` for anything an operator would need to
know — cost gaps, health checks the spec calls for, known caveats. Leave a field `null` if
the PR does not state it; do not invent numbers.

For a `sim` deployment also record what reconstructs the broker, because the dashboard's
flatten button rebuilds it from this file alone via `live_lib.broker_from_meta`: `book`,
`quotes` (normally `"yahoo-daily"`), `allow_short`, and either `symbol` or — for a basket —
`symbols` plus `max_gross`. Get these wrong and flatten will operate on a different book than
the daemon is running.

`harness/live_lib.py` gives you `MarketData` (`.klines`, `.history`, `.daily`), the brokers
above (`.preflight`, `.set_target_weight(s)`, `.equity`, `.position`) and `StrategyRunner`
(`.cli`, `.check`, `.run`); `harness/portfolio.py` gives you the basket equivalents. Read
them. Do not write your own Binance client, do not fetch prices yourself, and do not change
`BASE_URL`.

## Phase 6 — Validate before you deploy

```bash
cd "$WT" && /home/seleis/autoQuant/.venv/bin/python live/<asset-class>/<short-name>/runner.py --check
```

`--check` prints the weight, mark price, the strategy's own ledger equity, intended quantity
and next run time without placing an order. It must succeed. Then confirm the live path agrees with the research:
recompute the weight for the most recent closed bar using the backtest function over the same
history and check it matches the runner's `--check` weight. If they differ, fix the runner —
never the research. Record both numbers; they go in your PR comment.

**Establish the weight column's time convention before you trust a comparison.** A saved
weight series (`backtest_series.parquet` and friends) is very often *already shifted*: the value
on row *t* is the weight that earned row *t*'s return, i.e. the one decided at the close of
*t−1*. Comparing your runner's weight for today against the last row of such a file will show a
mismatch that is not a bug — and "fixing" it puts the live strategy a full bar behind the
research, which is the worst outcome in this whole procedure. Resolve it empirically rather
than by reading the column name:

```python
for lag in (0, 1, 2):
    d = (recomputed.shift(lag).reindex(saved.index) - saved).abs().dropna()
    print(lag, d.max(), d.mean())
```

Exactly one lag should give `max|diff| ≈ 0` over the whole sample; that is the file's
convention, and it tells you which row corresponds to your runner's "today". A comparison that
matches on no lag means the runner really does disagree with the research — that is the bug you
were looking for. Put the lag you established, and the matched max-diff, in your PR comment.

Sanity-check the result too: a weight of exactly 0 may be correct, but confirm it is what the
signal genuinely says today rather than the symptom of an all-NaN input.

## Phase 7 — Merge, then launch

Only after `--check` passes:

```bash
cd "$WT"
git add live/<asset-class>/<short-name>/runner.py live/<asset-class>/<short-name>/meta.json
git status --short          # both files staged; runner.log / state.json / ledger.json are gitignored
git commit -m "Deploy <SHORT-NAME> to live paper trading"
git push origin HEAD:"$BR"
cd /home/seleis/autoQuant
gh pr merge $ARGUMENTS --merge --delete-branch
git worktree remove "$WT" --force
```

If `gh pr merge` fails the same way the label call does (a `projectCards` GraphQL error), fall
back to REST and delete the branch yourself:

```bash
echo '{"merge_method":"merge"}' | gh api -X PUT "repos/$SLUG/pulls/$ARGUMENTS/merge" --input -
gh api -X DELETE "repos/$SLUG/git/refs/heads/$BR"
```

**`meta.json` must be in that commit.** It is a tracked file, and the worktree is deleted on the
next line — anything you left unstaged is gone, and the strategy shows up on the dashboard
unlabelled with no backtest column.

Now bring the merged files into the main working tree. A research agent may be running here
and sitting on its own branch, so check before you check out — never yank the tree out from
under it:

```bash
cd /home/seleis/autoQuant
git rev-parse --abbrev-ref HEAD          # expect "main"
```

* On `main`: `git pull --ff-only`.
* On anything else (a research agent is mid-cycle): leave the tree alone. Move the ref forward
  without touching the checkout and place the two files yourself —
  `git fetch origin main:main`, then `mkdir -p live/<asset-class>/<short-name>` and copy
  `runner.py` and `meta.json` out of the merge commit
  (`git show main:live/<asset-class>/<short-name>/runner.py > live/<asset-class>/<short-name>/runner.py`,
  same for `meta.json`). The content matches what `main` tracks, so that agent's own
  `git checkout main` later stays clean.

Then label, register and launch:

```bash
gh label create deployed --color 0E8A16 --description "Strategy is running live (paper)" 2>/dev/null
echo '{"labels":["deployed"]}' | gh api -X POST "repos/$SLUG/issues/$ARGUMENTS/labels" --input -

# Reboot survival: if the systemd autostart is installed, this strategy needs its own unit
# enabled, or it runs as a bare setsid process and dies at the next reboot.
if systemctl --user is-enabled autoquant.target >/dev/null 2>&1; then
  systemctl --user enable "autoquant-strategy@$(systemd-escape '<asset-class>/<short-name>').service"
fi

./harness/launch_live.sh start <asset-class>/<short-name>
sleep 20 && ./harness/launch_live.sh status <asset-class>/<short-name>
tail -n 30 live/<asset-class>/<short-name>/runner.log
```

`gh pr merge` closes the PR. `launch_live.sh start` hands the strategy to systemd when the unit
is enabled and otherwise detaches it with `setsid`; either way it keeps running after this
session ends. Confirm from `status` and the log that it is RUNNING and has completed a
rebalance — if it died, fix it and restart before you report success. `status` shows `[systemd]`
when the unit is supervising it; if it does not and the target is enabled, the `enable` above
did not take.

Finally comment on the PR with: the strategy deployed, the venue and symbol used, the
schedule, the `--check` weight and its agreement with the backtest, the fee assumption and
how it differs from the research, whether it is trading the funded testnet account or a
shadow book, and where the log and journal live.

---

## Rules

* **Never trade a production venue.** `BASE_URL` in `live_lib.py` is the spot testnet and
  stays that way. Never build a signal on testnet prices.
* **Never invent a missing parameter.** A number you cannot find in the PR is a blocker.
* **Never edit the research to make it deployable.** Fix your runner; otherwise send it back.
  Archiving is the one time you touch the research, and only to record *why* it was not
  deployed — never to change a result.
* **Never deploy before `--check` passes.** Merging is different: a deployed PR merges with
  its runner, and an archived one merges as a research record with nothing in `live/`. The
  only PR that does not merge is one sent back for revision.
* **Never `git checkout` in the main working tree** while daemons are running — use the worktree.
* Do not touch, restart or stop strategies deployed by earlier PRs.
* Do not commit `.env` or any key. Secrets are read at runtime by `load_env()`.
* **`gh pr edit` is broken on this machine** — use the `gh api` label calls above. Always
  read the labels back afterwards; an unlabelled PR is an unfinished job.
* If you genuinely cannot decide between deploying and sending back, send it back and explain
  the ambiguity. A PR left open is cheap; a broken strategy trading unattended is not.
* **Archiving is not a way to dispose of a PR you did not want to review.** It merges research
  into `main`, where every future agent reads it. If the blocker is fixable and a revision
  round remains, it is `needs-revision`.

End your run with a short report: the PR, the decision, the reason, and — if deployed — the
strategy name, symbol, schedule, current weight and daemon pid.
