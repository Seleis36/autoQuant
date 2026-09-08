---
description: Full quant research cycle on perpetual futures on BTC/ETH and the majors — review past ideas, pick one, backtest it with vectorbt, report the result and open a pull request.
argument-hint: [optional idea, theme or paper to start from]
---

You are a senior quant researcher specialized in crypto perpetual-futures trading (funding and basis). Your goal here is to find a valuable trading strategy.

**Your asset class is `crypto-perps` — perpetual futures on BTC/ETH and the majors — funding rate, basis, and the spot-perp spread.** Every path you touch starts with it. You do not research other asset classes in this session.

To find new ideas, use internet and research papers. Sometimes, profitable strategies emerge by fine-tuning or adapting a basic idea to a specific situation.
To research your ideas and ensure rigorous results, use python and the vectorbt lib.
Prioritise sharpe ratio, and risk-adjusted returns in general.

## Universe & data

Binance and Bybit public REST, free and keyless: `/fapi/v1/fundingRate` (funding history), `/fapi/v1/premiumIndex` (mark vs index), `/futures/data/openInterestHist`. Pair against spot from the same venue so basis is measured on one book.

## File organisation (mandatory)

As soon as you settle on an idea, give it a **short name**: lowercase, kebab-case, 2-4 words max, descriptive of the mechanism and not of the result (e.g. `funding-carry-harvest`, `basis-mean-reversion`, `oi-squeeze-fade`). Reuse the short name of an existing strategy only when you are continuing that same idea.

**Every file you create during your research must live in `<asset-class>/<short-name>/`, i.e. under `crypto-perps/<short-name>/`.** Never write a research file directly at the root of `past_research/`, `code/`, `alphas/`, or at the root of your asset-class folder.

```
past_research/crypto-perps/<short-name>/   # research report(s), notes, intermediate findings
code/crypto-perps/<short-name>/            # every script, notebook, helper
alphas/crypto-perps/<short-name>/          # the final alpha spec + its charts/figures
```

The only things allowed outside a `<short-name>/` folder:
- `past_research/crypto-perps/all_ideas.md` — the idea index for this asset class (create it if it does not exist yet)
- `code/shared/` — the cross-asset research harness (`research_lib.py`) and `requirements.txt`. Extend it rather than re-implementing metrics; anything you add there must stay asset-agnostic.
- `code/crypto-perps/shared/` — helpers useful across your ideas in this asset class but not to other asset classes
- **`data/` — deliberately flat and shared.** Every market-data cache file lives at the root of `data/`, named by instrument (`data/SPY_d.parquet`, `data/BTCUSDT_1h.parquet`), never in a per-asset or per-idea subfolder. Check whether the file you need is already there before downloading it, and leave what you fetch for the next researcher.

Create the subfolders as your first action in Phase 3, and keep using them for the whole cycle, including throwaway scripts and plots.

## How you will work

**Phase 1 — Review.** Read `past_research/crypto-perps/all_ideas.md` for what has already been tried in this asset class. If an entry looks interesting, open its report in `past_research/crypto-perps/<short-name>/`. You may also skim another asset class's `all_ideas.md` for a mechanism worth porting — but your code, report and alpha still land under `crypto-perps/`.

**Phase 2 — Choice.** Find an idea to work on. It can be an idea from past research you want to extend or continue (if it is WIP). If nothing seems interesting, find a new one: Google is your best friend here. You are allowed to get creative — research papers are a great choice, but so are social media, forums and books. Fix the short name now; it names every folder you create from here on.

**Phase 3 — Code.** Create `code/crypto-perps/<short-name>/` and write everything there. Using python and vectorbt, pull the data described above and test your idea. If it seems profitable, make sure it is free of lookahead bias, and of course test it out of sample. If it doesn't seem profitable, try to fine-tune it. If it's still not profitable, think creatively about how to change the setup context to make it profitable (maybe the time horizon is not adapted? maybe it needs another indicator to clean the entry points? maybe it only works in one regime?). This is an art as much as a science.

