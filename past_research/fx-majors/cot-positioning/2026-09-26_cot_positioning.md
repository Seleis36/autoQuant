# Contrarian CFTC positioning on the G10 majors — Working (borderline)

**Asset class:** `fx-majors` · **Short name:** `cot-positioning` · **Date:** 2026-09-26
**Status:** **Working** (borderline — OOS Sharpe 0.64 is below 0.8)
**Headline:** net Sharpe **0.80 full / 0.91 IS / 0.64 OOS** at measured costs, t = 3.38,
5 % vol, CAGR 3.9 %, MaxDD −11.4 %, 14 of 17 years positive, deflated-Sharpe p = 0.84 over 75 trials.

## Idea and hypotheses (written before the first run)

The CFTC's weekly Commitments of Traders give, for each CME currency future, the net
position of each trader group. Two published views, declared up front in `01_screen.py`:

* **H1 crowding reversal.** When speculators hold an extreme net long relative to their own
  history, the trade is crowded and unwinds (Tornell & Yuan 2012; sell-side "IMM positioning"
  models). Weight = −z(net share of OI, 3-year window).
* **H2 real-money flow continuation.** TFF asset managers build positions slowly; the
  currency they are accumulating keeps appreciating. Weight = +z(4-week change).
  Controls: H1 on asset managers, H2 on leveraged funds and legacy non-commercials.

## Data

* CFTC legacy futures-only report 1986+ (non-commercials, commercials) and Traders in Financial
  Futures 2006+ (dealers, asset managers, leveraged funds) for EUR, JPY, GBP, AUD, CAD, CHF,
  NZD futures (and the ICE dollar index, unused). New fetcher `code/fx-majors/shared/fetch_cot_fx.py`,
  caches `data/CFTC_COT_legacy_fx_w.parquet`, `data/CFTC_COT_tff_fx_w.parquet`.
* **Release timing** — the one place lookahead can hide. Positions are as of Tuesday and
  published Friday 15:30 ET; in weeks with a US federal holiday on Tuesday-Friday the release
  moves to the following Monday (CFTC schedule, e.g. 2026: Jan 5, Jul 6, Nov 16, Nov 30,
  Dec 28); the 2013, 2018-19 and 2025 shutdowns released backlogs weeks late. Each report
  gets `avail_utc` = Saturday 21:00 UTC (normal) or Tuesday 21:00 UTC (holiday week), clipped
  to the backlog release date. An `=X` row takes the **latest report by as-of date released
  strictly before its 00:00 UTC stamp**. A first version pivoted on the release stamp and
  averaged backlog reports that share one stamp; fixing it (and adding the holiday rule)
  moved the composite from 0.77 to 0.80 — the fix is in every number below.
* Prices: `=X` 2010-2026 traded in ticker space; Fed H.10 noon rates for an independent
  replication. **Stamp check:** `=X` row D equals the Dukascopy mid at 00:00 UTC on D (median
  level gap 1.1 bp, return correlation 0.99 across all Januaries 2010-2026).
* **Costs:** per ticker and year, the median half-spread standing at the 00:00 UTC print,
  measured on Dukascopy hourly bid/ask candles (new `fetch_duka_hourly.py`,
  `fx_panel.freeze_cost_table`, built from every January and July 2010-2026 for all seven
  pairs — the full crawl is throttled to days of wall clock): EURUSD 0.11-0.42 bp, USDJPY
  0.13-0.76, GBPUSD 0.30-0.79, AUDUSD 0.45-1.03, USDCAD 0.42-1.31, USDCHF 0.52-1.30, NZDUSD
  0.73-2.02 (the high ends are 2010-2011). The 21:00-22:00 UTC rollover is 2-3× wider — the
  00:00 UTC fill avoids it. Screens run before the table was frozen used the January months
  only; re-running on the frozen table moves any Sharpe by ≤ 0.01.

## Results

### 01 — screen (weekly, Monday-row rebalance, measured costs, `=X` 2010-2026)

| Signal | Book | Full | IS | OOS | t |
|---|---|---:|---:|---:|---:|
| H1 non-comm level (−z) | xs | 0.51 | 0.48 | 0.58 | 2.40 |
| H1 lev-funds level (−z) | xs | 0.35 | 0.51 | 0.01 | 1.60 |
| H1c asset-mgr level (−z) | xs | 0.62 | 0.32 | 1.18 | 2.76 |
| H2 asset-mgr 4w change (+z) | xs | **−0.53** | −0.58 | −0.45 | −2.18 |
| H2c lev-funds 4w change (+z) | xs | −0.53 | −0.56 | −0.49 | −2.30 |
| H2c non-comm 4w change (+z) | xs | −0.68 | −0.80 | −0.44 | −2.80 |
| Dealer level (+z) | xs | 0.56 | 0.49 | 0.73 | 2.60 |

`xs` = demeaned across the 7 currencies (USD-neutral); `bil` = each pair vs USD on its own
signal (all weaker, 0.2-0.4; table in `01_screen_fx.csv`). H1 holds for every group; **H2 is
rejected with the opposite sign for every group** — fresh positioning in *any* group is
followed by reversal. Dealers, the other side of those trades, look like the mirror image.
On H.10 2000-2026 the legacy change signal faded (−z) is 0.44 / 0.76 / 0.40 by decade.

### 02 — controls on the two legacy legs (`CP` = mean of −z level and −z 4w change)

