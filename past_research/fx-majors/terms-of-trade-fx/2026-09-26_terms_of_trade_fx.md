# Commodity terms of trade → FX — Failed

**Asset class:** `fx-majors` · **Short name:** `terms-of-trade-fx` · **Date:** 2026-09-26
**Status:** **Failed.** The pre-registered G8 terms-of-trade momentum is ≤ 0.15 net Sharpe
on `=X` and ≤ 0.26 on H.10 2000-2026. Inside the commodity bloc (AUD/CAD/NZD) a ToT
"fair-value gap" is positive in every decade (≈ 0.3-0.6), but most of it is plain 6-month
relative reversal of the three currencies; ToT itself adds a small, uncorrelated increment.

## Idea

Commodity currencies (Chen & Rogoff 2003) move with their export prices; if investors
under-react to slow terms-of-trade (ToT) trends, the currency with improving ToT should
keep appreciating (momentum), or a currency that lagged its ToT should catch up (gap).
Energy importers (JPY, EUR) are the mirror image through oil.

## ToT indices (weights fixed from trade shares before any run, never tuned)

AUD: iron ore .40 (`TIO=F`, from 2010-10; renormalised without it before), gold .15, crude .15
(LNG is oil-indexed), copper .10, wheat .10, cattle .10 · CAD: crude .60, natgas .10, gold .10,
wheat .10, copper .05, cattle .05 · NZD: dairy .60 (`DC=F`), cattle .25, wheat .15 · JPY: crude
−1.0 · EUR: crude −0.5 · USD, GBP, CHF: 0. Coal (`MTF=F`) was excluded because the series stops
in 2025-12 and could not run live. Commodity closes stamped ≤ D−1 for the `=X` row D weight;
front-month `=F` roll gaps add noise to the level changes but these are signals, not traded.

## Results

### 01 — G8 cross-section and pair-vs-USD (`01_screen.py`)

| Signal | `=X` 2010-26 xs (Full / IS / OOS) | `=X` bil | H.10 2000-26 xs (00-09 / 10-19 / 20-26) |
|---|---|---:|---|
| ΔToT 3m | 0.12 / 0.21 / −0.01 | −0.01 | 0.28 / 0.21 / −0.15 |
| ΔToT 6m | 0.15 / 0.11 / 0.24 | 0.06 | 0.10 / −0.05 / 0.07 |
| ΔToT 12m | 0.07 / 0.16 / −0.11 | 0.03 | −0.06 / 0.15 / −0.13 |
| Gap 12m | 0.00 / 0.12 / −0.21 | 0.09 | −0.24 / 0.32 / −0.02 |

### 02 — inside the commodity bloc (`02_bloc.py`; AUD/CAD/NZD demeaned among themselves = cross exposure only)

| Signal (bloc) | Rebal | `=X` Full | IS | OOS | H.10 00-09 | 10-19 | 20-26 |
|---|---|---:|---:|---:|---:|---:|---:|
| ΔToT 3m | M | 0.32 | 0.49 | 0.03 | 0.01 | 0.37 | 0.02 |
| ΔToT 12m | M | 0.28 | 0.24 | 0.35 | 0.36 | 0.22 | 0.44 |
| Gap 6m | M | **0.60** | 0.68 | 0.49 | 0.29 | 0.53 | 0.33 |
| Gap 12m | W | 0.45 | 0.47 | 0.41 | 0.44 | 0.29 | 0.45 |
| Each exporter vs USD, ΔToT sign (TS) | M/W | −0.29 to 0.08 | | | | | |

### 03 — control: is the gap just cross reversal? (`03_gap_control.py`)

| Bloc book, monthly | `=X` Full | IS | OOS | H.10 all 2000-26 |
|---|---:|---:|---:|---:|
| Gap 6m = z(ΔToT) − z(ΔFX) | 0.60 | 0.68 | 0.49 | 0.38 |
| Reversal 6m = −z(ΔFX) | 0.66 | 0.85 | 0.35 | 0.32 |
| ToT 6m = z(ΔToT) | 0.22 | 0.25 | 0.18 | 0.13 |
| Gap 6m, ToT lagged one more month | 0.49 | 0.69 | 0.18 | — |

Daily-return correlations: gap–reversal 0.64, gap–ToT 0.58, reversal–ToT −0.09. The ToT leg
is a genuine but small diversifier of relative reversal among the three commodity
currencies; neither leg alone, nor the gap, clears 0.7 on both samples.

## Why it fails

Commodity prices and commodity currencies co-move almost contemporaneously at daily
frequency; the monthly lead from ToT to FX is ≈ 0.1-0.3 Sharpe, the same order as the
measurement noise of a hand-weighted ToT index built from front-month futures. The bloc
result is mostly the old AUDNZD/AUDCAD range-trading effect, already known to be ≈ 0.3-0.6.

## Variants tried

8 + 7 (01) + 20 + 20 (02) + 24 + 6 (03) = **85 configurations**. The best cell (bloc
reversal 6m, 0.66 on `=X`) is within the best-of-85 null range and is 0.07 on H.10 2000-09.

## Files

`code/fx-majors/terms-of-trade-fx/01_screen.py`, `02_bloc.py`, `03_gap_control.py` (+ CSVs).
New cached data: `data/TIO=F_d.parquet`, `DC=F_d*.parquet`, `LE=F_d*.parquet`, `ZW=F_d_pre2010.parquet`.
No alpha spec.
