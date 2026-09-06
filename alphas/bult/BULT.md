# Alpha: BULT — BTC US-Close Liquidity Timer

**Universe:** spot BTC/USD · **Direction:** long/flat · **Leverage:** none (weight capped at 1.0)
**Rebalance:** hourly · **Turnover:** ~55 round-trips/year · **Assumed cost:** 3 bp/side (maker)

## Signal

```python
# ---- DAILY layer, all inputs lagged 1 day + 1 hour ----------------------------
trend  = mean_{n in 20,50,100,150,200}      [ 1{ P_close > SMA_n(P_close) } ]
macro  = mean over 4 series x 5 lookbacks {50,100,150,200,250} of the risk-on flag:
             HYG      > SMA_n(HYG)        # credit risk appetite
             LQD      > SMA_n(LQD)        # IG credit / financial conditions
             DX-Y.NYB < SMA_n(DXY)        # dollar, INVERTED
             ^GSPC    > SMA_n(SPX)        # equity risk appetite
base   = (trend * macro) * clip( 0.35 / EWMA_vol_20(daily returns), 0, 1 )

# ---- INTRADAY layer, known exactly at 20:00 UTC --------------------------------
pre    = cumulative BTC return from 00:00 UTC to 20:00 UTC (same day)
gate   = 1 if (UTC hour in {20, 21, 22}) and (pre < -0.010) else 0

weight = clip( base + 0.5 * gate, 0, 1 )
```

## Economic rationale

* **Base** — BTC is a long-duration liquidity asset. Credit spreads (HYG, LQD) and the dollar
  describe the liquidity regime it levers. This information is *not* in BTC's price: the macro
  composite correlates only 0.37 with BTC's own trend signal.
* **Overlay** — BTC's whole drift accrues in the 3 hours around the US equity close / spot-ETF 4pm-ET
  NAV strike (Sharpe 1.60 there vs 0.34 for the other 21 hours; 1.98 vs 0.03 post-ETF). The edge
  concentrates on days BTC sold off beforehand: scheduled, price-insensitive US demand absorbing
  overnight supply. The gate is what makes it survive transaction costs.

## Performance (2017-08 → 2026-09, Binance hourly, 3 bp/side)

| | CAGR | Vol | Sharpe | Sortino | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| BULT | 32.4% | 20.4% | **1.48** | 1.50 | −25.3% | 1.28 |
| Buy & hold | 38.1% | 71.8% | 0.81 | 0.98 | −83.9% | 0.45 |

In-sample 2017–21 **1.74** · out-of-sample 2022–26 **1.20** · ETF era 2024+ **1.25** ·
strict walk-forward **1.41**. Beta to BTC 0.18, annualised alpha 20.1%, avg exposure 26%.
Newey-West t = 3.66. Bootstrap 5–95% CI on Sharpe **[0.90, 2.13]**.

## Robustness

* vectorbt reproduces the engine to 1.8e-4 per bar (Sharpe 1.4717 vs 1.4777).
* Full strategy on **Bitstamp** data: Sharpe 1.486 vs Binance 1.483.
* Window effect replicates on Binance / Binance.US / Bitstamp / yfinance **and on ETH**.
* Parameter surface is a plateau: all 24 (threshold × size) cells give OOS Sharpe 0.94–1.22.
* Costs: 0bp → 1.64 · 3bp → 1.48 · 5bp → 1.37 · 10bp → 1.10.
* Placebo tests: randomised gate days p=0.015; mirrored gate (buy strength) only 1.21; shuffled-return control 4.1 sd below.

## Operational notes

* Execute at the hour boundary. One hour of delay costs ~0.34 Sharpe (1.48 → 1.14); two hours → 0.82.
* Macro series are weekday-only; forward-fill onto the 7-day crypto calendar. Stale weekend values
  are intended and realistic.
* **Health check:** monitor the rolling 20:00–23:00 UTC window Sharpe. The overlay's premise is a
  structural US-flow imbalance; if that Sharpe decays toward the rest-of-day level, cut `b` to 0 and
  fall back to the base (Sharpe ~1.33, ~6 round-trips/year).

## Code

`code/bult/strategy.py` — `build_signals()`, `backtest_hourly()`, `stats()`.
Research trail: `past_research/bult/2026-09-06_btc_us_close_liquidity_timer.md`.
