# Calendar / flow ensemble on the G10 dollar basket — Failed

**Asset class:** `fx-majors`
**Short name:** `calendar-flow-ensemble`
**Date:** 2026-09-12
**Status:** **Failed** (target was Sharpe ≥ 2; best honest ensemble nets 0.35)

## Acceptance criteria

- **Criteria:** "2+ sharpe strategy, get creative. You should find a breakthrough strategy" —
  read as net Sharpe ≥ 2.0 out of sample, after realistic costs.
- **Met:** NO.
- **Evidence:** the pre-specified five-sleeve ensemble has net Sharpe **0.35** full-sample
  (2010-01 → 2026-09), **0.32** in-sample (2010-2019) and **0.39** out-of-sample (2020 →
  2026-09) at 2 bp per side; gross (zero-cost) Sharpe 0.69. Block-bootstrap of the OOS
  segment: 5th–95th percentile −0.22 to 1.05, P(Sharpe > 2) = 0.000. No single effect or
  configuration among ~195 tried exceeded net Sharpe 0.7 on the full sample.
- **Variants tried:** ≈195 distinct configurations across seven screening scripts plus the
  ensemble (all listed in `code/fx-majors/calendar-flow-ensemble/screens/` and tabulated
  below). Deflated-Sharpe probability of the ensemble being real given 200 trials: 0.09.

## Universe, data, and the bar convention (important for the next researcher)

Universe: `EURUSD=X GBPUSD=X USDJPY=X AUDUSD=X USDCAD=X USDCHF=X NZDUSD=X` from yfinance,
converted to USD-per-foreign-unit so that a positive weight means long the foreign currency
/ short USD. Cache under `data/<ticker>_d.parquet`, 2010-01-05 → 2026-09-11, 4,340 rows
with a non-zero move. Macro overlays: `SPY EFA EWJ EWG EWU EWA EWC TLT GLD USO HYG ^VIX
^TNX DX-Y.NYB` and the CurrencyShares ETFs `FXE FXB FXY FXA FXC FXF UUP` (used only as an
independent price source for cross-checks). Loader: `code/fx-majors/shared/fx_data.py`.
Scheduled FOMC dates 2010-2027: `code/fx-majors/shared/fomc_dates.py` (from federalreserve.gov).

**Yahoo FX rows are stamped one day late.** Correlating the daily rows with 729 days of
hourly closes (`screens/probe_timing2.py`) shows the row stamped D matches the hourly close
at **00:00 UTC on D** (corr 0.96 for EURUSD, 0.95 for USDJPY at 23:00 UTC D−1). So the
return of row D+1 is UTC calendar day D, the row stamped Monday is Friday's session, and
there is no Saturday row. Consequences:

- Same-day correlation between `EURUSD=X` and `FXE` daily returns is 0.10; FX row D+1 vs
  FXE row D is 0.87. Anything that uses an equity/ETF close stamped D to set a weight at FX
  row D+1 is fine (the US close at 20:00–21:00 UTC precedes 00:00 UTC), but using the ETF
  close stamped D+1 against FX row D+1 is lookahead. Every test here uses macro rows
  stamped ≤ D−1 for the weight set at FX row D.
- A naive "ETF signal → trade FX" test produces Sharpe −22 (pure overlap), which is a
  useful sanity check that the alignment is understood.
- Deployment implication: the live weight for row D can be computed at ~00:00 UTC and
  filled at that row's close, using the previous US close.

Cost assumption: 2 bp per side on |Δw| summed across legs (G10 spot at the NY close; 5 bp
and 10 bp sensitivities reported). Annualisation 252. Split fixed before any result was
seen: IS 2010-2019, OOS 2020 → 2026-09. The split, sample start, universe and cost were
never changed afterwards. No sub-period was dropped.

## Idea

Public, economically motivated, calendar-anchored flows in FX that survive at daily
frequency:

1. **Month-end equity-rebalancing flow** (sell-side "month-end FX models", BNY iFlow):
   after a strong US-equity month, foreign holders rebalance / re-hedge by selling USD
   into the last London fixes of the month. Signal: SPY month-to-date return (through the
   previous US close), scaled by 3 % and clipped to ±1, held over the last 3 sessions.
2. **FOMC announcement day dollar depreciation** (Mueller, Tahbaz-Salehi & Vedolin, JF
   2017): short USD over the session containing a scheduled FOMC statement.
