# global-rebalance-pressure — month-end stock/bond rebalancing pressure on global equities

**Asset class:** `global-equity-etf` · **Short name:** `global-rebalance-pressure` · **Date:** 2026-11-28
**Status:** **Working.** Net Sharpe **0.84 full (2002-08 → 2026-11) / 1.01 IS (→ 2012) / 0.69 OOS (2013+)**.
The book trades a 0.6 SPY + 0.4 EFA mix over the last four sessions of the month at 1/2 bp, with gross ≤ 1. Bootstrap 5th
percentile 0.64. **Fading:** 2020-26 is 0.38, 2024-26 is 0.36, and the pre-1995 backcast is ≈ 0. This is a real
institutional flow, but its best years (2002-2016) are behind it.

## 1. Idea

Harvey, Mazzoleni & Melone (NBER w33554, 2025): balanced, pension and target-date funds that
hold stocks and bonds in fixed proportions rebalance on the calendar. After stocks out-run bonds
over the month they must sell equities into the month-end, and they buy after stocks lag. The
trades are predictable from public prices. The paper reports −17 bp next-day equity returns after
stocks become overweight. The `rates-bonds` session (`rebalance-pressure-bonds`) confirmed that
all of it sits in the equity leg and left it as "a lead for the equity-index researcher".

This idea came out of `intl-rebalance-flow`. Its horse race (`../intl-rebalance-flow/03_horse_race.py`)
showed that the SPY−bond drift moves SPY *and* the international ETFs together on the month-end
session (t −3.6 / −2.8 in 1999-2012). So the flow hits US-listed global equities as a
block, which is a directional trade on this asset class's ETFs.

## 2. Signal and data (`grp_lib.py`)

* **Z_t**, the calendar-fund drift: Σ(r_SPY − r_IEF) from the session after the previous month-end
  through close t, divided by the 252d std of the daily difference × √n. Z > 0 means stocks are overweight,
  so the fund sells equities.
* ETF era from 2002-08 (IEF listing): SPY, IEF, TLT, EFA, the nine country ETFs.
* **Backcast 1962-1998, untouched by any choice:** S&P 500 price index, and a synthetic 10y
  par-bond total return from FRED DGS10. DGS10 is a 15:30 ET mark, so the bond leg of the signal is
  30 minutes stale; that can blur the signal but cannot front-run it.

## 3. Event study (`01_event_study.py`, `02_settlement_eras.py`)

Slope of the next-session return on Z_t, by how many sessions are left in the month after the
earned session (0 = the last session), in bp per unit Z (t):

| outcome | L−5 | L−4 | **L−3** | L−2 | L−1 | **L** | mid-month (≥ 6 left) |
|---|---|---|---|---|---|---|---|
| SPY, 2002-08 → 2026 | −0.6 (−0.1) | 4.1 (0.7) | **−46.4 (−6.0)** | −13.7 (−2.0) | −21.9 (−2.8) | **−26.6 (−3.9)** | −2.8 (−1.6) |
| SPY, IS → 2012 | 12.5 | −1.2 | **−70.7 (−5.1)** | −25.2 (−2.2) | −19.3 (−1.2) | **−42.1 (−3.7)** | −0.8 |
| SPY, OOS 2013+ | −12.4 | 7.1 | **−28.7 (−3.3)** | −4.0 | −25.2 (−3.1) | −15.9 (−1.9) | −4.6 (−2.1) |
| EFA, full | −3.2 | −4.7 | **−43.3 (−5.4)** | −10.7 | −20.9 (−2.3) | **−27.7 (−3.6)** | −2.9 |
| 9-country basket, full | −0.2 | −12.2 | **−45.8 (−5.2)** | −12.3 | −27.3 (−2.6) | **−29.3 (−3.6)** | −2.9 |
| S&P, backcast 1962-79 | 1.5 | 9.8 | **+15.9 (+3.8)** | −6.1 | −4.8 | −4.8 | +2.3 |
| S&P, backcast 1980-98 | 0.9 | 4.9 | −10.8 (−2.1) | −4.8 | −9.0 | −7.1 | −2.7 |

* The drift matters only in the **last four sessions**. Mid-month it is −3 bp, so this is not
  generic stock-bond reversal. A rolling 15-session drift tested on every day of the month
  (`../intl-rebalance-flow/05_placebo_all_days.py`) gives the same picture: last four sessions
  −16 to −41 bp (t −2.2 to −5.2), all other days pooled −3.5 (t −1.6).
* The pattern is the same with TLT instead of IEF and with a global (0.6 SPY + 0.4 EFA) equity leg in
  the drift.
* **The effect appears historically as institutional calendar rebalancing becomes common.** It is wrong-signed in
  1962-79, weak in 1980-98 and strong after 1995.
* **A mechanism test that failed:** if rebalancers trade so as to *settle* by the month-end, the peak
  should sit at L − settlement lag. It sits at L−3 in the T+3 era (1995-2017, S&P t −7.5), but it
  **stays at L−3 in the T+2 era** (2017-24: L−3 −37.8, t −2.6; L−2 ≈ 0) instead of moving to L−2.
  The T+5 era (1980-95) shows no L−5 peak. In the T+1 era (2024-26, 29 months) the weight moves to L itself
  (SPY −41.6, t −2.1) and L−3 turns positive. The settlement story is rejected. Why L−3 dominates is
  unexplained, which is why the book pools the last four sessions instead of betting on one day.

## 4. Books (`03_books.py`, 42 cells)

**Spec (fixed before `03` ran; the window was read off the full-sample profile in §3, which is
disclosed):** at close t, if session t+1 is one of the last 4 of its month,
`w = −clip(Z_t, −2, 2)/2` on the GLOBAL mix (0.6 SPY + 0.4 EFA); flat otherwise; SPY 1 bp, EFA 2 bp,
countries 5 bp.

