# xs-momentum-neutral — regime-hedged betting-against-beta on liquid altcoins

**Date:** 2026-09-17 · **Asset class:** crypto-alts · **Status:** Working (borderline; see §9)

**Brief:** "1+ sharpe, winning in bear markets."

The short name was fixed when the seed was cross-sectional momentum on a dollar-neutral alt book. Momentum itself failed (§5.1); the mechanism that survived is betting-against-beta (BAB) with a regime-dependent hedge. The name is kept because it is the same research cycle and the same folders; the spec title says what the strategy actually is.

## 1. Idea

Altcoins load on a single dominant factor (BTC) with betas that disperse widely across names, from ~0.6 (exchange tokens, old large caps) to ~1.8 (new L1s, memecoins). Frazzini & Pedersen's betting-against-beta says high-beta assets are overpriced relative to low-beta ones because levered investors bid them up; in crypto the same story is stronger since leverage is the default way to express a view. A book long low-beta / short high-beta alts should therefore earn a positive alpha with a *negative* beta — exactly the payoff profile that "wins in bear markets".

The regime wrinkle: in bull phases the negative beta of a dollar-neutral BAB book bleeds. Sizing the legs to zero beta when BTC is above its 50-day SMA (net long dollars) and dollar-neutral when it is below turns a 0.7-Sharpe pure-alpha book into a 1.2-Sharpe book that is still positive in every bear phase.

## 2. Data

* 65 yfinance `<COIN>-USD` daily series, 2017-11-09 → 2026-09-17, fetched through `research_lib.load_series` into the flat `data/` cache (61 alt candidates + BTC + ETH; 14 requested tickers Yahoo does not serve: UNI, APT, SUI, MATIC/POL, FTM, GRT, COMP, STX, PEPE, IMX, TAO, TON, TRUMP).
* Yahoo's crypto `Volume` is already USD notional. Namesake traps: `ARB-USD` is a 2017 coin, not Arbitrum (dropped); `FIL`, `ONE`, `RENDER` carry pre-launch prints (masked before the real listing). `clean_close` masks isolated >150% daily moves.
* Universe rule (point-in-time, past data only): ≥120 closes, trailing 90-day median volume ≥ $5M, top-20 by that median. First fully populated 2018-03-08. Survivorship: no delisted coins in Yahoo, so LUNA/FTT-type collapses are absent — those would have been short-leg gains.
* Shared helpers added: `code/crypto-alts/shared/universe.py`; `research_lib.rank_xs / quantile_weights / linear_weights / backtest_xs` (asset-agnostic multi-asset backtest, weights shifted one bar, cost on Σ|Δw|).

## 3. Method and split

* Fixed before the first backtest: **IS 2018-01 → 2022-12**, **OOS 2023-01 → 2026-09**. Cost 10 bp per side, ANN = 365.
* Ex-post BTC bear phases for evaluation, frozen before any strategy was scored against them (`common.BEAR_WINDOWS`): 2017-12-16→2018-12-15 (−83%), 2019-06-26→2020-03-12 (−62%), 2021-04-13→2021-07-20 (−53%), 2021-11-08→2022-11-21 (−77%), 2025-10-06→2026-06-30 (−53%, inside OOS). Peak-to-trough phases only; recoveries do not count as bear.
* Also reported: BTC>SMA200 bull/bear split (a trading-regime view), calendar years.
* Lookahead check: weights recomputed on data truncated at five dates equal the full-sample weights on those dates to 0.0 (`08_final.py` companion check).

## 4. Screening stages (1101 configurations)

| Stage | Script | Configs | What |
|---|---|---|---|
| 1 | `01_explore.py` | 162 | XS momentum: lookback 7–180 × skip 0–7 × {tercile, rank-linear} × hold 1/3/7 |
| 2 | `02_families.py` | 68 | per-alt TSMOM L/S, SMA trend, alt-vs-BTC relative trend, basket trend (L/S, long-only, short-only), dollar-neutral BAB, low-vol, regime-conditioned momentum |
| 3 | `03_more.py` | 140 | short-term reversal 1–7d, BTC lead-lag, residual reversal/momentum, BAB variants (quantile, beta-neutral, vol-scaled), trend+BAB blends, universe 10/15/20/30 |
| 4 | `04_bab.py` | 216 | BAB grid: universe × beta window × {OLS, EWM, FP} × {dollar-neutral, beta-neutral} × hold |
| 5 | `05_overlay.py` | 77 | dollar-neutral BAB + regime-timed long/short basket overlays, bn/dn switch across 9 regime definitions, leg decomposition |
| 6 | `06_robust.py` | 162 | clean parametrisation grid + walk-forward |
| 7 | `07_compare.py` | 276 | hedge-mode distributions (always-bn, always-dn, switch, bear target beta −0.1/−0.2), vol targeting |

