# Policy-rate momentum on the G8 currencies — Failed

**Asset class:** `fx-majors` · **Short name:** `policy-rate-momentum` · **Date:** 2026-09-26
**Status:** **Failed** — no variant clears net Sharpe 0.35 on any sub-period; the pre-registered
primary (12-month change, linear cross-section) is −0.10 on 2010-2026 and −0.11 on 1999-2026.

## Idea

Dahlquist & Hasseltoft (JFE 2020, "Economic momentum and currency returns") and Brooks
(AQR 2017, "A half century of macro momentum") report that currencies of countries whose
fundamentals have been trending up keep appreciating — Sharpe ≈ 0.7 for the economic-momentum
portfolio, subsuming carry. The cleanest observable of a monetary cycle is the **change in the
policy rate**: announced, never revised, known the day it changes. If policy cycles are
persistent and FX under-reacts, currencies whose central bank has been hiking relative to the
others should keep appreciating over the next month.

## Data and conventions

* Prices: yfinance `EURUSD=X GBPUSD=X USDJPY=X AUDUSD=X USDCAD=X USDCHF=X NZDUSD=X`, 2010-01 →
  2026-09-25, traded in **ticker space** (USDJPY/USDCAD/USDCHF with flipped sign), exactly as
  `SimPortfolioBroker` marks them. Long history: Federal Reserve H.10 noon-NY rates (FRED
  `DEXUSEU DEXUSUK DEXJPUS DEXUSAL DEXCAUS DEXSZUS DEXUSNZ`), 1999-01 → 2026-09, month-end.
* Policy rates: BIS `WS_CBPOL` daily (new cache `data/BIS_CBPOL_d.parquet`); euro leg = ECB
  refi rate to 2008, deposit rate from 2009 (full allotment put €STR/EONIA on the floor).
  Lagged one calendar day before use, sampled at the last `=X` row of each month.
* 10-year yields: OECD monthly averages (FRED `IRLTLT01..M156N`, euro = Germany), usable only
  at the end of the month *after* the observation month.
* Book: signal for the 8 currencies (USD + 7), demeaned cross-sectionally (`lin`), rank
  (`rank`), or each pair against USD on its own (`bilat`); sum|w| = 1, held one month, scaled
  to 5 % ex-ante vol with the unit book's trailing EWMA vol sampled at the rebalance.
* P&L is **spot only** (the sim book accrues no carry). Carry-inclusive Sharpe is reported
  alongside so the reader can see what a forward book would have earned.
* Cost 1 bp per side (monthly books; measured half-spreads at 00:00 UTC are 0.2-1 bp, see
  `cost_table()` — drag is 1-7 bp a year here, irrelevant to the verdict).
* Split fixed before any result: IS 2010-2019, OOS 2020-2026.

## Results

### 2010-2026 on `=X` (daily P&L, `01_screen.py`)

| Variant | Net Sharpe | IS | OOS | Sharpe incl. carry | Turnover/yr |
|---|---:|---:|---:|---:|---:|
| Δ3m, linear | −0.40 | −0.29 | −0.59 | −0.36 | 6.8 |
| Δ6m, linear | −0.19 | −0.13 | −0.28 | −0.15 | 4.9 |
| **Δ12m, linear (primary)** | **−0.10** | −0.11 | −0.09 | −0.04 | 3.7 |
| Δ12m, rank | −0.08 | −0.08 | −0.08 | −0.01 | 4.1 |
| Δ12m, bilateral | 0.06 | 0.16 | −0.08 | 0.12 | 2.0 |
| Δ24m, bilateral | 0.19 | 0.11 | 0.33 | 0.27 | 1.5 |
| Carry level (reference), linear | −0.03 | −0.12 | 0.09 | 0.33 | 1.1 |

(14 configurations; full table in `code/fx-majors/policy-rate-momentum/01_screen.csv`.)

### 1999-2026 on H.10 noon rates (monthly P&L, `02_extend.py`, `03_dispersion.py`)

| Variant | 1999-2009 | 2010-2019 | 2020-2026 | All |
|---|---:|---:|---:|---:|
| Δ12m policy, linear | −0.14 | −0.07 | −0.11 | −0.11 |
| Δ24m policy, bilateral | 0.34 | −0.05 | 0.29 | 0.20 |
| Δ3m policy, linear | 0.02 | −0.35 | −0.48 | −0.20 |
| Δ12m 10y yield, bilateral | 0.03 | 0.19 | 0.41 | 0.17 |
| Δ3m 10y yield, bilateral | 0.45 | 0.10 | −0.55 | 0.12 |
| Cycle age (Δ12m − Δ3m), linear | −0.14 | 0.02 | −0.02 | −0.06 |
| Carry level, bilateral | 0.21 | −0.05 | 0.17 | 0.11 |
| Curve slope (10y − policy), linear | −0.09 | −0.11 | 0.01 | −0.08 |
| Δ12m policy, gated on high cycle dispersion | −0.50 | 0.31 | −0.35 | −0.31 |

(48 + 6 configurations; `02_extend.csv`, `03_dispersion.csv`.)

## Why it fails

* Rate changes are **priced before they happen**. By the time a central bank has moved, the
  2-year yield and the currency moved months earlier; the realised policy path carries no
  information the spot rate has not absorbed. The only consistently signed number is the
  *negative* 3-month change after 2010 (−0.35 / −0.48): fresh hikes are followed by mild
  depreciation ("buy the rumour, sell the fact"). It is 0.02 in 1999-2009, so inverting it
  would be a sign chosen after looking at one regime — not pursued.
* The published economic-momentum Sharpe includes the **forward premium** (carry) and a 1976+
  sample with EM and pre-euro currencies. Spot-only, G8, post-1999, nothing is left: even
  the carry-inclusive version of the primary is −0.04.
* Dispersion gating, which should help if the effect lives in divergent cycles (2022), makes
  it worse outside 2010-2019.

## Variants tried

68 configurations in total (14 + 48 + 6). Best full-period Sharpe: 0.20 (Δ24m bilateral);
with 68 trials the expected best-of-N under the null is ≈ 0.5 on a 27-year monthly sample,
so nothing here is distinguishable from noise.

## Files

* Code: `code/fx-majors/policy-rate-momentum/01_screen.py`, `02_extend.py`, `03_dispersion.py`
  (+ CSVs). Shared: `code/fx-majors/shared/fx_panel.py` (ticker-space backtest, measured cost
  table, monthly hold, lag rule), `macro_data.py` (BIS policy rates, FRED/H.10, OECD yields),
  `fetch_duka_hourly.py` (Dukascopy hourly bid/ask candles → cost model).
* No alpha spec (nothing deployable).
