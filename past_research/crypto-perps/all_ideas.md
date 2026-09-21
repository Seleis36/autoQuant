# All research ideas — Crypto perpetual futures (funding & basis) (`crypto-perps`)

One line per idea. Status is **Working** for a profitable idea, **Failed** otherwise.
Each line links to the full report in `<short-name>/`.

| Date | Idea | Status | Key result |
|---|---|---|---|
| 2026-09-18 | [Funding carry](funding-carry/2026-09-18_funding_carry.md) (`funding-carry`) — long spot / short USD-M perp on BTC and ETH, always on, exposure = min(1, 2 % / EWM-30d vol of the hedged P&L) re-set at funding stamps, perp leverage 1 with spot posted as collateral; 29 timing rules, 6 vol-target cells, 6 funding-scaling cells, 6 alts, cross-sectional top-n; IS 2020-22 / OOS 2023-26, 20 bp per switch both legs. Adds `data/bars/<SYM>_PERP/1h/` and `data/<SYM>_fundingRate.parquet` for 8 coins. | **Working** (vs "Sharpe ≥ 3", daily convention; monthly-horizon Sharpe 3.5) | Net Sharpe **10.2 daily / 5.7 weekly / 3.5 monthly / 2.5 quarterly**, IS 9.0 / OOS 12.7 daily, 3.6 / 3.5 monthly; CAGR **3.9 % on capital** (6.6 % always-on), vol 0.37 %, MaxDD −0.35 %, beta 0. It is a yield: all return is funding, the basis nets to zero. Not paper-tradeable here — neither book pays funding. Timing rules all lose to switching costs; BNB funding ≈ 0. |
