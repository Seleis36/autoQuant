# Alpha spec — `weekday-trend`

Revised 2026-09-09: `cap` reduced from 1.5 → 1.0 to keep the strategy inside long/flat
unlevered constraints for the spot testnet. All numbers below are recomputed under the new
cap. See §7 "Revision" of the report for before/after.

## Instrument & mechanics

| Field | Value |
|---|---|
| Instrument | spot BTC/USD (Coinbase, Binance, Bitstamp — all equivalent) |
| Direction | long / flat (no short) |
| Weight range | [0.0, 1.0] |
| Rebalance | once daily, at the 00:00 UTC daily close boundary |
| Bar convention | UTC daily closes, index timezone-naive |
| Cost assumed | 10 bp/side (round-trip 20 bp) |

## Signal (long/flat, lookahead-safe)

```
trend_t      = 1 if close_t > SMA_200(close)_t else 0
momentum_t   = 1 if close_t / close_{t-20} - 1 > 0 else 0
ewv_t        = EWMA halflife=20 of daily returns, annualised √365
vol_scalar_t = clip(0.40 / ewv_t, 0, 1.0)
skip_thu_t   = 0 if (t+1).dayofweek == 3 else 1        # 3 = Thursday

target_weight_t = trend_t * momentum_t * vol_scalar_t * skip_thu_t
```

`target_weight_t` is set at close of day `t` and is the weight held from close `t` to close `t+1`.

## Reference performance (10 bp/side, cap=1.0)

| Window | Sharpe | CAGR | MaxDD | AvgExpo | Turnover/yr |
|---|---|---|---|---|---|
| Full 2015-01 → 2026-09 (yfinance BTC-USD) | 1.60 | 42.6 % | −25.1 % | 24.1 % | 40.6 |
| IS 2015 → 2021 | 1.88 | 58.2 % | −25.1 % | | |
| OOS 2022 → 2026-09 | 1.18 | 25.2 % | −20.2 % | | |
| Strict walk-forward (train 3 y, step 1 y) | 1.15 | 23.6 % | | | |
| Bitstamp cross-check (2019-11 → 2026-09) | 1.29 full / 1.16 OOS | | | | |

## Deployment interface

```python
from code.spot_btc.weekday_trend.strategy import target_weight

# `close` = pd.Series of BTC daily closes with a DatetimeIndex (tz-naive, UTC daily).
w = target_weight(close)
# w[t] is the target weight to hold from close_t to close_{t+1}. Values in [0.0, 1.0].
```

All parameters default to the values above. No secondary data source is required.
