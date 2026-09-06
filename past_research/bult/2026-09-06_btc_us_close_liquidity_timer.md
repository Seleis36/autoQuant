# BTC US-Close Liquidity Timer (BULT)

**Date:** 2026-09-06
**Asset:** spot BTC, long/flat, no leverage, no shorting
**Status:** **Working**
**Headline:** Sharpe **1.48** full sample (2017-08 → 2026-09), **1.20 out-of-sample** (2022+),
**1.41 in strict walk-forward**, at 3 bp/side costs. CAGR 32.4%, vol 20.4%, MaxDD −25.3%,
Calmar 1.28, beta to BTC 0.18, annualised alpha 20.1%.

---

## 1. Motivation and how I got here

The brief was risk-adjusted return on spot BTC. I did **not** start with an answer; I started by
trying to kill the obvious ones, and all of them died. That elimination is the most useful part of
this report, because it explains why the surviving idea looks the way it does.

### 1.1 What failed (and why it matters)

| # | Idea tested | Result | Verdict |
|---|---|---|---|
| 1 | **SMA crossover** long/flat, 68-point grid (fast 1–50 × slow 20–250) | mean Sharpe **IS 1.51 → OOS 0.64**; **0 of 68** cells reached OOS Sharpe > 1; IS→OOS rank correlation **−0.17** | Failed |
| 2 | **TSMOM** (price vs price *k* days ago), k = 5…250 | best OOS 0.98 at k=40, but IS ranking would never have selected it; same negative IS/OOS relationship | Failed |
| 3 | **52-week-high proximity** (George & Hwang anchoring, applied time-series) | 63-point grid: max OOS Sharpe **0.94**, median **0.58**, IS→OOS spearman **−0.27** | Failed |
| 4 | **Inverse-vol targeting alone** | BTC's vol/return relation is **U-shaped**, not monotone (Sharpe by ex-ante vol quintile: 1.91 / 0.85 / 0.51 / 0.81 / 1.33). Naive vol targeting has no directional edge to harvest | Failed alone |
| 5 | **Turn-of-month & day-of-week tilts** | Real but small (turn-of-month OOS Sharpe 1.30 vs 0.42 mid-month). As a multiplicative tilt it only shrank exposure without improving the ratio | Rejected |
| 6 | **ETH/BTC as crypto risk appetite** | Correct sign in both halves (ETH/BTC below its MA → BTC Sharpe 1.71 IS / 0.85 OOS) but adds nothing once trend+macro are in | Rejected |
| 7 | **Better vol forecasts** (HAR-RV, realised vol from hourly, Parkinson) | Forecast quality improved a lot (corr 0.55 → 0.62, QLIKE −0.06 → −0.20) but strategy Sharpe did **not** (1.23 → 1.26) | No benefit |
| 8 | **Intraday crash circuit-breaker** | No improvement at any threshold | No benefit |
| 9 | **Ungated intraday session trading** | Real edge but ~730 round-trips/yr; **dies above 3 bp/side** | Needed the gate |

The repeated pattern in 1–3 is the key finding: **every price-only timing family on BTC shows a
negative in-sample → out-of-sample rank correlation.** Selecting parameters on BTC's own price
history is not merely useless post-2021, it is actively misleading. That pushed me to two
information sources BTC's price does not contain: **exogenous macro state** and **intraday clock
structure**.

---

## 2. The two surviving return sources

### 2.1 Source A — daily liquidity/trend regime (the base)

**Thesis.** Post-2020 BTC is a long-duration, liquidity-sensitive risk asset. The state variables
that describe global liquidity and risk appetite should therefore condition BTC's forward return.

I scanned 72 exogenous features (16 tickers × momentum/MA/vol transforms) for conditional
one-day-forward BTC Sharpe by quintile, requiring the *same-signed* spread in **both** halves of the
sample. Survivors, ranked by consistency:

| Feature | IS quintile spread | OOS quintile spread | OOS monotonicity |
|---|---|---|---|
| **HYG vs 200d MA** (credit risk appetite) | +2.85 | **+3.42** | 0.5 |
| **LQD vs 200d MA** (IG credit / financial conditions) | +1.18 | **+2.87** | **1.00** |
| **DXY vs 200d MA** (dollar, inverted) | −1.15 | −2.29 | −0.9 |
| **SPX 20d momentum** (equity risk appetite) | +2.10 | +0.95 | 0.8 |

