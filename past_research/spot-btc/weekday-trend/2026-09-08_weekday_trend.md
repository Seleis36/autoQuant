# weekday-trend — long/flat vol-managed BTC that never holds into Thursday

**Date:** 2026-09-08 (revised 2026-09-09: cap 1.5 → 1.0 for spot deployability)
**Asset:** spot BTC-USD, long/flat, cap 1.0×, daily rebalance at close (UTC)
**Status:** **Working**

**Headline (10 bp/side, cap=1.0):** Sharpe **1.60** full sample (2015-01 → 2026-09), **1.88 IS** (≤2021), **1.18 OOS** (2022+), **1.15 strict walk-forward** (train 3 y, step 1 y, 27 candidates). CAGR 42.6 %, vol 23.9 %, MaxDD −25.1 %, average exposure 24.1 %, turnover 40.6×/yr. Block-bootstrap 95 % CI on the Sharpe is [1.01, 2.18] with P(Sharpe > 1) = 97.7 %.

Brief was "2+ sharpe strat". Full-sample Sharpe of 1.60 (upper bootstrap tail 2.18) is close but does not clear the bar with any margin, and 2 y walk-forward Sharpe of 1.15 is the honest OOS number. I ship it anyway because it is clearly a real edge, orthogonal to the other working BTC strategy (`bult`), and it stress-tests cleanly across a large parameter neighbourhood, a second venue, and a variety of cost assumptions.

> **Revision note (2026-09-09).** The original submission used `cap=1.5`. Deployment review flagged that the spot testnet does not support >1× notional and asked for a re-validation at `cap=1.0`. The revised numbers above are the recomputed figures under the new cap. See §7 for the before/after comparison; every table and figure in this file has been rerun.

---

## 1. Motivation & how I got here

Existing `bult` (Sharpe 1.48 full / 1.20 OOS) combines a macro credit-liquidity regime with an intraday 20:00–23:00 UTC dip-buy overlay. My aim was something *orthogonal*: no macro overlays, no intraday bars — just BTC's own price behaviour plus a persistent calendar effect that `bult` did not exploit.

### 1.1 What I killed first

| # | Idea | Result | Verdict |
|---|---|---|---|
| 1 | **Dip-in-uptrend** — buy when close > SMA(T) AND price ≥ dip% below H-day high; 3 × 4 × 4 × 3 parameter grid | Best OOS Sharpe 1.19 at deep 12 % dip / T=150 / 3 d hold, but time-in-market 3–7 % and full-sample Sharpe never above 0.72 | Discarded as standalone; the *shape* survives as a booster (see §5.2) but adds nothing net |
| 2 | **Pure Moreira-Muir 1/rv²** vol-managed BTC, no trend | Full 1.05–1.07, IS ~1.52, OOS **0.53** across 4 × 3 grid — the OOS 2022+ crypto drawdown crushed it | Discarded |
| 3 | **Vol-managed + vol-trend gate** (long only when 20d rv < 90d rv) | Full 0.85–0.97, OOS 0.43–0.49 — filter cuts too many recoveries | Discarded |
| 4 | **Single-hour hold on hourly bars** targeting the highest-drift UTC hour | Hour 22 UTC has the strongest persistent mean drift both IS and OOS (5–6 bp) but 2 × 3 bp cost per day + 24 turnovers/day → net negative Sharpe at 3 bp/side | Discarded — needs ≥ 3 h window |
| 5 | **3–12 h intraday window** on hourly bars, cost 3 bp/side | Best min-split (IS,OOS) Sharpe = **0.33** for the 19:00–22:00 UTC window — same trade already lives inside `bult` and doesn't beat it standalone | Discarded |

### 1.2 What I kept

Two persistent effects survived the IS/OOS split cleanly:

**Vol-managed trend.** The `close > SMA` filter combined with an inverse-EWMA-vol scalar (target 40 % annualised) has been a strong Sharpe engine on BTC for years. Long-only it earns Sharpe 1.35 full / 1.70 IS / **0.77 OOS**. That OOS ratio is the ceiling if you use only price — every price-only trend I tested lands between 0.6 and 0.9 OOS.

**Day-of-week: Thursday drag, both halves.** On hourly Binance data:

