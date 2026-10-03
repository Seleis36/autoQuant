# staking-queue-flow — validator entry/exit queues as a supply-lock-up signal for spot ETH

**Date:** 2026-10-03
**Asset:** spot ETH/USDT (Binance daily bars, 00:00 UTC), long/flat, 10 bp/side
**Status:** **Failed** — every queue feature changes sign between the two halves of a 3.4-year sample; no rule beats vol-scaled buy-and-hold or improves the trend filter.

| 2023-06 → 2026-10, 10 bp/side | full | IS ≤ 2024 | OOS 2025+ |
|---|---|---|---|
| vol-scaled B&H | 0.54 | 1.02 | 0.10 |
| live `eth-trend-filter` | 1.15 | 0.77 | 1.52 |
| net queue > 0 × vol (the headline narrative) | 0.53 | 0.72 | 0.34 |
| net queue rising over 30 d × vol | −0.08 | 0.90 | −0.88 |
| TF veto while exit queue > entry queue | 1.04 | 0.56 | 1.52 |

## 1. Idea

Since withdrawals were enabled (Shapella, April 2023) ETH can only be staked or unstaked through
rate-limited queues. The press reads them as flow indicators: a long **entry queue** is capital
waiting to be locked up (bullish), a long **exit queue** is supply about to be released
(bearish). In 2025 the exit queue reached 2.7 M ETH after a 160% rally and the entry queue
later rose fivefold as treasury companies and ETFs began staking. The queue is public, daily,
and known weeks before the coins move, which is the property a flow signal needs.

## 2. Data and timing

- validatorqueue.com history (`etheralpha/validatorqueue-com`, `historical_data.json`), cached by
  `fetch_queue.py` at `data/VALIDATORQUEUE_ETH_d.parquet`: 1,221 daily rows, **2023-05-21 →
  2026-10-03**, 11 missing days. Entry queue, exit queue, staked amount and supply in ETH.
- The row dated D is committed between 00:07 and 04:50 UTC on D (GitHub commit history), ~20 h
  before the D+1 00:00 decision. Lag 0 is therefore legitimate; lags 1 and 3 give the same ICs.
- Queues are divided by the staked amount so that the Pectra change of units (validators of up
  to 2,048 ETH from May 2025) does not enter.
- **Split fixed before the run:** IS 2023-05-21 → 2024-12-31, OOS 2025-01-01 → 2026-10-02. The
  spot-eth convention (OOS from 2024) would leave seven months of IS.

## 3. Screen (`exp01_screen.py`) — 18 features × 3 horizons

Entry, exit and net queue as level, log, sign, 7 d and 30 d change and 90 d z-score; realised
staking growth over 7 and 30 d. Raw, partial (trend controls) and against the ETH/BTC return.

| IS→OOS Spearman of t-stats | h = 1 | h = 7 | h = 30 |
|---|---|---|---|
| raw | −0.31 | −0.51 | −0.46 |
| partial | −0.06 | −0.60 | −0.68 |
| vs ETH/BTC | −0.53 | −0.55 | −0.33 |

Features with \|t\| ≥ 2 in IS that keep their sign and \|t\| ≥ 2 OOS: **0** in all nine cells.

| raw IC, h = 30 (HAC t) | IS | OOS |
|---|---|---|
| net queue, level | −0.19 (−1.4) | +0.12 (0.2) |
| log entry queue | −0.20 (−2.6) | +0.02 (0.1) |
| entry queue, 30 d change | +0.08 (0.0) | **−0.43 (−3.7)** |
| net queue, 30 d change | +0.07 (0.2) | −0.37 (−2.7) |
| staked amount, 30 d growth | +0.00 (−0.2) | **+0.53 (4.3)** |
| exit queue, 90 d z | +0.00 (1.5) | −0.06 (0.2) |

- In 2023–24 a long entry queue was *bearish* (it was the post-Shapella backlog draining while
  ETH lagged); in 2025–26 realised staking growth was strongly bullish and a *rising* entry
  queue bearish. Neither half supports the other.
- The exit queue shows IS t-stats of 4–6 at h = 7 on an IC of 0.03: the queue was zero for most
  of 2023–24, so the regression is carried by a handful of points. The rank IC is the number.
- Independent information is scarce: 17 episodes of an exit queue above 100k ETH in the whole
  sample. Forward 30 d returns after their start range from −26% to +61%, and the episodes follow
  both rallies (+42% in the prior 30 d, July 2025) and sell-offs (−33%, February 2026).

## 4. A-priori rules, 2023-06 → 2026-10

| | full | IS | OOS | MaxDD | turn | alpha t vs TF (full) |
|---|---|---|---|---|---|---|
| vol B&H | 0.54 | 1.02 | 0.10 | −53% | 4× | |
| TF_live | 1.15 | 0.77 | 1.52 | −40% | 18× | |
| net queue > 0 × vol | 0.53 | 0.72 | 0.34 | −44% | 32× | −0.40 |
| net queue rising 30 d × vol | −0.08 | 0.90 | −0.88 | −45% | 32× | −0.88 |
| net queue rising 7 d × vol | 0.16 | 0.36 | −0.02 | −37% | 42× | −0.54 |
| exit queue z90 < 1 × vol | 0.39 | 0.75 | 0.05 | −48% | 24× | −0.69 |
| contrarian: net queue < 0 × vol | −0.26 | 0.07 | −0.48 | −36% | 27× | −1.79 |
| TF AND net queue > 0 | 1.01 | 0.48 | 1.52 | −36% | 36× | 0.01 |
| TF AND net queue rising 30 d | 0.64 | 0.94 | 0.34 | −22% | 28× | −0.06 |
| TF veto exit queue z90 > 1 | 1.07 | 0.73 | 1.43 | −39% | 27× | 0.26 |
| TF veto net queue < 0 | 1.04 | 0.56 | 1.52 | −36% | 35× | 0.14 |

Nothing beats the trend filter; the narrative rule (hold while more ETH is queuing to enter than
to leave) ties vol-scaled buy-and-hold and loses to it in IS.

## 5. Verdict

**Failed.** The queues are public and timely but carry no stable directional information:

- the sign of every feature flips between 2023–24 and 2025–26 (rank correlation of the t-stats
  −0.5 to −0.7 at 7–30 days);
- the one strong OOS relation (30 d staking growth, IC +0.53) is absent in IS and coincides with
  the 2025 treasury-staking wave — one episode;
- the sample has 17 exit-queue episodes and the unstaked coins are not necessarily sold (the
  2025 exits were largely re-staked through other operators).

Binding constraint: history. The queues exist in their present form only since May 2023, and
the staking population changed twice in that time (liquid-staking rotation in 2023–24, treasury
and ETF staking in 2025–26). Worth a re-test in two or three years, not before.

Configurations evaluated: 18 features × 3 horizons × {raw, partial, vs ETH/BTC}; 9 costed rules;
3 lags.

## 6. Files

- `code/spot-eth/staking-queue-flow/fetch_queue.py` — fetcher + cache (`data/VALIDATORQUEUE_ETH_d.parquet`)
- `exp01_screen.py` (+ `exp01_raw_ic.csv`)
