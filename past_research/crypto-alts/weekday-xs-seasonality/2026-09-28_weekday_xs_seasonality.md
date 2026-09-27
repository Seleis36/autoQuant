# weekday-xs-seasonality — same-weekday cross-sectional seasonality in liquid alts

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Failed

## 1. Idea

Long, Zaremba, Demir, Szczygielski & Vasenin ("Seasonality in the cross-section of cryptocurrency
returns", *Finance Research Letters* 35, 2020) find on 151 coins in 2016-19 that a coin's average
past return on the same weekday predicts its return on the next such weekday. The effect is not
subsumed by momentum, size, beta, idiosyncratic risk or liquidity. Heston-Sadka (2008) is the
equity analogue, where the usual explanation is recurring flows, e.g. exchange- or
region-specific weekly cycles (Asian weekend retail, US weekday institutions). Question: does it
hold on the liquid PIT top-20 alts, and can it pay 10 bp/side?

## 2. Setup
PIT top-20 universe, IS 2018-22 / OOS 2023-26, 10 bp/side (`code/crypto-alts/shared/study.py`).
Returns are XS-demeaned within the universe. Weight set at close D for day D+1 using past
same-weekday returns only (shifts 7j−1, j ≥ 1). Dollar-neutral linear-rank or tercile weights.

## 3. Results

**Same-weekday rolling mean, L ∈ {4, 8, 13, 26, 52} weeks (`01_screen.py` → `screen_01.csv`, 20 books).**
Daily rank IC vs next-day XS return: IS −0.007…+0.008, OOS +0.002…+0.009, full-sample t ≤ 1.1.
Gross (0 bp) Sharpe −0.03…0.64 (best L13 terciles 0.64 IS / 0.63 OOS gross), with turnover
315-360×/yr, so 10 bp costs 32-36 %/yr. **Net Sharpe −1.6 to −2.9 in every cell.**

**Re-framings (`02_reframe.py` → `reframe_02.csv`, 14 books):**

| Variant | turnover | gross full / IS / OOS | net @10 bp full |
|---|---|---|---|
| weekend-minus-weekday coin seasonality, L 13/26/52/104 w | 145-170×/yr | 0.49/0.53/0.43 at L13; −0.2…0.1 elsewhere (sign flips with L) | −0.70…−1.38 |
| expanding-window same-weekday mean (all history, ≥ 26 obs) | 327× | 0.22 / 0.37 / 0.01 | −2.16 |
| same, on BTC-beta-residual returns | 309× | 0.34 / 0.49 / 0.11 | −1.92 |
| turn-of-month (days 1-3) coin seasonality, expanding | 36× | −0.02 / 0.04 / −0.09 | −0.31 |

## 4. Verdict

**Failed.** There is no measurable same-weekday seasonality in the liquid alt cross-section
(IC ≈ 0, t < 1.2 in every lookback). The gross numbers are noise around zero whose sign changes
with the lookback, and the signal has to rebalance daily, which costs ~30 %/yr at 10 bp. Pooling
into weekend/weekday halves the turnover and still does not produce a stable sign. The published
effect (2016-19, 151 mostly small coins) most likely lives in illiquid names or has decayed.
Variants evaluated: 17 signals × 2 cost levels (34 books).

## 5. Files
`code/crypto-alts/weekday-xs-seasonality/01_screen.py`, `02_reframe.py`, `screen_01.csv`, `reframe_02.csv`.
