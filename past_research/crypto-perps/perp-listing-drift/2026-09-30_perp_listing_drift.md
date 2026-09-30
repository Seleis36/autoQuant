# Perp-listing drift — short spot after a Binance USDT-M perp listing (`perp-listing-drift`, crypto-perps)

**Date:** 2026-09-30 · **Status: Failed** (regime-concentrated). The best cell earns net Sharpe
1.28 full / 0.88 IS / 1.53 OOS. **Without 2025 it earns 0.53.** Median calendar-year Sharpe 0.14.
It was the best of 28 portfolio cells.

## 0. Idea

When Binance lists a USDT-M perpetual on a coin, two things change at once:

- **Pessimists get a cheap, levered short** for the first time. Miller (1977) and Hong & Stein
  (2003): relaxing a short-sale constraint lowers an overpriced asset. The CME BTC futures listing
  of December 2017 is the standard crypto example.
- **The listing is a hype event.** In 2024-25 traders called Binance perp listings a
  "death trap" (ai16z −84 %, VVV −67 % after listing, The Block 2025-02).

Hypothesis: spot drifts down after the perp listing. Trade it as β-hedged spot shorts, which the sim
book can price through Binance spot quotes with an open universe.

## 1. Data and events

`code/crypto-perps/perp-listing-drift/fetch_listings.py`:

- **Every USDT-M perpetual in `/fapi/v1/exchangeInfo`:** 658, including 130 SETTLING (delisted) ones.
- **First funding settlement per perp:** REST `fundingRate?startTime=1`. Note that `startTime=0` is
  silently treated as "not sent" and returns the *latest* rows. The first run hit this bug and was
  cleaned up.
- **Perp daily klines:** `data/BINANCE_<SYM>_PERP_1d.parquet`.
- **Spot daily klines:** `data/BINANCE_<BASE>USDT_1d.parquet` via `crypto-alts/shared/venues.py`,
  which falls back to the archive for delisted pairs.
- **Summary table:** `data/BINANCE_PERP_LISTINGS.parquet`.

**Event definition** (pre-registered in `common.py`):
- Listing time = min(onboardDate, first funding). D0 = its UTC day.
- One event per coin, the first perp. Multiplier contracts map to the spot base (1000PEPE → PEPE).
- Crypto underlyings only.
- **Tradeable only if Binance spot has a bar on D0.**
- Entry at the close of D0; the perp is already trading and was announced earlier.

361 events qualify: IS (D0 ≤ 2022) 132, OOS 229. By year: 2020 70, 2021 42, 2022 18, 2023 79,
2024 87, 2025 58, 2026 5.

Contracts that have vanished from exchangeInfo entirely cannot be recovered. They are mostly
collapsed coins, so the bias is against the short.

## 2. exp01 — event study

Abnormal return = coin − BTC, β = 1. CAR in %, (t), median.

| window | IS (n = 132) | OOS (n = 229) |
|---|---|---|
| −30 … −1 | **+60.7 (7.7)**, med +36.4 | **+51.9 (8.1)**, med +33.2 |
| −5 … −1 | +30.3 (6.3) | +39.1 (7.8) |
| day 0 | +3.4 (2.0) | +12.3 (6.5) |
| +1 … +30 | −4.7 (−1.1), med −13.8 | **−15.7 (−4.5)**, med −21.0 |
| +1 … +60 | −4.7 (−0.7), med −9.0 | −26.1 (−6.6), med −34.9 |
| +1 … +90 | −1.4 (−0.2), med −14.4 | **−35.6 (−8.5)**, med −42.1 |

- Coins run up 50–60 % into the listing, which is how Binance picks them.
- They then fall. Seventy percent are below BTC 90 days later.
- The IS means are dragged up by a right tail in the 2021 bull market. The IS medians are negative.

**By spot age at the perp listing, split by period** (CAR +1…+30 mean / median):

| age | IS | OOS |
|---|---|---|
| **< 30 days** (spot and perp launched together) | **−15.6 % / −29.4 %** (n 38) | **−19.7 % / −27.4 %** (n 123) |
| 30–180 days | −1.2 % / −13.8 % (29) | −0.4 % / −14.5 % (10) |
| 180 days – 2 years | +1.7 % / −2.4 % (56) | −11.6 % / −19.0 % (28) |
| > 2 years | −10.5 % / −15.2 % (9) | −12.6 % / −19.6 % (68) |

Only new tokens decline in both periods. The effect in old coins exists only after 2023.

**By year** (CAR +1…+30):

| 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| −10.6 % | −0.6 % | +6.3 % | −2.8 % | −9.3 % | **−43.9 %** | −4.9 % |

**By pre-listing run-up tercile** (+1…+30): low −1.5 %, mid −9.5 %, high −7.4 %. It is not a clean
"bigger pump, bigger dump".

## 3. exp02 — the tradeable basket (16 cells)

- Each event: short 5 % of capital in the coin's spot from the close of D0 + delay, long 5 % BTC,
  for H days.
- Gross short capped at 1.0. 10 bp/side.
- Funding line: what a *short-perp* implementation would have received or paid. The sim book books
  spot only.

| cell | full | IS | OOS | MaxDD | avg gross |
|---|---|---|---|---|---|
| H14 d0 | 0.82 | 0.14 | 1.29 | −24 % | 0.20 |
| H30 d0 | 1.13 | 0.38 | 1.65 | −36 % | 0.44 |
| H30 d1 | 1.12 | 0.53 | 1.54 | −35 % | 0.44 |
| H60 d0 | 1.11 | 0.20 | 1.82 | **−66 %** | 0.86 |
| H90 d0 | 0.99 | −0.08 | 1.91 | −78 % | 1.20 |
| H30 / H60 / H90, inverse-vol sizing | 0.29 / 0.52 / 0.32 | ≤ −0.09 | 0.66–1.14 | | |
| H60 d0 at 20 / 30 bp | 1.08 / 1.06 | | | | |
| H60 d0 + short-perp funding | 1.08 | 0.36 | 1.64 | −60 % | |

