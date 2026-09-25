# eth-venue-premium — the USD-venue vs Binance-USDT price premium as a spot-ETH timing signal

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT and Coinbase ETH-USD, hourly, 2017-08 → 2026-09-24)
**Short name:** `eth-venue-premium`
**Status:** **Working**. OOS Sharpe 1.49 at 10 bp/side on a pre-registered replication. It is an upgrade to the ETH trend sleeve (ρ 0.85 with the live `eth-trend-filter`), not an independent edge.

## TL;DR

`spot-btc/coinbase-premium` found that the Coinbase BTC-USD price relative to Binance BTCUSDT predicts BTC over the next 1–24 h, and that the information sits in the Binance-USDT leg (USDT/USD demand). It is live on BTC. After seven failed ETH-native ideas this session, the natural question was whether the same signal times ETH. **The BTC spec was applied to ETH with every parameter unchanged, fixed before any ETH number was computed.** The trend and vol parameters are the BTC spec's, not the ETH trend filter's.

| Variant (10 bp/side) | Full | IS ≤ 2023 | OOS 2024 → | IS ≤ 2022 | OOS 2023 → | MaxDD |
|---|---|---|---|---|---|---|
| **PRIMARY: premium state × SMA50d × vol 40%** | **1.38** | **1.33** | **1.49** | 1.43 | 1.31 | **−29%** |
| same base without the premium (SMA50d × vol 40%) | 1.17 | 1.20 | 1.10 | 1.20 | 1.13 | −31% |
| live `eth-trend-filter` (SMA40 daily × vol 50%) | 1.22 | 1.22 | 1.23 | 1.27 | 1.15 | −45% |
| ETH buy & hold | 0.70 | — | — | — | — | −94% |

The premium adds **+0.13 IS / +0.39 OOS** Sharpe over the identical base, and 2022 goes from −0.57 to +0.12. The result survives a 144-cell parameter neighbourhood (72% of cells OOS > 1, IS→OOS rank correlation **+0.58**), walk-forward re-selection (**1.34**), a 30-day block bootstrap (P(Sh > 1) = **86%**), 20 bp costs (**1.08**), a vectorbt re-implementation (1.37 vs 1.38), and a truncation lookahead test (12/12 identical).

## Motivation

Four of the session's first seven ideas failed for the same reason: whatever carried information about ETH was re-expressing ETH's own trend. The BTC premium study reported the opposite property: *gating trend × vol on the premium adds Sharpe in both halves* and its "no trend, vol only" version stands on its own. That makes it the strongest available candidate for improving on the live ETH sleeve. The mechanism is exchange-level demand. When USD-venue ETH trades rich to Binance USDT, dollars are arriving (or USDT is at a discount, because offshore holders are exiting to fiat). Arbitrage closes the gap within hours, but the directional flow that opened it persists for a day or so.

## Data

