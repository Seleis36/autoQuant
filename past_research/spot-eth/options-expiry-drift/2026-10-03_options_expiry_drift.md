# options-expiry-drift — ETH around the Deribit option expiries; a short before the month-end settlement

**Date:** 2026-10-03
**Asset:** spot ETH/USDT (Binance, 1-minute and hourly bars, UTC), short/flat, simulated book, 10 bp/side
**Status:** **Working (borderline).** A small, real calendar effect: ETH falls over the eight hours before the month-end option settlement. Net Sharpe 0.71 standalone, uncorrelated with every other spot-eth sleeve. Half of that Sharpe comes from three events, and it does not survive 30 bp/side.

Headline — `strategy.py` spec, short 1× ETH from 00:00 to 08:00 UTC on the last Friday of each month, 2020-01 → 2026-10:

| | full | IS 2020–23 | OOS 2024+ |
|---|---|---|---|
| Net Sharpe @10 bp/side | **0.71** | 0.58 | **0.88** |
| Gross move in the window (bp) | −61 (t −3.0) | −50 (t −2.1) | −76 (t −2.1) |
| Events | 81 | 48 | 33 |

- CAGR 4.5%, vol 6.5%, MaxDD −6.0%; in the market 1.1% of the time; turnover 24×/yr (12 round trips).
- Net per event +39 bp (t 1.9), 57% of events profitable; six of seven calendar years positive.
- Correlation of daily P&L with the live trend filter: −0.06.

## 1. Idea

Deribit holds most ETH option open interest. Its options settle at **08:00 UTC** against the
30-minute TWAP of the index (07:30–08:00). Every Friday is a weekly expiry; the **last Friday of
the month** is the monthly — and in March, June, September and December the quarterly — expiry,
where open interest is concentrated. The lore around these dates comes in three versions:
prices are pinned or pushed toward "max pain" before settlement, volatility is suppressed before
and released after, and the market rallies once the hedges are gone.

All three are testable on the 1-minute store with nothing but a calendar. The question is
whether any of them is large enough to pay 20 bp per round trip.

## 2. Data and protocol

- Binance ETHUSDT and BTCUSDT 1-minute bars (`bars.load_bars`), through 2026-10-02. Price "at
  time t" is the close of the minute bar ending at t.
- Event time T = Friday 08:00 UTC. Classes: quarterly (27), monthly (54), weekly (271); placebo
  = Tuesdays at the same clock time (351).
- **Sample start 2020-01-01**, fixed before any return was computed: Deribit ETH options had
  negligible open interest before 2020. The 28 last-Fridays of 2017-09 → 2019-12 serve as a
  pre-options placebo.
- IS 2020 → 2023, OOS 2024-01 → 2026-10 (the spot-eth convention).
- The calendar is a pure function of the date; there is no fitted parameter and nothing to leak.
  One bug was caught on the way: classifying "last Friday" inside a truncated date range turns
  the final Friday of the sample into a month-end. `common.expiries` now classifies against
  whole calendar months.

## 3. Event study (`exp01_event_study.py`) — 13 windows × 5 groups

Mean log return in bp (t-stat):

| window | month-end IS | month-end OOS | other Fridays IS | other Fridays OOS | Tuesday IS | Tuesday OOS |
|---|---|---|---|---|---|---|
| T−7d … T−3d | −80 (−0.6) | −1 (0.0) | +157 (2.5) | +25 (0.4) | +58 (0.9) | −5 (−0.1) |
| T−24h … T | +80 (1.3) | **−167 (−3.4)** | −35 (−0.9) | −30 (−0.8) | +48 (1.6) | +9 (0.3) |
| **T−8h … T** | **−50 (−2.1)** | **−76 (−2.1)** | +10 (0.5) | +25 (1.4) | +5 (0.4) | −42 (−2.9) |
| T−2h … T | −4 (−0.3) | −41 (−3.4) | +3 (0.3) | −3 (−0.3) | +7 (1.1) | −7 (−1.0) |
| T … T+4h | −38 (−1.0) | +41 (1.5) | +22 (1.7) | +4 (0.3) | +16 (1.3) | +1 (0.1) |
| T … T+24h | +60 (1.1) | +1 (0.0) | +9 (0.3) | +2 (0.1) | +16 (0.5) | +15 (0.5) |
| T … T+72h | **+242 (3.1)** | −63 (−0.6) | −6 (−0.1) | +33 (0.6) | +39 (0.7) | −10 (−0.2) |
| T … T+7d | **+495 (4.0)** | −210 (−1.2) | +30 (0.3) | +81 (1.0) | +135 (1.6) | +9 (0.1) |

