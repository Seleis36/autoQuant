# Dollar-regime tilt (non-US vs US equity keyed to the dollar trend) — Failed

**Asset class:** `global-equity-etf` · **Short name:** `dollar-regime-tilt` · **Date:** 2026-09-26
**Status:** **Failed.** The dollar's trend adds little beyond what the equity spread's own trend
already carries. That own-trend control turned out to be the more interesting signal, and it is
followed up separately as [`intl-relative-trend`](../intl-relative-trend/).

## Idea

A rising dollar tightens global financial conditions: dollar-debt balance sheets, EM capital
outflows, and translation losses on unhedged foreign equity (Bruno & Shin 2015; SSGA/JPM
"EM outperform when growth and the dollar align"). Dollar trends are persistent (FX TSMOM).
So the sign of the dollar's trend should time non-US vs US equity: long non-US / short SPY when
the dollar falls, and the reverse when it rises.

## Setup

* Dollar: ICE `DX-Y.NYB`, **lagged one day**, because the ICE close is after the 16:00 ET ETF
  close. For 1-12 month trends the lag costs nothing.
* Traded spreads, each SPY-beta-hedged on a trailing 252d beta and vol-targeted to 10 %:
  EEM − βSPY, EFA − βSPY, and EW(9 country ETFs) − βSPY ("EXUS"). There is also a
  cross-sectional book that tilts each country by its dollar beta (2-factor rolling OLS on SPY
  and ΔDXY).
* Signal (pre-registered headline): **−mean(sign(dollar return over 21/63/126/252 d))**. Each
  lookback alone is also shown.
* **Control:** the same ensemble on the spread's *own* price. If the dollar only matters
  through the spread's trend, the dollar signal is redundant with plain relative momentum.
* Weekly (Friday) or monthly rebalance. 5 bp/side on the ETF leg + 1 bp on SPY.
  2001-01 → 2026-09, IS ≤ 2012, OOS 2013+.

## Results (net Sharpe)

`01_dollar_tilt.py`, 35 cells:

| Spread | Signal | Rebal | Full | IS | OOS | MaxDD |
|---|---|---|---:|---:|---:|---:|
| EEM−SPY | DXY ensemble | W | 0.21 | −0.16 | 0.45 | −29 % |
| EEM−SPY | DXY ensemble | M | 0.20 | −0.13 | 0.39 | −29 % |
| EEM−SPY | DXY 21d | W | 0.44 | −0.09 | 0.78 | −29 % |
| EEM−SPY | DXY 63d / 126d / 252d | W | 0.13 / 0.01 / 0.01 | | | |
| EFA−SPY | DXY ensemble | W / M | −0.18 / 0.06 | | | |
| EXUS−SPY | DXY ensemble | M | 0.28 | 0.16 | 0.37 | −27 % |
| XS dollar-beta tilt | DXY ensemble | W / M | 0.04 / −0.02 | | | |
| *EXUS−SPY* | *own-trend ensemble (control)* | *M* | *0.59* | *0.85* | *0.38* | *−23 %* |
| *EFA−SPY* | *own-trend ensemble (control)* | *M* | *0.43* | *0.60* | *0.30* | *−17 %* |
| *EEM−SPY* | *own-trend ensemble (control)* | *M* | *0.36* | *0.56* | *0.24* | *−28 %* |
| EXUS−SPY | 50/50 DXY + own | M | 0.51 | 0.61 | 0.44 | −13 % |
| EXUS−SPY | always long (drift) | M | −0.17 | 0.52 | −0.73 | −81 % |

`02_dollar_reframe.py`, 8 cells:

| Spread | Signal | Full | IS | OOS |
|---|---|---:|---:|---:|
| EEM / EXUS | dollar long-cycle reversal (5y) | −0.32 / −0.42 | | |
| EEM / EXUS | dollar long-cycle reversal (3y) | −0.32 / −0.28 | | |
| EEM / EXUS | 1y z-score mean reversion | −0.16 / −0.16 | 0.31 / 0.06 | −0.47 / −0.37 |
| EEM / EXUS | risk-off (dollar↑ & VIX > 1y median → short) | 0.22 / 0.27 | 0.26 / 0.41 | 0.20 / 0.16 |

## Reading

* The dollar ensemble alone reaches 0.2-0.3, with IS ≤ 0.16 on every EM spread. The only
  strong-looking cell, DXY 21d on EEM (0.78 OOS), is negative in-sample. Among 43 cells it is a
  selection artifact.
* The dollar ensemble signal correlates 0.33-0.40 with the spread's own trend signal. Blending
  them lowers drawdown (−13 %) but not Sharpe relative to own trend alone. **The dollar is
  mostly a noisier read of the equity spread's own trend.**
* The long-cycle dollar "reversal" is strongly negative, which reads as 3-5 year dollar
  *persistence*. The sample holds essentially two dollar cycles (2002-08 down, 2011-22 up), so
  that is two observations, not a result.

**Failed.** Variants: 43 cells. The one thing worth keeping is the control: time-series momentum
of the ex-US-vs-US spread itself, 0.59 full / 0.85 IS / 0.38 OOS, t_NW 2.9. It is taken up with
its own robustness work as `intl-relative-trend`.

## Files

`code/global-equity-etf/dollar-regime-tilt/01_dollar_tilt.py`, `02_dollar_reframe.py`.
