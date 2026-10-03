# gas-burn-demand — on-chain fees, burn and activity as a demand signal for spot ETH

**Date:** 2026-10-03
**Asset:** spot ETH/USDT (Binance daily bars, 00:00 UTC), long/flat, 10 bp/side
**Status:** **Failed** — no fee, burn, net-issuance or activity feature predicts ETH (or ETH/BTC) in both halves; no a-priori rule beats vol-scaled buy-and-hold, and no gate or veto improves the live trend filter.

| best a-priori rules, 2018-09 → 2026-10 | full | IS ≤ 2023 | OOS 2024+ | alpha t vs TF (full) |
|---|---|---|---|---|
| vol-scaled B&H | 0.74 | 0.90 | 0.45 | |
| live `eth-trend-filter` | 1.14 | 1.12 | 1.18 | |
| net issuance below its 365 d median × vol | 0.73 | 0.77 | 0.77 | 0.26 |
| fee momentum 30/90 > 0 × vol | 0.70 | 0.85 | 0.35 | 0.24 |
| TF with a froth veto (fee z7/90 > 2) | 1.17 | 1.15 | 1.23 | 0.79 |

## 1. Idea

ETH is the only large asset whose "revenue" is observable daily: users pay fees in ETH, and since
EIP-1559 (2021-08) most of the fee is burnt. Three stories are told about it:

- **Demand momentum** — rising fees mean rising demand for block space; price follows.
- **Froth** — fee spikes mark euphoric tops (NFT mints, memecoin manias) or panic liquidations.
- **Scarcity** — when burn exceeds issuance the supply shrinks ("ultrasound money"); low net
  issuance should support the price, and ETH-specific demand should show up against BTC.

The brief names gas/burn series as a first-class signal source, and no earlier spot-eth study
used them (stablecoin supply and exchange flows were tested on 2026-09-25).

## 2. Data and timing

- CoinMetrics community API, daily, 2015-07 → 2026-10-02: `FeeTotNtv` (fees in ETH), `IssTotNtv`,
  `SplyCur`, `TxCnt`, `AdrActCnt`. Burn = issuance − Δsupply. Cache `data/COINMETRICS_ETH_d.parquet`
  (refreshed by `fetch_fees.py`, which also adds `BlkCnt`).
- **Publication lag, measured:** CoinMetrics' own `AssetEODCompletionTime` says the row for day D
  is complete a median **2.9 h** after D+1 00:00 UTC, 90th percentile 10 h, with a tail of days.
  Every chain series is therefore lagged one full day: the weight decided at D+1 00:00 uses the
  chain row of D−1. Fees are chain facts, not re-tagged estimates like exchange flows.
- Fees are taken **in ETH**, not USD, so no feature contains the price mechanically.
- Three structural breaks sit in the sample — London (2021-08-05), the Merge (2022-09-15), Dencun
  (2024-03-13, rollups stop paying calldata fees; mainnet fees fall ~90%). Features are therefore
  momentum ratios, rolling z-scores and rolling ranks, never raw levels.
- IS 2017-09 → 2023-12, OOS 2024-01 → 2026-10 (the spot-eth convention).

## 3. Screen (`exp01_screen.py`) — 24 features × 4 horizons, raw and partial

Features: fee momentum (7/30, 7/90, 30/90, 30/180), fee z-scores (1d/30, 7d/90, 7d/365, 30d/365),
fee per transaction, fee yield on supply (level, 365 d rank), net issuance 7/30/90 d and its
change, burn share of issuance, transaction-count and active-address momentum and z-scores.
Partial ICs control for returns over 1–60 d, the SMA40 state and 20 d realised vol.

| | h = 1 | h = 3 | h = 7 | h = 30 |
|---|---|---|---|---|
| IS→OOS Spearman of raw t-stats | −0.06 | −0.14 | −0.22 | −0.35 |
| IS→OOS Spearman of partial t-stats | +0.05 | −0.02 | −0.11 | −0.32 |
| features with IS \|t\| ≥ 2 (raw / partial) | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |
| …that also reach \|t\| ≥ 2 OOS | 0 | 0 | 0 | 0 |

- The single IS-significant family is **transaction-count momentum** (7/30: h = 7 IC +0.09, t 2.2;
  h = 30 IC +0.22, t 2.4). OOS it is −0.03 (t −0.2) and +0.00 (t −0.8). It worked in the 2017–21
  adoption phase (regime ICs +0.11 pre-London, +0.14 London→Merge) and reversed after the Merge
  (−0.20). Rollups moved the activity off mainnet.
- The fee features are null in both halves: largest \|t\| 2.0 (yesterday's fee vs its 30 d mean,
  h = 1, IC +0.059 IS → +0.033 OOS, t 1.1), and it vanishes at lag 2.
- Net issuance and burn share: \|t\| < 1.1 everywhere. The "ultrasound" story has no return
  content at 1–30 days.
- Fee features correlate 0.2–0.4 with past 30–60 d returns — fees rise in rallies — which is why
  the partial ICs are even smaller than the raw ones.

## 4. Re-framings (`exp02_reframings.py`)