What the three stories come to:

- **Post-expiry rally: decayed.** +2.4% over three days and +5% over a week after the month-end
  expiry in 2020–23 (t 3.1 and 4.0), then −0.6% and −2.1% in 2024–26. The week after the last
  Friday is the turn of the month, and this is the effect `spot-btc/turn-of-month-flow` found
  and lost over the same years.
- **Pinning: not visible.** Realised vol in the 24 h after against the 24 h before: median ratio
  0.94 / 0.95 at month-end, 0.89 / 0.91 on other Fridays, 0.97 / 0.99 on Tuesdays. No release.
  The day before the expiry flips sign between halves (+80 → −167 bp).
- **Pre-settlement dip: present in both halves.** Over the last eight hours ETH loses 50 bp IS
  and 76 bp OOS. Against other Fridays the gap is −60 bp (t −1.9), −101 bp (t −2.5), −77 bp
  (t −3.1) for IS, OOS and the full sample. It is the only one of the 13 month-end windows with
  \|t\| ≥ 2 and the same sign in both halves.

## 4. Is the dip real? (`exp02_pre_expiry_dip.py`)

**Hour by hour** (full sample, mean bp per hour before a month-end expiry): the loss sits in the
last four hours — T−4h −7, **T−3h −20 (t −2.6)**, T−2h +7, **T−1h −26 (t −3.3)**. The last hour
contains the settlement TWAP window. On other Fridays the same hours average −10, +11, −3, +4.

**Window robustness** (month-end expiries, bp, t):

| | IS | OOS |
|---|---|---|
| T−12h … T | −49 (−1.3) | −72 (−1.9) |
| **T−8h … T** | −50 (−2.1) | −76 (−2.1) |
| T−6h … T | −52 (−2.4) | −58 (−2.4) |
| T−4h … T | −46 (−2.2) | −49 (−2.5) |
| T−2h … T | −4 (−0.3) | −41 (−3.4) |
| T−8h … T+1h | −62 (−1.8) | −56 (−1.5) |

**By year** (bp): −43, −113, −67, **+20**, −46, −120, −57 for 2020 … 2026. Leave-one-year-out
mean between −51 and −75.

**Distribution** (81 events): mean −61, median −49, trimmed mean (2 + 2) −50, sd 184, 60% of
events negative, 57% below −20 bp (the round-trip cost), skew −1.7. The largest are 2025-02-28
(−914 bp), 2021-05-28 (−664), 2025-03-28 (−478).

**Controls** — the 00:00–08:00 UTC return on other days (bp, t; IS | OOS):

| | IS | OOS |
|---|---|---|
| all days | −2 (−0.3) | +1 (0.1) |
| Fridays that are not month-end | +10 (0.5) | +25 (1.4) |
| first Friday of the month | +8 (0.2) | −5 (−0.2) |
| last Thursday of the month | −22 (−0.6) | 0 (0.0) |
| last Wednesday of the month | +15 (0.5) | +36 (2.0) |
| last 7 calendar days, not a Friday | +5 (0.4) | +8 (0.8) |
| **last Friday = month-end expiry** | **−50 (−2.1)** | **−76 (−2.1)** |
| pre-options placebo, last Fridays 2017-09 → 2019-12 (n 28) | +27 (0.7) | |

It is not a Friday effect, not a month-end effect, and it was not there before the options were.

