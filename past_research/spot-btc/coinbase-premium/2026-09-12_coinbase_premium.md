# coinbase-premium — cross-venue price premium as a spot-BTC timing signal

**Date:** 2026-09-12
**Asset:** spot BTC/USDT (Binance), long/flat, unlevered, hourly bars
**Brief:** "2+ sharpe strat" (acceptance criterion: Sharpe ≥ 2.0)
**Status:** **Failed against the criterion.** Best honest configuration: net Sharpe **1.48 full / 1.48 IS / 1.48 OOS / 1.37 walk-forward** at 10 bp/side. Even at zero cost it is 1.84. The idea is a real, orthogonal, ~1.5-Sharpe long/flat signal; it is not a 2.0 one.

---

## 1. Motivation

Both existing spot-BTC sleeves (`bult`, `weekday-trend`) use BTC's own price, macro ETFs and calendar effects, and both report that price-only signals have a negative in-sample → out-of-sample rank correlation. To have a shot at 2.0 I went after information that neither uses and that is observable live without a key:

| Source | Endpoint | Cache file (`data/`) |
|---|---|---|
| Binance USDT-M perp funding (8h) | `fapi/v1/fundingRate` | `BTCUSDT_funding_8h.parquet` (2019-09 →) |
| Binance premium-index klines (mark vs index) | `fapi/v1/premiumIndexKlines` | `BTCUSDT_premium_1h.parquet` (2019-12 →) |
| Binance spot klines incl. taker-buy volume | `api/v3/klines` | `BTCUSDT_1h_flow.parquet` (2017-08 →) |
| Coinbase Exchange BTC-USD hourly | `api.exchange.coinbase.com/…/candles` | `COINBASE_BTCUSD_1h.parquet` (2015-07 →) |
| Deribit BTC DVOL (30d implied vol) | `public/get_volatility_index_data` | `DERIBIT_DVOL_BTC_1d.parquet` (2021-03 →) |
| Bitstamp USDT/USD daily | `api/v2/ohlc/usdtusd` | `BITSTAMP_USDTUSD_1d.parquet` (2021-06 →) |

`code/spot-btc/coinbase-premium/fetch_data.py` refreshes all of them.

**Protocol fixed before any result was seen:** IS = rows ≤ 2022-12-31, OOS = rows ≥ 2023-01-01 (never moved); cost 10 bp/side (testnet taker); selection statistics are IS-only, OOS shown for confirmation; every grid is reported in full.

## 2. Phase A — single-feature screen (`exp01_screen.py`)

58 daily features (row D = everything known at 00:00 UTC of D+1; target = next calendar-day Binance return). Selection: |NW t| of the Q5−Q1 spread ≥ 2 in IS **and** same sign OOS.

| Feature | IS spread bp/day | IS t | OOS spread | OOS t | Survivor |
|---|---|---|---|---|---|
| **Coinbase/Binance premium, daily mean** | **104.5** | **3.12** | 45.9 | 1.75 | yes |
| same, z-scored 90d | 78.6 | 2.84 | 76.1 | 2.78 | yes |
| DVOL z-score 90d | 107.9 | 2.36 | 37.2 | 2.00 | yes (2021+ only) |
| Taker-buy ratio 7d z | 64.3 | 2.18 | 15.5 | 0.72 | yes, weak |
| Vol-risk premium (DVOL − rv20) | 84.0 | 2.10 | 21.8 | 1.02 | yes, weak |
| Funding 7d mean (contrarian) | −70.6 | −1.96 | 3.1 | 0.15 | **no** — dies OOS |
| Premium-index (mark−index) last | −76.6 | −1.95 | 10.8 | 0.53 | **no** |
| Net taker flow (quote) | 8.6 | 0.26 | 32.3 | 1.42 | no |
| USDT/USD premium z | 31.5 | 0.64 | 58.1 | 2.24 | no (IS too short) |