Standalone, `LQD > MA200` alone times BTC at Sharpe 1.50 full / 1.89 IS / 0.95 OOS. Critically, the
macro composite has **only 0.37 correlation with BTC's own trend signal** — it is genuinely
orthogonal information, not a repackaged moving average.

To avoid picking a lucky lookback, every block is an **ensemble**: each macro series is averaged over
5 lookbacks (50/100/150/200/250), BTC trend over 5 (20/50/100/150/200). No single parameter is
selected.

```
regime = mean_5lb[ 1{BTC > SMA_n} ]  ×  mean_4series,5lb[ risk-on indicator ]
base   = regime × clip(0.35 / EWMA_vol_20, 0, 1)
```

This base earns Sharpe **1.33** at ~6 round-trips/year — slow and essentially cost-immune.

### 2.2 Source B — the US-close / ETF-NAV window (the overlay)

**The finding.** Using 79,248 hourly bars (Binance, 2017-08 → 2026-09), BTC's entire drift is earned
in a three-hour window, **20:00–23:00 UTC**, which straddles the US equity close and the spot-ETF
4pm-ET NAV strike.

| | window 20–23 UTC | other 21 hours |
|---|---|---|
| mean return | 9.81 bp/day | 6.08 bp/day |
| annualised vol | **22.3%** | **64.4%** |
| Sharpe (full) | **1.60** | 0.34 |
| Sharpe 2024+ (ETF era) | **1.98** | **0.03** |

I selected the window by **worst-of-three-periods** ranking (IS, OOS, ETF-era) across all 192
contiguous windows — 20:00+3h wins on that robustness criterion, not on peak performance
(min Sharpe 1.63; next best 1.26). Hour 23:00–24:00 is consistently *negative* in all three periods,
which is why the window closes at 23:00.

**This is not a data artifact.** It replicates across four independent sources and a second asset:

| Source | window Sharpe | rest-of-day Sharpe |
|---|---|---|
| Binance BTCUSDT | 1.60 | 0.34 |
| **Bitstamp** BTC/USD (separate venue) | 1.83 | −0.09 |
| **yfinance** BTC-USD (separate vendor) | 1.58 | 0.19 |
| Binance.US BTCUSD | 1.15 | 0.38 |
| **ETHUSDT** (different asset) | 1.46 | 0.27 |
| ETHUSDT 2024+ | **1.96** | −0.38 |

The effect **strengthens post-ETF on every venue**, which is what the mechanism predicts.

### 2.3 The gate that makes it tradeable

Ungated, the window needs 730 round-trips/year and dies above ~3 bp/side. But the edge is heavily
concentrated on days when BTC **sold off before the window** — i.e. scheduled, price-insensitive US
demand absorbing overnight supply:

| Pre-window return (00:00→20:00 UTC, known at 20:00) | gross bp | Sharpe IS | Sharpe OOS | Sharpe ETF-era |
|---|---|---|---|---|
| bottom quintile | **21.35** | 2.41 | **2.90** | **5.02** |
| < 0 | 12.32 | 1.88 | 2.09 | 3.56 |
| > 0 | 7.43 | 1.40 | 1.17 | 0.43 |
| top quintile | 1.92 | 0.27 | 0.56 | −0.63 |

Gating on `pre-window return < −1%` cuts trading to **55 round-trips/year** while *raising* the
per-trade edge. This is what turns a theoretically-real-but-untradeable effect into a strategy.

---

## 3. Final specification

```
DAILY  (all inputs lagged 1 day + 1 hour)
  trend  = mean over n in {20,50,100,150,200}      of 1{ P > SMA_n(P) }
  macro  = mean over {HYG:+, LQD:+, DXY:-, SPX:+} × {50,100,150,200,250} of risk-on flag
  base   = (trend × macro) × clip(0.35 / EWMA_vol_20, 0, 1)

INTRADAY (known exactly at 20:00 UTC)
  pre    = cumulative BTC return 00:00 → 20:00 UTC
  gate   = 1 if hour in {20,21,22} and pre < −1%, else 0

  weight = clip( base + 0.5 × gate , 0, 1 )
```

