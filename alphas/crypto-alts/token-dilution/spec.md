# Alpha spec — token-dilution (crypto-alts)

**Status:** Working (modest). Deploy preferably as a sleeve of `alt-sleeve-blend`, not alone.
**Code:** `code/crypto-alts/token-dilution/strategy.py::dilution_weights` (+ `load_inputs`).
**Report:** `past_research/crypto-alts/token-dilution/2026-09-28_token_dilution.md`.

## Rule
1. Universe (daily, past data only): the 20 alts with the highest trailing 90-day median yfinance USD
   volume among names with ≥ 120 closes and median volume ≥ $5M (candidate list
   `code/crypto-alts/shared/universe.py::ALTS`), restricted to names with a CMC circulating supply.
2. Signal: `-log(circ_supply[t] / circ_supply[t-84d])`, clipped to [−1, 2], where `circ_supply` is the
   CoinMarketCap weekly snapshot value re-stamped to snapshot date + 1 day and forward-filled.
3. Weights: cross-sectional percentile rank, demeaned, scaled so sum|w_alts| = 1 (dollar-neutral:
   long the least-diluting, short the most-diluting). Add `BTC-USD` = −Σ w_i·β_i with β the EWM
   (halflife 60) beta of daily returns to BTC.
4. Hold: average the daily target over the last 30 days (overlapping tranches).

## Trading
* Instruments: the yfinance `<COIN>-USD` alts in the universe (long and short) plus `BTC-USD`.
* Direction: long/short, market-neutral (β to BTC 0.00).
* Max leverage: gross ≤ 1.25 (average 1.02, max 1.24 in the backtest).
* Rebalance: daily targets at the 00:00 UTC daily close; changes are small (turnover 6.2×/yr).
* Bar/timezone: yfinance crypto daily bar stamped D closes at D+1 00:00 UTC. The CMC snapshot for
  Sunday D is used from the close of Monday D+1.
* Cost assumed: 10 bp per side.

## Headline (2018-03-08 → 2026-09-27, net 10 bp)
| | Sharpe | CAGR | Vol | MaxDD |
|---|---|---|---|---|
| Full | 0.77 | 12.9 % | 17.8 % | −25.3 % |
| IS 2018-22 | 0.76 | 12.9 % | 18.1 % | −24.6 % |
| OOS 2023-26 | 0.78 | 12.9 % | 17.5 % | −25.3 % |

Turnover 6.2×/yr, average gross 1.02, ρ to the live BAB book 0.26, deflated Sharpe 0.61 at 24 trials.

## Live data dependency
Weekly: `python code/crypto-alts/shared/cmc.py` (incremental; appends missing Sunday snapshots to
`data/CMC_listings_weekly.parquet`), or `load_inputs(refresh_cmc=True)`. The endpoint is CMC's
unofficial, keyless `data-api/v3`. If it stops answering, the signal goes stale: forward-fill is
capped at 10 days, after which names drop out of the universe and the book goes flat.

## Risks
Short-leg carry is unmodelled (10 %/yr on short notional → Sharpe 0.50). The book is weak with a
10-name universe (0.30). CMC supply methodology changes cause jumps, which the rank transform and clip mitigate.

Figures: `01_equity_drawdown.png`, `02_ic_by_horizon.png`, `03_yearly.png`.
