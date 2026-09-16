# industry-residual-reversal — sector-residual short-term reversal in S&P 500 names

**Status: Failed** vs acceptance criterion "1.5+ Sharpe". Best honest net Sharpe **0.60** (full),
and only by trading 12 % of the time (VIX > 25 gate). Best always-on net: 0.22. Gross Sharpe
never exceeds 1.10 in any variant.

Date: 2026-09-16 · Asset class: us-large-cap · Split fixed in advance: IS 2010-01→2017-12,
OOS 2018-01→2026-09 · Base cost 5 bp per side (S&P 500 quoted spreads 1–5 bp; 2 bp shown as
sensitivity, never as the headline) · ~240 variants evaluated.

Code: `code/us-large-cap/industry-residual-reversal/` (`screen1..5*.py`, `figures.py`, csv outputs).
Shared data layer built for this: `code/us-large-cap/shared/` (see `code/shared/DATA.md` §4).

## 1. Idea

Short-term reversal is the one cross-sectional anomaly the literature reports as still
net-profitable in *large* caps after 1990 once returns are residualised on industry / factor
exposure (Blitz, Huij, Lansdorp & Verbeek 2013 *Short-term residual reversal*; Da, Liu &
Schaumburg 2014 *A closer look at the short-term return reversal*, FRBNY SR 513: within-industry
reversal is the persistent part, across-industry is momentum). This asset class uniquely offers
~430 simultaneous, largely independent bets, so a modest IC could in principle compound into a
high-Sharpe dollar-neutral book. Question: does it clear 1.5 net in 2010–2026?

## 2. Data

* Panel: 634 priced S&P 500 members since 2010 (point-in-time membership from
  fja05680/sp500; 15 recycled tickers dropped, see DATA.md). Median 433 members/day.
* **Survivorship caveat**: no delisted names (75 % coverage of the index in 2010, 98 % now).
  This biases *long-loser* results upward (losers that went to zero are absent), i.e. it
  flatters the strategy. The result is Failed despite the bias.
* GICS sector from Wikipedia (current) / yfinance `.info` (past names); UNK bucket otherwise.
* Earnings reaction bars from `data/SP500_earnings_dates.parquet` (for the exclusion variant).

Engine `xs_lib.xs_backtest`: weights known at close *t* earn close-to-close *t+1*; cost on
Σ|Δw| per side. Dollar-neutral books, gross 1.0 (0.5 long / 0.5 short).

## 3. What was tried, and what it did

### 3.1 Signal screen (20 signals, decile L/S, daily rebalance) — `screen1.py`

| signal | IC(1d) | t | IC(5d) | t | gross Sh | net Sh 5bp | IS | OOS | turnover/yr |
|---|---|---|---|---|---|---|---|---|---|
| −ret 5d, sector-residual (**rev5_sec**) | 0.011 | 5.0 | 0.013 | 6.7 | **0.84** | −0.34 | −1.02 | −0.07 | 195 |
| −ret 21d, sector-residual | 0.006 | 2.9 | 0.009 | 4.5 | 0.59 | 0.02 | −0.30 | 0.18 | 96 |
| −ret 1d, sector-residual | 0.013 | 6.6 | 0.012 | 6.2 | 0.56 | −2.14 | −3.60 | −1.56 | 423 |
| −ret 5d raw | 0.012 | 4.2 | 0.015 | 5.4 | 0.65 | −0.29 | | | 198 |
| −ret 5d beta-residual (120d β to EW mkt) | 0.008 | 2.9 | 0.010 | 3.9 | 0.49 | −0.52 | | | 191 |
| −intraday 5d (sector-res.) | 0.010 | 3.7 | 0.013 | 5.1 | 0.68 | −0.38 | | | 201 |
| +overnight 5d (Aboody et al. persistence) | **−0.008** | −3.2 | −0.006 | −2.5 | −0.42 | −1.44 | | | 176 |
| 12-1 momentum | 0.015 | 4.0 | 0.014 | 3.9 | 0.16 | 0.04 | 0.14 | −0.01 | 29 |
| low vol / low max | ≤0.007 | | ≈0 | | −0.26 | −0.47 | | | 51 |
| rev5_sec on low-volume names only | 0.007 | 4.2 | 0.009 | 5.5 | 0.58 | −0.88 | | | 271 |
| rev5_sec on high-volume names only | 0.007 | 4.5 | 0.008 | 5.6 | 0.59 | −0.42 | | | 234 |

Findings: sector residualisation raises the IC t-stat (5.0→6.7 at 5d) but not the gross Sharpe
much; beta-residualisation is worse than sector. **Overnight returns reverse in large caps**
(negative IC) rather than persist as in Aboody et al. 2018 — that paper's persistence lives in
small/hard-to-value names. Volume conditioning (Cooper 1999) does not separate news from noise
here. Momentum is the only signal with turnover low enough to survive costs, and it has no
Sharpe.

### 3.2 Combination, weighting, holding period (84 configs) — `screen2.py`

Combos of z-scored rev1/rev5/rev21/intraday/overnight/mom12-1; decile vs full-universe
linear-rank vs inverse-vol-scaled linear weights; overlapping tranches of 1/3/5/10 days.

