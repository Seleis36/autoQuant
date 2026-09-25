# Country-pair mean reversion — Failed

**Asset class:** `global-equity-etf` · **Short name:** `country-pairs-reversion` · **Date:** 2026-09-26
**Status:** **Failed.** There is no multi-day mean reversion in country-pair spreads. The
daily gross edge is the one-day non-synchronous reversal already documented in
`nonsync-overreaction`, and costs eat it.

## Idea

EWA/EWC is the textbook cointegrated ETF pair (Chan, *Algorithmic Trading*, 2013): two
commodity economies whose spread mean-reverts. The same logic applies to other economic
twins: EWG/EWU, EWJ/EWY, EWY/FXI, EWZ/EWA, EWZ/EWC, EWA/FXI, and each broad fund against its
largest member (EFA/EWU, EFA/EWG, EEM/FXI, EEM/EWY, EEM/EWZ). With 36 country pairs available,
a diversified pairs book could harvest dispersion without the market beta that dominates this
correlated cross-section.

## Setup (`01_pairs.py`, `02_reframe.py`)

* The hedge ratio h is the rolling 252d return beta of A on B (known at t−1). Spread =
  cumulative log return of `A − h·B`. z = (spread − rolling mean_L) / rolling std_L, trailing.
* Books:
  * linear, `pos = −clip(z, ±2)/2`;
  * band, enter |z| > 2 and exit |z| < 0.5 or after a 20-day stop;
  * slow band, L = 250, exit at the zero cross, 60d stop.
  Each pair's position is scaled by its spread vol, averaged over pairs, and the book is scaled
  to 10 % vol on its trailing realised vol.
* 5 bp/side per leg. 2003-2026 (pre-2003 stale-print years excluded). IS ≤ 2012, OOS 2013+.
* Cointegration variant: each month, keep pairs whose trailing 504d Engle-Granger p < 0.05
  (log prices). Selection at month-end t applies from t+1.

## Results (Sharpe; net is at 5 bp)

| Book | net full | gross full | net IS | net OOS | gross OOS | Turn/yr |
|---|---:|---:|---:|---:|---:|---:|
| ECON L20 linear daily | −0.07 | **0.96** | 0.51 | −0.73 | 0.62 | 284 |
| ECON L20 linear weekly | −0.15 | 0.11 | −0.17 | −0.15 | 0.40 | 118 |
| ECON L60 band daily | 0.11 | 0.44 | 0.22 | 0.01 | 0.38 | 82 |
| ECON L120 band daily | **0.27** | 0.53 | 0.35 | 0.20 | 0.52 | 69 |
| ALL L20 linear daily | 0.04 | 0.69 | 0.63 | −0.64 | 0.21 | 186 |
| ALL L60 band daily | −0.17 | 0.06 | −0.01 | −0.31 | −0.04 | 57 |
| ALL L120 band daily | −0.01 | 0.18 | 0.24 | −0.22 | −0.01 | 47 |
| ECON L250 band-to-zero | 0.07 | 0.18 | 0.20 | −0.10 | 0.05 | 34 |
| ALL L250 band-to-zero | 0.03 | 0.12 | 0.20 | −0.14 | −0.04 | 26 |
| COINT-selected L60 band | 0.01 | 0.09 | −0.23 | 0.16 | 0.23 | 73 |

Other L / freq cells are in `01_pairs.py` output: 18 cells in `01`, 7 in `02`, 25 in total.

**Where the gross edge comes from.** Lagging the ECON L20 daily weights by 1, 2 and 5 days takes
gross Sharpe from 0.96 to 0.43, 0.44 and 0.15. Half the edge sits in the first day, which is the
non-synchronous overreaction. Most pairs mix an Asian ETF with a non-Asian one, or a broad fund
with a member that trades at a different local close. A weekly rebalance, which cannot capture
a one-day effect, has gross Sharpe 0.1-0.4. Genuine multi-week mean reversion (L = 120-250) is
0.1-0.5 gross, and < 0.3 net everywhere.

**Cointegration is fleeting.** On average 2.8 of the 36 pairs pass Engle-Granger at 5 % in any
month (range 0-10). That is roughly the 1.8 expected under the null, so the selected pairs are
mostly false positives, and trading them earns nothing.

## Verdict

**Failed** (best net full-sample Sharpe 0.27, OOS 0.20, among 25 cells). The binding
constraint is that country spreads trend, as `intl-relative-trend` shows, rather than
mean-revert. The one reversal that exists lasts one day and is smaller than a round trip.

## Files

`code/global-equity-etf/country-pairs-reversion/01_pairs.py`, `02_reframe.py`.
