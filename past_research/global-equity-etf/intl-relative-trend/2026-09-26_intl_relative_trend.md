# Slow relative trend of country ETFs vs SPY — Working (modest)

**Asset class:** `global-equity-etf` · **Short name:** `intl-relative-trend` · **Date:** 2026-09-26
**Status:** **Working.** Market-neutral, net Sharpe **0.64 full / 0.60 IS / 0.67 OOS** at 5 bp/side
on the ETFs (2001-2026). **0.52** on an independent 1980-2000 backcast. Modest, but the most
stable edge found in this asset class so far.

## Idea and where it came from

`dollar-regime-tilt` used the spread's *own* trend as a control for the dollar signal, and the
control beat the dollar. This idea takes that control seriously. The US-vs-rest-of-world equity
spread moves in **multi-year regimes**: 1985-89 Japan/ex-US, 1990-2000 US, 2002-07 ex-US/EM,
2008-26 US with brief reversals. The drivers are slow: allocation and home-bias flows, the
dollar cycle, and sector composition (US tech vs ex-US financials/materials). A slow
time-series trend on each country's SPY-hedged spread should ride those regimes.

This is **not** the country cross-sectional momentum that already failed
(`country-xs-momentum`, and `mom` in `dividend-yield-carry`, ≈ 0.1). XS momentum is
dollar-neutral *within* the cross-section and throws away the US-vs-rest factor. The edge here
lives in that factor: the aggregate sleeve alone carries it (0.71), and the per-country sleeve
is that factor plus noise (monthly corr 0.77).

## Final spec (`code/global-equity-etf/intl-relative-trend/strategy.py`)

1. For each of `EWJ EWG EWU EWZ EWY EWA EWC FXI INDA`, the daily spread is
   `r_i − β_i(t−1)·r_SPY`, where β is the rolling 252d close-to-close beta (min 126). "EXUS" is the
   equal-weight average of the available countries' returns, hedged the same way.
2. Signal = mean over L ∈ {126, 252, 504} trading days of sign(log cumulative spread over L).
3. **Month-end rebalance** (last trading day). Position = signal / (126d annualised spread vol).
   The ETF weight is the position; the SPY hedge is −Σ position·β.
   * AGG sleeve: the EXUS position split equally over the available country ETFs.
   * DIV sleeve: the 9 per-country spreads.
4. Each sleeve is scaled to 10 % ex-ante vol (trailing 126d covariance of the traded ETFs + SPY).
   They are blended 50/50 and the blend is re-scaled to 10 % (scalar ≤ 3).
5. Weights are held to the next month-end. Signals use closes up to t, and weights apply from t+1.

## Evidence

### ETF era, 2001-07 → 2026-09 (`03_robustness.py`, numbers from `strategy.target_weights`)

| | Full | IS 2001-12 | OOS 2013-26 |
|---|---:|---:|---:|
| Net Sharpe (5 bp/side ETFs, 1 bp SPY) | **0.64** | 0.60 | **0.67** |
| CAGR | 6.7 % | 6.0 % | 7.3 % |
| Vol | 11.2 % | 10.6 % | 11.6 % |
| Max drawdown | −24.5 % | −24.5 % | −19.6 % |
| t (Newey-West, 21 lags) | 3.18 | | |

* Turnover 7.9× gross per year. Average gross 2.10 (median 2.06, 99th pct 3.33, **max 3.53**).
  Average net country exposure −0.34, with SPY +0.31 on average. The book was net short ex-US in
  60 % of months.
* Correlation to SPY: **−0.06 daily, −0.02 monthly**.
* Stationary block bootstrap (63d blocks, 2000 draws): median Sharpe 0.63, 5th pct 0.31,
  P(SR > 0) = 0.999, P(SR > 0.5) = 0.76. Deflated Sharpe at N = 60 trials: 0.80.

### Sensitivity (all full-sample net Sharpe)

| Change | Sharpe | Change | Sharpe |
|---|---:|---|---:|
| **spec** | **0.64** | +1 day execution lag | 0.62 |
| AGG sleeve only | 0.71 | +5 day lag | 0.57 |
| DIV sleeve only | 0.52 | costs 2 bp | 0.65 |
| beta window 126 / 504 | 0.55 / 0.66 | costs 10 bp | 0.61 |
| lookbacks {252} | 0.49 | vol window 63 | 0.65 |
| lookbacks {126, 252} | 0.41 | mid-month rebalance | 0.67 |
| lookbacks {252, 504} | 0.61 | lookbacks {63…504} | 0.56 |

The weak spot is the 504-day leg. Without it the OOS falls to 0.30. That is consistent with the
backcast, where the 24-month lookback is the strongest single horizon (0.54 over 46 years).

### Independent backcast, 1977-2000 (`02_long_history.py`)

