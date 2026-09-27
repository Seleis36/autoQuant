# coinbase-premium-xs — coin-specific Coinbase premium as a cross-sectional alt signal

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Failed

## 1. Idea

On BTC and ETH, a Coinbase-USD price above Binance-USDT (US spot demand arriving) predicts
positive returns at hourly-to-daily horizons (`spot-btc/coinbase-premium`,
`spot-eth/eth-venue-premium`, both deployed). The cross-sectional port: each alt's Coinbase premium
minus the same-day cross-sectional median over every coin quoted on both venues. Demeaning cancels
the USD/USDT basis, USDT depegs and any market-wide US premium, leaving *coin-specific* US demand.
Pre-registered sign: positive (long the coins US buyers are paying up for).

## 2. Data and setup
* `code/crypto-alts/shared/venues.py`: Coinbase Exchange 1d candles
  (`data/COINBASE_<COIN>USD_1d.parquet`, 60 of 78 candidates; most alts listed on Coinbase only
  from 2019-21) and Binance spot 1d. Both venues' daily bars close at D+1 00:00 UTC = the yfinance
  close stamped D. Rows with zero Coinbase volume or |premium| > 50 % are masked.
* Coverage in the PIT top-20: 1.4 names/day in 2018, 5.4 in 2019, 10 in 2020, 13-18 from 2021.
  Books trade only on days with ≥ 6 names, so **IS is effectively 2019-22**.
* XS premium is small: median 0, 5-95 % range −12…+15 bp.
* PIT top-20 universe, IS 2018-22 / OOS 2023-26, 10 bp/side, BTC-beta-hedged linear-rank books,
  tranche holds (`code/crypto-alts/shared/study.py`).

## 3. Results

**IC screen (`01_ic.py` → `ic_01.csv`, 15 features × 5 horizons).** The level has a small positive
IC in both halves at short horizons: `lvl1` → 1d 0.024 (t 2.5) IS / 0.015 (t 2.4) OOS; `lvl7` → 7d
0.007 IS / 0.024 OOS. Long-window levels are IS-only (`lvl30` → 30d 0.122, t 4.1 IS vs 0.016 OOS),
the same coin-fixed-effect pattern as taker flow. The z-score vs own history is ≈ 0 everywhere.

**Costed books (`02_books.py` → `books_02.csv`, 30 books): median −0.39 full / −0.46 IS / −0.25 OOS.**

| Book (hold 14) | k=1 | k=3 | k=7 | k=14 | k=30 |
|---|---|---|---|---|---|
| raw level full / IS / OOS | 0.28/0.41/0.08 | 0.08/0.30/−0.24 | 0.24/0.54/−0.20 | 0.53/0.96/−0.10 | 0.77/1.45/−0.23 |
| level − own 180d mean | −0.99/−1.40/−0.20 | −1.08/−1.39/−0.52 | −0.97/−1.32/−0.36 | −0.67/−1.07/−0.04 | −0.41/−0.50/−0.28 |

The small daily IC does not survive into a tradable book. Holds of 3-7 days turn over 40-95×/yr,
and holds of 14+ days dilute the signal. The raw 14-30d level repeats the in-sample coin fixed effect.

**Post-hoc: the premium measured against its own history has the *opposite* sign** (negative in all 15
configs in both halves). That contradicts the pre-registered hypothesis, so it was diagnosed rather
than adopted (`03_contrarian_diag.py`): the contrarian book (7d hold) earns 0.37-0.62 full /
0.84-1.04 IS / −0.05…−0.46 OOS. Its IS comes from one window. By year it is 2021 +2.86, 2022 −1.57,
2023 +0.16, 2024 −0.13, 2025 −0.94, 2026 −1.11, and ETC's May-2021 rally alone contributes +72 % of
cumulative P&L. Excluding each coin's first 180/365 days on Coinbase (a uniform rule against
listing artefacts) cuts it to 0.09-0.43 / −0.04-0.24 full. OOS gross ≈ 0 either way.

## 4. Verdict

**Failed.** Coin-specific Coinbase premia carry a statistically visible but economically tiny
(≈ 0.02 IC, 1-day) signal that cannot pay 10 bp. Its slower forms are either a coin fixed effect
(positive, IS only) or a single 2021 episode (contrarian, post hoc, gone OOS). The BTC/ETH venue
premium does not port to the alt cross-section at daily resolution. Variants: 75 IC cells + 30
books + 6 diagnostic books.

## 5. Files
`code/crypto-alts/coinbase-premium-xs/`: `00_fetch.py`, `common.py` (`premium_panel`), `01_ic.py`,
`02_books.py`, `03_contrarian_diag.py`, `ic_01.csv`, `books_02.csv`, `books_02_nets.parquet`.
