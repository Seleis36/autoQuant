# jump-variance-timing — realized semivariance, jump and skewness measures as BTC timing signals

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance 5-minute returns from the 1m store; daily decisions at 00:00 UTC), long/flat
**Status:** **Failed.**
- The realized higher moments carry a faint 1-day signal. Positive-jump share over 3 days predicts lower next-day returns: IC −0.045 IS (t −2.1), −0.044 OOS (t −1.6).
- The signal is too small for daily turnover. At 10 bp/side, every IS-selected expression is below the plain `SMA50 × vol` baseline (1.26 full / 1.05 IS / 1.52 OOS).
- The best standalone, the PJV_3 veto, is 0.88 full / 0.81 / 0.99. At **zero cost** it is 1.09.

---

## 1. Idea

Lee & Wang (JFQA 2024, *Variance decomposition and cryptocurrency return prediction*) show that across coins, **jump-robust and positive-jump variance predict lower future returns**, while negative-jump variance does not. Two related findings point the same way:
- Bollerslev, Li & Zhao (2020): good-minus-bad semivariance (relative signed jump) predicts lower returns.
- Amaya et al. (2015): realized skewness predicts lower returns.

All three are lottery-demand stories: investors overpay after upside jumps. None of the live spot-BTC sleeves looks at the intraday *shape* of returns, only at the price level, trend and daily vol. So the question is whether these measures time BTC itself.

## 2. Features (`features.py`)

Daily sums come from 5-minute log returns; returns spanning a data gap are dropped. They are aggregated over trailing L = 1, 3, 7, 14 days, and a feature stamped D uses only day D and earlier.

| Feature | Definition |
|---|---|
| RV | log realized variance |
| RVz | RV relative to its 180-day mean |
| RSJ | relative signed jump, (RS⁺ − RS⁻) / RV |
| RSK | realized skewness, √N Σr³ / RV^1.5 |
| RKU | realized kurtosis |
| JV | jump share, max(RV − BPV, 0) / RV |
| PJV / NJV | jump share on days whose largest 5m move was up / down |
| ret | same-window return (control) |

## 3. Screen (`exp01_screen.py`) — 36 features × 3 horizons × raw and partial IC

- Rank IC of each feature against the forward 1 / 3 / 7-day return, on non-overlapping samples.
- A **partial IC** controls for the same-window return. RSJ and RSK are mechanically correlated with past return, and short-term BTC reversal is already known and does not pay.
- IS = 2017-09 → 2022, OOS = 2023+.

| Feature, h = 1 d | IC IS (t) | IC OOS (t) | partial IS / OOS t |
|---|---|---|---|
| ret_1 (reversal) | −0.053 (−2.2) | −0.038 (−1.3) | — |
| RSK_1 | −0.048 (−2.2) | −0.004 (−0.1) | −1.0 / +1.0 |
| RSK_3 | −0.045 (−2.1) | −0.027 (−1.0) | −2.2 / −1.0 |
| **PJV_3** | **−0.045 (−2.1)** | **−0.044 (−1.6)** | −2.1 / −1.6 |
| NJV_3 | +0.048 (2.2) | +0.001 (0.0) | 2.2 / −0.1 |
| RVz_1 | +0.043 (2.0) | +0.020 (0.8) | 1.8 / 0.7 |

- IS→OOS Spearman of the t-stats is **0.59 at h = 1**, then 0.05 at 3 d and −0.16 at 7 d. The information, such as it is, lives at the 1-day horizon.
- The longer horizons are noise. RSK_14 at 7 days goes −0.02 IS → +0.15 OOS.
- Lee & Wang's sign holds: PJV (upside-jump share) is bearish in both halves and NJV is not. But the magnitude is an IC of 0.045.

## 4. Strategy expressions (`exp02_backtest.py`) — 38 backtests

- Selection used IS only: every feature with |t_IS| ≥ 2 at h = 1, six in all, signed by its IS IC.
- Real-time standardisation is a rolling 365-day percentile rank.
- The composite is the mean of the six, also run smoothed with a 3- or 7-day EMA to cut turnover.
- Start 2018-03, 10 bp/side, daily Binance bars.

| Expression | full | IS | OOS | turnover/yr |
|---|---|---|---|---|
| vol-scaled B&H | 0.72 | 0.44 | 1.11 | 4 |
| **SMA50 × vol (baseline)** | **1.26** | **1.05** | **1.52** | 17 |
| A composite, standalone | 0.31 | 0.53 | −0.02 | 103 |
| A composite @ 0 bp | 0.67 | 0.82 | 0.45 | 103 |
| A composite EMA3 | 0.46 | 0.61 | 0.24 | 63 |
| B composite EMA3, gate on trend | 0.93 | 1.19 | 0.54 | 37 |
| C composite EMA3, tilt on trend | 1.23 | 1.19 | 1.28 | 27 |
| **A PJV_3 alone** | 0.88 | 0.81 | 0.99 | 60 |
| A PJV_3 @ 0 bp | 1.09 | 0.97 | 1.25 | 60 |
| C PJV_3 tilt | 1.28 | 1.15 | 1.46 | 27 |

- The gate (B) buys IS Sharpe and loses OOS every time: the EMA7 composite goes 1.21 → 0.27.
- The tilt (C) is never more than +0.02 over the baseline on the full sample, and lower OOS.

## 5. Verdict

- **Failed.** A 1-day IC of 0.04–0.05 on a 3.5%-a-day asset is ≈ 10–15 bp of edge per position change, the same size as one side of the cost. Daily turnover of 60–140×/yr consumes it.
- The 3–14-day aggregations that would trade less have no stable sign. This matches the repo's standing observation that BTC price-derived timing features lose their IS ranking OOS. Intraday return *shape* turns out not to be different enough information from the price path.
- Configurations: 216 screen cells, 38 backtests.
- `features.py` caches the daily moment table as `_daily_moments.parquet` next to the code. It is a derived table, not market data, is rebuilt in ~3 s, and is not committed.