Funding and the perp premium index are contrarian in IS and flat OOS — nothing to build on. Taker flow is weak. The Coinbase premium is the only feature that is strong in IS *and* holds OOS with a comparable magnitude, so the rest of the session is about it. Full table: `exp01_screen.csv`.

## 3. Phase B — what the premium is and how long it lasts (`exp02`, `exp03`, `exp04(i)`, `exp08`)

Definition (industry-standard "Coinbase premium"): `prem = Coinbase BTC-USD close / Binance BTCUSDT close − 1`.

**Horizon.** Next-day return by quintile of the 90d z-score, full sample: Q1 −20 bp, Q2 +3, Q3 +19, Q4 +16, **Q5 +49 bp/day**. Per-day effect decays from 49 bp (h=1) to 33 (h=5) to 17 (h=15): a 1–5-day signal. IS Q5 = +41 bp/day (Sharpe of those days 1.86), OOS Q5 = +69 bp/day (Sharpe 4.76, n=269).

**Hourly.** The hourly premium at bar T predicts bar T+1 (tercile spread 6.9 bp/h, NW t **6.5** IS / 4.1 OOS) and the effect accumulates: 17.8 bp over 4 h, 30.7 over 8 h, 67 over 24 h (IS). The predictive power is **uniform across decision hours** — there is no intraday structure to exploit (`exp03`, 24-hour table), which rules out a low-turnover "trade one window a day" expression.

**Demand or convergence?** After a top-tercile premium, over the next 24 h Binance gains 41 bp and *Coinbase itself gains 32 bp* (IS); OOS 31.6 vs 30.4. So the daily-scale effect is a genuine directional signal, not just Binance catching up with Coinbase. Only the 1-hour horizon has a convergence component (Binance +3.5 vs Coinbase +1.0 bp).

**Which leg carries it (the important finding, `exp08`).** On the 2019-11 → 2026-09 window where Bitstamp hourly exists, the same hysteresis strategy built on each ratio:

| Premium definition | Full | IS | OOS |
|---|---|---|---|
| Coinbase / Binance (USDT) | **1.49** | 1.45 | 1.53 |
| Bitstamp / Binance (USDT) | 1.29 | 1.20 | 1.35 |
| Coinbase / Bitstamp (both USD) | **0.01** | 0.10 | −0.07 |
| trend × vol only, no premium | 1.26 | 1.31 | 1.22 |

The USD-venue-vs-USD-venue premium is pure noise at hourly resolution (turnover 341×/yr, Sharpe 0). **The signal lives in the Binance-USDT-quote leg**: BTCUSDT relative to BTCUSD, i.e. the USDT/USD premium plus Binance-specific overshoot. Coinbase merely provides the cleanest USD reference (it beats Bitstamp by 0.2 Sharpe). Anyone reading this as "US institutional demand" should stop — the honest label is *USD-venue vs Binance-USDT price dislocation*. Timestamp alignment across the three venues was verified (return correlation 0.997/0.994 at lag 0, |corr| < 0.03 at every other lag).

## 4. Phase C — turning it into a long/flat strategy

### 4.1 Daily expressions (`exp02(d)`, `exp03b`, `exp04(iii)`) — 224 configurations
Gating a daily trend×vol strategy on the premium **does not add Sharpe at daily frequency**: `sma50 × vol` alone is 1.38 (1.32 IS / 1.46 OOS) and every premium-gated variant lands at 1.0–1.3 because the gate halves exposure and adds 30–70 turnover/yr at 10 bp. Sizing forms (linear in z, step, no-trade bands 0.2–0.5) do not change that. The premium standalone (`z90>0`) is 0.89, barely above buy-and-hold (0.82).

### 4.2 Hourly hysteresis (`exp04(ii)`, `exp05`) — 64 + 24 configurations
Because the effect is a 1–24 h effect, the right expression is to track the hourly z-score continuously with a **state machine** (enter long when z > `enter`, exit when z < `exit`) so that turnover stays at ~90 side-trades/yr instead of hourly churn, then apply the same trend × inverse-vol sizing as the other sleeves.

