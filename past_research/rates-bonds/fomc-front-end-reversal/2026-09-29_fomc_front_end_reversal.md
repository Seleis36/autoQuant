# fomc-front-end-reversal — does the 2y fade its FOMC-day move?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Where it came from

In `post-fomc-drift`, the book that *follows* the 2y yield's FOMC-statement-day move for the
next five days was negative in both windows (syn2 −0.79 IS 1994-2009 / −0.64 OOS 2010-2026;
SHY −0.62 OOS). Read at face value that says the front end overreacts to FOMC news and
partly reverses within a week — a plausible mechanism (statement / dot-plot / presser
reactions are re-interpreted over the following days of Fed speak). Before building a
strategy on it, two checks: is the reversal visible in yields rather than only in a net
Sharpe, and is it specific to FOMC days?

## 2. Event study — `01_event_study.py`, `01_event_study_output.txt`

Regression of the cumulative yield change over t+1…t+h on the day-t change (−1 = full
reversal), FRED CMT yields in bp, with placebo event sets.

| 2y, slope (t) | h = 1 | h = 2 | h = 5 | h = 10 |
|---|---|---|---|---|
| FOMC, IS 1994-2009 (n = 135) | −0.14 (−1.8) | **−0.34 (−3.2)** | −0.35 (−2.7) | −0.36 (−1.6) |
| FOMC, OOS 2010-2026 (n = 134) | **+0.15 (+2.5)** | +0.06 (0.7) | +0.08 (0.7) | +0.28 (1.7) |
| day before FOMC (placebo), OOS | −0.32 (−2.4) | −0.51 (−2.8) | −0.35 (−1.4) | −0.59 (−1.9) |
| CPI days, OOS | −0.02 | +0.02 | −0.08 | −0.03 |
| NFP days, IS / OOS | −0.01 / +0.18 | −0.12 / +0.09 | −0.27 / +0.16 | −0.16 / +0.26 |
| all other days, IS | +0.03 (1.7) | +0.01 | −0.04 | +0.05 |
| all other days, OOS (n = 3638) | **−0.11 (−6.1)** | −0.11 (−4.4) | −0.11 (−2.8) | −0.04 |

* The FOMC-specific reversal is **real in 1994-2009 and gone in 2010-2026**; since 2010 the
  first day after the statement actually *continues* the move.
* What exists since 2010 is a **generic** next-day mean reversion in the 2y on ordinary days
  (t = −6), absent before 2010. That is the zero-lower-bound era: with the policy rate pinned
  (48 % of 2010-2026 days) and forward guidance anchoring the front end, 2y moves revert.
* The 5y and 10y show the same pattern, weaker.

## 3. Books — `02_books.py`, `02_books_output.txt`

Fade = long the 2y after its yield rose (+sign(Δy)). 2 bp/side.

| Book | IS net | OOS net | OOS gross | OOS in ZLB / non-ZLB (net) |
|---|---|---|---|---|
| FOMC fade, enter day t, H = 1…10 (syn2) | −0.55 … +0.08 | −1.24 … −0.39 | −0.18 … +0.02 | −1.16 / −1.38 (H = 1) |
| FOMC fade, enter t+1, H = 1…10 (syn2) | −0.14 … +0.02 | −0.84 … −0.37 | −0.10 … +0.14 | |
| same on SHY | −0.70 … +0.27 | −1.24 … −0.32 | −0.08 … +0.15 | |
| generic daily fade, all days (syn2) | −3.14 | −2.81 | **+0.95** | −4.24 / −2.31 |
| generic daily fade, all days (SHY) | −2.71 | −3.51 | +0.40 | −5.55 / −2.73 |
| generic fade, \|Δy\| ≥ 5 bp only (SHY) | −1.80 | −1.63 | +0.28 | |

**The FOMC "reversal" was a cost artifact.** The 2y's excess return has ~1.5 %/yr of
volatility, so 2 bp/side on a book that trades eight events a year is a large share of its
P&L. Both the follow and the fade books are negative net; gross, the FOMC fade is ≈ 0
(−0.18 to +0.15) OOS. The negative follow-book Sharpe was never evidence for the fade.

The generic ZLB-era reversal is gross-positive (0.95 syn2, 0.40 SHY) but turns over ~200×
a year on an instrument whose whole annual move is smaller than the cost. Nothing is
tradable on SHY at a realistic spread.

## 4. Verdict

**Failed.** 26 books plus 36 event-study cells, on top of the 210 cells of
`post-fomc-drift` that suggested it. The FOMC-day front-end overreaction existed in 1994-2009
(slope −0.34, t = −3.2) and has disappeared since. The lesson for the next researcher:
**on 2y / SHY, never infer the sign of an edge from a negative net Sharpe.** The cost at
2 bp/side is of the same order as the gross P&L, so both directions of a noise signal lose
money. Always print gross next to net.