| Test | Full | IS | OOS |
|---|---:|---:|---:|
| CP | 0.69 | 0.78 | 0.53 |
| Price reversal, same 4-week window and z (H.10 prices) | 0.33 | 0.20 | 0.60 |
| CP residualised on price reversal (weekly XS regression) | 0.35 | 0.57 | −0.02 |
| CP, report used 1 week late / 2 weeks late | 0.40 / 0.20 | | |
| Level leg, 1 week / 2 weeks late | 0.29 / 0.30 | | |
| z-window 52 / 104 / 260 | 0.65 / 0.62 / 0.65 | | |
| change horizon 2 / 8 / 13 weeks | 0.64 / 0.50 / 0.49 | | |
| 2 / 4 overlapping weekly tranches | 0.63 / 0.37 | | |

Reading: part of the edge is short-term price reversal seen through positioning (speculators
chase 4-week moves); positioning adds information on top of price over 2010-2019 but not
detectably after 2020. The change leg decays within two weeks (a flow/price-pressure effect);
the level leg is slower (still 0.30 two weeks late).

### 03 — pre-registered composites (four books, only these four were run)

| Book | Full | IS | OOS | t | Turnover | Cost bp/yr | Gross SR | ×3 cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A legacy nc (2 legs) | 0.71 | 0.80 | 0.60 | 3.05 | 36.7 | 21 | 0.76 | 0.63 |
| B TFF lev + am (4 legs) | 0.71 | 0.71 | 0.71 | 3.06 | 35.0 | 20 | 0.75 | 0.63 |
| **C all 6 legs** | **0.80** | **0.91** | **0.64** | 3.38 | 34.8 | 20 | 0.84 | 0.72 |
| D = C with inverse-vol currency weights | 0.76 | 0.87 | 0.59 | 3.31 | 35.6 | 20 | 0.80 | 0.68 |

C is the deployed book (chosen as the broadest composite, not the best OOS — B is better
OOS, 0.71). All four are scaled to 5 % ex-ante vol.

### 04 — robustness of C

* Neighbourhood z-window {52, 104, 156, 260} × change horizon {2, 4, 8}: full 0.68-0.80,
  OOS 0.60-0.86, t 2.8-3.4 — the chosen cell is the best full-sample one, but no cell is weak.
* Leave one leg out: 0.65-0.88 full (dropping asset-manager level hurts most, 0.65).
* Leave one currency out: 0.52 (no CHF) to 0.86 (no EUR); CHF and NZD carry the most.
* Rebalance on the Tuesday row instead of Monday: 0.84 / 0.99 / 0.61.
* H.10 noon-rate replication (independent prices, weekly, 1 bp): 2007-09 **−0.31**,
  2010-19 0.91, 2020-26 0.53, all 0.48. The GFC years lost money — the one sub-period that
  contradicts the result, and a reason to size this modestly.
* Gross exposure mean 1.49, max 2.42 (the 3.0 cap never binds); book exactly USD-neutral.

### 05 — final (the deployable `strategy.target_weights`)

* Reproduces book C to 3e-15; **truncation test** (prices and COT cut at T, 40 random T):
  weights identical to the full run.
* Net Sharpe 0.80 / 0.91 / 0.64; CAGR 3.9 %, vol 5.0 %, MaxDD −11.4 %, Calmar 0.34; cost drag 20 bp/yr.
* Cost ladder full/OOS: 0 bp 0.84/0.68 · measured 0.80/0.64 · ×2 0.76/0.60 · ×3 0.72/0.55 ·
  flat 1 bp 0.77/0.60 · flat 2 bp 0.70/0.51.
* Per-year Sharpe: 2010 0.34, 2011 3.11, 2012 1.09, 2013 −1.16, 2014 1.88, 2015 1.10,
  2016 −0.42, 2017 1.31, 2018 2.17, 2019 0.34, 2020 0.32, 2021 0.32, 2022 −0.29, 2023 0.71,
  2024 1.86, 2025 0.51, 2026 (to Sep) 1.36.
* OOS block bootstrap: mean 0.63, 5-95 % [0.05, 1.23], P(>0) = 0.97.
* Carry a forward book would add: +3 bp/yr (Sharpe incl. carry 0.81) — the book is
  effectively carry-neutral, so the sim book's missing carry accrual does not bias it.
* Deflated-Sharpe probability with 75 trials: 0.84.

Figures: `alphas/fx-majors/cot-positioning/equity_drawdown.png`, `weights_recent.png`.

## Why it might work

Positioning in listed FX futures is a visible proxy for fast-money flows. Fresh flows push
prices beyond fair value and revert (price-pressure / liquidity-provision), and extreme
aggregate positioning leaves the marginal buyer exhausted. Dealers, who warehouse the other
side, are the natural liquidity providers and their positioning predicts the same way. The
effect is modest (≈ 4 %/yr at 5 % vol) and long-lived in this sample, but it is partly
the same thing as short-term price reversal.

## Variants tried

20 (01) + 24 (02) + 4 (03) + 25 (04) + 2 (Tuesday row, H.10) = **75 configurations**; the
deflated-Sharpe probability accounts for all of them.

## Files

* Code: `code/fx-majors/cot-positioning/01_screen.py`, `02_refine.py`, `03_composite.py`,
  `04_robust.py`, `05_final.py`, `strategy.py`; CSV/parquet outputs next to them.
* Shared: `code/fx-majors/shared/fetch_cot_fx.py` (CFTC legacy + TFF, release-time-aware
  availability, weekly `refresh_current_year()`), `fx_panel.py`, `fetch_duka_hourly.py`.
* Spec: `alphas/fx-majors/cot-positioning/spec.md`.
