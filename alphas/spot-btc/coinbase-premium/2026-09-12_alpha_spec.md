# Alpha spec — `coinbase-premium` (candidate; did NOT meet the session's Sharpe ≥ 2.0 criterion)

> Status: **Failed against acceptance criterion** (best 1.48 vs 2.0 required). This spec is kept so the
> signal can be reused if a future brief has a lower bar. Report: `past_research/spot-btc/coinbase-premium/2026-09-12_coinbase_premium.md`.

## Instrument & mechanics

| Field | Value |
|---|---|
| Instrument | spot BTC/USDT on Binance (the traded leg is Binance because the signal is Binance-vs-USD-venue) |
| Direction | long / flat, no short |
| Weight range | [0.0, 1.0], no leverage |
| Bars | hourly, UTC, index = bar open time, tz-naive |
| Rebalance | every hour at the bar close (weight at t is known at t+1h and held over bar t+1); in practice the state changes ~90 times/yr |
| Secondary data | Coinbase Exchange BTC-USD hourly closes (public REST, no key) |
| Cost assumed | 10 bp/side |

## Signal

```
prem_t   = coinbase_close_t / binance_close_t − 1
z_t      = (prem_t − mean_720(prem)) / std_720(prem)            # 30-day trailing, hourly bars
state_t  = 1 once z_t > 0.0, until z_t < −1.5, then 0 (hysteresis; NaN keeps state)
trend_t  = 1{ binance_close_t > SMA_1200(binance_close) }        # 50 days
ewv_t    = EWMA(halflife 480 bars) std of hourly returns × √8760
scale_t  = clip(0.40 / ewv_t, 0, 1.0)
w_t      = state_t × trend_t × scale_t
```

## Reference performance (10 bp/side, Binance BTCUSDT hourly 2017-08 → 2026-09)

| Window | Sharpe | CAGR | MaxDD | AvgExpo | Side-trades/yr |
|---|---|---|---|---|---|
| Full | 1.48 | 39.9 % | −33.1 % | 29 % | 88 |
| IS ≤ 2022-12 | 1.48 | | | | |
| OOS 2023-01 → 2026-09 | 1.48 | | | | |
| Walk-forward 2020–26 (36 candidates, expanding) | 1.37 | 36 % | −33 % | | |
| Bootstrap 5–95 % | [0.84, 2.02] | | | | |

## Deployment interface

```python
from strategy import target_weight   # code/spot-btc/coinbase-premium/strategy.py
w = target_weight(binance_close_1h, coinbase_close_1h)   # both pd.Series, hourly, index = bar open (UTC)
# w[t] is the weight to hold from close_t to close_{t+1}; values in [0, 1].
```
All parameters default to the values above. Requires ≥ 1200 hourly bars of history to warm up.
