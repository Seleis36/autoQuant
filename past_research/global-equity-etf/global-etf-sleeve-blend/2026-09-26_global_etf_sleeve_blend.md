# Global-ETF sleeve blend — Working

**Asset class:** `global-equity-etf` · **Short name:** `global-etf-sleeve-blend` · **Date:** 2026-09-26
**Status:** **Working.** Net Sharpe **0.81 full / 0.77 IS / 0.86 OOS** (2001-07 → 2026-09, 5 bp/side),
CAGR 7.2 %, max DD −21 %, correlation to SPY 0.10. **This is the recommended deployment from this
session.** It supersedes deploying `intl-relative-trend` on its own.

## What it is

An equal-risk combination of the two uncorrelated country-ETF edges found this session:

| Sleeve | Mechanism | Standalone net Sharpe (full / IS / OOS) |
|---|---|---|
| [`intl-relative-trend`](../intl-relative-trend/) | slow (6/12/24m) trend of each country's SPY-hedged spread + the ex-US aggregate; month-end; market-neutral | 0.64 / 0.60 / 0.67 |
| [`fomc-global-beta`](../fomc-global-beta/) | long the EW country basket over FOMC day −1 and day 0 (Lucca-Moench, Brusa-Savor-Wilson) | 0.45 / 0.45 / 0.51 |

Daily correlation of the two sleeves: **−0.06**.

```
w_t = 0.67 * intl_relative_trend.target_weights(close)  +  0.87 * fomc_global_beta.target_weights(close)
```

Both constants were fixed on IS data only (2001-07 → 2012), in `01_calibrate.py`:
* k = vol(trend) / vol(FOMC at gross 1) = **1.290**, which gives equal risk;
* L = 0.10 / vol(0.5·trend + 0.5·k·FOMC) = **1.342**, which gives a 10 % book;
* so A = 0.5·L = 0.67 and B = 0.5·L·k = 0.87.

Equal risk (1/N) was the a-priori choice. A one-third FOMC risk share is shown as a
sensitivity (0.77); it was not selected.

## Results (`02_evaluate.py`, numbers from `strategy.target_weights`)

| | Full | IS 2001-12 | OOS 2013-26 |
|---|---:|---:|---:|
| **Net Sharpe, 5 bp/side (SPY 1 bp)** | **0.81** | 0.77 | **0.86** |
| CAGR | 7.2 % | 7.5 % | 6.9 % |
| Max drawdown | −21.0 % | −21.0 % | −13.1 % |
| Vol | 9.1 % | | |
| t (Newey-West) | 3.99 | | |
| Net Sharpe at 2 bp / 10 bp | 0.87 / 0.72 | 0.83 / 0.69 | 0.93 / 0.75 |

* Turnover 19× gross per year: trend ≈ 5, FOMC ≈ 14, the latter from 16 round trips a year on
  the basket.
* Gross exposure: average 1.41, 99th pct 2.31, **max 3.00**. Average net +0.035.
* Correlation to SPY 0.10 daily.
* Bootstrap (63d stationary blocks, 2000 draws): median 0.82, 5th pct 0.46, P(SR > 0) = 1.000,
  P(SR > 0.5) = 0.93.
* Deflated Sharpe at N = 100 trials (the whole session's ~250 cells are mostly correlated
  variants within ideas; N = 100 is a conservative effective count): 0.95.
* Calendar years: 19 of 26 positive. Worst: 2002 −18 %, 2010 −10.5 %, 2025 −6.4 %.
* **Look-ahead:** weights computed on data truncated at 2009-03-31, 2019-12-31 and 2026-09-15
  (mid-month, inside an FOMC window) equal the full-sample weights exactly.
* **"+1 day lag" drops the blend to 0.64 (OOS 0.53).** This is not a look-ahead symptom.
  The FOMC sleeve trades a calendar published a year in advance, and lagging it by a day moves
  the window onto days 0/+1, which are negative OOS. The trend sleeve alone loses only
  0.64 → 0.62 under the same lag.

## Risks

* The trend sleeve is a bet on multi-year US-vs-ex-US regimes. It is slow to turn, and each
  regime flip costs a drawdown (2002, 2010-11, 2023, 2025).
* The FOMC sleeve's P&L is concentrated: the top 5 of 205 meetings carry 55 % of it. A decade
  without crisis-era Fed surprises would leave it at ≈ +16 bp per meeting.
* Both sleeves depend on the NYSE holiday list in `code/global-equity-etf/shared/trading_calendar.py`
  (2026-27) and the FOMC calendar in `code/global-equity-etf/fomc-global-beta/fomc_snapshot.csv`
  (through 2027-12). **Both must be extended before 2028.**

## Files

Spec `alphas/global-equity-etf/global-etf-sleeve-blend/alpha.md` with `equity_drawdown.png`. Code
`code/global-equity-etf/global-etf-sleeve-blend/`: `strategy.py`, `01_calibrate.py`,
`02_evaluate.py`, `03_figure.py`.
