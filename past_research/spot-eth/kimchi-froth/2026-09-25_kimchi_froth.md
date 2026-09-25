# kimchi-froth — the Korean ETH premium as a retail-froth signal

**Date:** 2026-09-25
**Asset class:** spot-eth (Binance ETHUSDT daily at 00:00 UTC; Upbit KRW-ETH/KRW-BTC daily; USDKRW, 2018-01 → 2026-09-24)
**Short name:** `kimchi-froth`
**Status:** **Failed**

## TL;DR

The hypothesis: Korean retail paying a premium on Upbit (the "kimchi premium", sustained by capital controls) marks froth, so a high premium should precede weak ETH returns. Alternatively, a *rising* premium signals retail inflow and positive short-run returns. The results:

- The **premium level** is contrarian at a 30-day horizon in both halves: IC **0.15 IS / 0.25 OOS**, and nearly identical using BTC's premium. With overlapping 30-day windows that is t ≈ 1.3 / 1.4, not significant in either half. At 1–7 days it is ~0.
- The **z-scored** premium flips sign between halves (30d IC −0.07 IS / +0.20 OOS). Premium *changes* carry nothing (|IC| ≤ 0.04).
- **Froth vetoes do not monetise it.** Flattening the live trend filter when the premium exceeds 3 / 5 / 8% gives IS 1.01 / 0.90 / 0.98 against 1.09 ungated, and OOS 1.20 / 1.32 / 1.50 against 1.20. On `eth-venue-premium` they give OOS 1.11 / 1.49 / 1.57 against 1.49, and cut IS every time. z-score vetoes hurt IS more (0.78–0.94). High-premium stretches (104 days above 5% in 2021, 61 in 2024) sit inside bull runs that kept going for weeks.

## Data

- `data/UPBIT_KRWETH_d.parquet`, `data/UPBIT_KRWBTC_d.parquet`: Upbit public daily candles, aligned to 00:00 UTC (`candle_date_time_utc`), 2017-09-25 →. Fetcher: `code/spot-eth/kimchi-froth/fetch_upbit.py`.
- USDKRW from yfinance `KRW=X` (flat cache). Per DATA.md, the row stamped D is the ~00:00 UTC rate on D. It is used at the D+1 00:00 close, i.e. 24 h stale, which is conservative (FX moves < 1%/day against premium swings of several %).
- `kp_D = Upbit close_D / (Binance ETHUSDT close_D × USDKRW row D) − 1`.
- ETH premium by year (mean / max / min %): 2017 7.4 / 42 / −3 · 2018 4.0 / **58** / −4 · 2019 0.3 / 8 / −4 · 2020 −0.4 / 12 / −5 · 2021 4.1 / 21 / −6 · 2022 1.6 / 9 / −3 · 2023 1.7 / 7 / −1 · 2024 2.8 / 12 / −1 · 2025 1.9 / 10 / −3 · 2026 0.0 / 5 / −4.

## 1. ICs (`01_kimchi_signals.py`)

| Signal | 1d IS | 7d IS | 30d IS | 1d OOS | 7d OOS | 30d OOS |
|---|---|---|---|---|---|---|
| −kp (level, contrarian) | −0.019 | 0.061 | **0.151** | 0.000 | 0.070 | **0.245** |
| −kp BTC | −0.018 | 0.062 | 0.152 | 0.002 | 0.072 | 0.247 |
| −kp z (365d) | −0.065 | −0.049 | −0.070 | −0.014 | 0.034 | 0.202 |
| −(kp ETH − kp BTC) | −0.042 | −0.015 | −0.056 | −0.047 | −0.020 | −0.033 |
| Δkp 7d (inflow) | 0.040 | 0.035 | 0.019 | 0.024 | 0.015 | −0.036 |

## 2. Froth gates (`01_kimchi_signals.py`, `02_level_gates.py`, 20 configs)

| Base | Gate | Full | IS | OOS | MDD | share flat |
|---|---|---|---|---|---|---|
| trend filter | none | 1.12 | 1.09 | 1.20 | −48% | 0 |
| trend filter | kp ≤ 3% | 1.07 | 1.01 | 1.20 | −40% | 22% |
| trend filter | kp ≤ 5% | 1.03 | 0.90 | 1.32 | −46% | 9% |
| trend filter | kp ≤ 8% | 1.14 | 0.98 | 1.50 | −48% | 3.5% |
| trend filter | kp z ≤ 1 | 0.93 | 0.78 | 1.28 | −52% | 12% |
| trend filter | kp z ≤ 2 | 1.02 | 0.91 | 1.28 | −50% | 5% |
| vol-scaled B&H | none / kp ≤ 3% / 5% / 8% | 0.60 / 0.66 / 0.40 / 0.53 | 0.67 / 0.69 / 0.38 / 0.51 | 0.44 / 0.60 / 0.43 / 0.58 | | |
| eth-venue-premium | none / kp ≤ 3% / 5% / 8% | 1.35 / 1.13 / 1.25 / 1.34 | 1.29 / 1.13 / 1.14 / 1.23 | 1.49 / 1.11 / 1.49 / 1.57 | | |

## Verdict

**Failed.** The binding constraint is **timing resolution**. The premium level knows, loosely, that the next month is worse when Korean retail is euphoric, but euphoria lasts, and a veto takes the book out of the best weeks of every bull run. Nothing is consistent across halves at the monthly horizon, where the few independent observations (~100 months) cannot confirm an IC of 0.15–0.25.

**Variants tried:** 21 IC cells + 20 gates.

## Files

- `code/spot-eth/kimchi-froth/fetch_upbit.py`
- `code/spot-eth/kimchi-froth/01_kimchi_signals.py`, `02_level_gates.py`
