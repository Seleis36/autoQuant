# vol-regime-equity-timing — timing SPY with the vol-complex state

**Status: Failed.** No vol-complex signal times SPY better than buy-and-hold once the VIX close
(16:15 ET) is lagged to be knowable at the 16:00 fill. Buy-and-hold excess Sharpe is 0.78 IS /
0.79 OOS. The best rules match it OOS (0.80–0.84) by cutting risk, not by adding return. The
Bollerslev–Tauchen–Zhou VRP predictability is strong through 2018 and **reverses sign in 2019–26**.
34 configurations were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

The equity-premium literature says the vol surface carries information about the equity premium:
* Bollerslev, Tauchen & Zhou (2009): the variance risk premium VIX² − RV² predicts 1–3 month index
  returns.
* Johnson (2017): the VIX term-structure slope carries risk-premium information.
* Moreira & Muir (2017): volatility-managed portfolios.

Practitioners summarise this as "be in SPY when the VIX curve is in contango, in cash when it
inverts". The idea was to turn vol-complex state into a SPY weight (0–1.5×) and beat buy-and-hold on
a risk-adjusted basis. Such a strategy would be structurally different from the short-VIXY books.

## 2. Setup

* Data: `SPY`, `^VIX`, `^IRX` from 1998-12 (flat cache `*_d_pre2010` + current files) and `^VIX3M`
  from 2006-07. This session added `data/IDX_VIX3M_d_pre2010.parquet`.
* Returns are **SPY excess of 3-month T-bills**, 2 bp/side on |Δw|, with the weight at close *t*
  held *t → t+1*. Every VIX-family input is lagged one session. RV is from SPY closes, known at 16:00.
* Windows: IS 2011–18 (parameter choice) / OOS 2019–26. A second hold-out, **PRE 1999–2010**
  (dot-com, GFC), was never used for selection.

## 3. Results (01_screen.py, 02_reframe.py): excess Sharpe

| rule | FULL 99-26 | PRE 99-10 | IS 11-18 | OOS 19-26 | MaxDD | avg w |
|---|---|---|---|---|---|---|
| **SPY buy & hold** | 0.43 | 0.07 | **0.78** | **0.79** | −60 % | 1.00 |
| slope VIX3M/VIX > 1 (2006+) | 0.52 | 0.23 | 0.48 | 0.75 | −39 % | 0.89 |
| slope > 0.95 / > 1.05 | 0.57 / 0.64 | 0.01 / 0.46 | 0.61 / 0.76 | 0.94 / 0.64 | | |
| implied-vol target 12/15/18 ÷ VIX (cap 1–1.5) | 0.43–0.44 | ~0 | 0.73–0.76 | 0.84–0.86 | −34…−47 % | 0.67–1.01 |
| realised-vol target (non-vol benchmark) | 0.48–0.50 | 0.08 | 0.75–0.78 | 0.80–0.87 | | |
| Moreira-Muir variance-managed (RV² / VIX²) | 0.50 / 0.40 | 0.06 / −0.03 | 0.74 / 0.67 | 0.85 / 0.75 | | |
| VRP > 0 (VIX > RV21), daily | 0.42 | 0.20 | 0.75 | 0.52 | | |
| VIX < MA20 / < 1.1·MA20 / < 30 | 0.25 / 0.38 / 0.33 | | 0.59 / 0.65 / 0.67 | 0.91 / 0.88 / 0.70 | | |
| slope>1 × IV target; slope>1 or VIX<20; slope>1 & VRP>0 | 0.56 / 0.54 / 0.49 | | 0.55 / 0.52 / 0.52 | 0.73 / 0.75 / 0.59 | | |
| contrarian: 1.5× when slope < 0.9 | 0.49 | 0.10 | 0.79 | 0.64 | | |
| monthly 1 + k·z(VRP), k = 0.25 / 0.5 | 0.49 / 0.52 | 0.19 / 0.20 | 0.88 / **0.93** | 0.63 / 0.66 | | |
| monthly VRP > 0 / > expanding median | 0.47 / 0.42 | | 0.86 / 0.82 | 0.66 / 0.55 | | |
| COT vol-ETP crowding gate (idea 1's scores) on SPY | 0.50 / 0.59 | | 0.70 / 0.76 | 0.73 / 0.78 | | |
| weekly-rebalanced slope>1 / IV15 | 0.53 / 0.44 | | 0.61 / 0.74 | 0.66 / 0.80 | | |

**BTZ predictive regression** of forward SPY log return on month-end VRP (VIX² − RV², HAC t):

| window | 1-month β t-stat | 3-month β t-stat |
|---|---|---|
| 1999–2010 | **5.45** | 4.96 |
| 2011–2018 | **5.66** | 1.35 |
| 2019–2026 | **−1.71** | −1.79 |

The VRP → equity-return relation was one of the strongest published predictors through 2018 and has
flipped sign since. The IS-best rule (monthly VRP tilt, 0.93 IS) delivers 0.66 OOS, below
buy-and-hold.

## 4. Why it fails

* The one-day lag is binding. Slope and VIX-trend filters are regime switches that fire *after* the
  first down day. With the 15-minute-stale VIX removed, they miss the entry day of each sell-off and
  then miss the rebound. Daily slope filters turn over 15–40× a year.
* Vol targeting (implied or realised) lowers drawdown (−60 % → −34…−47 %) but its Sharpe gain over
  buy-and-hold is within noise. In 2011–26 it is 0.73–0.87 vs 0.78–0.79. It is also not a
  vol-complex edge: realised-vol targeting, with no VIX input, does as well.
* The only window where vol timing clearly adds Sharpe is 1999–2010 (two −50 % bear markets), and
  in that window VIX3M exists only from 2006.

## 5. Conclusion

SPY timing with VIX-complex state is not an edge on daily bars in the post-2011 sample. Do not revisit
without intraday access to the 16:00 VIX value. That would remove the one-day lag, which is the
binding constraint for regime switches. Do not revisit the BTZ VRP either: its sign has flipped.

## 6. Files

`code/vol-complex/vol-regime-equity-timing/`: `ve_lib.py` (long 1999+ panel, excess-return
backtest), `01_screen.py` (24 rules), `02_reframe.py` (monthly VRP regressions and rules, COT gate
on SPY, weekly rebalancing). No alpha spec: the idea failed.
