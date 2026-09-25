# sector-sleeve-blend — four weak, uncorrelated sector-ETF edges, risk-weighted once a year

**Status: Working (borderline).** Net Sharpe **0.88 full 2002-2026 / 0.94 IS / 0.81 OOS**
(T-bill excess, 2 bp/side), 0.65 OOS at 5 bp. Honest selection-free version 0.62 OOS. It does
**not** clear a Sharpe-1 bar out of sample. Its case is diversification: β 0.26 to SPY, a third of
SPY's drawdown, and |ρ| ≤ 0.02 with the live treasury-calendar and crypto-alts books.
Asset class `sector-etf`. Date 2026-09-25.

## Why a blend
Eight single ideas were tested this session (see `../all_ideas.md`). None clears Sharpe ≈1 on
its own. Four gave small, robust edges that survive out of sample, and they are nearly
uncorrelated with one another:

| Sleeve | Source idea | Spec (fixed before the blend was built) | Standalone Sharpe full / IS / OOS |
|---|---|---|---|
| **ON** | `overnight-sentiment-reversal` | long low / short high recent-overnight-return sectors, rank ensemble over 21-252 d, 21-day tranches, SPY β-hedge | 0.52 / 0.60 / 0.41 |
| **CAL** | `equity-flow-calendar` | EW sector basket on TOM [−3, +3], scheduled-FOMC day + day before, pre-holiday | 0.69 / 0.75 / 0.59 |
| **DIP** | `sector-short-reversal` (TS re-framing) | Connors canonical: RSI(2) < 10 & close > SMA200 → 1/9 long, exit close > SMA5 (max 10 d) | 0.62 / 0.60 / 0.63 |
| **RATE** | `rate-sensitivity-rotation` | 126-d rate beta × sign of 1-month ΔDGS10 (lagged 1 d), monthly, SPY β-hedge | 0.33 / 0.35 / 0.30 |

Pairwise daily correlations 2000-2026: ON with anything |ρ| ≤ 0.03; RATE ≈ 0; CAL–DIP 0.31
(0.39 OOS — both are long equities after weakness or into flow windows). The arithmetic of four
equal-risk sleeves with these Sharpes and correlations gives ≈0.95-1.0, which is what the IS-weighted
blend delivers.

**Selection disclosure.** ON is the selection-free ensemble of its idea. DIP is the canonical
Connors specification — it was not the best of that idea's 96 cells. CAL is the best of 10
literature-window combinations for the EW basket (the others ran 0.40-0.66). RATE is the best of 18
rate books. The *choice of these four sleeves* was made after seeing that they, and not the
reversal, BAB, seasonality and lead-lag books, were positive. The WF7 control below measures
what that choice is worth.

## Construction (`strategy.py`)
* Each sleeve produces target weights on the 11 SPDRs + SPY (its own 2 bp-net return series is
  kept for sizing).
* **Risk weights, once a year:** in year Y, sleeve *i* gets
  k_i = (10 % / √n) / σ_i, where σ_i is the std of the sleeve's net daily returns from its first
  trade through 31 Dec of Y−1 (expanding). A sleeve needs 3 years of history to enter, and n is the
  number of eligible sleeves. No look-ahead, and nothing is fitted to returns.
* Total weight = Σ k_i · W_i, netted across sleeves (costs are charged on the *combined*
  turnover), gross capped at 2.0 (binds on 1 % of days; uncapped max 2.4, same Sharpe).
* Resulting 2025-26 weights: ON 0.89, CAL 0.48, DIP 1.11, RATE 0.64.

## Results — the deployable function (`final_eval.py`, 2002-01 → 2026-09-24)
Excess of T-bills (DGS3MO charged on net dollar exposure):

| | Sharpe full | IS 2002-14 | OOS 2015-26 | CAGR (excess) | vol | MaxDD | t_NW |
|---|---|---|---|---|---|---|---|
| **blend, 2 bp** | **0.88** | 0.94 | **0.81** | 9.4 % | 10.9 % | −24.7 % | 4.85 |
| blend, 0 bp | 0.98 | 1.04 | 0.91 | 10.6 % | 10.9 % | −24.4 % | 5.40 |
| blend, 5 bp | 0.73 | 0.80 | 0.65 | 7.6 % | 10.9 % | −26.8 % | 4.02 |
| SPY buy & hold (excess) | 0.50 | 0.35 | 0.70 | 8.1 % | 18.9 % | −56.2 % | 2.98 |

* Total-return (not excess) Sharpe, which is what the paper book will show: 0.94 / 0.99 / 0.89,
  CAGR 10.2 %.
* Turnover 54×/yr (one-way, on capital), mean gross 1.13, mean net long 0.36 (range −0.38 … +2.0).
* **Alpha vs SPY** (HAC t): full 7.1 %/yr, t 3.6, β 0.26; IS 8.6 %/yr, t 3.2; **OOS 5.4 %/yr,
  t 1.97**, residual Sharpe 0.56.
* 2002 is −22 %. That year the rule has only CAL eligible (the other sleeves lack 3 years of
  history), so it runs CAL alone at 10 % vol through the 2002 bear market. From 2003, when ≥ 3
  sleeves are live, Sharpe is 1.02. The headline keeps 2002 because dropping it would be a
  post-hoc sample choice.
* Year by year (excess %), blend vs SPY: 2008 **+17.0 vs −37.7**, 2022 **+11.4 vs −19.9**,
  2018 −9.8 vs −6.4, 2015 −5.1 vs +1.2, 2024 −1.8 vs +18.6. The blend lost money in 5 of 25 years.
* Stationary block bootstrap: 5 / 50 / 95 % = 0.57 / 0.89 / 1.24, P(Sharpe > 1) = 0.30.
* Deflated Sharpe: 0.99 at N = 30, 0.94 at N = 200, 0.85 at N = 1000. The session ran ~580 books
  plus ~900 screen tests.
