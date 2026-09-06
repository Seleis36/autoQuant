# All research ideas — Spot Bitcoin (`spot-btc`)

| Date | Idea | Status | Key result |
|---|---|---|---|
| 2026-09-06 | [BTC US-Close Liquidity Timer](bult/2026-09-06_btc_us_close_liquidity_timer.md) — daily credit/dollar liquidity regime as the base, plus a gated dip-buy overlay in the 20:00–23:00 UTC US-close / ETF-NAV window | **Working** | Sharpe **1.48** full / **1.20 OOS** / **1.41 walk-forward** @3bp; CAGR 32.4%, MaxDD −25.3%, beta 0.18, alpha 20.1%; replicates on 4 venues + ETH |
| 2026-09-06 | SMA crossover long/flat (68-point grid) — *within the above report* | Failed | 0 of 68 cells reach OOS Sharpe > 1; IS→OOS rank corr −0.17 |
| 2026-09-06 | Time-series momentum, k = 5–250 days — *within the above report* | Failed | Best OOS 0.98 but unselectable in-sample; same negative IS/OOS relationship |
| 2026-09-06 | 52-week-high proximity (George & Hwang anchoring) — *within the above report* | Failed | Max OOS Sharpe 0.94, median 0.58, IS→OOS spearman −0.27 |
| 2026-09-06 | Inverse-vol targeting standalone — *within the above report* | Failed alone | BTC's vol/return relation is U-shaped, not monotone; works only as an overlay |
