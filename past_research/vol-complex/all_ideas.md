# All research ideas — Equity volatility complex (`vol-complex`)

One line per idea. Status is **Working** for a profitable idea, **Failed** otherwise.
Each line links to the full report in `<short-name>/`.

| Date | Idea | Status | Key result |
|---|---|---|---|
| 2026-09-14 | [Term-structure carry](term-structure-carry/2026-09-14_term_structure_carry.md) — short VIXY (or long SVXY) conditioned on the VIX term structure (VIX3M/VIX, VIX9D, exact CBOE futures basis and Simon-Campasano daily roll), VRP, VVIX, VIX momentum, SPY trend, vol-scaling, SPY beta hedge, VIXY/VIXM front-vs-mid spread, FOMC/opex/VIX-expiry calendar legs, weekday, next-day reversal; ~140 variants, IS 2011-18 / OOS 2019-26. Adds `data/CBOE_VX_futures_d.parquet` (all VIX futures contracts 2013+). | **Failed** (vs Sharpe ≥ 1.5) | Best selection-free: short VIXY if VIX3M/VIX>1, net Sharpe **0.79 full / 0.88 IS / 0.70 OOS** @5bp, MaxDD −63%, bootstrap 5–95% [0.39, 1.17], P(Sh>1.5)=0.2%. Edge lives entirely in post-spike VIX 20–35 days; calm-market contango (VIX<16) earns ~0 after tails; beta-hedged carry is negative; calendar legs 1.10 full but 0.12 walk-forward (data-mined). |
