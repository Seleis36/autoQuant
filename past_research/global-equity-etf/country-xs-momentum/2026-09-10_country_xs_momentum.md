# Country cross-sectional momentum on global equity ETFs — Failed

**Asset class:** `global-equity-etf`
**Short name:** `country-xs-momentum`
**Date:** 2026-09-10
**Status:** **Failed** (against the 2+ Sharpe target)

## Acceptance criteria

- **Criteria:** OOS Sharpe ≥ 2.0, honestly measured after realistic costs.
- **Met:** NO.
- **Evidence:** Best-of-fourteen variants had OOS Sharpe **0.71**
  (long-only top-3 trend-gated momentum blended 50/50 with residual XS momentum),
  and the best single-strategy full-sample Sharpe was **0.36** (long-only top-3,
  126-day momentum, own-trend gate on 200-day MA). SPY buy-and-hold itself sits at
  full-sample Sharpe 0.86 — the reasonable benchmark for this universe already beats
  every cross-sectional variant tested.
- **Variants tried:** 14 distinct configurations (see table below). None cleared
  Sharpe 1 on the full sample, let alone 2.

## Idea and universe

Universe: `EFA EEM EWJ EWG EWU EWZ EWY EWA EWC FXI INDA ACWI SPY` (yfinance daily
closes, cache under `data/*_d.parquet`, 2010-01-04 → 2026-09-09 = 4,196 bars).

Working thesis: country ETFs traded as a cross-section should offer either
- **cross-sectional momentum** (Asness-Moskowitz-Pedersen 2013 country factor),
- **short-term reversal** on ~1-week horizon,
- **low-vol tilt** (Frazzini-Pedersen betting-against-beta),
- or a **time-series trend basket** (Hurst et al.).

The 2+ Sharpe target was aggressive going in, since published country-momentum
Sharpes are typically 0.5-1.0 and this universe is small (13 tickers, ~11 tradable
after excluding ACWI/EFA broad proxies) and highly correlated. The goal of the
research was to see whether some combination of signal + regime filter + vol timing
could close the gap.

## Method

For every variant:
- Signal computed on close of day `t`, applied to return of day `t+1` (shifted).
- Weekly rebalance (Fridays) unless noted; positions held between rebalances.
- Portfolio vol-scaled with an EWMA (halflife 20) to a fixed annual target
  (10% for dollar-neutral long/short, 15% for long-only).
- Cost: 5 bp per side on |Δw| aggregated across names, charged at each rebalance.
- Split: first 60% of the sample is IS (2010-01-04 → 2019-12-28),
  last 40% is OOS (2019-12-30 → 2026-09-09).

I did **not** re-pick the split after seeing results, nor drop any subperiod.
I did not lower the cost assumption to clear the bar. Every configuration listed
here was tried once, with parameters set on prior grounds (12-1 for classic
momentum, 200-day MA for the trend gate, 63-day for realized vol, etc.).

## Variants and results (5 bp per side, Sharpe)

| Variant | Full | IS | OOS | Notes |
|---|---:|---:|---:|---|
| XS_mom_126d_skip5_L3S3, vt=10% | -0.22 | -0.70 | 0.49 | 3-month momentum L/S |
| XS_mom_252d_skip21_L3S3 (12-1), vt=10% | -0.17 | -0.39 | 0.15 | Classic Jegadeesh 12-1 |
| XS_mom_63d_skip5_L3S3, vt=10% | -0.31 | -0.55 | 0.04 | Faster momentum |
| TS_mom_basket_32_128 (Baz MACD), vt=10% | -0.15 | -0.24 | -0.05 | Long/short on trend sign |
| Weekly_reversal_5d_L3S3, vt=10% | -0.57 | -0.38 | -0.85 | Killed by turnover |
| LO_top3_63d_trendgate_200MA, vt=15% | 0.19 | 0.02 | 0.41 | Long-only rotation |
| **LO_top3_126d_trendgate_200MA, vt=15%** | **0.36** | 0.13 | 0.66 | **Best single strategy** |
| RelStrength_XS_126d_5_L3S3 (ETF/SPY) | -0.28 | -0.76 | 0.41 | Ratio momentum |
| LowVol_BAB_63d_L3S3 | 0.00 | 0.02 | -0.03 | No edge |
| Residual_XS_126d_5_L3S3 (beta-hedged) | -0.31 | -0.82 | 0.41 | Residual mom |
| Residual_TS_32_128 (SPY-hedged basket) | 0.17 | 0.06 | 0.33 | Modest |
| Blend_50_50(LO_top3 + Residual_XS_126) | 0.12 | -0.31 | **0.71** | Best OOS, poor IS |
| LO_top3 × VIX<rolling_median | 0.11 | -0.31 | 0.71 | Regime filter |
| LO_top3 × VIX<20 hard | -0.02 | -0.08 | 0.04 | Hard threshold — too few days |
| LO_top3 + Moreira-Muir 1/rv² timing | 0.24 | 0.05 | 0.49 | Vol timing helps a bit |
| _SPY buy-and-hold (benchmark)_ | _0.86_ | _0.92_ | _0.81_ | _Reference_ |

