# Sleeve blend: COT positioning + three weak macro sleeves — Failed (as an improvement)

**Asset class:** `fx-majors` · **Short name:** `fx-sleeve-blend` · **Date:** 2026-09-26
**Status:** **Failed.** The idea was that adding this session's weak but uncorrelated sleeves
to `cot-positioning` would raise its risk-adjusted return materially. It does not: the
equal-risk blend is **0.83 full / 0.94 IS / 0.68 OOS** against 0.80 / 0.91 / 0.64 for COT
alone, and needs three more data pipelines (local equity indices, commodity futures,
five central-bank yield sources). The blend is profitable, but it is not worth deploying
in place of COT.

## Sleeves and the inclusion rule (declared before the blend was run)

Every sleeve found this session whose **pre-specified composite** (not its best cell) is
positive net on both `=X` 2010-2026 and the Fed H.10 long sample:

| Sleeve | Definition | Standalone at 5 % vol (Full / IS / OOS) |
|---|---|---|
| COT | `cot-positioning` book C (6 contrarian COT legs, weekly) | 0.80 / 0.91 / 0.64 |
| EQM | equity momentum: z(1/3/6/12m local-index return), G8 demeaned, weekly (`equity-flow-rebalance`) | 0.40 / 0.55 / 0.18 |
| TOTB | commodity-bloc ToT gap, mean of 6m and 12m, AUD/CAD/NZD demeaned, monthly (`terms-of-trade-fx`) | 0.33 / 0.49 / 0.10 |
| RDL | rate-differential composite, EUR/GBP/JPY/CAD vs USD, weekly (`rate-diff-lag`) | 0.38 / 0.20 / 0.66 |

`policy-rate-momentum` is excluded (negative). Daily net-return correlations: COT-EQM 0.23,
COT-TOTB 0.12, COT-RDL −0.08, the others within ±0.14.

Each sleeve is scaled to 5 % ex-ante vol (EWMA 126d of its unit book, re-set weekly,
scalar ≤ 3), averaged, re-scaled to 5 %, gross capped at 3; costs at the blend level with
the measured 00:00 UTC half-spreads (legs net across sleeves).

## Results (`01_blend.py`, four declared books)

| Book | Full | IS | OOS | t | CAGR | MaxDD | Turnover | Cost bp/yr | Full @ ×2 cost | OOS @ 1 bp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| COT only | 0.80 | 0.91 | 0.64 | 3.38 | 3.9 % | −11.4 % | 34.8 | 20 | 0.76 | 0.60 |
| **EQ4** (equal risk) | **0.83** | 0.94 | **0.68** | 3.33 | 4.3 % | −11.4 % | 44.3 | 24 | 0.79 | 0.63 |
| WF4 (walk-forward inclusion: expanding Sharpe > 0) | 0.83 | 0.93 | 0.68 | 3.33 | 4.2 % | −11.4 % | 44.0 | 24 | 0.78 | 0.63 |
| EQ3 without COT | 0.58 | 0.63 | 0.50 | 2.41 | 2.8 % | −10.9 % | 40.7 | 20 | 0.54 | 0.45 |

The walk-forward rule drops only RDL in 2014, so WF4 ≈ EQ4. A post-hoc check
(`02_posthoc_srweight.py`, not one of the declared books): walk-forward weights proportional
to each sleeve's expanding Sharpe give 0.78 / 0.86 / 0.66 — allocation is not the missing piece.

Per-year Sharpe, COT vs EQ4: the blend helps in 2012, 2015, 2021, 2022, 2025 and hurts in
2017 (1.31 → −0.05), 2020 (0.32 → −1.04), 2023 (0.70 → −0.73), 2026 (1.36 → 0.41).

## Why it fails

With a 0.8 core and three ≈ 0.35-0.40 sleeves at low correlation, equal risk weighting
gives the core only a quarter of the risk; the arithmetic ceiling for equal weights is
≈ 0.87 and the optimum (weights ∝ Sharpe, known only in hindsight) ≈ 1.0. The weak sleeves
are also weakest exactly out of sample (EQM 0.18, TOTB 0.10), so the blend’s OOS gain is 0.04.

## Takeaway for deployment

Deploy `cot-positioning` alone. The three weak sleeves are a modest, largely independent
second edge (0.57 / 0.50 together) that a future cycle could strengthen — most promisingly
RDL, which is the only one that is better OOS than IS, and which needs AUD/CHF/NZD daily
yields that were not scriptable here.

## Variants tried

4 declared books + 1 post-hoc weighting = **5 configurations** (sleeve definitions were
fixed by the earlier ideas).

## Files

`code/fx-majors/fx-sleeve-blend/sleeves.py` (the four sleeve builders), `01_blend.py`,
`02_posthoc_srweight.py`, `01_blend.csv`, `01_blend_nets.parquet`. No alpha spec.
