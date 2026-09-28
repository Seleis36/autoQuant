# perp-crowding — contrarian retail positioning on Binance BTC perps, traded on spot BTC

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance daily bars, 00:00 UTC), long/flat, unlevered, daily rebalance
**Status:** **Working.**

Headline, from the exact `strategy.py` spec at 10 bp/side, 2021-03-01 → 2026-09-24:

| | full | IS 2021-03 → 2022 | **OOS 2023 → 2026-09** |
|---|---|---|---|
| Sharpe | **1.25** | 0.61 | **1.53** |
| vol-scaled B&H | 0.52 | −0.67 | 1.11 |
| SMA50 × vol | 0.94 | −0.57 | 1.52 |

- CAGR 37.6%, vol 29%, **MaxDD −30%**, Sortino 1.64.
- Turnover 41×/yr (52 state flips/yr, average holding spell 7.7 days); average exposure 0.43.
- **Selection-adjusted walk-forward** over the 16-member positioning family: **1.09** for 2022–26, against 0.57 for vol B&H and 0.95 for SMA50 × vol.
- The honest weakness: 2023+ OOS (1.53) only ties a plain SMA50 trend filter. The edge over trend comes from the 2021–22 chop and bear market.

---

## 1. Idea

Binance publishes, every 5 minutes, the **global long/short account ratio** for BTCUSDT perps: accounts net long divided by accounts net short. It is a head count, so it is dominated by the many small accounts, the retail crowd. The same feed has the top-trader account and position ratios, open interest and the taker long/short volume ratio.

The hypothesis is that retail positioning is a contrarian indicator:
- **Crowd more long than usual:** longs are crowded, marginal buyers are exhausted, and liquidations sit below the price. Returns should be poor.
- **Crowd short or unusually flat** (retail fading a rally, or capitulated after a drop): returns should be good.

This is the crypto analogue of the contrarian speculator positioning that works in FX in this repo (`fx-majors/cot-positioning`). The difference is that the data are daily, free and real-time instead of weekly and three days stale.

None of the existing BTC research used these series:
- `coinbase-premium` screened funding, the premium index and taker flow;
- `crypto-perps` used funding cross-sectionally;
- funding is dead as a spot signal in both.

## 2. Data

- **Source:** data.binance.vision `futures/um/daily/metrics/BTCUSDT`, 5-minute snapshots from **2020-09-01** → 2026-09-27 (638k rows).
- The shared fetcher writes nothing until the last day, and my first run was cut off near day 2,000. `fetch_metrics.py` in this folder is a parallel, resumable replacement with the same output: `data/BTCUSDT_metrics_5m.parquet`, same schema.
- **Columns:** `count_long_short_ratio` (global accounts, *the signal*), `count_toptrader_long_short_ratio` (top-trader accounts), `sum_toptrader_long_short_ratio` (top-trader positions), `sum_open_interest[_value]`, `sum_taker_long_short_vol_ratio`.
- **Timing:**
  - For daily bar D (decision at D+1 00:00 UTC), the spec uses the last snapshot stamped strictly before D+1 00:00 − **1 h**, i.e. 22:55.
  - The REST endpoint `fapi.binance.com/futures/data/globalLongShortAccountRatio` returns the same values: 2026-09-19 archive 23:50 = 0.941118, REST 23:55 = 0.9410. The REST stamp is **5 minutes later** than the archive `create_time`, so the archive stamp is the start of the window. The 1-hour cutoff removes any doubt.
  - Cutoffs of 0 h, 2 h and 6 h give the same result (§5).
- **Protocol:** IS = 2020-09 → 2022-12, OOS = 2023-01 → 2026-09. Strategy evaluation starts 2021-03-01, after the expanding-rank warm-up of 180 days. Cost 10 bp/side.

## 3. Screen (`exp01_screen.py`) — 36 features × 3 horizons, raw and partial IC

The 36 features are:
- 4 ratios (global, top-account, top-position, top-position − global), each as level, 90 d z, and 1/3/7 d change;
- OI growth 1/3/7 d, OI × return-sign quadrants, taker ratio 1/3/7 d, OI z.

The partial IC controls for the same-window return.

| | h = 1 d | h = 3 d | h = 7 d |
|---|---|---|---|
| IS→OOS Spearman of partial t | **0.70** | **0.60** | 0.38 |
| IS-significant (\|t\| ≥ 2) that keep their sign OOS | **8 / 8** | 3 / 3 | 5 / 5 |

No other screen this session had better than ~0.5 consistency, and three were negative.

