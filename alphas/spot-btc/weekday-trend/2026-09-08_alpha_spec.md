# Alpha spec — `weekday-trend`

## Instrument & mechanics

| Field | Value |
|---|---|
| Instrument | spot BTC/USD (Coinbase, Binance, Bitstamp — all equivalent) |
| Direction | long / flat (no short) |
| Weight range | [0.0, 1.5] |
| Rebalance | once daily, at the 00:00 UTC daily close boundary |
| Bar convention | UTC daily closes, index timezone-naive |
| Cost assumed | 10 bp/side (round-trip 20 bp) |

## Signal (long/flat, lookahead-safe)

```
trend_t      = 1 if close_t > SMA_200(close)_t else 0
momentum_t   = 1 if close_t / close_{t-20} - 1 > 0 else 0
ewv_t        = EWMA halflife=20 of daily returns, annualised √365
vol_scalar_t = clip(0.40 / ewv_t, 0, 1.5)
skip_thu_t   = 0 if (t+1).dayofweek == 3 else 1        # 3 = Thursday

target_weight_t = trend_t * momentum_t * vol_scalar_t * skip_thu_t
```

`target_weight_t` is set at close of day `t` and is the weight held from close `t` to close `t+1`.

## Reference performance (10 bp/side)

| Window | Sharpe | CAGR | MaxDD | AvgExpo | Turnover/yr |
|---|---|---|---|---|---|
| Full 2015-01 → 2026-09 (yfinance BTC-USD) | 1.63 | 45.4 % | −25.1 % | 25.3 % | 43 |
| IS 2015 → 2021 | 1.93 | 63.1 % | −25.1 % | | |
| OOS 2022 → 2026-09 | 1.15 | 25.5 % | −20.2 % | | |
| Strict walk-forward (train 3 y, step 1 y) | 1.21 | 24.0 % | | | |
| Bitstamp cross-check (2019-11 → 2026-09) | 1.28 full / 1.14 OOS | | | | |

## Deployment interface

```python
from code.spot_btc.weekday_trend.strategy import target_weight

# `close` = pd.Series of BTC daily closes with a DatetimeIndex (tz-naive, UTC daily).
w = target_weight(close)
# w[t] is the target weight to hold from close_t to close_{t+1}.
```

All parameters default to the values above. No secondary data source is required.
