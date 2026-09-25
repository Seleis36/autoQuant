# upshock-continuation — riding ETH after extreme short-horizon up-moves

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT 1m → 1h bars, 2017-09 → 2026-09-24)
**Short name:** `upshock-continuation`
**Status:** **Failed** as a new edge. It is profitable standalone (Sharpe 1.12 full / 1.27 OOS) but not additive to the live `eth-trend-filter`, and marginal after deflation.

## TL;DR

This idea came out of the `flush-rebound` event study. ETH down-shocks do not revert, but **up-shocks continue**: after a 1–24 h rise of more than 2–4 ex-ante sigmas, forward 12–48 h returns beat the unconditional drift in both halves (mean t **1.24 IS / 1.16 OOS** over 120 cells). Plausible mechanisms are attention/FOMO inflow and short-liquidation cascades on perps. That is intraday time-series momentum (Shen, Urquhart & Wang 2022 find the same in BTC; Wen et al. 2022 in the cross-section of majors).

The selection-free version — the mean of 45 hold indicators over k ∈ {1,2,4,8,12} h, Z ∈ {2,2.5,3}, H ∈ {12,24,48} h — gated by ETH > 40d SMA, earns **Sharpe 1.12 full / 1.07 IS / 1.27 OOS** at 10 bp/side, MaxDD −26%, average exposure 11%. However:

1. It is **0.64 correlated** with the live `eth-trend-filter`, and its alpha after regressing on that strategy is **t_NW 0.99 IS / 1.01 OOS** (not significant).
2. Every way of combining it with the trend filter (overlay, additive, multiplicative, return blend) leaves the OOS Sharpe at 1.19–1.24, against 1.23 for the trend filter alone.
3. **Deflated Sharpe 0.86** at the honest trial count (129), below 0.95.
4. Turnover is 69×/yr, so it is **cost-fragile**: Sharpe 0.84 at 20 bp and 0.56 at 30 bp.

It is a real effect, but in this asset class it is a subset of the trend exposure we already run.

## Data and conventions

The same setup as `flush-rebound`: hourly bars left-labelled at the open (UTC); the event at the close of bar t uses `z_k = log(C_t/C_{t−k}) / (σ_{t−k}√k)`, with σ the EWM(168 h) std of 1h log returns lagged k bars. Long from the close of the event bar for H hours (a re-trigger extends the hold). `research_lib.backtest` applies the weight to the next bar. Costs are 10 bp per side. Sharpe is computed on UTC-daily compounded returns. IS ≤ 2023-12-31, OOS ≥ 2024-01-01.

The trend-filter reference is the live spec (`1{C > SMA40d} × min(0.5/EWMvol20, 1)` on 00:00 UTC closes), replayed on the hourly grid with the daily weight applied from the next 00:00. It gives **1.22 full / 1.22 IS / 1.23 OOS**.

## 1. Event study split by trend state (`01_grid.py`)

Excess forward return over the *same-state* unconditional mean, averaged across 45 cells (k × Z × H):

| State | excess bp IS | excess bp OOS | mean t IS | mean t OOS |
|---|---|---|---|---|
| all | +61 | +38 | 1.77 | 1.13 |
| uptrend (C > 40d SMA) | +57 | **+73** | 1.33 | **1.35** |
| downtrend | +38 | −36 | 0.78 | −0.24 |

The continuation lives in uptrends only. In downtrends, up-shocks are bear-market rallies that fail OOS.

## 2. Costed single-cell grid (45 configs, `01_grid.py`)

| Stat | Full | IS | OOS |
|---|---|---|---|
| Median Sharpe of 45 cells | 0.74 | 0.84 | 0.64 |
| Best full-sample cell (k12 Z2 H48) | 1.30 | 1.48 | 0.83 |
| IS→OOS Spearman | | | −0.22 |

The IS→OOS Spearman is negative, so picking a single cell is hopeless. Hence the ensemble.

## 3. Ensemble, gating, sizing, combination (`02_ensemble.py`, 12 variants)

