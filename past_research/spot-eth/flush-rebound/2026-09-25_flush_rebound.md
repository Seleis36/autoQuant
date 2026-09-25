# flush-rebound — buying ETH after extreme short-horizon drops

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT 1m bars → 1h, 2017-09 → 2026-09-24)
**Short name:** `flush-rebound`
**Status:** **Failed**

## TL;DR

The hypothesis: an extreme 1–24 h drop in ETH is often a perp-liquidation cascade that pushes spot below fair value, so a liquidity provider who buys the flush should earn a rebound (Nagel 2012: reversal returns pay for liquidity provision, and pay more when volatility is high). **It does not hold in ETH.** Across 240 unconditional event cells, down-shocks have mean t-stat **+0.29 IS / −0.31 OOS**. None of the conditioning variables (volume spike, ETH-specific vs market-wide drop, trend regime, perp funding crowding, daily horizon) produces a rebound that shows up in both halves. A costed long/flat grid of 72 configs has median Sharpe **0.08 full / 0.18 IS / −0.33 OOS**, and IS rank is unrelated to OOS rank (Spearman 0.02). The best in-sample config (IS 0.84) returns 0.18 OOS.

The by-product worth keeping is that **up-shocks continue**: mean t **+1.24 IS / +1.16 OOS** across 120 cells. That became its own idea, `upshock-continuation` (see all_ideas.md).

## Data and conventions

- `load_bars("ETHUSDT", "1h", resample_from="1m")` — 1h bars are left-labelled and left-closed, so the bar stamped t covers [t, t+1h) and its close is known at t+1h. Extended to 2026-09-24 with `fetch_binance_vision.py` during this session.
- `load_bars("BTCUSDT", ...)` on the same grid, used for the ETH/BTC ratio shock.
- `data/ETHUSDT_fundingRate.parquet`: 8-hourly funding, forward-filled from its stamp.
- **Event definition:** at the close of bar t, `z_k = log(C_t / C_{t−k}) / (σ_{t−k} · √k)`, where σ is the EWM (halflife 168 h) std of 1h log returns **measured up to t−k**, so the shock does not inflate its own yardstick. Forward return = `log(C_{t+H} / C_t)`, entered at the close of the event bar. Events are de-clustered: after one event, the next is counted only once H hours have passed.
- Split fixed in advance, the same split as `eth-trend-filter`: **IS ≤ 2023-12-31, OOS ≥ 2024-01-01**.
- Costs for the strategy grid: 10 bp per side on |Δw| (the testnet taker fee).

## 1. Unconditional event study (`01_event_study.py`)

Grid: k ∈ {1, 2, 4, 8, 12, 24} h × Z ∈ {2, 2.5, 3, 4} × H ∈ {4, 12, 24, 48, 96} h × {down, up} = 240 cells.

| Side | mean t IS | mean t OOS | median t IS | median t OOS |
|---|---|---|---|---|
| down (rebound) | 0.29 | −0.31 | 0.13 | −0.40 |
| up (continuation) | **1.24** | **1.16** | 1.30 | 1.05 |

Representative down-shock cells:

| k | Z | H | n IS | bp IS | t IS | n OOS | bp OOS | t OOS |
|---|---|---|---|---|---|---|---|---|
| 1 | 2.0 | 4 | 1175 | +14 | 1.60 | 545 | −5 | −0.51 |
| 2 | 2.5 | 4 | 552 | +31 | 2.16 | 263 | −7 | −0.51 |
| 4 | 2.0 | 4 | 665 | +27 | 2.06 | 295 | −15 | −1.16 |
| 4 | 4.0 | 4 | 100 | +96 | 2.86 | 46 | −13 | −0.34 |
| 4 | 2.5 | 48 | 246 | +5 | 0.10 | 116 | −89 | −1.92 |
| 8 | 4.0 | 24 | 58 | −42 | −0.35 | 23 | +177 | 1.48 |
| 12 | 2.0 | 48 | 212 | +11 | 0.21 | 97 | −101 | −1.96 |

The only IS-significant pattern is a small **4-hour bounce** after 1–4 h drops (+14 to +96 bp, t ≈ 2). It vanishes OOS, and 14–30 bp gross is under the 20 bp round trip anyway. The large-Z, long-k OOS positives (k = 8–12, Z = 4) have IS signs that are negative or zero and sit on 20–40 events: that is noise.

## 2. Conditional re-framings (`02_conditional.py`)

