# Alpha spec — alt-sleeve-blend (crypto-alts)

**Status:** Working, the recommended crypto-alts deployment (upgrade of the live `xs-momentum-neutral` BAB book).
**Code:** `code/crypto-alts/alt-sleeve-blend/strategy.py`: `inputs = load_inputs(); w = blend_weights(inputs)`.
**Report:** `past_research/crypto-alts/alt-sleeve-blend/2026-09-28_alt_sleeve_blend.md`.

## Rule
Target weights (known at the daily close t, applied to t+1) =
`LEVERAGE × Σ_s RISK_WEIGHTS[s] × w_s`, with `LEVERAGE = 2.0` and constant risk weights fixed on 2018-22:

| Sleeve | Risk weight | Sleeve code (defaults as in each spec) |
|---|---|---|
| bab: regime-hedged betting-against-beta, top-20 alts | 0.2226 | `code/crypto-alts/xs-momentum-neutral/strategy.py::alt_bab_weights` |
| dilution: short 12-week CMC circulating-supply growth, BTC-β-hedged, 30d tranches | 0.2921 | `code/crypto-alts/token-dilution/strategy.py::dilution_weights` |
| volume: short abnormal volume (k × base ensemble), BTC-β-hedged, 30d tranches | 0.2461 | `code/crypto-alts/volume-attention/strategy.py::volume_attention_weights` |
| funding: short high / long low Binance perp funding (14-90d), β-neutral, 7d tranches | 0.2392 | `code/crypto-perps/funding-xs-crowding/strategy.py::target_weights` |

Each sleeve is a dollar-neutral (or β-neutral) long/short book of gross ≈ 1 on the liquid-alt
cross-section, plus a BTC hedge leg where specified. Positions in the same coin from different
sleeves are netted.

## Trading
* Instruments: yfinance `<COIN>-USD` spot alts in each sleeve's point-in-time top-20 universe (long
  and short), plus `BTC-USD` (hedge legs; also a funding-sleeve name) and `ETH-USD` (funding sleeve only, |w| ≤ 0.05).
  58 instruments traded over the backtest, all priced from the shared daily cache.
* Direction: long/short, market-neutral on average (net dollar exposure +0.11, β to BTC −0.02).
* **Max leverage: gross 2.0** (average 1.08). This is the validated range at `LEVERAGE = 2.0`.
* Rebalance: daily at the 00:00 UTC close (yfinance bar stamped D closes at D+1 00:00 UTC); turnover 14×/yr.
* Sizing: fixed risk weights × sleeve weights × leverage. No vol targeting (it hurt BAB in the original study).
* Cost assumed: 10 bp per side on the netted turnover.

## Headline (net 10 bp, L = 2.0)
| | Sharpe | CAGR | Vol | MaxDD |
|---|---|---|---|---|
| Full 2018-03-08 → 2026-09-27 | **1.39** | 34.3 % | 23.1 % | −24.0 % |
| IS 2018-22 | 1.47 | 33.2 % | 21.5 % | −22.9 % |
| OOS 2023-26 | **1.31** | 33.8 % | 24.6 % | −24.0 % |

Live BAB alone, same period: 1.22 / 1.35 / 1.06, MaxDD −30 %. Pooled BTC-bear Sharpe 1.59 (BAB 1.49).
30 bp cost → 1.27 / 1.18 OOS. 10 %/yr short carry → 1.18 / 1.09 OOS. Bootstrap 5-95 % [0.82, 2.01].

## Live data dependencies (all daily unless noted)
1. yfinance daily cache for the alt candidate list + BTC-USD (already refreshed by the live runners).
2. **Weekly** CoinMarketCap snapshots: `python code/crypto-alts/shared/cmc.py` (incremental), or
   `load_inputs(refresh_cmc=True)`. Keyless but unofficial endpoint. If it goes stale, the dilution
   sleeve drops names after 10 days of forward-fill and goes flat.
3. Binance USD-M funding history `data/<SYM>USDT_fundingRate.parquet`, refreshed by
   `code/crypto-perps/shared/funding_panel.py` (`fetch_funding_rest`). The funding sleeve is not
   deployed elsewhere, so nothing refreshes these files today. The runner must, or the funding sleeve
   goes stale. Settlements are used with an 8h safety lag (`daily_funding(lag_hours=8)`).

## Known weaknesses
Semi-out-of-sample provenance of the sleeve set. Walk-forward inclusion from 2021 gives 0.71 on
2021-26 but 1.30 on 2023-26. 2026 YTD is −0.79, with every sleeve negative. Short-leg carry is unmodelled.

Figures: `01_equity.png`, `02_drawdown.png`, `03_rolling_sharpe.png`, `04_yearly.png`, `05_exposure.png`.
