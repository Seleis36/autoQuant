# rebalance-pressure-bonds — 60/40 rebalancing pressure as a Treasury timer

**Date:** 2026-10-10 · **Asset class:** rates-bonds · **Status: Failed**

**Result.** Harvey, Mazzoleni and Melone (2025) replicate here: after stocks become
overweight in a drifting 60/40 fund, stocks-minus-bonds falls the next day (t −3 in 1990-2009
and again in 2010-2026). But that is an equity effect. The Treasury leg on its own has no
stable sign — the paper's threshold signal predicts bonds *up* when the stock-bond correlation
is negative and bonds *down* (t −2.8) when it is positive. The pre-registered bond-only books
are at most 0.24 net in the design sample and 0.2-0.65 out of sample; the best re-framed one
is 0.50 in sample and 0.00 after. The one bond-specific
regularity is a give-back on the first session of the month (bonds fall after a month in
which stocks out-performed, t ≈ −2 in each of three eras, clean against placebos), worth
0.2-0.5 net Sharpe on twelve trading days a year.

Code: `code/rates-bonds/rebalance-pressure-bonds/`

## 1. Idea

Pension and target-date funds rebalance to fixed weights on thresholds and on calendar dates.
When stocks have out-run bonds they sell stocks and buy bonds; the paper measures a 17 bp
next-day fall in equities and a trading Sharpe above 1 on S&P futures minus 10y futures,
1997-2023. If bond buying is half of that trade, the Treasury leg alone should be timeable —
and the deployed `treasury-flow-calendar` month-end long could be sized by who is overweight.

The earlier `cross-asset-tsmom` tested past equity returns on bonds at monthly horizons and
failed. This is the daily, flow-dated version.

## 2. Signals and data (`rp_lib.py`)

A notional 60/40 fund's equity weight drifts with the S&P 500 and a 10y Treasury.
* **Threshold:** the fund trades back to 60 % when |w − 60 %| ≥ δ; the signal is the average
  pre-trade deviation over δ = 0 … 2.5 %.
* **Calendar:** the fund trades back at the last close of the month; the signal is the
  month-to-date deviation, used when the next session is among the last N of the month.

S&P 500 price index 1982-2026; synthetic 10y constant-maturity total return 1982-2026 for the
drift; traded bond = synthetic 10y before 2010, IEF and TLT after. Design sample 1990-2009,
test sample 2010-2026, 2 bp per side. The paper's own sample (1997-2023) covers most of the
test window, so only 2024-26 is post-publication.

Timing caveat on the synthetic bond: CMT yields are a 15:30 ET mark, so its "next-day" return
starts 30 minutes before the stock close that builds the signal. ETF tests have no overlap.

## 3. Event study (`01_event_study.py`)

Slope of the next session's return, in bp per percentage point of equity overweight (t):

| target | signal | 1990-2009 | 2010-2026 | 2024-26 | 1982-1996 |
|---|---|---|---|---|---|
| stocks − bonds | threshold | −17.0 (−3.3) | −30.3 (−2.9) | −5.0 (−0.3) | +1.8 (0.3) |
| stocks − bonds | calendar, last 5 | −21.2 (−3.2) | −13.8 (−3.9) | −7.2 (−0.9) | −3.2 (−0.4) |
| S&P 500 | threshold | −17.0 (−3.7) | −25.9 (−2.9) | −6.2 (−0.4) | −9.0 (−1.8) |
| **10y bond** | threshold | **0.0 (0.0)** | +4.4 (1.9) | −1.3 (−0.3) | −10.8 (−2.7) |
| **10y bond** | calendar, last 5 | +1.9 (1.3) | +1.8 (1.2) | −2.5 (−0.7) | −2.9 (−1.6) |
| **10y bond** | month-end deviation → first session | −6.5 (−2.1) | −10.7 (−3.7) | n/a | −9.7 (−1.3) |
| IEF | threshold | +6.2 (2.6)¹ | +5.5 (2.6) | −1.5 (−0.4) | |
| TLT | threshold | +8.9 (2.0)¹ | +13.3 (2.7) | −5.5 (−0.6) | |

¹ 2002-07 → 2009 only.

The paper's left-hand side replicates. All of it sits in the stock leg. The bond slope is
zero in the design sample, positive in 2002-2021 and negative before 1997.

By trailing 250-session stock-bond correlation (`03_reframings.py`, 1983-2026): threshold →
next-day bond slope +3.3 (t 1.6) when the correlation is below −0.2, +3.6 (1.7) between ±0.2,
**−10.7 (−2.8)** above +0.2. The stock slope is negative in all three (−24.9, −14.9, −11.2).
So the bond "signal" is the stock reversal seen through the correlation of the day — the same
regime dependence that broke every earlier duration timer in this folder.

## 4. Bond-only books (`02_books.py`, net Sharpe at 2 bp; gross in the CSV)

