# intl-rebalance-flow — month-end US-vs-international rebalancing pressure

**Asset class:** `global-equity-etf` · **Short name:** `intl-rebalance-flow` · **Date:** 2026-11-28
**Status:** **Working — sleeve-grade, borderline.** The pre-registered form (9-country basket) **failed**:
net −0.05 full / −0.39 IS / +0.30 OOS. The re-framed form uses EFA as the single international leg,
with the signal from EFA's own month-to-date gap to SPY. It nets **0.69 full / 0.83 IS (2002-12) / 0.60 OOS (2013-26)**
at 2 bp EFA / 1 bp SPY. It is in the market one session a month, at CAGR 1.5 % on 2.2 % vol (scale 2). The result is
cost-sensitive (0.35 at 2.5× costs) and uneven (2013-19 ≈ 0). Use it only as a sleeve.

## 1. Idea

Target-date funds (≈ $4 T), balanced funds and global pensions hold US and international equity
in fixed proportions (Vanguard TDFs ≈ 60/40 US/international) and rebalance on the calendar. When
the US out-runs international over a month, the month-end rebalance sells US equity and buys
international funds. Parker-Schoar-Sun (JF 2023) show that TDFs' contrarian rebalancing moves
prices. Harvey-Mazzoleni-Melone (NBER w33554, 2025) show calendar rebalancing between stocks and bonds is
predictable and costs about 17 bp on the next day. This idea applies the same logic to the US-vs-international split.
It is not covered by `dollar-regime-tilt`, `intl-relative-trend` or `country-pairs-reversion`:
those are trend/reversion over weeks to years, while this is a single-session flow keyed to the calendar.

## 2. Data and conventions

Country ETFs, EFA, EEM, VEU, SPY, plus currency-hedged EAFE/Japan/Europe ETFs (DBEF, HEFA, DXJ, HEDJ) and FXE/FXY/UUP
for the FX split; daily closes on the SPY calendar, 1999-2026. The month-end is the last session in the data
(research) or by the NYSE calendar (`strategy.py`). Signal **Z** = month-to-date Σ(r_SPY − r_INTL) through the close
before the earned session, divided by trailing 252d hedged-spread vol × √n. Pre-registered split:
IS ≤ 2012, OOS 2013+.

## 3. Event study (`01_event_study.py`, `02_robustness.py`, `03_horse_race.py`)

The slope of the **last-session** return on Z (signal through L−1), in bp per unit Z (t):

| outcome | 1999-2012 | 2013-2026 |
|---|---|---|
| 9-country basket − β·SPY | +3.1 (0.52) | **+16.7 (3.61)** |
| SPY | +1.2 (0.13) | **−22.1 (−3.48)** |
| 9-country basket (raw) | +4.0 (0.37) | −3.0 (−0.44) |
| EFA − β·SPY | +8.5 (1.39) | **+17.1 (4.29)** |
| EFA − DBEF (the FX part of EFA) | n/a | −1.0 (−0.36) |
| FXE / −UUP | −13.5 (−1.9) / −12.9 (−1.8) | −5.2 (−1.7) / −3.8 (−1.4) |

* **The effect sits in the SPY leg, not in an international bid.** International ETFs do not rise.
  SPY falls into the month-end close when the US has out-run international over the month, and
  the currency part is zero. That is consistent with US equity being *sold*; any international
  buying does not show up at the US close.
* It is **distinct from stock-bond rebalancing.** In a joint regression with the SPY−TLT drift, the
  US−INTL drift keeps its coefficient on the hedged spread (OOS +18.1, t 3.7), and SPY−TLT has none (−4.4).
  SPY−TLT instead moves SPY and international ETFs *together*; that is the idea
  [`global-rebalance-pressure`](../global-rebalance-pressure/).
* With the basket signal, 1999-2012 shows nothing, and sub-periods are 1999-05 0.9, 2006-12 −0.1, 2013-19 1.7,
  2020-26 3.5 (t). Quarter-ends carry most of it (2013-19 q-end t 2.9, 2020-26 t 4.8).
* Single-day placebos (the same regression anchored 1-15 sessions before the month-end) give |t| up
  to 2.9 on isolated days, so one day at t ≈ 2 means nothing here. The last session is the only one
  that is positive in both halves once the signal is EFA's own (§5).

## 4. Pre-registered book: failed (`06_books.py`)

Position in (EW basket − β·SPY) over the last session = clip(Z, ±2)/2 × 4; 5 bp countries, 1 bp SPY.

| book | full | IS | OOS | gross full | @2 bp | @10 bp |
|---|---|---|---|---|---|---|
| **spec: last session, clip** | **−0.05** | −0.39 | 0.30 | 0.38 | 0.17 | −0.41 |
| sign sizing | −0.36 | −0.78 | 0.12 | 0.20 | | |
| L−1..L | −0.49 | −0.61 | −0.36 | −0.18 | | |
| quarter-ends only | 0.23 | −0.26 | 0.68 | 0.51 | | |
| L+1 give-back (short) | −0.16 | −0.11 | −0.22 | 0.25 | | |
| L long + L+1 short | −0.15 | −0.35 | 0.06 | 0.45 | | |

This form is cost-bound. The OOS edge is ≈ 17 bp per unit Z on a session whose round trip in a
nine-ETF basket plus the SPY hedge costs ≈ 12 bp. In-sample it has no edge at all.

