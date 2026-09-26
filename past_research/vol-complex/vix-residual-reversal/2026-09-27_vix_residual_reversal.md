# vix-residual-reversal — fading the vol move that the equity move does not explain

**Status: Failed.** The VIXY return left over after its rolling SPY beta has no next-day
predictability (Spearman IC −0.03…+0.04 IS and OOS). The re-framings also fail:
* today's SPY move → tomorrow's VIXY: best 0.58 full, IS 0.41, negative after SPY hedging;
* a VIXY-vs-VIXM curve residual: gross Sharpe ≈ 0, net −1.1…−1.8 at 214× turnover.

Nineteen trading configurations plus IC screens were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

VIX futures react to equity moves with a stable spot-vol beta (VIXY ≈ −3.9 × SPY, 63-day rolling,
IQR −4.6…−3.1). A day on which vol moves *more or less than SPY implies* reflects non-fundamental
flow:
* hedging demand ahead of events;
* leveraged-ETP end-of-day rebalancing (UVXY/SVXY buy futures on up days, sell on down days);
* dealer gamma.

That flow should mean-revert. The trade fades the residual in VIXY, SPY-hedged so that it is a pure
vol-vs-equity relative-value bet with no short-vol carry. VIXY, VIXM and SPY all close at 16:00 ET,
so there is no index-timing issue.

## 2. Results

### 2.1 IC screen (01_screen.py)

Residual z = (r_VIXY − β_{t−1} · r_SPY) / σ_63, summed over 1/2/3/5 days, against next-day VIXY and
SPY-hedged VIXY returns:

| target | IS IC (1/2/3/5 d) | OOS IC (1/2/3/5 d) |
|---|---|---|
| next-day VIXY | +0.03 / +0.04 / +0.03 / 0.00 | −0.02 / −0.01 / −0.01 / 0.00 |
| next-day hedged | −0.02 / 0.00 / +0.01 / +0.03 | −0.01 / −0.01 / −0.01 / −0.03 |

The quintile means are non-monotone noise. By contrast, the **raw** SPY move predicts tomorrow's
VIXY with IC +0.06 IS / +0.08 OOS (after an SPY drop, VIXY tends to give back), and the raw VIXY move
reverses slightly (−0.03 / −0.06).

### 2.2 Re-framings (02_reframe.py, 03_curve_momentum_check.py), net 5 bp (7 bp with VIXM)

| rule | full | IS | OOS | note |
|---|---|---|---|---|
| short VIXY next day after SPY z < −0.5 | 0.58 | 0.41 | 0.73 | 85× turnover, skew −3.2 |
| … z < −1 / −1.5 / −2 | 0.22 / 0.03 / 0.05 | | | the effect is not about big drops |
| … z < −0.5 and contango (lag 1) | −0.03 | | | |
| linear long/short clip(z_SPY/2) | 0.38 | 0.31 | 0.43 | 129× turnover |
| long VIXY after SPY z > 1 | −0.01 | 0.30 | −0.27 | |
| SPY-hedged short after z < −1 / −1.5 | −0.65 / −0.55 | | | hedge removes everything |
| VIXY-vs-VIXM residual fade, 1/3/5-day | −1.79 / −1.13 / −1.23 | | | **gross 0.13 / −0.05 / −0.43** |

The large negative curve-fade numbers are not residual momentum. The residual's AC(1) is −0.07
(OOS −0.12), which is the right sign for a fade. But the gross edge is about zero, and the book's 8 %
volatility cannot carry 117–214× annual turnover. The unhedged "short after SPY down day" rule
(0.58) is a high-turnover repackaging of short-vol carry: it loses its edge when hedged, and it
overlaps with `term-structure-carry`'s failed next-day-reversal test.

## 3. Conclusion

At the daily close, the vol-complex move relative to the equity move is not predictable. Whatever
flow drives the residual (ETP rebalancing, hedging) is absorbed within the day, beyond daily
resolution. Only the carry component survives, and that is already documented. Do not revisit on
daily bars.

## 4. Files

`code/vol-complex/vix-residual-reversal/`: `01_screen.py` (residual IC screen),
`02_reframe.py` (SPY-move rules, hedged versions, curve residual), `03_curve_momentum_check.py`
(autocorrelation, lead-lag, gross-vs-net check). No alpha spec.
