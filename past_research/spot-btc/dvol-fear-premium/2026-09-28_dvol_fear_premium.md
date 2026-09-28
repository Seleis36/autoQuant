# dvol-fear-premium — BTC variance risk premium (Deribit DVOL vs realized vol) as a timing signal

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance daily bars, 00:00 UTC), long/flat
**Status:** **Failed.**
- log(DVOL / RV30) has a positive **partial** IC (controlling for RV30 and the 20-day return) in both halves:
  - 1 day: +0.071 IS (t 2.0) and +0.062 OOS (t 2.3);
  - 7 days: +0.20 and +0.12.
- The raw quintile profile *flips* between halves, and no tradeable expression separates from the controls. The best OOS forms (1.57–1.65) sit on top of `SMA50 × vol` at 1.52 and an **RV-only control at 1.61**.
- The IS window (2021-10 → 2022-12) is a bear market in which every long-biased form is negative.

---

## 1. Idea and why BTC might differ from ETH

The variance risk premium (IV² − RV²) predicts equity index returns (Bollerslev, Tauchen & Zhou 2009): when implied variance is high relative to realized, investors are paying for crash insurance, and the risk premium shows up in the spot. For BTC:
- The `coinbase-premium` screen (2026-09-12) found the DVOL 90-day z-score significant in both halves (t 2.36 / 2.00) and flagged it as "worth a look".
- `spot-eth/dvol-vrp` failed because an RV-only control gave the same lift.

So the test was designed around that failure mode: every IV feature is residualised on realized vol before it is believed.

## 2. Data

- Deribit BTC DVOL, daily 2021-03-24 → 2026-09-27, refreshed with `code/spot-eth/dvol-vrp/fetch_dvol.py` (`currency="BTC"`). Hourly was also fetched.
- **Timing check:** the daily bar D close equals the hourly index value at D+1 00:00 UTC in all 2,014 days (max abs diff 0.0). DVOL bar D is therefore exactly known at the decision time of Binance bar D.
- RV30 / RV7 are computed from 5-minute Binance returns (`jump-variance-timing/features.py`).
- IS = 2021-04 → 2022-12 (640 days), OOS = 2023+ (1,362 days).

## 3. Screen (`exp01_screen.py`) — 17 features × 3 horizons, raw and partial IC

| Feature | h = 1 d partial IC IS (t) | OOS (t) | h = 7 d partial IS | OOS |
|---|---|---|---|---|
| log IV | +0.060 (1.6) | +0.074 (2.7) | +0.10 | +0.13 |
| RV30 (control) | +0.033 (0.9) | **−0.017 (−0.7)** | +0.17 | **−0.00** |
| VRP = IV² − RV30² | +0.077 (2.0) | +0.062 (2.3) | +0.23 (2.3) | +0.12 (1.7) |
| **log(IV/RV30)** | **+0.071 (2.0)** | **+0.062 (2.3)** | +0.20 (2.0) | +0.12 (1.7) |
| log(IV/RV30) z180 | +0.086 (2.1) | +0.072 (2.8) | +0.19 | +0.13 |
| VRP z180 | +0.079 (1.9) | +0.068 (2.5) | +0.19 | +0.12 |
| ΔIV 20 d | +0.028 | +0.058 (2.2) | +0.23 | +0.04 |

- Unlike ETH, realized vol alone has **no** OOS signal for BTC, and the IV-over-RV spread keeps a positive partial IC in both halves.
- This is the most consistent statistic found this session.
- log(IV/RV30) correlates +0.29 with the SMA50 trend state and +0.24 with the 20-day return. The leverage effect lowers RV in rallies, so the *raw* signal is partly trend.

## 4. Strategies (`exp02_backtest.py`, `exp03_quintiles_linear.py`) — 24 + 6 backtests

Evaluated 2021-10-01 → 2026-09 (after the z180 warm-up) at 10 bp/side.

| Expression | full | IS | OOS | turnover | exposure |
|---|---|---|---|---|---|
| vol-scaled B&H | 0.56 | −1.08 | 1.11 | 4 | 0.81 |
| **SMA50 × vol** | **0.97** | −1.28 | **1.52** | 19 | 0.43 |
| A 1{log IV/RV > 0} × vol | 0.31 | −1.47 | 0.94 | 18 | 0.60 |
| A 1{VRP z180 > 0} × vol | 0.70 | −0.95 | 1.30 | 24 | 0.43 |
| A hysteresis ±0.05 × vol | 0.51 | −1.11 | 1.11 | 9 | 0.60 |
| B VRP z180 gate on trend | 1.12 | −0.69 | 1.57 | 22 | 0.29 |
| C VRP z180 tilt on trend | 1.08 | −1.04 | 1.60 | 20 | 0.36 |
| linear rank(IV/RV) × trend × vol | 1.02 | −1.23 | **1.65** | 17 | 0.23 |
| top-2 quintiles × trend × vol | 1.06 | −0.84 | 1.57 | 20 | 0.18 |
| **control** C 1{RV z180 < 0} tilt | 1.02 | −1.15 | **1.61** | 17 | 0.37 |
| **control** B 1{RV z180 < 0} gate | 0.96 | −0.96 | 1.51 | 15 | 0.30 |

Next-day return by expanding-window quintile of log(IV/RV30), in bp:

| | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| IS | +16 | −15 | −7 | −43 | −34 |
| OOS | +10 | +6 | −6 | +20 | **+69** |

## 5. Verdict

- **Failed.** The partial-IC evidence is real in the statistical sense. BTC's IV-over-RV spread carries information that realized vol and recent return do not, in both halves.
- But the effect is not monotone and not stable in its raw form. The top quintile was the worst bucket in 2021–22 and the best since 2023. Every tradeable expression lands within ±0.1 of the trend baseline and of a realized-vol-only control, so the premium cannot be harvested separately from what the live sleeves already hold.
- The IS window is 15 months of bear market and cannot validate any threshold. The best OOS number (linear tilt, 1.65) was found after seeing OOS, among 30 expressions, and is not a claim.
- **For a future researcher:**
  - revisit when DVOL has a second full cycle (2027+);
  - the right test is a pre-registered partial-IC-weighted tilt on an existing sleeve, not a gate;
  - an options-based expression (sell variance when IV/RV is high) is the natural harvest but is not deployable on spot.
- Configurations: 102 screen cells (×2 raw/partial), 30 backtests.
