# Alpha spec — perp-crowding (spot-btc)

**Status:** Working
**Report:** `past_research/spot-btc/perp-crowding/2026-09-28_perp_crowding.md`
**Code:** `code/spot-btc/perp-crowding/strategy.py` → `target_weight(close, ls_ratio)`, every default = this spec

## Instrument and direction
- **Traded:** spot BTC/USDT on Binance. Long/flat, **max weight 1.0 (no leverage)**, never short.
- Deployable on the Binance spot testnet as-is. On a SimBroker it can use `binance-public` quotes.

## Signal
- **Input:** Binance USD-M BTCUSDT **global long/short account ratio**, 5-minute series.
  - History: data.binance.vision `metrics` column `count_long_short_ratio`, cached in `data/BTCUSDT_metrics_5m.parquet` (refresh: `code/spot-btc/perp-crowding/fetch_metrics.py`).
  - Live: `GET https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m`, field `longShortRatio`. REST keeps 30 days only.
  - **REST timestamps are 5 minutes later than archive `create_time`.** Subtract 5 min from REST stamps before appending them to the archive series.
- **Crowd level for daily bar D:** `log(ratio)` from the last snapshot stamped strictly before D+1 00:00 UTC − 1 h (22:55 archive stamp).
- **Rank:** percentile of that level among **all prior daily levels since 2020-09-01** (expanding, min 180 days; flat before).
- **State:** hold BTC while `rank < 0.5`, i.e. the crowd is less long than its historical median.

## Sizing and rebalance
- `w = state × clip(0.40 / σ, 0, 1)`, where σ = EWMA std of daily close-to-close returns (half-life 20 days) × √365.
- **Rebalance daily at 00:00 UTC**, on the close of the Binance daily bar. The weight decided at D+1 00:00 is held until D+2 00:00.
- **Execution must be same-bar.** A one-day delay cuts Sharpe from 1.24 to about 1.05.

## Headline numbers (10 bp/side, 2021-03-01 → 2026-09-24)

| | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| Full | **1.25** | 37.6% | −30.2% |
| IS (2021-03 → 2022) | 0.61 | | |
| **OOS (2023 → 2026-09)** | **1.53** | | |
| Walk-forward over the 16-member family (2022–26) | 1.09 | | |

- Vol 29%, Sortino 1.64.
- Turnover 41×/yr (≈ 52 state flips a year, average spell 7.7 days); average exposure 0.43.
- Cost sensitivity: 0 bp 1.39, 5 bp 1.32, 20 bp 1.10, 30 bp 0.96.
- Benchmarks, same window (full / IS / OOS):
  - vol-scaled buy-and-hold 0.52 / −0.67 / 1.11;
  - SMA50 × vol 0.94 / −0.57 / 1.52.

## Variants
- **P2:** `target_weight(..., trend_sma=50)`, the same sleeve with an SMA50 trend gate: 1.29 / −0.15 / 1.77, MaxDD −28%.
- **P3:** an overlay for the live `coinbase-premium` sleeve, multiplying its weight by this sleeve's state (from the previous 00:00): 1.37 / −0.10 / 1.84 vs 0.99 / −0.45 / 1.53, MaxDD −27% vs −33%.

## Risks
- Out-of-sample it ties a plain trend filter; the edge over trend was earned in 2021–22.
- The history is only 5.5 years.
- The ratio's definition belongs to Binance.
- 2025 was −0.47.

## Figure
`equity.png`: growth of 1 for P1, P2, SMA50 × vol and vol-scaled B&H, with the crowd rank underneath. Data in `equity.csv`.
