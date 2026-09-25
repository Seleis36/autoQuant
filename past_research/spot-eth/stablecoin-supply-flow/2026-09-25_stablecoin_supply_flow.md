# stablecoin-supply-flow — stablecoin net issuance as a buying-power signal for spot ETH

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT daily closes at 00:00 UTC, 2018-06 → 2026-09-24)
**Short name:** `stablecoin-supply-flow`
**Status:** **Failed**

## TL;DR

The hypothesis: new stablecoin issuance is fiat entering crypto as dry powder, so supply growth should lead ETH (Griffin & Shams 2020 on Tether; Ante, Fiedler & Strehle 2021 on issuance events; the Glassnode "stablecoin supply ratio"). On a supply aggregate of USDT + USDC + BUSD + DAI (CoinMetrics community), lagged one extra day:

- **Slow growth (30–60 d) is a mirage.** IC with 30-day forward ETH returns is +0.19–0.25 IS and **−0.12 to −0.22 OOS**. The in-sample effect was the 2020–21 bull market, when issuance and prices rose together.
- **Short-horizon growth (7 d) has a small positive IC in both halves** (7d→7d: 0.036 IS / 0.094 OOS). A long/flat vol-scaled gate `1{g7 > 0}` earns **Sharpe 0.96 full / 0.94 IS / 1.00 OOS**, against 0.62 / 0.72 / 0.44 for vol-scaled buy-and-hold.
- It is not a new edge. It is **0.58 correlated** with the live `eth-trend-filter`, alpha vs it is **t_NW 0.94 IS / 0.66 OOS**, and a 30/70 blend lifts the trend filter from 1.10 / 1.06 / 1.20 to only 1.17 / 1.13 / 1.26. Used as a gate on the trend filter it makes things worse (1.06 / 1.07 / 1.05).
- **Mint events** (daily issuance above the trailing-year 80th/90th/95th percentile) show positive excess forward returns in both halves in most cells, but at t < 1.9 on 14–206 events. Conditioning on a preceding ETH decline (the Griffin–Shams pattern) does not sharpen it.
- **Ethereum-chain stablecoins** (DefiLlama, 2020-06+) are weaker than the all-chain total (OOS 0.72 vs 1.10). Ethereum's share of stablecoins is weaker still.

## Data

- `data/COINMETRICS_{USDT,USDC,BUSD,DAI}_d.parquet` — `SplyCur` from the CoinMetrics community API (free, no key). USDT covers every chain from 2014; USDC from 2018-08. Fetcher: `code/spot-eth/shared/coinmetrics.py`.
- `data/DEFILLAMA_STABLE_{ALL,ETHEREUM,USDT,USDC}_d.parquet` — DefiLlama stablecoin charts. Fetcher: `code/spot-eth/stablecoin-supply-flow/fetch_stablecoins.py`. **Trap:** DefiLlama's history is incomplete before ~2020 (USDT on Omni is missing: total supply shows $0.06 bn in mid-2018 against a true ~$2.8 bn, with fake +27,000% daily "jumps" as chains come online). Use it from 2020-06 only; use CoinMetrics for anything earlier.
- `data/COINMETRICS_ETH_d.parquet` — ETH market cap, for the supply ratio.
- **Timing:** ETH daily bar D is Binance [D, D+1), closing at D+1 00:00 UTC. The weight set at that close uses the supply value **stamped D−1** (CoinMetrics stamps a daily value at the start of the day it covers; the extra day guarantees publication). Weights are applied to the next day's return by `research_lib.backtest`, with 10 bp per side.
- Sample starts 2018-06 (USDC listed, warm-up for 365-day z-scores). IS 2018-06 → 2023-12, OOS 2024-01 → 2026-09.

## 1. Predictive ICs (Spearman, `01_signals.py`)

| Signal | 1d IS | 7d IS | 30d IS | 1d OOS | 7d OOS | 30d OOS |
|---|---|---|---|---|---|---|
| g1 (1-day growth) | 0.060 | 0.069 | 0.103 | 0.031 | 0.057 | −0.015 |
| g7 | 0.038 | 0.079 | 0.160 | 0.032 | 0.045 | −0.071 |
| g30 | 0.046 | 0.110 | 0.216 | −0.008 | −0.050 | −0.120 |
| g60 | 0.054 | 0.124 | **0.251** | −0.007 | −0.065 | **−0.217** |
| gz7 (7d growth z vs 365d) | 0.013 | 0.036 | 0.052 | 0.043 | **0.094** | 0.023 |
| gz60 | 0.029 | 0.062 | 0.146 | 0.020 | 0.004 | −0.143 |
| −SSR z (dry powder) | 0.002 | 0.008 | 0.009 | 0.007 | 0.010 | 0.091 |

## 2. Long/flat strategies (47 variants, `01_signals.py`)

Gate = `1{signal > thr}`, sized either by the trend filter's vol scalar (`vs`, target 50%, cap 1) or multiplied into the live trend-filter weight (`vs × trend`).

