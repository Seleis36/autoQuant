# eth-btc-relative-momentum — trend-following the ETH/BTC ratio as a dollar-neutral pair

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT & BTCUSDT daily closes at 00:00 UTC, 2017-12 → 2026-09-24)
**Short name:** `eth-btc-relative-momentum`
**Status:** **Failed**

## TL;DR

This is the market-neutral cousin of the ETH/BTC gate that `eth-trend-filter` rejected: trade the ratio itself, long ETH / short BTC when the ratio trends up and the reverse when it trends down (simulated book, 10 bp per side on each leg). It is uncorrelated with the live trend filter by construction (ρ ≈ 0.0–0.15), which is why it was worth testing after four trend-redundant results. **It has no stable edge.** Median Sharpe across 32 ratio-momentum configs is **0.21 full / 0.17 IS / 0.09 OOS**. Short lookbacks (7–14 d) earn 0.9–1.1 IS and **−0.5 to −0.7 OOS**. The ratio trended hard in 2018–21 and has chopped since 2022. Beta-hedged residual momentum shows the same flip (7d: **+1.30 IS → −1.24 OOS**). A risk-on/off pair keyed to BTC's trend peaks at 0.49 full. Short-horizon ratio *reversal* loses in both halves (−1.8 IS / −0.6 OOS), so there is no stable sign to exploit at any horizon.

## Setup

- Pair exposure `s ∈ [−1, 1]`: weights `{ETH: +s, BTC: −s}` (dollar-neutral) or `{ETH: +s, BTC: −β s}` (beta-hedged, β = EWM-60d beta clipped to [0.5, 2]).
- Sizing: raw (±1 per leg, gross 2) or vol-targeted to 20% annualised on the ratio (EWM-20d), capped at 1 per leg.
- `research_lib.backtest_xs`: weights known at the D+1 00:00 close are applied to the next day; costs are charged on Σ|Δw|.
- IS 2017-12 → 2023-12, OOS 2024-01 → 2026-09.

## 1. Ratio time-series momentum (`01_ratio_tsmom.py`, 32 configs)

| Signal | Sizing | Full | IS | OOS | MDD | Turnover | ρ to TF |
|---|---|---|---|---|---|---|---|
| sign(7d ratio return) | raw | 0.54 | 0.91 | −0.59 | −77% | 229 | 0.13 |
| sign(14d) | raw | 0.73 | **1.14** | **−0.52** | −78% | 159 | 0.14 |
| sign(30d) | raw | 0.45 | 0.52 | 0.28 | −82% | 108 | 0.09 |
| sign(60d) | vt20 | 0.22 | 0.18 | 0.30 | −48% | 36 | 0.00 |
| sign(180d) | vt20 | 0.31 | 0.41 | 0.09 | −31% | 25 | 0.02 |
| MACD 4/16 (Baz-style, tanh) | raw | 0.38 | 0.39 | 0.34 | −51% | 21 | 0.10 |
| MACD 32/128 | raw | −0.14 | −0.08 | −0.29 | −53% | 5 | −0.13 |
| ensemble of signs 7–180 d | vt20 | 0.38 | 0.57 | 0.01 | −37% | 50 | 0.05 |
| ensemble of MACDs | vt20 | 0.08 | 0.08 | 0.08 | −20% | 6 | −0.06 |
| **median of 32** | | **0.18–0.21** | **0.15–0.17** | **0.09–0.10** | | | |

Yearly Sharpe of the 7–180 d sign ensemble: 2018 +1.94, 2019 +0.86, 2020 +0.70, 2021 +1.15, **2022 −1.34, 2023 −0.16, 2024 −0.76**, 2025 +0.87, 2026 −0.05. Log ETH/BTC change per year: 2018 −0.41, 2019 −0.68, 2020 +0.35, 2021 +1.14, 2022 −0.10, 2023 −0.29, 2024 −0.41, 2025 −0.05. The trending years made the IS record. Since 2022 the ratio has drifted down in a choppy way that whipsaws every lookback.

## 2. Re-framings (`02_reframings.py`, 12 configs)

| Variant | Full | IS | OOS | MDD | ρ to TF |
|---|---|---|---|---|---|
| (a) beta-hedged residual momentum 7d | 0.50 | **1.30** | **−1.24** | −61% | 0.11 |
| (a) … 14d | 0.47 | 1.04 | −0.77 | −54% | 0.14 |
| (a) … 60d | 0.26 | 0.56 | −0.38 | −42% | 0.02 |
| (b) risk-on pair (long ETH/short BTC iff BTC > SMA100) | 0.49 | 0.59 | 0.28 | −46% | 0.22 |
| (b) … BTC > SMA20 | 0.14 | −0.05 | 0.57 | −42% | 0.27 |
| (c) ratio reversal 3d | −1.40 | −1.76 | −0.65 | −95% | −0.02 |
| (c) ratio reversal 14d | −1.36 | −1.83 | −0.36 | −94% | −0.15 |

## Lookahead check

Signals use closes ≤ D, β is an EWM of past returns and is applied through `beta.shift(1)` in the residual, and `backtest_xs` shifts weights by one bar. Short-horizon reversal being negative in both halves means short-horizon ratio momentum survives *gross* in both halves. It is the costs (turnover 120–230×/yr on two legs) plus the OOS weakening that make it negative net.

## Verdict

**Failed.** The binding constraint is **regime instability of the ratio's trendiness**: momentum 2018–21, noise since. The IS/OOS sign flip appears in every short and medium lookback, raw and beta-hedged. Uncorrelated with the trend filter, yes, but with no expected return.

**Variants tried:** 44.

## Files

- `code/spot-eth/eth-btc-relative-momentum/01_ratio_tsmom.py` (+ `01_ratio_tsmom.csv`)
- `code/spot-eth/eth-btc-relative-momentum/02_reframings.py`