## 5. Results

### 5.1 Cross-sectional momentum — Failed
Best cell 14d/skip 7/tercile/hold 7: full 0.56, IS 0.44, OOS 0.77. Medians by lookback all ≤ 0.31; 60–180d lookbacks negative OOS. Skipping the last week helps slightly; nothing near 1. Residual (BTC-hedged) momentum 14d: 0.64 at universe 15, 0.25 at universe 20 — unstable.

### 5.2 Reversal, lead-lag — Failed hard
1–7 day cross-sectional reversal: Sharpe −0.6 to −2.9 net (turnover 70–340×/yr; the gross sign is momentum, not reversal). BTC 1-day lead on alts: −1.1 (reversed, i.e. alts do not lag BTC by a day any more); 2–3 day lead: 0.2. Residual 1-day reversal −2.5.

### 5.3 Trend on alts — bull-only
Per-alt 14d TSMOM long-only 0.82 full but bear −0.32; long/short 0.69 with short legs at −1.0 in bull. Basket-level SMA long/flat 0.5–0.8. Short-only legs earn 0.7–0.9 in bear and lose 1.0+ in bull under any regime filter tried (SMA 20–200 on BTC or the basket): daily alt shorts on a trend signal are whipsawed to death.

### 5.4 Betting-against-beta — the edge
Dollar-neutral BAB (universe 20, EWM-60 beta, rank-linear, hold 14): full 0.74 / IS 0.95 / OOS 0.51, but **pooled bear 1.62** with every bear phase positive (0.33, 0.71, 4.36, 2.80, 1.05) and non-bear 0.07. Leg decomposition: the short high-beta leg earns 1.2–1.9 Sharpe in every bear phase and loses in bulls; the long low-beta leg is the mirror. Beta of the book to BTC −0.09.

Across the 216-config BAB grid: dollar-neutral median pooled-bear 1.26, non-bear −0.03; beta-neutral median full 0.90, non-bear 1.15, bear 0.10. EWM betas beat OLS and Frazzini-Pedersen (corr × vol ratio) betas; halflife 30–60 beats 90–120; hold 14 ≥ 7 > 3; universe 20 > 15 > 25.

### 5.5 Regime-hedged BAB — final
Beta-neutral legs when BTC > SMA50, dollar-neutral otherwise. Over 9 regime definitions (BTC/basket SMA 50/100/200, BTC 30/60/90d momentum) the switch gives full 1.06–1.27, OOS 0.84–1.20, pooled-bear 1.13–1.59, never worse than the dollar-neutral book in any bear phase except 2018 (0.11–0.54 vs 0.33).

Hedge-mode distributions on the common 54-config grid (medians): always-beta-neutral 1.12 full / 1.01 OOS / bear 0.67 with 3 of 5 bear phases negative; **switch 1.09 / 0.80 / 1.20 with 4 of 5 positive** (2019-20 ≈ −0.1); always-dollar-neutral 0.73 / 0.37 / 1.58 with 5 of 5 positive. An intermediate bear target beta (−0.1) sits between (1.11 / 0.97 / 0.89). The switch is the only mode that is both ≥ 1 and bear-positive; it pays for that with ~0.2 of OOS Sharpe versus the always-beta-neutral book. The seed asked for bear robustness, so the switch is the deliverable.

Final defaults (universe 20, EWM halflife 60, terciles 30%, SMA50, hold 14), 2018-03-08 → 2026-09-17, 10 bp:

| | Sharpe | CAGR | MaxDD | Turnover | Net exp |
|---|---|---|---|---|---|
| Full | **1.22** | 29.9% | −30.4% | 9.1×/yr | +0.13 |
| IS | 1.35 | 33.8% | −30.4% | | |
| OOS | **1.05** | 25.1% | −28.8% | | |
| Bear phases pooled | **1.49** | 39.7% | −26.4% | | |
| Non-bear | 1.02 | 23.5% | −30.6% | | |

Per bear phase: 2018 +0.25, 2019-20 +0.26, 2021 +4.32, 2022 +2.71, 2025-26 (OOS) +0.78. Yearly: 2018 −0.2, 2019 −0.5, 2020 0.7, 2021 3.0, 2022 2.7, 2023 0.5, 2024 1.5, 2025 2.4, 2026 YTD −0.7. Beta to BTC −0.04 (0.01 bull, −0.08 bear). t_NW 3.15.