| trend filter | trend × vol alone (hourly) | + hysteresis(0, −1.5) | + hysteresis(1, −1) |
|---|---|---|---|
| SMA 20d | 1.12 (1.28 / 0.88) | 1.34 (1.42 / 1.22) | 1.42 (1.45 / 1.38) |
| **SMA 50d** | 1.25 (1.29 / 1.18) | **1.48 (1.48 / 1.48)** | 1.46 (1.38 / 1.58) |
| SMA 100d | 1.13 (1.10 / 1.17) | 1.38 (1.25 / 1.55) | 1.40 (1.22 / 1.64) |
| SMA 200d | 0.93 (0.82 / 1.07) | 1.16 (0.97 / 1.40) | 1.29 (0.94 / 1.73) |
| no trend, vol only | — | 1.42 (1.23 / 1.70) | — |

(full / IS / OOS, 10 bp/side.) The premium adds **+0.2 to +0.35 Sharpe on top of every trend baseline, in both halves** — that consistency is the evidence it is real. The 36-cell walk-forward grid has full-sample Sharpe min 0.97 / median 1.29 / max 1.48: a plateau, and the chosen cell is its top.

**Locked candidate** (`strategy.py` defaults): hourly bars; `z = (prem − mean₇₂₀)/std₇₂₀`; enter z > 0, exit z < −1.5; × 1{close > SMA(1200 h)} × clip(0.40 / EWMA-vol(hl 480 h), 0, 1).

### 4.3 Ensemble with `weekday-trend` (`exp05(3)`)
On the same Binance daily closes: weekday-trend 1.26, premium (daily-sampled) 1.37, **50/50 ensemble 1.47** (1.41 / 1.54), daily-return correlation 0.64 (0.70 OOS). Both are long-BTC-in-uptrend sleeves; diversification is limited.

## 5. Validation of the candidate (`exp06`, `exp08`)

| Check | Result |
|---|---|
| Full / IS / OOS Sharpe, 10 bp | **1.48 / 1.48 / 1.48**; CAGR 39.9 %, vol ~27 %, MaxDD −33.1 %, avg exposure 29 %, 88 side-trades/yr, NW t 4.38 |
| Strict walk-forward (expanding train, 36 candidates, test 2020–26) | **Sharpe 1.37**, CAGR 36 %, MaxDD −33 %; picks (0, −1.5, SMA50) in 5 of 7 years |
| Yearly Sharpe (cand / B&H) | 2017 3.7/2.9 · 2018 −1.7/−0.9 · 2019 2.1/1.3 · 2020 3.3/2.2 · 2021 1.5/1.0 · 2022 −1.8/−1.3 · 2023 2.4/2.4 · 2024 2.0/1.8 · 2025 0.4/0.1 · 2026 0.3/−0.2 |
| Cost sensitivity | 0 bp 1.84 · 3 bp 1.73 · 5 bp 1.66 · **10 bp 1.48** · 20 bp 1.13 |
| Lookahead probe | legal extra lag −1 bar 1.41, −2 bars 1.37; **illegal** +1 bar of future weight 3.11 — peak-then-decay on the legal side, blow-up on the illegal side, as a leak-free short-horizon signal should look |
| Block bootstrap (daily, 21d blocks, 2000) | median 1.44, 5–95 % **[0.84, 2.02]**, P(Sh > 1) 0.89, **P(Sh > 2) 0.056** |
| Deflated Sharpe, 400 trials | P(true SR > 0) = 0.948 |
| Placebo: premium z block-shuffled (30d blocks, 200 draws) | placebo mean 0.92, sd 0.17, max 1.34 vs real 1.48 → empirical p = 0.00 |
| vectorbt `from_orders` (targetpercent, fees 0.1 %) | Sharpe 1.485 vs custom 1.492, return corr 0.999, max per-bar diff 1e-3 |
| Venue replication | see §3: Bitstamp/Binance 1.29 — replicates with a different USD reference; Coinbase/Bitstamp 0.01 — does **not** replicate without the Binance leg |

