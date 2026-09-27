# insider-opportunistic-buys — Form 4 open-market insider trades in S&P 500 names

**Status: Failed.** Pooled event studies show a strong effect: officer/director purchases
earn +36 bp sector-residual over 21 days (t 5.3). That average is mostly clustered filings.
De-duplicated to one event per ticker-week it is **+1 bp**, and every tradeable book is flat
or negative: event books have gross Sharpe ≈ 0, and the best monthly cross-sectional book
reaches 0.39 net full / 0.24 OOS. The Cohen-Malloy-Pomorski "opportunistic" filter leaves
~50 purchases a year in this universe, too few to trade.

Date: 2026-09-27 · Asset class: us-large-cap · IS 2010/11–2017 / OOS 2018–2026-09 · 5 bp per
side · 16 event subsets × 4 horizons + 42 event books + 40 cross-sectional books ≈ 100 variants.

Code: `code/us-large-cap/insider-opportunistic-buys/` (`events.py`, `event_study.py`,
`portfolio.py`, `xs_screen.py`, `figures.py`; CSVs next to them).
New shared data: `code/us-large-cap/shared/fetch_form345.py` → `data/SP500_insider_trades.parquet`
(829 k open-market P/S transactions, 617 tickers, 2006-Q1 → 2026-Q2).

## 1. Idea

Insiders know more than the market. Open-market purchases are voluntary and cash-costly, so
the literature treats them as the informative side (Lakonishok & Lee 2001; Jeng, Metrick &
Zeckhauser 2003). Cohen, Malloy & Pomorski (2012, *Decoding Inside Information*) show that
separating out **routine** traders, those who trade in the same calendar month every year,
leaves **opportunistic** trades with ~80 bp/month of abnormal return. The mechanism is
distinct from everything tried before in this asset class (reversal, earnings, fundamentals).
The data is free and point-in-time (SEC *Insider Transactions Data Sets*, with EDGAR filing
dates).

## 2. Data and timing

* Quarterly SEC zips 2006-Q1…2026-Q2; SUBMISSION ⨝ NONDERIV_TRANS ⨝ REPORTINGOWNER, codes P
  (open-market purchase) and S (open-market sale) only, forms 4 and 4/A. Issuer CIKs are the
  same map as `fetch_xbrl.py`, including holdco predecessors.
* An event is one (ticker, owner, filing date, code). **Entry = close of the first trading day
  after the filing date.** The dataset has no acceptance time and EDGAR accepts until 22:00
  ET. Filings more than 60 days after the trade are dropped.
* Routine/opportunistic per CMP: an insider needs trades in each of the three prior calendar
  years. They are *routine* if one calendar month hosts a trade in all three years,
  *opportunistic* otherwise; anyone with a shorter history is *unclassified*.
* Purchases by officers and directors: 1,000–2,500 transactions/yr in 200–290 names. Sales run
  ~20–40 k/yr.

## 3. Results

### 3.1 Pooled event study (`event_study.py`, sector-residual simple returns, bp)

| subset | N/yr | +5 | +21 | +63 | +126 | +63 IS / OOS |
|---|---|---|---|---|---|---|
| purchases, all (ex 10 %-owner-only) | 679 | +28 (t 7.5) | +36 (t 5.3) | +49 (t 4.3) | +63 | **+115 / −41** |
| purchases, opportunistic | 53 | +17 | +69 (t 2.8) | +114 (t 2.6) | +138 | +171 / +69 |
| purchases, routine | 103 | +6 | −32 | −141 | −210 | +20 / −308 |
| purchases, officer | 282 | +37 | +64 | +97 | +109 | +163 / +8 |
| purchases, CEO/CFO | 118 | +5 | −1 | +14 | +21 | |
| purchases, cluster ≥3 insiders/30d | 247 | +50 | +84 | +139 | +191 | +233 / 0 |
| purchases ≥ $1 M | 75 | +30 | −1 | 0 | +42 | |
| sales, all | 8,070 | −3 | −7 (t −3.9) | −3 | +3 | −23 / +24 |
| sales, unclassified | 4,995 | −7 | −19 (t −8.9) | −24 | −10 | −38 / −1 |
| sales, routine | 1,604 | +8 | +24 | +58 | +53 | |

The t-stats assume independent events, and the events are not independent. **2010 alone has
3,024 purchase events at +159 bp** (21 d): ED's 468 filings, then bank insiders at HBAN, ZION
and others buying after the TARP recapitalisations. Other years run 300–700 events with
means of ±30 bp and no sign consistency (`figures/01_purchase_event_by_year.png`). Keeping one
event per ticker-week (6,026 events): **+3 / +1 / −5 bp** at 5/21/63 days. Averaging per
entry day (portfolio weighting): +2 / −8 / −3 bp.

### 3.2 Event books (`portfolio.py`)

Long every member with a qualifying event in the last H ∈ {21, 63, 126} bars, equal weight,
each long hedged with its sector's EW member basket (or the EW market). 7 subsets × 3 H ×
2 hedges = 42 books. **No purchase book has a positive IS Sharpe.** Best full-sample:
opportunistic purchases H 126, market-hedged: 0.11 (IS −0.08 / OOS 0.22, gross 0.23, 19
names). Short leg on non-routine sellers of > 20 % of holdings, H 126: 0.24 (0.23 / 0.25) at
0.7 % vol.

### 3.3 Cross-sectional monthly signals (`xs_screen.py`)

This treats insider activity as a slow characteristic. Measures: Lakonishok-Lee net purchase
ratio (126/252 d), net $ selling / market cap, and number of sell events, each with and
without routine traders. They go through the sector-neutral monthly quintile/linear books of
`quality-value-composite`, with and without a beta hedge (40 books).

| signal | book | full | IS | OOS |
|---|---|---|---|---|
| selling intensity, non-routine, 126 d | quintile | **0.39** | 0.72 | 0.24 |
| selling intensity, non-routine, 252 d | quintile | 0.37 | 0.58 | 0.28 |
| net purchase ratio, non-routine, 126 d | linear | 0.27 | 0.28 | 0.28 |
| selling intensity, all, 252 d | linear | −0.32 | 0.59 | **−0.90** |

All of them decay out of sample, and linear weighting of selling intensity collapses OOS:
the names with the heaviest insider selling since 2018 (mega-cap tech founders) kept
winning.

## 4. Why it fails here

1. **Large-cap insiders are not informed traders at the margin.** The CMP/Seyhun effect lives
   in small caps, where insiders' information advantage is large relative to analyst
   coverage. In S&P 500 names, purchases are rare (~2 per name per year) and dominated by
   directors' token buys (median $13–160 k).
2. **The pooled average is a handful of episodes.** The 2010 bank-insider recapitalisation
   buys and March-2020 buys carry the event-study mean. A book that trades each name once is
   flat.
3. Selling is compensation-driven (10b5-1 plans, option exercises). It carries a weak
   negative drift that is too small (≤ 25 bp over months) for a sector-hedged book to clear
   costs out of sample.

## 5. Variants and multiple testing

About 100 configurations. The best OOS Sharpe among books with positive IS is 0.28. Under the
null, expected best-of-100 with these correlated books is of that order, so there is no
evidence of an insider edge in this universe after 2010.

## 6. Not tried

10b5-1 flag (only in filings since April 2023, too short); insider trades in *other* firms
(the dataset is issuer-filtered); combining insider buys with the 52-week-low anchor
(George-Hwang), since the "purchase after −5 % 21 d residual" subset was +82 bp at 126 d but
IS-negative at 63 d.
