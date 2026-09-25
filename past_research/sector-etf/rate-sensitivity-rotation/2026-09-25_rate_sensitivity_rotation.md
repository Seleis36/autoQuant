# rate-sensitivity-rotation — sector rate betas × the recent trend in 10-year yields

**Status: Failed.** Asset class `sector-etf`. Date 2026-09-25.

## Idea
QuantSeeker's "rate momentum" sector strategy (2024-25, reported to beat 12-month price momentum
since 1998) ranks sectors by the return a regression on 10-year-yield changes implies. The economic
story: yields trend at 1-12 month horizons, and if equity sectors under-react to the rate
component of their news, sectors that gain from the ongoing yield trend (banks, energy when yields
rise; utilities, real estate, staples when they fall) keep gaining, net of the market.

## Setup
Common sector-etf setup (IS 1999-2014 / OOS 2015-2026, 2 bp/side, close *t* → *t+1*, SPY hedge to
beta 0). Rate beta = coefficient on ΔDGS10 in a rolling 2-factor OLS (SPY + ΔDGS10) over L = 126 or
252 days. Signal = rate beta × (DGS10 change over the past k days, **lagged one day** — FRED's
constant-maturity yields are end-of-day quotes that are not synchronous with the 16:00 ET ETF close).
k ∈ {21, 63, 126, 252}; monthly rebalance or 21-day tranches; linear cross-sectional weights.

Note: with linear cross-sectional weights a common scalar (the yield trend) only enters through its
sign, so "beta × trend" and "beta × sign(trend)" are the same book: 32 printed rows are 16 distinct
books, plus the static rate-beta tilt for 2 windows = 18 distinct books.

## Results (`rate_grid.py`)
| Cell | Sharpe full | IS | OOS | monthly IC IS / OOS |
|---|---|---|---|---|
| L126, k21, monthly (best) | 0.33 | 0.35 | 0.30 | 0.06 / 0.02 |
| L126, k21, tranches | 0.32 | 0.39 | 0.24 | 0.06 / 0.02 |
| L252, k21, monthly | 0.29 | 0.32 | 0.24 | 0.03 / 0.04 |
| L252, k252 | 0.04 | 0.14 | −0.07 | 0.01 / −0.02 |
| L126, k63, monthly | −0.18 | −0.21 | −0.14 | −0.02 / −0.03 |
| static rate-beta tilt (L126 / L252) | −0.01 / −0.16 | | | |

Only the 1-month yield change carries any information, and weakly (vol ≈6 %, CAGR ≈2 %). 3- to
12-month rate trends — the horizon at which yields actually trend (rates-bonds research) — are
worthless or negative for sector selection: sectors price the rate trend as it happens.

## Verdict
18 distinct books. Best 0.33 full / 0.30 OOS, t-stats < 2 in either half. **Binding constraint:
no under-reaction** — the rate-implied component of sector returns is priced within a month.

## Files
`code/sector-etf/rate-sensitivity-rotation/rate_grid.py` (+`rate_grid.csv`).