**H60 d0 by year:**

| year | return | Sharpe |
|---|---|---|
| 2020 | +99 % | 1.87 |
| **2021** | **−67 %** | −1.55 |
| 2022 | −7 % | −0.42 |
| 2023 | +45 % | 1.09 |
| 2024 | +53 % | 1.06 |
| **2025** | **+186 %** | 3.90 |

- Short-perp funding was +6.7 %/yr in IS but **−7.5 %/yr OOS**: new listings are crowded shorts.
- Inverse-vol sizing kills the edge because the most volatile new coins are the ones that fall.
- The 2021 bull market squeezed every short: −67 %.

## 4. exp03 — re-framings (12 cells, declared before running)

| cell | full | IS | OOS | MaxDD | worst year |
|---|---|---|---|---|---|
| all events H30 / H60 | 1.13 / 1.11 | 0.38 / 0.20 | 1.65 / 1.82 | −36 / −66 % | −12 / −67 % |
| A: spot age < 30 d, H30 / H60 | 1.14 / 1.18 | 0.65 / 0.68 | 1.44 / 1.49 | −26 / −28 % | −9 / −17 % |
| B: squeeze stop at 1.5× entry, H30 / H60 | 1.14 / 1.26 | 0.48 / 0.55 | 1.59 / 1.78 | −31 / −46 % | |
| C: no alt season (EW alt/BTC < 200d SMA), H30 / H60 | 1.17 / 1.10 | 0.20 / −0.42 | 1.68 / 1.92 | −35 / −64 % | |
| D: pre-listing run-up > 0, H30 / H60 | 0.61 / 0.73 | 0.02 / 0.03 | 1.18 / 1.57 | | |
| **A + B, H30 / H60** | **1.24 / 1.28** | **0.84 / 0.88** | **1.50 / 1.53** | **−20 / −24 %** | −2 / −5 % |

**A + B H60 by year** (Sharpe): 2020 1.93, 2021 0.10, 2022 −1.52, 2023 0.25, 2024 0.36,
**2025 3.82** (+155 %), 2026 0.26.

## 5. exp04 — honesty checks on A + B

| | Sharpe | **ex-2025** | CAGR ex-2025 | MaxDD | years > 0 | median year SR | DSR (N = 28) | funding %/yr |
|---|---|---|---|---|---|---|---|---|
| H30, 10 bp, spot | 1.24 | **0.45** | 6.0 % | −20 % | 5/7 | 0.29 | 0.85 | −2.6 |
| H30 + short-perp funding | 1.09 | 0.38 | 4.8 % | −19 % | 5/7 | 0.30 | 0.75 | |
| H60, 10 bp, spot | 1.28 | **0.53** | 8.8 % | −24 % | 5/7 | 0.14 | 0.89 | −3.0 |
| H60 + short-perp funding | 1.15 | 0.48 | 7.8 % | −23 % | 5/7 | 0.23 | 0.82 | |
| H60, 30 bp | 1.24 | 0.49 | | | | | | |

- Correlation with `retail-crowding-xs`: **0.05**.
- Excluding 2025 is not used to claim anything. It is the concentration test: removing the single
  best year leaves 0.45–0.53.

## 6. Verdict

**Failed.** There is a real, large event effect: new tokens that get a perp alongside their spot
listing fall 15–20 % against BTC within a month, in both periods. But as a book:

1. **The P&L is two years.** 2020 (DeFi-summer tokens) and 2025 (the low-float / high-FDV token
   collapse) make the Sharpe. 2021-24 are flat to negative, and the median year is 0.14.
2. **The best cell is best-of-28.** It combines two filters (age and stop); each alone keeps IS
   at 0.55–0.68.
3. **A real implementation is worse.** Shorting a two-week-old token means shorting its perp and
   paying its funding (−3 %/yr at A+B, −7.5 %/yr on all events). Spreads on new listings are wider
   than the 10 bp charged; 30 bp costs a little.
4. **The tail is squeezes.** 2021 lost 67 % unfiltered.

**For the next researcher:** new-token supply is a live phenomenon. If a longer stretch of post-2025
data shows the young-token short holding up outside a crash year, it is uncorrelated (0.05) with the
other perps sleeve. It is expressible in the sim book with `open_universe` and Binance spot quotes.
The event feed is `exchangeInfo.onboardDate`, which is live.

## 7. Files

```
code/crypto-perps/perp-listing-drift/fetch_listings.py   listings, first funding, perp + spot klines
  common.py                     pre-registered event rule, loaders
  exp01_event_study.py (+ exp01_events.csv, exp01_paths.parquet)
  exp02_portfolio.py   (+ exp02_results.csv)
  exp03_reframe.py     (+ exp03_results.csv, exp03_events.csv)
  exp04_check.py
data/BINANCE_PERP_LISTINGS.parquet, data/BINANCE_<SYM>_PERP_1d.parquet (658 perps),
data/BINANCE_<BASE>USDT_1d.parquet, data/<SYM>_fundingRate.parquet (first <= 1000 stamps for new perps)
```

Variants: 16 (exp02) + 12 (exp03) portfolio cells, plus the exp01 splits.
