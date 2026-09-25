# session-momentum — ETH intraday session drift, session-to-session momentum, and weekday effects

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT 1m → 1h bars, UTC, 2017-09 → 2026-09-24)
**Short name:** `session-momentum`
**Status:** **Failed** as a standalone strategy (every intraday window dies on the 10 bp fee). It produced one **amendment for the live `eth-trend-filter`**: skip Thursdays, worth +0.1 Sharpe in both halves.

## TL;DR

- **Hour-of-day.** 21:00 and 22:00 UTC (US close) are the only hours positive in both halves: +4.1 / +4.3 bp IS (t 1.9 / 2.1), +7.2 / +3.4 bp OOS (t 3.2 / 1.6). This is the same window `spot-btc/bult` exploits. Holding ETH only from 21 to 23 UTC earns Sharpe **1.52 gross, 0.90 at 2 bp, −0.03 at 5 bp**: about 11 bp per day of drift against a 20 bp round trip. All 60 standalone windows are negative at 10 bp (median −1.4).
- **Session-to-session momentum** (Asia → Europe → US → US close, and Gao-et-al. "first k hours → rest of day"): several correlations are significant IS (t 3–5) and none hold OOS, except first-16h → last-8h (0.057 IS / 0.121 OOS), which sits between neighbours of ~0. Conditional windows are dead at 10 bp. Used as a tilt on the trend filter they give 1.03–1.29 full and 1.07–1.18 OOS, against 1.22 / 1.23 for the plain trend filter.
- **Weekday.** **Thursday** is the worst weekday IS (−47 bp/day) and OOS (−58 bp, t −1.8), and it trails the other six days **in 10 of 10 calendar years**. The BTC `weekday-trend` research found the same drag. Picking the worst IS weekday (Thursday) and flattening the live trend filter on it lifts Sharpe from **1.22 / 1.22 / 1.23 to 1.33 / 1.33 / 1.32** (full / IS / OOS) at 10 bp, with MaxDD −45% → −40%. The overlay is neutral at 20 bp. ρ to the live trend filter is 0.92: an amendment, not a new edge.

## Data and conventions

Hourly bars from `load_bars("ETHUSDT","1h",resample_from="1m")`, left-labelled at the bar open (UTC). To be long *during* hour H, the weight is 1 at the close of bar H−1 (`backtest` shifts by one bar). The trend-filter reference (`1{C > SMA40} × min(0.5/EWMvol20, 1)` on 00:00 UTC closes) is replayed on the hourly grid, with each daily weight applied from the following 00:00. Weekday = weekday of the UTC day being held. Costs are 10 bp per side on every change of weight. IS ≤ 2023-12-31, OOS ≥ 2024-01-01. Sharpe is computed on UTC-daily compounded returns.

## 1. Seasonality map (`01_seasonality_map.py`)

**Hour of day (bp per hour; selected rows):**

| UTC hour | bp IS | t IS | bp OOS | t OOS |
|---|---|---|---|---|
| 2 | −4.2 | −2.0 | +0.6 | 0.3 |
| 3 | −4.8 | −2.4 | +3.4 | 1.9 |
| 9 | −4.6 | −2.2 | +2.0 | 1.2 |
| 13 | +3.4 | 1.4 | −4.9 | −1.9 |
| **21** | **+4.1** | **1.9** | **+7.2** | **3.2** |
| **22** | **+4.3** | **2.1** | **+3.4** | **1.6** |
| 23 | −0.3 | −0.1 | −3.4 | −2.0 |

Most IS-significant hours flip sign OOS. Only 21–22 UTC hold.

**Weekday (bp per UTC day):**

| | Mon | Tue | Wed | **Thu** | Fri | Sat | Sun |
|---|---|---|---|---|---|---|---|
| IS | +7 | −1 | +13 | **−50** (t −1.5) | +35 | +37 | +13 |
| OOS | +48 | −56 | +61 | **−58** (t −1.8) | −1 | +16 | +2 |

**Session cross-correlations** (S1 00–08, S2 08–13, S3 13–21, S4 21–24 UTC):

