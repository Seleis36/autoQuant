# muni-treasury-lead-lag — muni ETFs follow Treasuries with a lag

**Date:** 2026-10-10 · **Asset class:** rates-bonds · **Status: Failed** (real gross effect; not enough net)

**Result.** Municipal bond ETFs load on the Treasury return of the previous one to three
sessions (lag-1 beta 0.07-0.20, t up to 5.2 in sample and 2.9 out of sample; LQD shows none).
A book that is long the muni ETFs / short their duration after a Treasury rally, and the
reverse after a sell-off, has a gross Sharpe of **1.95 in sample (2008-17) and 1.57 out of
sample (2018-26)**. At 2 bp per side the IS-selected cell is 1.06 / 0.88 — but that in-sample
number trades ETFs that turned over $3-8M a day, where 2 bp is not a credible cost. On a
point-in-time liquid universe (≥ $10M a day) it is **−0.20 in sample / 0.78 out of sample**.
Break-even cost is 4.4 bp, one session of entry delay removes the net (0.16 / 0.19), and
2024-25 lost money. Not deployable.

Code: `code/rates-bonds/muni-treasury-lead-lag/` (`book.py` is a research book, not a strategy).

## 1. Idea

Municipal bonds trade by appointment and are marked from evaluated prices that absorb a
Treasury move over several days. If the ETF price inherits part of that, the muni ETF's
return over the next sessions is predictable from the Treasury return just seen. The
deployed `muni-reinvestment-flow` uses the same ETFs on a calendar; this is a different
mechanism (information lag, not flow), and `equity-credit-lead-lag` found no such lag in the
liquid credit ETFs.

## 2. The lag is there (`01_lead_lag.py`, `05_nav_mechanism.py`)

Distributed-lag regression of each ETF's daily return on IEF's return at lags 0-5:

| ETF | same day (IS / OOS) | lag 1 (IS / OOS) | t lag 1 | lag 2 | sum of lags 1-5 |
|---|---|---|---|---|---|
| MUB | 0.23 / 0.37 | 0.07 / 0.11 | 2.8 / 1.7 | 0.04 / 0.04 | 0.10 / 0.20 |
| TFI | 0.23 / 0.35 | 0.13 / 0.12 | 5.2 / 2.9 | 0.06 / 0.12 | 0.25 / 0.34 |
| ITM | 0.24 / 0.45 | 0.15 / 0.20 | 4.7 / 1.6 | 0.08 / 0.06 | 0.26 / 0.31 |
| PZA | 0.29 / 0.51 | 0.12 / 0.18 | 3.2 / 1.9 | 0.13 / 0.08 | 0.30 / 0.37 |
| HYD | 0.23 / 0.42 | 0.09 / 0.22 | 2.4 / 1.6 | 0.04 / −0.03 | 0.11 / 0.22 |
| VTEB | 0.38 / 0.35 | −0.02 / 0.14 | −0.7 / 1.9 | 0.07 / 0.07 | 0.11 / 0.29 |
| SHM, SUB (short) | 0.05 / 0.14 | 0.03-0.05 / 0.04-0.07 | 1.7-2.4 / 1.5-1.8 | | 0.05-0.09 / 0.10-0.14 |
| **LQD (placebo)** | 0.54 / 0.94 | 0.02 / 0.07 | 0.3 / 1.1 | −0.01 / 0.03 | −0.07 / 0.09 |

A third to a half of the muni response to a Treasury move arrives after the day it happens.
Muni mutual-fund NAVs show the same lag in every decade since 1990 (Vanguard long-term:
lag-1 0.12 / 0.12 / 0.10 / 0.15 and lag-2 0.05 / 0.07 / 0.06 / 0.12 across 1990-99 / 2000-07 /
2008-17 / 2018-26), so it is the evaluated-price process, not a sample accident.

## 3. Books (`01_lead_lag.py`, 16 cells; IS 2008-17, OOS 2018-26, 2 bp per side on every leg)

Position = clip(k-session IEF return / trailing vol, −1, 1) in an equal-weight basket of the
eight muni ETFs, hedged with IEF at trailing 250-session betas; k = 1 / 2 / 3 / 5; every day
or |z| > 1 only; held one session or smoothed over three.

* Gross Sharpe 0.5-2.0 in sample, 1.0-1.6 out of sample across the 16 cells.
* Net: IS 0.07-1.07, OOS −0.20-0.98. **IS-best: k = 3, every day → 1.07 / 0.88.**
* Placebos: the same signal five sessions stale −0.04 / 0.21 gross; LQD in place of the munis
  0.35 / 0.20 gross.