| Variant | Full | IS | OOS | CAGR | MDD | TIM | ρ to TF |
|---|---|---|---|---|---|---|---|
| trend filter (reference, 2018-06+) | 1.10 | 1.06 | 1.20 | 40% | −48% | — | 1.00 |
| vol-scaled buy & hold | 0.62 | 0.72 | 0.44 | 21% | −68% | 100% | — |
| g7 > 0 × vs | 0.96 | 0.94 | 1.00 | 35% | −50% | 52% | 0.58 |
| g30 > 0 × vs | 0.88 | 1.13 | 0.50 | 31% | −50% | 54% | 0.58 |
| gz7 > −0.5 × vs | 0.98 | 1.17 | 0.71 | 33% | −49% | 45% | 0.60 |
| g7 > 0 × trend | 1.06 | 1.07 | 1.05 | 30% | −41% | 29% | 0.78 |
| g30 > 0 × trend | 1.12 | 1.24 | 0.89 | 33% | −38% | 30% | 0.80 |
| −SSR z > −0.5 × trend | 1.23 | 1.12 | 1.43 | 32% | −37% | 21% | 0.68 |
| median of 47 | ~0.70 | ~0.80 | ~0.70 | | | | |

The best cell (−SSR × trend, 1.43 OOS) is the maximum of 47, with an IC of ~0 on its own. It is a trend-filter subset selected by chance, not a signal.

## 3. Additivity (`02_additivity_and_mints.py`)

| Gate × vs | Full | IS | OOS | IS alpha t vs TF | OOS alpha t vs TF | 30/70 blend with TF (Full/IS/OOS) |
|---|---|---|---|---|---|---|
| g3 > 0 | 0.67 | 0.65 | 0.72 | 0.09 | 0.10 | 1.07 / 1.03 / 1.16 |
| **g7 > 0** | 0.96 | 0.94 | 1.00 | 0.94 | 0.66 | **1.17 / 1.13 / 1.26** |
| g14 > 0 | 0.82 | 1.02 | 0.48 | 1.21 | −0.50 | 1.12 / 1.15 / 1.05 |

## 4. Mint events (Griffin–Shams style)

Excess forward ETH log-return over the unconditional mean. t is deflated by √H for overlapping windows.

| Threshold | Condition | H | n IS | ex bp IS | t IS | n OOS | ex bp OOS | t OOS |
|---|---|---|---|---|---|---|---|---|
| q80 | all | 1 | 196 | +32 | 0.76 | 206 | +25 | 1.08 |
| q90 | all | 3 | 95 | +55 | 0.39 | 92 | +132 | 1.31 |
| q95 | all | 3 | 49 | +133 | 0.59 | 44 | +165 | 1.48 |
| q80 | after ETH −7d < 0 | 3 | 83 | +188 | 1.19 | 85 | −19 | −0.16 |
| q90 | after ETH −7d < 0 | 1 | 33 | +21 | 0.19 | 31 | +130 | 1.88 |

Signs are mostly positive, but no cell reaches significance in both halves, and events are too rare (≈ 10–35 per year) to carry a strategy.

## 5. Ethereum-chain stablecoins (DefiLlama, 2020-06+, `03_eth_chain.py`)

| Gate × vs | Full | IS | OOS | ρ to TF |
|---|---|---|---|---|
| trend filter (same window) | 1.23 | 1.26 | 1.20 | 1.00 |
| vol-scaled B&H | 0.87 | 1.21 | 0.44 | — |
| all-chain supply g7 > 0 | 1.36 | 1.58 | 1.10 | 0.70 |
| Ethereum-chain supply g7 > 0 | 1.16 | 1.50 | 0.72 | 0.65 |
| Ethereum share of supply g7 > 0 | 1.03 | 1.20 | 0.83 | 0.48 |

## Lookahead / PIT notes

- A one-day extra lag on every supply series: value stamped D−1 is used at the D+1 00:00 close.
- Stablecoin supply is not revised materially (it is an on-chain token count), but DefiLlama's chain coverage is backfilled. Hence the 2020-06 start for that source.
- Rolling z-scores use trailing windows only.

## Verdict

**Failed.** Stablecoin issuance does carry information about ETH at a weekly horizon, but it is the same information as ETH's own trend. The binding constraint is **redundancy** (ρ 0.6–0.8 with the live trend filter, alpha t < 1, blend lift ≤ 0.06), not cost. The slow-growth version that looks strong in papers built on 2019–2021 data **reverses sign OOS**.

**Variants tried:** 33 IC cells, 47 long/flat strategies, 3 additivity gates × 2 blends, 27 mint cells, and 6 Ethereum-chain gates (≈ 120).

## Files

- `code/spot-eth/stablecoin-supply-flow/fetch_stablecoins.py` — DefiLlama fetcher
- `code/spot-eth/shared/coinmetrics.py` — CoinMetrics community fetcher (also used by later ideas)
- `code/spot-eth/stablecoin-supply-flow/01_signals.py` (+ `01_signals.csv`), `02_additivity_and_mints.py`, `03_eth_chain.py`
