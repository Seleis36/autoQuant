# whale-taker-flow — large-vs-small taker order-flow imbalance on Binance spot BTC

**Date:** 2026-09-28
**Asset:** spot BTC/USDT (Binance), long/flat, unlevered, hourly bars
**Status:** **Failed. The information is real; the trade is not incremental.**
- Whale-minus-retail taker imbalance (aggTrades ≥ $100k vs < $1k) predicts BTC over the next 1–72 h in both halves:
  - hourly-sampled partial IC, 72h window → next 24 h: +0.047 (t 2.2) in 2018–22 and +0.087 (t 3.2) in 2023–26;
  - shift placebo p < 0.005.
- Standalone, the best IS configuration is 1.12 full / 0.93 IS / 1.37 OOS at 10 bp/side. A strict walk-forward over its grid gives **0.86**, against 0.87 for vol-scaled buy-and-hold.
- As a confirmation filter on the live `coinbase-premium` sleeve, the pre-specified cell scores **1.49 / 1.37 / 1.64** vs 1.34 / 1.17 / 1.56, with MaxDD −23% vs −33%. But the filter family's median is 1.37, and a selection-adjusted walk-forward is **1.37 vs 1.48** for the unfiltered sleeve.
- The robust effect is **drawdown reduction, not Sharpe**.

---

## 1. Idea