- `bars.load_bars("ETHUSDT", "1h", resample_from="1m")` — Binance spot, bar-open stamps, UTC. This is the traded series.
- `data/COINBASE_ETHUSD_1h.parquet` — Coinbase Exchange public candles, 2017-08-01 → now, 80,193 bars. Fetcher: `code/spot-eth/eth-venue-premium/fetch_coinbase.py` (incremental). `data/COINBASE_BTCUSD_1h.parquet` was refreshed by the same fetcher.
- **Alignment:** Binance vs Coinbase hourly return correlation is **0.970 at lag 0**, −0.004 at lag −1 and −0.011 at lag +1. The stamps are the same convention.
- **Premium level (bp; mean, std by year):** 2017 +135 / 224 · 2018 −37 / 110 · 2019 −5 / 57 · 2020 +5 / 17 · 2021 +6 / 9 · 2022 −1 / 9 · 2023 +2 / 10 · 2024 −1 / 6 · 2025 0 / 5 · 2026 −6 / 6. 2017–18 are the USDT de-peg years. The 30-day z-score normalises them away.
- Protocol: IS ≤ 2023-12-31 / OOS ≥ 2024-01-01 (this asset class's split), also reported on the BTC study's ≤ 2022 / ≥ 2023 split. 10 bp per side on every weight change. Sharpe is on UTC-daily compounded returns (ann. 365).

## The signal (`strategy.py`)

```
prem_t  = Coinbase_ETHUSD_close_t / Binance_ETHUSDT_close_t − 1
z_t     = (prem_t − mean_720(prem)) / std_720(prem)
state_t = 1 after z > 0, 0 after z < −1.5 (hysteresis; NaN keeps state)
w_t     = state_t × 1{C_t > SMA_1200h(C)} × min(0.40 / EWMvol_480h(ret)·√8760, 1)
```

The hysteresis keeps turnover at ~76×/yr instead of the ~700×/yr an hourly threshold would churn.

## 1. Pre-registered replication and references (`01_replicate.py`, 8 variants)

| Variant | Full | IS | OOS | CAGR | MDD | AvgExp | Turn | ρ to live TF |
|---|---|---|---|---|---|---|---|---|
| **PRIMARY** | **1.38** | **1.33** | **1.49** | 39% | −29% | 0.23 | 76 | 0.84 |
| SMA50d × vol40 (no premium) | 1.17 | 1.20 | 1.10 | 35% | −31% | 0.29 | 46 | 0.93 |
| live eth-trend-filter | 1.22 | 1.22 | 1.23 | 46% | −45% | 0.34 | 17 | 1.00 |
| premium × vol40, no trend | 1.35 | 1.40 | 1.22 | 50% | −56% | 0.41 | 80 | 0.67 |
| premium × SMA40d × vol50 (ETH-TF parameters) | 1.40 | 1.42 | 1.37 | 51% | −36% | 0.28 | 99 | 0.85 |
| **BTC** premium × SMA50d × vol40, traded on ETH | 1.46 | 1.39 | 1.65 | 42% | −26% | 0.23 | 68 | 0.83 |
| BTC premium × vol40, no trend | 1.35 | 1.29 | 1.47 | 50% | −57% | 0.40 | 70 | 0.66 |
| live eth-trend-filter × premium state | 1.46 | 1.41 | 1.57 | 53% | −42% | 0.27 | 60 | 0.90 |

Every way of adding the premium to a trend × vol base improves it in both halves. The BTC-premium version is slightly better OOS, but it was not the pre-registered spec and is kept as a documented alternative.

**Yearly Sharpe (PRIMARY vs same base without premium vs live TF):**

| | 2017* | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|---|---|---|
| PRIMARY | 2.08 | −0.79 | 0.47 | 3.02 | 2.22 | **0.12** | 0.91 | **2.09** | 1.52 | 0.73 |
| base (no premium) | 2.57 | −0.26 | 0.52 | 2.77 | 1.60 | −0.57 | 1.21 | 0.78 | 1.40 | 1.18 |
| live TF | 3.01 | −0.11 | 0.66 | 2.97 | 1.75 | −0.79 | 0.97 | 0.69 | 1.67 | 1.44 |

\* partial years. PRIMARY yearly returns: 2018 −9.9%, 2019 +9.0%, 2020 +166%, 2021 +87%, 2022 +0.6%, 2023 +27%, 2024 +68%, 2025 +39%, 2026 YTD +14%. The worst calendar-year drawdown is −27% (2023).

## 2. Robustness (`02_robustness.py`)

**(a) Parameter neighbourhood.** z-window {360, 720, 1440} × enter {−0.5, 0, 0.5, 1} × exit {−1, −1.5, −2} × trend {none, SMA40d, SMA50d, SMA100d} = **144 cells**:

| Trend | Full min / median / max | IS min / median / max | OOS min / median / max |
|---|---|---|---|
| none | 0.71 / 1.23 / 1.55 | 0.78 / 1.28 / 1.62 | 0.48 / 1.08 / 1.73 |
| SMA40d | 0.91 / 1.30 / 1.55 | 1.04 / 1.33 / 1.56 | 0.60 / 1.25 / 1.65 |
| SMA50d | 0.88 / 1.27 / 1.45 | 0.95 / 1.25 / 1.53 | 0.71 / 1.30 / 1.73 |
| SMA100d | 0.70 / 1.09 / 1.37 | 0.85 / 1.17 / 1.47 | 0.35 / 0.92 / 1.32 |

72% of cells have OOS > 1, and IS→OOS Spearman is **+0.58**: the ranking is stable, unlike every price-only grid this session. PRIMARY sits in the middle of the z = 720 / SMA50d plateau (its row: 1.18–1.43 full across the 12 enter/exit pairs).

**(b) Cost:** 0 bp 1.67 / 1.64 / 1.75 · 5 bp 1.52 / 1.49 / 1.62 · **10 bp 1.38 / 1.33 / 1.49** · 20 bp 1.08 / 1.02 / 1.23 · 30 bp 0.79 / 0.71 / 0.97 (full / IS / OOS).

**(c) Execution delay** (state lagged extra hours): +1 h 1.23 / 1.09 / **1.55** · +2 h 1.17 / 1.05 / 1.46 · +3 h 1.05 / 0.89 / 1.42 · +6 h 1.11 / 0.99 / 1.40. The first hour carries part of the IS edge, mostly the 2017–19 period when the premium was large and converged quickly. The OOS edge is a slower directional effect and does not depend on speed.

**(d) Bootstrap and deflation:** 30-day block bootstrap of daily returns (2000 draws): mean 1.38, 5–95% **[0.77, 1.96]**, P(Sh > 0) = 100%, **P(Sh > 1) = 86%**. Deflated Sharpe: 1.00 at 1 trial (the honest count for a pre-registered spec), 0.97 at 100, **0.94 at 250** (every configuration evaluated in this idea).

**(e) Walk-forward:** every 90 days, pick the best trailing-730-day Sharpe among the 144 cells and apply it for 90 days (2019-10 → 2026-09). Result: **1.34** (IS part 1.37 / OOS part 1.29), CAGR 44%, MDD −36%. PRIMARY on the same window: 1.52 / 1.55 / 1.49. Selection mostly chooses z-window 720, and slightly degrades rather than improves on the fixed spec.

**(f) Which premium:** the ETH and BTC premium z-scores correlate **0.90**, and their hysteresis states agree **91%** of hours. That is consistent with a common USDT/USD driver. PRIMARY on the ETH premium 1.38 / 1.33 / 1.49; BTC premium 1.46 / 1.39 / 1.65; mean z 1.39 / 1.34 / 1.49; both states required 1.43 / 1.35 / 1.62.

**(g) Overlap with live books:** daily-return correlation **0.85** with `spot-eth/eth-trend-filter` and **0.60** with `spot-btc/coinbase-premium` (its published spec replayed on BTC).

## 3. Validation of the deployable function (`03_validate.py`)

- `strategy.target_weight` reproduces PRIMARY exactly: 1.377 daily Sharpe.
- **vectorbt** (`Portfolio.from_orders`, targetpercent, 10 bp fees, fills at bar close) gives **1.366**, total return 18.2× vs 18.7×. The small gap is vectorbt re-trading price drift every bar. (A first attempt that passed `w.shift(1)` to vectorbt returned 1.18. That was an extra hour of lag introduced in the cross-check itself and is consistent with (c).)
- **Truncation test:** weights recomputed from data cut at 12 random timestamps equal the full-sample weights at those stamps (12/12). Nothing reads the future.
- Stacking the session's Thursday skip (`session-momentum`) gives 1.41 / 1.36 / 1.55, MDD −32%. It is **not adopted**, to keep the replicated spec identical to what runs on BTC.

## Lookahead / PIT checklist

- z-score, SMA and EWM vol are trailing, and the hysteresis is causal. The weight at t uses closes ≤ t on both venues and is applied to t → t+1 by `backtest`.
- The Coinbase premium is computed on the intersection of stamps. Missing Coinbase hours keep the previous state.
- Coinbase and Binance candles are final exchange prints (no revisions) and are available live from public endpoints with no key.
- The spec was fixed before any ETH result (the BTC parameters). All tuning afterwards is reported as neighbourhood or walk-forward, not used.

## What this idea is not

- **Not an independent edge.** ρ 0.85 to the live ETH trend sleeve. Deployed next to it, it roughly doubles the same ETH-long exposure. Deployed *instead of* it, it improves OOS Sharpe by ~0.26 and cuts MaxDD from −45% to −29%, at 4.5× the turnover and lower CAGR (39% vs 46%, because average exposure is 0.23 vs 0.34).
- **Shares a driver with the live BTC sleeve** (ρ 0.60). A USDT/USD regime change would hit both.
- **Cost-sensitive at the margin:** 1.08 at 20 bp. Market orders on the testnet at 10 bp are inside the budget. Slippage on real size was not modelled.

## Verdict

**Working.** Pre-registered, OOS 1.49, walk-forward 1.34, bootstrap P(Sh > 1) 86%, DSR 0.94 at 250 trials, and robust across 144 neighbouring configs. Deployable long/flat on the Binance spot testnet with public inputs.

**Variants tried:** 8 replication variants + 144 neighbourhood + 5 cost + 5 lag + 4 premium sources + 1 Thursday stack = **167**.

## Files

- `code/spot-eth/eth-venue-premium/fetch_coinbase.py` — Coinbase hourly fetcher (incremental)
- `code/spot-eth/eth-venue-premium/01_replicate.py` — pre-registered replication and references
- `code/spot-eth/eth-venue-premium/02_robustness.py` (+ `02_neighbourhood.csv`) — neighbourhood, cost, lag, bootstrap, walk-forward, sources, overlap
- `code/spot-eth/eth-venue-premium/03_validate.py` — vectorbt cross-check, truncation test, figures
- `code/spot-eth/eth-venue-premium/strategy.py` — `target_weight(binance_close, coinbase_close)`
- `alphas/spot-eth/eth-venue-premium/2026-09-25_alpha_spec.md`, `equity.png`, `equity.csv`
