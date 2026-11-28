# country-iv-premium — option-implied fear premia of country ETFs vs SPY

**Asset class:** `global-equity-etf` · **Short name:** `country-iv-premium` · **Date:** 2026-11-28
**Status:** **Failed.** No implied-vol signal keeps its sign across the pre-registered halves
(IS 2011-03 → 2018, OOS 2019 → 2026). The best books (long high abnormal country fear vs SPY)
are 0.0 IS / 0.8 OOS, with the 63-session predictive slope flipping from +126 bp (t 2.2) to −180 bp (t −2.7).
The global-VRP timer of the basket replicates in 2011-18 (t 2.6) and dies after (t 0.2).

## Idea

Bollerslev, Marrone, Xu & Zhou (2014): variance risk premia predict international equity
returns, the global VRP best of all. The cross-sectional version is untested: a country whose implied vol
is high relative to its realized vol (VRP), or relative to the VIX (abnormal country fear),
should earn a premium over SPY if fear is compensated. It should under-perform if option
markets lead bad news. The signal uses a data source no earlier idea here has used.

## Data

CBOE ETF volatility indices VXEFA (2008+), VXEEM, VXEWZ, VXFXI (2011-03+; VXFXI missing 2022-03 →
2025), from `cdn.cboe.com/api/global/us_indices/daily_prices/<X>_History.csv` (yfinance has one row
only). Also NSE India VIX for INDA and S&P/ASX 200 VIX for EWA (yfinance), and VIX for SPY. Cached as
`data/CBOE_VX{EFA,EEM,EWZ,FXI}_d.parquet`, `data/IDX_INDIAVIX_d.parquet`, `data/IDX_AXVI_d.parquet`.
CBOE indices settle at 16:15 ET, after the ETF close, so **every IV is lagged one session**. The
target is each ETF's SPY-hedged spread (252d beta). The split was fixed before any result.

## Results (`01_ic_study.py`, `02_books.py`)

Pooled time-series slope of the hedged spread on the name's own z-scored signal:

| signal | 5d IS | 5d OOS | 21d IS | 21d OOS |
|---|---|---|---|---|
| VRP = IV − RV21 | −9.4 bp (−1.9) | +11.3 (2.5) | −15.1 (−0.7) | +42.9 (2.4) |
| log(IV/RV21) | −7.7 (−1.6) | +7.1 (1.5) | −20.8 (−1.0) | +55.3 (2.7) |
| RELIV = log(IV/VIX) − 252d mean | −8.4 (−1.9) | +1.6 (0.3) | +20.9 (1.2) | +14.4 (0.7) |
| 5d change of log(IV/VIX) | −9.9 (−2.0) | +7.2 (1.3) | +9.5 (0.5) | −2.3 (−0.1) |

* Cross-sectional rank IC: all |IC| ≤ 0.05 except the 21d fear shock, +0.087 IS (t 1.8) → −0.100 OOS (t −2.2).
* RELIV at 63 sessions: +126 bp (t 2.16) IS → **−180 bp (t −2.72)** OOS.
* Extreme fear events (RELIV z > 1.5) earn −88 / −91 bp over the next 21 sessions (IS / OOS), the same as the
  average hedged spread (−95 / −65) and as z < −1.5 (−109 / −90). Extreme fear carries no information.
* Global VRP (average across the 7 names) → next 21 sessions of the basket: +135 bp/z (t 2.55) IS,
  +9 bp (t 0.21) OOS. This is the same predictor flip `vol-complex/vol-regime-equity-timing` found for SPY.

Books (month-end, hedged spreads, 10 % vol target, 5 bp ETF / 1 bp SPY), net Sharpe full / IS / OOS:

| book | full | IS | OOS |
|---|---|---|---|
| XS long top-2 / short bottom-2 RELIV | 0.42 | 0.01 | 0.80 |
| XS rank-linear RELIV | 0.36 | −0.11 | 0.78 |
| TS sign(RELIV z), equal risk | 0.27 | −0.06 | 0.56 |
| TS clip(z)/2, equal risk | 0.27 | −0.02 | 0.52 |

The OOS 0.5-0.8 has no in-sample support, and the 63-session slope runs the other way, so it is not
evidence.

## Why it fails

Six ETFs and fifteen years are too little cross-section and history to estimate a premium whose
sign depends on the regime: implied vol premia were compensation in 2011-18 (the EM taper and commodity bust)
and a lead on bad news after 2019, or vice versa depending on horizon. EEM overlaps FXI, INDA and EWZ, so the
effective cross-section is smaller still.

## Variants

5 signals × 2 horizons × 3 periods × 2 forms (IC, TS) = 60 tests, plus the global-VRP timer (12) and the
RELIV re-framings (63-session, events) and 4 books. Approximately 80 cells.

Code: `code/global-equity-etf/country-iv-premium/` (`iv_lib.py`, `01_ic_study.py`, `02_books.py`).