The earlier `coinbase-premium` screen found *aggregate* Binance taker-buy imbalance weak (IS t 2.2 → OOS t 0.7). Aggregate flow mixes two populations the microstructure literature treats as opposites:
- **Informed / institutional** traders, who hit the book in size (Kyle 1985; Easley–O'Hara).
- **Noise / retail** traders, who trade small and are contrarian indicators in equities (Kaniel, Saar & Titman 2008; Barber, Odean & Zhu 2009 on small-trade imbalance).

Splitting the tape by trade size should separate them. The tick store has every Binance spot BTCUSDT aggTrade since 2017-08, and no earlier BTC study used it.

## 2. Data (`build_flow.py`)

- 109 monthly aggTrades files (2017-08 → 2026-08, 23 GB) are reduced to an **hourly table of taker-buy and taker-sell notional and counts in 5 USD size buckets** (<1k, 1–10k, 10–100k, 100k–1M, ≥1M). It takes 2 min 40 s with 4 processes. Output: `data/BTCUSDT_spot_takerflow_size_1h.parquet`.
- An aggTrade merges one taker order's fills at one price, so its notional is a lower bound on the parent order size.
- The buckets were fixed before any result: **L = ≥ $100k**, **S = < $1k**, M in between.
- The hour stamped t covers [t, t+1h), the same convention as the bar store. A signal at index t is known at t+1h and applied to bar t+1.
- Timing was checked with the lag probe in §6.

## 3. Daily screen (`exp01_screen.py`, `exp02_diagnostics.py`) — 124 features × 3 horizons

Partial ICs control for the same-window return, because taker flow moves price contemporaneously.

| Feature (daily sampling) | h = 1 d partial IC IS (t) | OOS (t) | h = 3 d IS | OOS |
|---|---|---|---|---|
| **LmS_3** = imb(L) − imb(S), 3 d | +0.057 (2.7) | +0.072 (2.8) | +0.075 (1.9) | +0.161 (3.4) |
| imb_L_3 | +0.059 (2.8) | +0.046 (1.7) | +0.066 (1.6) | +0.146 (3.2) |
| retail net flow (z, 1 d), h = 7 | −0.05 | −0.19 (−2.8) | | |
| share of volume in L trades | −0.05 (−2.2) | −0.06 (−2.2) | slow regime level, z-score ≈ 0, not used | |

- **Caveat found in diagnostics.** At *daily* sampling, the IS significance of LmS comes almost entirely from Aug–Dec 2017 (yearly IC1 +0.37). For 2018–22 the IC1 is +0.02 / +0.04 / −0.03 / −0.01 / +0.03, and the IC of LmS minus its 90-day mean is t 0.56 IS.
- OOS is positive every year (IC3 2023–26: +0.04 / +0.17 / +0.11 / +0.22), and the top decile earns +225 bp over the next 3 days.
- Adding controls for 14-day return, SMA50 state and RV30 changes nothing (OOS partial t 2.66 / 3.52).

## 4. Hourly sampling (`exp04_hourly_ic.py`) — 20 cells

Hourly sampling has 24× the observations. The information shows up in 2018–22 too once 2017 is excluded (column IS18):

| window W → horizon k | IS partial IC (t) | **IS 2018–22 (t)** | OOS (t) |
|---|---|---|---|
| 24 h → 1 h | 0.017 (3.8) | **0.018 (4.2)** | 0.016 (3.0) |
| 24 h → 4 h | 0.025 (2.8) | 0.026 (2.9) | 0.024 (2.2) |
| 72 h → 24 h | 0.062 (2.8) | 0.047 (2.2) | 0.087 (3.2) |
| 72 h → 72 h | 0.110 (2.8) | 0.100 (2.6) | 0.097 (2.1) |
| 168 h → 24 h | 0.070 (3.2) | 0.051 (2.4) | 0.052 (2.0) |

## 5. Strategies

### 5.1 Daily forms (`exp03_backtest.py`) — 15 backtests, 2018-03 → 2026-08

| | full | IS | OOS | ρ to trend |
|---|---|---|---|---|
| vol-scaled B&H | 0.71 | 0.44 | 1.08 | 0.70 |
| SMA50 × vol | 1.24 | 1.05 | 1.49 | 1.00 |
| A 1{rank(LmS_3) > ½} × vol | 1.12 | 0.74 | 1.63 | 0.66 |
| B gate on SMA50 × vol | 1.40 | 1.12 | 1.73 | 0.80 |
| C tilt on SMA50 × vol | 1.38 | 1.15 | 1.67 | 0.96 |

### 5.2 Hourly state machine (`exp05_hourly_state.py`) — 30 configs, selection on 2018–22

The signal is the LmS over W h, z-scored vs 720 h, run through a hysteresis state machine (enter e / exit x) × [SMA 1200 h] × inverse-EWMA-vol (hl 480 h, 40%, cap 1).
- The grid median is 0.98 full / 0.70 IS / 1.25 OOS, with IS→OOS Spearman **−0.24**.
- IS-selected without trend: **W24 (0, −1)**, 1.12 / 0.93 / 1.37 (vol B&H 0.74 / 0.46 / 1.12).
- IS-selected with trend: W168 (0, −1.5), 1.21 IS → 1.07 OOS, *below* the hourly SMA50 × vol OOS of 1.22.

### 5.3 Combination with the live `coinbase-premium` sleeve (`exp06_blend.py`, `exp07_flow_composite.py`)

The whale state is timed differently from the premium: weight correlation 0.22 and z-score correlation 0.13. But as long-only BTC books the daily P&L correlation is 0.61. Four pre-specified combinations were run, all with coinbase-premium's own parameters:

| (10 bp/side, 2018-01 → 2026-08) | full | IS | OOS | MaxDD |
|---|---|---|---|---|
| coinbase-premium, live spec | 1.34 | 1.17 | 1.56 | −33% |
| 50/50 weights with the S1 whale sleeve | 1.37 | 1.17 | 1.62 | −33% |
| composite z = (z_prem + z_whale)/√2 | 1.41 | **1.39** | 1.45 | −30% |
| **premium AND whale (S2)** | **1.49** | 1.37 | **1.64** | **−23%** |
| premium OR whale | 1.09 | 1.04 | 1.15 | −39% |

## 6. Validation (`exp08_validate.py`, `exp09_s2_walkforward.py`)

| Check | S1 standalone | S2 premium AND whale |
|---|---|---|
| Timing: whale z +1 / +2 bars late (legal) | 1.04 / 0.88 | 1.43 / 1.37 |
| Timing: 1 bar early (**illegal**) | 1.94 | 1.74 |
| Costs 0 / 3 / 5 / 10 / 20 bp | 1.47 / 1.36 / 1.29 / 1.12 / 0.77 | 1.92 / 1.79 / 1.70 / 1.49 / 1.06 |
| Large bucket ≥ $1M instead of ≥ $100k | **0.39** | 1.21 |
| Large ≥ $10k | 1.01 | 1.38 |
| Small < $10k instead of < $1k | 0.87 | 1.37 |
| Neighbourhood (W 12–168 h × exit −1/−1.5/−2), full Sharpe | — | median **1.37**, min 1.04 (cbprem 1.34) |
| **Strict walk-forward**, yearly re-selection, 2020–26 | **0.86** (vol B&H 0.87) | **1.37**, 2023+ 1.24 (cbprem 1.48 / 1.56) |
| Circular-shift placebo on whale z (200 draws) | real 1.12 vs mean 0.32, max 0.82 | real 1.49 vs mean 1.09, max 1.49; p < 0.005 |
| Block bootstrap (21 d), 5–95% | [0.50, 1.68], P(>1) 0.61 | [0.77, 1.98], P(>1) 0.86 (cbprem 0.74) |
| Deflated Sharpe, 60 trials | 0.85 | 0.98 |
| vectorbt `from_orders` (targetpercent, 0.1% fee) | — | 1.484 vs 1.490, return corr 0.999 |
| Worst drawdown / share of days > 20% under water | −47% | **−22% / 3.2%** (cbprem −32% / 11.5%) |

Yearly Sharpe:

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| S1 | −0.45 | 2.17 | 2.46 | 0.56 | −0.27 | 2.86 | 2.09 | 0.39 | −0.55 |
| S2 | −0.71 | 1.86 | 3.42 | 1.20 | −1.04 | 2.25 | 2.33 | 0.33 | 0.85 |
| cbprem | −1.60 | 2.09 | 3.23 | 1.29 | −1.82 | 2.37 | 2.00 | 0.40 | 0.65 |

The whale filter mostly helps in the two bear years, 2018 and 2022.

## 7. Verdict

**Failed** as a new Sharpe source, for three reasons:
1. **Standalone, it does not survive honest selection.** The walk-forward of the 30-config grid (0.86) equals vol-scaled buy-and-hold (0.87). The ≥ $1M bucket variant collapses to 0.39.
2. **As a filter on coinbase-premium, the Sharpe gain is a top-of-family number.**
   - The fixed cell (W24, exit −1.5) comes from an IS-selected window and a copied exit, and is +0.15 over the live sleeve.
   - But the neighbourhood median is +0.03.
   - A walk-forward that may choose "no filter" underperforms the live sleeve (1.37 vs 1.48).
   - On IS alone, the composite-z form (IS 1.39) would have been preferred over AND (1.37), and composite-z is 1.45 OOS, below the live 1.56.
3. The information is genuine but small next to BTC's own variance. The decile profile shows it is almost entirely a top-decile *long* effect, so no short leg helps.

**What does survive:** the whale-confirmation AND-filter cuts coinbase-premium's worst drawdown from −32% to −22%. It also cuts the share of days spent more than 20% under water from 11.5% to 3.2%, and does so at every lag and bucket variant tried. That is a risk overlay a deployment reviewer could consider for `live/spot-btc/coinbase-premium`. It is **not** claimed as an alpha here.

A live version would need real-time aggTrades: REST `api/v3/aggTrades` paging, ~1–3 M trades a day, or the websocket stream, because the archive lags by a day.

Configurations: 372 daily screen cells, 20 hourly IC cells, 15 daily + 30 hourly + 7 blend + 4 combination backtests, and 15 neighbourhood + 8 bucket + 8 cost + 6 timing variants.
