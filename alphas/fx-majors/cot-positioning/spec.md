# Alpha spec — `fx-majors/cot-positioning`

**Status:** Working (borderline: OOS Sharpe 0.64 < 0.8) · **Date:** 2026-09-26
**Report:** `past_research/fx-majors/cot-positioning/2026-09-26_cot_positioning.md`
**Signal code:** `code/fx-majors/cot-positioning/strategy.py :: target_weights(px, cot_legacy, cot_tff)`
(all parameters defaulted to the values below; `load_inputs(refresh=True)` returns the three inputs)

## What it trades

| Item | Value |
|---|---|
| Instruments | `EURUSD=X GBPUSD=X USDJPY=X AUDUSD=X USDCAD=X USDCHF=X NZDUSD=X` (yfinance, shared daily cache) |
| Direction | long/short, cross-sectional; the book is exactly USD-neutral in currency space (currency weights sum to 0 every row) |
| Rebalance | weekly, on the first `=X` row of each ISO week (normally the row stamped Monday); weights constant otherwise |
| Sizing | demeaned composite signal, sum\|w\| = 1, × vol-target scalar k = min(3, 5 % / EWMA-126d vol of the unit book), k re-set only at the weekly rebalance |
| Gross exposure | mean 1.49, max 2.42 (2010-2026); cap 3.0 — set `max_gross = 3.0` |
| Per-ticker max \|w\| | ≈ 1.0 |
| Ticker sign | EURUSD/GBPUSD/AUDUSD/NZDUSD carry the currency weight; USDJPY/USDCAD/USDCHF carry minus it (already applied by the function) |

## Signal

Six contrarian legs on CFTC Commitments of Traders for the CME currency futures (EUR, JPY,
GBP, AUD, CAD, CHF, NZD), each a net long as share of open interest on the weekly as-of-Tuesday grid:
legacy non-commercials, TFF leveraged funds, TFF asset managers; for each, `−z(level)` and
`−z(4-report change)`, z over the trailing 156 reports (min 52). Equal-weight mean.

## Bar / timezone convention

* `=X` row D is the 00:00 UTC quote on D (verified against Dukascopy hourly mid: median level
  gap 1.1 bp, return correlation 0.99). The weight at row D is held from row D's close to
  row D+1's close; the sim book fills at row D's close.
* A COT report is usable on row D only if it was released strictly before 00:00 UTC D:
  normal weeks Friday 15:30 ET (stamped usable Saturday 21:00 UTC), US-holiday weeks the
  following Monday (usable Tuesday 21:00 UTC), shutdown backlogs at their release dates
  (`fetch_cot_fx._avail`). The Monday row therefore always sees the report released the
  previous Friday.
* Live: refresh the CFTC files once a week after the Friday release
  (`fetch_cot_fx.refresh_current_year()`, a few hundred KB) and the `=X` cache daily; compute
  after 00:00 UTC once the new `=X` row is final. The function is truncation-safe (weights at
  T computed on data cut at T equal the full-history weights at T, 40/40 dates).

## Headline numbers (2010-01 → 2026-09, measured costs)

| | Full | IS 2010-19 | OOS 2020-26 |
|---|---:|---:|---:|
| Net Sharpe | **0.80** | 0.91 | **0.64** |
| CAGR | 3.9 % | 4.5 % | 3.0 % |
| Vol | 5.0 % | 5.0 % | 4.9 % |
| Max drawdown | −11.4 % | −11.4 % | −7.9 % |
| t (Newey-West) | 3.38 | 2.85 | 1.83 |

* Turnover 34.8× gross per year; cost drag 20 bp/yr.
* Cost ladder (Sharpe full / OOS): 0 bp 0.84 / 0.68 · measured 0.80 / 0.64 · measured ×2 0.76 / 0.60 ·
  measured ×3 0.72 / 0.55 · flat 1 bp 0.77 / 0.60 · flat 2 bp 0.70 / 0.51.
* OOS block bootstrap (21-day blocks, 5,000 draws): mean 0.63, 5-95 % [0.05, 1.23], P(>0) 0.97.
* Deflated-Sharpe probability given 75 configurations tried: 0.84.
* 14 of 17 calendar years positive; worst year 2013 (−5.9 %).

## Cost assumption

Research charges, per ticker and per side, the median half-spread at the 00:00 UTC print
for that pair and year, measured on Dukascopy hourly bid/ask candles (every January and July
2010-2026; 2020-26 averages: EURUSD 0.17 bp, USDJPY 0.20, GBPUSD 0.39, USDCAD 0.50, USDCHF 0.59,
AUDUSD 0.75, NZDUSD 0.94; table `data/fx_halfspread_h23.parquet`, `fx_panel.freeze_cost_table`).
The sim broker takes one number for all legs: **slippage 1 bp, fee 0** is conservative
against the measured schedule (flat 1 bp gives 0.77 / 0.60).

## Caveats the deployer should know

* The sim book accrues no carry, and neither does this backtest. It hardly matters here: on
  policy-rate differentials the book's carry averages +3 bp/yr (Sharpe incl. carry 0.81), so
  the sim book neither flatters nor penalises it relative to a real forward book.
* On Fed H.10 noon rates the same book is −0.31 in 2007-2009 (GFC carry unwind) — the effect
  is a post-crisis regularity in this data, 0.91 (2010-19) and 0.53 (2020-26) there.
* About 40 % of the return is shared with plain 4-week price reversal (ρ = 0.40 on daily net
  returns); positioning residualised on price reversal keeps 0.35 full-sample but ≈ 0 OOS.
