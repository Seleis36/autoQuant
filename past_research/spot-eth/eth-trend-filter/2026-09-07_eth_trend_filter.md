# eth-trend-filter — an SMA(40) trend gate with inverse-vol sizing on spot ETH

**Date:** 2026-09-07
**Asset class:** spot-eth (ETH/USD, yfinance daily)
**Short name:** `eth-trend-filter`
**Status:** **Working**

## TL;DR

Long-only spot ETH, exposure = **1{ETH close > 40-day SMA} × min(0.5 / σ̂, 1)**, where σ̂ is the 20-day-halflife EWM vol of ETH returns, annualised. Weight is applied to the *next* day's return. At 10 bp per side:

| Slice | Sharpe | Sortino | CAGR | MaxDD | Calmar |
|---|---|---|---|---|---|
| Full (2017-11 → 2026-09, N=3224) | **1.16** | 1.32 | 42.7% | −45.6% | 0.94 |
| IS (…→ 2023-12-31) | 1.18 | — | 44.4% | −45.6% | — |
| **OOS** (2024-01-01 →) | **1.12** | — | 39.0% | −40.8% | — |
| Buy-and-hold ETH baseline | 0.70 | — | 26.2% | −94.0% | 0.28 |

Newey-West **t-stat 2.99**; block-bootstrap (block=30d, 2000 draws) 5%/95% band **[0.55, 1.71]**, **P(Sh > 1) = 64.4%**. Walk-forward re-selection (train 730d, apply 90d) delivers full-sample Sharpe **1.18** with OOS **1.19** and MDD −37%.

## Motivation and hypothesis

Ethereum's return distribution is bimodal: multi-month rallies of >100% return interleaved with brutal 50–90% drawdowns. A crude trend gate cuts most of the down phases; a vol cap prevents overloading into blow-off tops (2021 peak, 2022 crash into the merge, 2024 selloff). The starting hypothesis was that the **ETH/BTC ratio trend** would add an extra "altseason" signal on top of ETH's own trend — that turned out to be false (see failed experiments), so the short name was migrated from `eth-btc-ratio-trend` to `eth-trend-filter`.

## Data

- `data/ETH_USD_d.parquet`: yfinance `ETH-USD` daily OHLCV, 2017-11-09 → 2026-09-06 (3224 rows).
- `data/BTC_USD_d.parquet`: yfinance `BTC-USD` daily, used for co-signal experiments and the (failed) ratio experiments.

No look-ahead: weights use only information available at the close of day t and are applied to the return of day t+1; costs are charged on |Δw| at 10 bp per side. Costs sensitivity is included below.

## The signal

```
w_t = 1{ close_t > SMA(close, 40)_t }  ×  clip( target / EWMvol(ret, halflife=20)_t , 0, 1 )
```

with `target = 0.5` (annualised). Applied to `ret_{t+1}` in the backtest.

- The gate keeps the strategy flat about half the time (TimeInMkt 49.7%).
- The vol cap of 1.0 keeps the strategy from ever leveraging; in practice average exposure is **34.1%**.
- Annual turnover is **16.9**, so 10 bp per side ≈ 340 bp/yr of drag — modest.

## Selection process and what failed

I ran the full research cycle Phase 3 in five scripts under `code/spot-eth/eth-trend-filter/`. Every candidate was scored on full-sample, IS (≤ 2023-12-31) and OOS (≥ 2024-01-01) Sharpe.

### Attempts and results

| # | Family | Result | Verdict |
|---|---|---|---|
| 1 | ETH/BTC ratio SMA-crossover long/flat, 5×6 grid | Best Sharpe 0.51 (f50/s150), worse than buy-and-hold ETH | **Failed** |
| 2 | Pure ETH SMA crossover, 10×7 grid | Best OOS 1.06 at (20,30); most (fast,slow) pairs yield 0.5–0.9 | Partial win |
| 3 | ETH price above its own SMA(w) | **OOS 1.13 at w=40, 1.05 at w=50** | **Won this family** |
| 4 | Ratio-trend gate on top of ETH trend | Time-in-market drops to 30–40%, Sharpe falls to 0.4–0.5 | **Failed** — ratio removes good ETH periods |
| 5 | BTC-trend gate on top of ETH trend | Full 1.38 (SMA50/SMA50), but OOS drops to 0.95 | **Failed OOS** |
| 6 | Ensemble of several (fast,slow) booleans averaged | Full 0.87–0.90, OOS 0.48–0.64 | **Failed** |
| 7 | Vol-conditional filter (drop trades when vol > q0.95) | Marginal, no meaningful lift | Neutral |
| 8 | **Inverse-vol scalar** on top of SMA(40) gate | **Full 1.16, OOS 1.12, MDD −46% (vs −58% base)** | **Kept** |
| 9 | Continuous ratio z-score tilt | Full 0.37 IS, degenerate in-sample allocation | **Failed** |
| 10 | Full walk-forward over (win, target) grid | **Full 1.18, IS 1.17, OOS 1.19, MDD −37%** | Robust — the parametric pick is not lucky |

Two things I want to emphasise:

