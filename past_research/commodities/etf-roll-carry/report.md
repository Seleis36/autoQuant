# etf-roll-carry — cross-sectional commodity carry, measured from the =F / ETF return gap

**Asset class:** commodities · **Status: Failed** (marginal — Sharpe 0.57 timing-robust, not significant after multiple-testing deflation) · 2026-09-25

## 1. Data finding that matters for every future commodities study

The yfinance continuous front contracts (`GC=F … ZW=F`) are **stitched without roll adjustment**.
A holder never earns the jump from the expiring to the next contract, so `=F` returns overstate
long returns in contango markets. Compounded annual return, same dates, futures vs. the ETF that
actually holds and rolls the futures:

| Pair | =F CAGR | ETF CAGR | gap |
|---|---|---|---|
| NG=F / UNG | −3.5% | −24.9% | 21.4 pp/yr |
| ZW=F / WEAT | +0.3% | −10.0% | 10.3 |
| CL=F / USO | +1.2% | −4.3% | 5.5 |
| ZC=F / CORN | +2.8% | −1.5% | 4.3 |
| HG=F / CPER | +4.6% | +3.3% | 1.3 |
| GC=F / GLD, SI=F / SLV | ~ +0.5 pp (fee + financing) | | |

**Do not book P&L on `=F` closes.** Any long-biased backtest on them is flattered by the missing roll
cost; a short-biased one is penalised. This study books every return on the ETFs
(GLD SLV CPER USO UNG CORN SOYB WEAT, the latter three from Teucrium; common sample from 2011-11
when CPER lists, signals need 1y of history so the backtests effectively start late 2012 for
copper and 2011 for the others).

The same gap is a free signal: over k days, `ln(ETF_t/ETF_{t-k}) − ln(F_t/F_{t-k})`, annualised, is
the **realised roll yield** the ETF earned. It is > 0 in backwardation and < 0 in contango. That is the idea
here: Koijen-Moskowitz-Pedersen-Vrugt (2018) "Carry" / Gorton-Hayashi-Rouwenhorst (2013)
term-structure sorting, with the curve slope read off the return gap because yfinance has no
deferred contracts.

## 2. Protocol

* Signals at the close of day t, applied to t+1 returns (`research_lib.backtest_xs`); cost 10 bp per
  side on |Δw| unless stated. ETF borrow fees for the short leg (UNG, WEAT, CORN) are **not**
  modelled. They are usually < 1%/yr but not free.
* Split fixed before the first run: IS 2011–2018, OOS 2019–2026-09.
* Cross-section: long top 37.5% / short bottom 37.5% (3 vs 3 of 8), dollar-neutral, gross 1.0.
* COT data: CFTC disaggregated futures-only, 2010–2026 (`code/commodities/shared/fetch_cot.py`,
  cached to `data/CFTC_COT_disagg_w.parquet`). Tuesday positions used from the following Monday's
  close (report date + 6 days); reports inside the 2013, 2018-19 and 2025 shutdown backlogs are
  held back until a conservative publication date.

## 3. What was tried (≈127 configurations in total)

### 3.1 Raw carry, single look-back (`explore.py`, `explore2.py` — 68 configs)
* The first run had the sign reversed (the gap is positive in contango). Corrected thereafter.
* **Daily rebalancing is dead**: 125× annual turnover → −12%/yr in costs; both signs lose.
* Monthly rebalancing, correct sign: Sharpe 0.2–0.57 depending on k ∈ {21,63,126,252} and a
  skip-gap of {0,1,5,21} days. It is not monotone in k or skip. Noisy.
* Time-series carry (sign of own carry, inverse-vol): −0.4 to +0.2. **Fails.** The long legs in
  "backwardated" names lose more than short UNG earns.

### 3.2 Factor zoo, monthly XS (`explore3.py` — 16 configs), full-sample Sharpe [IS / OOS]
| Signal | Quantile L/S |
|---|---|
| carry (avg rank of k=63,126,252) | **0.56** [0.53 / 0.62] |
| momentum (ETF total return, same k) | 0.13 [−0.19 / 0.39] |
| hedging pressure (−commercial net / OI) | 0.12 [−0.13 / 0.35] |
| HP vs own 1y mean | −0.36 |
| managed-money net / OI | 0.32 [0.17 / 0.47] |
| −skewness 252d | 0.28 [0.29 / 0.29] |
| pre-registered composite carry+mom+HP+skew | 0.32 [0.10 / 0.53] |
| carry + mom | 0.43 [0.20 / 0.66] |

