# eth-perp-crowding — contrarian retail positioning on Binance ETH perps, traded on spot ETH

**Date:** 2026-10-03
**Asset:** spot ETH/USDT (Binance daily bars, 00:00 UTC), long/flat, unlevered, daily rebalance, 10 bp/side
**Status:** **Failed** — ETH's own retail crowd does not time ETH. The *BTC* crowd does, but that is the bet the book already runs as `spot-btc/perp-crowding`.

| 2022-06 → 2026-10, 10 bp/side | full | IS ≤ 2023 | OOS 2024+ | MaxDD |
|---|---|---|---|---|
| **BTC spec on ETH price × ETH crowd (pre-registered)** | **0.59** | 0.71 | **0.51** | −26% |
| vol-scaled B&H | 0.53 | 0.68 | 0.45 | −53% |
| live `eth-trend-filter` (SMA40 × vol 0.5) | 0.90 | 0.41 | 1.18 | −40% |
| ETH price × **BTC** crowd | 1.11 | 1.42 | 0.93 | −35% |

## 1. Idea

`spot-btc/perp-crowding` (2026-09-28, Working, live) holds spot BTC only while Binance's
*global long/short account ratio* for the BTCUSDT perp — a head count of the retail crowd — is
below its own expanding-history median, sized by inverse volatility. It was never run on ETH.
The same feed exists for ETHUSDT, so the test here is a **pre-registered replication**: the BTC
`strategy.py :: target_weight` is imported and called with its defaults on ETH closes and the
ETH ratio. Nothing is re-fitted.

## 2. Data and protocol

- `data/ETHUSDT_metrics_5m.parquet` (data.binance.vision `futures/um/daily/metrics`): 5-minute
  snapshots **2021-12-01 → 2026-10-02**. The ETH archive does not exist before 2021-12-01 (HTTP
  404 for 2020-09 … 2021-11); BTC's starts 2020-09-01.
