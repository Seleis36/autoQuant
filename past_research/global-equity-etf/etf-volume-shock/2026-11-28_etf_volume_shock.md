# etf-volume-shock — abnormal country-ETF dollar volume as a flow proxy

**Asset class:** `global-equity-etf` · **Short name:** `etf-volume-shock` · **Date:** 2026-11-28
**Status:** **Failed.** Abnormal volume carries no cross-sectional information (|IC| ≤ 0.02 at 5 and
21 sessions). The one consistent pooled slope (signed abnormal volume → −8 / −15 bp over the next
5 sessions, t −1.3 / −1.9) is a few basis points a week. Every tradeable form loses, even before costs
(gross −0.31 to +0.28).

## Idea

Shares-outstanding history, the direct ETF-flow measure of Brown, Davies & Ringgenberg (RF 2021),
is not available for free (yfinance `get_shares_full` returns 2016-21 snapshots only). Dollar
volume is the closest public proxy: creations and redemptions spike volume. Three priors compete:
* flows are non-fundamental demand that reverts (BDR) → fade signed volume;
* high volume attracts attention and earns a premium (Gervais-Kaniel-Mingelgrin 2001);
* high-volume returns reverse when trading is liquidity-driven, which index products are
  (Llorente-Michaely-Saar-Wang 2002).

## Data and signals (`01_volume_study.py`)

Nine country ETFs + EFA + EEM, 2001-06 → 2026-11, with yfinance volume, which is split-consistent (checked across EWJ's
2016 reverse split). The target is each ETF's SPY-hedged spread over sessions t+2 … t+1+h. The one-session
skip removes the non-synchronous 1-day reversal documented in `nonsync-overreaction`.
AV5 = log(5-session $vol / prior 63-session mean); SAV5 = AV5 × sign(hedged 5d return); RV5 =
hedged 5d return in vol units; RVxAV = RV5 × AV5.

| signal | IC 5d IS / OOS | pooled slope 5d IS / OOS (bp, t) | IC 21d IS / OOS |
|---|---|---|---|
| AV5 | 0.005 / −0.001 | −4.8 (−0.8) / +1.1 (0.1) | −0.005 / −0.021 |
| SAV5 | 0.018 / −0.016 | −8.2 (−1.3) / −15.0 (−1.9) | −0.004 / 0.008 |
| RV5 | −0.010 / −0.012 | −1.0 / −1.8 | −0.029 / 0.014 |
| RVxAV | 0.014 / −0.011 | −3.7 / −3.2 | 0.034 / 0.004 |
| RV5 on high-volume weeks only | −0.025 / −0.061 | −1.6 / −2.2 | −0.097 / −0.024 |

## Books (`02_books.py`; 5 bp ETFs, 1 bp SPY; full / IS / OOS net, gross full)

| book | net full | IS | OOS | gross full |
|---|---|---|---|---|
| fade extreme signed volume, \|z\| > 1.5, 5 sessions after a 1-session skip | −0.61 | −0.28 | −0.80 | −0.24 |
| same, \|z\| > 2.0 | −0.53 | −0.13 | −0.73 | −0.31 |
| weekly cross-sectional rank fade of SAV5 | −0.44 | −0.58 | −0.30 | 0.11 |
| aggregate ex-US $vol shock signed by the basket return, fade basket vs SPY weekly | 0.01 | 0.10 | −0.08 | 0.28 |

## Why it fails

Country-ETF volume is dominated by hedging and macro trading (EWZ, FXI and EEM are options-hedging
vehicles), not by the slow-moving allocation flows BDR measure from shares outstanding. Without
creation/redemption data the proxy is mostly noise, and the reversal in it is far smaller than a
5 bp round trip.

## Variants

5 signals × 2 horizons × 3 periods × 2 forms = 60 tests and 4 books.

Code: `code/global-equity-etf/etf-volume-shock/` (`01_volume_study.py`, `02_books.py`).