* vectorbt cross-check: at 1/3 scale (no margin needed) 0.940 vs 0.941, daily ρ 0.9999. At full
  scale vectorbt's cash account cannot borrow and under-holds on the ~2 % of days when net long
  exceeds 1 (0.98, ρ 0.977).
* Gross cap sensitivity (`cap_sensitivity.py`): none 0.87 / 0.80 · 2.0 0.88 / 0.81 · 1.5 0.90 / 0.87
  · 1.0 0.88 / 0.85. Not used to choose the spec.
* Live-data substitution (`tnx_check.py`): RATE fed with yfinance ^TNX instead of FRED DGS10 →
  0.89 / 0.94 / 0.84, daily ρ 0.996.
* Correlation with the live books since 2018-03: treasury-flow-calendar −0.004, crypto-alts BAB
  +0.022.

## How the weighting and sleeve choice move the number (all variants tried)
| Variant | full | IS | OOS | note |
|---|---|---|---|---|
| CORE4, monthly EWM-126 vol weights (`blend.py`, first try) | 0.86 | 1.11 | **0.58** | fast weights cut CAL/DIP after the 2020 vol spike, into the rebound |
| CORE4, 5 bp | 0.69 | 0.94 | 0.41 | |
| CORE3 (no RATE), EWM | 0.83 | 1.03 | 0.61 | |
| ALL7 (+ REV, BAB, SEAS reference books), EWM | 0.73 | 1.01 | 0.42 | |
| WF7: ALL7, sleeve on in Y iff expanding Sharpe through Y−1 > 0, EWM | 0.70 | 0.93 | 0.50 | |
| CORE4, weights frozen at IS vols (`diag.py`) | 0.95 | 1.06 | 0.81 | diagnostic |
| **CORE4, yearly expanding vol (`slowvol.py`)** | 0.99 | 1.16 | 0.80 | research twin of `strategy.py` (starts 2003 in practice) |
| CORE3, yearly | 0.91 | 1.05 | 0.74 | |
| ALL7, yearly | 0.82 | 1.09 | 0.57 | |
| **WF7, yearly — the selection-free control** | **0.91** | 1.19 | **0.62** | REV and BAB stay switched on (positive IS) and drag OOS; SEAS switches off in 2008 |
| `strategy.py` (CORE4 yearly, gross cap 2, from 2002) | 0.88 | 0.94 | 0.81 | headline |

The weighting scheme matters about as much as the sleeves: fast (EWM) vol weights cost ≈0.2 of OOS
Sharpe. The yearly expanding scheme was chosen *after* the EWM version disappointed OOS. It is the
simpler and slower of the two and uses no future data, but the switch itself is a researcher degree of
freedom and counts in the trial total.

## Risks and what would break it
* **Weak OOS alpha**: t 1.97 over 11.7 years. The honest forward expectation is Sharpe ≈0.6-0.8, not
  0.88.
* **Fat left tail from DIP (the main deployment risk).** Worst blend days: **−10.0 % (2011-08-08),
  −8.8 % (2020-02-27), −5.7 % (2018-02-05)**. That is a 14σ day for a 10.9 %-vol book. In each, DIP
  (−7.5 %, −5.7 %, −3.8 %) and CAL were long several sectors that had passed the RSI(2)/SMA200
  filter just before a crash leg. 1 % daily VaR is only −1.9 %, so this is jump risk and normal-vol
  sizing does not see it. **Gross cap changes the tail, not the Sharpe:**

  | gross cap | Sharpe full / OOS | CAGR (excess) | worst day | 1 % VaR |
  |---|---|---|---|---|
  | none (max 2.4) | 0.87 / 0.80 | 9.4 % | −10.0 % | −1.87 % |
  | 2.0 (spec) | 0.88 / 0.81 | 9.4 % | −10.0 % | −1.86 % |
  | 1.5 | 0.90 / 0.87 | 9.2 % | −8.6 % | −1.78 % |
  | 1.0 | 0.88 / 0.85 | 7.1 % | −5.7 % | −1.47 % |

  A cap of 1.0 needs no margin and halves the worst day at the same Sharpe. It is offered as a
  deployment option, not as the tested spec, because it was examined after the spec was fixed.
* **CAL is market beta in windows.** It is a timing sleeve, not a hedge, and correlates 0.31-0.39 with
  DIP.
* **RATE is the weakest leg** (t 1.85) and bled from 2015 to 2020. Dropping it (CORE3) costs ≈0.07.
* **Leverage**: net long reaches 2.0 on ~1 % of days (CAL window + several DIP entries). The paper book
  must allow gross 2.0.
* **Calendar inputs**: the FOMC schedule (`fomc_dates.csv`, covers 2027) must be refreshed each
  year. The NYSE holiday rules miss unscheduled closures (six since 1999, announced days ahead
  at most).

## Files
* `code/sector-etf/sector-sleeve-blend/strategy.py` — `target_weights(close, open_, y10=None, …)`,
  self-contained (sleeves, NYSE calendar, yearly risk weights, gross cap).
* `sleeves.py`, `failed_refs.py`, `corr.py`, `blend.py`, `diag.py`, `slowvol.py`,
  `verify_strategy.py`, `final_eval.py`, `cap_sensitivity.py`, `tnx_check.py`, `fomc_dates.csv`,
  `window_dressing_screen.py` (quarter-end window-dressing / tax-loss screen for a fifth sleeve: no
  consistent effect -- quarter-end QTD IC +0.05 IS vs −0.16 OOS; January loser bounce same sign but
  only 27 Januaries).
* Alpha spec and figures: `alphas/sector-etf/sector-sleeve-blend/`.
