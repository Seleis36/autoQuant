# earnings-event-drift — announcement premium, PEAD and the earnings cycle in S&P 500 names

**Status: Failed** vs acceptance criterion "1.5+ Sharpe". The only real effect is a ~9 bp
sector-residual run-up in the 5 bars before the print (t = 5.0, IS +7 / OOS +10 bp). A
sector-hedged long book of it has gross Sharpe **0.83** and is **negative net at 5 bp** (0.18 at
2 bp). No post-earnings drift exists in this universe after 2010.

Date: 2026-09-16 · Asset class: us-large-cap · IS 2010–2017 / OOS 2018–2026-09 · 5 bp per side ·
~55 variants (11 windows × unconditional, 30 PEAD conditionals, 5 books × 3 costs).

Code: `code/us-large-cap/earnings-event-drift/` (`event_study.py`, `event_profile.py`,
`preannounce_backtest.py`, outputs `*_out.txt`, `event_profile.csv`, `preannounce_results.csv`).

## 1. Idea

Savor & Wilson (2016) report announcers earn ~10 %/yr abnormal on announcement days (portfolio
Sharpe 0.94); Frazzini & Lamont (2007) an "expected announcer" premium; Bernard & Thomas the
post-earnings drift. The data needed — historical announcement dates with before/after-open
timing — turned out to be available from yfinance (`get_earnings_dates(limit=100)`, ~100 prints
per ticker back to 2002; 79 % of inferred reaction bars show volume > 1.5× normal, median 2.1×).
Event effects have per-trade edges an order of magnitude above short-term reversal's, so this
was the natural second cycle after `industry-residual-reversal` failed on costs.

## 2. Method

Reaction bar = announcement day for before-open prints, next bar for after-close (Yahoo hour
≥ 16). 27.9 k events on 613 tickers, 2010–2026. Returns are **sector-residual, simple**
(the first pass used log residuals and showed a spurious −45 bp post-window: the log
correction −σ²/2 ≈ 1 bp/day, 42 days ≈ 45 bp; documented here so nobody repeats it).

## 3. Results

### 3.1 Unconditional windows (bp, sector-residual)

| window | N | mean | t | IS | OOS |
|---|---|---|---|---|---|
| pre [−10,−6] | 27.9k | +3 | 1.5 | +7 | 0 |
| pre [−5,−2] | | +4 | 2.8 | +2 | +6 |
| pre [−1] | | **+4** | **5.4** | +5 | +4 |
| pre [−5,−1] | | **+9** | **5.0** | +7 | +10 |
| reaction [0,+1] | | −3 | −0.8 | −2 | −3 |
| post [+2,+5] | | 0 | 0.0 | 0 | 0 |
| post [+2,+21] | | +1 | 0.3 | −4 | +5 |
| post [+2,+42] | | −4 | −0.9 | −9 | 0 |

Full event-time profile −45…+45 in `figures/02_event_profile.png`: flat except the last five
bars before the print.

### 3.2 PEAD conditional on the reaction (z = reaction-bar residual / 20d vol)

| reaction | post [+1,+5] | post [+2,+21] | post [+2,+42] (IS / OOS) |
|---|---|---|---|
| z > +2 (N 6.5k) | +2 (t 0.6) | +6 (t 0.9) | −5 (+11 / −16) |
| z < −2 (N 6.3k) | −7 (t −1.6) | −19 (t −1.8 at 42d) | −19 (−14 / −23) |
| 2-day reaction z < −2 | −5 | | −24 (t −2.3) |

Bad prints drift a further ~20 bp over two months (t ≈ 2), good prints do not drift and
reverse OOS. A 42-day L/S on this has a ~40 bp/quarter spread per name — with 4 events a
year per name it is ~1.6 %/yr on a book with ~4 % residual vol → Sharpe ≈ 0.4 before costs.
Not pursued further.

### 3.3 Pre-announcement long book — `preannounce_backtest.py` (upper bound)

Long every name in the window, sector-hedged, dollar-neutral, gross 1.0 when ≥ 20 names.
Uses the *actual* date as the expected date (mild lookahead; a real implementation would use
Yahoo's forward calendar or last date + 91 days, which can only do worse).

| window | names/day | turnover/yr | gross Sh | net 2 bp | net 5 bp | IS/OOS (5 bp) |
|---|---|---|---|---|---|---|
| [−5,−1] | 33 | 64 | 0.83 | 0.18 | **−0.80** | −1.28 / −0.50 |
| [−3,−1] | 20 | 79 | 0.90 | −0.01 | −1.39 | |
| [−1,−1] | 7 | 106 | 1.14 | −0.41 | −2.70 | |
| [−10,−1] | 66 | 58 | 0.94 | 0.41 | −0.39 | |
| [−5,0] (incl. reaction) | 40 | 64 | 0.44 | 0.09 | −0.44 | |

Vol of these books is 1.4–2.2 %/yr: the effect is real, tiny, and 100 % eaten by the spread.
`figures/01_preannounce_equity.png`.

## 4. Conclusion

The earnings announcement premium in S&P 500 names post-2010 is ≈ 9 bp per event, not the
30–100 bp of the older, all-cap literature; PEAD is absent; the reaction itself is unpredictable
from prices. Nothing here approaches 1.5 even at zero cost (best gross 1.14 with 7 names/day).

## 5. Not tried / left for a future cycle

* Earnings-cycle *phase* as a slow signal (days-since-last vs days-to-next): the profile is
  flat outside [−5, −1], so there is nothing to harvest at quarterly turnover.
* Conditioning the pre-announcement run-up on options-implied move (no options data here).
* Ex-dividend run-ups (Hartzmark & Solomon): same magnitude class, same cost problem expected.
