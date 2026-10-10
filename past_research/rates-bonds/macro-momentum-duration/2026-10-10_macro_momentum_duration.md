# macro-momentum-duration — point-in-time growth and inflation momentum as a duration timer

**Date:** 2026-10-10 · **Asset class:** rates-bonds · **Status: Failed**

**Result.** Growth momentum (unemployment, payrolls, industrial production, real retail sales,
housing starts, sentiment) and inflation acceleration (CPI, core PCE), each built only from
the data vintage that was public on the decision date, do not time the 10-year Treasury.
Short duration when macro momentum is positive: best design-sample (1996-2009) Sharpe 0.25,
test-sample (2010-2026) Sharpe of that cell −0.06 on the synthetic 10y and −0.10 on IEF.
Across the 20 cells of the fresher-data run the design/test rank correlation is −0.02, and no
cell in either run has the same sign with |Sharpe| above 0.3 in both halves. Timing the credit premium on growth momentum is
negative in both halves.

Code: `code/rates-bonds/macro-momentum-duration/`

## 1. Idea

"Macro momentum" (Brooks, AQR 2017): bonds do badly when growth and inflation are
accelerating and well when they are slowing; a trend signal on the macro data itself, not on
prices. Every earlier duration timer in this folder was built on prices or positioning and
flipped sign at 2015 / 2018 / 2022. A signal on the economy should not depend on the
stock-bond correlation regime — and it should have been short duration in 2021-22.

No earlier rates-bonds idea used the vintage store.

## 2. Point-in-time construction (`mm_lib.py`)

At each decision date the signal reads, for every series, the ALFRED vintage that was public
then: the whole history as known that day, so revisions and release lag are both respected.
For each series the k-month change (k = 3, 6, 12) of the latest published value is z-scored
against the history of the same change **inside that vintage** (1970 onward). No statistic
mixes vintages.

    growth    = mean z of −Δ unemployment, Δ ln payrolls, Δ ln industrial production,
                Δ ln real retail sales, Δ ln housing starts, Δ sentiment
    inflation = mean z of the change in k-month CPI and core-PCE inflation against the k
                months before (acceleration)
    macro     = (growth + inflation) / 2 ;   position = −clip(macro, −1, 1)

The shared vintage store began in 2010. For a design sample that is also point-in-time I
backfilled monthly vintages to 1996-01 for CPI, payrolls, unemployment, industrial production
and housing starts (sentiment from 1998-08, core PCE from 2000-08, retail sales from 2001-07,
their first vintages; they join the averages when available).

Design sample 1996-06 → 2009-12 on the synthetic 10y excess return; test sample 2010-01 →
2026-09 on IEF and TLT in excess of cash; 2 bp per side.

## 3. Month-end decisions (`01_macro_timer.py`)

Decision at month-end with the vintage of the 1st of that month. The average datum is
**85 days old** at the decision — the price of the monthly vintage grid.

| signal | syn10 1996-2009 | syn10 2010-26 | IEF 2010-26 | TLT 2010-26 |
|---|---|---|---|---|
| macro, 3 m | 0.07 | −0.01 | −0.04 | −0.12 |
| macro, 6 m | −0.10 | −0.15 | −0.15 | −0.18 |
| macro, 12 m | −0.03 | −0.02 | −0.01 | −0.07 |
| growth only, 3 / 6 / 12 m | 0.13 / 0.08 / 0.17 | 0.01 / −0.17 / −0.24 | 0.00 / −0.19 / −0.23 | −0.01 / −0.11 / −0.28 |
| inflation only, 3 / 6 / 12 m | −0.05 / −0.42 / −0.32 | 0.00 / −0.09 / 0.09 | −0.03 / −0.08 / 0.08 | −0.10 / −0.14 / 0.02 |
| macro sign, 6 m (design-best) | **0.18** | −0.16 | −0.15 | −0.19 |
| average of 3 / 6 / 12 m | −0.02 | 0.12 | 0.10 | 0.02 |
| long-only benchmark | 0.43 | 0.09 | 0.16 | 0.11 |

Predictive slopes (next-month 10y excess return per 1 z): 6-month growth +13 bp (t 0.5) in
the design sample and −2 bp (t −0.2) in the test sample; 6-month inflation acceleration
+30 bp (t 1.5) and −6 bp (t −0.3). In the design sample the sign is the opposite of the
hypothesis.

The 2021-22 case the idea was built for: the composite's 2020-26 Sharpe on syn10 is −0.09
(3 m), 0.20 (6 m) and 0.08 (12 m) — the right sign for two of three and far too small.

**Credit premium** (HYG − β × IEF, long when growth momentum is positive, IS 2008-17 / OOS
2018-26): −0.32 / −0.10, −0.32 / −0.54, −0.35 / −0.55 for 3 / 6 / 12 months, against 0.83 / 0.27
for holding the premium.

## 4. Re-framings (`02_timely.py`)

1. **Fresher data.** Decide at the close of the *second* session of each month with the
   vintage dated the 1st of that month (everything published through the 1st, one session of
   margin). Data age falls from 85 to 56 days. Result: macro 3 / 6 / 12 m → 0.12 / −0.10 / 0.03
   in design, −0.03 / −0.33 / −0.12 in test.
2. **Macro news** — the month-on-month change in each momentum z-score (what the latest
   releases added). Design-best cell of the whole study: news in 3-month growth, 0.25 →
   −0.06 (syn10), −0.10 (IEF), 0.00 (TLT).
3. **Inflation regime** (CPI year-on-year above / below 3 %, as known at the decision):
   6-month growth in high inflation 0.39 → 0.08; composite in high inflation 0.38 → −0.20;
   everything else negative in at least one half.

Design/test rank correlation over the 20 cells of this script: −0.02. No cell has the same
sign and |Sharpe| > 0.3 in both samples.

## 5. Why it fails

My reading, consistent with the signs above but not tested here: monthly US macro releases
are priced on the day, so what a point-in-time signal still holds two months later is a
trend the market has already extrapolated, and whether that trend is good or bad for bonds
depends on how the Fed is reacting at the time (positive slope in 1996-2009, none after). The published macro-momentum results rest on
a 30-country cross-section and on forecast revisions, neither of which a single-country
realised-data timer has.

## 6. Variants

15 month-end timer cells × 3 instruments, 3 credit cells, 20 second-session cells, 8 regime
cells: 46 configurations. Reusable: `mm_lib.Vintages` (indexed `as_of` over the vintage
store, about 100× faster than repeated `fetch_alfred.as_of`) and the 1996-2009 vintages now
in `data/vintages/`.