| Variant | Full | IS | OOS | CAGR | MDD | AvgExp | Turnover | ρ to TF |
|---|---|---|---|---|---|---|---|---|
| trend filter (live) | 1.22 | 1.22 | 1.23 | 46% | −45% | 0.34 | 17 | 1.00 |
| E = mean of 45 cells | 1.04 | 1.15 | 0.74 | 31% | −35% | 0.18 | 90 | 0.53 |
| E_any (in any cell) | 0.73 | 0.97 | 0.05 | 30% | −76% | 0.66 | 119 | 0.60 |
| E × vol-scalar | 1.01 | 1.13 | 0.78 | 19% | −27% | 0.12 | 62 | 0.56 |
| E_any × vol-scalar | 0.64 | 0.97 | −0.04 | 20% | −70% | 0.45 | 85 | 0.64 |
| **E × uptrend** | **1.12** | **1.07** | **1.27** | 28% | **−26%** | 0.11 | 69 | 0.64 |
| E_any × uptrend × vs | 1.10 | 1.34 | 0.57 | 35% | −38% | 0.25 | 84 | 0.84 |
| max(w_TF, E_any × vs) | 0.79 | 0.97 | 0.39 | 30% | −70% | 0.55 | 51 | 0.78 |
| min(1, w_TF + E × vs) | 1.21 | 1.27 | 1.07 | 56% | −51% | 0.43 | 58 | 0.95 |
| w_TF × (1 + E), cap 1 | 1.23 | 1.23 | 1.24 | 57% | −46% | 0.38 | 35 | 0.98 |
| 0.5 w_TF + 0.5 E_any × vs | 1.00 | 1.19 | 0.55 | 35% | −49% | 0.39 | 51 | 0.89 |

Return blends of the trend filter with `3·E·uptrend` (`03_alpha_vs_tf.py`): 75/25 → 1.27 / 1.29 / **1.23**; 50/50 → 1.27 / 1.31 / **1.19**. MaxDD improves from −45% to −33–36%, but OOS Sharpe does not move.

**Regression of E × uptrend on the trend filter (daily returns):**

| | beta | alpha/yr | t_NW | IR |
|---|---|---|---|---|
| IS | 0.47 | 6.7% | 0.99 | 0.34 |
| OOS | 0.41 | 9.1% | 1.01 | 0.60 |

## 4. Robustness of E × uptrend (`04_robustness.py`)

| Cost/side | Full | IS | OOS |
|---|---|---|---|
| 0 bp | 1.39 | 1.34 | 1.57 |
| 5 bp | 1.26 | 1.21 | 1.42 |
| **10 bp** | **1.12** | **1.07** | **1.27** |
| 20 bp | 0.84 | 0.81 | 0.96 |
| 30 bp | 0.56 | 0.54 | 0.65 |

Yearly Sharpe: 2017 1.44 · 2018 −0.57 · 2019 0.54 · 2020 2.92 · 2021 1.55 · **2022 0.99** (the trend filter lost −0.79 that year) · 2023 0.03 · 2024 1.38 · 2025 1.69 · 2026 0.53.

Deflated Sharpe (Bailey–López de Prado, skew/kurtosis-adjusted): 0.98 at 12 trials (the ensemble variants only), 0.92 at 57, **0.86 at 129** (all configurations evaluated in this idea, including the 72 flush-rebound configs whose event study spawned it).

## Lookahead check

σ is lagged k bars, events use closes ≤ t, and the 40d-SMA gate is evaluated at t. The weight is applied from bar t+1 by `backtest`. The trend-filter replay uses daily closes known at 00:00 UTC and applies them from that stamp onward.

## Verdict

**Failed** as a new, deployable edge. The binding constraint is **redundancy with the live trend filter** (ρ 0.64, alpha t ≈ 1). Secondary constraints are cost fragility (turnover 69×/yr) and a DSR below 0.95. The effect itself is genuine and asymmetric: ETH has momentum after up-shocks and no reversal after down-shocks. The next researcher should not re-test it as a timing overlay on the trend filter; all four overlay forms were tried here.

**Variants tried:** 135 event cells, 45 costed single cells, 12 ensemble/combination variants, and 2 blends.

## Files

- `code/spot-eth/upshock-continuation/01_grid.py` (+ `01_grid.csv`, `01_event_by_state.csv`)
- `code/spot-eth/upshock-continuation/02_ensemble.py`
- `code/spot-eth/upshock-continuation/03_alpha_vs_tf.py`
- `code/spot-eth/upshock-continuation/04_robustness.py`