| Feature | h = 1 partial IC IS (t) | OOS (t) | h = 3 IS (t) | OOS (t) |
|---|---|---|---|---|
| top-trader account ratio (log) | −0.151 (−3.8) | −0.038 (−1.4) | −0.221 (−3.0) | −0.098 (−2.1) |
| **global account ratio (log)** | −0.101 (−3.0) | −0.033 (−1.3) | −0.129 (−2.1) | −0.096 (−2.1) |
| top-position − global | +0.146 (3.6) | +0.012 (0.5) | +0.202 (2.8) | +0.030 (0.7) |
| global ratio z90 | −0.053 | −0.040 | −0.053 | −0.122 (−2.6) |
| OI growth, taker ratio | all \|t\| < 2 in at least one half | | | |

The yearly 3-day IC of the global ratio is negative in 6 of 7 years:

| 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| −0.04 | −0.16 | −0.02 | −0.09 | −0.12 | −0.05 | +0.05 |

The top-trader account ratio flipped in 2022 (+0.22).

## 4. From signal to strategy (`exp02` – `exp03`)

Two mechanical IS rules were run first:

| IS-selection rule | form | full | IS | OOS |
|---|---|---|---|---|
| composite of the 8 IS-significant features | standalone × vol | 1.01 | 0.32 | 1.34 |
| | gate on SMA50 × vol | 1.09 | −0.42 | 1.61 |
| IS-strongest single feature (top-trader accounts) | standalone | 1.10 | 0.35 | 1.35 |
| | gate on SMA50 × vol | 1.40 | 0.78 | 1.62 |
| **global account ratio (retail crowd)** | standalone | 1.21 | 0.86 | 1.36 |
| | gate on SMA50 × vol | 1.33 | 0.18 | 1.69 |

**Choice of the global ratio.** It is the canonical "retail crowd" measure the hypothesis is about. It is one of the 8 IS-significant features and has the most consistent yearly sign. It was **not** the single IS-best feature: the top-trader account ratio was, and its OOS is similar (1.35 / 1.62).

The global ratio is robust to how it is normalised. The top-trader ratio is not (rank365 standalone 0.66).

| Normalisation | standalone full / IS / OOS | trend gate full / IS / OOS |
|---|---|---|
| expanding rank < 0.5 | 1.21 / 0.86 / 1.36 | 1.33 / 0.18 / 1.69 |
| rolling 365 d rank | 1.19 / 0.79 / 1.40 | 1.34 / 0.29 / 1.71 |
| rolling 90 d z < 0 | 1.20 / 0.65 / 1.47 | 1.30 / 0.04 / 1.72 |
| rolling 180 d z < 0 | 1.30 / 0.69 / 1.58 | 1.12 / −0.03 / 1.49 |

## 5. Validation (`exp04` – `exp09`)

| Check | Result |
|---|---|
| **Truncation test** (`strategy.target_weight` on data cut at 2022-06-30, 2024-03-15, 2025-11-01 vs the full run) | max \|Δw\| = **0** at all three |
| Snapshot cutoff 0 h / 1 h (spec) / 2 h / 6 h before the close | 1.21 / **1.25** / 1.25 / 1.23 standalone. Not sensitive, so there is no end-of-day leak |
| State lagged +1 / +2 days (legal) | 1.05 / 0.78. Fast decay: **must trade at the 00:00 UTC close** |
| State advanced 1 day (illegal) | 4.34. The ratio co-moves with same-day price, so peeking is hugely profitable, as expected |
| Funding control | Partial IC of the ratio after 7 d funding and 3 d return: −0.121 (t −2.2) IS, −0.081 (t −1.7) OOS. Funding alone: +0.02 / −0.01, dead |
| **Momentum controls** 1{ret_k > 0} × vol, k = 1…7 | Standalone −0.05 … 0.40 full, all far below 1.21. OOS next-day return is +25 bp when not crowded whatever yesterday's sign (+22 bp if yesterday was up), and +3 bp when crowded |
| **Trend controls** 1{ret_k > 0}, k = 10…60, and close > SMA 10…100 | Full 0.25 … 0.94 and IS −1.23 … −0.21, all below P1 (1.21 / 0.86). OOS 0.65 … 1.52: SMA50 (1.52) and ret_14 (1.43) beat P1's OOS at the screening definition, and SMA50 ties the spec's 1.53 |
| Partial IC after ret 1/3/7/14/30 and the SMA50 state | h = 1: −0.115 (t −3.4) IS, −0.020 (−0.8) OOS. **h = 3: −0.132 (t −2.2) IS, −0.101 (t −2.1) OOS** |
| Residual positioning (ratio change net of 0–2 day returns) | 0.43 / 0.89 OOS. The informative part is the accumulated *level*, not the daily innovation |
| Circular-shift placebo of the ratio (200 draws, shift ≥ 90 d) | spec 1.24 vs placebo mean 0.21, sd 0.32, max 1.03; **p = 0.000** |
| Block bootstrap (21 d) of the spec | median 1.22, 5–95% [0.49, 1.98], P(Sharpe > 1) = 0.69 (SMA50 × vol: 0.38) |
| Deflated Sharpe | 0.89 with 16 trials (the family); **0.72 with 80** (every configuration in this study) |
| **Walk-forward**, 16-member family (4 ratios × 2 normalisations × standalone/gate), yearly re-selection 2022–26 | **1.09** (2023+ 1.23); vol B&H 0.57; SMA50 × vol 0.95 (2023+ 1.52) |
| Family dispersion (16) | median 1.19 full / 1.35 OOS; OOS range 0.55 … 1.72 |
| Costs 0 / 5 / 10 / 20 / 30 bp/side | 1.39 / 1.32 / **1.25** / 1.10 / 0.96 |
| vectorbt `from_orders` (targetpercent, 0.1% fee) | 1.205 vs custom 1.208, return corr 0.9997 (screening definition) |

