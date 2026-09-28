# credit-calendar-flow — does the credit premium have its own calendar?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

The only robust rates edge in this repo is calendar flow in **duration**
(`treasury-flow-calendar`: TLT month-end, FOMC, pre-auction; deployed). Credit has flow
calendars of its own that could produce a second, differently-risked sleeve:

* HY and IG mutual-fund / ETF inflows arrive at the start of the month (payroll-date
  contributions, reinvestment of the coupons that pay on the 1st and 15th);
* month-end index rebalancing drops downgraded and short bonds (forced selling into the
  last days, re-buying after);
* the weekday, pre-/post-holiday and macro-event (FOMC, CPI, payrolls) patterns.

Traded object: the **duration-stripped** premium, so that the TLT month-end effect cannot be
counted twice: HY = HYG − 0.47 IEF, JNK = JNK − 0.47 IEF, IG = LQD − 1.15 IEF (hedges from
published effective durations, fixed). Raw HYG / LQD are shown for comparison.
**Split fixed in advance:** IS 2007-04 → 2017, OOS 2018 → 2026.

## 2. Event study — `01_event_study.py`, `01_event_study_output.txt`

Mean daily return (bp) and t-stat for 22 calendar buckets × 7 series × 2 windows (~300 cells).

| HY premium, bp (t) | IS | OOS |
|---|---|---|
| last 3 days (ME−3, −2, −1) | +11.2 (1.6), −4.3, +6.3 | −2.7, +9.2 (2.3), −4.9 |
| first 3 days (MS+1, +2, +3) | +4.7, +4.7, +5.0 | +5.5, +9.8 (2.1), +2.1 |
| MS+4 | −14.1 (−1.7) | +4.9 |
| Tuesday / Wednesday | +4.3 (1.5) / +2.9 | +3.4 (1.5) / +4.1 (1.7) |
| pre-holiday | +5.5 (0.4) | +24.8 (1.5) |
| FOMC day | **+25.2 (2.3)** | −2.8 (−0.3) |

No bucket has |t| > 2 with the same sign in both windows, on any of HY, JNK or IG. The IG
premium's month-end is negative OOS (ME−3 −6.2 bp, t −2.5; ME−1 −5.0 bp, t −2.0): LQD's
month-end strength is duration, and hedging the duration out leaves a small *negative*
credit residual.

## 3. Window books — `02_books.py`, `02_books_output.txt`

Three windows chosen a priori from the mechanism, not from the table: turn of the month
(first 3 trading days), month-end (last 3), pre-holiday. Long-only, 2 bp/side on both legs.

| Window | HY IS / OOS | JNK IS / OOS | IG IS / OOS | raw HYG IS / OOS |
|---|---|---|---|---|
| first 3 days | 0.22 / 0.45 | 0.19 / 0.47 | −0.09 / −0.16 | 0.19 / 0.55 |
| last 3 days | 0.17 / −0.21 | 0.25 / −0.20 | −0.26 / −1.31 | 0.50 / 0.36 |
| last 3 + first 3 | 0.37 / 0.40 | 0.47 / 0.41 | −0.09 / −0.56 | 0.59 / 0.77 |
| pre-holiday | −0.01 / 0.38 | −0.06 / 0.40 | 0.08 / 0.19 | −0.07 / 0.49 |

The duration-stripped HY turn-of-month earns 1.0–1.6 %/yr at 0.2–0.5 Sharpe. Raw HYG
around the turn looks better (0.59 / 0.77), but only because it carries HYG's 3.4 years of
duration into the Treasury month-end window, which is the deployed strategy's
edge in another wrapper.

## 4. Verdict

**Failed.** ~320 cells. The credit premium has no calendar of its own that survives both
windows. What HY / LQD earn around the turn of the month is mostly the Treasury month-end
effect already deployed in TLT. The duration-stripped residual is ≤ 0.5 Sharpe, and it is
negative for IG.
