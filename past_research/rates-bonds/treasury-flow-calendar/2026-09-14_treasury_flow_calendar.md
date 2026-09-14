# treasury-flow-calendar — calendar flow effects in long Treasuries (TLT)

**Date:** 2026-09-14 · **Asset class:** rates-bonds · **Status:** Working (borderline against the "Sharpe ≥ 1" brief; see §9)

**Brief:** "1+ Sharpe strat, ideally adding hedging to the existing live strats but not necessary."

## 1. Idea

Treasury prices carry three well-documented, calendar-driven flow effects. Each has a
mechanism, a published paper, and a date that is known in advance:

| Leg | Direction | Mechanism | Paper |
|---|---|---|---|
| Month-end | long, last 3 trading days of the month | Index duration extension at month-end; insurers and passive funds buy long coupons into the rebalance | Hartley & Schwarz (2019), *Predictable End-of-Month Treasury Returns* — Sharpe ≈ 1 for the last 2–3 days, 1990–2018 |
| FOMC | long, the trading day before and the day of the statement | Pre-announcement risk-premium compression; on average dovish surprises 2010→ | Lucca & Moench (2015) for equities; Savor & Wilson (2013) for announcement-day premia in bonds |
| Pre-auction | short, the 2 trading days before each 10y and 20y auction (reopenings included) | Dealers build a concession ahead of taking down supply; prices fall into the auction and recover after | Lou, Yan & Zhang (2013), *Anticipated and Repeated Shocks in Liquid Markets* — Sharpe 0.84 for their 10-day version, 1980–2008 |

The three signals are summed and clipped to [−1, +1], traded in TLT (iShares 20+ Year
Treasury) with daily bars. Exposure is non-zero on 32 % of days (19 % long, 13 % short).

Everything is knowable at the close it is set on: the Fed publishes FOMC dates a year ahead,
Treasury publishes a tentative auction calendar quarterly and firm dates about a week ahead
(the 2-day window sits well inside that), and NYSE holidays are fixed years ahead.

## 2. Data

* `data/TLT_d.parquet`, `IEF`, `SHY`, `LQD` — daily closes 2010→2026-09 (shared cache, adjusted).
  Pre-2010 holdout copies `data/<T>_d_pre2010.parquet` (2002-07→2009) fetched for this study.
* `data/IDX_TNX_d_pre2010.parquet`, `IDX_TYX_d_pre2010.parquet` — 10y/30y CMT yields 1990→2009,
  turned into synthetic par-bond returns for a long holdout (§6).
* Calendars, snapshotted in `code/rates-bonds/treasury-flow-calendar/calendar_snapshots/`:
  * `auctions.csv` — every note/bond auction 1990→2026-09 plus announced upcoming ones, from
    TreasuryDirect `TA_WS/securities/search` and `/upcoming`.
  * `fomc.csv` — statement day of every scheduled meeting 1982→2027-12.
  * `cpi.csv`, `payrolls.csv` — exact release dates from ALFRED vintage lists (tested, not used).

## 3. Method and split

Split fixed before the first backtest: **IS 2010-01→2017-12**, **OOS 2018-01→2026-09**,
plus a **PRE 2002-07→2009-12** ETF holdout that was never opened during the event study, and a
**1990→2009 synthetic-bond holdout** added at the end. Cost **2 bp per side** (TLT's quoted
spread is ~1 bp on ~$90; 2 bp is a deliberate margin). `research_lib.backtest` shifts weights
one bar, ann = 252.

Caveat on the OOS label: the event study that surfaced the three legs was run on the full
2010→2026 sample. The *legs* are literature priors, but the *windows* (3 days, 1+0 days,
2 days / 10y+20y) were read off a table that includes 2018→2026. The honest selection-free
numbers are the PRE holdouts and the walk-forward in §6.

## 4. Event study (2010→2026, daily close-to-close, bp and t-stat)

Full tables: `event_study_output.txt`. Highlights on TLT:

| Event | Day | TLT mean bp | t |
|---|---|---|---|
| Month-end | last day / −1 / −2 / −4 | +14.8 / +10.3 / +11.9 / +12.9 | 2.4 / 2.0 / 1.8 / 2.2 |
| Month-start | +3 / +5 | −14.4 / −11.7 | −2.1 / −1.6 |
| FOMC | day before / day of | +14.5 / +20.6 | 2.0 / 2.2 |
| 10y auction | −2 / −1 | −13.8 / −8.3 | −2.1 / −1.3 |
| 20y auction (2020→) | −2 / −1 / 0 | −27.0 / −12.4 / +18.6 | −2.7 / −1.3 / 1.8 |
| 30y auction | −3 / −2 / +1 | −12.1 / −5.5 / +7.0 | −1.8 / −0.9 / 1.1 |
| CPI, payrolls | any | nothing usable | |t| < 1.3 |

The month-end effect is stable across halves (last 3 days ≈ +12 bp/day in both 2010–17 and
2018–26). The 2y/5y/7y auctions fall in the last week of the month and are confounded with
month-end, so they are not traded separately.

## 5. Backtests (TLT, 2 bp/side) — `backtest_v1_output.txt`, `round2_output.txt`

### Single legs

| Leg | PRE 02-09 | IS 10-17 | OOS 18-26 | FULL 10-26 |
|---|---|---|---|---|
| month_end3 | 0.76 | 0.98 | 0.59 | 0.78 |
| month_end2 | 1.13 | 0.90 | 0.39 | 0.64 |
| month_end4 | 0.60 | 0.79 | 0.51 | 0.65 |
| fomc day-before + day | 0.14 | 0.43 | 0.80 | 0.63 |
| fomc day only | −0.10 | 0.00 | 0.77 | 0.43 |
| fomc 2-before + day | 0.23 | 0.24 | 0.53 | 0.40 |
| pre-auction 10y+20y, 2d | −0.30 | −0.12 | 1.29 | 0.72 |
| pre-auction 10y only, 2d | −0.30 | −0.12 | 0.96 | 0.48 |
| pre-auction 10y+20y, 1d / 3d | −0.25 / −0.06 | −0.20 / 0.24 | 0.54 / 0.97 | 0.25 / 0.67 |
| pre-auction 10y+30y, 5d (LYZ window) | −0.07 | 0.54 | 0.39 | 0.46 |
| post-auction 10y/30y, +1,+2 | 0.46 | 0.26 | −0.15 | 0.04 |
| month-start short, days 3&5 | 0.24 | 0.49 | 0.42 | 0.45 |
| month-start short, all first 5 / first 3 | 0.30 / 0.58 | 0.33 / 0.58 | 0.39 / −0.01 | 0.36 / 0.26 |
| mid-month settlement long (+1,+2 after 15th) | 0.45 | 0.39 | −0.16 | 0.08 |

### Combinations

| Combination | PRE 02-09 | IS 10-17 | OOS 18-26 | FULL 10-26 | CAGR full | MaxDD full |
|---|---|---|---|---|---|---|
| **core3 = month_end3 + fomc + pre-auction** | **0.63** | **0.88** | **1.55** | **1.25** | 10.3 % | −11.5 % |
| month_end3 + fomc | 0.84 | 1.11 | 0.90 | 1.00 | 6.3 % | −7.2 % |
| month_end3 + pre-auction | 0.48 | 0.68 | 1.38 | 1.07 | | |
| core3 + post-auction | 0.72 | 0.86 | 1.18 | 1.03 | | |
| core3 + month-start short (3,5) | 0.73 | 1.10 | 1.55 | 1.35 | 12.6 % | −10.2 % |
| core3 + month-start short (all 5) | 0.70 | 0.99 | 1.29 | 1.15 | | |
| all five legs | 0.84 | 1.07 | 1.25 | 1.17 | | |
| core3 on IEF | 0.52 | 0.88 | 1.60 | 1.29 | 4.8 % | −4.9 % |
| core3 on SHY | 0.31 | −0.41 | 0.36 | 0.11 | | |