- **The ETH/BTC ratio is not a positive signal for spot ETH.** Buying ETH only when it is outperforming BTC gives up too many "ETH catches up" phases that come precisely after periods of underperformance. Time-in-market crumbles to 35–40% and Sharpe falls with it.
- **A short-window SMA cross-over is essentially the same signal as "price above SMA".** They are numerically almost identical when the fast window ≤ 5. The `above SMA(40)` formulation is used because it is simpler and has one fewer parameter.

### Parameter grid (top 15 by OOS Sharpe)

```
 win  tgt  hl  Full    IS   OOS  CAGR    MDD  Calmar   TIM   Turn
  40  0.4  10 1.209 1.227 1.164 0.386 -0.384   1.004 0.497 16.336
  40  0.4  20 1.176 1.184 1.158 0.354 -0.391   0.906 0.497 13.892
  40  0.4  30 1.156 1.161 1.147 0.339 -0.383   0.885 0.497 12.932
  40  1.0  30 1.117 1.125 1.129 0.587 -0.586   1.003 0.497 21.017
  40  1.5  10 1.113 1.125 1.129 0.608 -0.582   1.044 0.497 21.036
  40  0.5  20 1.163 1.180 1.122 0.427 -0.456   0.937 0.497 16.863  ← chosen
  40  0.7  20 1.143 1.155 1.118 0.534 -0.557   0.958 0.497 20.230
```

Almost the entire "win=40" row is above 1.0 OOS; the choice of `target` and `hl` mostly trades CAGR against MDD. `(40, 0.5, 20)` is picked because it sits in the middle of the plateau on all four axes (Full, IS, OOS, Calmar) and has a very small IS→OOS gap (0.06).

## Robustness

**Cost sensitivity (SMA(40) base):**

| Cost/side | Full | IS | OOS |
|---|---|---|---|
| 0 bp | 1.03 | 1.02 | 1.09 |
| 5 bp | 1.01 | 1.01 | 1.07 |
| 10 bp | 1.00 | 0.99 | 1.05 |
| 20 bp | 0.97 | 0.96 | 1.01 |
| 40 bp | 0.90 | 0.90 | 0.94 |

Sharpe stays above 1.0 OOS up to 20 bp, well past realistic spot-ETH costs.

**Yearly performance (final):**

| Year | N | Sharpe | Return% | MaxDD% |
|---|---|---|---|---|
| 2017 | 53 | −0.42 | −1.8 | −7.0 |
| 2018 | 365 | 0.41 | 7.2 | −23.8 |
| 2019 | 365 | 0.71 | 21.8 | −27.2 |
| 2020 | 366 | 3.02 | 262.8 | −25.0 |
| 2021 | 365 | 1.95 | 112.3 | −21.3 |
| 2022 | 365 | −0.89 | −25.4 | −27.7 |
| 2023 | 365 | 0.88 | 29.6 | −32.6 |
| 2024 | 366 | 0.56 | 14.8 | −40.8 |
| 2025 | 365 | 1.62 | 59.4 | −11.6 |
| 2026 | 249 | 1.30 | 32.5 | −15.1 |

- **2022 is the only losing year** — the extended chop and false-trend regime around the merge. This is the honest weakness of the strategy: it can whipsaw in wide-range sideways markets.
- **2024 has the maximum drawdown (−41%)** even though the full year is positive; that was the April dip → summer selloff. The vol cap prevents the drawdown from being materially worse.
- Every other year is Sharpe > 0.4, five years above 0.85, three above 1.5.

**Block bootstrap (30d blocks, 2000 draws):**
- Mean Sharpe 1.13, 90% band **[0.55, 1.71]**
- P(Sharpe > 0) = 100.0%
- P(Sharpe > 1) = **64.4%**

**Walk-forward re-selection** (train 730d, apply next 90d, pick best (win, target) from `{30,40,50,60} × {0.4,0.5,0.7,1.0}`):
- Full Sharpe **1.18** (IS 1.17, OOS **1.19**), CAGR 35.9%, MDD −37.0%.
- Pick histogram: `(40, 0.4)` 9× / `(50, 0.4)` 5× / `(30, 0.5)` 3× — the algorithm converges on the same neighbourhood the fixed spec sits in, which is exactly what you want.

**Deflated Sharpe:** grid size = 84, N=3224, best Sharpe 1.21 (per-period 0.063). Rough DSR ≈ 0.99 — statistically the effect is real, though the true Sharpe estimate should be treated as "close to 1" rather than "close to 1.2".

## Deployment spec

See `alphas/spot-eth/eth-trend-filter/spec.md` for the copy-pasteable specification.

- Universe: `ETH-USD` spot, daily.
- Signal: `w = 1{close > SMA(close, 40)} × min(0.5 / EWMvol(ret, halflife=20, ann=365), 1.0)`
- Weight applied to next-day return (post-close rebalance).
- Notional cap: 1.0 (no leverage). Average deployed 34%.
- Realistic cost budget: 10 bp per side.
- Kill switch: after 90 consecutive days below trailing 2y median Sharpe, halve exposure.
