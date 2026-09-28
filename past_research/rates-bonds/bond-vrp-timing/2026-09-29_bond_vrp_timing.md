# bond-vrp-timing — does the Treasury variance risk premium time duration?

**Date:** 2026-09-29 · **Asset class:** rates-bonds · **Status:** **Failed**

## 1. Idea

Mueller, Vedolin & Yen (2017), *Bond variance risk premiums*: the gap between implied and
realised Treasury volatility predicts bond excess returns. Investors pay up for rate-vol
insurance when the premium is high, and the term premium is high with it. The MOVE index
gives a free daily implied-vol series from 2002-11, and realised vol from CMT yield changes
is never revised. The idea has not been tested in this repo; `credit-spread-trend` used the
VIX, not rates vol.

## 2. Setup — `01_screen.py`, `01_screen_output.txt`

* MOVE (`^MOVE`, now cached as `data/IDX_MOVE_d.parquet`): 1-month implied normal vol, bp/yr,
  weights 2y/5y/10y/30y = 0.2/0.2/0.4/0.2. Realised: the same weights on 21-day CMT yield
  changes (bp), annualised, so the units match (mean MOVE 79.4, mean RV 75.6, mean VRP +3.8 bp).
* Signals: `vrp` = z(MOVE − RV), `ratio` = z(log MOVE/RV), `move_z` = z(MOVE),
  `vrp_raw` = VRP standardised on its expanding history, `dmove` = z(5-day MOVE change).
  z on a trailing 252-day window.
* Books: long duration when the signal is high (the hypothesis); linear `clip(z/2, ±1)` or
  binary sign; weekly or monthly re-set; IEF and TLT excess of the bill; 2 bp/side.
* **Split fixed in advance:** IS 2003–2014, OOS 2015–2026.

## 3. Results

Spearman IC vs forward excess returns (weekly samples):

| Signal | IEF 21d IS / OOS | IEF 63d IS / OOS | TLT 21d IS / OOS |
|---|---|---|---|
| vrp | **+0.17 / −0.10** | +0.18 / −0.02 | +0.07 / −0.10 |
| ratio | +0.16 / −0.10 | +0.15 / −0.03 | +0.07 / −0.09 |
| vrp_raw | +0.15 / −0.13 | +0.09 / −0.06 | +0.00 / −0.13 |
| move_z | +0.07 / −0.00 | +0.03 / −0.08 | +0.08 / −0.03 |
| dmove | −0.05 / +0.02 | 0.00 / −0.03 | −0.03 / +0.00 |

The published relation is there in 2003-2014: VRP IC +0.17 on IEF at one month. In
2015-2026 **it reverses** (−0.10 to −0.13) on both instruments. 40 books: IS −0.65 … +0.37,
OOS −0.41 … +0.29. The VRP books go from 0.15–0.37 IS to **−0.2 to −0.4 OOS**, and the
Spearman correlation between IS and OOS ranks across the 40 books is **−0.47**. The only
positive-OOS family (`dmove`, 0.12–0.29) is negative IS.

## 4. Verdict

**Failed.** ~100 IC cells and 40 books. The bond variance risk premium timed duration
before 2015 and has timed it the wrong way since. One reading: after 2015 high implied vol
arrived with *inflation* shocks (2021-23) rather than flight-to-quality shocks, so a high
premium came before bond losses rather than gains. This is the same regime break that
killed the VIX-spike duration hedge in `credit-spread-trend`. Any vol-based duration
timer designed on pre-2015 data should be assumed to fail after 2021 unless it is conditioned
on the stock-bond correlation regime, and the correlation-conditioned version of a related
signal (`cross-asset-tsmom` round 2) also failed.
