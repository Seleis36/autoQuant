# fomc-cycle-weeks — do Treasuries follow the FOMC-cycle even-week pattern?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

Cieslak, Morse & Vissing-Jorgensen, *Stock Returns over the FOMC Cycle* (JF 2019): since 1994
the US equity premium is earned in the **even weeks** of FOMC-cycle time (weeks 0, 2, 4, 6
after a statement), which they attribute to systematic, mostly dovish informal Fed
communication after the bi-weekly Board meetings. If the channel is monetary news, Treasuries
should see it too. The deployed `treasury-flow-calendar` only uses FOMC day −1 and day 0;
the rest of the cycle had not been examined for rates.

## 2. Setup — `01_event_study.py`, `01_event_study_output.txt`

* FOMC-cycle time = calendar days since the last scheduled statement; CMVJ week buckets
  (week 0 = days −1…3, week 2 = 9…13, …, 7 = 34+); day −1 belongs to the next meeting's week 0.
* Mean daily excess return by week, for synthetic 10y / 2y (1994+), IEF / TLT (2002+), SPY
  for reference; computed with and without the deployed flow-calendar days (last 3 days of the
  month, FOMC −1 and 0) so the new effect cannot re-count the old one.
* **Split fixed in advance:** IS 1994–2009, OOS 2010–2026.

## 3. Results (bp/day, t in brackets)

| syn10 excess | IS 1994-2009 | OOS 2010-2026 | OOS, flow-calendar days removed |
|---|---|---|---|
| week 0 | +2.4 (1.1) | **+7.0 (3.0)** | +2.1 (0.5) |
| week 2 | +0.6 (0.2) | −4.3 (−1.9) | **−7.4 (−2.9)** |
| week 4 | +0.8 (0.3) | −1.6 (−0.9) | −2.4 (−1.4) |
| week 6 | +3.0 (1.1) | +0.8 (0.3) | −1.2 (−0.5) |
| week 5 | 0.0 | +5.7 (2.6) | +5.9 (2.5) |
| **even weeks** | +1.7 (1.4) | +0.8 (0.7) | **−2.6 (−2.1)** |
| odd weeks | +0.8 (0.6) | +2.1 (1.6) | +1.1 (0.8) |

* The OOS week-0 strength is exactly the deployed FOMC day −1 / day 0 leg; with those days
  removed it disappears.
* Treasuries have **no even-week premium**. IS it is +1.7 bp against +0.8 for odd weeks
  (t 1.4); OOS, net of the deployed days, even weeks are *negative* (−2.6 bp, t −2.1), with
  week 2 the worst (−7.4, t −2.9).
* The OOS week-2 / week-5 pattern (−7.4 / +5.9) has no IS counterpart (−1.2 / −1.1) and was
  not pursued: 8 weeks × 5 instruments × 2 windows × 2 exclusion modes = 160 cells, and a
  pattern visible only in one window of that table is what the table would produce by chance.
* Side note: SPY's even-week premium is still visible here in 2010-2026 (+7.0 bp, t 2.7).
  `sector-etf/equity-flow-calendar` found it faded on its sample.

## 4. Verdict

**Failed.** The FOMC-cycle effect in rates is fully contained in the statement window the
deployed strategy already trades. The rest of the cycle carries no premium in the direction
CMVJ's equity mechanism predicts.
