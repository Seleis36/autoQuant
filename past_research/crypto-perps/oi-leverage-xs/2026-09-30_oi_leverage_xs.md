# Open-interest leverage — cross-sectional and market-wide (`oi-leverage-xs`, crypto-perps)

**Date:** 2026-09-30 · **Status: Failed.**
- **Cross-sectional OI growth is dead** in both directions.
- **OI / market cap** has the strongest IC in this session but is a size / low-beta tilt in disguise.
- **The time-series re-framing**, a BTC leverage gate, earns 1.12 / 1.26 IS / 0.99 OOS standalone.
  It does not beat an SMA50 trend filter out of sample, and it does not replicate on ETH, XRP or BNB.

## 0. Idea

Leverage piling into a coin makes it fragile: its longs are the next forced sellers. Coins that just
flushed their leverage have cleared that overhang.

- **Cross-sectional hypothesis:** short the coins where OI is building fastest or is largest
  relative to size, and go long the de-levered ones.
- **Time-series re-framing:** leverage cycles. Hold less BTC when market-wide leverage is extreme.

## 1. Data and set-up

- **OI:** `sum_open_interest` (coins) and `sum_open_interest_value` (USDT) from the Binance metrics
  archive (`data/<SYM>_metrics_5m.parquet`, see `retail-crowding-xs` §1). Last stamp before D 23:00 UTC.
- **Market cap:** CMC weekly circulating supply, known one day after the snapshot
  (`crypto-alts/shared/cmc.py`), × the daily close.
- **Universe, split and cost:** the same pre-registered ones as `retail-crowding-xs`.
  - PIT top-20 of the 64 perps.
  - IS 2022-03 → 2023-12, OOS 2024-01 → 2026-09.
  - q30 L/S, β-neutral, 10 bp.

## 2. exp01 — cross-sectional screen (24 cells)

Contrarian ICs (signal = −feature), mean daily Spearman IC:

| feature | IS IC1 / IC7 (t7) | OOS IC1 / IC7 (t7) |
|---|---|---|
| oig7, 7-day Δlog OI in coins | 0.023 / 0.033 (1.3) | −0.001 / −0.016 (−0.8) |
| oig30 | 0.031 / 0.038 (1.5) | 0.000 / 0.006 (0.3) |
| oig7 residual on 7d return | 0.012 / 0.021 | −0.005 / −0.017 |
| **oi_mcap = log(OI value / mcap)** | **0.071 / 0.114 (3.7)** | **0.059 / 0.091 (3.1)** |
| oi_mcap, own-90d demeaned | 0.024 / 0.031 | −0.003 / 0.004 |
| oi / 30d volume, own-90d demeaned | 0.022 / 0.044 | 0.001 / 0.005 |

L/S books, 7-day tranches:
- **Every OI-growth cell is negative in both directions** (−0.03 … −1.78).
- The own-history-demeaned levels are ≤ 0.03.
- **−oi_mcap h7: 0.90 / 0.65 IS / 1.04 OOS**, turnover 11×/yr.

## 3. exp02 — what OI / market cap is

Cross-sectional Spearman correlation of log(OI/mcap) with (IS / OOS):

| log mcap | turnover (vol/mcap) | beta | 30d vol | funding | retail L/S ratio | mom30 |
|---|---|---|---|---|---|---|
| **−0.78 / −0.66** | **+0.81 / +0.85** | +0.55 / +0.54 | +0.50 / +0.59 | +0.12 / +0.19 | +0.03 / −0.04 | −0.12 / −0.09 |

| variant | full | IS | OOS |
|---|---|---|---|
| −oi_mcap q30 h7 | 0.90 | 0.65 | 1.04 |
| linear / q20 / q50 / h14 / h30 | 0.90 / 0.88 / 0.68 / 0.97 / 0.96 | | |
| **control: big-minus-small (+log mcap)** | **0.89** | 0.62 | 1.06 |
| residual on log mcap | 0.50 | 0.50 | 0.50 |
| residual on turnover | 0.62 | 0.82 | 0.49 |
| **residual on beta** | **0.09** | −0.18 | 0.26 |
| residual on retail L/S ratio | 0.86 | 0.61 | 1.00 |
| frozen IS coin means | 0.98 | 0.88 | 1.05 |
| composite rank(−oi_mcap) + rank(−retail ratio) | 1.40 | 1.01 | 1.63 |

- **OI / mcap is a size and low-beta tilt.** The book is always long BTC and BNB, 91–95 % long XRP
  and TRX, and short BCH, NEAR, LTC and AAVE.
