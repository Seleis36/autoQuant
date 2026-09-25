# Cross-country carry and value on country ETFs — Failed

**Asset class:** `global-equity-etf` · **Short name:** `dividend-yield-carry` · **Date:** 2026-09-26
**Status:** **Failed.** No carry, value or fundamental-momentum signal beats noise on this
cross-section.

## Idea

Koijen, Moskowitz, Pedersen & Vrugt (2018, *Carry*): an equity index's carry is D/P − r_local,
and a currency's carry is r_local − r_US. A US investor in an *unhedged* country ETF earns both,
so the ETF's carry is **D/P − r_US**. Cross-sectionally r_US is common, so **the carry ranking
is the dividend-yield ranking**. That is also the classic country-value signal (Asness, Liew &
Stevens 1997). Value is known to be negatively correlated with country momentum, which failed
here earlier (`country-xs-momentum`). A value + momentum blend (Asness-Moskowitz-Pedersen 2013)
was therefore the natural second test.

## Data

* **Distribution yield.** iShares distributions (yfinance `Ticker.dividends`, ex-date,
  `data/<T>_div.parquet`) divided by the prior day's **unadjusted** close
  (`data/<T>_d_unadj.parquet`; the auto-adjusted cache understates old prices and would inflate
  old yields). Point-in-time, since ex-dates are public on the day.
* Distributions are lumpy: semi-annual, with specials (EWJ Dec-2025 paid 3.8 % in one
  distribution). So the yield is an **exponentially smoothed sum** of ex-date yields, τ = 2 years,
  valid after two years of history. This avoids the hard-window trap in which a 365-day window
  holds 1 or 3 semi-annual payments depending on date drift.
* Universe: 9 country ETFs + SPY (the US as the tenth country). EFA, EEM and ACWI are excluded
  as aggregates of the cross-section. Monthly rebalance at the last close of the month.
  Rank-weighted, dollar-neutral, scaled to 10 % ex-ante vol on the trailing 126d covariance.
  5 bp/side (SPY 1 bp).
* Sample 2001-01 → 2026-09. IS ≤ 2012, OOS 2013+ (fixed before this idea was run).

## Results (net Sharpe, 5 bp)

`01_carry_value.py`, 18 cells:

| Signal | Full | IS | OOS | MaxDD | Turn/yr |
|---|---:|---:|---:|---:|---:|
| dy (yield level), rank | 0.02 | 0.07 | −0.03 | −36 % | 2.5 |
| dy_rel (log yield vs own 5y mean) | 0.04 | −0.06 | 0.11 | −47 % | 5.0 |
| ltr (−5y-to-1y return) | −0.02 | −0.40 | 0.22 | −52 % | 5.5 |
| mom (12-1) | 0.11 | 0.34 | −0.10 | −49 % | 9.3 |
| dy + mom | 0.09 | 0.28 | −0.05 | −48 % | 7.6 |
| ltr + mom | −0.18 | −0.22 | −0.15 | −62 % | 10.1 |
| dy + ltr + mom | −0.03 | 0.09 | −0.11 | −52 % | 8.7 |

Tercile (top-3/bottom-3) weights give the same picture (±0.05).

`02_reframe.py`, 28 more cells. Beta-neutral legs, ex-US cross-section, dividend growth
(fundamental momentum: 1y/2y growth in smoothed USD dividends per share), quarterly rebalance:

| Signal | base | beta-neutral | ex-US | quarterly |
|---|---:|---:|---:|---:|
| dy | 0.02 / −0.03 | −0.08 / −0.18 | 0.06 / 0.04 | 0.00 / −0.04 |
| dy_rel | 0.04 / 0.11 | 0.16 / 0.24 | 0.19 / 0.27 | 0.04 / 0.10 |
| ltr | −0.02 / 0.22 | −0.08 / 0.16 | 0.26 / 0.53 (IS −0.22) | −0.06 / 0.16 |
| dgrow1 | 0.00 / −0.01 | 0.04 / 0.03 | −0.02 / −0.09 | 0.03 / 0.02 |
| **dgrow2** | 0.12 / 0.07 | **0.20 / 0.18** (IS 0.22) | 0.13 / −0.04 | 0.08 / −0.02 |
| dgrow1 + mom | −0.03 / −0.19 | 0.00 / −0.17 | −0.10 / −0.31 | 0.07 / −0.01 |
| dy + mom | 0.09 / −0.05 | 0.08 / −0.10 | 0.00 / −0.17 | 0.10 / −0.02 |

(full / OOS Sharpe). The only cell positive in both halves is 2-year dividend growth,
beta-neutral: 0.20 full, 0.22 IS, 0.18 OOS, t_NW 1.0. With 46 cells over ~25 years, the SE of
an annual Sharpe is ≈ 0.2, and the expected best-of-46 under the null is ≈ 0.44. Nothing here is
distinguishable from noise.

Book betas are ≈ 0 (−0.04…+0.08) in every base cell. The failure is not a hidden EM-beta bet
washing out.

## Why it fails

* **Ten names.** A rank book on ten countries is a bet on 3-4 pairs. Published country-value
  Sharpes (~0.3-0.5) come from 18-40 markets.
* **2013-2026 was the decade the US (the lowest-yield, most expensive market) beat everything.**
  Carry is short SPY throughout and pays for it. The ex-US version is cleaner but still ≈ 0 on
  the yield level.
* **Yield differences are near-static.** EWA, EWU and EWZ are always high; INDA, EWY and SPY are
  always low. Level-carry is a fixed country tilt with 2.5×/yr turnover. The relative-to-history
  form (dy_rel) is the timing version, and it too sits at 0.1-0.3.

## Files

`code/global-equity-etf/dividend-yield-carry/01_carry_value.py`, `02_reframe.py`. Shared helpers:
`code/global-equity-etf/shared/xs.py` (monthly XS book), `data.py` (`load_dividends`,
`load_unadjusted_close`).