## 5. Re-framing: one liquid international leg (`07_efa_leg.py`, `08_efa_robustness.py`)

No institution holds an equal-weight basket of nine countries. The international sleeve of a TDF or balanced
fund is an EAFE or all-world-ex-US index fund. Re-framing therefore uses EFA (or VEU, or EEM) as the single
leg. That cuts the round trip to 2 + 1 bp, and the signal can be measured on the leg itself.
Twelve cells, net at 2 bp (EEM 3 bp):

| leg | signal | all months full / IS / OOS | quarter-ends only full / IS / OOS |
|---|---|---|---|
| EFA | basket | 0.32 / 0.00 / 0.63 | 0.29 / −0.06 / 0.70 |
| **EFA** | **own (SPY−EFA)** | **0.66 / 0.75 / 0.60** | 0.52 / 0.35 / 0.67 |
| VEU | basket | 0.47 / 0.36 / 0.55 | 0.51 / 0.14 / 0.77 |
| VEU | own | 0.53 / 0.53 / 0.56 | 0.51 / 0.15 / 0.74 |
| EEM | basket | 0.18 / −0.32 / 0.54 | 0.33 / −0.20 / 0.75 |
| EEM | own | 0.25 / −0.37 / 0.70 | 0.37 / −0.21 / 0.83 |

EFA-own is the cell carried forward. It is positive in both halves, and the developed-market legs agree
(VEU 0.53 / 0.53 / 0.56). EEM fails in sample, so emerging markets are not part of the flow.

**Robustness of EFA-own at scale 2** (`08`, `09_validate.py`, numbers from `strategy.py`):

* Day profile, EFA−β·SPY on day j (signal through j−1), bp per Z (t): last session **+19.5 (5.17)**,
  IS +26.8 (3.86), OOS +18.8 (4.52). L−3 is +8.2 (2.6). Every other day from L−5 to +3 is
  |t| < 2.4, and the next session is −6.0 (−1.3), a small give-back.
* Placebo books, the same trade anchored 1-12 sessions before the month-end: the true month-end is
  0.69 / 0.83 / 0.60, and no placebo is positive in both halves above 0.4. Eleven of the twelve are ≤ 0.16 full.
* Cost ladder (full / IS / OOS): 0 bp 0.84 / 0.97 / 0.76 · 1 bp 0.77 · **2 bp 0.69 / 0.83 / 0.60** · 3 bp 0.62 ·
  5 bp 0.46 / 0.62 / 0.36. At 2.5× costs it is 0.35.
* Sign sizing gives 0.46. Quarter-ends only give 0.54 and non-quarter months 0.48: both contribute.
* **+1 session lag: −0.52.** Holding the session after the month-end loses, which is the give-back. Timing
  is the trade.
* Sub-periods: 2002-07 0.19, **2008-12 1.38, 2013-19 0.00**, 2020-26 0.93, 2024-26 1.51.
* Events 291, mean +15 bp, hit rate 54 %, top-5 months = 28 % of P&L.
* Stationary bootstrap (63d blocks): median 0.70, 5th pct 0.41, P(SR > 0.5) = 0.87.
  Deflated Sharpe 0.91 at N = 20 and 0.81 at N = 60.
* Correlation to SPY 0.01; to `global-rebalance-pressure` 0.04; to the deployed
  `global-etf-sleeve-blend` −0.01.
* **Look-ahead:** weights from `strategy.py` on data truncated at five dates (including two live
  last-session dates and the final two sessions in the sample) equal the full-sample weights exactly.
  vectorbt (`from_orders`, targetpercent, weights/4 because vectorbt cannot borrow) reproduces
  the book's Sharpe, 0.693 vs 0.693, with daily corr 0.998.

## 6. Spec (`strategy.py`)

At the close of the session before the last session of the month (NYSE calendar):
`pos = clip(Z, −2, 2)/2 × 2.0`, `w_EFA = pos`, `w_SPY = −β·pos` (252d beta). Flat on every other day.

| | full 2002-26 | IS 2002-12 | OOS 2013-26 |
|---|---|---|---|
| Net Sharpe (EFA 2 bp, SPY 1 bp) | **0.69** | 0.83 | **0.60** |

CAGR 1.5 %, vol 2.2 %, MaxDD −5.0 %, turnover 33×/yr, average gross 0.07, **max gross 4.46**
(on one session), time in market 4.6 %, NW t 3.57.

## 7. Honest accounting

* Variants: 25 outcomes × 2 signal windows in the event study, a 6-signal horse race, 6 basket books,
  12 single-leg books, 13 placebo books and 9 sensitivity books. Twenty-two distinct
  tradeable configurations were tried before the reported one.
* The reported cell was chosen after the pre-registered basket book failed, and it is the best of
  the 12 single-leg cells. Its in-sample number (0.75-0.83) exists only because the signal was
  re-defined on EFA; the basket-signal version of the same EFA trade is 0.00 in sample. Treat the
  edge as "a real US-selling flow at the month-end close, about 0.5 Sharpe after selection".
* No mechanism test isolates TDFs. The visible part is US selling at the close; whether the other
  side is international buying cannot be seen at the US close.

## 8. Files

Code `code/global-equity-etf/intl-rebalance-flow/`: `lib.py`, `01_event_study.py` … `10_figures.py`,
`strategy.py`. Spec and figures: `alphas/global-equity-etf/intl-rebalance-flow/`.