### 5.6 Things that did not help
* Portfolio vol targeting (15–25%, scale-down only): 0.91–1.09 full, OOS 0.70–0.92 — it cuts exposure exactly in the high-vol bear phases where the book earns.
* Long-only trend + dollar-neutral BAB blends: 0.78–0.98 full, bear −0.3 to −0.6.
* Adding a short-basket overlay in bear (LS overlays): bear improves, bull whipsaw costs more; 0.45–0.97.
* Bigger universe (25–30): more small, noisy names in the legs; 0.7–0.9.

## 6. Robustness

* 162-config grid (§4 stage 6): full min 0.68 / 25% 0.90 / median 1.03 / max 1.38; OOS median 0.70, P(OOS ≥ 1) = 12%; pooled bear > 0 in 100%, all five phases > 0 in 11%. Equal-weight of all configs: 1.13 full / 1.41 IS / 0.78 OOS.
* Walk-forward (best full-Sharpe config on expanding window, applied to the next calendar year, 2021-2026): stitched 1.55; realised 2.2, 2.8, 0.6, 1.5, 2.4, −0.9. Only six test years, two of them bear years.
* Cost: 1.26 (0 bp) → 1.22 (10) → 1.18 (20) → 1.14 (30). Turnover is low because of the 14-day tranche averaging.
* Short-leg carry (funding/borrow, not modelled): 5%/yr on short notional → 1.13 / OOS 0.97; 10% → 1.04 / 0.88; 20% → 0.85 / 0.71. **This is the binding real-world risk**: in bear phases funding on high-beta alts is often negative (shorts pay).
* Block bootstrap (30d, 2000): mean 1.25, 5–95% [0.64, 1.82], P(Sh > 1) 75%, P(Sh > 0) 100%.
* Deflated Sharpe (skew 0.35, kurt 10): 0.98 at 10 trials, 0.90 at 50, 0.79 at 200, 0.63 at 1000. The 1101 configurations are heavily correlated (one mechanism, five knobs); effective trials are closer to 50 than 1000.
* OOS composition: long leg dominated by TRX, BNB, LTC, XRP, BCH (and SHIB — a low-beta memecoin, which is uncomfortable); short leg NEAR, SOL, WIF, DOGE, ADA, BONK, OP. Largest OOS losers: SOL short (−28% cumulative contribution), ZEC short (−21%, the late-2025 ZEC rally); largest winners XRP long (+31%), SHIB long (+26%), TRX long (+24%).

## 7. Weaknesses, honestly

1. **OOS is 1.05 for the spec but 0.70 for the median config.** The spec's universe size (20) was the best of {10,15,20,30} in stage 3 before the grid; halflife 60 / SMA50 / hold 14 were central choices. Treat the OOS number as 0.7–1.05.
2. 2018 and 2019-20 bears are only marginally positive (+0.25); the big bear numbers are 2021-22 and 2025-26. Two calendar years (2018, 2019) and 2026 YTD are negative.
3. The hedge switch is BTC-SMA50 market timing. It is what makes the book bear-positive, and it costs OOS Sharpe versus the always-beta-neutral book.
4. Short-leg carry is unmodelled and can plausibly cost 5–10%/yr of short notional.
5. Survivorship helps the long leg slightly (no dead low-beta names) and hurts the short leg (no LUNA/FTT).

## 8. Files

* `code/crypto-alts/xs-momentum-neutral/`: `common.py` (panel, splits, bear windows), `01_explore.py` … `09_figures.py`, `strategy.py::alt_bab_weights`, CSV outputs per stage (`families_02.csv`, `more_03.csv`, `bab_04.csv`, `overlay_05.csv`, `robust_06.csv`, `compare_07.csv`), `final_08.log`, `compare_07.log`, `weights_final.parquet`, `grid_nets.parquet`.
* `code/crypto-alts/shared/universe.py`; `code/shared/research_lib.py` (+ cross-sectional helpers).
* `alphas/crypto-alts/xs-momentum-neutral/spec.md` + five PNGs + `backtest_series.parquet`.

## 9. Verdict

Working, borderline. Against "1+ Sharpe, winning in bear markets": the spec config clears both (1.22 full, 1.05 OOS, all five bear phases positive, pooled bear 1.49) and the grid supports the bear claim unconditionally (100% of configs bear-positive) and the Sharpe ≥ 1 claim on the full sample (median 1.03) but not on the OOS sample (median 0.70). Deploy at ≤ 1.0× gross only if short-leg funding is confirmed to cost < 10%/yr; otherwise archive as a research record.

Next researcher: the BAB alpha itself is robust and bear-driven; the weak part is the hedge. A better bull/bear classifier than SMA50 (e.g. one built from the alt basket's own drawdown or from realised-vol regimes) or a continuous beta target would be the natural extension. Do not re-run momentum, reversal or lead-lag on daily alt data — they are dead at 10 bp.
