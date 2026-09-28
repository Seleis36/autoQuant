# muni-reinvestment-flow — municipal-bond coupon reinvestment flows vs Treasuries

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Working (borderline)** — weak
standalone (net Sharpe 0.52 over 2008-26), uncorrelated with the deployed rates sleeve

## 1. Idea

Munis are a flow-driven market: retail-dominated, fragmented, with coupons and principal
redemptions concentrated on the 1st of the month (and in size on Jan 1, Jun 1, Jul 1,
Dec 1). Two flow effects are widely cited by muni strategists:

* **Summer reinvestment season** — June-August reinvestment of the largest coupon/redemption
  wave against light new-issue supply: munis outperform Treasuries.
* **Tax season** — retail sells munis / funds see outflows into the April 15 deadline:
  munis underperform in March-April.

The traded object is the **duration-hedged muni premium**, muni ETF minus a trailing-beta
position in the Treasury ETF of similar duration, so the result cannot be the Treasury
calendar that `treasury-flow-calendar` already trades.

## 2. Data

* Muni ETFs: MUB (iShares, 2007-09), TFI (SPDR, 2007-09), ITM (VanEck, 2007-12), SHM (SPDR short,
  2007-10), HYD (VanEck high-yield, 2009-02). `00_fetch.py` added `*_d_pre2010.parquet` copies.
* Hedges: IEF (MUB/TFI/ITM/HYD), SHY (SHM).
* Muni mutual funds for the untouched holdout: VWITX, VWLTX, VWSTX, VMLTX, VWAHX (Vanguard) and
  PRTAX (T. Rowe Price), daily unadjusted NAVs from 1980 → `data/MUNI_FUNDS_nav_d.parquet`.
  These are daily-accrual funds: income is paid on the last business day of the month outside
  the NAV, so the unadjusted NAV is a pure price series. Checked: the mean NAV change on pay
  dates is +0.4 … +2.7 bp, against dividends of 28–49 bp, so there is no drop.
* Synthetic 10y CMT *price* returns (FRED) as the Treasury hedge for the NAV series.

## 3. Research path — every step, including the failed ones

### 3.1 Pre-registered seasonal book — `01_screen.py`, `01_screen_output.txt` → **Failed**

Long the hedged premium Jun-Aug, short it Mar-Apr, 3 bp/side/leg; IS 2008-2016, OOS
2017-2026, fixed before any number was computed.

| | MUB | TFI | ITM | SHM | HYD |
|---|---|---|---|---|---|
| IS 2008-16 | −0.15 | −0.14 | 0.08 | 0.32 | −0.23 |
| OOS 2017-26 | 0.20 | 0.26 | 0.25 | 0.30 | 0.15 |

The calendar-month profile is unstable (MUB April +126 bp IS → −15 bp OOS; November −61 →
+120). The seasonal story does not hold at monthly resolution.

### 3.2 Day-of-month diagnostic — `01_screen.py` (tail), `02_month_start_days.py`

The same script carried a pre-specified diagnostic — the first 3 trading days of the month
(coupons pay on the 1st) vs the rest. It was flat in 2008-16 and strong in 2017-26 (MUB first
3 days +2.5 bp/day, t 2.5; SHM +2.4, t 4.3; rest ≈ 0). The day-by-day split (02) put the
2017-26 premium on days 1-5 (MUB_h +1.0/+3.7/+3.0/+2.6/+2.5 bp; TFI_h, ITM_h, SHM_h alike), with
the rest of the month ≈ −0.3 bp/day.

**Artefact check.** iShares, SPDR and VanEck bond ETFs go ex-dividend on the first business
day of the month, and a mis-dated dividend in Yahoo's adjusted closes would manufacture a
month-start return. Raw closes plus Yahoo's dividends reproduce the adjusted returns to
≤ 1.4 bp/day, and 129 of 140 ex-dates sit on trading day 1. The pattern is not an
adjustment artefact.

**Honest status at this point:** the effect was *found* in 2017-2026 ETF prices, so those
years cannot serve as its out-of-sample test.

### 3.3 Untouched holdout: muni fund NAVs 1990-2016 — `03_nav_holdout.py`, `03_nav_holdout_output.txt`

