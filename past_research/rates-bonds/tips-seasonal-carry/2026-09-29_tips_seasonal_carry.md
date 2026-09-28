# tips-seasonal-carry — is the known TIPS inflation accrual priced?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

A TIPS holder's principal is indexed to a **reference CPI that lags by three months**: on
day k of month M it interpolates linearly from CPI-U NSA of month M−3 (on the 1st) to that of
M−2 (on the 1st of M+1). So the inflation accrual earned over month M,

    a(M) = CPI_NSA(M−2) / CPI_NSA(M−3) − 1,

is **known exactly** once CPI(M−2) is published, around the middle of M−1 — before month M
starts. NSA CPI has a big seasonal (Jan–May prints high, Oct–Dec low or negative), so a(M)
swings from about −15 bp (Jan/Feb) to +50 bp (Mar–May) per month (table in §3) while the
nominal alternative's carry does not. If real yields do not fully offset that known carry,
TIPS vs duration-matched nominals has a free, seasonal, perfectly-timed return. Desk
practice says the carry is priced ("seasonally-adjusted breakevens"; Ejsing-Garcia-Werner
2007, ECB 2007); the question is how completely, at the ETF level.

## 2. Data

* ETFs: TIP (2003-12, `TIP_d_pre2010` spliced), SCHP (2010-08), STIP (2010-12), VTIP (2012-10),
  LTPZ; nominal hedges IEF, IEI (2007, `IEI_d_pre2010`), SHY, VGSH, TLT. `00_fetch.py`.
* FRED `CPIAUCNS` (the TIPS reference index; the NSA series is not revised), `T5YIE`,
  `T10YIE` (daily market breakevens, not revised), `DFII5/10`.
* Traded object: monthly hedged excess `x(M) = r_TIPS(M) − b·r_nominal(M)`, b = trailing
  252-day OLS beta at the last close of M−1.

## 3. Round 1 — is the seasonal part priced? — `01_event.py`, `01_event_output.txt`

Regression of x(M) on the seasonal part of the known accrual, `a(M) − mean(a over the prior
12 months)`. Slope 1 = unpriced; slope 0 = fully priced.

| Pair | sample | slope | t | monthly vol of x |
|---|---|---|---|---|
| TIP − IEF | 2005-2026 | 0.21 | 1.16 | 1.17 % |
| TIP − IEI | 2008-2026 | 0.28 | 1.26 | 1.29 % |
| SCHP − IEI | 2011-2026 | 0.23 | 1.15 | 0.90 % |
| STIP − SHY | 2012-2026 | **0.07** | 0.61 | 0.50 % |
| VTIP − VGSH | 2013-2026 | 0.16 | 1.20 | 0.54 % |
| LTPZ − TLT | 2011-2026 | 0.59 | 1.28 | 2.11 % |

**The market prices 75–95 % of the known seasonal carry**, most completely in the short TIPS
(STIP, slope 0.07) where it matters most for yield. At a slope of ~0.2 and a seasonal SD of
0.33 %/month, the unpriced part is ~7 bp/month against 0.5–1.2 % of monthly noise:
Sharpe ≈ 0.1–0.2 before costs. Calendar-month profile (STIP−SHY, bp): accrual
−15/−12/+41/+48/+51/+35/+35/+30/+8/+14/+20/+11 Jan→Dec; hedged excess
+21/+24/+7/+25/+2/−3/+24/−4/−23/+15/+1/+1 — no relation.

## 4. Round 2 — inflation carry and momentum as breakeven timers — `02_inflation_carry.py`

Re-framing: maybe breakevens don't under-react to the seasonal but to the *level* or *trend*
of inflation. Five signals known at the last close of M−1, with the direction fixed by the
hypothesis (positive = long TIPS vs nominals):

* `carry1` = 12·a(M) − BEI (next month's known accrual annualised minus breakeven);
* `carry3` = 4·Σa(M−2..M) − BEI;
* `yoy_gap` = known YoY CPI − BEI;
* `mom6` = 6-month change in known YoY CPI (inflation momentum);
* `bei_mom3` = 3-month breakeven change (price momentum control).

Books: sign(s) or clip(z60, ±1), monthly, 3 bp/side on both legs. Split fixed in advance:
IS 2004–2015, OOS 2016–2026. 5 signals × 2 modes × 5 pairs × 2 breakeven tenors = 100 cells.

| Signal (TIP−IEF, BEI5, sign) | IS | OOS | FULL | FULL ex 2021-22 |
|---|---|---|---|---|
| carry1 | 0.41 | 0.03 | 0.26 | 0.24 |
| carry3 | −0.87 | 0.04 | −0.50 | −0.59 |
| yoy_gap | −0.52 | −0.25 | −0.41 | −0.44 |
| mom6 | **−0.78** | **−0.40** | −0.62 | −0.80 |
| bei_mom3 | 0.36 | 0.19 | 0.29 | 0.26 |

On the short-TIPS pairs (STIP−SHY, VTIP−VGSH) `bei_mom3` is the only positive family: 0.40–0.67
IS, 0.26–0.29 OOS. Medians over the BEI10 variants: every signal ≤ 0.04 OOS.

The hypothesised direction fails everywhere OOS (≤ 0.08 for carry1, negative for yoy_gap and
mom6). The one sizeable pattern runs **the other way**: fading inflation momentum — long
breakevens after inflation *fell* — is +0.78 IS / +0.40 OOS on TIP−IEF, +0.73 / +0.28 on
TIP−IEI, but +0.43 / +0.24 on STIP−SHY and ~0 on VTIP−VGSH. It was not a pre-registered
direction, it is carried by the 2008 and 2020 breakeven collapses and recoveries, and it
reaches 0.40 OOS only on the longest-duration pair. Not pursued as a Working claim.

## 5. Verdict

**Failed.** ~120 cells. The seasonal inflation carry is almost entirely priced into TIPS real
yields (slope 0.07–0.28 of 1.0), and neither inflation carry nor inflation momentum times
breakevens in the hypothesised direction out of sample. The binding constraint is market
efficiency, not costs: the effect a desk would trade is ≈ 7 bp/month against ≈ 1 %/month of
breakeven noise.

## 6. Reusable

* `01_event.py: accrual_monthly()` — the known TIPS accrual per month from CPI-U NSA, with
  one/two months of look-ahead that is genuinely public.
* TIPS ETF caches: STIP, VTIP, SCHP, LTPZ, IEI, VGSH (`data/`, 2010+), `TIP_d_pre2010`,
  `IEI_d_pre2010`; FRED `CPIAUCNS`, `T5YIE`, `T10YIE`, `DFII5`, `DFII10`.
