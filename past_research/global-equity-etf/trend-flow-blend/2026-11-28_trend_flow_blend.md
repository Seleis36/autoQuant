# trend-flow-blend — slow country trend + FOMC + two month-end flow sleeves

**Asset class:** `global-equity-etf` · **Short name:** `trend-flow-blend` · **Date:** 2026-11-28
**Status:** **Working, recommended deployment.** Net Sharpe **1.25 full (2003-03 → 2026-11) / 1.40 IS / 1.15 OOS (2013+)**,
CAGR 10.5 %, vol 8.3 %, MaxDD −9.5 %, at 5 bp countries / 2 bp EFA / 1 bp SPY. It **supersedes
`global-etf-sleeve-blend`**, which scores 0.91 / 1.02 / 0.82 with MaxDD −20 % on the same data and window.
Deploy one or the other, not both: they share two sleeves (daily corr 0.86).

## What it is

Four sleeves, each from its own unmodified `strategy.py`:

| sleeve | mechanism | standalone net full / IS / OOS | multiplier |
|---|---|---|---|
| [`intl-relative-trend`](../intl-relative-trend/) | 6/12/24-month trend of country ETFs vs SPY, market-neutral | 0.68 / 0.77 / 0.62 | 0.490 |
| [`fomc-global-beta`](../fomc-global-beta/) | long EW country basket over FOMC day −1/0 | 0.56 / 0.64 / 0.52 | 0.605 |
| [`global-rebalance-pressure`](../global-rebalance-pressure/) | stock/bond month-end rebalancing: −clip(Z)/2 on 0.6 SPY + 0.4 EFA, last 4 sessions | 0.85 / 1.03 / 0.69 | 0.861 |
| [`intl-rebalance-flow`](../intl-rebalance-flow/) | US-vs-EFA month-end rebalancing: EFA − β·SPY on the last session | 0.68 / 0.81 / 0.60 | 0.672 |

Sleeve daily correlations: all within ±0.07, except FOMC × rebalance at +0.27 (both are long/short
equity beta around the turn of the month, and FOMC statements often fall in the last days of a month).

```
w_t = 0.490·trend + 0.605·fomc + 0.861·rebalance + 0.672·intl_flow ;  if Σ|w_t| > 4: w_t *= 4 / Σ|w_t|
```

## Calibration (`01_calibrate.py`, IS 2003-03 → 2012 only, `calib.json`)

Rules written down before any blended number was computed:
1. Equal risk: multiplier ∝ 1 / (IS daily vol of the sleeve, zeros included).
2. Sparse-sleeve caps *in final book terms*: the rebalance sleeve may reach gross ≤ 2, and the one-session
   `intl-rebalance-flow` gross ≤ 3, on their active sessions.
3. Book scalar L such that the blended IS vol is 10 % (bisection with the caps applied).
4. A per-session rule: if the combined target gross exceeds 4, scale the row down to 4. This is known at the close. It never
   bound in 2003-2026 (max gross 3.97).

Only the `intl-rebalance-flow` cap binds: equal risk would have given it 2.6×, and it is capped at 0.67×. An
implementation slip, with the cap applied before L, was found and fixed before any blended result was
looked at. Its symptom was the rebalance sleeve shrinking to gross 0.14.

## Results (`02_evaluate.py`, numbers from `strategy.target_weights`)

| | full | IS 2003-12 | OOS 2013-26 | 2020-26 | 2024-26 | CAGR | vol | MaxDD |
|---|---|---|---|---|---|---|---|---|
| **trend-flow-blend** | **1.25** | **1.40** | **1.15** | 0.89 | 0.68 | 10.5 % | 8.3 % | **−9.5 %** |
| deployed global-etf-sleeve-blend | 0.91 | 1.02 | 0.82 | 0.55 | 0.05 | 8.1 % | 9.1 % | −20.2 % |
| without intl_flow (same multipliers) | 1.14 | 1.30 | 1.03 | 0.65 | 0.18 | | | −10.8 % |
| without rebalance (same multipliers) | 1.04 | 1.16 | 0.94 | 0.79 | 0.59 | | | −13.6 % |
| costs × 2 | 1.13 | 1.30 | 0.99 | 0.74 | 0.52 | | | |
| +1 session lag | 0.52 | 0.67 | 0.40 | | | | | −23.6 % |

* Newey-West t **5.94**. Turnover 42× gross per year (FOMC ≈ 10, rebalance ≈ 10, intl-flow ≈ 23, trend ≈ 4).
  Average gross 1.11, 99th pct 2.32, **max 3.97**.
* P&L share: trend 36 %, rebalance 33 %, FOMC 21 %, intl-flow 10 %.
* Correlation to SPY 0.18; to the deployed blend 0.86.
* Stationary bootstrap (63d blocks, 2000 draws): median 1.26, **5th pct 0.97**, P(SR > 1) = 0.93.
  Deflated Sharpe ≈ 1.00 at N = 100 and N = 300.
* Calendar years: 19 of 24 positive. Worst years: 2010 −5.7 %, 2025 −2.6 %, 2023 −1.5 %, 2017 −1.4 %, 2019 −0.5 %.
* **Look-ahead:** `strategy.py` on data truncated at 6 dates reproduces the full-sample weights exactly
  (max |diff| 0). The dates are inside the 2008 rebalance window, mid-2015, a live last-session date (2026-09-29), mid-September 2026 inside an FOMC window,
  and the last two sessions. vectorbt `from_orders` at weights/4 (its cash account cannot
  borrow) gives Sharpe 1.242 vs 1.250, with daily corr 0.9996.
* **The lag result is not look-ahead.** Three of the four sleeves trade dates known in advance (FOMC days,
  the last sessions of the month), and a one-session delay moves each onto a reversing session. The trend
  sleeve alone is lag-robust (0.64 → 0.62). Live, the book has to fill at the signal close, as the simulator does.

## What is honest about the split

The multipliers were fit on IS only. But the two new sleeves were *designed* with the full sample in view.
The rebalance window was read off a 2002-2026 day profile. `intl-rebalance-flow` became an EFA trade after the
pre-registered basket version failed. So the OOS 1.15 is not a clean hold-out for those two sleeves.
The clean evidence for them is:
* `global-rebalance-pressure` is 0.6-0.9 for every window from the last 2 to the last 5 sessions, and 0.44 in an untouched
  1995-2002 S&P backcast;
* `intl-rebalance-flow` passes 12 placebo anchors, and the VEU leg agrees (0.53 / 0.53 / 0.56).

Without the two new sleeves the blend is the deployed one (0.91). Expect the deployed improvement to be
nearer +0.2 than +0.34 Sharpe.

## Risks

* **Recent decay of the calendar sleeves.** In 2024-26, FOMC is −0.81, rebalance 0.36 and intl-flow 1.51 (sleeve level); the blend is 0.68.
  The FOMC and rebalance flows are published and crowded.
* **Execution timing.** The flow sleeves need the close of the signal day; the +1 lag gives 0.52.
* **Calendars.** `shared/trading_calendar.py` holds NYSE holidays through 2027, and
  `fomc-global-beta/fomc_snapshot.csv` the FOMC dates through 2027-12. **Both must be extended before 2028.**
* **Data:** the rebalance sleeve needs the IEF close (signal only) in the live price feed.

## Files

Code `code/global-equity-etf/trend-flow-blend/`: `strategy.py`, `01_calibrate.py` (+ `calib.json`),
`02_evaluate.py`, `03_figure.py`. Spec and figure: `alphas/global-equity-etf/trend-flow-blend/`.
