# token-dilution — circulating-supply growth predicts alt underperformance

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Working (modest standalone, 0.77 / 0.78 OOS; recommended as a sleeve of `alt-sleeve-blend`)

## 1. Idea

Guo ("Token dilution and the cross-section of cryptocurrency returns", SSRN 6636258, 2026; 404
coins, weekly, 2020-26) finds that a 12-week token dilution rate and the FDV premium (fully-diluted
over circulating market cap) predict cross-sectional returns with NW t of −2.8 / −3.1. The
explanation offered is limited investor attention to publicly disclosed vesting and emission
schedules. The equity analogue is the net-issuance anomaly (Pontiff-Woodgate 2008). New supply
from unlocks, staking emissions, treasury sales and ecosystem grants comes with a seller attached,
and the market prices it late. Pre-registered sign: **negative** (short the most-diluting alts),
primary measure = Guo's 12-week circulating-supply growth.

## 2. Data

* **CoinMarketCap historical listing snapshots**, keyless `data-api/v3/cryptocurrency/listings/historical`
  (the endpoint behind coinmarketcap.com/historical). New shared fetcher `code/crypto-alts/shared/cmc.py`
  → `data/CMC_listings_weekly.parquet`: every Sunday 2017-01-01 → 2026-09-20, top 300 by market cap,
  **including coins that later died**. That is 508 snapshots × 300 rows with circulatingSupply,
  totalSupply, maxSupply, dateAdded, price, marketCap and volume.
* Timing: a snapshot stamped D carries quotes at D 00:00 and supplies updated late on D. It is used
  from the close of D+1 (`known_lag_days = 1`) and forward-filled daily. Supplies are what CMC
  displayed at the time, so methodology changes appear as jumps. The rank-based signal and a
  [−1, 2] log clip keep those from dominating.
* Mapping: each yfinance alt gets the CMC id whose snapshot price tracks its close (median |log ratio| < 5 %).
  All 62 tradable candidates mapped. This sidesteps namesake-ticker traps (ARB, FIL, ONE, …).
* CoinMetrics community `SplyCur` was considered and rejected. It has no SOL, AVAX, NEAR, FIL,
  ATOM or TRX, and for ERC-20s it is total minted supply, not circulating supply.
* Tradable universe unchanged: PIT top-20 by trailing 90d median yfinance USD volume (≥ 120 closes,
  ≥ $5M), 16.5 names/day with supply in 2018 and 20 from 2019. IS 2018-22 / OOS 2023-26 (fixed by
  the first crypto-alts study), 10 bp/side.

## 3. Results

### 3.1 IC screen (`01_ic.py` → `ic_01.csv`)
Daily rank IC vs forward XS-demeaned return, NW t:

| Signal | 7d IS / OOS | 30d IS / OOS | 60d IS / OOS |
|---|---|---|---|
| **dilution 12w** | **−0.035 (t −2.4) / −0.060 (t −3.4)** | −0.063 (−2.3) / −0.091 (−2.9) | −0.087 (−2.8) / −0.105 (−2.8) |
| dilution 4w | −0.038 (−2.6) / −0.036 (−2.3) | −0.058 / −0.055 | −0.089 / −0.079 |
| dilution 26w | −0.024 / −0.059 | −0.037 / −0.100 | −0.056 / −0.128 |
| dilution 52w | −0.014 / −0.062 | −0.019 / −0.105 | −0.034 / −0.135 |
| overhang log(total/circ) | +0.008 / −0.039 | +0.034 / −0.057 | +0.046 / −0.080 |
| age since CMC listing | +0.040 / +0.078 | +0.041 / +0.155 | +0.041 / +0.215 |
| log market cap | +0.041 / +0.086 | +0.054 / +0.170 | +0.049 / +0.235 |

Dilution is negative in both halves at every window and horizon (figure 02). The FDV overhang,
Guo's other measure, has the wrong sign in-sample and is not used. Size and age are much stronger
OOS than IS, which is the 2023-26 "large caps win" regime. They are treated as controls, not signals.

### 3.2 Costed books (`02_books.py` → `books_02.csv`, 24 dilution configs + 4 controls)
Linear-rank, dollar-neutral alt legs (sum|w| = 1), `bn` = plus a BTC leg zeroing the EWM-60 beta,
overlapping tranches. Grid: window {4,12,26,52}w × hold {7,14,30} × {dn, bn}. **Median 0.46 full /
0.46 IS / 0.38 OOS.** 22 of 24 cells are positive full-sample, and every 12w cell is positive in both halves.

| 12w, hold | 7 | 14 | 30 |
|---|---|---|---|
| dn (no BTC leg) full / IS / OOS | 0.42 / 0.52 / 0.30 | 0.49 / 0.61 / 0.34 | 0.62 / 0.78 / 0.40 |
| **bn** full / IS / OOS | 0.57 / 0.50 / 0.67 | 0.65 / 0.59 / 0.73 | **0.77 / 0.76 / 0.78** |

`bn` was the house default before this idea ran (it was used in `volume-attention` and both
premium studies). In-sample dn and bn are equal (0.78 vs 0.76). The BTC hedge matters OOS because
a dollar-neutral dilution book is net short beta (it shorts the young, high-beta diluters), and
2023-25 was a BTC bull market.