* Gross Sharpe: max **0.95** (all six signals, decile, hold 1). Linear weights lower vol
  (5 % vs 8 %) but not Sharpe.
* Net at 5 bp: max **0.22** (all6 decile hold 10: IS 0.09 / OOS 0.30, turnover 37).
  Every hold-1 config is negative net. Decay vs cost: going from hold 1 → 10 cuts gross
  Sharpe by ~40 % and turnover by ~80 %; the crossover leaves ~0.2 net.
* `figures/01_turnover_decay.png` shows the cost drag is linear in turnover at ≈ 0.0055
  Sharpe per unit of annual one-way turnover — at 5 bp any reversal book turning > 150×/yr
  starts below zero.

### 3.3 Regime gating (12 configs) — `screen3.py`

Reversal is a liquidity-provision premium and pays when markets are stressed
(`figures/03_yearly_gross_vs_vix.png`: 2011 gross 2.2, 2020 2.0, 2024 1.6; 2012/2016/2021/2023
≈ 0).

| book | gate | gross | net 5bp | IS | OOS | avg gross exposure |
|---|---|---|---|---|---|---|
| linear rev5+21 hold 3 | none | 0.75 | 0.12 | 0.00 | 0.19 | 0.91 |
| linear rev5+21 hold 3 | ×(VIX/20)² cap 3 | 0.76 | 0.43 | 0.25 | 0.54 | 0.83 |
| linear rev5+21 hold 3 | VIX > 25 only | 0.82 | **0.60** | 0.44 | 0.73 | **0.12** |
| decile rev5 hold 1 | VIX > 25 only | 0.80 | 0.52 | 0.47 | 0.61 | 0.13 |

The gate improves net Sharpe by not trading, not by earning more; the book is flat 88 % of
the time and the 0.60 is on ~2 % annual return. Not a strategy.

### 3.4 Extreme-move event study and asymmetric event book — `screen3.py`, `screen4.py`

Sector-residual forward returns (bp) after moves of |z| > 2 own-vol units:

| formation | side | N/yr | h1 | h3 | h5 | h10 | OOS h5 |
|---|---|---|---|---|---|---|---|
| 1 day | loser (z<−2) | 1697 | −4 (t −2.9) | −1 | 0 | +3 | +2 |
| 1 day | winner (z>+2) | 1703 | −4 (t −3.2) | −7 | −8 (t −3.6) | −12 (t −3.7) | −9 |
| 3 day | loser | 2001 | 0 | +3 | +5 (t 2.5) | +6 | +6 |
| 3 day | winner | 1986 | −6 (t −5.3) | **−14 (t −8.3)** | **−16 (t −7.4)** | −17 | **−21** |

Clear asymmetry: big *losers* in large caps do not bounce (one-day drops are news and
drift), big multi-day *winners* give back 15–20 bp. But a sector-hedged book of it
(108 configs: formation 1/3/5 d, |z| > 1.5–3, short-winners / long-losers / both, hold 3/5/10)
tops out at gross **0.74**, net **−0.12** — the hedge legs turn over daily and the book
earns ~4 %/yr gross at 6 % vol.

### 3.5 Earnings-window exclusion (8 configs) — `screen5_earnings_excl.py`

Dropping names whose formation window contains an earnings reaction bar lifts decile rev5
gross Sharpe **0.86 → 1.10** (IS −0.91 → −0.36 net) — the classic "reversal is stronger on
non-news days" result — but net stays ≤ 0.17 because turnover rises with the extra churn of
the mask. Excluding names *about to* report (next 5 bars) hurts (the pre-announcement run-up
is part of the reversal P&L, see the earnings-event-drift report).

### 3.6 Cost sensitivity

At **2 bp**/side the best always-on book (all6 decile hold 10) reaches ≈ 0.4 and linear
hold-1 books ≈ 0.3; at **0 bp** the best is 0.95. The criterion is out of reach at any cost.

## 4. Why it fails

Per-trade edge in S&P 500 names post-2010 is 5–20 bp on a 3–5 day horizon, against a 10 bp
round trip. Breadth cannot fix a negative expectation per trade. The premium also clusters in
stress years, so any "always-on" version spends most years paying costs for nothing.

## 5. Variants and multiple-testing

~240 configurations across five screens. The best net full-sample Sharpe among *always-on*
configurations is 0.22; expected best-of-240 under the null with these correlated variants is
of that order, so there is no evidence of a net edge at all. Gross edge (IC t ≈ 5–8) is real
and consistent with the literature.

## 6. Figures

`figures/01_turnover_decay.png` gross/net vs holding period and cost drag vs turnover ·
`figures/02_equity.png` growth of $1, gross and net, with the VIX gate ·
`figures/03_yearly_gross_vs_vix.png` yearly gross Sharpe vs VIX.

## 7. What a future attempt would need

A signal with quarterly-scale turnover (≤ 10×/yr) and ≥ 50 bp per-trade edge, or a venue
where costs are genuinely ≤ 1 bp. Do not re-run reversal variants for a 1.5 target.
