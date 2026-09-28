# ust-cot-positioning — CFTC positioning in Treasury futures as a duration timer

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

Contrarian COT positioning is the one mechanism that has worked in two other asset classes
of this repo: `fx-majors/cot-positioning` (fade speculators' net share of OI in CME currency
futures, 0.80 / 0.64 OOS) and `vol-complex/vix-cot-positioning` (asset-manager crowding in VIX
futures, 1.00 / 0.96 OOS). The Treasury futures complex is the largest and best-reported
futures market in the CFTC data, with 40 years of legacy history (1986+) and 20 years of the
Traders-in-Financial-Futures split (2006+). The question: does positioning in the 2y / 5y /
10y / bond futures predict the next 1–13 weeks of duration returns?

Prior on mechanism: speculators who crowd one side get squeezed (contrarian); asset managers
using futures as duration substitutes are slow-moving demand (possibly *follow*); dealers are
the liquidity providers (fade their counterparties = follow dealers?). Post-2018, leveraged
funds' positions are dominated by the cash-futures **basis trade** (short futures / long cash
on repo), which is a relative-value position, not a directional view — a known structural
break that the design must survive.

## 2. Data

* `code/rates-bonds/shared/fetch_cot_ust.py` (new, reusable) → `data/CFTC_COT_legacy_ust_w.parquet`
  (1986-01 → 2026-09-22; 2y from 1990, 5y from 1988, ultra-10y 2016+, ultra-bond 2010+) and
  `data/CFTC_COT_tff_ust_w.parquet` (2006-06 → 2026-09-22). Release timing copied from the
  FX fetcher: as-of Tuesday, public Friday 15:30 ET (Monday in holiday weeks; shutdown
  backlogs 2013 / 2018-19 / 2025 released on their actual dates). A daily ETF bar stamped D
  uses only reports whose release falls on a calendar date **strictly before D** — a normal
  report first trades at Monday's close.
* Returns: synthetic 10y constant-maturity excess return (FRED CMT, `rates-carry-trend/curve_lib.py`,
  re-exported by the new `code/rates-bonds/shared/rb_data.py`) and IEF excess of the 3m bill
  (IEF 2002-07+ via the `*_pre2010` splice).

## 3. Method and splits (fixed before any number)

* **Legacy groups** (non-commercial, commercial, non-reportable): IS **1990–2009** on synthetic
  10y, OOS **2010–2026** on IEF and synthetic 10y.
* **TFF groups** (leveraged funds, asset managers, dealers, other reportables): IS
  **2006-06–2017**, OOS **2018–2026** on IEF.
* Signals on the weekly report grid: `lvl` = z-score of net share of OI; `chg` = z-score of
  the dh-report change. Aggregation across 2y/5y/10y/bond by equal-weighted mean (round 1)
  or DV01-weighted net risk share (round 2).
* Book: weekly re-set, linear `clip(z/2, ±1)` or extremes-only `sign(z)·1{|z|>1}`, 2 bp/side.
  Direction (follow/fade) chosen on IS and frozen for OOS.

## 4. Round 1 — `01_screen.py`, `01_screen_output.txt`

Spearman ICs vs forward 1/4/13-week returns, aggregate and per tenor, plus linear books
(52 book cells, 312 IC cells). Nothing exceeds |IC| 0.13 in-sample at 4 weeks. The
aggregate books (follow direction; contrarian is the negative):

| Group / signal | IS (syn10) | OOS (syn10) | IS (IEF) | OOS (IEF) |
|---|---|---|---|---|
| legacy commercials, 4w change | −0.41 | −0.32 | −0.49 | −0.31 |
| legacy non-commercials, 4w change | +0.26 | +0.14 | +0.23 | +0.10 |
| legacy non-commercials, level | +0.10 | −0.16 | +0.17 | −0.17 |
| TFF lev funds, level | +0.02 | −0.39 | +0.05 | −0.44 |
| TFF lev funds, 4w change | −0.64 | +0.43 | −0.63 | +0.37 |
| TFF asset managers, level | −0.06 | +0.09 | −0.06 | +0.10 |
| TFF dealers, 4w change | −0.08 | −0.46 | −0.10 | −0.47 |
| TFF other reportables, level | +0.13 | +0.42 | +0.16 | +0.47 |

The TFF leveraged-fund and asset-manager signals **change sign** across the 2018 split, at
13-week horizons most visibly (lev-fund level IC +0.13 IS → −0.28 OOS; asset-manager level
−0.07 → +0.25). That is the basis-trade regime: since ~2018 leveraged funds' net short and
asset managers' net long grow together as mirror images of cash-futures arbitrage, and the
"crowding" they measure is not a directional bet.

## 5. Round 2 — `02_refine.py`, `02_refine_output.txt`, `02_refine.csv`

216 configurations: DV01-weighted aggregation × {level, change over 1/2/4/8/13 reports} ×
z-window {52, 156, 260} × {linear, extremes-only} × 6 groups. Direction picked on IS.

| | legacy (IS 1990-09 → OOS 2010-26) | TFF (IS 2006-17 → OOS 2018-26) |
|---|---|---|
| best IS config | fade commercials' 4w change, z156, extremes: **0.59** | fade lev funds' level, z52, extremes: **0.72** |
| its OOS on IEF | **−0.00** | **−0.34** |
| median OOS of the top-10 IS | −0.00 | **−0.55** |
| median OOS of all configs | 0.00 | −0.26 |
| Spearman(IS rank, OOS rank) | −0.09 | **−0.34** |

The TFF table is a clean regime flip: the whole "fade leveraged-fund changes" family is
+0.6 to +0.7 in 2006-2017 and −0.5 to −0.67 in 2018-2026. The legacy family has no
in-sample ranking power at all out of sample.

## 6. What was not done, and why

* No regime-switch rule ("fade lev funds before 2018, follow after"): the switch date would
  be chosen from the OOS result, which is exactly the post-hoc selection the acceptance
  rules forbid.
* No basis-trade unwind timer (very large lev-fund shorts → tail sell-off risk, e.g. March
  2020, April 2025): two or three events in the sample, not testable.

## 7. Verdict

**Failed.** ~270 cells (52 round-1 books, 216 round-2 books), no configuration selected on IS
has a positive OOS Sharpe above 0.2; the best consistent-sign family (fade commercials'
4-week change) is 0.3–0.5 IS and 0.2–0.3 OOS, i.e. noise-level. The mechanism that works in
FX and VIX futures does not transfer to Treasury futures, because positioning there is
dominated by hedging and relative-value (basis) trades rather than by directional
speculation.

## 8. Reusable

* `code/rates-bonds/shared/fetch_cot_ust.py` — Treasury-futures legacy + TFF COT with
  release-date availability, `net_share`, `on_daily_rows` (US-close convention).
* `code/rates-bonds/shared/rb_data.py` — ETF closes with the pre-2010 splice, synthetic CMT
  returns, `stats_table`.
