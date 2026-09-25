# sector-short-reversal — short-horizon mean reversion across the SPDR sectors

**Status: Failed.** Asset class `sector-etf`. Date 2026-09-25.

## Idea
Industry-level short-term reversal is documented as *stronger* than stock-level reversal
(Da, Liu & Schaumburg 2014; the "industry reversal" line of work), and sector SPDRs are
the cheapest instruments in US equities to trade (1-cent spreads on $40-600 prices).
The us-large-cap research found gross reversal Sharpe ~1 killed by 10 bp round trips;
sector ETFs cut that cost by ~3-5×. Nagel (2012) adds that reversal is a liquidity-provision
return that scales with VIX, which suggests a volatility gate.

## Setup (fixed before results, shared by every sector-etf idea)
* Data: 11 SPDR sectors + SPY, yfinance auto-adjusted daily, 1998-12-22 → 2026-09-24
  (pre-2010 spliced from `data/<T>_d_pre2010.parquet`, `code/sector-etf/shared/data.py`).
  XLRE enters 2016-10, XLC 2019-06 (one year of history required before a name enters).
* IS 1999-2014, OOS 2015-2026-09. Cost 2 bp per side on all traded notional (5 bp stress).
* Signals at close *t*, earn *t+1* (`research_lib.backtest_xs`). Beta = EWM(126d) to SPY,
  lagged one day in the residual.

## Evidence
### 1. Rank-IC scan (`ic_scan.py`)
Past-k relative (sector − SPY) and beta-residual returns vs next-day relative returns:

| k | IC IS | t IS | IC OOS | t OOS |
|---|---|---|---|---|
| 1 | −0.036 | −5.3 | −0.015 | −2.0 |
| 3 | −0.035 | −5.1 | −0.007 | −1.0 |
| 5 | −0.024 | −3.5 | −0.006 | −0.7 |
| 21 | −0.010 | −1.4 | −0.014 | −1.8 |
| 252 | +0.018 | +2.6 | +0.018 | +2.2 |

The 1-3 day reversal was strong before 2015 and has faded to a third of its size since.
12-month momentum is weakly positive in both halves (picked up again in later ideas).

### 2. Cross-sectional book (`grid.py`, 192 cells)
Linear weights on −(k-day relative or residual return), raw or vol-scaled; SPY hedge to
zero beta; 1/3/5-day tranches; VIX gates none / >1y median / >20 / >25.

* Best IS cell `resid|k1|volz|n5|vix>20`: **IS 0.96 → OOS −0.22** (gross OOS −0.01).
* Ungated always-on books: IS ≤ 0.73, OOS −0.5…0.1 — the turnover (75-380×/yr) eats the
  whole OOS gross edge at 2 bp.
* Best OOS cell `rel|k3|volz|n3|vix>25`: full 0.63, IS 0.70, OOS 0.50. Its P&L by year is
  2000 +6.7 %, 2001 +14.2 %, 2008 +17.4 %, **2020 +18.9 %**, and ≈0 in every other year —
  a crisis-only liquidity-provision trade, and the OOS half is essentially one event.

### 3. Time-series re-framing (`ts_grid.py`, 96 cells)
Connors-style: long a sector when RSI(2) < 5/10/20 or 3-day vol-z < −1/−1.5/−2, optional
SMA200 filter, exit on RSI(2)>50 or close>SMA5 or max 5/10 days, 1/9 of capital per name.

* Unhedged: Sharpe 0.55-0.64 full, 0.4-0.63 OOS at 10-30 % average exposure — the same
  Sharpe as buying and holding SPY (0.53 full / 0.82 OOS) or EW sectors (0.57 / 0.73).
* **SPY-hedged versions are all negative** (best OOS −0.08): the dip-buying edge is
  market-level mean reversion, not anything sector-specific.

### 4. Extreme-move and VIX-scaled re-framings (`events_vixscale.py`, 24 cells)
* Fading |z|>2/2.5/3 one-day residual moves, 1-10 day holds: best full 0.37, OOS ≤ 0.29.
* Size ∝ VIX/20 (capped 2×) instead of a gate: best OOS 0.08.

## Verdict
312 configurations. Nothing sector-specific survives out of sample; the only sector-relative
reversal left after 2014 lives in VIX>25 crises (2020 alone). The time-series version works
only because it is long the market after dips, and it does not beat holding the market.
**Binding constraint: the effect itself decayed** (IC −0.035 → −0.010), not costs — gross
OOS Sharpe of the always-on books is ≈0 too.

## Files
`code/sector-etf/sector-short-reversal/`: `ic_scan.py`, `grid.py` (+`grid_results.csv`),
`ts_grid.py` (+`ts_grid_results.csv`), `events_vixscale.py`.