USD-converted local price indices (Nikkei, FTSE, TSX, ASX 200, Hang Seng; DAX from 1999) are
converted at FRED H.10 month-end FX and compared against the S&P 500. It runs monthly, with a
36-month beta and 10 bp/side on leg + hedge. Coverage is 1 country until 1984, 2 until 1987,
and 4-6 after. Germany is left out before 1999: FRED's only DM series is a *monthly average*,
and averaging creates positive autocorrelation that would flatter a trend test.

| Signal | 1980-2000 | 1985-2000 | 2001-12 | 2013-26 | 1980-2026 |
|---|---:|---:|---:|---:|---:|
| **Blend 50/50, slow 6/12/24m (the spec)** | **0.52** | **0.63** | 0.58 | 0.59 | **0.56** |
| AGG, slow | 0.35 | 0.38 | 0.59 | 0.63 | 0.50 |
| DIV, slow | 0.57 | 0.79 | 0.53 | 0.51 | 0.55 |
| AGG, fast ensemble 1/3/6/12m | 0.17 | 0.14 | 0.47 | 0.30 | 0.28 |
| AGG, 1m / 3m | −0.10 / −0.03 | | | | 0.06 / 0.05 |
| AGG, 12m / 24m | 0.37 / 0.25 | | | | 0.44 / 0.54 |

None of the 1980-2000 data was used for any choice. **The slow-beats-fast pattern and the ~0.5
Sharpe level both replicate there.**

## Honest accounting of the search

* The first specification tried (in `dollar-regime-tilt`) was the fast ensemble 21/63/126/252d.
  The slow ensemble was added in `01_trend_books.py` after seeing ETF-era results. In-sample
  (2001-12) the 21-day lookback looked best (0.92 IS → 0.06 OOS), so **an in-sample selection
  would have chosen the wrong horizon.** The independent case for the slow ensemble is the
  1980-2000 backcast, not the ETF era.
* The blend was chosen a priori over the higher-scoring AGG-only book (0.71), to avoid picking
  the best sleeve.
* Cells evaluated: 35 (`01`) + 16 (`02`) + 15 sensitivity (`03`) ≈ 66, plus the 43 in
  `dollar-regime-tilt` whose control led here. DSR is reported at N = 60.
* Effective sample: the regimes are long, so the number of independent bets is small, perhaps
  5-7 major regime switches in 46 years. The annual-return Sharpe (≈ 0.56) is a little below the
  daily one, since P&L is positively autocorrelated within regimes. Treat this as a
  0.4-0.6-Sharpe diversifier, not a 0.64 certainty.

## Failure modes

* **Regime turns.** The worst stretch is 2010-12 (−24.5 %), where the 2009-10 EM rebound and
  euro-crisis whipsaw hit. Rolling 3y Sharpe dips to −0.6 there and to −0.5 in 2025, when ex-US
  bounced against a long-US book.
* **Long-lookback dependence.** Most of the edge sits in the 12-24 month horizon. It is slow to
  react by construction and will give back a chunk at each regime flip.
* **Crowding with the US-exceptionalism trade.** The book has been net long SPY vs ex-US for most
  of 2013-2026. If that trade unwinds in one violent move, expect a drawdown before the trend
  flips.

## Files

* Spec: `alphas/global-equity-etf/intl-relative-trend/alpha.md`, figures `equity_drawdown.png`,
  `long_history_backcast.png`
* Code: `code/global-equity-etf/intl-relative-trend/strategy.py` (deployable), `lib.py`,
  `01_trend_books.py`, `02_long_history.py`, `03_robustness.py`, `04_figures.py`
* Data added: `data/<T>_d_pre2010.parquet` for the country ETFs and indices,
  `data/<IDX>_d_long.parquet` (pre-2001 local indices), `data/FRED_DEX*_d.parquet` (H.10 FX)
* **Look-ahead test:** `strategy.target_weights` run on data truncated at 2008-10-31, 2015-06-30, 2020-03-31 and 2026-08-31 reproduces the full-sample weights on those dates exactly (max abs diff 0).
* **Live-edge fix (found while building the blend).** The first version picked month-ends as
  "last date of each month in the data". On a partially observed month that makes every new day
  a rebalance day, so the live runner would re-trade daily and diverge from the backtest. The
  rebalance day is now one whose *next NYSE session* (`code/global-equity-etf/shared/trading_calendar.py`,
  holiday list 2026-27, **extend yearly**) is in a new month. Truncation tests at mid-month dates
  (2026-09-15/16/24) now match exactly. Historical numbers are unchanged to 2 decimals.
* **Superseded for deployment by [`global-etf-sleeve-blend`](../global-etf-sleeve-blend/)**, which
  adds the uncorrelated FOMC sleeve: 0.81 / 0.77 / 0.86. Deploy one or the other, not both.
