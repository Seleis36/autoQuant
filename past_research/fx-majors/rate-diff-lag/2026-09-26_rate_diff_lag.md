# Rate-differential lead-lag (market yields → FX) — Failed

**Asset class:** `fx-majors` · **Short name:** `rate-diff-lag` · **Date:** 2026-09-26
**Status:** **Failed.** The pre-specified multi-horizon composite is net Sharpe **0.36 full /
0.17 IS / 0.61 OOS** on `=X` and 0.24 on H.10 2002-2026. Whatever lead the rate
differential has over spot shows up only in the 2021-2025 rate cycle.

## Idea

Rate differentials are the first-order driver of G10 FX. `policy-rate-momentum` showed that
the *realised* policy path is priced before it happens; market yields are the expectations
themselves and move daily. If spot under-reacts to them (slow-moving real-money hedging,
inattention), the recent change of the 2y/5y differential should predict the currency (H1);
alternatively FX drifts back to the level the differential implies (H2, fair-value gap).

## Data

New fetcher `code/fx-majors/shared/fetch_yields.py`, caches `data/YLD_<CCY><TENOR>_d.parquet`:
USD FRED `DGS2`/`DGS5`; EUR Bundesbank Svensson Bund curve 2y/5y; JPY MoF constant-maturity
JGB 2Y/5Y (history + current-month files, Shift-JIS); CAD Bank of Canada Valet 2y/5y
benchmarks; GBP Bank of England IADB `IUDSNZC` (5y nominal zero coupon — the IADB has no 2y).
Not obtainable: AUD (RBA site refuses scripted access), CHF (SNB `rendoblid` cube ends
2025-07), NZD. So the test runs on EUR, GBP, JPY, CAD vs USD. Yields stamped D−1 (local
closes, all final before 00:00 UTC D) set the weight of `=X` row D; costs are the measured
00:00 UTC half-spreads; H.10 noon rates for 2002-2026 with yields stamped D−1 (conservative).

## Results

### 01 — pre-registered H1 and H2 (`01_screen.py`, 32 + 6 configurations)

| Signal (5y) | Book | Rebal | Full | IS | OOS | Turnover |
|---|---|---|---:|---:|---:|---:|
| H1 Δd 1 day | pair vs USD | D | −0.11 | −0.49 | 0.41 | 131 |
| H1 Δd 5 days | pair vs USD | W | 0.38 | 0.01 | 0.98 | 27 |
| H1 Δd 20 days | pair vs USD | W | 0.38 | 0.33 | 0.45 | 14 |
| H1 Δd 20 days | 5-ccy XS | W | 0.08 | 0.13 | 0.00 | 30 |
| H2 fair-value gap | pair vs USD | W | 0.20 | −0.00 | 0.48 | 9 |
| H2 fair-value gap | 5-ccy XS | W | 0.25 | 0.12 | 0.47 | 17 |
| H1 Δd 20 days, **2y** | pair vs USD | W | 0.45 | 0.40 | 0.51 | 13 |

H.10 2002-2026, 5y, weekly: H1 Δd5 pair 0.11 / −0.10 / 0.67 (by 2002-09 / 2010-19 / 2020-26),
H1 Δd20 pair 0.29 / 0.04 / 0.30, H2 pair −0.18 / 0.02 / 0.48. Every reversed sign is
negative, so there is a direction, but it is weak and concentrated after 2020.

### 02 — re-framings (`02_regime.py`)

| Book | `=X` Full | IS | OOS | H.10 02-09 | 10-19 | 20-26 |
|---|---:|---:|---:|---:|---:|---:|
| COMP: mean z(Δd 5/20/60d), 2y and 5y, pair vs USD | 0.36 | 0.17 | 0.61 | 0.21 | 0.12 | 0.42 |
| COMP, 5-ccy XS | 0.17 | −0.09 | 0.63 | 0.19 | −0.02 | 0.30 |
| COMP gated on 60d FX-rates correlation > expanding median | 0.17 | −0.04 | 0.50 | 0.06 | −0.06 | −0.14 |
| COMP scaled by that correlation | 0.30 | 0.04 | 0.67 | −0.03 | −0.04 | −0.09 |

COMP per-year Sharpe: 2021 1.65, 2022 1.17, 2024 1.33, but 2012 −0.60, 2013 −0.89, 2017 −0.36,
2020 −0.25. The regime gate, meant to keep the signal on only when FX is rate-driven, hurts
everywhere.

## Why it fails

Spot absorbs rate moves within the day. The =X print sits ~4 hours after the US yield close,
so the only thing left to predict is a slow drift that exists in years when a single
macro theme (divergent 2021-24 hiking cycles) dominates and vanishes in range-bound years.
With four pairs the breadth is also too small to diversify the per-pair noise.

## Variants tried

38 (01) + 12 (02) = **50 configurations**. Best `=X` full-sample cell 0.45; best-of-50 null
≈ 0.55 on a 16-year sample.

## Files

`code/fx-majors/rate-diff-lag/01_screen.py`, `02_regime.py` (+ CSV/parquet). Shared:
`code/fx-majors/shared/fetch_yields.py`. No alpha spec.
