# volume-attention — abnormal trading volume predicts alt underperformance

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Failed (real but too weak standalone; kept as a sleeve candidate)

## 1. Idea

Miller (1977) and Garfinkel et al. ("Disagreement and returns: the case of cryptocurrencies",
*Financial Management* 2025): when disagreement is high and shorting is costly, prices reflect the
optimists, and abnormal volume is the usual proxy for disagreement. Barber-Odean attention buying
tells the same story: retail flows into coins that are "in the news", which shows up as a volume
surge, and they then underperform. Garfinkel et al. sort daily. The version here is slow: a coin's
volume over the last k days relative to its own prior 180/365 days, ranked across the PIT top-20
alts, short the surging names and long the quiet ones.

**Provenance, stated up front.** The mechanism surfaced as a by-product of the
`taker-flow-imbalance` IC screen (`ic_02.csv`), which already covered 2023-26. The OOS numbers
below are therefore not a clean hold-out for the *choice of mechanism*. They are clean for every
parameter choice, which was made on IS only (rule fixed before the grid ran) or avoided entirely
through the (k, base) ensemble.

## 2. Setup

* Panel, PIT universe (top-20 by trailing 90d median yfinance USD volume, ≥ 120 closes, ≥ $5M),
  splits IS 2018-22 / OOS 2023-26, 10 bp/side: `code/crypto-alts/shared/study.py`.
* Signal: `AV(k, base) = log(mean vol[t-k+1..t] / mean vol[t-k-base+1..t-k])`, yfinance USD volume.
* Book: dollar-neutral linear-rank weights, short high AV, gross 1. `bn` adds a BTC leg sized to
  zero the EWM-60 beta, and `dn` omits it. Daily targets are averaged over `hold` overlapping
  tranches. Weights are shifted one bar in `backtest_xs`.

## 3. Results

### 3.1 Grid (60 configs, `01_grid.py` → `grid_01.csv`)
k ∈ {7,14,30,60,90} × base ∈ {180,365} × hold ∈ {7,14,30} × {dn, bn}.

* Median full 0.33 / IS 0.40 / OOS 0.20, ρ to BAB 0.07.
* Consistent structure: longer holds are better (30 > 14 > 7), the BTC-beta hedge adds 0.15-0.20 in
  every cell, k = 30-60 is best, and k = 7 is noise.
* **IS-selected cell** (rule fixed in advance): `k30|b180|h30|bn`, **0.69 full / 0.74 IS / 0.63 OOS**,
  CAGR 12 %, MaxDD −31 %, t_NW 2.1, turnover 8×/yr, pooled-bear 1.29 (per bear: 2.0, 0.3, 2.3, 1.7, 0.6).
  Best-of-60 in-sample, so the expected OOS decay applies. It decayed by only 0.1.

### 3.2 Refinements (`02_refine.py` → `refine_02.csv`), selection-free ensemble over the 10 (k, base) cells, bn, hold 30

| Book | full | IS | OOS | bear | ρ BAB |
|---|---|---|---|---|---|
| AV ensemble, linear | 0.56 | 0.61 | 0.49 | 0.95 | 0.10 |
| AV ensemble, terciles | 0.56 | 0.60 | 0.51 | 0.88 | 0.10 |
| AV ⟂ same-window return | 0.61 | 0.78 | 0.36 | 0.84 | 0.12 |
| AV ⟂ abnormal volatility | 0.54 | 0.40 | 0.74 | 0.88 | 0.09 |
| up-day volume only (Miller optimism) | 0.54-0.61 | 0.51-0.58 | 0.58-0.65 | 0.96 | 0.10 |
| down-day volume only | 0.56-0.59 | 0.74-0.85 | 0.20-0.28 | 0.82-0.96 | 0.07 |
| inverse-vol position sizing | 0.34-0.46 | 0.51-0.81 | −0.15-0.07 | ~1.0 | 0.1 |
| control: 30d reversal (same construction) | 0.08 | 0.07 | 0.11 | 0.87 | −0.02 |
| control: 30d momentum | −0.30 | −0.26 | −0.36 | −1.08 | 0.02 |
| control: abnormal volatility | 0.20 | 0.25 | 0.12 | 0.51 | 0.06 |
| AV ensemble, universe 10 / 15 / 30 | 0.40 / 0.36 / 0.47 | 0.50 / 0.34 / 0.72 | 0.24 / 0.40 / 0.10 | | |

Reading:
* The effect is not reversal in disguise. The ensemble correlates 0.40 with a 30d reversal book,
  but reversal on its own earns 0.08, and volume orthogonal to returns still earns 0.61 full.
  It is not abnormal volatility either: AV ⟂ abnormal |return| holds 0.54 full and is the best OOS
  variant, while abnormal volatility alone earns 0.20.
* Up-day volume (the Miller "optimists buying" leg) carries the OOS result. Down-day volume was
  IS-strong and faded OOS.
* Inverse-vol sizing kills it: the edge sits in the volatile names.
* Universe size matters more than it should. 20 names (the pre-fixed standard) is the best of
  10/15/20/30, and at 30 names the OOS is 0.10.

### 3.3 As a sleeve next to BAB (`03_blend.py`)
Equal-risk-style blend, risk weights from IS volatility only:

| | full | IS | OOS | pooled bear |
|---|---|---|---|---|
| BAB alone (live spec) | 1.22 | 1.35 | 1.06 | 1.49 |
| BAB + ⅓-risk AV ensemble | 1.29 | 1.44 | 1.11 | 1.71 |
| BAB + ⅓-risk up-day AV | 1.31 | 1.43 | 1.16 | 1.72 |
| BAB + ½-risk AV ensemble | 1.21 | 1.34 | 1.04 | 1.71 |

The low correlation (0.10) turns into only +0.05-0.10 of Sharpe because the sleeve itself is ~0.5.

## 4. Verdict

**Failed** as a standalone strategy. The abnormal-volume premium is real in the sense that
matters: the sign is the same IS and OOS, it is robust to return and volatility controls,
selection-free at ~0.5, and the IS-picked cell held 0.63 OOS. But ~0.5-0.6 Sharpe on a
dollar-neutral alt book, with 20-name universe sensitivity and a mechanism chosen after seeing
2023-26 ICs, is not deployable by itself. It is carried forward as a candidate sleeve for a
multi-sleeve blend (see the session's blend idea). Variants evaluated: 60 grid + 27 refinement
books + 8 blends = 95.

## 5. Files
`code/crypto-alts/volume-attention/`: `common.py` (`abn_volume`), `01_grid.py`, `02_refine.py`,
`03_blend.py`, `grid_01.csv`, `refine_02.csv`, `*_nets.parquet`.
