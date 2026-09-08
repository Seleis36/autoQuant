# All research ideas — Spot Bitcoin (`spot-btc`)

| Date | Idea | Status | Key result |
|---|---|---|---|
| 2026-09-06 | [BTC US-Close Liquidity Timer](bult/2026-09-06_btc_us_close_liquidity_timer.md) — daily credit/dollar liquidity regime as the base, plus a gated dip-buy overlay in the 20:00–23:00 UTC US-close / ETF-NAV window | **Working** | Sharpe **1.48** full / **1.20 OOS** / **1.41 walk-forward** @3bp; CAGR 32.4%, MaxDD −25.3%, beta 0.18, alpha 20.1%; replicates on 4 venues + ETH |
| 2026-09-06 | SMA crossover long/flat (68-point grid) — *within the above report* | Failed | 0 of 68 cells reach OOS Sharpe > 1; IS→OOS rank corr −0.17 |
| 2026-09-06 | Time-series momentum, k = 5–250 days — *within the above report* | Failed | Best OOS 0.98 but unselectable in-sample; same negative IS/OOS relationship |
| 2026-09-06 | 52-week-high proximity (George & Hwang anchoring) — *within the above report* | Failed | Max OOS Sharpe 0.94, median 0.58, IS→OOS spearman −0.27 |
| 2026-09-06 | Inverse-vol targeting standalone — *within the above report* | Failed alone | BTC's vol/return relation is U-shaped, not monotone; works only as an overlay |
| 2026-09-08 | [Weekday trend](weekday-trend/2026-09-08_weekday_trend.md) — long/flat BTC when close>SMA(200) AND ret_20>0, sized by inverse-EWMA-vol (target 40% ann, cap 1.5×), flat every Thursday | **Working** | Sharpe **1.63 full / 1.93 IS / 1.15 OOS / 1.21 walk-forward** @10bp; CAGR 45%, MaxDD −25%; bootstrap P(Sh>1)=98%; replicates on Bitstamp OOS 1.14 |
| 2026-09-08 | Dip-in-uptrend standalone (dip depth × trend × hold sweep) — *within the above report* | Failed | Best OOS Sharpe 1.19 but full-sample never above 0.72 due to 3–7% time-in-market |
| 2026-09-08 | Pure Moreira-Muir 1/rv² vol-managed BTC — *within the above report* | Failed | Full ~1.06, OOS **0.53** — no directional edge post-2022 without a trend gate |
| 2026-09-08 | Single-hour hourly holds (best UTC hour = 22 UTC) — *within the above report* | Failed | Per-hour drift positive both halves but 2×3bp × 24 turnovers/day → net negative Sharpe |
