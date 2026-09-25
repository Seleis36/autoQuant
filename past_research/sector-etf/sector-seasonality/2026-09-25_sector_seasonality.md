# sector-seasonality — same-calendar-month return seasonality across sectors

**Status: Failed.** Asset class `sector-etf`. Date 2026-09-25.

## Idea
Heston & Sadka (2008) and Keloharju, Linnainmaa & Nyberg (2016, JF) show that an asset's
average return in the *same calendar month* over the past 20 years predicts its return
this month, in stocks, industries, countries and commodities (17-industry 2-vs-2 book:
+0.70 %/month gross, 1963-2011). With 27 years of ETF history a same-month mean rests on
~25 observations, so the signal is estimated instead on **Ken French's 49 value-weighted
industry portfolios (1926-07 → 2026-07), mapped to GICS sectors** (`code/sector-etf/shared/french.py`;
monthly correlation with the ETFs 0.93-0.99 for the original nine, 0.83 XLC, 0.68 XLRE).
The signal is only ever read from months ≥ 11 months old, so the ~2-month publication lag
of the French file never binds.

Also tested, as a literature-fixed special case: the **Halloween sector rotation** of
Jacobsen & Visaltanachoti (2009) — cyclicals {XLY XLI XLB XLK XLF} over defensives
{XLP XLU XLV} from November to April, the reverse May-October.

## Setup
Common sector-etf setup (see `sector-short-reversal` report): IS 1999-2014 / OOS 2015-2026,
2 bp/side, weights at close *t* earn *t+1*. Monthly rebalance on the last trading day of the
month; SPY hedge to zero beta (EWM-126 beta) unless stated.

Grid: look-back L ∈ {10, 20, 30, 50} years × signal {raw same-month mean, same-month mean
minus all-month mean} × construction {top/bottom 2, top/bottom 3, linear} = 24 cells.

## Results
### Part A — on the French sector proxies themselves (gross, dollar-neutral, `seasonal_grid.py`)
| Period | Sharpe range over 24 cells | median |
|---|---|---|
| 1946-1998 (holdout before any SPDR existed) | 0.44 – 0.85 | ≈0.75 |
| 1999-2014 | −0.45 – 0.40 | ≈0.12 |
| 2015-2026 | −0.16 – 0.25 | ≈0.05 |

The effect is real and strong **before** its publication and decays to nothing after —
the textbook post-publication pattern (McLean & Pontiff 2016).

### Part B — traded on the ETFs (SPY-hedged, 2 bp, `etf_book.py`)
All 24 cells negative in full sample: best IS −0.02 (`L30|ex|lin`), OOS −0.28…+0.05.
`debug_proxy_vs_etf.py` reconciles Part A with Part B (same signal, L30-ex, 2-vs-2,
dollar-neutral): proxy 11 names 0.39 IS → proxy restricted to names the ETFs actually
offered 0.25 → ETF returns 0.15 → plus the beta hedge and costs ≈ −0.06. The 1999-2014
proxy edge came partly from the pre-listing XLRE/XLC proxies, which were not tradeable.

### Halloween rotation (`halloween.py`, 4 cells)
Proxies: two-sided Sharpe 0.53 (1946-98), 0.42 (1999-2014), **−0.16 (2015-26)** — since
2015 cyclicals have beaten defensives by *more* in summer (+0.61 %/mo) than in winter
(+0.29 %/mo). ETFs: two-sided dollar-neutral 0.13 full / −0.08 OOS; winter-only 0.21 / 0.19;
beta-neutral versions ≈0.

## Verdict
52 configurations; none positive OOS by more than noise. **Binding constraint: decay** — the
seasonal effect lived in 1946-1998 and is gone from the sector cross-section since the ETFs
exist. The small universe (9-11 names) makes it worse: a 2-vs-2 book on 11 names carries
mostly idiosyncratic sector noise.

## Files
`code/sector-etf/sector-seasonality/`: `seasonal_grid.py` (+`partA_proxy.csv`), `etf_book.py`
(+`partB_etf.csv`), `halloween.py`, `debug_proxy_vs_etf.py`; shared loader
`code/sector-etf/shared/french.py` (caches `data/FF49_industries_vw_m.parquet`,
`data/FF49_industries_cap_m.parquet`).
