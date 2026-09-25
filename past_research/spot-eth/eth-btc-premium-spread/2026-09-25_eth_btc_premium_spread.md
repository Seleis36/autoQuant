# eth-btc-premium-spread — ETH's USD-venue premium relative to BTC's, as an ETH/BTC pair signal

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT/BTCUSDT and Coinbase ETH-USD/BTC-USD hourly, 2017-10 → 2026-09-24)
**Short name:** `eth-btc-premium-spread`
**Status:** **Failed**

## TL;DR

`eth-venue-premium` showed that the ETH and BTC Coinbase/Binance premium z-scores correlate 0.90 and their states agree 91% of hours. The hope was that the **residual**, meaning ETH-specific USD-venue demand (US spot ETH ETF creations, US-hours DeFi flows), times a *market-neutral* ETH/BTC pair and so gives an edge uncorrelated with every long-ETH sleeve. It does not pay. The spread `z_e − z_b` predicts the next 1–4 h of the ETH/BTC ratio (IC 0.02–0.04 in both halves) but is worth only **2–10 bp** per hour (D10−D1). A pair trade pays **40 bp per round trip** across two legs. Every costed hysteresis config loses: gross Sharpe 0.1–1.1, **net −0.7 to −7.9**.

## Setup

- `z_e`, `z_b` = 720-hour z-scores of (Coinbase close / Binance close − 1) for ETH and BTC. Spread `s = z_e − z_b`, or the z-score of the raw premium difference.
- Target: forward log change of Binance ETHUSDT/BTCUSDT over H ∈ {1, 4, 24, 72} h. IS ≤ 2023, OOS 2024+.
- Pair: dollar-neutral `{ETH: +p, BTC: −p}`, `p = hysteresis(s) × min(0.20/σ_ratio, 1)`, hourly, 10 bp per side on each leg (simulated book).

## 1. Information content (`01_spread_ic.py`)

| Signal | H | IC IS | D10−D1 bp IS | IC OOS | D10−D1 bp OOS |
|---|---|---|---|---|---|
| z_e − z_b | 1 | 0.044 | 8.7 | 0.031 | 2.0 |
| z(pe − pb) | 1 | 0.044 | 9.3 | 0.032 | 2.9 |
| z_e − z_b | 4 | 0.020 | 9.7 | 0.021 | 4.3 |
| z_e − z_b | 24 | 0.003 | 1.7 | 0.010 | 9.7 |
| z_e − z_b | 72 | −0.010 | −6.2 | 0.031 | 37.7 |
| z_e (ETH premium alone) | 24 | −0.012 | 19.5 | 0.043 | 18.9 |

The relative premium is a **1-hour convergence effect** (Binance ETH catching up with Coinbase ETH faster than BTC does), not a directional flow. At 24 h and beyond it carries nothing about the ratio.

## 2. Costed pair (`02_pair_bt.py`, 8 configs)

| enter | exit | gross Sharpe | net Full | net IS | net OOS | Turnover/yr |
|---|---|---|---|---|---|---|
| 1.0 | 0.0 | 0.99 | −6.25 | −6.61 | −5.75 | 627 |
| 1.5 | 0.0 | 0.55 | −3.41 | −3.68 | −3.05 | 214 |
| 2.0 | 0.0 | 0.49 | −1.52 | −1.62 | −2.08 | 81 |
| 3.0 | 0.0 | 0.07 | −0.72 | −0.75 | −1.32 | 20 |
| 3.0 | 0.5 | −0.05 | −0.86 | −0.92 | −1.32 | 20 |

Raising the entry threshold cuts turnover faster than it concentrates edge. Gross Sharpe falls to zero before the costs stop dominating.

## Verdict

**Failed.** The binding constraint is **cost vs horizon**: 2–10 bp of 1–4 h information against a 40 bp round trip. The ETH-specific part of the venue premium is microstructure (arbitrage lag), not flow. The directional content of the premium is common to ETH and BTC and is already used by `eth-venue-premium`.

**Variants tried:** 16 IC cells + 8 costed pairs.

## Files

- `code/spot-eth/eth-btc-premium-spread/01_spread_ic.py`
- `code/spot-eth/eth-btc-premium-spread/02_pair_bt.py`