Each condition was applied on top of the down-shock (k ∈ {2, 4, 8, 12}, Z ∈ {2, 3}, H ∈ {12, 24, 48}). The table shows the average t-stat over those 24 cells:

| Condition | Mechanism it tests | mean t IS | mean t OOS |
|---|---|---|---|
| base (no condition) | — | −0.04 | −0.62 |
| volume > 2× 30d avg during the drop | forced flow / liquidation | 0.36 | −0.30 |
| volume > 3× | stronger forced flow | 0.19 | −0.13 |
| ETH/BTC ratio z < −2 over k (ETH-specific drop) | idiosyncratic overshoot | **−0.67** | **−0.93** |
| ETH/BTC ratio z > −0.5 (market-wide drop) | systematic flush | 0.89 | −0.22 |
| uptrend (price > 40d SMA before the drop) | dip in uptrend | 0.51 | 0.24 |
| downtrend | — | −0.52 | −0.91 |
| 7d funding above its 180d median (crowded longs) | long liquidation | −0.26 | −0.02 |
| 7d funding below median | — | 0.63 | −0.66 |
| daily horizon (1–3 d drop, 1–5 d hold), 27 cells | slower reversal | −0.3 avg | −0.3 avg |

Findings:
- **ETH-specific drops keep falling** (negative t in both halves). That is short-horizon *relative momentum*, the opposite of the hypothesis.
- **Crowded funding does not help.** Liquidations of crowded longs do not produce a larger rebound than other drops.
- **Daily-horizon drops continue over 3–5 days** (negative mean forward returns). ETH has momentum at every horizon here, not reversal.
- "Dip in uptrend" is the only condition positive in both halves, and it is weak (0.51 / 0.24).

## 3. Costed strategy grid (`03_strategy_grid.py`)

Long 1.0 at the close of the event bar, hold H hours, extend on re-trigger, 10 bp per side. k ∈ {2, 4, 8, 12} × Z ∈ {2, 2.5, 3} × H ∈ {12, 24, 48} × cond ∈ {none, uptrend} = **72 configs**. Sharpe is computed on UTC-daily compounded returns (ann = 365).

| Config (top by IS) | Full | IS | OOS | CAGR | MDD | TIM | Turnover | ρ to trend-filter |
|---|---|---|---|---|---|---|---|---|
| k2 Z2 H48 uptrend | 0.68 | 0.84 | 0.18 | 23% | −56% | 29% | 71× | 0.69 |
| k2 Z2.5 H48 uptrend | 0.53 | 0.78 | −0.32 | 14% | −59% | 19% | 56× | 0.60 |
| k4 Z2 H48 uptrend | 0.58 | 0.78 | −0.11 | 17% | −47% | 22% | 60× | 0.60 |
| k12 Z3 H24 uptrend | 0.47 | 0.45 | 0.65 | 7% | −28% | 2% | 13× | 0.25 |
| **Median of 72** | **0.08** | **0.18** | **−0.33** | | | | | |

IS→OOS Spearman across the 72 configs = **0.02**. The best-IS configs are just the trend-filter's long periods again (ρ = 0.6–0.7 with the live `eth-trend-filter`), with much worse Sharpe. For reference, the live trend filter replayed on the same hourly grid gives **1.22 full / 1.22 IS / 1.23 OOS**.

## Lookahead check

- σ is lagged by k bars, the event uses closes ≤ t, entry is at C_t, and `research_lib.backtest` shifts weights one bar. Nothing in the event definition touches t+1.
- The 40d SMA used for the regime condition is taken at t−k (before the drop). Funding is forward-filled from its own stamp.
- Removing any of these lags only helps the IS numbers, and the conclusion is negative anyway.

## Verdict

**Failed.** ETH shows no liquidity-provision rebound after flushes at horizons from 4 h to 5 days, on any conditioning tried, net or even gross of costs. The binding constraint is the **sign of the effect**, not cost: ETH exhibits short-horizon momentum, not reversal. The negative result on ETH-specific drops and the positive continuation after up-shocks both point the same way.

**Variants tried:** 240 event cells + 216 conditional cells + 27 daily-horizon cells + 72 costed strategies.

## Files

- `code/spot-eth/flush-rebound/01_event_study.py` (+ `01_event_study.csv`)
- `code/spot-eth/flush-rebound/02_conditional.py` (+ `02_conditional.csv`)
- `code/spot-eth/flush-rebound/03_strategy_grid.py` (+ `03_strategy_grid.csv`)
- `code/spot-eth/shared/ethdata.py` — shared hourly-bar / split / trend-baseline helpers