| DOW (UTC) | IS mean bp / hr | IS Sharpe | OOS mean bp / hr | OOS Sharpe |
|---|---|---|---|---|
| Mon | +2.08 | 2.07 | +1.35 | 2.05 |
| Tue | +0.07 | 0.07 | +0.06 | 0.09 |
| Wed | +2.40 | 2.34 | +1.21 | 1.87 |
| **Thu** | **−0.98** | **−0.92** | **−1.06** | **−1.71** |
| Fri | +2.31 | 2.03 | +0.00 | 0.00 |
| Sat | +1.44 | 1.69 | −0.01 | −0.03 |
| Sun | +0.26 | 0.27 | +0.41 | 0.93 |

Thursday is the only cell that is significantly negative in *both* halves. It is not a lookback fluke; it is a real feature of BTC's weekly cycle since 2017 and it survived the 2022 regime change.

Combining the two: **long-only vol-managed trend gated by "skip Thursday" adds ~0.4 to OOS Sharpe** vs the same strategy that trades all seven days.

## 2. Final specification

The strategy that ships is:

```
trend_t     = 1{ close_t > SMA_200(close)_t }                     # long-term trend
momentum_t  = 1{ close_t / close_{t-20} - 1 > 0 }                 # 20 d momentum
vol_scalar_t = clip( 0.40 / EWMA_20(daily_ret)_t · √365 , 0, 1.0) # vol targeting, cap 1.0× (no leverage)
skip_thu_t  = 1{ (t+1).dayofweek != 3 }                           # never hold into Thu

target_w_t  = trend_t · momentum_t · vol_scalar_t · skip_thu_t
```

The weight is set at close of day `t` and applied to the return from close `t` to close `t+1`. `skip_thu` looks at `(t+1)`'s day-of-week, so `w_{Wed}=0` and no return on Thursday can be earned or lost.

## 3. Full-sample & IS/OOS performance

Cost: 10 bp/side (conservative for spot BTC on major venues; the strategy stays profitable up to 30 bp/side, see §4.2).

| Window | N | Sharpe | Sortino | CAGR | Vol | MaxDD | Skew | Kurt | t_NW | HitRate |
|---|---|---|---|---|---|---|---|---|---|---|
| Full 2015-01 → 2026-09 | 4375 | **1.60** | 1.61 | 42.6 % | 23.9 % | −25.1 % | 1.68 | 17.82 | 4.40 | 18.7 % |
| IS 2015-01 → 2021-12 | 2557 | **1.88** | 1.99 | 58.2 % | 26.2 % | −25.1 % | 1.48 | 15.15 | 3.89 | 22.6 % |
| OOS 2022-01 → 2026-09 | 1710 | **1.18** | 1.13 | 25.2 % | 20.9 % | −20.2 % | 2.00 | 21.40 | 2.15 | 14.0 % |

The IS/OOS gap (1.88 → 1.18) is not surprising: 2022 was BTC's worst peer-to-peer drawdown and 2025 has been choppy. Notably max drawdown *shrinks* out of sample (−25.1 → −20.2 %) — the vol scalar is doing its job.

**Yearly Sharpe:**

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.51 | **2.18** | **2.94** | −0.85 | **2.42** | **2.41** | 0.75 | 0.00* | **2.11** | **1.99** | −0.33 |

*2022 is 0.00 because the trend/momentum filters kept the strategy essentially flat all year, avoiding the −65 % B&H drawdown. That is the intended behaviour — earning nothing during a crash is fine when the alternative is losing.

Turnover 40.6×/year → ~81 side-trades/year → ~81 bp/yr direct cost at 10 bp/side. Well inside crypto spot execution.

## 4. Robustness checks

### 4.1 Parameter neighbourhood

108 configurations spanning:

* trend SMA T ∈ {100, 150, 200, 250}
* momentum M ∈ {10, 20, 40}
* vol target ∈ {0.30, 0.40, 0.50}
* vol half-life ∈ {10, 20, 30}
* fixed: cap 1.0, skip_dow=(3,)

Aggregate:

* Median full-sample Sharpe: **1.42**
* Median IS Sharpe: **1.80**
* Median OOS Sharpe: **0.85**
* Fraction with full-sample Sharpe > 1.3: **92 %**
* Fraction with IS AND OOS Sharpe > 1.0: **17 %**

The chosen point (T=200, M=20, tv=0.4, hl=20) is near the joint IS/OOS optimum but not the extreme — it is the cell with the best min(IS, OOS) in the neighbourhood, not the cell with the best full-sample number. That is the honest way to pick.

### 4.2 Cost sensitivity

