# cme-cot-positioning — CFTC positioning in CME Bitcoin futures as a spot-BTC timing signal

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance daily bars, 00:00 UTC), long/flat, unlevered
**Status:** **Failed.** No COT feature predicts BTC out of sample. The IS→OOS rank correlation of 71 feature ICs is +0.05 at 1 week and −0.18 / −0.20 at 2 / 4 weeks. The best use of COT, a gate or tilt on a trend baseline, loses to the baseline OOS: median 0.99 / 1.43 vs 1.52.

---

## 1. Motivation

The three live spot-BTC sleeves (`bult`, `weekday-trend`, `coinbase-premium`) all trade BTC's own price, macro ETFs, the calendar and venue premia. None of them uses **who holds the regulated futures**. In other asset classes in this repo, CFTC positioning is the one non-price source that has worked:
- `fx-majors/cot-positioning`: contrarian speculator positioning, 0.80 / 0.64 OOS, deployed.
- `vol-complex/vix-cot-positioning`: an asset-manager share gate, 1.00 / 0.96 OOS, deployed.

CME Bitcoin futures (code 133741, 5 BTC) and Micro Bitcoin (133742, 0.1 BTC) are in the Traders-in-Financial-Futures (TFF) report. The categories are dealers, asset managers, leveraged funds, other reportables and non-reportables (retail). Two mechanisms were plausible:
1. **Crowding:** extreme leveraged-fund or retail positioning precedes reversals, as in FX.
2. **Institutional demand:** asset managers adding net longs is slow-moving real-money demand that persists.

A 2026 paper (Shen, Li & Luo, *Finance Research Letters* 106) also reports that **asset managers' option positions** predict the second-week-ahead CME futures return. That claim was tested separately in §4.

## 2. Data and timing (`fetch_cot_btc.py`, `features.py`)

- CFTC yearly zips `fut_fin_txt_{y}` (TFF, futures only), `com_fin_txt_{y}` (TFF, futures + delta-adjusted options) and `deacot{y}` (legacy). Cached as `data/CFTC_COT_{tff,tffcomb,legacy}_btc_w.parquet`.
- Coverage: 2018-04-10 → 2026-09-22, 442 weekly reports. Micro contracts start 2021-05. Standard and micro are summed in **BTC units** (5 and 0.1 BTC per contract).
- **Release timing** reuses the FX rule. A report as of Tuesday is usable after Saturday 21:00 UTC, or Tuesday 21:00 UTC in federal-holiday weeks. Shutdown backlogs are clipped to their actual release dates.
- A daily bar D takes the latest report public strictly before D+1 00:00 UTC, which is the moment its weight is set. The Saturday bar is therefore the first bar that can use Friday's release.
- Positioning drifts structurally with the ETF basis trade. Yearly mean leveraged-fund net / OI goes −0.05 (2018), −0.27 (2020), −0.41 (2021), −0.54 (2024), −0.39 (2026). Asset-manager net goes −0.03 → +0.49 (2024) → +0.20 (2026). Every strategy expression therefore uses trailing 52-report z-scores, not levels.

Protocol, fixed before any result: IS = weeks ≤ 2022-12-31, OOS = 2023-01-01 onward. Cost 10 bp/side, the testnet taker fee. Selection statistics are IS only.

## 3. Futures positioning screen (`exp01_screen.py`)

I screened 71 features against the forward 7 / 14 / 28-day BTC return, sampled weekly on the Saturday bar (213 feature × horizon cells). For each of the five TFF groups the features were:
- net / OI; 26- and 52-report z;
- 1 / 4 / 13-week change;
- BTC flow / OI;
- long and short share z.

On top of those: OI growth and OI z, plus legacy non-commercial, commercial and non-reportable net shares. The statistic is rank IC with Newey–West t.

| Feature (7-day horizon) | IC IS | t IS | IC OOS | t OOS |
|---|---|---|---|---|
| leveraged-fund short share z52 | +0.171 | 2.57 | −0.024 | −0.33 |
| leveraged-fund net Δ13w | −0.167 | −2.57 | +0.081 | +1.21 |
| legacy non-commercial net | −0.160 | −2.53 | −0.017 | −0.27 |
| non-reportable (retail) net | +0.157 | 2.50 | +0.019 | +0.29 |
| other-reportable net z52 | +0.139 | 1.98 | +0.066 | +0.96 |
| dealer net Δ13w | +0.113 | 1.72 | +0.017 | +0.24 |
| other-reportable long z52 | +0.113 | 1.68 | +0.114 | 1.60 |
| dealer net Δ1w | +0.103 | 1.51 | +0.108 | 1.59 |