**Permutation.** Drawing one random Friday per month 5,000 times: the full-sample mean is as low
as observed in 0.2% of draws; a mean as low as observed in *both* halves at once occurred in 0
of 5,000. With a Bonferroni factor of 39 for the windows and classes examined in §3, the
both-halves criterion still gives p < 0.01.

**BTC.** Same clock, same window: −48 bp (t −2.3, 69% negative) IS and −62 bp (t −2.4, 76%
negative) OOS; other Fridays −1 and +11. ETH minus BTC: −3 and −14 bp (t −0.2, −1.0). The effect
is market-wide, not ETH-specific, so BTC is a consistency check rather than independent evidence
— but it is at least as clean there.

**Two things that do not fit the mechanism, stated plainly:**

- *Quarterly expiries show nothing.* ETH −8 bp (n 27, t −0.3) against −87 bp (n 54, t −3.4) on
  the other monthly expiries; BTC −15 against −73. Quarterlies carry the most open interest, so a
  hedging-flow story predicts the opposite. With 27 events the difference is 1.9 standard
  errors. The spec trades all twelve; dropping the quarterlies after seeing this would be
  selection.
- *The timing moved.* In 2020–23 the loss came between T−8h and T−2h (−46 bp) and the last two
  hours were flat; in 2024–26 the last two hours alone lose 41 bp (t −3.4).

**Conditioning** (mechanism: hedges on out-of-the-money calls are unwound as their delta decays,
which should be stronger after a rally):

| | IS | OOS | full |
|---|---|---|---|
| prior 30 d up | −65 (−2.0) | −89 (−3.3) | −73 (−3.0) |
| prior 30 d down | −30 (−0.8) | −67 (−1.2) | −50 (−1.4) |
| DVOL above its median | −77 (−1.8) | −32 (−1.0) | −62 (−2.1) |
| DVOL below its median | +20 (0.7) | −98 (−1.9) | −56 (−1.6) |

The direction agrees with the story after rallies in both halves, but the difference (23 bp) is
well inside the noise and the rank correlation between the prior move and the dip is +0.07 /
−0.04. Not used.

## 5. The sleeve (`strategy.py`, `exp03_validate.py`)

Short 1× ETH from Friday 00:00 UTC to Friday 08:00 UTC on the last Friday of every month; flat
otherwise. 00:00 is the daily bar boundary and was in the §3 grid before any result was seen.
Shorting needs the simulated book.

| | full | IS | OOS |
|---|---|---|---|
| Net Sharpe, 10 bp/side | 0.71 | 0.58 | 0.88 |
| Net per event (bp) | +39 | +28 | +54 |

Yearly net return: +2.3%, +10.8%, +5.3%, **−4.9%**, +2.9%, +11.9%, +3.2% (2020 … 2026 YTD).

| Check | Result |
|---|---|
| Event bootstrap of the annualised Sharpe (81 monthly events, 10,000 draws) | median 0.74, 5–95% **[0.16, 1.27]**, P(> 0) 0.98, P(> 0.5) 0.76 |
| t-stat of the net per-event return | 1.92 |
| Deflated Sharpe at 1 / 16 / 64 trials | 0.99 / 0.70 / **0.48** |
| Costs 0 / 5 / 10 / 15 / 20 / 30 bp per side | 1.05 / 0.89 / **0.71** / 0.53 / 0.35 / −0.03 |
| Without the best 1 / 2 / 3 events | 0.60 / 0.48 / **0.36** full (OOS 0.64 without 2025-02-28) |
| Without the worst 1 / 2 / 3 events | 0.79 / 0.86 / 0.92 |
| Same window on the first / second / third Friday | −0.37 / −0.74 / −0.58 |
| Same spec on BTC | 0.76 / 0.64 / 0.93; P&L correlation with the ETH sleeve 0.88 |
| vectorbt `from_orders` (targetpercent, 0.1% fee) | 0.693 vs 0.712, daily return correlation 0.9974 |
| Truncation test (`target_weight` on data cut at four dates, two of them inside an event) | max \|Δw\| = 0 |

Entry and exit neighbourhood, net Sharpe full | IS | OOS:

