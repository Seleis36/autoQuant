# turn-of-month-flow — BTC's turn-of-the-month premium as a standalone calendar sleeve

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance daily bars, 00:00 UTC), long/flat
**Status:** **Failed: the effect has decayed and reversed since 2023.**
- The last 3 plus first 3 calendar days of the month earned +50 bp/day IS (2017-09 → 2022), against +6 bp/day on other days (t 2.8).
- The pre-sample (BTC-USD 2014 → 2017-08) agrees: +44 vs +24 bp/day.
- OOS (2023+) the window earns **−4 bp/day vs +20** on other days. The TOM sleeve's Sharpe goes **1.10 IS → −0.25 OOS**.

---

## 1. Idea

The equity turn-of-month effect (Ariel 1987; Lakonishok & Smidt 1988) is usually explained by month-start cash inflows: salaries, pension contributions and dollar-cost-averaging buys. For BTC there is also the month-end CME/Deribit expiry.

- `bult` (2026-09-06) saw a turn-of-month Sharpe of 1.30 vs 0.42 mid-month OOS (2022+). It rejected TOM *as a tilt* because a tilt only shrank exposure.
- The open question was whether TOM works as its own cheap sleeve: 12 round trips a year, ≈ 2.4%/yr of cost at 10 bp/side, and uncorrelated in timing with trend.

## 2. Profile (`exp01_tom_profile.py`)

`tdm` counts calendar days from the month boundary: +1 is the first of the month, −1 the last day. The windows were fixed on IS; OOS is shown for confirmation.

| Window | IS bp/day (t) | IS rest | OOS bp/day (t) | OOS rest |
|---|---|---|---|---|
| [−3, +3] | **+50.5 (2.79)** | +6.2 | **−4.4 (−0.31)** | +19.6 |
| [−2, +3] | +51.3 (2.56) | +7.8 | −5.3 | +18.9 |
| [−1, +3] | +56.5 (2.55) | +8.6 | −9.6 | +18.6 |
| [+1, +3] | +59.3 (2.34) | +10.1 | +9.6 (0.43) | +15.5 |
| [−5, +5] | +35.8 (2.39) | +4.7 | −6.5 | +25.3 |

- Pre-sample check (yfinance BTC-USD, 2014-09 → 2017-08), [−3, +3]: +43.8 bp/day (t 2.25) vs +23.6.
- OOS, the last calendar day of the month is **−68 bp (t −2.3)**, against +48 bp IS.

## 3. By year and by regime (`exp02_yearly_and_trade.py`)

| Year | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| TOM − rest, bp/day | +66 | +45 | +57 | +12 | +79 | +29 | **−18** | **−58** | +13 | **−37** |

- Six positive years out of six before 2023, then three negative years out of four.
- Conditioning on trend does not rescue it. OOS, with the trend on, TOM earns +1 bp/day vs +30 bp/day on other days; with the trend off, −12 vs +5.

## 4. Costed sleeve (10 bp/side, from 2017-09)

| | full | IS | OOS | exposure |
|---|---|---|---|---|
| vol-scaled B&H | 0.81 | 0.61 | 1.11 | 0.70 |
| SMA50 × vol | 1.40 | 1.31 | 1.52 | 0.38 |
| **TOM [−3, +3] × vol** | 0.52 | **1.10** | **−0.25** | 0.14 |
| TOM × trend × vol | 0.60 | 0.98 | −0.04 | 0.07 |

The TOM sleeve's yearly Sharpe runs 3.33, 0.08, 1.61, 0.93, 1.97, −0.05 for 2017–2022, then 0.46, −0.68, 0.31, −1.21 for 2023–2026.

## 5. Verdict

- **Failed.** A textbook in-sample calendar effect, also present in the independent 2014–2017 pre-sample, that stopped working when the market's composition changed.
- A plausible reading: after 2023, and especially with the January-2024 spot ETFs, month-end flows are dominated by fund rebalancing and redemptions, not retail month-start DCA. That is consistent with the OOS −68 bp on the last day of the month, but 44 observations cannot establish it.
- Nothing here is deployable. The OOS "skip TOM" variant of the trend sleeve (1.58 vs 1.52) was seen only after looking at OOS and is **not** a claim.
- Configurations: 17 single-day cells and 10 windows for the profile, 5 costed sleeves.