## 4. The selected book (`02_selected.py`)

| 2 bp per side | Sharpe | CAGR | Vol | MaxDD | gross Sharpe |
|---|---|---|---|---|---|
| IS 2008-17 | 1.06 | 3.3 % | 3.1 % | −6.9 % | 1.95 |
| OOS 2018-26 | 0.88 | 3.8 % | 4.3 % | −6.0 % | 1.57 |
| Full | 0.95 | 3.5 % | 3.7 % | −6.9 % | 1.72 |

Turnover 142× a year, average gross 0.75. The P&L is the muni legs (5.8 % / 6.3 % a year
gross); the IEF hedge leg contributes 0.1 % / 0.6 %, so this is not Treasury reversal in
disguise. Truncation test exact; vectorbt 1.08 / 0.88 against 1.08 / 0.88, daily ρ 0.998.
Daily correlation with the deployed sleeves 0.02 and 0.13, with `cef-discount-reversion` 0.02
(monthly 0.57: both are paid in stress).

What breaks it:

* **Cost.** 0 bp 1.95 / 1.57 · 1 bp 1.51 / 1.23 · 2 bp 1.06 / 0.88 · 3 bp 0.62 / 0.54 · 4 bp
  0.18 / 0.19 · 5 bp −0.25 / −0.15.
* **Delay.** Entering one session later: 0.16 / 0.19 net (gross 1.04 / 0.88). The first
  session carries most of the catch-up; the book only works if it trades on the close that
  completes the signal.
* **Calm years.** Net %: 2008 +10.9, 09 +6.4, 10 +3.0, 11 +6.1, 12 +2.8, 13 +4.3, 14 −1.2,
  15 −1.6, 16 +0.9, 17 +1.0, 18 −0.3, 19 −0.1, 20 +16.3, 21 +0.4, 22 +13.3, 23 +6.3, 24 −2.3,
  25 −2.3, 26 +2.4. Gross was +0.5 % and +0.9 % in 2024-25: with MUB and VTEB now trading
  $250-400M a day the catch-up is small unless rates are moving hard.

## 5. Honest universe (`04_liquid_universe.py`)

Median daily dollar volume: MUB $15M in 2012-14, $386M in 2024-26; TFI $4M → $21M; ITM $3M →
$10M; PZA $3M → $21M; SHM $8M → $11M. Before 2015 only MUB was a 2 bp instrument.

| eligible while 60-session median volume ≥ | funds 2012 / 2020 / 2025 | net 2 bp IS / OOS | gross IS / OOS | net 4 bp IS / OOS |
|---|---|---|---|---|
| no floor | 7 / 8 / 8 | 1.08 / 0.88 | 1.97 / 1.57 | 0.18 / 0.19 |
| $5M | 2 / 7 / 8 | 0.14 / 0.87 | 1.32 / 1.56 | −1.03 / 0.19 |
| **$10M** | 1 / 6 / 7 | **−0.20 / 0.78** | 0.91 / 1.46 | −1.29 / 0.10 |
| $20M | 0.2 / 3 / 5.5 | 0.70¹ / 0.61 | 2.51 / 1.14 | −1.06 / 0.09 |

¹ from 2012-03, usually one fund.

By liquidity rank (2012-26): the two most liquid funds of the day gross 1.46 / net 0.55; the
four least liquid gross 1.82 / net 0.98. The lag is not just stale prints in thin funds, but
the in-sample net result is.

## 6. Cost-aware sizing (`03_cost_aware.py`, 36 cells)

Sizing on the Treasury move in bp with a dead zone, selected on IS at a 4 bp stress cost:
best cell (k = 3, dead zone 0.75 %, full at 2 %) IS 0.62 at 4 bp → OOS 0.31; at 2 bp 0.90 / 0.51.
Family means 0.79 / 0.68 at 2 bp and 0.25 / 0.28 at 4 bp; IS/OOS rank correlation −0.23.
It does not improve on the simple book.

## 7. Verdict

The muni lag is real, old, and visible in the most liquid muni ETF. A gross Sharpe above 1.5
in both halves is the best gross result among the ETF ideas in this folder. It still fails
as a strategy: it needs ≤ 2 bp all-in on eight ETFs, a fill on the very close that completes
the signal, and volatile rates. Where the 2 bp assumption is honest (liquid funds, 2018-26)
there is no clean in-sample period behind it. 58 cells scored.

**If someone revisits:** the one configuration worth a fresh look is MUB + VTEB only, at a
measured 1 bp cost, as an overlay on the deployed `muni-reinvestment-flow` (which already
trades MUB and IEF) — judged on data after 2026-10.
