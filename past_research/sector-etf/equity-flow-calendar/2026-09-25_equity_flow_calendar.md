# equity-flow-calendar — month-end, FOMC and holiday flow windows on the sector basket

**Status: Failed** (standalone Sharpe ≈0.7, no better risk-adjusted than holding the basket
out of sample). Asset class `sector-etf`. Date 2026-09-25.

## Idea
The rates-bonds `treasury-flow-calendar` alpha works because institutional cash flows land on
predictable dates. Equities have their own documented flow calendar:
* **turn of the month** — Lakonishok & Smidt (1988), McConnell & Xu (2008): [-1, +3];
* **dash for cash** — Etula, Rinne, Suominen & Vaittinen (2020 RFS): month-end payment needs
  depress prices before, and lift them across, the turn; window [-3, +3];
* **pre-FOMC drift** — Lucca & Moench (2015): the statement day and the day before;
* **FOMC-cycle even weeks** — Cieslak, Morse & Vissing-Jorgensen (2019);
* **pre-holiday** — Ariel (1990).

Traded through the sector ETFs: long the equal-weight sector basket (or SPY, or the four
highest-beta sectors) inside the windows, flat outside. All windows were fixed from the papers
before any backtest; nothing was fitted.

## Setup
Common sector-etf setup: IS 1999-2014 / OOS 2015-2026, 2 bp/side, weights at close *t* earn
*t+1*. Every feature of day *t+1* is known at close *t* (position in the month, the published
FOMC schedule — unscheduled meetings removed, since they were not known in advance — and the
NYSE holiday calendar). FOMC dates are a snapshot of the rates-bonds calendar
(`fomc_snapshot.csv`).

## Event study (`event_study.py`), EW basket, mean bp/day (t)
| Bucket | IS | OOS |
|---|---|---|
| day −4 | +21.3 (2.3) | +12.7 (1.4) |
| day −2 | +8.0 (0.9) | +18.7 (2.4) |
| day +1 | +16.2 (1.6) | +10.0 (1.2) |
| day +2 | +8.4 (1.0) | +12.5 (1.5) |
| days −7/−6 | −10 (−1.1) | +2…+5 |
| day before FOMC | +10.6 | +9.0 |
| FOMC week 0 (CMVJ) | +11.9 (2.2) | **−3.7** |
| pre-holiday | +14.3 (1.7) | +15.1 (2.2) |
| all other days | +3.2 | +4.4 |

The turn-of-month and pre-holiday premia persist; the CMVJ even-week pattern and the
statement-day premium have faded since 2015; the negative "pre-payment" days −7/−6 have
flipped sign.

## Books (`books.py`, 39 rows; `overlays.py`, 14 rows)
| Book | Sharpe full | IS | OOS | CAGR | MaxDD | time in |
|---|---|---|---|---|---|---|
| SPY buy & hold | 0.53 | 0.35 | 0.82 | 8.7 % | −55 % | 100 % |
| EW sectors buy & hold | 0.57 | 0.48 | 0.73 | 9.1 % | −53 % | 100 % |
| **EW, TOM[-3,+3] + pre-FOMC + pre-holiday** | **0.69** | 0.75 | 0.59 | 6.8 % | −25 % | 35 % |
| SPY, same windows | 0.65 | 0.66 | 0.64 | 6.8 % | −30 % | 35 % |
| EW, all windows incl. CMVJ even weeks | 0.66 | 0.75 | 0.52 | 9.0 % | −27 % | 66 % |
| EW, TOM[-1,+3] only | 0.40 | 0.45 | 0.32 | 2.7 % | −19 % | 19 % |
| EW, tilt 1.5× in-window / 0.5× out | 0.72 | 0.70 | 0.76 | 11.4 % | — | 100 % |
| EW windows + inverse-vol (20 %) | 0.70 | 0.88 | 0.44 | 7.9 % | — | 51 % gross |
| EW windows + SMA200 trend gate | 0.51 | 0.80 | **0.11** | 3.2 % | — | 27 % |

The window book halves drawdowns (−25 % vs −53 %) and was positive in 2008 (+8.6 %) and 2022
(+10.1 %), but OOS its Sharpe (0.59) is *below* just holding the basket (0.73), because the
2015-26 bull market paid on out-of-window days too (out-of-window Sharpe 0.37 OOS vs −0.08 IS).
High-beta sectors do not carry more of the premium than the EW basket; the sector cross-section
adds nothing to a market-level calendar effect.

## Verdict
~53 configurations. The flow calendar is real (turn-of-month and pre-holiday premia survive
OOS) but is a **market-level** effect worth ≈0.6-0.7 Sharpe at 35 % exposure, not a sector
edge, and not enough to stand alone. **Binding constraint: per-day edge (~9 bp) against ~1.2 %
daily vol** — no timing overlay lifts that ratio. Possible use: a drawdown-reducing sleeve, or
the timing leg of a multi-sleeve book.

## Files
`code/sector-etf/equity-flow-calendar/`: `cal.py` (ex-ante calendar features), `event_study.py`,
`books.py` (+`books.csv`), `overlays.py`, `fomc_snapshot.csv`.