The statistic was written into the script before any holdout number was computed:
D_m = Σ(hedged daily premium over trading days 1-5 of month m) − 5 × mean(premium over the
rest of month m), with the premium = NAV return − b0·r_T,t − b1·r_T,t−1 (trailing 252-day OLS,
lagged; the lag term absorbs stale evaluated pricing).

| Six-fund average D | mean bp/month | t | hit rate | months |
|---|---|---|---|---|
| 1990-1999 | 1.3 | 0.39 | 0.54 | 120 |
| **2000-2007** | **6.5** | **2.47** | 0.69 | 96 |
| 1990-2007 | 3.6 | 1.66 | 0.61 | 216 |
| 2008-2016 | 12.5 | 2.59 | 0.60 | 108 |
| 2017-2026 (discovery window) | 13.7 | 4.63 | 0.74 | 117 |

Every fund is positive in 2000-07, 2008-16 and 2017-26; none is significant in the 1990s. The
flow exists in the underlying market out of sample: absent in the 1990s, present from
2000 and growing. That fits the growth of muni mutual funds, ETFs and separately managed
accounts that reinvest monthly.

### 3.4 Does it reach traded prices? — `04_etf_D.py`, `04_etf_D_output.txt`

The same D on the ETFs:

| | MUB | TFI | ITM | SHM | HYD | VWITX NAV |
|---|---|---|---|---|---|---|
| 2008-16, bp (t) | 2.1 (0.3) | 3.8 (0.6) | 11.9 (1.5) | −4.1 (−0.9) | −8.4 (−0.9) | 13.0 (2.3) |
| 2017-26, bp (t) | 15.4 (4.3) | 22.1 (5.2) | 28.0 (5.3) | 13.6 (6.6) | 13.6 (1.6) | 16.2 (5.3) |

Monthly correlation of the ETF D with the NAV D is 0.61-0.78. **In 2008-16 the NAV effect did
not show up in ETF market prices**; from 2017 it does. So the *tradable* version is a
post-2017 phenomenon, even though the flow itself is older. One reading is that muni ETF
prices tracked the underlying far more loosely before the muni-ETF boom. Another is that the
2008-16 NAV effect is partly evaluated-pricing behaviour. The data cannot separate the two.

### 3.5 Big reinvestment months — `06_by_month.py`

A-priori group {Jan, Jun, Jul, Dec}: NAV 2000-07 11.1 vs 4.2 bp (big vs other), 2008-16 13.6 vs
11.9, ETFs 2017-26 29.7 vs 14.8. The 2000-2016 NAV calendar-month means put January
(+35 bp) and February (+21) on top, and December is negative (−3). The support is mixed, so no tilt
was adopted.

### 3.6 The book — `05_backtest.py`, `strategy.py`, `07_final.py`