| book | syn10 1990-2009 | IEF 2010-26 | TLT 2010-26 | IEF / TLT 2022-26 |
|---|---|---|---|---|
| A threshold, daily, scaled | −0.27 | 0.31 | 0.41 | −0.06 / 0.20 |
| A threshold, daily, sign | −0.28 | 0.37 | 0.43 | 0.08 / 0.25 |
| B calendar, last 5, scaled | −0.17 | 0.37 | 0.61 | 0.46 / 0.79 |
| B calendar, last 5, sign | −0.36 | 0.34 | 0.65 | 0.19 / 0.49 |
| B calendar, last 3, sign | −0.39 | 0.23 | 0.47 | −0.30 / −0.11 |
| C month-start reversal, first session, sign | **0.24** (IS-best) | 0.21 | 0.28 | −0.02 / −0.29 |
| C month-start, 3 sessions, sign | 0.03 | 0.29 | 0.33 | 0.27 / −0.16 |

Nothing clears 0.3 in the design sample. A and B are negative there and positive after 2010,
which is the correlation regime again, not a result.

## 5. Re-framings (`03_reframings.py`)

**Month-start give-back.** First-session bond return by the sign of the month-end deviation:

| | stocks overweight | bonds overweight | t of difference |
|---|---|---|---|
| syn10 1982-89 | −0.8 bp | +22.3 bp | −2.0 |
| syn10 1990-2009 | −7.3 bp | +8.8 bp | −2.1 |
| syn10 2010-2026 | −8.8 bp | +7.1 bp | −2.0 |
| IEF 2010-2017 / 2018-2026 | −11.9 / −1.7 | +7.0 / +9.4 | −2.0 / −1.0 |
| TLT 2010-2026 | −11.2 bp | +15.7 bp | −1.7 |

Same sign everywhere; a 16 bp swing on one day a month. As a book (net, IS / OOS):

| variant | syn10 | IEF | TLT |
|---|---|---|---|
| sign | 0.24 / 0.27 | 0.26¹ / 0.21 | 0.42¹ / 0.28 |
| scaled, z clipped at ±1 | 0.30 / 0.52 | 0.36¹ / 0.44 | 0.43¹ / 0.47 |
| scaled, z clipped at ±2 | 0.29 / 0.57 | 0.37¹ / 0.48 | 0.46¹ / 0.46 |
| only \|z\| > 1 | 0.22 / 0.60 | 0.31¹ / 0.51 | 0.35¹ / 0.41 |
| quarter-ends only | −0.20 / 0.50 | −0.64¹ / 0.36 | −0.61¹ / 0.42 |
| non-quarter month-ends | 0.50 / 0.00 | 0.89¹ / 0.02 | 1.01¹ / 0.07 |
| placebo: second session only | −0.61 / −0.08 | −0.49¹ / −0.12 | −0.54¹ / 0.01 |
| placebo: session 10 | −0.23 / −0.24 | −0.29¹ / −0.26 | −0.37¹ / −0.17 |

The effect is real in sign and specific to the first session, and too small: 12 sessions a
year at about 8 bp each, less four basis points of round trip. The best design-sample variant
(non-quarter month-ends, 0.50) is 0.00 in the test sample, and the best test variant (0.60)
is 0.22 in the design sample. Quarter-ends are not reliably stronger.

**Conditioning the deployed month-end long.** Unconditional long over the last three
sessions (IEF): 0.79 / 1.00. Only after stocks out-performed: 0.36 / 0.94. Only after bonds
out-performed: 0.72 / 0.40. The halves disagree on which condition helps; the month-end
effect is index extension, not rebalancing, and should stay unconditional.

**Adding the month-start leg to the deployed sleeve (TLT, 2 bp):** 1.32 → 1.34 (full leg) or
1.37 (half) in 2010-26; 0.63 → 0.79 in 2002-09; 1.65 → 1.50 in 2018-26. Not worth a change
to a live strategy.

**Reference, cross-asset (not a rates-bonds book):** SPY − IEF on the paper's signals, 2 bp
per leg: threshold 0.49 (2002-09) / 0.32 (2010-26) / −0.72 (2024-26); calendar last five
0.81 / 0.54 / 0.42. Well short of the paper's futures Sharpe and weak after publication. A
lead for the equity-index researcher, if anyone.

## 6. Why it fails here

Rebalancing flow is small against the Treasury market and large against nothing in
particular; what moves is the equity leg. The bond leg inherits a sign from the stock-bond
correlation, which has flipped three times in the sample (1997, 2021-22). The only
correlation-free piece — bonds give back month-end buying on the first session — is a
12-day-a-year trade worth a few basis points.

## 7. Variants

180 event-study regressions (6 signals × 6 targets × 5 periods), 48 book cells (16 books ×
3 instruments), ~75 re-framing cells. Reusable: `rp_lib.py` (drift signals, NYSE-aware
days-left-in-month, Newey-West slope).
