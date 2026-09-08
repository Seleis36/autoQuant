# All research ideas — Spot Ethereum (`spot-eth`)

One line per idea. Status is **Working** for a profitable idea, **Failed** otherwise.
Each line links to the full report in `<short-name>/`.

| Date | Idea | Status | Key result |
|---|---|---|---|
| 2026-09-07 | [ETH trend filter](eth-trend-filter/2026-09-07_eth_trend_filter.md) — long spot ETH when close > SMA(40), sized by inverse-vol scalar (target 0.5, capped 1.0). ETH/BTC ratio explored as a gate/tilt and dropped. | **Working** | Sharpe **1.16 full / 1.12 OOS / 1.19 walk-fwd** @10bp; CAGR 42.7%, MaxDD −45.6%, Calmar 0.94, t_NW 2.99; bootstrap P(Sh>1)=64% |
| 2026-09-07 | ETH/BTC ratio SMA-crossover as long-only signal on ETH — *within the above report* | Failed | Best Sharpe 0.51, worse than ETH buy-and-hold (0.70) |
| 2026-09-07 | ETH-trend × ratio-trend AND-gate — *within the above report* | Failed | Ratio gate cuts too many good ETH periods; Sharpe drops to 0.40–0.49 |
| 2026-09-07 | ETH-trend × BTC-trend AND-gate — *within the above report* | Failed OOS | Full 1.38 IS 1.54 but OOS 0.95, MDD little improved |
| 2026-09-07 | Multi-window trend ensemble — *within the above report* | Failed | Full 0.87–0.90, OOS 0.48–0.64; noise dominates |
