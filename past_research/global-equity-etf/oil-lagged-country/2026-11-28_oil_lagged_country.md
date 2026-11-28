# oil-lagged-country — lagged oil-price changes as a country-equity timer (Driesprong-Jacobsen-Maat)

**Asset class:** `global-equity-etf` · **Short name:** `oil-lagged-country` · **Date:** 2026-11-28
**Status:** **Failed.** In the ETF era (2001-2026) last month's oil change predicts nothing: every
country, the basket, SPY, EFA and EEM have |t| < 1.3, and most slopes have the *wrong* (positive) sign.
The effect exists in the 1988-2000 backcast (US −0.072, t −2.1, matching the paper) and is gone
after publication. Re-framings (5-21 session horizons, Kilian-Park supply-shock residual,
oil-beta cross-section) are all |t| < 2.4 with unstable signs, and the books are below 0.

## Idea

Driesprong, Jacobsen & Maat (JFE 2008): oil price changes in month m predict lower stock returns
in month m+1 in 12 of 18 developed markets and the world index (1973-2003). They read this as
investors under-reacting to oil news. In this asset class it can be applied two ways: as a timer of the
country basket, or as a cross-section (oil exporters EWC/EWZ/EWA/EWU vs importers EWJ/EWY/INDA/FXI/EWG),
where the delayed reaction should scale with each country's oil exposure. The paper's sample ends
in 2003, so the whole ETF era is post-publication.

## Data

EIA Cushing WTI spot (RWTC), daily 1986-2026, cached at `data/EIA_WTI_d.parquet` (FRED's
`DCOILWTICO` mirror timed out repeatedly this session; EIA's xls was converted in a throwaway
venv). The monthly log changes correlate 0.996 with CL=F. Equity: ETF total returns 2001-2026, IS ≤ 2012 /
OOS 2013+. Backcast: local price indices × FRED H.10 month-end FX, plus the S&P 500, 1988-2000.

## Results

**1. Time series** (`01_oil_study.py`): slope of next-month return on this month's log oil change (t):

| | 2001-26 | IS 2001-12 | OOS 2013-26 | backcast 1988-2000 |
|---|---|---|---|---|
| SPY / US | −0.007 (−0.30) | +0.018 (0.43) | −0.017 (−0.65) | **−0.072 (−2.09)** |
| country basket | +0.013 (0.46) | +0.025 (0.42) | +0.007 (0.23) | −0.012 (−0.29) |
| WORLD (½ SPY + ½ basket) | +0.003 (0.13) | +0.021 (0.44) | −0.005 (−0.20) | −0.042 (−1.19) |
| EEM | +0.037 (1.17) | +0.073 (1.03) | +0.020 (0.65) | |
| 9 countries | −0.018 … +0.072, all \|t\| < 1.3 | | | UK −0.063 (−1.5) |

The contemporaneous slope (WORLD on same-month oil) is **+0.153 (t 6.8)**. Since 2001 oil has traded
as a risk-on asset, so an oil rise is no longer bad news that equities absorb slowly. The
two-month-ahead placebo is also 0.

**2. Cross-section:** country 60-month oil beta × this month's oil change → next month's demeaned
return. Rank IC −0.002 (t −0.07) full, +0.033 IS, −0.029 OOS.

**3. Re-framings** (`02_reframe.py`):
* Horizons of 5 / 10 / 21 sessions, non-overlapping, with a 1-session skip: all |t| ≤ 1.5 except the
  10-session OOS on the basket (+0.034, t 2.3, the *wrong* sign and negative in IS).
* Kilian-Park supply shock (oil change net of its rolling beta to world equities over the same
  window): 21-session slopes +0.03 (t ≈ 1.1), wrong sign; XS IC 0.015 (t 0.6).
* Books (WORLD long/short = −clip(z_resid)/2, 5 bp countries / 1 bp SPY): weekly −0.12 / −0.23 / −0.01,
  monthly −0.10 / 0.01 / −0.22 (full / IS / OOS).

## Why it fails

The effect required oil rises to be bad news (an input-cost shock) that markets priced slowly.
After 2001 the dominant oil shocks were demand-driven (China, 2008, 2020) and moved together
with equities. The under-reaction itself, if it ever was one, was arbitraged after the 2008
publication. The 1988-2000 US slope of −0.07 is the last trace.

## Variants

14 outcomes × 4 periods (TS), 1 XS, 3 horizons × 2 signals × 3 outcomes × 3 periods, 1 residual XS,
2 books: ≈ 75 regressions, 3 tradeable configurations. Nothing was close enough to warrant more.

Code: `code/global-equity-etf/oil-lagged-country/` (`ol_lib.py`, `01_oil_study.py`, `02_reframe.py`).
