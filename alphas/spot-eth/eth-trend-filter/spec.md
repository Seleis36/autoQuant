# Alpha spec — `spot-eth / eth-trend-filter`

**Status:** Working. Full-sample Sharpe 1.16 (OOS 1.12) net of 10 bp/side.

## Universe & bar

Spot ETH/USD, daily bars, close-based. Data from yfinance `ETH-USD` (or any equivalent spot venue such as Coinbase/Kraken/Binance `ETHUSDT` daily close).

## Signal

At the close of each day t:

```
trend_t   = 1{ close_t > SMA(close, 40)_t }
vol_t     = EWMstd(pct_change(close), halflife=20)_t * sqrt(365)     # annualised
scalar_t  = clip( 0.5 / vol_t , 0.0, 1.0 )
w_t       = trend_t * scalar_t                                        # target weight
```

**Weight is applied to the return of day t+1** (i.e. rebalance is executed on the close print of day t, effective from t+1 open onward).

- No leverage: hard cap at w = 1.0.
- No shorting: hard floor at w = 0.0.
- No overnight leverage risk (spot only).

## Costs and turnover

Modeled at 10 bp per side on |w_t − w_{t−1}|. Annual turnover ≈ 17. Real-world spot-ETH costs on the majors are 5-15 bp per side; the strategy stays >1.0 OOS Sharpe up to 20 bp.

## Reference metrics (2017-11-09 → 2026-09-06, N=3224)

| | Sharpe | Sortino | CAGR | Vol | MaxDD | Calmar | HitRate | t_NW | Turnover/y | AvgExposure |
|---|---|---|---|---|---|---|---|---|---|---|
| Full sample | 1.16 | 1.32 | 42.7% | 36.9% | −45.6% | 0.94 | 55.5% | 2.99 | 16.9 | 34.1% |
| IS (≤ 2023-12-31) | 1.18 | — | 44.4% | — | −45.6% | — | — | — | — | — |
| OOS (≥ 2024-01-01) | 1.12 | — | 39.0% | — | −40.8% | — | — | — | — | — |
| Buy-and-hold ETH | 0.70 | — | 26.2% | 84.5% | −94.0% | 0.28 | 51.9% | — | — | 100% |

Block bootstrap (30-day blocks, 2000 draws): mean 1.13, 90% CI [0.55, 1.71], P(Sh > 1) = 64.4%.

## Assumed execution

- One decision per day at settlement (23:59 UTC close print).
- Marketable-limit or IOC on spot ETH/USD; slippage budget 5 bp on top of taker fee.
- Position sizing = notional × w_t. No margin, no borrow.

## Kill switch (recommended)

If the trailing 90-day realised Sharpe drops below −0.5, halve exposure until it recovers above 0. This is a portfolio-risk guardrail, not part of the alpha per se.

## Files

- `../../past_research/spot-eth/eth-trend-filter/2026-09-07_eth_trend_filter.md` — full research report.
- `../../code/spot-eth/eth-trend-filter/` — reproduction scripts (01–06).
- `01_equity.png`, `02_drawdown.png`, `03_rolling_sharpe.png`, `04_weight.png` — charts.
- `backtest_series.parquet` — day-by-day price, weight, and per-strategy returns.