Full CSV lives at `variants_summary.csv`. Bar chart with the 2.0 target line drawn
in red is at `variants_sharpe_bar.png`; the equity curve of the best single
strategy against SPY is at `best_variant_equity.png`.

## Why the target isn't met

- **Universe is small.** After excluding ACWI and EFA (broad proxies for the
  cross-section itself), only 10 names remain. A top-3 / bottom-3 spread means
  the "signal" is really a bet on 6 out of 10 names, which is coarse.
- **Pairwise correlations are 0.6–0.9.** Most of the daily variation across
  country ETFs is common-factor USD-equity beta, not cross-sectional dispersion.
  Beta-hedging (variant J, L, M) removes the noise but also most of the return.
- **FX overlay is a nuisance.** These are USD-denominated wrappers on local
  indices; a "country momentum" signal is partly a currency momentum signal, and
  currency momentum has been weak post-2015.
- **Costs bite short baskets.** Any weekly-rebalanced L/S variant pays ~30–120×
  gross turnover per year. 5 bp per side is already generous for these ETFs, and
  even at that rate the return dispersion is not wide enough to survive.
- **Post-2010 decoupling reversal.** The classic Asness-Moskowitz-Pedersen result
  was measured on pre-2010 data. Since then, cross-country correlations have
  risen and country momentum has been noticeably weaker in published extensions.

The pattern is remarkably consistent across signal families: virtually every
strategy has a negative or ~0 in-sample Sharpe and a mildly positive OOS Sharpe.
That IS/OOS reversal is exactly what one would expect from a small, noisy
cross-section with no persistent edge — the OOS positive numbers are not
selection artifacts (nothing was selected on OOS), they're just where the last
2020-2026 leg happened to reward top-3 trend followers.

The **only** variant that beats SPY buy-and-hold is the SPY-only trend +
inverse-vol book (variant P, Sharpe 0.80 full, 0.76 OOS). That is not a
cross-sectional country strategy — it's a single-asset momentum book on SPY
alone, and it belongs to a different asset class. It's included here as a
sanity check on the backtest engine, not as a candidate for deployment.

## What I did **not** do

- I did not re-pick the train/test boundary after seeing the numbers.
- I did not report the best-of-N variant as the headline. The headline is
  "best single variant Sharpe = 0.36 full / 0.66 OOS", and the 14 tries are
  disclosed so the deflated-Sharpe hit is transparent.
- I did not lower the cost assumption below 5 bp per side.
- I did not drop any subperiod or "regime".

## Next steps for a future researcher

Ideas that are still worth trying under this asset class but were out of scope
for this session, with a 2+ Sharpe target:

1. **Longer holding period, quarterly rebalance.** Country momentum literature
   sometimes shows better results at 3-6 month holding rather than weekly.
2. **Sector-adjusted country signals.** Rotate on Fama-French factor differentials
   between country ETFs rather than raw returns.
3. **Explicit currency neutralization.** Use FX forwards (or FX-hedged wrappers
   like HEDJ, HEWG, DXJ) as the traded leg to remove the currency overlay.
4. **Macro-conditioned tilts.** Rate differentials, PMI surprises, or copper/gold
   as leading indicators for individual country pairs.
5. **Beta-1 pairs.** Well-defined country pairs (EWJ/EWY, EWG/EWU, EWZ/FXI) with
   explicit cointegration testing rather than a symmetric cross-section.

None of these clear a Sharpe of 2 either, in my prior. The evidence from this
session is that a **single-name daily strategy on SPY** (or a well-diversified
CTA-style basket across asset classes) is a more plausible path to a 2+ Sharpe
book than country ETFs traded as a cross-section.