3. **Year-end dollar weakness**: short USD over the last 5 sessions of the calendar year.
4. **Cross mean reversion**: 60-day z-score reversion on nine G10 crosses (AUDNZD, EURCHF,
   EURGBP, AUDCAD, NZDCAD, CADCHF, GBPCHF, EURJPY, AUDJPY), dollar-neutral by construction.
5. **Calendar-month seasonality** of the basket, sign estimated from *past years only*.

Each sleeve is scaled to a 2 % ex-ante vol contribution using an EWMA of its own realised
return, summed, vol-targeted to 4 % and capped at 1.5× gross. Sleeves' net returns are
essentially uncorrelated (|ρ| ≤ 0.15), so the ensemble is close to the best the sleeves
can do together.

## Ensemble result (2 bp/side)

| Sleeve | Net Sharpe | Gross Sharpe | IS | OOS | t (NW) | Turnover/yr | Avg gross expo |
|---|---:|---:|---:|---:|---:|---:|---:|
| month_end | 0.23 | 0.42 | 0.50 | −0.14 | 1.0 | 20 | 0.10 |
| fomc | 0.12 | 0.31 | 0.00 | 0.33 | 0.5 | 15 | 0.03 |
| year_end | 0.69 | 0.75 | 0.71 | 0.66 | 2.4 | 2 | 0.02 |
| cross_rev | 0.19 | 0.56 | 0.08 | 0.37 | 0.9 | 27 | 0.41 |
| season (expanding, honest) | −0.06 | −0.02 | −0.10 | −0.02 | −0.3 | 12 | 0.82 |
| **ENSEMBLE** | **0.35** | **0.69** | **0.32** | **0.39** | 1.4 | 59 | 0.59 |

Full-sample ensemble: CAGR 1.1 %, vol 3.4 %, MaxDD −7.8 %, hit rate 49.6 %, max gross 1.5×.
Cost sensitivity: 0 bp → 0.69, 2 bp → 0.35, 5 bp → −0.17, 10 bp → −1.03.
Per-year Sharpe ranges from −1.2 (2014) to 2.2 (2023); 2024-2026 are all negative.
OOS block bootstrap (21-day blocks, 2,000 draws): mean 0.40, P(>0) 0.86, P(>1) 0.07,
P(>2) 0.000.

Figures: `ensemble_equity.png` (ensemble and sleeves, IS/OOS line, drawdown) and
`sleeves_sharpe.png` (IS/OOS Sharpe per sleeve against the 2.0 target line).
Table: `ensemble_summary.csv`.

