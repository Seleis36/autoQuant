# Alpha spec — residual-momentum (us-large-cap)

**Status:** Working (modest). Net Sharpe 0.63 full / 0.61 IS (2011-17) / 0.63 OOS (2018-26-09)
at 5 bp per side, 10 % vol.

| field | value |
|---|---|
| Instruments | S&P 500 constituents (single names, flat daily cache `data/<TICKER>_d.parquet`) + hedge: EW member basket (default) or `RSP` |
| Direction | long/short, dollar-neutral stock book + beta hedge (small net short/long of the EW basket) |
| Signal | residual 12-1 momentum t-stat: daily OLS of r on EW-market and EW-sector returns over 252 bars; residuals summed over bars [t-251, t-21] / (std·√n) |
| Cross-section | winsorised ±3σ z-score, demeaned within GICS sector |
| Sizing | linear in z, Σ|w| = 1 before scaling; then × min(10 % / realised 126-bar vol of the unscaled book, 3.6) |
| Rebalance | last NYSE session of each month (`code/us-large-cap/shared/trading_calendar.py`), weights, hedge and scale all re-set together, held to the next month-end |
| Leverage | average gross 2.36, max 3.55 (validated range) |
| Bar / timezone | daily closes, US/Eastern session close; weights computed at close t, filled at close t, earn t→t+1 |
| Cost assumed | 5 bp per side on every Σ|Δw| (stocks, hedge, scale changes) |
| Turnover | 12.7× per year one-way at 10 % vol |
| Warm-up | 275 bars per name; vol scale needs 60 bars of book returns |

## Performance (net 5 bp, 10 % vol target)

| | Sharpe | CAGR | max DD | vol |
|---|---|---|---|---|
| Full 2011-01 → 2026-09 | 0.63 | 6.3 % | −16.9 % | 10.6 % |
| IS 2011-2017 | 0.61 | | | |
| OOS 2018-2026 | 0.63 | | | |
| cost 2 bp / 10 bp | 0.66 / 0.57 | | | |

Correlation to SPY 0.13; to the `quality-value-composite` fundamental blend −0.01. Also a sleeve
(multiplier 0.457) of `alphas/us-large-cap/large-cap-sleeve-blend/` (1.03 / 1.57 / 0.81 OOS).

## Code

```python
import sys; sys.path.insert(0, "code/us-large-cap/residual-momentum")
from strategy import residual_momentum_weights, _panel_inputs
X = _panel_inputs()                 # {"close", "member", "sector", "rsp"}
W = residual_momentum_weights(X)    # all defaults = this spec; hedge="RSP" for the one-line hedge
```

`W` columns are tickers (plus `RSP` when hedge="RSP"); the EW-basket hedge is folded into the
ticker weights. Lookahead check: `lookahead_check.py` (truncation at mid-month and month-end
dates reproduces full-sample weights exactly).

Report: `past_research/us-large-cap/residual-momentum/2026-09-27_residual_momentum.md`.
