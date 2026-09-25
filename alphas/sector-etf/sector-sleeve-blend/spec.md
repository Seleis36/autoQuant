# Alpha spec — `sector-sleeve-blend`

Report: `past_research/sector-etf/sector-sleeve-blend/2026-09-25_sector_sleeve_blend.md`
Status: **Working (borderline)**. Net Sharpe 0.88 full / 0.81 OOS at 2 bp. Expected live Sharpe
≈0.6-0.8. The case for deploying it is diversification (β 0.26, ρ ≈ 0 with the live books), not a
high standalone Sharpe.

## Instrument & mechanics

| Field | Value |
|---|---|
| Instruments | **XLK XLF XLE XLV XLI XLY XLP XLU XLB XLRE XLC** + **SPY** (hedge / beta leg) — 12 ETFs, all in the shared daily cache |
| Book | simulated, long **and** short, cross-sectional basket |
| Direction | long/short per name; the book is net long on average (+0.36), range −0.38 … +2.0 |
| Max gross exposure | **2.0** (`gross_cap=2.0`, binds on ~1 % of days; uncapped research max 2.4). Conservative option `gross_cap=1.0`: same Sharpe, no margin, worst day halved, lower CAGR — see Risks |
| Rebalance | daily at the NYSE close; the row for close *t* is held from close *t* to close *t+1* |
| Sizing | four sleeves, each scaled by k_i = (10 % / √n) / σ_i, σ_i = the sleeve's own expanding net-return vol through the prior 31 Dec; weights fixed within the calendar year |
| Bar / timezone | yfinance daily bars, auto-adjusted OHLC, tz-naive index = US session date. **Uses Open** (overnight return) as well as Close |
| Cost assumed | **2 bp per side** on all traded notional (sector-SPDR half-spreads 0.2-1.3 bp; MOC fills are cheaper). At 5 bp: 0.73 full / 0.65 OOS |
| Turnover | ≈ 54× capital per year (one-way) |
| Average exposure | gross 1.13, net long 0.36 |

## Sleeves (all inside `strategy.py`)

| Sleeve | Signal at close *t* | Weights |
|---|---|---|
| ON | mean cross-sectional rank of −Σ log(Open/prevClose) over 21, 42, 63, 126, 252 days | linear, dollar-neutral, 21-day tranches; SPY = −Σ β_i w_i (EWM-126 β) |
| CAL | is **day t+1** in TOM [−3, +3], a scheduled FOMC statement day or the day before, or the last session before a weekday NYSE holiday? | EW long all listed sectors if yes, flat otherwise |
| DIP | per sector: RSI(2) < 10 and close > SMA200 → enter; exit when close > SMA5 or after 10 sessions | +1/9 per active sector |
| RATE | 126-d rate beta (2-factor OLS on SPY and Δ10y) × sign of the 10y yield's 21-day change, lagged 1 day | linear, dollar-neutral, monthly; SPY β-hedge |

A sector joins once it has 252 days of history: XLRE from 2016-10, XLC from 2019-06.

## Reference performance (`final_eval.py`, excess of T-bills, 2 bp)

| Window | Sharpe | CAGR | Vol | MaxDD | t_NW |
|---|---|---|---|---|---|
| FULL 2002-01 → 2026-09 | **0.88** | 9.4 % | 10.9 % | −24.7 % | 4.85 |
| IS 2002 → 2014 | 0.94 | | | | |
| OOS 2015 → 2026-09 | **0.81** | | | | |
| 2003+ (≥ 3 sleeves eligible) | 1.02 | | | | |
| Selection-free control (WF7: 7 candidate sleeves, walk-forward on/off) | 0.91 full / 0.62 OOS | | | | |
| SPY buy & hold (excess) | 0.50 / OOS 0.70 | 8.1 % | 18.9 % | −56.2 % | |

Total-return Sharpe (what the paper book shows): 0.94 full / 0.89 OOS, CAGR 10.2 %.
Alpha vs SPY 7.1 %/yr (t 3.6) full, 5.4 %/yr (t 1.97) OOS, β 0.26. Bootstrap 5-95 % Sharpe
[0.57, 1.24], P(Sharpe > 1) = 0.30. DSR 0.94 at N = 200 trials, 0.85 at N = 1000.
Correlation since 2018 with treasury-flow-calendar −0.004, crypto-alts BAB +0.022.

Figures: `equity_drawdown.png`, `sleeve_contributions.png`. Series: `backtest_series.parquet`
(`net_excess_2bp`, `spy_excess`). Yearly table: `yearly_excess_returns.csv`.

## Deployment interface

```python
import sys; sys.path.insert(0, "code/sector-etf/sector-sleeve-blend")
from strategy import target_weights, SECTORS

# close, open_: DataFrames (date x ticker) with the 11 sector ETFs and SPY, auto-adjusted daily bars,
#               full history (>= 4 years; the yearly risk weights need 3 years of sleeve returns)
# y10: 10-year yield series. Pass yfinance "^TNX" Close (refreshed by live_lib.daily);
#      the default reads data/FRED_DGS10_d.parquet, which nothing refreshes live.
W = target_weights(close, open_, y10=tnx_close)       # DataFrame, columns SECTORS + ["SPY"]
w_today = W.iloc[-1]                                   # hold from today's close to the next close
```

`^TNX` in place of DGS10 was tested: 0.89 full / 0.84 OOS, daily ρ 0.996 with the research book.

## Operational notes
* **FOMC schedule**: `code/sector-etf/sector-sleeve-blend/fomc_dates.csv` covers scheduled meetings
  through 2027 (unscheduled ones are excluded in code). Append the next year's Fed calendar each
  December. A missing date only switches off one CAL window day.
* **Trading calendar**: past sessions come from the data index. Day *t+1* beyond the last bar comes
  from NYSE holiday rules in `strategy.py`, which match every session 1999-2026 except six
  unscheduled closures (9/11, presidential funerals, Hurricane Sandy).
* The function recomputes everything from full history on each call (≈0.3 s on the 1998-2026 panel). Output is
  deterministic given the same bars.

## Risks
* **Jump risk from DIP + CAL**: worst days −10.0 % (2011-08-08), −8.8 % (2020-02-27), −5.7 %
  (2018-02-05) against a 1 % VaR of −1.9 %. With `gross_cap=1.0`: Sharpe 0.88 / 0.85 OOS, CAGR 7.1 %,
  worst day −5.7 %, and no margin needed. Prefer it if the book cannot take a 10 % day.
* Weak OOS alpha significance (t 1.97). RATE is the weakest leg (t 1.85). CAL and DIP are
  long-equity timing sleeves that correlate 0.3-0.4 with each other.
* Lost money in 5 of 25 years (2002 −22 % with CAL alone, 2011, 2015, 2018 −10 %, 2024).
