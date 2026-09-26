# FOMC global premium on country ETFs — Failed standalone, used as a sleeve

**Asset class:** `global-equity-etf` · **Short name:** `fomc-global-beta` · **Date:** 2026-09-26
**Status:** **Failed** as a standalone strategy. Net Sharpe 0.45 (IS 0.45 / OOS 0.51) at 6 % time
in market, which is no better risk-adjusted than holding the basket (0.47). It is kept as the
second sleeve of [`global-etf-sleeve-blend`](../global-etf-sleeve-blend/), because it is
uncorrelated (−0.06) with `intl-relative-trend`.

## Idea

Brusa, Savor & Wilson (2020, *RoF*, "One central bank to rule them all"): equity markets
worldwide earn large excess returns on **FOMC** announcement days, and not on other central
banks' days. Higher-beta markets earn more. Lucca & Moench (2015): most of the US premium
accrues in the 24 hours *before* the statement. For US-listed country ETFs, the 14:00 ET
statement falls inside the US session, so the ETFs price the global reaction the same day.
Savor & Wilson (2014): the security market line is steep on announcement days and flat
otherwise, which suggests a high-minus-low-beta test as well.

## Setup

* Scheduled statement days 2001-2026 from the rates-bonds calendar snapshot, with the 8
  unscheduled intermeeting actions removed (they were not known in advance). The Fed's
  published 2026-27 calendar is included. File: `fomc_snapshot.csv`.
* Windows **fixed from the literature before any backtest**: days −1 and 0, i.e. hold from the
  close of day −2 to the close of day 0. Day 0 alone was also tested.
* Baskets: EW of the 9 country ETFs, EEM, EEM − βSPY, and high-minus-low beta terciles
  (trailing 252d beta, top-3 vs bottom-3).
* 5 bp/side (SPY 1 bp). IS 2001-2012, OOS 2013-2026. CPI and payroll days were checked as
  controls.

## Event study (`01_event_study.py`): mean bp (t)

| | day −1 IS | day 0 IS | day −1 OOS | day 0 OOS | day +1 OOS | day +2 OOS |
|---|---:|---:|---:|---:|---:|---:|
| EW9 | −7 (−0.3) | **+62 (3.8)** | +16 (2.2) | +21 (1.7) | −20 (−1.6) | −20 (−1.7) |
| SPY | −3 | +42 (3.0) | +13 (1.8) | +7 (0.7) | −7 | −5 |
| EEM | −3 | +92 (3.9) | +14 (1.5) | +25 (1.7) | −22 | −16 |
| EEM − SPY | −4 | +41 (3.3) | +1 | +18 (1.8) | −14 | −11 |
| HML beta | −9 | +19 (1.6) | −3 | −2 | +8 | −13 |

Non-event days average about 4-5 bp for EW9. CPI and NFP days show no consistent premium
(signs flip between halves).

## Books (`02_books.py`), net Sharpe on all days (flat = 0)

| Book | Full | IS | OOS | CAGR | MaxDD | In market |
|---|---:|---:|---:|---:|---:|---:|
| **EW9, days −1/0** | **0.45** | 0.45 | **0.51** | 2.7 % | −15 % | 6.3 % |
| EEM, days −1/0 | 0.47 | 0.52 | 0.45 | 3.4 % | −15 % | 6.3 % |
| EW9, day 0 | 0.57 | 0.87 | 0.24 | 2.3 % | −9 % | 3.2 % |
| EEM, day 0 | 0.60 | 0.91 | 0.27 | 3.0 % | −7 % | 3.2 % |
| EEM − βSPY, day 0 | 0.15 | 0.04 | 0.23 | 0.4 % | −15 % | 3.2 % |
| HML beta, days −1/0 | −0.35 | −0.18 | −0.60 | | | |
| calendar: FOMC + turn-of-month + pre-holiday, EW9 | 0.45 | 0.63 | 0.23 | 4.8 % | −28 % | 27 % |
| *buy & hold EW9* | *0.47* | *0.49* | *0.46* | *8.4 %* | *−62 %* | *100 %* |

The global premium is a **level** effect: the whole country basket rises. The *beta spread*
(Savor-Wilson SML steepening) does not survive: HML is negative and EEM − βSPY ≈ 0 net. Day 0
alone decays from 0.87 to 0.24, while the two-day window holds (0.45 / 0.51).

## Robustness (`03_robustness.py`), EW9 days −1/0

* 205 events: mean +35 bp net per event, median +35, hit rate 57 %, t 2.4.
* **Concentration:** the top 5 events (2001-08 crisis cuts) are 55 % of total P&L. Without
  them the mean is +16 bp, t 1.4.
* Sub-periods, mean bp (t): 2001-06 +19 (0.7), 2007-12 +71 (1.5), 2013-19 +31 (1.9),
  2020-26 +23 (1.0). All positive, none individually significant.
* **Window placebo** (every 2-day window from −6 to +4): days −1/0 is the best window both IS
  (+45 bp) and OOS (+27 bp). The neighbours are ≤ +18 IS and ≤ +8.5 OOS. Days +1/+2 are −51 bp
  OOS, a post-FOMC give-back that is not present IS (−8), so it was not traded.
* Leave one country out: 0.43-0.46. Costs 10 bp: 0.32.

## Verdict

**Failed standalone.** It is real, fixed ex ante by the literature, and passes the placebo. But
it is small (≈ 2-3 % a year at 6 % vol) and leans on a handful of crisis meetings. It is not a
better use of risk than the basket itself. Its value is that it is **uncorrelated with the
relative-trend book** (daily corr −0.06): at equal risk it lifts that book from 0.64 to 0.81.
See `global-etf-sleeve-blend`.

Variants: 18 event-study series × offsets (descriptive), 12 books + 3 benchmarks, and 10 placebo
windows.

## Files

`code/global-equity-etf/fomc-global-beta/`: `strategy.py` (sleeve weights; live edge via
`shared/trading_calendar.py`), `01_event_study.py`, `02_books.py`, `03_robustness.py`, and
`fomc_snapshot.csv`, `cpi.csv`, `payrolls.csv` (calendar snapshots copied from
rates-bonds/sector-etf).
