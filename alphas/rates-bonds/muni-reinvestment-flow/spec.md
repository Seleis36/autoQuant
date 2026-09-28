# Alpha spec — muni-reinvestment-flow

**Status:** Working (borderline) · **Asset class:** rates-bonds · **Report:**
`past_research/rates-bonds/muni-reinvestment-flow/2026-09-29_muni_reinvestment_flow.md`

## What it trades

Month-start reinvestment of municipal coupons and redemptions (paid on the 1st). Munis
outperform duration-hedged Treasuries over the first five sessions of the month.

| Leg | Instrument | Weight while held (per 1.0 of book capital, `scale` = 1) |
|---|---|---|
| long | MUB | +0.25 |
| long | TFI | +0.25 |
| long | ITM | +0.25 |
| long | SHM | +0.25 |
| short | IEF | −0.25 × (β_MUB + β_TFI + β_ITM), β vs IEF |
| short | SHY | −0.25 × β_SHM, β vs SHY |

* β = trailing 252-session OLS beta of the muni ETF's daily return on its hedge's daily return
  (min 126 sessions), estimated through the decision close. Typical values: MUB/TFI/ITM ≈ 0.3-0.6
  vs IEF, SHM ≈ 0.3-0.5 vs SHY. Average hedge notional 0.37.
* **Direction:** long munis / short Treasuries only (never reversed). Flat 76 % of sessions.
* **Timing:** set at the close of the last NYSE session of month m−1; held through the close of
  session 5 of month m; flat from session 5's close. Daily bars, US close, tz-naive.
  The live edge needs to know that the next session starts a month: `strategy.hold_flags` extends
  the observed index with an NYSE holiday calendar (the New Year rule matches NYSE).
* **Leverage:** gross 1.37 on held days at `scale` = 1. The validated book is `scale` = 1. Any
  leverage is a pure scalar: Sharpe is unchanged, while cost and drawdown scale with it.
  The blend analysis used 2.9× to run at half the risk of `treasury-flow-calendar`.
* **Cost assumption:** 2 bp per side on every leg (quoted spreads: MUB/IEF ~1 bp, TFI/ITM/SHM
  ~2 bp, SHY ~1 bp). The book dies above ~4 bp/side.

## Code

```python
import sys; sys.path.insert(0, "code/rates-bonds/muni-reinvestment-flow")
import strategy
w = strategy.target_weights(close)   # close: DataFrame with MUB TFI ITM SHM IEF SHY (adjusted)
# row t = target held from close t to close t+1
```

## Headline numbers (net of 2 bp/side, `scale` = 1, 252-day annualisation)

| | Sharpe | CAGR | Vol | MaxDD |
|---|---|---|---|---|
| 2008-2016 | 0.18 | 0.3 % | 1.5 % | −3.8 % |
| 2017-2026 (discovery window) | 0.88 | 1.2 % | 1.3 % | −2.9 % |
| Full 2008-2026 | 0.52 | 0.7 % | 1.4 % | −3.8 % |

Turnover 33×/yr; 23.5 % of sessions held. Correlation with `treasury-flow-calendar` ≈ 0; at
half its risk this book lifts that sleeve's full-sample Sharpe 1.21 → 1.32. Out-of-sample
evidence for the mechanism: muni fund NAVs, first-5-session excess +6.5 bp/month (t 2.5) in
2000-07 and +12.5 (t 2.6) in 2008-16, absent in the 1990s. Deflated-Sharpe probability of the
ETF backtest over 45 trials: 0.44.

## Figures

* `01_equity_curve.png` — gross and net cumulative return, 2008-2026.
* `02_per_year_sharpe.png` — per-year net Sharpe.
* `03_nav_holdout_by_era.png` — the NAV holdout statistic by era.