Yearly (spec):

| | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---|---|---|---|---|---|
| Sharpe | 1.85 | −0.34 | 2.47 | 2.55 | −0.47 | 0.91 |
| Return | +44.7% | −12.5% | +117% | +116% | −14.3% | +16.2% |

## 6. Place in the live book

| (hourly books, 10 bp/side, 2021-03 → 2026-09) | full | IS | OOS | MaxDD |
|---|---|---|---|---|
| `coinbase-premium`, live spec | 0.99 | −0.45 | 1.53 | −33% |
| P1 perp-crowding (held hourly) | 1.25 | 0.88 | 1.42 | −34% |
| 50/50 weights coinbase-premium + P1 | 1.24 | 0.37 | 1.57 | −24% |
| **P3: coinbase-premium AND not-crowded** | **1.37** | −0.10 | **1.84** | −27% |

- Daily P&L correlation of P1 is 0.71 with coinbase-premium and 0.76 with SMA50 × vol. All are long-only BTC.
- Weight correlation with coinbase-premium is 0.56: the timing is genuinely different.
- P2 (P1 × SMA50 gate) scores 1.29 / −0.15 / 1.77, MaxDD −28%.

## 7. Verdict and limitations

**Working.** It is a long/flat spot-BTC sleeve built on a non-price information source:
- it beats vol-scaled buy-and-hold in both halves;
- it beats every price-trend and momentum control on the full sample and IS;
- it survives a selection-adjusted walk-forward (1.09 vs 0.95 / 0.57), a placebo (p = 0) and a truncation test;
- it trades ~50 times a year at testnet cost.

Read these before deploying it:
1. **OOS it ties a plain trend filter** (1.53 vs 1.52), and the walk-forward 2023+ is below it (1.23). Its advantage is in choppy and bear markets: 2021–22, and 2022 at −0.34 vs −2.19 for SMA50 × vol.
2. **Short history**: 5.5 years and one venue's definition of the ratio. If Binance changes how it counts accounts, the expanding rank breaks.
3. **Fast decay**: one day of execution delay costs ~0.2 Sharpe. The sleeve has to act at the 00:00 UTC close on the ratio snapshot from before 23:00 UTC.
4. 2025 was negative (−0.47). The deflated Sharpe at the full 80-configuration count is 0.72.
5. Mechanical IS alternatives (the 8-feature composite, the top-trader ratio) reach similar OOS (1.34–1.62). The choice of the global ratio rests on mechanism and stability, not on OOS.

Configurations evaluated: 216 screen cells (108 raw + 108 partial), ≈ 80 strategy backtests, and 200 + 200 placebo draws.

## 8. Reproduction

```bash
.venv/bin/python code/spot-btc/perp-crowding/fetch_metrics.py BTCUSDT   # resumable, ~5 min
.venv/bin/python code/spot-btc/perp-crowding/exp01_screen.py            # screen
.venv/bin/python code/spot-btc/perp-crowding/exp02_backtest.py          # IS-selected forms
.venv/bin/python code/spot-btc/perp-crowding/exp03_robustness.py        # normalisations, cbprem overlay
.venv/bin/python code/spot-btc/perp-crowding/exp04_validate.py          # timing, funding, placebo, bootstrap
.venv/bin/python code/spot-btc/perp-crowding/exp05_momentum_control.py
.venv/bin/python code/spot-btc/perp-crowding/exp06_trend_control.py
.venv/bin/python code/spot-btc/perp-crowding/exp07_wf_blend.py          # walk-forward, blends
.venv/bin/python code/spot-btc/perp-crowding/exp08_final.py             # spec numbers, truncation, figure
.venv/bin/python code/spot-btc/perp-crowding/exp09_spec_stats.py        # spec bootstrap/DSR/placebo
```