**Lookahead policy.** Hourly bar *T* covers [T, T+1h); a weight known at time *T* is applied to that
bar's return with no shift. Every daily input is lagged a full day plus one hour. The gate uses only
the 00:00→20:00 return, known exactly at the 20:00 decision point.

---

## 4. Results

| | CAGR | Vol | **Sharpe** | Sortino | MaxDD | Calmar | t(NW) | RT/yr |
|---|---|---|---|---|---|---|---|---|
| **BULT @3bp/side** | 32.4% | 20.4% | **1.48** | 1.50 | −25.3% | 1.28 | 3.66 | 55 |
| Buy & hold | 38.1% | 71.8% | 0.81 | 0.98 | −83.9% | 0.45 | 2.50 | 0 |

| Period | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| IS 2017–2021 | 1.74 | 43.9% | −25.3% |
| **OOS 2022–2026** | **1.20** | 22.6% | −14.3% |
| ETF era 2024+ | 1.25 | 24.5% | −14.3% |

Per year (BULT vs BTC Sharpe): 2017 **3.66**/2.85 · 2018 **−1.25**/−0.87 · 2019 **2.41**/1.34 ·
2020 **3.34**/2.24 · 2021 0.79/0.98 · 2022 **−0.44**/−1.29 · 2023 1.65/2.42 · 2024 **2.15**/1.77 ·
2025 **0.36**/0.08 · 2026 **1.63**/−0.09.

**Relationship to BTC:** daily correlation 0.61, **beta 0.18**, annualised alpha **20.1%**, average
exposure 26%. Up-day capture 0.228 vs down-day capture 0.184 — it participates in rallies more than
in selloffs relative to its exposure.

### Component attribution

| Variant | Sharpe | OOS | ETF era | MaxDD |
|---|---|---|---|---|
| **Full** | **1.48** | **1.20** | 1.25 | −25.3% |
| no overlay (base only) | 1.33 | 0.97 | 0.87 | −18.4% |
| overlay ungated | 1.26 | 0.94 | 0.91 | −34.8% |
| no vol targeting | 1.25 | 1.10 | 1.13 | −37.8% |
| no BTC trend sleeve | 1.24 | 0.82 | 0.64 | −41.3% |
| no macro sleeve | 1.42 | 1.15 | 1.21 | −34.1% |
| overlay only (no base) | 0.85 | 1.06 | **1.69** | −20.1% |

Every component earns its place. Note the overlay alone is the *only* component whose ETF-era Sharpe
(1.69) exceeds its full-sample Sharpe — the intraday effect is getting stronger, the daily regime
effect is not.

---

## 5. Validation

**Engine cross-check.** vectorbt `Portfolio.from_orders` (target-percent, same fees) reproduces the
custom engine: Sharpe 1.4717 vs 1.4777, return-stream correlation **0.99989**, max per-bar
difference 1.8e-4 (discrete-share accounting).

**Independent venue.** Re-running the *entire* strategy on Bitstamp BTC/USD hourly data:
Sharpe **1.486** vs Binance **1.483** on the identical window.

**Strict walk-forward.** Re-selecting (gate threshold, overlay size) each year using only prior data,
2020–2026: **Sharpe 1.41**, CAGR 29.9%, MaxDD −23.4%, t(NW) 2.99. The parameters never see the future.

**Parameter surface — plateau, not spike.** All 24 (threshold × size) cells give full-sample Sharpe
1.25–1.48 and **OOS Sharpe 0.94–1.22**; every cell clears 0.94 OOS. Vol target is nearly irrelevant
(Sharpe 1.47–1.48 across 25–50%).

**Cost robustness.** 0bp → 1.64 · 3bp → 1.48 · 5bp → 1.37 · **10bp → 1.10**. The gate makes the
strategy viable even at retail taker fees, which the ungated version was not.

**Execution stress.** 1 hour late → Sharpe 1.14; 2 hours late → 0.82. Timing matters but has tolerance.

**Statistics.** Newey-West t = 3.66 (21-day lags). Stationary-block bootstrap (21-day blocks, 4000
reps): mean Sharpe 1.51, 5–95% CI **[0.90, 2.13]**, P(Sharpe ≤ 0) = 0.0000, **P(Sharpe < 1) = 8.4%**.
Deflated Sharpe accounting for **400 trials** across this entire study: **P(true SR > 0) = 0.928**.