Controls, same construction: long big market cap 0.35 / −0.05 / 0.93 (ρ 0.07 with dilution);
low-beta (always-β-neutral BAB) 1.27 / 1.29 / 1.24 (ρ 0.30).

### 3.3 Robustness of the spec (12w, bn, hold 30; `03_robust.py` → `robust_03.csv`)

| Variant | full | IS | OOS |
|---|---|---|---|
| **spec** | **0.77** | **0.76** | **0.78** |
| window ensemble 4/12/26/52w | 0.74 | 0.68 | 0.81 |
| terciles instead of linear | 0.66 | 0.64 | 0.68 |
| inverse-vol sizing | 0.80 | 0.67 | 0.97 |
| hold 60 | 0.85 | 1.01 | 0.64 |
| 8w / 16w window | 0.84 / 0.63 | 1.01 / 0.62 | 0.63 / 0.64 |
| cost 20 / 30 bp | 0.74 / 0.70 | 0.73 / 0.69 | 0.75 / 0.71 |
| universe 10 / 15 / 30 | 0.30 / 0.53 / 0.90 | 0.44 / 0.62 / 1.07 | 0.08 / 0.40 / 0.66 |

Fama-MacBeth (rank on rank, weekly, 30d forward; controls log mcap, age, −beta, 30d return): the
dilution slope stays positive, +0.051 (t 1.9) full, +0.056 (t 1.5) IS, +0.045 (t 1.2) OOS. It is
partly shared with size and beta, but not subsumed.

### 3.4 Diagnostics (`04_diag.py`)
* **The short leg earns it.** High-dilution coins alone (β-hedged) earn 0.46 full / 0.35 IS / 0.64 OOS,
  and the low-dilution long leg alone ≈ 0. Largest OOS losers (per-coin P&L): SOL, LINK, NEAR. Largest
  winners: longs in TRX, BNB (supply burns), BCH, SHIB.
* **Not a young-token effect here.** Contrary to Guo, within the PIT top-20 the premium lives in coins
  listed ≥ 2 years (0.94 / 1.07 / 0.74). Young ones are too few (6/day) to form a book (0.18). Guo's
  young-token premium is concentrated in names too small for this universe.
* **Truncation lookahead test:** weights rebuilt from yfinance and CMC data cut at 2019-06-30,
  2021-05-15, 2022-11-20, 2024-03-10 and 2025-12-31 equal the full-sample weights on those dates,
  max |diff| = 0.0.

### 3.5 Headline (spec, 2018-03-08 → 2026-09-27, `07_headline.py`)

| | Sharpe | CAGR | Vol | MaxDD | t_NW |
|---|---|---|---|---|---|
| Full | **0.77** | 12.9 % | 17.8 % | −25.3 % | 2.02 |
| IS 2018-22 | 0.76 | 12.9 % | 18.1 % | −24.6 % | 1.43 |
| OOS 2023-26 | **0.78** | 12.9 % | 17.5 % | −25.3 % | 1.45 |

Yearly: 2018 0.01, 2019 0.80, 2020 −0.41, 2021 1.42, 2022 1.84, 2023 −0.39, 2024 2.27, 2025 1.17, 2026 YTD −0.77.
Gross 1.02 average (alt legs 0.47 long / 0.47 short, BTC leg +0.06, range −0.06…+0.25), turnover 6.2×/yr,
β to BTC 0.00, ρ to live BAB 0.26. Block bootstrap (30d) 5-95 % [0.13, 1.41], P(Sh > 0) 0.98.
Deflated Sharpe 0.75 at 10 trials, 0.61 at 24 (the dilution grid), 0.49 at 50. Short-leg carry
(unmodelled) at 5 / 10 / 20 %/yr of short notional → 0.64 / 0.50 / 0.23.

## 4. Verdict

**Working, modest.** A pre-registered, literature-motivated mechanism with the predicted sign in
both halves, t ≈ −2.4 IS and −3.4 OOS on the 7-day IC, and an OOS book that matches IS
(0.76 → 0.78). It is not a ≥ 1 Sharpe strategy on its own: bootstrap intervals are wide,
it is weak with a 10-name universe, and short carry could halve it. Its value is diversification.
ρ to BAB is 0.26, and it is the largest risk weight in [`alt-sleeve-blend`](../alt-sleeve-blend/),
the recommended deployment. Variants: 32 IC cells + 28 books + 11 robustness books + 4 diagnostics.

## 5. Files
* `code/crypto-alts/token-dilution/`: `common.py`, `01_ic.py`, `02_books.py`, `03_robust.py`, `04_diag.py`,
  `05_check_strategy.py` (strategy.py reproduces the research book to 3e-17), `06_figures.py`,
  `07_headline.py`, **`strategy.py`** (`dilution_weights`, `load_inputs`), CSV/parquet outputs, `idmap.json`.
* Shared: `code/crypto-alts/shared/cmc.py` (fetch/refresh snapshots, `yahoo_map`, `wide`).
* `alphas/crypto-alts/token-dilution/spec.md` + 3 figures + `backtest_series.parquet`.