| Predictor → target | corr IS (t) | corr OOS (t) |
|---|---|---|
| prev day → S1 | −0.057 (−2.8) | −0.003 (−0.1) |
| prev S4 → S1 | −0.119 (−5.7) | +0.015 (0.5) |
| S1 → S2 | +0.048 (2.3) | +0.021 (0.7) |
| S3 → S4 | −0.063 (−3.0) | −0.038 (−1.2) |
| S1+S2+S3 → S4 | +0.094 (4.5) | −0.009 (−0.3) |
| first 16h → last 8h | +0.057 (2.7) | +0.121 (3.8) |
| first 12h → last 12h | +0.077 (3.7) | +0.004 (0.1) |
| first 20h → last 4h | +0.078 (3.8) | +0.025 (0.8) |

The IS structure (overnight reversal into Asia, intraday momentum into the US close) does not survive into 2024–26.

## 2. Costed strategies (`02_strategies.py`)

| Family | Variants | Result |
|---|---|---|
| A. Standalone window [a, a+L), a ∈ {0,2,…,22}, L ∈ {2,4,6,8,12} | 60 | median Sharpe **−1.43 full / −2.06 OOS**; best IS 0.19 → OOS −1.30. Turnover 730×/yr |
| 21–23 UTC window, cost sweep | 3 | 1.52 @0 bp · 0.90 @2 bp · −0.03 @5 bp |
| B. Long [k, 24) if first k hours up, k ∈ {4,8,12,16,20} | 5 | full −0.42 … 0.69; OOS −1.39 … 1.07; all fail OOS or on cost |
| B'. TF + 0.5 × conditional window | 5 | full 1.03–1.29, OOS 1.07–1.18 (TF alone 1.22 / 1.23) |
| C. TF flat on worst-IS weekday (= Thursday) | 1 | **1.33 / 1.33 / 1.32**, MDD −40%, turnover 51× |
| C'. TF flat Tue + Thu (Tue chosen with OOS knowledge — reported, not used) | 1 | 1.36 / 1.26 / 1.60 |
| C''. TF flat Thu + Sun | 1 | 1.07 / 1.15 / 0.87 |

## 3. Thursday overlay stability (`03_thursday_stability.py`)

| Year | Thu bp/day | other days bp/day | TF Sharpe | TF skip-Thu Sharpe |
|---|---|---|---|---|
| 2017 | −169 | +112 | 3.01 | 2.83 |
| 2018 | −31 | −30 | −0.11 | 0.19 |
| 2019 | −135 | +32 | 0.66 | 1.55 |
| 2020 | +25 | +68 | 2.97 | 2.84 |
| 2021 | +14 | +68 | 1.75 | 1.91 |
| 2022 | −32 | −18 | −0.79 | −0.52 |
| 2023 | +5 | +23 | 0.97 | 0.31 |
| 2024 | −4 | +19 | 0.69 | 0.75 |
| 2025 | −60 | +15 | 1.67 | 1.57 |
| 2026 | −100 | +19 | 1.44 | 1.86 |

| Cost/side | TF skip-Thu (Full / IS / OOS) | TF (Full / IS / OOS) |
|---|---|---|
| 5 bp | 1.40 / 1.40 / 1.41 | 1.25 / 1.24 / 1.25 |
| 10 bp | 1.33 / 1.33 / 1.32 | 1.22 / 1.22 / 1.23 |
| 20 bp | 1.17 / 1.19 / 1.15 | 1.18 / 1.18 / 1.18 |

Caveats. The Thursday effect has no convincing mechanism (candidates: US macro-data Thursdays, pre-expiry hedging before Friday 08:00 UTC Deribit expiries). It is one weekday picked from seven, and the "replication" on BTC is not independent (ETH/BTC daily correlation ≈ 0.8). The out-of-sample confirmation (t −1.8 on 2024–26, IS-selected) and the 10-of-10-years consistency are what make it worth recording. The uplift disappears at 20 bp, because it adds ~34 round trips a year.

## Verdict

**Failed** as a session / intraday strategy. The binding constraint is **cost**: the robust intraday drift (21–23 UTC) is about 11 bp per day, and the session-momentum structure is not stable across halves. The **Thursday skip** is a small, IS-selected, OOS-confirmed improvement to `eth-trend-filter` (+0.10 OOS Sharpe at 10 bp). It is recorded here for whoever next revises that strategy. It is not deployed as a separate book, because at ρ 0.92 it would double the same exposure.

**Variants tried:** 24 hours + 7 weekdays + 17 session correlations in the map; 60 + 3 + 10 + 4 costed strategies.

## Files

- `code/spot-eth/session-momentum/01_seasonality_map.py`
- `code/spot-eth/session-momentum/02_strategies.py`
- `code/spot-eth/session-momentum/03_thursday_stability.py`
