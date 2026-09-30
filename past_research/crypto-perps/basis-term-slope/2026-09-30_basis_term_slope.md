# Quarterly basis term slope — dated-futures carry as a BTC/ETH timer (`basis-term-slope`, crypto-perps)

**Date:** 2026-09-30 · **Status: Failed.** The annualised quarterly basis is a weak trend proxy with a
positive IC, not a crowding signal. Its slope over perp funding carries nothing. No pre-declared rule
beats SMA50 × inverse-vol.

## 0. Idea

The perp funding rate prices leverage demand over the next 8 hours. A dated quarterly future prices
it over the next ~3 months, so the gap between the two is a term premium.

Hypothesis: a steep term structure (dated basis far above funding) means long demand is being paid
for in advance and is crowded, so hold less. Deep backwardation means fear. The perp-funding version
of this timing is dead (spot-btc `coinbase-premium` screen, `funding-xs-crowding`). The dated
contract had not been tried.

## 1. Data

- **Futures:** `code/crypto-perps/basis-term-slope/fetch_quarterly.py` pulls Binance **COIN-M**
  `continuousKlines` (CURRENT_QUARTER and NEXT_QUARTER, keyless) into
  `data/BINANCE_{BTCUSD,ETHUSD}_{CQ,NQ}_1d.parquet`.
  - History from 2020-06 / 2020-07. The USDT-M quarterlies only start 2021-02.
- **Roll check:** the expiry-day row (e.g. Friday 2024-03-29) already carries the next contract. The
  basis jumps from 0.14 % to 6.8 %, and the new CQ equals the previous NQ. So the expiry of a close
  at D+1 00:00 is the first quarterly expiry after that instant (last Friday of Mar/Jun/Sep/Dec,
  08:00 UTC).
- **Annualised basis:** log(F / Binance spot) × 365 / days to expiry. Use the current quarter when
  ≥ 30 days remain, otherwise the next quarter.
- **Funding:** trailing 7-day mean of daily USDT-M funding, settlements up to D 16:00, × 365.
- **Slope:** basis − funding.
- **z-scores:** 365-day. IS 2020-07 → 2023-12, OOS 2024+.

Median annualised BTC basis by year:

| 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| 10.9 % | 12.1 % | 1.7 % | 5.4 % | 10.6 % | 6.3 % | 2.8 % |

ETH is similar.

## 2. exp01 — ICs and rules

Spearman IC of z with forward returns (partial IC after mom30 and SMA50 distance in brackets):

| series | BTC h30 IS | BTC h30 OOS | ETH h30 IS | ETH h30 OOS |
|---|---|---|---|---|
| basis_ann | +0.134 (+0.042) | +0.062 (+0.076) | +0.175 (+0.215) | +0.042 (−0.006) |
| slope | +0.023 (+0.075) | +0.084 (+0.084) | −0.086 (−0.098) | −0.018 (+0.015) |
| funding 7d | +0.057 (−0.041) | −0.049 (−0.047) | +0.187 (+0.225) | +0.032 (−0.032) |

The sign is *positive*: a rich basis goes with rising prices, i.e. trend. Once trend is controlled,
nothing is consistent across coins and halves.

**Rules on spot × inverse-vol** (40 %, cap 1), 10 bp, from the first z:

| rule | BTC full / IS / OOS | ETH full / IS / OOS |
|---|---|---|
| inverse-vol alone | 0.59 / 0.50 / 0.69 | 0.50 / 0.55 / 0.45 |
| SMA50 × inverse-vol | **1.01 / 0.94 / 1.08** | **0.90 / 0.62 / 1.20** |
| basis: flat if z > 1 (crowded) | 0.37 / 0.40 / 0.34 | 0.31 / 0.41 / 0.21 |
| basis: flat if z < −1 (fear) | 0.74 / 0.46 / 1.06 | 0.57 / 0.53 / 0.61 |
| slope: flat if z > 1 | 0.39 / 0.34 / 0.45 | 0.38 / 0.50 / 0.25 |
| slope: flat if z < −1 | 0.61 / 0.35 / 0.91 | 0.71 / 0.66 / 0.77 |
| SMA50 × inverse-vol × basis flat if z > 1 | 0.68 / 0.71 / 0.65 | 0.70 / 0.39 / 1.01 |

- The contrarian "crowded basis" rule *hurts* in every case.
- The fear rule helps BTC OOS only (1.06 vs 0.69), is below inverse-vol IS, and loses to SMA50.

## 3. Verdict

**Failed.** The dated basis contains the same information as funding and price trend. It is higher
in bull markets, and neither its level nor its slope over funding times spot beyond what SMA50
already does. This is consistent with every earlier funding and premium timing screen in this repo.

Variants: 3 series × 2 horizons × 2 coins ICs, 7 rules × 2 coins = 14 backtests.

## 4. Files

```
code/crypto-perps/basis-term-slope/fetch_quarterly.py   COIN-M CQ/NQ continuous klines, expiry calendar
code/crypto-perps/basis-term-slope/exp01_screen.py      (+ exp01_results.csv)
```
