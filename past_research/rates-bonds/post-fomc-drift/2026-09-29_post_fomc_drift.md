# post-fomc-drift — do Treasury yields keep drifting after Fed policy moves?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed** (follow-up `fomc-front-end-reversal` also Failed)

## 1. Idea

Brooks, Katz & Lustig, *Post-FOMC Announcement Drift in U.S. Bond Markets* (NBER w25127,
2018): after a fed funds target **increase**, bond-mutual-fund investors — for whom a hike is
salient — sell gradually for weeks; arbitrageurs absorb that supply slowly, so longer
Treasury yields drift up after the announcement. Prediction: short duration for several weeks
after hikes (and, symmetrically if weaker, long after cuts).

## 2. Setup — `01_screen.py`, `01_screen_output.txt`

* **Target events (A):** FRED `DFEDTAR` (to 2008-12-15) spliced with `DFEDTARU` (upper bound):
  185 changes since 1982, **60 in 1994-2009, 32 in 2010-2026**. Event day = first day the new
  target is in the series. Pre-1994 the Fed did not announce decisions, so 1985-1993 is
  reported as "early" and is not the IS window.
* **Surprise events (B):** 2y CMT change on each of the 270 scheduled FOMC statement days
  since 1994 (calendar snapshot from `treasury-flow-calendar`); entry lagged one extra day
  because H.15 yields are published after the close.
* Position: yield-up event → short duration, yield-down → long, for H ∈ {5, 10, 20, 40, 60}
  trading days; overlaps summed and clipped to ±1; 2 bp/side.
* Instruments: synthetic 2y / 5y / 10y excess returns (1982+), SHY / IEF / TLT excess (2002+).
* **Split fixed in advance:** IS 1994–2009, OOS 2010–2026.
* 7 event variants (all / hikes / cuts; surprise all / |Δ| ≥ 5 bp / up / down) × 5 horizons ×
  6 instruments = **210 cells**.

## 3. Results

**The drift, as published — duration (10y, TLT):**

| Variant | syn10 IS / OOS | TLT IS / OOS |
|---|---|---|
| hikes only, H = 20 | −0.09 / 0.30 | −0.50 / 0.28 |
| hikes only, H = 60 | −0.01 / 0.26 | −0.38 / 0.30 |
| all target changes, H = 20 | −0.11 / 0.30 | −0.23 / 0.29 |
| surprise ≥ 5 bp, H = 40 | 0.09 / 0.24 | 0.13 / 0.30 |

In 1994-2009 the hike drift is **negative** on every horizon (TLT −0.38 to −0.64): long
yields fell after hikes as often as they rose (the 2004-06 "conundrum" is in this window).
OOS 2010-2026 it is +0.25 to +0.30, carried by the 2022 hiking cycle, at 10-30 % exposure.
Not a stable effect.

**Front end (2y, SHY) after target changes:** all changes, H = 40-60: syn2 IS 0.38-0.47 /
OOS 0.28-0.35, SHY IS 0.65 / OOS 0.28-0.34. Consistent in sign, but this is the
well-known persistence of Fed cycles (the 2y keeps pricing the next move) earning
0.3 %/yr on 26-33 % exposure — Sharpe 0.3, not a strategy.

**The surprise version in the front end.** The follow-the-surprise book on the 2y is
negative in both windows at short horizons:

| Follow 2y FOMC-day move, H = 5, **net of 2 bp/side** | IS 1994-2009 | OOS 2010-2026 |
|---|---|---|
| syn2 | −0.79 | −0.64 |
| SHY (IS = 2002-09) | −0.47 | −0.62 |
| syn2, \|Δ\| ≥ 5 bp | −0.54 | −0.35 |

It was first read as the 2y reversing its FOMC-day move, and taken forward as a separate
idea (`fomc-front-end-reversal`). **That reading was wrong, and the follow-up shows why:**
the 2y excess return has ~1.5 %/yr of volatility, so 2 bp/side on a book that re-sets eight
times a year is a large share of its P&L. The *fade* book is negative net too; gross, both
are ≈ 0 OOS (−0.18 to +0.15). The FOMC-specific reversal does exist in 1994-2009 (event-study
slope −0.34, t = −3.2) but not in 2010-2026 (+0.06). The 210 cells here count towards
that idea's trial total.

## 4. Verdict

**Failed** for the drift mechanism: the post-hike drift in long yields is negative in
1994-2009 (TLT −0.4 to −0.6) and only +0.3 in 2010-2026, driven by one cycle. The
front-end cycle persistence is real but only 0.3 Sharpe.