Only carry is consistent in both halves. Adding factors dilutes it; with 8 names the other
factors' spreads are mostly noise.

### 3.3 Decomposition and risk weighting (`explore4.py` — 13 configs)
* P&L contribution of carry [q] (ann.): short natgas +4.4%, long gold +1.1%, silver +1.1%,
  copper +0.9%, corn +0.7%, wheat +0.4%, crude −0.8%.
* Static control (expanding-mean carry rank): 0.37. Pure timing (carry minus own mean): −0.03.
  → **The edge is a persistent cross-sectional structure**: it is short the chronic-contango ETFs
  (UNG, WEAT, CORN) and long the metals. It does not come from timing changes in the curve.
* Inverse-vol weighting within legs: carry 0.56 → **0.71** [0.75 / 0.71]. Portfolio vol targeting
  (10%) adds nothing (0.69). Inverse-vol versions of the composites are all worse than carry alone.

### 3.4 Robustness of carry-ivol (`robustness.py` — ~30 configs)
| Variant | Sharpe | IS | OOS | MaxDD |
|---|---|---|---|---|
| base, rebalance on last bd of month | 0.73 | 0.75 | 0.71 | −21.6% |
| rebalance 5 bd before month-end | **0.38** | 0.43 | 0.33 | −29.6% |
| rebalance 10 bd before | 0.47 | | | |
| rebalance 15 bd before | 0.54 | | | |
| **tranched (mean of 4 monthly books, offsets 0/5/10/15)** | **0.57** | **0.60** | **0.55** | **−26.3%** |
| tranched, q=0.5 | 0.65 | 0.63 | 0.67 | −18.7% |
| tranched, k=63 only | 0.77 | 0.57 | 0.98 | −26.2% |
| tranched, k=252 only | 0.30 | | | |
| tranched, drop natgas | **0.34** | 0.22 | 0.47 | |
| tranched, cost 20 bp | 0.50 | | | |

Month-end rebalancing is the luckiest of the four offsets, so the tranched book is the honest
estimate. Headline for the tranched book: CAGR 5.6%, vol 10.6%, Sharpe 0.57, Sortino 0.81,
MaxDD −26.3%, skew −0.44, Newey-West t = 2.40, turnover 6.7×/yr, gross 0.94, net ≈ 0.

Deflated Sharpe probability (Bailey–López de Prado) for the tranched book: 0.75 at N=10 trials,
0.49 at N=50, **0.39 at N=100**, 0.33 at N=150. With ~127 configurations evaluated, the result
is **not distinguishable from the best of many noise strategies**.

Yearly (month-end base): 2011 +29, 2012 +17, 2013 −12, 2014 +5, 2015 +11, 2016 +4, 2017 +15,
2018 −2, 2019 +10, 2020 −3, 2021 −3, 2022 +14, 2023 +12, 2024 −4, 2025 +25, 2026 YTD +13 (%).

## 4. Verdict

**Failed.** The effect is real in direction and matches the literature, and IS/OOS are stable.
But after removing rebalance-day luck it is a Sharpe-0.57 book with a −26% drawdown. It does not
survive deflation for the number of variants tried, and about half of it is one trade (short UNG).
Take natgas out and it is 0.34. The binding constraint is breadth. Published commodity carry
uses 20–30 contracts, and 8 names give 3-vs-3 legs where one idiosyncratic contract dominates.

## 5. For the next researcher
* The **=F vs ETF gap** is reusable as a carry/roll-yield measure for any commodity with a
  futures-holding ETF, and as a warning: never book P&L on `=F`.
* Most promising extension (not done here, because it would re-pick the universe after seeing
  results): **pre-register** a wider panel of single-commodity futures ETFs with a matching `=F`
  (BNO/BZ=F, UGA/RB=F, CANE/SB=F, UNL, DBB …), then run the tranched inverse-vol carry book unchanged.
  Breadth is the lever. More signal engineering on 8 names is not.
* COT hedging pressure and managed-money positioning add nothing cross-sectionally on 8 names.
* Time-series carry does not work on these ETFs.

## Files
* `code/commodities/shared/panel.py` — =F / ETF pair loader
* `code/commodities/shared/fetch_cot.py` — CFTC COT fetcher with release-lag / shutdown handling
* `code/commodities/etf-roll-carry/{explore,explore2,explore3,explore4,robustness,factors}.py`
