# Equity-flow rebalancing (Hau-Rey) and its mirror, equity momentum → FX — Failed

**Asset class:** `fx-majors` · **Short name:** `equity-flow-rebalance` · **Date:** 2026-09-26
**Status:** **Failed.** The pre-registered rebalancing sign is negative in every sub-period.
Its declared rival — past relative equity outperformance → currency *appreciation* — is
positive in all three sub-periods of 1999-2026, but only ≈ 0.4 net Sharpe full-sample and
0.1-0.2 out of sample. Kept as a candidate sleeve for a blend, not deployable alone.

## Idea

Hau & Rey (RFS 2006) and Camanho, Hau & Rey (RFS 2022): global equity investors rebalance
toward target weights. After a foreign market outperforms in local currency, foreign holders
are overweight it, sell, and repatriate — so the outperformer's currency *depreciates*, slowly
because institutional rebalancing is sluggish. The rival hypothesis, declared up front, is
macro momentum (Brooks 2017): equity outperformance signals better growth and attracts
return-chasing inflows, so the currency *appreciates*.

## Setup

* Currencies: G8 (USD + 7 pairs). Signal = log local-currency equity return over k months,
  demeaned across the 8 currencies, sum|w| = 1 (dollar-neutral across G8; the USD leg is implied).
* Local equity, two sources: `px` — local indices `^GSPC ^GDAXI ^FTSE ^N225 ^AXJO ^GSPTSE
  ^SSMI ^NZ50` (no FX inside the signal); `tr` — US-listed country ETFs `SPY EWG EWU EWJ EWA
  EWC EWL ENZL` (total return) divided by the FX rate. `tr` shares the traded FX print with
  the signal, which can manufacture a positive lead-lag; it is re-run with the signal window
  ending 3 or 10 business days before the rebalance (`skip`), and `px` is the clean control.
* Timing: equity closes stamped ≤ D−1 for the weight at `=X` row D. Rebalance on the last row
  of each month (`M`) or ISO week (`W`), weights held until the next rebalance.
* Samples: Fed H.10 noon rates 2000-2026 (monthly/weekly, 1 bp/side) and `=X` 2010-2026
  (daily P&L, 1 bp/side; measured 00:00 UTC half-spreads are ≤ 1 bp, turnover here 4-34/yr,
  so cost drag ≤ 3 bp/yr). Spot only — the sim book accrues no carry.
* IS 2010-2019 / OOS 2020-2026 (fixed in advance, used for every fx-majors idea this session).

## Results

### Pre-registered test (Hau-Rey sign), H.10, monthly (`01_screen.py`)

| Source | k=1 | k=3 | k=6 | k=12 |
|---|---:|---:|---:|---:|
| tr, all 2000-26 | −0.45 | −0.23 | −0.31 | −0.23 |
| px, all 2000-26 | −0.31 | −0.19 | −0.42 | −0.41 |

The primary (tr, k = 3) is −0.23 (−0.23 / −0.41 / +0.15 by sub-period). Rejected.

### Rival sign (equity momentum), selected rows (`02_refine.py`, 90 configurations)

| Data | Source, skip | Signal | Rebal | 2000-09 | 2010-19 | 2020-26 | All |
|---|---|---|---|---:|---:|---:|---:|
| H.10 | px, 0 | combo 1/3/6/12 | M | 0.43 | 0.55 | 0.06 | 0.39 |
| H.10 | px, 0 | k6 | W | 0.40 | 0.39 | 0.37 | 0.38 |
| H.10 | px, 3 | combo | W | 0.40 | 0.54 | 0.07 | 0.38 |
| H.10 | tr, 10 | combo | W | 0.56 | 0.48 | 0.13 | 0.44 |
| H.10 | tr, 0 | k1 | M | 0.47 | 0.36 | 0.41 | 0.41 |

| `=X` 2010-26, 1 bp | Signal | Rebal | Full | IS | OOS | Turnover/yr |
|---|---|---|---:|---:|---:|---:|
| px, skip 0 | combo | W | 0.39 | 0.54 | 0.12 | 18 |
| px, skip 3 | combo | W | 0.50 | 0.69 | 0.16 | 18 |
| px, skip 0 | k12 | W | 0.53 | 0.85 | −0.06 | 9 |
| px, skip 0 | k1 | M | 0.35 | 0.21 | 0.63 | 15 |
| tr, skip 0 | combo | W | 0.37 | 0.48 | 0.18 | 19 |

Book vol is ≈ 3 % at unit gross; CAGR ≈ 1 %; MaxDD ≈ −7 to −10 %.

## Reading

* The rebalancing channel is not visible in G8 spot at monthly horizons: the sign is the
  opposite of Hau-Rey's in 31 of 32 cells. Whatever rebalancing exists is dominated by
  return-chasing/information flow.
* The momentum sign survives the mechanical-bias controls (`px` has no FX in the signal;
  `tr` with a 10-day skip is as good as without), and is positive in 1999-2009, a period no
  choice in this study was fitted to. That makes it a plausible small effect (t ≈ 2 over 27
  years), not an artefact.
* It is too small to trade alone: ≈ 0.4 full-sample, and 2020-2026 is 0.1-0.2 for the
  lookback composite. Individual lookbacks that look better OOS (k1 monthly 0.63) are worse
  elsewhere — picking one would be best-of-N selection over ~100 cells.

## Variants tried

16 (01, H.10) + 16 (01, `=X`) + 50 (02, H.10) + 40 (02, `=X`) = **122 configurations**; the
best full-period cell (0.53) is well inside the best-of-122 null range for a 16-year daily
sample (≈ 0.6). The only claim made is the sign consistency across three sub-periods.

## Files

`code/fx-majors/equity-flow-rebalance/01_screen.py`, `02_refine.py` and their CSVs. New data:
`data/IDX_STOXX50E_d_pre2010.parquet`, `IDX_SSMI_d_pre2010.parquet`, `IDX_NZ50_d_pre2010.parquet`,
`EWL_d*.parquet`, `ENZL_d.parquet`. No alpha spec.
