# overnight-sentiment-reversal — sectors with high recent overnight returns under-perform

**Status: Failed as a standalone strategy** (net Sharpe 0.52 full / 0.41 OOS). It is the one
genuinely *sector-specific* edge found in this session and is carried as the `ON` sleeve of
[`sector-sleeve-blend`](../sector-sleeve-blend/2026-09-25_sector_sleeve_blend.md).
Asset class `sector-etf`. Date 2026-09-25.

## Idea
Aboody, Even-Tov, Lehavy & Trueman (2018, JFQA) show that a stock's overnight return
(close → next open) proxies firm-specific investor sentiment: retail orders cluster at the open,
and stocks with high overnight returns subsequently under-perform. Lou, Polk & Skouras (2019)
document a persistent "tug of war" between overnight and intraday clienteles. The effect appeared
unprompted in a characteristic screen (`char_screen.py` in this idea's code folder): it was the
only one of 15 sector characteristics with the same-signed monthly IC in both halves
(63-day overnight: −0.094 IS, t −3.3 / −0.056 OOS, t −1.7), while every momentum variant was ≈0.

## Setup
Common sector-etf setup (IS 1999-2014 / OOS 2015-2026, 2 bp/side, weights at close *t* earn
*t+1*, SPY hedge to beta 0). Overnight return = log(Open_t / Close_{t−1}) from yfinance
auto-adjusted bars — both prices are known at the close of *t*. Dividends do not leak into it:
auto-adjustment scales the prior close, so the ex-date gap is removed.

## Evidence
### IC map (`ic_map.py`)
Look-backs 42-252 days × horizons 21-63 days all carry negative IC in both halves, e.g.
k = 63 / h = 63: −0.089 IS, **−0.125 OOS (t −2.7)**; k = 252 / h = 63: −0.117 / −0.123. One-day
horizons are ≈0 — it is a slow sentiment effect, not a gap reversal. Intraday returns carry the
opposite sign at long look-backs (the tug of war), but weakly.

### Book grid (`book_grid.py`, 48 cells)
−overnight (ON) or intraday-minus-overnight (TUG) × k ∈ {42, 63, 126, 252} × linear/tercile ×
monthly / 21-day / 63-day tranches. **All 48 cells positive full-sample, 47 of 48 positive OOS**;
median 0.32 full / 0.31 OOS; ON-only median 0.38 / 0.32, worst 0.24 / 0.27. Best IS cell
`ON42|terc|t21` 0.69 IS → 0.33 OOS. TUG is weaker than ON alone.

### Pre-declared refinement (`refine.py`, 18 cells)
Raw / vol-normalised / beta-residual overnight × each look-back and the **equal-weight rank
ensemble over k ∈ {21, 42, 63, 126, 252}** (no look-back picking). Reference = raw ensemble:

| Book | Sharpe full | IS | OOS | CAGR | vol | MaxDD | t_NW | turnover |
|---|---|---|---|---|---|---|---|---|
| **raw ENS (reference, `strategy.py`)** | **0.52** | 0.60 | **0.41** | 2.8 % | 5.6 % | −9.6 % | 3.03 | 8.8×/yr |
| volz ENS | 0.50 | 0.56 | 0.41 | 2.6 % | 5.4 % | −13.6 % | 2.88 | 8.7× |
| residual ENS | 0.40 | 0.47 | 0.30 | 2.0 % | 5.4 % | −14.0 % | 2.26 | 8.5× |

### Diagnostics (`diagnose.py`, `robustness.py`, `conviction.py`, `spy_ts.py`)
* **Not a static tilt**: the time-invariant part of the weights is 2 % of their second moment;
  a book on each sector's expanding-mean overnight drift alone earns 0.10. The time-varying
  part alone earns 0.44.
* **Opening prints are clean**: < 0.5 % of days have Open = previous Close in any era.
* Positive in 20 of 27 years; 3-year rolling Sharpe median 0.57, negative in 8 % of windows.
* Costs: 0.55 at 0 bp, 0.47 at 5 bp, 0.40 at 10 bp (turnover only 8.8×/yr).
* Market-neutral: beta −0.015, correlation to SPY −0.05.
* Stationary block bootstrap (21 d): 5 / 50 / 95 % = 0.25 / 0.52 / 0.80; P(Sharpe > 1) = 0.4 %.
* DSR 0.65 at N = 66 trials of this idea, 0.54 at N = 150.
* vectorbt re-computation: Sharpe 0.53 vs 0.53, daily correlation 1.000.
* Scaling gross by cross-sectional dispersion (bet more when sentiment diverges): 0.45 — worse.
* Market level: SPY's own past overnight return does not time SPY (|t| < 1 IS).
* ETF-flow version (Brown, Davies & Ringgenberg 2021) not testable: yfinance shares-outstanding
  history for the SPDRs covers 2016-2021 only.

## Verdict
~72 books. A robust, cost-insensitive, market-neutral sentiment-reversal effect that survives out
of sample in every construction tried, but at **Sharpe ≈0.5 with 5-6 % vol** it is too weak to
trade alone (P(Sharpe > 1) < 1 %). Binding constraint: **breadth** — 9-11 sectors give an
IC of ~0.05-0.1 very little room. It is uncorrelated with every other sleeve found (|ρ| ≤ 0.1), so
its value is as a diversifying sleeve, which is how `sector-sleeve-blend` uses it.

## Files
`code/sector-etf/overnight-sentiment-reversal/`: `char_screen.py` (15-characteristic screen that surfaced it), `ic_map.py` (+csv), `book_grid.py` (+csv; its
returns parquet is regenerated, not committed), `diagnose.py`, `refine.py` (+csv), `spy_ts.py`, `conviction.py`,
`robustness.py`, `strategy.py` (`target_weights(close, open_)` — the reference ENS book).