## 6. Verdict against the acceptance criterion

- Criterion: Sharpe ≥ 2.0. **Met: NO.**
- Closest: 1.48 full-sample (IS = OOS = 1.48), 1.37 walk-forward, bootstrap upper 95 % bound 2.02, P(Sharpe > 2) ≈ 6 %.
- Binding constraint: the signal is a 1–24 h dislocation worth ~5 bp/h in the top tercile; at 10 bp/side it can only be harvested with a low-turnover state machine, which caps the incremental Sharpe at ~+0.3 over a trend baseline that is itself ~1.25. Even at **zero cost** the candidate is 1.84, so cost is not what separates it from 2.0 — the daily-scale information content is.
- Configurations evaluated: ~310 backtests (8 + 168 daily composites, 62 hysteresis, 48 band-sizing, 24 baselines/ensembles) plus ~130 screening statistics. Best-of-310 on a plateau where the median is 1.29 argues for discounting the 1.48 towards ~1.35.

## 7. What did not work (so nobody repeats it)

1. **Perp funding rate** as a spot timing signal — contrarian in IS (t −1.96), zero OOS. All lookbacks 1–30 d.
2. **Perp premium index** (mark − index) — same pattern, dead.
3. **Taker buy/sell imbalance** (1–30 d, z-scored, US/Asia/late-session splits, quote-flow) — best IS t 2.2 but OOS t 0.7; nothing tradeable.
4. **DVOL / VRP** — survives the screen but the 2021+ sample gives 1.75 IS years; not pursued as primary. Worth a look by someone with a 1.5 bar.
5. **USDT/USD (Bitstamp) directly** — OOS t 2.2 but only 1.6 IS years; the same information reaches the strategy through the Binance-USDT leg of the premium anyway.
6. **Premium as a daily gate on trend** — halves exposure, adds turnover, no Sharpe gain (§4.1).
7. **Intraday window trading of the premium** — no hour-of-day structure; every window pays 20 bp round-trip for the same per-day edge.
8. **Premium change / momentum (`dprem`)** — weaker than the level in both halves.
9. **Coinbase vs Bitstamp (pure USD-venue) premium** — noise at hourly resolution (§3).
10. **Ensemble with `weekday-trend`** — 1.47, corr 0.64.

## 8. Files

```
code/spot-btc/coinbase-premium/fetch_data.py         six public-endpoint fetchers -> data/
code/spot-btc/coinbase-premium/features.py           daily feature panel (00:00 UTC stamp convention)
code/spot-btc/coinbase-premium/exp01_screen.py       58-feature screen (+ exp01_screen.csv)
code/spot-btc/coinbase-premium/exp02_cbprem.py       decomposition, horizon, transform grid, first rules
code/spot-btc/coinbase-premium/exp03_hourly.py       hourly predictability, by decision hour
code/spot-btc/coinbase-premium/exp03b_daily_composite.py  168 daily composites (+ csv)
code/spot-btc/coinbase-premium/exp04_hysteresis.py   demand-vs-convergence, hysteresis grid, no-trade bands
code/spot-btc/coinbase-premium/exp05_ensemble.py     baselines, asymmetric gate, weekday-trend ensemble, costs
code/spot-btc/coinbase-premium/exp06_validate.py     walk-forward, lookahead, bootstrap, DSR, placebo, vbt
code/spot-btc/coinbase-premium/exp07_figures.py      figures -> alphas/
code/spot-btc/coinbase-premium/exp08_alignment.py    venue alignment + three-way decomposition
code/spot-btc/coinbase-premium/strategy.py           target_weight(binance_close_1h, coinbase_close_1h)
alphas/spot-btc/coinbase-premium/                    candidate spec + equity.png/csv, premium_signal.png, premium_quintiles.png
```
`exp01` regenerates `panel.parquet` (not committed); run `fetch_data.py` first.
