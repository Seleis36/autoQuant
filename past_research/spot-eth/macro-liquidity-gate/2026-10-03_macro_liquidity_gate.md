# macro-liquidity-gate — credit, dollar and equity risk state as a gate on spot ETH

**Date:** 2026-10-03
**Asset:** spot ETH/USDT (Binance daily bars, 00:00 UTC), long/flat, unlevered, 10 bp/side
**Status:** **Failed** — the BULT macro regime lifts the ETH trend filter in every in-sample cell and in a quarter of the out-of-sample ones; the one strong cell is a best-of-24.

| 2018-06 → 2026-10, 10 bp/side | full | IS ≤ 2023 | OOS 2024+ |
|---|---|---|---|
| live `eth-trend-filter` | 1.10 | 1.06 | 1.18 |
| **pre-registered port: TF × BULT macro composite** | **1.22** | 1.28 | **1.09** |
| BULT base on ETH (trend ensemble × macro × vol 0.35) | 1.19 | 1.31 | 0.92 |
| macro composite × vol, no trend | 0.82 | 1.13 | 0.30 |
| best cell found: TF AND fast-60d macro state | 1.42 | 1.35 | 1.55 |
| macro-gate family, median of 24 cells | 1.21 | 1.28 | 1.11 |
| walk-forward over the family, 2021+ (TF 0.96) | 0.96 | | 1.22 (TF 1.18) |

## 1. Idea

`spot-btc/bult` (2026-09-06, live) times BTC with a macro-liquidity regime: the share of
50–250-day moving averages that HYG, LQD and the S&P 500 are above and the dollar index is below.
Its report says the composite is only 0.37 correlated with BTC's own trend and that the result
"replicates on ETH" — but the ETH line there is about the intraday window, not the regime. ETH is
the higher-beta risk asset, so a risk-state gate should matter at least as much. The test is a
port with the tickers and lookbacks unchanged, judged on what it adds to the live trend filter.

## 2. Data and timing

- yfinance daily closes from the flat cache: HYG, LQD, DX-Y.NYB, ^GSPC (and ^VIX for §5), through
  2026-10-02.
- The US session of date D closes at 20:00/21:00 UTC, three hours before the ETH daily bar D
  closes (D+1 00:00 UTC). The macro row dated D is used for the weight held over bar D+1 — BULT's
  convention. Weekends and holidays carry the last close forward. Lags of 1, 2 and 5 days are
  shown.
- Evaluation from 2018-06 (the 200-day ETH lookback of the BULT trend ensemble); IS ≤ 2023, OOS
  2024+.

## 3. Port (`exp01_replicate.py`)

Composite: mean 0.67; correlation 0.23 with ETH's SMA40 state and 0.36 with the trend ensemble —
it is not ETH's trend in disguise.

| | full | IS | OOS | CAGR | MaxDD | turn | expo | ρ to TF | alpha t vs TF (full / IS / OOS) |
|---|---|---|---|---|---|---|---|---|---|
| vol B&H | 0.63 | 0.72 | 0.45 | 19% | −59% | 4× | 0.56 | 0.72 | |
| TF_live | 1.10 | 1.06 | 1.18 | 40% | −48% | 18× | 0.35 | | |
| M1 macro × vol | 0.82 | 1.13 | 0.30 | 22% | −49% | 7× | 0.38 | 0.73 | 0.09 / 1.28 / −1.05 |
| B1 BULT base on ETH | 1.19 | 1.31 | 0.92 | 23% | −18% | 8× | 0.19 | 0.85 | 1.49 / 1.92 / −0.22 |
| B0 the same without macro | 1.11 | 1.19 | 0.95 | 27% | −26% | 10× | 0.25 | 0.88 | 0.97 / 1.36 / −0.20 |
| **G1 TF × macro (the port)** | 1.22 | 1.28 | 1.09 | 36% | −34% | 15× | 0.26 | 0.94 | 1.61 / 1.89 / −0.54 |
| G2 TF AND macro > 0.5 | 1.31 | 1.33 | 1.28 | 47% | −40% | 15× | 0.29 | 0.92 | 2.25 / 2.00 / 1.09 |
| G3 TF × (0.5 + 0.5 macro) | 1.17 | 1.18 | 1.15 | 38% | −38% | 16× | 0.31 | 0.99 | 1.62 / 1.90 / −0.52 |
| D1 50/50 TF + M1 | 1.05 | 1.16 | 0.83 | 32% | −33% | 12× | 0.37 | 0.94 | 0.10 / 1.29 / −1.04 |

Partial IC of the composite after trend controls (HAC t):

| | h = 1 | h = 7 | h = 30 |
|---|---|---|---|
| IS | +0.048 (2.4) | +0.103 (2.5) | +0.185 (2.7) |
| OOS | −0.007 (−0.8) | −0.070 (−1.2) | −0.115 (−1.3) |

Significant and positive in sample, negative out of sample.

Next-day ETH return by state (bp): in an up-trend with macro on, +47 IS (t 3.0) and +36 OOS
(t 2.2); in an up-trend with macro off, −10 and −7. That is the part that works. In a down-trend
with macro on: +3 IS, −25 OOS — macro alone does not make ETH worth holding, which is why the
standalone timer is 0.30 OOS.

On BTC over the same window the BULT base gives 1.25 / 1.43 / 0.86; the ETH port correlates 0.69
with it.

## 4. Why the out-of-sample half says so little (`exp02_fast_and_robust.py`)