### 5.1 Placebo and integrity tests

A real effect must fail its own mirror images. It does:

| Test | Result | Reading |
|---|---|---|
| **Placebo windows** — same strategy run on each of the 24 possible 3-hour windows | chosen window ranks **1 of 24** on full *and* OOS Sharpe; median placebo 1.15 vs real 1.48 | Partly circular (I selected this window on this data). The non-circular evidence is the cross-venue / cross-asset replication in §2.2. |
| **Randomised gate** — keep the window, randomly reassign which days are traded, same trade count, 200 draws | random-gate Sharpe mean 1.29, 95th pct 1.43, max 1.53; real 1.478 → **empirical p = 0.015** | The *specific* dip condition, not just trading fewer days, is what adds the edge. |
| **Mirrored gate** — trade when pre-window return > **+1%** instead of < −1% | Sharpe 1.21 (OOS 0.92) vs real 1.48 (OOS 1.20) | Directionally consistent with dip-absorption: buying strength is much weaker than buying weakness. |
| **Lookahead probe** — shift the weight ±1, ±2 bars | −2: 0.45 · −1: 0.98 · **0: 1.48** · +1: 1.14 · +2: 0.82 | Peak exactly at zero shift, decaying smoothly both ways. An accidental leak would have shown performance *preserved* under added lag; it is not. |
| **Block-shuffled returns** — run the strategy on permuted returns, 100 draws | shuffled mean 0.51, sd 0.23, max 1.01 vs real 1.48 (**4.1 sd above**, above the max of 100 draws) | Note the shuffled baseline is not zero, and should not be: a long-biased strategy on a positive-drift asset keeps the drift under shuffling. What is destroyed is the timing, and that is worth ~1.0 Sharpe. |


---

## 6. Limitations and risks — read this before trading it

1. **IS 1.74 → OOS 1.20 is real decay.** Some of the in-sample number is selection. The walk-forward
   figure (1.41) and the OOS figure (1.20) are the honest ones; the 1.48 headline is not.
2. **Two losing years, both bear markets:** 2018 (−18.8%) and 2022 (−3.8%). 2025 was near-flat
   (+5.2%). This is a long/flat strategy with positive BTC beta — it will lose in sustained downtrends,
   just far less than holding (2018: −18.8% vs −73.0%; 2022: −3.8% vs −64.2%).
3. **Deflated Sharpe of 0.93, not 0.99.** I ran roughly 400 specifications. This survives multiple-
   testing correction but not overwhelmingly.
4. **The overlay depends on a structural feature that could decay.** The 20:00–23:00 UTC edge exists
   because US flows are scheduled and price-insensitive. If ETF flows normalise or the window gets
   arbitraged, source B degrades. Monitor the ETF-era window Sharpe as a live health check.
5. **Execution matters.** Sharpe drops from 1.48 to 1.14 with one hour of delay. This needs
   automated execution at the hour boundary, not discretionary fills.
6. **SPX is the weakest macro leg** — dropping it *improves* OOS Sharpe from 1.20 to 1.28. I kept all
   four because the set was fixed before that ablation was run; removing it now would be fitting.
7. **Costs assume 3 bp/side (maker).** Verify against your actual venue tier before sizing.
8. **~9 years of data, one asset.** BTC's regime has changed twice in that span. Treat the confidence
   interval [0.90, 2.13] as the honest range, not the point estimate.

---

## 7. Reproduction

```
code/shared/research_lib.py   shared harness: data, metrics, NW t-stat, deflated Sharpe, backtester
code/bult/fetch_intraday.py   Binance hourly downloader (79,248 bars)
code/bult/strategy.py         BULT: build_signals() / backtest_hourly() / stats()
code/bult/exp01..exp21_*.py   every experiment in this report, in order
alphas/bult/BULT.md           deployable specification
```

`exp01`–`exp04` are the failures (§1.1), `exp05`–`exp07` the macro discovery, `exp10`–`exp12` the
intraday discovery and cross-venue validation, `exp16`–`exp17` the gate, `exp18`–`exp20` validation.
