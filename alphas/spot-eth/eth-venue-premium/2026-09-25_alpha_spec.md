# Alpha spec — `eth-venue-premium` (spot-eth)

**Status:** Working. This is a pre-registered replication of `spot-btc/coinbase-premium` on ETH with parameters unchanged.
**Report:** `past_research/spot-eth/eth-venue-premium/2026-09-25_eth_venue_premium.md`
**Code:** `code/spot-eth/eth-venue-premium/strategy.py :: target_weight(binance_close, coinbase_close)`

## Instrument and book

| Item | Value |
|---|---|
| Traded instrument | **ETHUSDT spot on Binance** (Binance spot testnet) |
| Direction | **long / flat** (weight ∈ [0, 1]) |
| Max leverage | **1.0** (no leverage, no shorts) |
| Rebalance | **hourly**, at each closed 1h bar (UTC). Trade when the target changes |
| Bar / timezone | 1h bars stamped at bar **open**, UTC, tz-naive. Weight computed from closes ≤ bar t, held over bar t+1 |
| Signal inputs | Binance ETHUSDT 1h closes (traded series) and **Coinbase Exchange ETH-USD 1h closes** (public `GET /products/ETH-USD/candles?granularity=3600`, no key) |
| History needed | ≥ 1200 hourly bars (50 days) for the trend SMA; ≥ 720 premium bars for the z-score; ≥ 480 bars for the vol estimator. Fetch **≥ 1500 bars** of both series |
| Cost assumption | 10 bp per side (testnet taker) |

## Rule (every parameter is a default in `strategy.py`)

```
prem_t  = Coinbase_ETHUSD_close_t / Binance_ETHUSDT_close_t − 1          (bars present on both venues)
z_t     = (prem_t − mean(prem, 720 bars)) / std(prem, 720 bars)
state_t = hysteresis: goes to 1 when z_t > 0.0; goes to 0 when z_t < −1.5; otherwise unchanged
          (a missing Coinbase bar leaves the state unchanged)
trend_t = 1{ Binance_close_t > SMA(Binance_close, 1200 bars) }            (50-day SMA on hourly bars)
vol_t   = EWM std of hourly Binance returns, halflife 480 bars, × √8760
w_t     = state_t × trend_t × min(0.40 / vol_t, 1.0)
```

`w_t` is the target fraction of the sleeve's capital to hold in ETH from the close of bar t to the close of bar t+1.

## Expected behaviour (backtest 2017-08 → 2026-09-24, 10 bp/side, Sharpe on daily-compounded returns)

| Metric | Full | IS (≤ 2023) | OOS (2024 →) |
|---|---|---|---|
| Sharpe | **1.38** | 1.33 | **1.49** |
| CAGR | 38.9% | — | — |
| Max drawdown | −29.2% | — | — |
| Vol (ann.) | 26.4% | — | — |
| Sortino / Calmar | 1.78 / 1.33 | — | — |
| Newey-West t | 3.48 | — | — |
| Walk-forward (2y train, 90d apply, 144-cell grid) | 1.34 | 1.37 | 1.29 |
| Annual turnover (Σ\|Δw\|) | 76 | | |
| Average exposure / time in market | 0.23 / 40% | | |

Cost sensitivity (full / OOS): 0 bp 1.67 / 1.75 · 5 bp 1.52 / 1.62 · **10 bp 1.38 / 1.49** · 20 bp 1.08 / 1.23 · 30 bp 0.79 / 0.97.

Correlation of daily returns: 0.85 with the live `spot-eth/eth-trend-filter`, 0.60 with the live `spot-btc/coinbase-premium`. **It is an upgrade to the ETH trend sleeve, not an independent edge.** Running both books doubles the same ETH exposure.

## Operational notes

- Coinbase candles omit hours with no trades. Compute the premium on the intersection of stamps; a missing hour must **keep** the previous state, not reset it (`strategy.py` does this).
- Use closed bars only on both venues. A forming Coinbase candle would leak a partial premium into the z-score.
- The signal decays fast. An extra 1 h delay costs ~0.15 of full-sample Sharpe (OOS is unaffected: 1.55), and 3 h costs ~0.3. Trade at the next bar open, as the BTC sleeve does.
- Same USDT-premium mechanism as the BTC sleeve: the ETH and BTC premium states agree 91% of the time. If the harness already polls Coinbase BTC-USD for the BTC sleeve, the only new input is the ETH-USD product.

## Figures

- `equity.png` — equity (log) against the live trend filter and buy-and-hold, with drawdown
- `equity.csv` — daily equity of all three series