**Spike events.** Fee z-score above 2 or 3 (1 d vs 30 d, and 7 d vs 90 d), split by whether ETH
fell or rose more than 3% that day. 18 cells × 4 horizons: one cell has \|t\| > 2 (z1/30 in (2,3],
price up, h = 3, OOS, n = 6). No panic rebound and no euphoric top: after a 7 d/90 d spike above
3 the next 30 days were +15.5% IS (n 36) and −5.6% OOS (n 7) relative to the unconditional mean.

**By trend regime.** h = 7 IC inside up-trends and down-trends, 9 features × 2 regimes × 2 halves:
largest \|t\| 1.7, and the sign differs between halves in 6 of the 18 feature-regime pairs.

**Against BTC.** The same 24 features against the forward ETH/BTC return:

| | h = 7 | h = 30 |
|---|---|---|
| IS→OOS Spearman of t | −0.13 | −0.30 |
| IS \|t\| ≥ 2 | 3 (tx and address momentum) | 2 |

Active-address momentum 7/30 is the nearest thing to a relative signal (h = 7: +0.115, t 2.5 IS;
+0.067, t 1.9 OOS) but it is gone at h = 30 OOS (−0.03) and `eth-btc-relative-momentum` already
showed the pair cannot carry a weak 7-day signal at 40 bp round trip. Net issuance has the
*wrong* sign against BTC OOS (+0.22, t 1.8–2.3: more issuance, ETH outperforms) — post-Dencun
issuance rose while ETH rallied in 2025.

**A-priori costed rules** (10 bp/side, 2018-09 → 2026-10; alpha t is the HAC t of the regression
intercept on the live trend filter):

| | full | IS | OOS | MaxDD | turn | alpha t full / IS / OOS |
|---|---|---|---|---|---|---|
| vol B&H | 0.74 | 0.90 | 0.45 | −54% | 4× | |
| TF_live | 1.14 | 1.12 | 1.18 | −48% | 18× | |
| fee momentum 30/90 > 0 × vol | 0.70 | 0.85 | 0.35 | −41% | 5× | 0.24 / 0.61 / −0.47 |
| fee momentum 7/30 > 0 × vol | 0.38 | 0.60 | −0.14 | −58% | 14× | −0.97 / −0.35 / −1.17 |
| yesterday's fee above its 30 d mean × vol | 0.60 | 0.77 | 0.20 | −43% | 48× | −0.05 / 0.33 / −0.52 |
| fee-yield 365 d rank > 0.5 × vol | 0.72 | 0.82 | 0.44 | −35% | 4× | 0.22 / 0.40 / −0.21 |
| net issuance below 365 d median × vol | 0.73 | 0.77 | 0.77 | −43% | 4× | 0.26 / 0.16 / 0.58 |
| TF AND fee momentum 30/90 > 0 | 0.46 | 0.51 | 0.33 | −48% | 12× | −1.56 / −1.12 / −1.16 |
| TF AND fee momentum 7/30 > 0 | 0.81 | 1.06 | 0.18 | −37% | 14× | −0.18 / 0.58 / −1.06 |
| TF veto fee z7/365 > 2 | 1.07 | 1.01 | 1.18 | −46% | 17× | −0.16 / −0.20 / — |
| TF veto fee z7/90 > 2 | 1.17 | 1.15 | 1.23 | −49% | 19× | 0.79 / 0.60 / 0.66 |
| TF OR fee z1/30 > 2 | 1.15 | 1.10 | 1.23 | −45% | 22× | 0.36 / −0.15 / 0.56 |
| TF × (0.5 + 0.5·1{fee momentum 30/90 > 0}) | 0.92 | 0.92 | 0.93 | −45% | 15× | −1.56 / −1.12 / −1.16 |

No standalone rule beats vol-scaled buy-and-hold in the full sample; the froth veto moves the
trend filter by +0.03.

**Lag sensitivity.** `fee_z1_30` at h = 1: lag 0 (not obtainable live) +0.046 / −0.023, lag 1
+0.059 / +0.033, lag 2 +0.003 / +0.003. `fee_mom_30_90` at h = 30 is unchanged by the lag
(+0.04 IS / +0.15 OOS, t ≤ 1.0). There is no fast information being destroyed by the
conservative one-day lag.

## 5. Verdict

**Failed.** Fees, burn, net issuance and activity counts are coincident with price and
carry nothing forward at 1–30 days:

- zero of 24 features is significant in both halves, and the IS→OOS rank correlation of the
  t-stats is zero or negative at every horizon;
- the only IS effect (transaction-count momentum) belongs to the pre-rollup adoption phase and
  reversed after the Merge;
- the best costed rule is a tie with vol-scaled buy-and-hold (0.73 vs 0.74).

Binding constraint: structural breaks. The mapping from mainnet fees to demand for ETH changed
three times in five years, and after Dencun most activity pays almost nothing on mainnet. A
demand series that survives this would have to add rollup activity (L2 fees, blob fees), which
has history only from 2024.

Configurations evaluated: 24 features × 4 horizons × {raw, partial}; 18 event cells × 4
horizons; 36 regime ICs; 48 ETH/BTC ICs; 11 costed rules; 4 lags.

## 6. Files

- `code/spot-eth/gas-burn-demand/common.py` — feature builder with the one-day lag
- `fetch_fees.py` — cache refresh + publication-lag measurement
- `exp01_screen.py` (+ `exp01_raw_ic.csv`, `exp01_partial_ic.csv`), `exp02_reframings.py`