- Only 49% of 1-week features keep their IS sign OOS.
- The Spearman correlation of IS IC with OOS IC is **+0.05 (7 d), −0.18 (14 d), −0.20 (28 d)**. At 2 and 4 weeks, IS significance anti-predicts OOS.
- Every feature that passes |t_IS| ≥ 2 *and* keeps its sign OOS is a structurally trending level, and its OOS IC is ≤ 0.02.

Full table: `code/spot-btc/cme-cot-positioning/exp01_screen.csv`.

## 4. Strategy expressions (`exp02_backtest.py`) — 48 + 2 backtests

Selection used IS only: all 15 distinct features with |t_IS| ≥ 1.5 at 7 days, each signed by its IS IC and standardised by its own trailing 52-report z. There was also one IS composite, the mean of the 15 signed z. Each signal was run three ways:
- **A:** standalone, `1{z>0} × inverse-vol(40%, hl 20, cap 1)`;
- **B:** a gate on `SMA50 × vol`;
- **C:** a tilt on it, `SMA50 × vol × (0.5 + 0.5·1{z>0})`.

Backtests start 2018-10, the first date with a 26-report z.

| | full | IS | OOS |
|---|---|---|---|
| vol-scaled buy & hold | 0.81 | 0.57 | 1.11 |
| **SMA50 × vol (baseline)** | **1.42** | 1.33 | **1.52** |
| A standalone — median of 16 | 0.94 | 0.97 | 0.94 |
| B trend gate — median of 16 | 1.30 | 1.51 | **0.99** |
| C trend tilt — median of 16 | 1.46 | 1.51 | **1.43** |
| B IS composite | 1.47 | **1.91** | **0.92** |
| C IS composite | 1.54 | 1.68 | 1.36 |
| A dealer flow 13w (best OOS standalone) | 1.34 | 1.15 | 1.56 |

What the table shows:
- The gate B adds +0.18 IS and costs −0.53 OOS. That is the signature of fitted noise: the composite goes 1.91 → 0.92.
- The tilt C is a diluted trend and never beats the baseline OOS by more than 0.10, with no consistency across features.
- The best OOS standalone, dealer 13-week flow, has an OOS IC of 0.03 (t 0.45) at the weekly horizon. Its 1.56 OOS Sharpe sits beside a 1.11 buy-and-hold with 31% exposure, and it adds +0.07 over the baseline as a tilt. That is a trend proxy, not information.

## 5. Option positions (`exp03_options.py`) — Shen–Li–Luo replication

Option positions were computed as combined − futures-only in delta-adjusted BTC, for each group:
- options average only 3–11% of combined OI;
- asset-manager option net is ≤ 1.4% of OI in any year and zero before 2021.

Across 42 cells (4 features × 5 groups + share, × week 1 / week 2):
- the paper's feature, AM option net, has week-2 IC −0.08 IS (t −1.3) and +0.09 OOS (t 1.3). The sign flips;
- the pre-specified week-2 trade on the IS sign gives OOS Sharpe −0.41 / 0.63 / 0.81 for net / Δ1 / z52, all below vol-scaled buy-and-hold;
- the IS-significant option features (dealer, other-reportable, non-reportable; |t| 2.0–2.9) are all flat or reversed OOS.

## 6. Verdict

- **Failed.** CFTC positioning in CME Bitcoin contains no stable information about next-week to next-month spot returns on this sample.
- Why it differs from FX and VIX: in those markets the COT categories map onto a stable economic role. Speculators crowd a carry currency; vol-ETP sponsors sit in the asset-manager line. In BTC, the categories were re-populated by the 2024 ETF basis trade. Leveraged funds' net short is mostly the short leg of cash-and-carry, and asset managers' net long partly mirrors it. A 52-week z of these lines measures basis-trade capacity, not directional conviction.
- The sample is also short: 440 weekly observations, 190 of them OOS. It cannot resolve an IC of 0.1 in any single half.
- Configurations evaluated: 213 screen cells + 42 option cells, 48 strategy backtests + 2 baselines + 3 option trades.

## 7. Reusable pieces

- `fetch_cot_btc.py` fetches BTC TFF (futures and combined) and legacy COT with release timing. `on_daily_rows` maps weekly reports onto 00:00 UTC daily bars at the decision time.
- `code/spot-btc/shared/btc_data.py` builds Binance BTCUSDT daily and hourly bars from the 1m store and drops a still-forming last bar. It also provides a full / IS / OOS evaluator.