Share of days with the composite above 0.5: 0.42, 0.97, 0.78, 0.91, **0.09**, 0.77, **0.95**,
**0.91**, 0.74 for 2018 … 2026. The slow regime was open for almost all of 2024–25; it removed a
trend-filter position on 1 day in 2024 and 4 in 2025. All its out-of-sample information is 64
days in 2026. On the 68 OOS days it removed, the next-day return was −7 bp (t −0.2).

Robustness of G2, the binary gate:

| | full | IS | OOS |
|---|---|---|---|
| threshold 0.3 / 0.4 / **0.5** / 0.6 / 0.7 | 1.14 / 1.19 / **1.31** / 1.29 / 1.16 | 1.12 / 1.23 / 1.33 / 1.41 / 1.35 | 1.18 / 1.11 / **1.28** / 1.04 / 0.72 |
| macro lag 0 / 1 / 2 / 5 days | 1.31 / 1.25 / 1.20 / 1.23 | 1.33 / 1.29 / 1.23 / 1.18 | 1.28 / 1.17 / 1.14 / 1.32 |
| lookbacks (50) / (100) / (200) / (20,50,100) / (150,200,250) | 0.90 / 1.28 / 1.27 / 1.16 / 1.22 | 0.96 / 1.33 / 1.43 / 1.16 / 1.34 | 0.76 / 1.20 / 0.90 / 1.16 / 0.98 |
| without HYG / LQD / DXY / SPX | 1.24 / 1.34 / 1.29 / 1.15 | 1.32 / 1.40 / 1.36 / 1.20 | 1.07 / 1.20 / 1.17 / 1.03 |

- Circular-shift placebo of the macro state (500 draws): G2 1.31 against a placebo mean of 0.92
  (sd 0.20), p = 0.020.
- Block bootstrap of Sharpe(G2) − Sharpe(TF): median +0.22, 5–95% [−0.01, +0.44], P(> 0) 0.94.
- OOS is a knife edge on the threshold: 1.28 at 0.5, 1.04 at 0.6, 0.72 at 0.7.

## 5. A faster macro state, and the whole family (`exp02`, `exp03_neighbourhood.py`)

If the slow regime is always open, a faster one might discriminate: the sign of k-day momentum
of HYG, LQD, SPX (+), DXY and VIX (−), averaged. Two horizons were fixed a priori (20, 60):

| | full | IS | OOS | alpha t vs TF (full / IS / OOS) |
|---|---|---|---|---|
| TF × fast20 | 1.24 | 1.27 | 1.17 | 1.53 / 1.61 / 0.29 |
| TF AND fast20 > 0.5 | 1.17 | 1.24 | 1.05 | 1.22 / 1.39 / 0.03 |
| TF × fast60 | 1.29 | 1.28 | 1.31 | 2.08 / 1.80 / 1.05 |
| **TF AND fast60 > 0.5** | **1.42** | 1.35 | **1.55** | 2.60 / 1.99 / 1.68 |

One cell stands out, so the family was run in full before believing it — 8 horizons (10 … 250
days) × 3 forms for the composite, and each of the five series alone at each horizon:

| family | cells | median lift over TF: full / IS / OOS | share with lift > 0: IS / OOS / both | IS→OOS Spearman |
|---|---|---|---|---|
| composite | 24 | +0.11 / **+0.22** / **−0.07** | 1.00 / 0.25 / 0.25 | +0.22 |
| single series | 40 | +0.02 / +0.09 / −0.17 | 0.65 / 0.28 / 0.15 | −0.12 |
| all | 64 | +0.07 / +0.18 / −0.12 | 0.78 / 0.27 / 0.19 | −0.01 |

OOS Sharpe of TF AND state > 0.5 by horizon: 0.23, 1.05, 0.96, **1.55**, 1.27, 1.15, 1.07, 1.17
for k = 10 … 250, against 1.18 for the trend filter. k = 60 is the peak of a ridge two cells wide.

- The IS-best composite cell (k = 250, AND) goes 1.39 IS → 1.17 OOS; the trend filter is 1.18.
- Walk-forward with yearly re-selection over the 24 composite cells, 2021+: **0.96 against 0.96**
  for the trend filter; 2024+: 1.22 against 1.18.

## 6. Verdict

**Failed.** A macro risk state improves the ETH trend filter in sample in every one of 24
composite cells, and the conditional returns have the right shape (up-trend with macro on: +47 /
+36 bp a day; up-trend with macro off: −10 / −7). But:

- the pre-registered port is *below* the trend filter out of sample (1.09 against 1.18), and the
  partial ICs turn negative;
- the family's median OOS lift is −0.07, a quarter of the cells beat the trend filter in both
  halves, and the selection-adjusted walk-forward ties it;
- the slow regime was open on 93% of OOS days through 2025, so most of the OOS evidence is 64 days
  of 2026.

The binary gate on the unchanged BULT composite (G2: 1.31 / 1.33 / 1.28, placebo p 0.02,
bootstrap lift [−0.01, +0.44]) is the closest thing to a result. It is recorded here as a
candidate, not an amendment: it was not the pre-registered form, and its OOS rests on one
threshold. The next macro-off episode will say more than this sample can.

Binding constraint: too few regime changes. Six years of in-sample contain two macro-off
regimes (2018, 2022); the out-of-sample half contains a fraction of one.

Configurations evaluated: 9 forms of the slow composite, 8 component sleeves, 21 robustness
cells for G2, 8 fast variants, 64 family cells; partial ICs at 3 horizons for 3 composites.

## 7. Files

- `code/spot-eth/macro-liquidity-gate/exp01_replicate.py` — composite builder (BULT, unchanged) and the port
- `exp02_fast_and_robust.py`, `exp03_neighbourhood.py` (+ `exp03_family.csv`)