Note on the seasonality sleeve: a leave-one-year-out version (which uses *future* years
to set each year's sign) shows Sharpe 0.60 / OOS 0.17 in the screen; the expanding-window
version that a live system could actually run is −0.06. The effect is not real.

## Everything else that was tried (net Sharpe at 2 bp, full sample; IS / OOS in brackets)

All from `screens/screen1.py` … `screen7.py`; CSVs next to them.

**Calendar effects on the equal-weight 7-currency basket**
- Short-USD always: −0.17. Long-USD over each weekday session: Friday session (Monday
  row) is the only positive one, gross 0.48 but net −0.15 (1-day holds cannot pay a
  4 bp round trip). NFP Fridays alone: 0.07. Post-NFP fade: −0.03; follow: −0.74.
- Turn-of-month long/short USD, last/first 1-3 rows: −0.62 to −0.02.
- Month-end rebalancing, 25 variants on the session calendar (SPY MTD sign / scaled,
  SPY−EFA relative, country ETF vs SPY per currency, SPY+TLT blend; hold windows
  {L}, {L−1,L}, {L−2..L}, {L−1}, {L−2,L−1}): best net 0.34 (scaled SPY MTD over
  sessions L−2,L−1: IS 0.65 / OOS −0.05); the fix session itself (L) is −0.3 to −0.5
  for every signal, i.e. the flow is front-run and the fix session reverses.
- FOMC: hold over the announcement session 0.12; the session before −0.17; the session
  after −0.58.
- Quarter-end long/short USD, last 3/5/10 sessions: −0.45 to 0.23. Year-end short USD
  last 5 / 10 sessions: 0.69 / 0.49 (the one effect that holds IS and OOS, but only
  five days a year).
- Tokyo-fix "gotobi" days (5/10/15/20/25/EOM), short JPY: −0.53; basket version −0.64.

**Momentum / reversal**
- Time-series momentum (Baz MACD 8/24 … 64/192, sign of 21/63/126/252-day return),
  vol-scaled basket: −0.40 to −0.11. FX trend is dead in this sample.
- Cross-sectional momentum 1–252 days: all negative (−2.3 at 1 day). The 1-day
  cross-sectional *reversal* is gross 0.48 but net −1.35 at 336 turnover; demeaned
  version −1.32; basket-level 1–10 day reversal −0.59 to 0.00; vol-regime conditional
  versions −0.59 to −0.05. Cross-checked on the CurrencyShares ETFs (ETF-on-ETF −1.34
  net), so it is a cost artefact, not a data artefact.
- Large-move fade/follow (|z| > 1.5/2/2.5): not reached (script stopped earlier), the
  weaker 1-day reversal above already bounds it.
- Cross mean reversion z20 / z60 on nine crosses: single crosses −0.3 to 0.37
  (GBPCHF z60 best, EURGBP z60 0.33 / OOS 0.60); all-cross basket z60 0.18, z20 −0.16.

**Cross-asset lead-lag (macro lagged one stamp, so no overlap)**
- SPY 1/2/5-day return → short USD: −0.76 / −0.55 / −0.51. VIX change → long USD:
  −0.92 / −0.58 / −0.43. DXY continuation: −0.98 / −0.49 / −0.31.
- Risk-off pairs (long JPY+CHF, short AUD+NZD on VIX up or SPY down, 1 and 5 days):
  −1.68 to −0.32.
- Oil → CAD, gold → AUD / CHF, 10-year yield change → long USD / short JPY, at 1/5/21
  days: −0.86 to 0.18.
- After-hours (20:00 → 00:00 UTC, from ETF vs spot) follow / fade: −1.81 / −0.85.

**Carry proxy and learning**
- ETF-implied carry (drift of log(FXE/EURUSD) etc. vs UUP/DXY): rank L/S −1.44, sign
  basket −0.60. Too noisy, and the simulated book does not accrue carry anyway.
- Walk-forward ridge on 7×7 lagged FX returns + 8 macro features (3-year train, 1-year
  test, λ ∈ {10, 100, 1000}; sign, scaled, cross-sectional, EWMA-smoothed 2/5/10):
  −0.45 to 0.02 net; best gross 0.64 at 170 turnover.

## Why the target is not met

- Every effect that exists in this universe is worth 1–5 bp per session on a basket with
  ~40 bp daily vol. A 2 bp per-side cost is comparable to the edge for anything held a
  single day, and the effects that survive costs (year-end, month-end) are active
  5–35 days a year, which caps the annual Sharpe near 0.7 no matter how well they are
  sized.
- The sleeves are uncorrelated but weak; combining five effects of net Sharpe 0.1–0.7
  gives 0.35 net / 0.69 gross, in line with the √N arithmetic. Reaching 2.0 would need
  ~30 independent effects of this size, or an intraday execution (fix-window) that daily
  bars cannot express.
- Nothing predictive comes from equities, rates, VIX, commodities or the dollar index at
  1–21 day horizons once the ETF/FX timing offset is respected. The only large numbers in
  the screens were alignment artefacts.

## What a future researcher could still try

- Real carry (policy or 2-year rates per country, not yfinance-derivable) with vol
  scaling, if the simulated book ever accrues carry.
- The Friday-session dollar strength (gross 0.48) is the one intraday-ish regularity that
  the daily bar captures; it needs ≤ 1 bp cost or a longer hold to be usable.
- Long-horizon value (5-year reversal) as a monthly sleeve; not tested here.

## Files

- Report: this file. Figures and summary CSV alongside.
- Code: `code/fx-majors/calendar-flow-ensemble/01_ensemble.py`, `strategy.py`
  (`target_weights(fx, macro)` → DataFrame of weights per currency, all parameters
  defaulted), `screens/` (every screening script, timing probes and their CSVs).
- Shared helpers: `code/fx-majors/shared/fx_data.py`, `code/fx-majors/shared/fomc_dates.py`.
- No alpha spec was written because nothing is deployable.