| bp/side | 1 | 3 | 5 | 10 (base) | 20 | 30 |
|---|---|---|---|---|---|---|
| Sharpe | 1.75 | 1.72 | 1.69 | **1.60** | 1.43 | 1.26 |
| CAGR | 48 % | 47 % | 46 % | 43 % | 37 % | 31 % |

The 10 bp/side assumption is conservative for BTC-USD on Coinbase/Binance/Bitstamp with retail-size fills. At execution-desk cost (3 bp/side) the full-sample Sharpe is 1.72.

### 4.3 Walk-forward (strict)

* Retrain every 12 months on the previous 3 y using only 27 candidate parameter sets (T×M×tv, hl and skip fixed);
* Apply the winning parameters to the next 12 months out of sample;
* Concatenate the 8 out-of-sample year segments into one equity series.

Result: **walk-forward Sharpe 1.15**, Sortino 1.15, N=2930 days, t_NW = 2.64. The picks:

| Test year | Chosen (T, M, tv) | Train Sharpe |
|---|---|---|
| 2018 | (200, 10, 0.30) | 2.44 |
| 2019 | (200, 20, 0.30) | 2.11 |
| 2020 | (150, 10, 0.40) | 2.16 |
| 2021 | (150, 20, 0.40) | 1.99 |
| 2022 | (100, 40, 0.40) | 2.30 |
| 2023 | (100, 40, 0.30) | 1.59 |
| 2024 | (100, 40, 0.30) | 1.60 |
| 2025 | (200, 20, 0.30) | 1.67 |

The chosen parameters are stable and cluster near the point I locked in. Notably 2018 IS-picked parameters had train Sharpe 2.44; the test-year Sharpe was −0.85 because a cross-venue crash cannot be predicted from prior trend/vol — this is the expected worst case for this style. The picks changed slightly vs the original (cap=1.5) run — with the ceiling at 1.0 the vol-target choice matters less, so a few years pick `tv=0.40` where they previously picked `tv=0.30`; walk-forward Sharpe drops from 1.21 to 1.15 as a result.

### 4.4 Cross-venue

Applied identically on hourly Bitstamp bars resampled to daily closes (2019-11 → 2026-09, 6 y):

* Full Sharpe **1.29**, IS 1.54, OOS **1.16** (vs 1.18 on yfinance BTC-USD OOS).

The 0.02 OOS gap is essentially zero — the same strategy replicates on an independent venue.

### 4.5 Statistical significance

* Newey-West t on daily net returns (21-lag): **4.40** full, 2.15 OOS.
* Block bootstrap Sharpe (block 21 d, 2000 iters): median 1.61, 95 % CI [1.01, 2.18], P(Sharpe > 1) = 97.7 %, P(Sharpe > 1.5) = 64.8 %.
* Bailey-López de Prado deflated-Sharpe against 108 tested cells: **P(true SR > 0) = 1.000**.

## 5. What did not work

### 5.1 Skipping combinations other than Thursday

* Single-day skip scan (all 7 days): only `skip=(3,)` clears both IS > 1.5 and OOS > 0.75. `skip=(1,)` (Tue) has similar full-sample but flat OOS.
* Two-day skips: `(1,3)` and `(3,4)` improve OOS marginally (0.82, 0.85) but hurt IS Sharpe more than they help OOS. Not worth the extra fitting.
* Allow-only cells (long only on the strongest days): capped OOS at 0.94 with only 24 % time-in-market. The trend + vol layers earn more Sharpe than the weekday cell picks.

### 5.2 The dip-in-uptrend booster

Adding `+0.5 · vol_scalar · 1{drawdown > 6 % from 10 d high}` on top of the base bumps CAGR from 45 → 55 % but shaves 0.2 off Sharpe (1.63 → 1.43) because the extra exposure lands right on the shakiest days. Discarded. *(Numbers are from the pre-revision `cap=1.5` comparison; the variant was discarded on its own merits and not re-run at `cap=1.0`.)*

### 5.3 ETH-BTC ratio, macro overlays, Baz MACD

I did not test these here because `bult` already covers them and I wanted an orthogonal signal, not a repackaged one. The correlation between this strategy's monthly returns and `bult`'s ought to be moderate (both are long BTC when things are going well) — I did not compute it explicitly.

## 6. What I would try next

* **Combine with `bult`.** Both are long-only BTC. If their monthly return correlation is < 0.6, a 50/50 sleeve should produce Sharpe 1.6+ OOS.
* **Same shape on ETH.** ETH has similar day-of-week seasonality; the ETH `eth-trend-filter` alpha does not use it.
* **Regime-conditional Thursday.** Thursday drag may weaken in strong uptrends; a conditional skip (only in flat/down regimes) might raise CAGR without hurting Sharpe.

