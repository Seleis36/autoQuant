# Alpha spec — `intl-relative-trend` (global-equity-etf)

**Status:** Working (modest). Market-neutral diversifier.
**Report:** `past_research/global-equity-etf/intl-relative-trend/2026-09-26_intl_relative_trend.md`
**Signal code:** `code/global-equity-etf/intl-relative-trend/strategy.py` → `target_weights(close)`

## Instruments
Long/short: `EWJ EWG EWU EWZ EWY EWA EWC FXI INDA` (iShares country ETFs) and `SPY` as the hedge
leg. Daily auto-adjusted closes (yfinance), on the SPY trading calendar. Not-yet-listed names
are NaN.

## Direction, sizing, leverage
* Long/short. Each country is long or short its SPY-beta-hedged spread, depending on the slow
  trend of that spread.
* Sizing: position = trend signal / spread vol. Two sleeves (AGG: EW ex-US spread; DIV:
  per-country spreads), each scaled to 10 % ex-ante vol, blended 50/50, and re-scaled to 10 %.
* **Gross leverage: average 2.1×, 99th pct 3.3×, max 3.53× observed. Cap gross at 3.6×.**
  Net dollar exposure varies (SPY leg ≈ −Σ country·β).
* Target volatility 10 % annualised (realised 11.2 %).

## Timing
* Signal computed at the US close (16:00 ET) of the **last trading day of each month**. Fill at
  that same close. Weights are held until the next month-end.
* The backtest applies weights from the next bar (shift 1). `target_weights` returns daily rows,
  constant between month-ends.

## Parameters (defaults in `strategy.py`)
`LOOKBACKS = (126, 252, 504)`, `BETA_WIN = 252`, `VOL_WIN = 126`, `COV_WIN = 126`,
`TARGET_VOL = 0.10`, `blend = 0.5`, `SCALAR_CAP = 3.0`.
Warm-up is about 504 + 252 bars of history per name before its first position. INDA (listed
2012-02) enters in 2014.

## Costs assumed
5 bp per side on the country ETFs, 1 bp per side on SPY. Turnover 7.9× gross per year.
At 10 bp / 2 bp the Sharpe is 0.61.

## Headline numbers (net, 2001-07 → 2026-09)
| | Full | IS 2001-12 | OOS 2013-26 |
|---|---:|---:|---:|
| Sharpe | 0.64 | 0.60 | 0.67 |
| CAGR | 6.7 % | 6.0 % | 7.3 % |
| Max DD | −24.5 % | −24.5 % | −19.6 % |
Correlation to SPY −0.06 daily. Independent 1980-2000 backcast on local indices × FX: Sharpe 0.52.

## Figures
`equity_drawdown.png` (ETF era: equity, drawdown, rolling 3y Sharpe) and
`long_history_backcast.png` (1977-2026 index backcast).