- Daily bars from the 1m Binance store, bar D = [D 00:00, D+1 00:00) UTC. For bar D the signal is
  the last snapshot stamped before 23:00 (the spec's 1-hour cutoff); the weight is held over bar D+1.
- Evaluation starts **2022-06-01** (archive start + the spec's 180-day rank warm-up).
  Split = the spot-eth convention, fixed before the run: IS ≤ 2023-12-31, OOS 2024-01-01+.
  Where the BTC ratio is the signal the window is 2021-03+, and the BTC study's split
  (IS ≤ 2022 / OOS 2023+) is shown as well.
- Every sleeve is judged against the live trend filter: P&L correlation, HAC t-stat of the
  regression alpha, and gate/blend forms (`code/spot-eth/shared/evalkit.py`, new this session).

## 3. Replication (`exp01_replicate.py`)

| | full | IS | OOS | CAGR | MaxDD | turnover | exposure | ρ to TF | alpha t vs TF (full / IS / OOS) |
|---|---|---|---|---|---|---|---|---|---|
| P1 spec, ETH crowd | 0.59 | 0.71 | 0.51 | 11.4% | −26% | 34× | 0.20 | 0.62 | 0.09 / 0.74 / −0.13 |
| P2 spec + SMA50 gate | 0.41 | 0.07 | 0.76 | 6.3% | −25% | 24× | 0.15 | 0.67 | −0.52 / −0.56 / 0.22 |
| ETH price × BTC crowd | 1.11 | 1.42 | 0.93 | 34.3% | −35% | 34× | 0.36 | 0.74 | 1.32 / 2.29 / 0.25 |
| BTC price × ETH crowd | 0.29 | 0.85 | −0.29 | | | | | | |
| BTC spec on BTC, same window | 1.20 | 1.31 | 1.12 | 36.2% | −30% | 45× | 0.50 | | |

- The ETH crowd is "uncrowded" on only 33% of days against 56% for BTC: the ETH ratio has
  drifted up, so the expanding median sits low. State agreement between the two crowds is 0.65;
  the log ratios correlate 0.38 in levels and 0.72 in daily changes.
- Yearly Sharpe of P1: 0.36 / 0.92 / **2.83** / −0.11 / −0.30 for 2022…2026. One good year.
- The **ETH** crowd fails on BTC too (0.29), while the **BTC** crowd works on both assets.

## 4. What the positioning series know (`exp02_screen.py`)

39 features (three ETH ratios as level / expanding rank / z90 / z180 / rank365 / 1-3-7d change,
ETH-minus-BTC crowding, the BTC crowd, top-minus-global, OI growth, taker ratio) × h = 1/3/7 d,
raw and partial (controls: returns over 1–60 d, SMA40 state, 20d realised vol).

| partial IC (HAC t) | h=1 IS | h=1 OOS | h=3 IS | h=3 OOS |
|---|---|---|---|---|
| ETH global ratio, z180 | −0.123 (−2.8) | −0.003 (−0.6) | −0.215 (−3.7) | −0.053 (−1.1) |
| ETH global ratio, expanding rank | −0.094 (−2.4) | −0.002 (−0.4) | −0.179 (−2.5) | −0.039 (−0.7) |
| **BTC global ratio, expanding rank** | −0.129 (−2.8) | **−0.053 (−2.4)** | −0.167 (−2.1) | **−0.091 (−2.3)** |
| BTC global ratio, level | −0.108 (−2.3) | −0.049 (−2.6) | −0.113 (−1.3) | −0.084 (−2.3) |
| ETH − BTC crowding (level) | +0.003 (0.7) | +0.035 (1.4) | −0.025 (−0.2) | +0.042 (1.1) |
| top-position − global, z90 | +0.147 (2.7) | −0.032 (−0.3) | +0.173 (2.6) | +0.006 (0.1) |

- IS→OOS Spearman of the partial t-stats: +0.17 / +0.15 / +0.20 (BTC study: 0.70 / 0.60 / 0.38).
  Of 10 IS-significant features at h = 1, two keep |t| ≥ 2 OOS — both are the BTC crowd.
- The ETH ratio was contrarian in 2022–23 and is noise since. The ETH-minus-BTC spread is empty in
  both halves, so there is no ETH-specific crowding to trade against ETH/BTC either.
- Reading: retail crowding is a **market-wide** state. The BTC perp measures it best; the ETH
  ratio is a noisier copy with a drifting mean.

## 5. ETH timed by the BTC crowd (`exp03_market_crowd.py`), 2021-03 → 2026-10

| | full | IS ≤ 2022 | OOS 2023+ | IS ≤ 2023 | OOS 2024+ | MaxDD | turn | alpha t vs TF (full / ≤2023 / 2024+) |
|---|---|---|---|---|---|---|---|---|
| vol B&H | 0.53 | 0.15 | 0.71 | 0.61 | 0.45 | −54% | 4× | |
| TF_live | 0.83 | 0.25 | 1.10 | 0.48 | 1.18 | −48% | 19× | |
| SMA50 × vol | 0.93 | 0.30 | 1.21 | 0.69 | 1.18 | −33% | 13× | |
| **A** ETH price × BTC crowd (spec) | **1.18** | 1.07 | 1.24 | 1.33 | 1.05 | −36% | 32× | 1.99 / 2.27 / 0.51 |
| **C1** TF AND BTC-uncrowded | **1.11** | 0.33 | 1.39 | 0.78 | 1.41 | **−27%** | 24× | 1.69 / 1.07 / 1.19 |
| C2 TF × (0.5 + 0.5·uncrowded) | 1.00 | 0.31 | 1.27 | 0.65 | 1.33 | −33% | 21× | 1.70 / 1.07 / 1.20 |
| D 50/50 TF + A | 1.10 | 0.76 | 1.24 | 1.00 | 1.20 | −31% | 29× | |

Next-day ETH return by state (bp, 2024+): uptrend & uncrowded **+40** (t 2.4, n 390); uptrend &
crowded −12; downtrend & uncrowded −9; downtrend & crowded −17. Before 2024 the crowd also paid in
downtrends (+60 bp, t 1.8) — that leg is gone.

**It is the BTC sleeve on another asset.** P&L correlation of A with the live BTC
`perp-crowding` sleeve is **0.80** (0.67 with TF_live). Regressing A on [TF_live, BTC sleeve]:

| | alpha / yr | t | β TF | β BTC sleeve |
|---|---|---|---|---|
| full | +3.7% | 0.64 | 0.31 | 0.64 |
| IS ≤ 2023 | +7.7% | 1.09 | 0.24 | 0.65 |
| OOS 2024+ | −2.1% | −0.24 | 0.38 | 0.64 |

## 6. Robustness and re-framings (`exp04_robustness.py`)

| Check | Result |
|---|---|
| ETH own-ratio family, 3 ratios × 4 normalisations (expanding rank, rank365, z90, z180), standalone | median **0.48 / 0.63 / 0.45**; best full 0.65; none above TF_live (0.90) |
| Same family as a gate on TF_live | median 0.69 / 0.10 / 0.99 vs TF 0.90 / 0.41 / 1.18; the two cells above TF full (top-account rank365 1.08, top-position z90 0.98) have IS −0.25 and 0.60 |
| Market-wide composite, mean expanding rank of 7 majors (BTC ETH SOL BNB XRP DOGE ADA), 2022-06+ | standalone 1.17 / 1.17 / 1.17, alpha t vs TF 1.70 / 1.86 / 0.94 — the same as BTC alone (1.11 / 1.42 / 0.93) within noise; 5 alts without BTC and ETH 1.02 / 0.88 / 1.10 |
| Crowd-state lag −1 (illegal) / 0 / +1 / +2 / +3 days | A 3.55 / **1.18** / 0.87 / 0.72 / 0.56; C1 2.23 / **1.11** / 0.94 / 0.86 / 0.93 — fast decay, as on BTC |
| Snapshot cutoff 0 / 1 / 2 / 6 h before the close | A 1.14 / 1.18 / 1.21 / 1.16 — no end-of-day leak |
| Rank threshold 0.3 … 0.7 | A 1.01 – 1.20, C1 0.95 – 1.11 (TF 0.83) |
| Costs 0 / 5 / 10 / 20 / 30 bp | A 1.29 / 1.24 / 1.18 / 1.08 / 0.97; C1 1.19 / 1.15 / 1.11 / 1.02 / 0.94; TF 0.88 … 0.72 |
| Truncation test (data cut at 2022-06-30, 2024-03-15, 2025-11-01) | max \|Δw\| = 0 at all three |
| Circular-shift placebo of the crowd state (500 draws, shift ≥ 90 d) | A 1.18 vs mean 0.25, sd 0.29, **p = 0.000**; C1 1.11 vs mean 0.51 (TF alone 0.83), **p = 0.018** |
| Block bootstrap (21 d) of Sharpe(C1) − Sharpe(TF) | median **+0.28**, 5–95% [−0.14, +0.71], P(> 0) = 0.86 |

Place in the ETH book (daily P&L, 2021-03+):

| | full | IS ≤ 2023 | OOS 2024+ | MaxDD |
|---|---|---|---|---|
| TF_live | 0.83 | 0.48 | 1.18 | −48% |
| `eth-venue-premium` (live spec) | 1.14 | 0.82 | 1.46 | −27% |
| TF + venue-premium, 50/50 | 1.00 | 0.65 | 1.35 | −35% |
| C1 + venue-premium, 50/50 | 1.19 | 0.86 | 1.49 | −26% |
| venue-premium AND uncrowded | 1.24 | 0.87 | 1.58 | −23% |

## 7. Verdict

- **Failed as specified.** The ETH perp's retail head count does not time ETH: 0.59 full / 0.51
  OOS under the pre-registered spec, median 0.48 / 0.45 over 12 normalisations, partial ICs gone
  after 2023.
- **The BTC crowd is a market-wide state and it does carry to ETH** (A 1.18 full, placebo
  p = 0.000), but the book already holds it: ρ 0.80 with `spot-btc/perp-crowding`, residual alpha
  t 0.64 full / −0.24 OOS. Deploying A would lever the same bet, not add one.
- **Amendment candidate for `eth-trend-filter`, not applied:** gating the live trend filter by
  the BTC crowd state (C1) lifts it 0.83 → 1.11 full, 0.48 → 0.78 IS, 1.18 → 1.41 OOS and cuts the
  drawdown from −48% to −27%; placebo p = 0.018, but the bootstrap interval of the lift
  [−0.14, +0.71] includes zero. Same class of finding as the Thursday skip.
- Binding constraint: ETH has no positioning information of its own; ETH minus BTC crowding has
  a partial IC indistinguishable from zero in both halves.

Configurations evaluated: 39 features × 3 horizons (screen); 62 costed sleeves (8 replication,
9 forms × 2 splits, 24 own-ratio family, 12 composites, 9 threshold/cutoff variants).

## 8. Files

- `code/spot-eth/eth-perp-crowding/common.py` — loaders; imports the BTC spec unchanged
- `exp01_replicate.py`, `exp02_screen.py` (+ `exp02_partial_ic.csv`), `exp03_market_crowd.py`, `exp04_robustness.py`
- `code/spot-eth/shared/evalkit.py` — daily IC / partial IC / additivity helpers (new, shared)