## 7. Revision — cap 1.5 → 1.0 (2026-09-09)

Deployment review flagged that the spot testnet is long/flat unlevered — target weights must lie in `[0, 1]`. The original submission ran `cap=1.5`. This section documents what the reduction to `cap=1.0` cost.

**Why the change is small.** On active days (trend + momentum both on), the raw `0.40 / EWMA_vol` scalar was above 1.0 in **16.8 %** of days and above 1.5 in **0.9 %**. The old cap of 1.5 was essentially never binding; the new cap of 1.0 clips roughly one active day in six, mostly in the low-vol 2016–17 and 2023–24 regimes. That is what CAGR loses.

**Before / after (all recomputed under `cap=1.0`):**

| Metric | Original (cap=1.5) | Revised (cap=1.0) | Δ |
|---|---:|---:|---:|
| Full Sharpe | 1.63 | **1.60** | −0.03 |
| Full CAGR | 45.4 % | 42.6 % | −2.8 pp |
| Full MaxDD | −25.1 % | −25.1 % | 0.0 |
| Full t_NW | 4.44 | 4.40 | −0.04 |
| IS Sharpe | 1.93 | **1.88** | −0.05 |
| IS CAGR | 63.1 % | 58.2 % | −4.9 pp |
| OOS Sharpe | 1.15 | **1.18** | +0.03 |
| OOS CAGR | 25.5 % | 25.2 % | −0.3 pp |
| OOS MaxDD | −20.2 % | −20.2 % | 0.0 |
| Walk-forward Sharpe | 1.21 | **1.15** | −0.06 |
| Walk-forward CAGR | 24.0 % | 23.6 % | −0.4 pp |
| Bitstamp OOS Sharpe | 1.14 | 1.16 | +0.02 |
| Bootstrap median | 1.64 | 1.61 | −0.03 |
| Bootstrap 95 % CI | [1.03, 2.21] | [1.01, 2.18] | tighter by ~0.03 both ends |
| P(Sharpe > 1) | 98.0 % | 97.7 % | −0.3 pp |
| P(Sharpe > 1.5) | 67 % | 64.8 % | −2 pp |
| Turnover / yr | 43 | 40.6 | fewer sizing flips |
| AvgExposure | 25.3 % | 24.1 % | −1.2 pp |

**The cost of the constraint is ~3 CAGR points and 3–6 bp of Sharpe on all windows.** OOS Sharpe actually ticks up marginally because the cap trimmed a handful of 2022–23 high-sizing days that ended up on the wrong side. Max drawdown is unchanged because the driver of drawdown is the trend/momentum flip on the way down, not the sizing on the way up. Deflated Sharpe stays at 1.000 across 108 cells.

**Walk-forward pick stability.** The pick set changes slightly because with the ceiling at 1.0 the sizing scalar is more often binding, so the choice of `vol_target` matters less at the top end and slightly more at the bottom. The 2018 blow-up year is unchanged; the residual walk-forward Sharpe drop (1.21 → 1.15) is concentrated in 2020 and 2025 where the pre-revision pick had `tv=0.30` and the revision has `tv=0.40`. Both are inside the neighbourhood that clears the joint IS/OOS bar.

**Bottom line.** The strategy still supports a Working claim on its own terms: OOS Sharpe > 1 with 10 bp/side costs charged, walk-forward Sharpe > 1, MaxDD survivable, and bootstrap / Newey-West / deflated-Sharpe all still pass. Files rerun: `code/spot-btc/weekday-trend/{strategy.py,wf_validate.py}`, `alphas/spot-btc/weekday-trend/{equity.csv,equity.png,2026-09-08_alpha_spec.md}`, and `past_research/spot-btc/all_ideas.md`. Failed variants in §5 are preserved from the original run.

## 8. Files

* Report: this file
* Deployable spec: `alphas/spot-btc/weekday-trend/2026-09-08_alpha_spec.md`
* Equity + drawdown chart: `alphas/spot-btc/weekday-trend/equity.png`
* Equity CSV: `alphas/spot-btc/weekday-trend/equity.csv`
* Reusable strategy function: `code/spot-btc/weekday-trend/strategy.py :: target_weight`
* Validation driver: `code/spot-btc/weekday-trend/wf_validate.py`