- A plain big-minus-small book earns the same 0.89.
- Once beta is taken out, nothing is left (0.09).
- Quintile forward-7d excess returns are not monotone (IS Q1…Q5: +13, +4, +49, −41, −24 bp).
- Its P&L is uncorrelated with retail crowding (−0.10). That is why the composite reaches 1.40. The
  composite is **not adopted** for `retail-crowding-xs`: the IS gain is +0.03 and the rest is OOS.

## 4. exp03–exp05 — time-series re-framing: leverage cycles

- L = log(OI / supply). This is price-free: OI value / mcap = OI coins / supply.
- z = (L − 365d mean) / 365d std.
- Forward returns by z. Pre-declared rules on BTC spot, 10 bp.

**Forward-return IC of z** (Spearman, BTC L on BTC returns):

| | IS 2021-03 → 2023 | OOS 2024 → 2026-09 |
|---|---|---|
| h7 | −0.146 | −0.063 |
| h30 | −0.202 | −0.129 |
| h30, partial on mom30 + SMA50 distance | −0.190 | −0.129 |
| h30, partial also on the retail L/S ratio | −0.221 | −0.136 |

**BTC rules** (2021-03 → 2026-09):

| rule | full | IS | OOS | MaxDD | exposure |
|---|---|---|---|---|---|
| buy & hold | 0.44 | 0.21 | 0.76 | −77 % | 1.00 |
| inverse-vol (40 %, cap 1) | 0.49 | 0.32 | 0.68 | −61 % | 0.78 |
| leverage gate (flat if z > 1) | 1.06 | 1.15 | 0.97 | −37 % | 0.61 |
| **gate × inverse-vol** | **1.12** | **1.26** | **0.99** | −23 % | 0.49 |
| SMA50 × inverse-vol (reference) | 0.90 | 0.75 | **1.06** | −43 % | 0.42 |
| SMA50 × inverse-vol × gate | 1.24 | 1.46 | 1.03 | −21 % | 0.27 |
| live spot-btc perp-crowding × inverse-vol | 1.23 | 1.35 | 1.11 | −30 % | 0.44 |
| perp-crowding × inverse-vol × gate | 1.38 | 1.60 | 1.15 | −26 % | 0.27 |
| gate thresholds 0.5 / 1.5 | 1.01 / 0.71 | 0.92 / 0.33 | 1.10 / 1.06 | | |
| z windows 180 / 730 d | 1.07 / 1.05 | 0.72 / 1.11 | 1.41 / 1.04 | | |

**Days gated out, by year:**

| 2021 | **2022** | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| 51 % | **87 %** | 0 % | 18 % | 19 % | 69 % |

- Most of the IS value is sitting out the 2022 bear market.
- Market-wide L (sum over the 64 perps, 2022-06+) gives "long if z < 0" 1.24 / 2.11 / 0.82 on a very
  short IS.

**Out-of-asset replication** (exp05). Same parameters, first z 2022-05:

| coin | IC30 | buy & hold | gate × inverse-vol | SMA50 × inverse-vol |
|---|---|---|---|---|
| ETH | −0.03 | 0.44 | 0.49 | 0.96 |
| SOL | −0.16 | 0.69 | 0.83 | 0.96 |
| XRP | +0.04 | 0.74 | 0.50 | 0.46 |
| BNB | +0.06 | 0.64 | 0.57 | 0.99 |

**It does not replicate.** Only SOL agrees in sign.

## 5. Verdict

**Failed.**
- Cross-sectional OI growth carries no information.
- The strong OI / market-cap IC is the size and beta cross-section, which is already live in
  crypto-alts as BAB.
- The BTC leverage gate has information that is not trend and not the retail ratio. The partial IC
  is consistent in both halves. But:
  - OOS it does not beat SMA50 × inverse-vol (0.99 vs 1.06);
  - its IS value is mostly the 2022 bear market;
  - it fails on ETH, XRP and BNB with the same parameters.
- One use, not deployed from here: as an extra gate on the live `spot-btc/perp-crowding` sleeve
  (1.23 → 1.38 full, 1.11 → 1.15 OOS). The OOS gain is too small to justify on its own.

Variants: 24 (exp01) + 16 (exp02) + 6 (exp03) + 12 (exp04) + 4 coins (exp05) ≈ 62.

## 6. Files

```
code/crypto-perps/oi-leverage-xs/exp01_screen.py        (+ exp01_results.csv)
code/crypto-perps/oi-leverage-xs/exp02_oi_mcap.py       (+ exp02_results.csv)
code/crypto-perps/oi-leverage-xs/exp03_aggregate_ts.py
code/crypto-perps/oi-leverage-xs/exp04_btc_timer.py
code/crypto-perps/oi-leverage-xs/exp05_eth_replication.py
```