| window | instrument | full | IS | OOS | 2020-26 | 2024-26 |
|---|---|---|---|---|---|---|
| **last 4 (spec)** | **GLOBAL** | **0.84** | **1.01** | **0.69** | 0.38 | 0.36 |
| last 4 | SPY | 0.86 | 1.07 | 0.67 | 0.37 | 0.41 |
| last 4 | EFA | 0.76 | 0.90 | 0.66 | 0.35 | 0.22 |
| last 4 | 9-country basket | 0.67 | 0.79 | 0.60 | 0.22 | 0.10 |
| last 4, TLT drift | GLOBAL | 0.86 | 1.00 | 0.76 | 0.44 | 0.50 |
| last 4, sign sizing | GLOBAL | 0.72 | 0.79 | 0.66 | 0.33 | 0.57 |
| last 5 | GLOBAL | 0.75 | 0.89 | 0.64 | 0.38 | 0.26 |
| last 3 | GLOBAL | 0.72 | 0.83 | 0.63 | 0.43 | 0.73 |
| L−1..L | GLOBAL | 0.72 | 0.76 | 0.71 | 0.45 | 0.48 |
| L only | GLOBAL | 0.62 | 0.80 | 0.44 | 0.38 | 0.48 |
| L−3 only | GLOBAL | 0.45 | 0.60 | 0.30 | 0.03 | −0.79 |

Every window that includes the last 2-5 sessions is 0.6-0.9 full, so the result does not hinge on
the exact window. L−3 alone has faded (OOS 0.30, −0.79 in 2024-26), which is consistent with the T+1 shift.

**Backcast** (S&P 500 / syn10, 1 bp): spec window −0.16 (1962-79), 0.30 (1980-98), **0.44 (1995-06 → 2002-07)**,
the latter being the years between T+3 and the ETF sample.

## 5. Validation (`04_validate.py`, numbers from `strategy.py`)

| | full 2002-08 → 2026-11 | IS → 2012 | OOS 2013+ |
|---|---|---|---|
| **Net Sharpe** (SPY 1 bp, EFA 2 bp) | **0.84** | 1.01 | **0.69** |
| at 0× / 2× / 5× costs | 0.87 / 0.81 / 0.71 | 1.03 / 0.99 / 0.91 | 0.74 / 0.65 / 0.51 |

* CAGR 3.8 %, vol 4.6 %, MaxDD −5.5 %, Newey-West t 3.88. Turnover 10.8× gross/yr. Average gross
  0.064, **max gross 1.00**, in the market 18.7 % of sessions, average net −0.017. Correlation to SPY +0.20.
* Stationary bootstrap (63d blocks): median 0.86, **5th pct 0.64**, P(SR > 0.5) = 0.997.
  Deflated Sharpe 0.995 at N = 42 (this idea's cells) and 0.988 at N = 100.
* **Concentration:** 287 active months, 63 % positive. The top five months (Oct-Nov 2008, Dec 2018,
  Aug 2011, Nov 2007) are 43 % of P&L. Without 2008 it is 0.80; without the top five months, 0.68.
* Calendar years negative: 2017, 2019, 2023, 2025, all small (−0.1 to −1.7 %).
* **Lag:** +1 session gives 0.18 and +2 gives 0.02. The trade is calendar-dated, and a late fill lands on the
  next month's first session, which reverses (+22 bp per Z on M+1, `../intl-rebalance-flow/04_day_profile.py`).
* **Look-ahead:** `strategy.py` on data truncated at 7 dates (inside the window in 2008, 2015, 2020
  and 2024, and the last three sessions of the sample) reproduces the full-sample weights exactly.
  vectorbt `from_orders` (targetpercent, both directions, gross ≤ 1 so no borrowing issue)
  matches: Sharpe 0.839 vs 0.839, corr 1.0000.
* Correlation with the deployed `global-etf-sleeve-blend` is 0.15, and with `intl-rebalance-flow` 0.04.

## 6. Risks

* **Decay.** OOS is 0.69 overall, but 0.38 in 2020-26 and 0.36 in 2024-26. The flow is published
  (2025), the settlement cycle keeps shortening, and futures desks pre-position for the
  well-publicised pension month-end estimates. Expect ≈ 0.4 going forward, not 0.84.
* **Crisis concentration.** Large drifts happen in crashes and rebounds; 2008 alone is +30 %.
* **Execution.** Z needs the SPY and IEF prints at the close the trade is filled on. A one-day
  delay destroys the edge.

## 7. Honest accounting

Event study: 3 drift definitions × 4 outcomes × 3 periods, plus the backcast and 4 settlement eras.
Books: 42 cells. The window was chosen after the full-sample day profile, so the IS number is not
a clean in-sample estimate. The independent checks are the 1995-2002 backcast (0.44) and the
stability across windows (0.6-0.9). The published paper's sample (1997-2023) overlaps the whole
ETF era, so only 2024-26 is post-publication (0.36).

## 8. Files

Code `code/global-equity-etf/global-rebalance-pressure/`: `grp_lib.py`, `01_event_study.py`,
`02_settlement_eras.py`, `03_books.py`, `04_validate.py`, `05_figures.py`, `strategy.py`. Spec and figures
in `alphas/global-equity-etf/global-rebalance-pressure/`. It uses `next_session_days_left`, added to
`code/global-equity-etf/shared/trading_calendar.py`.

## Deployment review

PR #29 (2026-11-28): not deployed as a standalone strategy. The PR recommends `trend-flow-blend`, which carries this sleeve unmodified through its `strategy.py`, and that blend is what was deployed (sim book, `live/global-equity-etf/trend-flow-blend/`). A second standalone copy would double the same month-end trade.