| entry (UTC) | exit 07:00 | **exit 08:00** | exit 09:00 | exit 12:00 |
|---|---|---|---|---|
| Thu 16:00 | −0.04 \| −0.40 \| 0.61 | 0.29 \| −0.16 \| 1.13 | 0.24 \| −0.03 \| 0.83 | 0.26 \| 0.19 \| 0.47 |
| Thu 20:00 | 0.13 \| 0.07 \| 0.22 | 0.50 \| 0.35 \| 0.73 | 0.42 \| 0.41 \| 0.44 | 0.40 \| 0.53 \| 0.11 |
| **Fri 00:00** | 0.24 \| 0.18 \| 0.31 | **0.71 \| 0.58 \| 0.88** | 0.55 \| 0.55 \| 0.55 | 0.48 \| 0.62 \| 0.18 |
| Fri 02:00 | 0.18 \| 0.28 \| 0.03 | 0.78 \| 0.71 \| 0.88 | 0.55 \| 0.64 \| 0.38 | 0.46 \| 0.69 \| −0.10 |
| Fri 04:00 | 0.01 \| 0.15 \| −0.25 | 0.69 \| 0.60 \| 0.85 | 0.47 \| 0.59 \| 0.22 | 0.39 \| 0.65 \| −0.25 |
| Fri 06:00 | −1.50 \| −1.76 \| −1.02 | −0.05 \| −0.60 \| 1.01 | −0.08 \| −0.12 \| 0.02 | 0.06 \| 0.25 \| −0.49 |

A plateau of 0.69–0.78 for entries between 00:00 and 04:00 with the exit at 08:00. The exit is
the sensitive leg: leaving an hour early gives up the settlement hour (0.24), an hour late gives
back part of it (0.55).

**As a veto on the trend filter** (hourly book, 2020+, flat over the same eight hours): 1.300 →
1.336 full, 1.374 → 1.376 IS, 1.184 → 1.277 OOS. Positive, too small to matter.

## 6. Verdict

**Working (borderline).** The gross effect has the properties one asks of a real one — both
halves, six of seven years, absent before listed options had open interest, absent on every
other Friday and every other late-month weekday, present in BTC, permutation p = 0.002 — and it
nets +39 bp per event after a 20 bp round trip.

What limits it:

- **Size.** Sharpe 0.71 with a bootstrap interval of [0.16, 1.27]; the net per-event t-stat is
  1.9. At 64 trials — every cell looked at — the deflated Sharpe is 0.48.
- **Tail dependence.** Three of 81 events (two crash mornings in early 2025, one in May 2021)
  supply half the Sharpe: 0.36 without them. The median event still pays (−49 bp gross), but
  the typical year is +3%, not +5%.
- **Cost.** 0.35 at 20 bp/side, nothing at 30. It needs a cheap short: the simulated book at
  10 bp, or in practice a perp at 4–5 bp taker.
- **An unexplained hole.** The quarterly expiries, where the mechanism should be strongest,
  contribute nothing.

Its value is that it is unrelated to everything else in the book: eight hours a month, short,
ρ −0.06 with the trend filter. It is a small diversifier, not a second engine.

The same spec on spot BTC is at least as good (0.76 / 0.64 / 0.93) and was not known to the
spot-btc research; ρ 0.88 with this sleeve, so it is one bet, not two.

Configurations evaluated: 65 event-study cells per half (13 windows × 5 groups); 12 window
variants, 9 calendar controls, 6 conditioning cells; 30 costed sleeves (the spec, 23 entry/exit
neighbours, 3 placebo Fridays, BTC, the trend-filter veto and its base).

## 7. Files

- `code/spot-eth/options-expiry-drift/strategy.py` — `target_weight(close)`, the deployable signal
- `common.py` — expiry calendar, price lookups
- `exp01_event_study.py` (+ `exp01_event_returns.csv`), `exp02_pre_expiry_dip.py`, `exp03_validate.py`, `exp04_figures.py`
- `alphas/spot-eth/options-expiry-drift/2026-10-03_alpha_spec.md` + three figures