`core3 + month-start short (3,5)` is the best full-sample cell but the days 3 and 5 were
cherry-picked from the event table (days 1, 2, 4 are not negative); the un-mined version
(short all five first days) does not beat core3. **core3 is the deployed configuration** —
each leg has a paper, and it was declared the a-priori core before the combination table was run.

### Sizing and cost

Vol-targeting the position (target 12–20 %, cap 1–2×) changes nothing: full Sharpe 1.16–1.18
vs 1.25 unscaled. Constant leverage does not change Sharpe; the spec caps gross at 1.0.

| Cost/side | 0 bp | 1 bp | 2 bp | 3 bp | 5 bp | 10 bp |
|---|---|---|---|---|---|---|
| FULL 2010-26 | 1.43 | 1.35 | 1.26 | 1.18 | 1.02 | 0.60 |
| OOS 2018-26 | 1.75 | 1.66 | 1.57 | 1.49 | 1.31 | 0.86 |

Turnover is 66 round-trips per year, so the strategy is cost-sensitive: it dies above ~5 bp.
TLT trades at ~1 bp; the simulator must not be configured with the crypto default of 10 bp.

## 6. Robustness — `robustness_v1_output.txt`, `long_holdout_output.txt`

**Per-year Sharpe, core3 (2 bp):** 2010 2.43 · 2011 1.63 · 2012 −0.67 · 2013 0.10 · 2014 −0.04 ·
2015 0.37 · 2016 1.50 · 2017 1.08 · 2018 1.54 · 2019 2.51 · 2020 1.99 · 2021 0.86 · 2022 2.56 ·
2023 1.68 · 2024 1.12 · 2025 1.33 · 2026 (to Sep) ≈ 0. Three flat years in 2012–15; nothing
below −0.7.

**Walk-forward leg selection** (expanding window from 2002, each year keeps only the legs whose
Newey-West t on data *before* that year exceeds a threshold; 5–7 candidates):

| Threshold | 2010-26 | 2010-17 | 2018-26 |
|---|---|---|---|
| t > 0.5 | 0.86 | 0.99 | 0.75 |
| t > 1.0 | 0.75–0.88 | 0.72–0.80 | 0.71–1.01 |
| t > 1.5 | 0.52–0.80 | 0.65–0.72 | 0.43–0.87 |

The walk-forward never reaches 1.0. It always carries month-end; it only adds the pre-auction
leg from 2023, after the leg had already delivered its best years, and it keeps the
post-auction leg (good until 2017, dead after) through 2022. **This is the selection-free
estimate: 0.75–0.88.**

**1990→2009 synthetic-bond holdout** (par-bond returns from the 10y and 30y CMT yields; the
proxies correlate 0.95 / 0.94 with IEF / TLT on 2010→2026):

| | synthetic 10y 1990-99 | 2000-09 | 1990-09 | synthetic 30y 1990-99 | 2000-09 | 1990-09 |
|---|---|---|---|---|---|---|
| month_end3 | 0.83 | 0.71 | 0.76 | 0.83 | 0.77 | 0.78 |
| fomc | 0.81 | 0.39 | 0.55 | 0.84 | 0.26 | 0.48 |
| pre-auction 2d | 0.18 | −0.28 | −0.08 | 0.20 | −0.16 | −0.02 |
| **core3** | **1.08** | **0.73** | **0.87** | **1.10** | **0.77** | **0.89** |
| month_end3 + fomc | 1.09 | 0.88 | 0.96 | 1.11 | 0.92 | 0.99 |

Month-end and FOMC replicate over twenty untouched years at roughly the 2010→2026 level. The
pre-auction concession does not exist before 2010: it is a feature of the post-2009 issuance
regime (auction sizes roughly tripled, and the 20y was reintroduced in 2020), which is
consistent with the dealer-balance-sheet mechanism but means that leg carries regime risk.