Specification (window = the NAV statistic's 5 sessions; everything else fixed before 07):
at the close of the last trading day of month m−1, go long 1/4 notional each of MUB, TFI,
ITM, SHM and short β × IEF (β × SHY for SHM), β = trailing 252-day OLS beta of daily returns;
hold to the close of trading day 5 of month m; flat otherwise. 2 bp/side on every leg.

**Primary result (`07_final_output.txt`, via `strategy.target_weights` + `research_lib.backtest_xs`):**

| | Sharpe | CAGR | Vol | MaxDD | t (NW) |
|---|---|---|---|---|---|
| 2008-2016 | 0.18 | 0.3 % | 1.5 % | −3.8 % | 0.54 |
| 2017-2026 (discovery window) | 0.88 | 1.2 % | 1.3 % | −2.9 % | 2.89 |
| **Full 2008-2026** | **0.52** | 0.7 % | 1.4 % | −3.8 % | 2.32 |

Held on 23.5 % of sessions; average gross when held 1.37 (1.00 muni + 0.37 Treasury hedge);
turnover 33× a year.

Per-year net Sharpe: 2008 −0.19 · 2009 2.05 · 2010 −0.75 · 2011 0.76 · 2012 −0.22 · 2013 −0.23 ·
2014 −0.73 · 2015 −1.64 · 2016 0.55 · **2017 2.51 · 2018 −0.11 · 2019 1.61 · 2020 0.86 · 2021 2.18 ·
2022 1.69 · 2023 1.75 · 2024 0.42 · 2025 −0.00 · 2026 (to Sep) 0.85.**

Cost ladder (full / 2017-26): 0 bp 0.99 / 1.40 · 0.5 bp 0.87 / 1.27 · 1 bp 0.76 / 1.14 ·
**2 bp 0.52 / 0.88** · 3 bp 0.29 / 0.62 · 5 bp −0.17 / 0.11. Quoted spreads are ~1 bp on MUB
and IEF (≈$106 / $95 with a 1¢ tick) and ~2 bp on TFI, ITM and SHM (≈$46), so 2 bp/side is
2-4× the half-spread. The strategy is cost-sensitive and dies above ~4 bp.

Sensitivities (2 bp, full / 2017-26): 3 sessions 0.19 / 0.39 (day 1 is the weakest day);
7 sessions 0.49 / 1.01; 5-ETF basket including HYD 0.47 / 0.80; MUB only 0.28 / 0.59.
The 4-ETF basket was fixed before 07, but HYD's exclusion came after 04 had shown HYD weaker.
Including it costs 0.05.

### 3.7 Lookahead and live-edge checks

* Weights on row t are set from data through close t and applied to t+1 (backtest_xs shift).
  The calendar (the first 5 sessions of the next month) is known in advance. β uses returns
  through the decision close.
* **Truncation test:** weights recomputed on data cut at the first two and last two sessions
  of every month 2019-2026 (368 cuts) equal the full-run weights: **0 mismatches**. The first
  run found 1 mismatch (2021-12-30). pandas' `nearest_workday` observes a Saturday New Year's
  Day on the preceding Friday; NYSE does not. `strategy.py` now uses the NYSE rule.
  **The deployed `treasury-flow-calendar/strategy.py` uses the same pandas rule** and would
  mis-date its live month-end window on 2027-12-31 (New Year 2028 is a Saturday). That file
  was not modified here, but the deployment agent should look at it.

### 3.8 Relation to the deployed rates sleeve

Correlation with `treasury-flow-calendar` net returns: daily −0.007, weekly 0.036, monthly
0.005. The two books barely overlap in time: TFC is long TLT in the last 3 sessions of the
month; this book is long munis / short Treasuries in the first 5. Blend (same 2008-26
sample):

| | full Sharpe | 2017-26 Sharpe |
|---|---|---|
| treasury-flow-calendar alone | 1.21 | 1.53 |
| + muni book at half TFC's risk (2.9× muni notional) | **1.32** | **1.77** |
| + muni book at equal risk (5.8×) | 1.23 | 1.73 |

## 4. Multiple testing

About 45 distinct book configurations were evaluated under this short name: 5 seasonal
books, a 5-instrument × 3-window × 2-hedge grid, 4 sensitivities, and the primary. The
deflated-Sharpe probability of the full-sample 0.52 over 45 trials is **0.44**. Taken alone,
the 2008-2026 ETF backtest does not prove an edge. The case for one rests on:
(i) the untouched 2000-2016 NAV holdout (t 2.5 in each of two sub-periods, every fund
positive); (ii) the t-stats of 4-7 across five ETFs in 2017-26, well past what 45 trials
produce by chance, although those years are also where the effect was spotted.

## 5. Verdict

**Working (borderline).** A real, documented flow is visible in muni fund NAVs out of sample
since 2000, and in muni ETF prices since 2017, strongly. It is tradable as a small,
market-neutral, low-turnover sleeve that is uncorrelated with everything else in the rates
book. Standalone it is weak: 0.52 net over 2008-26, 0.18 before 2017, and < 1 % a year per
unit of notional. Its value is as a diversifier next to `treasury-flow-calendar`. Honest
live expectation: Sharpe 0.5-0.9 at 2 bp/side, with regime risk: 2024-25 were flat.

## 6. Files

* Code: `code/rates-bonds/muni-reinvestment-flow/` — `00_fetch.py`, `01_screen.py`,
  `02_month_start_days.py`, `03_nav_holdout.py`, `04_etf_D.py`, `05_backtest.py`, `06_by_month.py`,
  `07_final.py`, `mlib.py`, **`strategy.py`**.
* Outputs: `*_output.txt` next to each script (copied here), `05_backtest.csv`, `03_nav_holdout.csv`.
* Alpha: `alphas/rates-bonds/muni-reinvestment-flow/` — `spec.md`, `backtest_series.parquet`,
  `weights.parquet`, figures 01-03.
