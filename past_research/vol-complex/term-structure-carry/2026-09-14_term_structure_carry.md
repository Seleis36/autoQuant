# term-structure-carry — VIX term-structure / roll-yield carry in the vol ETPs

**Status: Failed** against the brief's criterion (Sharpe ≥ 1.5). Best selection-free result:
short VIXY when VIX3M/VIX > 1, **net Sharpe 0.79** (2011-01 → 2026-09 @5 bp/side), 0.88 IS / 0.70 OOS.
Bootstrap 5–95 % band [0.39, 1.17]; P(true Sharpe > 1.5) ≈ 0.2 %. ~140 variants evaluated; none above 0.9
on a selection-free basis.

Date: 2026-09-14 · Asset class: vol-complex · Author: research agent (Fable 5.1)

## 1. Idea

The VIX futures curve is in contango ~80 % of the time; a constant-maturity 1-month long-vol ETP
(VXX / VIXY) pays that roll every day and has lost ~40–70 %/yr in calm years. The literature
(Simon & Campasano 2014 "The VIX futures basis"; Johnson 2017 "Risk premia and the VIX term
structure"; Cooper 2013 "Easy volatility investing"; Cheng 2019 "The VIX premium") says the slope
of the term structure and the variance risk premium (VIX − realised vol) predict the sign of
short-vol returns. The question was whether any conditioning of a short-VIXY (or long-SVXY)
position on daily-bar signals reaches a net Sharpe of 1.5 while being honest about the 2018-02,
2020-03, 2024-08 and 2025-04 gap days.

## 2. Data

All in the shared flat cache `data/`, daily, tz-naive, yfinance adjusted closes, cut at 2026-09-11
(the 2026-09-14 rows are a partial session):

| Series | Span | Note |
|---|---|---|
| `^VIX`, `^VIX3M`, `^VVIX` | 2010-01 → | VIX3M has ~40 missing days, forward-filled onto VIXY's index |
| `^VIX9D` | 2011-01 → | |
| `VIXY` | 2011-01-04 → | the tradable, 1× short-term futures; 3 945 bars |
| `SVXY`, `UVXY` | 2011-10 → | −1×/2× until 2018-02-27, −0.5×/1.5× after (verified by regression on VIXY: −0.99/1.99 then −0.50/1.48) |
| `VXX` | 2018-01-25 → | too short, unused |
| `VIXM` | 2011-01 → | mid-term (months 4–7) ETF, for the curve spread |
| `SPY` | 2010-01 → | hedge / trend filter |
| `data/CBOE_VX_futures_d.parquet` | 2013-01 → | **new**: every VIX futures contract's daily settle from CBOE's CDN (`fetch_vx_futures.py`), 30 795 rows. Pre-2013 files are not on the CDN. |

From the futures I rebuilt an SPVXSTR-style constant-maturity index; correlation with VIXY's daily
return is 0.94 over 2013–2026 and 0.99+ from 2021 (earlier CBOE settles are noisier). Signals derived
from it (front-month basis F1/VIX, F2/F1 roll, Simon-Campasano daily roll (F1−VIX)/TTM) correlate
0.56–0.94 with the VIX3M/VIX proxy.

**Timing caveat.** VIX-family indices close at 16:15 ET, VIXY at 16:00. A same-day signal has a
15-minute look-ahead on the days the slope crosses its threshold. Every headline number is
reported both same-day and with a 1-day lag; the lag costs ~0.2 Sharpe for the level rules.

## 3. Method

`research_lib.backtest` conventions: weight set at close *t* is applied to the *t→t+1* return;
cost charged on |Δw| at 5 bp/side for VIXY/SVXY/SPY, 10 bp for VIXM (thin). Sharpe annualised on
252 days. Split **fixed before any OOS number was looked at**: IS = 2011-01 → 2018-12 (contains
Volmageddon), OOS = 2019-01 → 2026-09. Gross exposure ≤ 1 unless stated.

## 4. Results

### 4.1 Baselines (VIXY, 5 bp)

| Rule | Sharpe full | IS | OOS | CAGR | MaxDD | Skew |
|---|---|---|---|---|---|---|
| short VIXY always | 0.63 | 0.71 | 0.56 | 20 % | −92 % | −1.7 |
| **short if VIX3M/VIX > 1, flat otherwise (reference)** | **0.79** | 0.88 | 0.70 | 33 % | −63 % | −1.3 |
| same, 1-day lag | 0.59 | 0.66 | 0.53 | 18 % | −86 % | −1.7 |
| sign(slope − 1) long/short ±1 | 0.71 | 0.80 | 0.62 | 28 % | −79 % | 0.0 |
| short if slope > 0.95 / 1.05 / 1.10 | 0.81 / 0.59 / 0.58 | | | | | |
| long SVXY if contango (−1× then −0.5×) | 0.77 | 0.86 | 0.70 | 27 % | −50 % | −1.2 |
| hysteresis in 1.0 / out 0.9 | 0.76 | 0.78 | 0.75 | 32 % | −81 % | |

Cost sensitivity is negligible (0.80 at 0 bp, 0.78 at 10 bp; turnover ≈ 12 one-way changes/yr).
Yearly Sharpe of the reference: 2012 1.85, 2017 2.46, 2023 2.04, but 2014 0.16, 2018 −0.83,
2022 −0.05, 2024 0.00, 2026 YTD −0.03.

### 4.2 Where the money comes from (the key finding)

P&L of the reference rule by VIX level at entry:

| VIX at entry | days | net return contributed | Sharpe of those days |
|---|---|---|---|
| < 13 | 696 | +0.02 | 0.02 |
| 13–16 | 1 117 | +1.28 | 0.54 |
| 16–20 | 1 075 | +1.05 | 0.37 |
| 20–25 | 566 | +2.88 | 1.91 |
| 25–35 | 397 | +1.76 | 1.53 |
| > 35 | 93 | +0.33 | 3.98 |

**Calm-market contango harvesting (VIX < 16, half the days) earns essentially nothing after its
tails; the strategy's return is the post-spike normalisation at VIX 20–35.** That is why every
"be more careful in calm markets" filter below fails to help: there is no calm-market edge to protect.

### 4.3 Sizing and hedging

| Variant | full | IS | OOS |
|---|---|---|---|
| × inverse-EWMA-vol scalar (target 15 %) | 0.52 | 0.66 | 0.37 |
| × 15/VIX | 0.66 | 0.83 | 0.49 |
| + SPY beta hedge (63-day rolling β ≈ −3.2, short SPY) | **−0.24** | 0.07 | −0.53 |
| + half beta hedge | 0.26 | 0.49 | 0.02 |
| unconditional short + full hedge | −0.01 | 0.26 | −0.24 |

Vol-scaling hurts because it sizes *down* exactly in the VIX 20–35 regime where the edge lives.
The beta-hedged carry is negative in both halves: over 2011–2026 the short-VIXY return is fully
explained by its ≈3× SPY beta (β × SPY drift ≈ 40 %/yr vs 33 % CAGR earned). There is no
SPY-orthogonal alpha in the daily-bar roll yield in this sample.

### 4.4 Gating with other vol-complex signals (short-only unless noted)

| Gate added to contango | full | IS | OOS |
|---|---|---|---|
| VIX < 10-day MA | 0.58 | 0.57 | 0.59 |
| VIX9D < VIX (short end also in contango) | 0.35 | 0.50 | 0.21 |
| VRP10 = VIX − RV10 > 0 | 0.42 | 0.60 | 0.24 |
| SPY > SMA200 / SMA100 / SMA50 | 0.56 / 0.49 / 0.32 | | |
| VVIX < 95 / > 95 | 0.71 / 0.41 | | |
| slope bucket [1.0,1.05) / [1.05,1.1) / [1.1,1.15) / [1.15,1.25) / >1.25 | 0.50 / 0.14 / 0.37 / 0.19 / 0.43 | | |
| VIX momentum k = 5/10/21/42/83 short-only | 0.67 / 0.38 / 0.47 / 0.60 / 0.66 | | |
| VRP 5/10/21 smoothed MA5, short-only | 0.65 / 0.70 / 0.52 | | |
| 5-flag ensemble score (slope, VRP10, VIX<MA10, SPY>SMA200, VVIX<95), weight = −score | 0.81 | 0.84 | 0.78 |
| spike-fade OR contango (VIX off 10-day high by 25 % & > 20) | 0.70 | 0.69 | 0.72 |
| long-vol tail leg (VIX9D > VIX & VIX > MA10) added | 0.66 | 0.72 | 0.62 |

The ensemble is the only thing marginally above the reference (0.81, with lower vol and −56 %
MaxDD) and it is stable IS/OOS, but it is nowhere near 1.5.

### 4.5 Actual futures basis (2013-05 → 2026-09, from the CBOE contract data)

| Signal | full | IS (2013–18) | OOS |
|---|---|---|---|
| VIX3M/VIX > 1 (reference, same window) | 0.70 | 0.71 | 0.70 |
| F1/VIX − 1 > 0 / 0.02 / 0.05 / 0.10 | 0.48 / 0.60 / 0.50 / −0.08 | | |
| basket basis > 0.05 / 0.10 | 0.55 / 0.54 | 0.91 / 1.14 | 0.30 / 0.14 |
| F2/F1 − 1 > 0 / 0.05 | 0.54 / 0.42 | | |
| Simon-Campasano daily roll > 0.05, short-only | 0.70 | **1.20** | **0.36** |
| daily roll > 0.05 short / < −0.05 long | 0.37 | 0.88 | 0.06 |

The published daily-roll rule reproduces its high in-sample Sharpe and then halves out of sample.
The exact basis is no better than the free VIX3M/VIX proxy.

### 4.6 Front-vs-mid curve spread (VIXY vs VIXM)

Dollar-neutral −1 VIXY / +k VIXM harvests the faster front-month decay with little SPY beta:
k = 1.5: 0.66 full (0.22 IS / 1.04 OOS); k = 2: 0.48 (−0.27 / 1.10); two-sided sign(slope) version
0.24 / −0.21; vol-scaled −0.22. The 2011–2013 mid-term decay kills the IS half; not stable.

### 4.7 Calendar legs (event study, then selection-free re-test)

VIXY returns by trading-day offset around FOMC, monthly opex and VIX futures expiry show several
|t| ≈ 2 cells with the same sign IS and OOS (short the day before FOMC, long the day after, short the
two days before VIX expiry, short the day after opex). Stacked on 0.5× contango carry these give
**1.10 full / 1.29 IS / 0.91 OOS** — the best full-sample number of the session, and it is
data-mined: the legs were picked from 45 offsets on the full sample. Selecting legs on IS only
(|t| ≥ 2) gives IS 1.47 → **OOS 0.22**; with |t| ≥ 1.5, 1.61 → 0.72. Expanding-window yearly
re-selection 2015–2026: calendar-only **0.12**, calendar + carry **0.58** vs carry alone **0.74** in the
same window. The calendar legs are noise; they make carry worse when chosen honestly.

### 4.8 Others tried

Weekday (Monday-held return −32 bp/day, Thursday +10 bp, not exploitable after gating: best 0.60);
next-day reversal after |VIXY move| > 5/10/15 % (0.41 / 0.09 / −0.05); short-both-leveraged-ETP
decay harvest rejected analytically (daily-rebalanced short of a +1.5× and −0.5× pair has zero expected
arithmetic P&L before borrow; the "decay" is a log-return artefact).

### 4.9 Statistics for the reference rule

Block bootstrap (21-day blocks, 2 000 draws) of the full-sample Sharpe: 5–95 % **[0.39, 1.17]**,
P(Sharpe > 1) = 0.18, P(Sharpe > 1.5) = 0.002. Newey-West t = 3.6. Deflated Sharpe probability
(Bailey–López de Prado) 0.999 for one trial, **0.65 after ~140 trials**.

## 5. Conclusion

Short-VIXY carry conditioned on the term structure is a real but modest, fat-tailed, SPY-beta-laden
premium: ~0.8 Sharpe, −63 % drawdown, −1.3 skew, and the edge is concentrated in post-spike
normalisation, not calm-market roll. Nothing in daily-bar vol-complex data (slope, short-end slope,
VRP, VVIX, momentum, exact futures basis, calendar events, front/mid spread, hedging, sizing) lifts it
to 1.5 on a selection-free basis. The binding constraint is structural: the 15 % of days with
VIX > 20 provide the return and the same regime provides the gap risk, so any filter that avoids
the risk also forfeits the return. **Do not spend another session re-conditioning short-vol carry
on daily bars.** Untested directions that would need different data: intraday (the 16:00–16:15
ETP-vs-NAV gap and end-of-day leveraged-ETP rebalancing flow), options-based (SPX variance swaps vs
VIX futures), and VIX futures beyond the ETPs (calendar spreads with margin, not dollar-neutral ETFs).

## 6. Files

* `code/vol-complex/term-structure-carry/`: `fetch_data.py`, `fetch_vx_futures.py` (CBOE contract
  history → `data/CBOE_VX_futures_d.parquet`), `tsc_lib.py` (features, multi-leg backtest),
  `explore01_baseline.py` … `explore08_selection_free.py`, `final.py`, `strategy.py` (reference rule,
  `target_weight(vixy_close, vix, vix3m, threshold=1.0, size=1.0, lag=0)`), `vx_curve.parquet`,
  `reference_weights_and_returns.csv`, `walkforward_returns.parquet`.
* Figures in this folder: `01_equity.png`, `02_drawdown.png`, `03_yearly_sharpe.png`,
  `04_vix_level_attribution.png`.
* No alpha spec was written: the idea does not meet the criterion.