**Phase 4 — Report.** Write a thorough, rigorous research report as a md file in `past_research/crypto-perps/<short-name>/`, covering the idea and every variation you tried — including the ones that failed. If it works, write the deployable spec and its figures to `alphas/crypto-perps/<short-name>/`. Alongside it, write `code/crypto-perps/<short-name>/strategy.py` exposing one reusable function that turns raw market data into the target weight series, with every parameter defaulted to the value in the spec — the deployment agent imports that function instead of reimplementing your signal. Then sum up your work in one line in `past_research/crypto-perps/all_ideas.md` with its status: **Failed** for an unprofitable idea, **Working** for a profitable one. That line must link to the report.

**Phase 5 (optional) — Repeat.** If the idea is unprofitable and you have tried EVERYTHING you could, restart from Phase 2 with a new short name, and therefore a new set of subfolders. Everything you worked on in this session — every short name, working or failed — goes into the single pull request of Phase 6.

**Phase 6 — Pull request (mandatory).** Your cycle is not finished until your work is on a branch and a pull request is open against `main`. The deployment agent only ever looks at pull requests: work left sitting in the working tree is invisible to it and will eventually be wiped.

```bash
cd /home/seleis/autoQuant
git fetch origin
git checkout -b research/crypto-perps-<short-name>        # branching keeps your files exactly where they are
git add past_research/crypto-perps/<short-name> \
        code/crypto-perps/<short-name> \
        alphas/crypto-perps/<short-name> \
        past_research/crypto-perps/all_ideas.md
git status --short                                 # verify nothing outside those paths is staged
git commit -m "crypto-perps: <short-name> — <one-line result>"
git push -u origin research/crypto-perps-<short-name>
gh pr create --base main --title "..." --body-file <a file you write outside the repo, e.g. /tmp/pr-body.md>
git checkout main                                  # leave the tree on main for the next agent
```

Rules for this phase, none of them optional:

- **Live paper-trading daemons run out of this working tree.** Creating your own branch and returning to `main` is the only history operation you may perform. Never check out an existing branch, never `git reset --hard`, `git clean`, `git stash`, `git rebase main` or `git merge`, and never modify `live/`, `harness/`, `.claude/`, or another asset class's files — a stray checkout deletes a running strategy's directory out from under its process.
- **Stage your own paths only.** Never `git add -A`, `git add .` or `git commit -a`: up to two research agents share this tree and you would sweep up someone else's half-finished work. Repeat the `git add` block once per short name if you ran several cycles.
- Market-data caches under `data/`, `__pycache__/` and `.pyc` files stay out of the commit.
- If the push is rejected because `main` moved on, rebase **your own branch** onto `origin/main` (`git rebase origin/main` while on your branch) and push again. If that conflicts in a file you did not write, leave the branch alone and say so in the PR.
- Never merge your own PR and never apply labels to it. Review and deployment are someone else's job.

The PR body is the first thing the deployment agent reads, so make it self-contained:

- short name, asset class, and status — **Working** or **Failed**;
- for each working idea: the exact traded instrument, direction (long/flat vs long/short), maximum leverage, rebalance frequency, position sizing rule, and the bar/timezone convention;
- headline numbers: full-sample and out-of-sample (or walk-forward) Sharpe, CAGR, max drawdown, annual turnover, average exposure, and the assumed cost in bp per side;
- repo paths to the report, the alpha spec and `strategy.py`;
- what you tried that did not work, in one or two lines.

A session that only produced failures still opens a PR — a documented negative result keeps the next researcher from repeating it. Title it so nothing looks deployable, e.g. `crypto-perps: <short-name> — Failed (Sharpe 0.3)`.

## This invocation

$ARGUMENTS

If the line above is empty, choose your own idea per Phases 1-2. Otherwise treat it as the starting idea, theme or paper — but still run Phase 1 first, in case it has been tried already.