**Deflated Sharpe** (25 trials, skew 1.4, excess kurtosis 16): P(SR > 0) ≈ 1.00 — the full
sample t-stat of 5.4 leaves no room for a multiple-testing explanation; the doubt is
stationarity, not noise. **Block bootstrap** (21-day blocks, 2010→2026): Sharpe 5–95 %
[0.91, 1.63], P(SR > 1) = 0.89.

**Month-of-year diagnostic** (is month-end stronger in refunding or quarter-end months?):
no — refunding months +13–14 bp/day vs +11 bp otherwise, in both 1990–2009 and 2010–2026.
Not used.

## 7. Relation to the live book (the "hedging" part of the brief)

Daily correlation with the live spot-crypto trend strategies (weekday-trend on BTC and the
published ETH SMA(40) rule, both re-run here) is −0.03 / +0.02; weekly −0.06 / −0.01. In the
worst-decile weeks of the BTC weekday-trend book (mean −3.8 %), this strategy returned +0.37 %
on average — small and positive, not a hedge. Because it is uncorrelated with positive
carry, adding it to the BTC book at 1× raises the book's weekly Sharpe from 1.09 to 1.66 in
the 2018→2026 overlap; at 2× to 1.96. It is a **diversifier**, not a hedge. TLT buy-and-hold
itself is also uncorrelated with the crypto book (−0.02), so no rates instrument in this
universe offers a genuine hedge on daily data.

## 8. What failed / did not help

* Post-auction recovery (Lou-Yan-Zhang's second half): positive 1990→2017, dead since (0.04 full).
* CPI and payrolls days: no usable premium in TLT (|t| < 1.3) — the Savor-Wilson bond effect
  does not survive on 2010→2026 ETF data.
* Month-start short legs: only the cherry-picked (3,5) version helps; the un-mined versions
  add nothing. Not deployed.
* Mid-month settlement / coupon reinvestment long: 0.08 full.
* IEF instead of TLT: identical Sharpe, half the return; SHY: too small vs cost.
* LQD month-end: 0.32 / 1.36 / 0.60 — weaker and less stable than TLT.
* Vol-targeted sizing: no improvement.
* Conditioning month-end on refunding / quarter-end months: no difference.

## 9. Verdict

Full-sample net Sharpe **1.26** (2010→2026, 2 bp), IS 0.88, OOS 1.57, CAGR 10.4 %, max DD
−11.5 %, average gross exposure 32 %, 66 round-trips/year. Against the literal brief
("1+ Sharpe") the full-sample and 2018→2026 numbers clear it. Against the selection-free tests
they do not: walk-forward 0.75–0.88, 2002–09 ETF holdout 0.63, 1990–2009 synthetic 0.87–0.89.
The month-end + FOMC pair alone is the robust core (≈1.0 across 36 years on three instruments);
the pre-auction leg is what lifts 2018→2026 to 1.5 and is a post-2010 regime feature.

Honest expectation for live: Sharpe **0.9–1.2** at 2 bp, with the pre-auction leg the first
thing to break if auction sizes fall. Reported as **Working** with that caveat stated in the
PR's acceptance block; the deployment agent should treat "Met" as borderline.

## 10. Files

* Code: `code/rates-bonds/treasury-flow-calendar/` — `calendars.py` (fetch + snapshots),
  `event_study.py`, `backtest_calendar.py`, `robustness.py`, `round2.py`, `long_holdout.py`,
  `final.py`, **`strategy.py`** (deployable).
* Outputs: this folder — `event_study_output.txt`, `backtest_v1_output.txt`,
  `robustness_v1_output.txt`, `round2_output.txt`, `long_holdout_output.txt`, `final_output.txt`.
* Alpha: `alphas/rates-bonds/treasury-flow-calendar/` — `spec.md`, figures 01–05,
  `backtest_series.parquet`, `weights_and_returns.csv`.

Variants evaluated: 13 legs × TLT, 6 combinations, IEF/SHY/LQD instrument checks, 4 sizing
variants, 3 un-mined round-2 legs and 5 round-2 combinations on two instruments, 6
walk-forward configurations — about 45 distinct backtests over roughly 30 distinct strategy
configurations, all reported above.
