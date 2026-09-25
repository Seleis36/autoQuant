# exchange-netflow — ETH exchange in/outflows as a distribution / accumulation signal

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT daily closes at 00:00 UTC, 2018-06 → 2026-09-24)
**Short name:** `exchange-netflow`
**Status:** **Failed**

## TL;DR

The hypothesis: ETH sent to exchanges is about to be sold, and ETH withdrawn (to cold storage, staking or DeFi) is being accumulated. So net outflows should be bullish, and inflows during rallies ("distribution") bearish. On CoinMetrics community exchange flows (`FlowInExNtv`, `FlowOutExNtv`, `SplyExNtv`), lagged one extra day:

- **ICs are small.** The best is 7-day net-outflow z vs 7-day forward return: 0.055 IS / 0.100 OOS. The 30-day ICs of most signals shrink or flip OOS.
- **Gates add nothing.** Median of 60 vol-scaled long/flat gates: Sharpe 0.51 full / 0.40 OOS, no better than vol-scaled buy-and-hold (0.62 / 0.44). Median of 60 trend-filter × flow gates: 0.69 / 0.99, below the ungated trend filter's 1.10 / 1.20.
- **Price/flow divergence.** "Accumulation" (ETH down while outflows are high) earns +50 to +300 bp over the next 7 days in both halves (t 0.25–1.2), then **gives it back by day 30**. A "distribution veto" on the trend filter cuts IS Sharpe (1.06 → 0.81–1.05) while nudging OOS up (1.20 → 1.14–1.39). That in-sample/out-of-sample disagreement is what noise looks like.
- **The data is not point-in-time.** CoinMetrics re-tags exchange addresses (`SplyExNtv` jumps 13.4 M → 19.3 M ETH in H1 2025 as new entities are labelled), so even these weak numbers are an upper bound.

## Data

- `data/COINMETRICS_ETH_d.parquet` (`code/spot-eth/shared/coinmetrics.py`, community API): `FlowInExNtv`, `FlowOutExNtv`, `SplyExNtv`, `SplyCur` from 2015.
- Value stamped D−1 used at the close of bar D (D+1 00:00 UTC), 10 bp per side, weights applied next day. IS 2018-06 → 2023-12, OOS 2024+.
- Sanity: daily net flow and ΔSplyExNtv correlate 0.76. The residual has spikes up to 5.4 M ETH, which are entity (re)labelling events, not flows.

## 1. Signals and ICs (`01_flows.py`)

For n ∈ {1, 3, 7, 14, 30} days, each z-scored against its trailing 365 days:
`−nf_n` = −(Σ inflow − Σ outflow)/supply; `−dSx_n` = −Δlog exchange supply; `−in_n` = −log Σ inflow; `out/in_n` = log(Σ outflow / Σ inflow).

| Signal | 7d IS | 30d IS | 7d OOS | 30d OOS |
|---|---|---|---|---|
| −nf7 | 0.055 | 0.112 | **0.100** | 0.033 |
| −nf30 | 0.096 | 0.059 | 0.000 | 0.024 |
| −dSx7 | 0.067 | 0.129 | 0.087 | 0.026 |
| −dSx30 | 0.124 | 0.085 | −0.010 | −0.058 |
| −in7 | −0.064 | −0.126 | −0.049 | −0.089 |
| out/in7 | 0.060 | 0.119 | 0.058 | 0.009 |

Inflow level has the "wrong" sign in both halves: heavy inflows come with active bull markets, not with tops.

## 2. Long/flat strategies (120 variants)

20 signals × 3 thresholds × {vol-scaled gate, trend-filter × gate}:

| Group | median Full | median IS | median OOS |
|---|---|---|---|
| gate × vol scalar (60) | 0.51 | 0.52 | 0.40 |
| trend filter × gate (60) | 0.69 | 0.60 | 0.99 |
| trend filter alone (ref) | 1.10 | 1.06 | 1.20 |
| vol-scaled buy & hold (ref) | 0.62 | 0.72 | 0.44 |

The top cells (for example `out/in30 > 0 × TF`, 1.19 / 1.08 / 1.46, ρ 0.74 to TF) are the upper tail of 120 draws around a median below the reference.

## 3. Price/flow divergence (`02_divergence.py`, 36 event cells + 4 vetoes)

| Event | n | Z | H | n IS | ex bp IS | t IS | n OOS | ex bp OOS | t OOS |
|---|---|---|---|---|---|---|---|---|---|
| accumulation | 7 | 0.5 | 7 | 243 | +249 | 1.20 | 124 | +140 | 0.79 |
| accumulation | 7 | 0.5 | 30 | 243 | +878 | 0.91 | 120 | −218 | −0.24 |
| accumulation | 14 | 1.0 | 30 | 137 | +720 | 0.67 | 75 | −700 | −0.64 |
| distribution | 14 | 1.5 | 7 | 32 | −836 | −1.77 | 30 | −11 | −0.02 |

| Trend filter with distribution veto | Full | IS | OOS |
|---|---|---|---|
| none (ref) | 1.10 | 1.06 | 1.20 |
| n7, Z1.0 | 0.99 | 0.81 | 1.39 |
| n7, Z1.5 | 1.04 | 0.92 | 1.30 |
| n14, Z1.0 | 1.05 | 0.99 | 1.19 |
| n14, Z1.5 | 1.07 | 1.05 | 1.14 |

## Verdict

**Failed.** Exchange flows hold at most a weak weekly signal that is neither strong enough to trade alone nor additive to the trend filter. The data vintage is not point-in-time, which by itself would block deployment. The binding constraint is **signal strength** (IC ≤ 0.10), with a PIT problem on top.

**Variants tried:** 60 IC cells, 120 strategies, 36 divergence cells, and 4 vetoes.

## Files

- `code/spot-eth/exchange-netflow/01_flows.py` (+ `01_flows.csv`)
- `code/spot-eth/exchange-netflow/02_divergence.py`
