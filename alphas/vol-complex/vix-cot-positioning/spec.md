# Alpha spec — `vix-cot-positioning`

Report: `past_research/vol-complex/vix-cot-positioning/2026-09-27_vix_cot_positioning.md`
Status: **Working (with caveats)**. Net Sharpe 1.00 full / 0.96 OOS at 5 bp/side. However,
2022–26 Sharpe is 0.38 and the book is flat as of 2026-09-25. Expected live Sharpe ≈ 0.4–0.8.

## Instrument & mechanics

| Field | Value |
|---|---|
| Instrument | **VIXY** (ProShares VIX Short-Term Futures ETF), single name. Equivalent: long SVXY at −weight (Sharpe 0.95, no borrow) |
| Direction | **short / flat** only. Weight ∈ [−1, 0] |
| Max gross exposure | **1.0** (short 100 % of capital in VIXY), reached on 9 % of days |
| Average exposure | −0.40; in the market 72 % of days, average size 0.55 when in |
| Rebalance | daily at the NYSE close; the weight for close *t* is held from close *t* to close *t+1* |
| Signal inputs | `^VIX`, `^VIX3M` daily closes (yfinance), VIXY closes; weekly CFTC TFF VIX-futures report (`data/CFTC_COT_tff_vix_w.parquet`) |
| Sizing rule | average of 25 binary votes: 1[VIX3M/VIX at close t−1 > 1 AND score_t > θ] over 5 positioning scores × θ ∈ {−0.5, 0, 0.25, 0.5, 1.0}; weight = −mean(votes) |
| Scores | z-score of asset-manager net share (AM long − AM short)/OI over 52/104/156 reports; (z(AM) − z(lev-funds net))/2 over 104/156 reports; min periods 2/3 of window |
| COT timing | a report (as-of Tuesday) is used from the first session dated after `avail_utc` = Tue + 4 d 21:00 UTC (Monday's close for a normal Friday release; holiday weeks +7 d; shutdown backlogs at their release date) |
| Bar / timezone | yfinance daily bars, auto-adjusted closes, tz-naive index = US session date. The VIX-family close (16:15 ET) is lagged one session so the signal is known at the 16:00 fill |
| Cost assumed | **5 bp per side** on traded notional (VIXY half-spread ~1–2 bp). At 10 bp: 0.99; at 40 bp: 0.89 |
| Turnover | ≈ 10.7× capital per year (one-way) |
| Not modelled | short-borrow fee on VIXY (≈ 1–5 %/yr × 0.4 average short ≈ −0.04 Sharpe) |

## Reference performance (`final.py`, net 5 bp, VIXY, no cash yield)

| Window | Sharpe | CAGR | Vol | MaxDD | Skew | t_NW |
|---|---|---|---|---|---|---|
| FULL 2011-01 → 2026-09 | **1.00** | 32.0 % | 33.4 % | −43.3 % | −1.47 | 4.33 |
| IS 2011 → 2018 | 1.04 | 35.4 % | 35.1 % | | | |
| OOS 2019 → 2026-09 | **0.96** | 28.6 % | 31.4 % | | | |
| 2022 → 2026-09 | 0.38 | ~8.7 %/yr | | | | |
| Carry reference (short if VIX3M/VIX(t−1) > 1) | 0.60 / OOS 0.54 | 18.2 % | 60.7 % | −86 % | | |

* SPY β 0.96, α 19 %/yr (t 2.7); OOS β 0.71, α 17.5 %/yr (t 1.9).
* Bootstrap Sharpe 5–95 %: [0.63, 1.38]. DSR 0.87 at N = 150 trials.
* Correlation (2018+) with live books: sector-sleeve-blend 0.18, treasury-flow-calendar −0.06,
  crypto-alts BAB 0.00.

Figures: `equity_drawdown.png`, `signal_exposure.png`, `yearly_sharpe.png`. Series:
`backtest_series.parquet` (`weight_VIXY`, `net_ret`, `carry_lag1_net`). Tables: `stats.csv`, `yearly.csv`.

## Tail risk (must be read)

This is a short-vol book. VIXY's worst closes in the sample are +43 %, +39 % and +34 %. At full
size, one such day costs 35–45 % of capital. The worst realised day was −25.5 % (2020-06-11).
Apr-2025 lost 28 % over three weeks. The gate sat out Feb-2018, Mar-2020 and Aug-2024 because
inverse-vol crowding preceded them, and that will not always happen. Running at `size=0.5` halves
every number above except Sharpe.

## Deployment interface

```python
import sys
sys.path.insert(0, "code/vol-complex/vix-cot-positioning")
sys.path.insert(0, "code/vol-complex/shared")
from strategy import target_weight
from fetch_cot_vix import fetch_tff, refresh_current_year

refresh_current_year()            # weekly (Saturday onward): pulls this year's CFTC file, merges
tff = fetch_tff()                 # data/CFTC_COT_tff_vix_w.parquet
# vixy, vix, vix3m: pd.Series of daily closes (VIXY, ^VIX, ^VIX3M), tz-naive session-date index,
# at least 3 years of COT history before the first traded date (the 156-report z-score needs 104)
w = target_weight(vixy, vix, vix3m, tff)      # defaults = spec; w.iloc[-1] = today's target
```

`target_weight` defaults: `thresholds=(-0.5, 0, 0.25, 0.5, 1.0)`, `slope_threshold=1.0`,
`slope_lag=1`, `size=1.0`. A truncation test confirms that weights computed on data cut at any
date equal the full-history weights (no look-ahead, no dependence on future rows).
