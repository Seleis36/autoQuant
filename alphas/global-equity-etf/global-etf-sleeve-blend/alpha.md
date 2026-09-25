# Alpha spec — `global-etf-sleeve-blend` (global-equity-etf)

**Status:** Working. **Recommended deployment** (supersedes standalone `intl-relative-trend`; deploy one, not both).
**Report:** `past_research/global-equity-etf/global-etf-sleeve-blend/2026-09-26_global_etf_sleeve_blend.md`
**Signal code:** `code/global-equity-etf/global-etf-sleeve-blend/strategy.py` → `target_weights(close)`.
It imports `../intl-relative-trend/strategy.py`, `../fomc-global-beta/strategy.py` and
`../shared/trading_calendar.py` by path, so keep the folder layout.

## Instruments
`EWJ EWG EWU EWZ EWY EWA EWC FXI INDA SPY`: daily auto-adjusted closes (yfinance) on the SPY
calendar, with not-yet-listed names as NaN. The `close` passed in must contain all 10 columns.

## Direction, sizing, leverage
* Long/short. Weights = 0.67 × intl-relative-trend weights (market-neutral country spreads vs
  SPY, 10 % vol sleeve) + 0.87 × FOMC weights (long the equal-weight available country basket
  only on the 2 sessions whose returns are FOMC day −1 and day 0).
* Gross: average 1.41×, 99th pct 2.31×, **max 3.00× observed. Cap gross at 3.1×.**
* Realised vol 9.1 %. Correlation to SPY 0.10.

## Timing / rebalance
* All signals are computed at the 16:00 ET close of day t and filled at that close; the
  backtest applies them to day t+1.
* Trend sleeve: rebalanced on the **last NYSE session of each month**, held otherwise.
* FOMC sleeve: on at the closes of FOMC day −2 and day −1, off at the close of day 0.
  Scheduled meetings only, from `fomc-global-beta/fomc_snapshot.csv`.
* Between events and month-ends the weights are constant fractions of equity.

## Costs assumed
5 bp per side on country ETFs, 1 bp per side on SPY. Turnover 19× gross per year.
Net Sharpe 0.72 at 10 bp, 0.87 at 2 bp.

## Headline (net, 2001-07 → 2026-09)
| | Full | IS 2001-12 | OOS 2013-26 |
|---|---:|---:|---:|
| Sharpe | 0.81 | 0.77 | 0.86 |
| CAGR | 7.2 % | 7.5 % | 6.9 % |
| Max DD | −21.0 % | −21.0 % | −13.1 % |

## Maintenance
Extend `code/global-equity-etf/shared/trading_calendar.py:NYSE_HOLIDAYS` (currently 2026-27) and
`fomc_snapshot.csv` (currently through 2027-12-08) each year. Without them, a month-end or FOMC
window that falls next to a holiday is mis-timed.
