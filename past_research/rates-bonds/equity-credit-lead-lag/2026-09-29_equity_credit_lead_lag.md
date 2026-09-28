# equity-credit-lead-lag — do stocks lead credit ETFs at daily frequency?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

A long literature finds stock returns lead high-yield bond returns (Kwan 1996; Hotchkiss &
Ronen 2002; Downing, Underwood & Xing 2009 — "stocks lead HY bonds but not IG"): the equity
market is more liquid and more informationally efficient, so credit catches up with a lag.
If that survives in the bond-ETF wrapper, yesterday's equity move (or the part of it the
credit ETF has not yet absorbed) predicts today's duration-stripped credit return.

`credit-spread-trend` (2026-09-22) showed credit is the only rates axis with risk-asset beta
and that *confirming* credit signals are too slow; a *leading* one from equities is the
natural next thing to try.

## 2. Setup

* Traded objects (hedge ratios from published effective durations, fixed, not fitted):
  HY = HYG − 0.47 IEF · JNK = JNK − 0.47 IEF · IG = LQD − 1.15 IEF · EM = EMB − 1.0 IEF.
* Predictors at the close of day t: `spy_k` (SPY k-day return, k = 1, 2, 5); `resid_k`
  (−(credit k-day return − β·SPY k-day return), β on a trailing 252-day regression: positive
  = credit has lagged equities); `own_k` (the premium's own return, autocorrelation control).
* Pre-registered direction: follow (credit catches up with equities).
* Split fixed in advance: IS 2007-04 → 2017 (HYG/LQD pre-2010 spliced; JNK/EMB from 2010),
  IS10 = 2010-2017 shown separately so the GFC does not carry the in-sample number,
  OOS 2018 → 2026. Cost: 2 bp/side on gross turnover of both legs.

## 3. Results

### Round 1 — `01_screen.py`, `01_screen_output.txt`: Pearson correlations

108 cells (4 credits × 3 predictors × 3 k × 3 h). Correlations are ≤ 0.1 in absolute value
outside crisis windows, flip sign between IS and OOS, and the few large ones are produced by
single episodes: IG `own5 → h1` is −0.31 IS (2008) and +0.55 OOS (March 2020 LQD crash and
Fed rebound).

### Round 2 — `02_books.py`, `02_books_output.txt`: Spearman ICs and books

Spearman IC of the 1-day predictor on the next day's premium: IS −0.02 → +0.04, OOS −0.03 →
−0.09 across all four credits. 96 books (predictor × k × h × {all days, |z| > 1.5 only}):
median IS −0.38, median OOS −0.56; 2 cells above 0.3 IS, none of them above 0.3 OOS.

### Round 3 — `03_gross.py`, `03_gross_output.txt`: gross vs net

The negative net numbers are mostly cost: a daily sign-flip on a two-leg spread turns over
220–550× notional a year, ≈ 0.4 Sharpe per bp of cost. Gross, the lead-lag itself:

| Follow-SPY, 1-day hold, gross | IS10 2010-17 | OOS 2018-26 |
|---|---|---|
| HY | 0.02 | −0.58 |
| JNK | 0.03 | −0.33 |
| IG | 0.29 | −0.12 |
| EM | 0.52 | −0.35 |

**There is no equity → credit-ETF lead-lag at the daily close since 2010**, even before
costs. ETF market makers arbitrage the ETF price against equity and CDX hedges intraday; the
under-reaction the literature finds lives in the underlying bonds' stale prices (the NAV),
not in the ETF price that can be traded.

## 4. What showed up instead (not a claim)

The sign that does appear is the *opposite* one, and mostly after 2018: credit ETFs partly
**reverse** large equity-driven moves the next day. Fading the residual on large-move days
only (|z| > 1.5, ~6 % of days) at 2 bp net: HY 0.15 / 0.63, JNK 0.40 / 0.55, IG 0.44 / 0.81,
EM 0.38 / 0.69 (IS 07-17 / OOS 18-26). Fading SPY itself on big days: HY −0.15 / 0.69,
JNK 0.63 / 0.56. The gross residual-fade on all days is 0.8–1.1 OOS but only 0.0–0.6 IS10,
and it cannot pay 2 bp at 200–470× turnover.

That pattern is consistent with bond-ETF **liquidity provision** — on stress days the ETF is
the liquidity vehicle, trades through the NAV, and mean-reverts (Pan & Zeng 2019; Dannhauser &
Hoseinzade 2022). But the hypothesis was formed after seeing 2018-2026, the IS evidence is
weak and mixed in sign, and there is no untouched sample left to test it on with this data.
It is recorded here as a lead for a future researcher who can get ETF premium/discount-to-NAV
history (iShares publishes daily premium/discount), which would test the mechanism directly
rather than through its price footprint.

## 5. Verdict

**Failed.** ~240 cells over three rounds. The pre-registered lead-lag is absent gross of
costs since 2010 (−0.58 to −0.12 OOS for the follow-SPY book), and the reversal that
appears instead was found by looking at the OOS window, so it cannot be claimed.
