# alt-sleeve-blend — equal-risk blend of four uncorrelated liquid-alt sleeves

**Date:** 2026-09-28 · **Asset class:** crypto-alts · **Status:** Working (recommended deployment; an upgrade of the live BAB book)

## 1. Idea

The live crypto-alts book (`xs-momentum-neutral`, regime-hedged betting-against-beta) is a single
mechanism. It runs 1.22 full / 1.06 OOS with a −30 % drawdown. This session and an earlier
crypto-perps study produced three more alt cross-section sleeves, each weaker but nearly
uncorrelated with it and with each other:

| Sleeve | Mechanism | Standalone full / IS / OOS | ρ to BAB |
|---|---|---|---|
| `bab` | long low-β / short high-β alts, regime hedge (live) | 1.22 / 1.35 / 1.06 | 1 |
| `dilution` | short 12-week circulating-supply growth ([token-dilution](../token-dilution/)) | 0.77 / 0.76 / 0.78 | 0.26 |
| `volume` | short abnormal-volume surges ([volume-attention](../volume-attention/), selection-free ensemble) | 0.56 / 0.61 / 0.49 | 0.10 |
| `funding` | short crowded-funding perps, P&L on spot (`crypto-perps/funding-xs-crowding`, 2020-09+) | 0.64 / 0.51* / 0.96 | 0.04 |

\* IS on its active days (2020-09 → 2022). Pairwise sleeve correlations are all 0.04-0.26.
Four ~0.5-1.2 Sharpe streams with ρ ≈ 0.1 should combine to well above any one of them.

## 2. Pre-registered rule (written in `01_blend.py` before it ran)

* Candidates: the four sleeves above, each exactly as its own `strategy.py` produces it.
* Inclusion: IS Sharpe (active days, 2018-03-08 → 2022-12-31) ≥ 0.3 **and** |ρ to BAB| < 0.5. All four pass.
* Risk weights: k_s ∝ 1 / σ_s(IS, active days), normalised to sum 1 → **bab 0.223, dilution 0.292,
  volume 0.246, funding 0.239**. They are fixed constants in `strategy.py` and not re-estimated live.
* Blend at the **weight level**: w = L · Σ k_s w_s. Trades that offset across sleeves net out, and
  costs (10 bp/side) are charged on the blended turnover. The primary is the all-passing set. Every
  subset is reported, plus a walk-forward inclusion control.
* Leverage L: 1.0 gives 12 % vol. The spec uses **L = 2.0**, which matches BAB's own IS volatility.
  Sharpe does not depend on L.

**Provenance, honestly.** The rule was fixed before the blend was computed, but after each sleeve's
standalone results, OOS included, had been seen. Dilution was pre-registered from the literature.
The volume sleeve was found in a screen that covered 2023-26. The funding sleeve and its low BAB
correlation were documented in an earlier PR. The blend's OOS is therefore *semi*-out-of-sample. The
controls in §4 are there to show how much of the result survives without that knowledge.

## 3. Results (`01_blend.py` → `blend_01.csv`; `02_final.py` → `final_02.log`)

### 3.1 All subsets (L = 1, net 10 bp, 2018-03-08 → 2026-09-27)

| Sleeves | full | IS | OOS | pooled bear | MaxDD | vol |
|---|---|---|---|---|---|---|
| bab (live) | 1.22 | 1.35 | 1.06 | 1.49 | −30 % | 24 % |
| bab + dilution | 1.26 | 1.39 | 1.12 | 1.26 | −18 % | 16 % |
| bab + volume | 1.22 | 1.34 | 1.05 | 1.71 | −22 % | 16 % |
| bab + funding | 1.34 | 1.36 | 1.32 | 1.48 | −17 % | 15 % |
| bab + dilution + volume | 1.30 | 1.43 | 1.14 | 1.54 | −17 % | 14 % |
| bab + dilution + funding | 1.37 | 1.44 | 1.31 | 1.32 | −12 % | 13 % |
| bab + volume + funding | 1.33 | 1.37 | 1.28 | 1.73 | −16 % | 13 % |
| dilution + volume + funding (no BAB) | 1.03 | 0.98 | 1.11 | 1.07 | −17 % | 12 % |
| **all four (primary)** | **1.39** | **1.47** | **1.31** | **1.59** | **−13 %** | **12 %** |

Leave-one-out from the primary: dropping any single non-BAB sleeve keeps 1.30-1.37 full / 1.14-1.31 OOS.
Without BAB the other three still make a 1.03 / 0.98 / 1.11 book. The gain comes from diversification,
not from one lucky sleeve.

### 3.2 Primary at spec leverage L = 2.0

| | Sharpe | CAGR | Vol | MaxDD | Sortino | Calmar |
|---|---|---|---|---|---|---|
| Full (2018-03-08 → 2026-09-27) | **1.39** | 34.3 % | 23.1 % | −24.0 % | 2.03 | 1.42 |
| IS 2018-22 | **1.47** | 33.2 % | 21.5 % | −22.9 % | 1.96 | 1.45 |
| OOS 2023-26 | **1.31** | 33.8 % | 24.6 % | −24.0 % | 2.05 | 1.40 |

Same-vol comparison: BAB alone runs 1.22 / 1.35 / 1.06 at 24 % vol with MaxDD −30 %.

* Exposure: gross average 1.08, max 2.00; net dollar exposure +0.11 on average (BAB's bull-regime net long);
  BTC hedge leg +0.04 on average; β to BTC −0.02. Turnover 14×/yr.
* BTC bear phases (frozen in `shared/study.py`): pooled 1.59; per phase 2018 +1.20, 2019-20 −0.11,
  2021 +4.81, 2022 +2.50, 2025-26 +0.54. BAB alone: +0.25, +0.26, +4.32, +2.71, +0.78.
* Calendar years: 2018 1.12, 2019 0.76, 2020 0.08, 2021 2.12, 2022 3.04, 2023 0.70, 2024 2.35, 2025 1.88,
  **2026 YTD −0.79**. Every sleeve is negative in 2026 YTD (BAB −0.59, dilution −0.77, volume −0.03,
  funding −0.20), so the blend's worst year is a year where diversification had nothing to work with.
* t_NW 3.68. Block bootstrap (30d, 2000 draws): mean 1.42, 5-95 % [0.82, 2.01], P(Sh > 1) 0.88,
  P(Sh > 0) 1.00. Deflated Sharpe 0.995 / 0.969 / 0.916 at 10 / 50 / 200 trials.

### 3.3 Costs and carry
* Cost per side 0 / 5 / 10 / 20 / 30 bp → full 1.45 / 1.42 / 1.39 / 1.33 / 1.27, OOS 1.37 / 1.34 / 1.31 / 1.24 / 1.18.
* Short-leg carry (funding/borrow, not modelled; average short notional 0.48 at L = 2) at 5 / 10 / 20 %/yr →
  full 1.28 / 1.18 / 0.97, OOS 1.20 / 1.09 / 0.88. At 10 %/yr the blend still beats the uncharged BAB OOS.

## 4. Controls against hindsight

* **Walk-forward inclusion.** At each 1 January from 2021, a sleeve is included if its expanding
  Sharpe to date is ≥ 0.3, weighted by expanding 1/σ. In 2021 only `volume` qualifies: BAB had lost
  in 2018-19, dilution was flat and funding had no history. From 2022 BAB, dilution and funding are
  in, and from 2023 all four. Stitched 2021-26: **0.71** (BAB alone 1.73), dragged down by 2021 when
  BAB was excluded. 2023-26: **1.30** vs BAB 1.06. A researcher in early 2021 would **not** have
  built this blend. By 2023 the same rule picks exactly the primary set, and from then on it beats BAB.
* **Equal-weight ignorance check.** The risk weights are close to 1/4 each (0.22-0.29), so the
  result does not depend on estimated weights.
* **Truncation lookahead test** on the full `strategy.py` pipeline. Yfinance, CMC snapshots and
  funding were cut at 2021-06-30, 2022-11-20, 2024-08-05 and 2026-03-31, and the last-row weights
  equal the full-sample weights, max |diff| = 0.0. `strategy.py` reproduces the research blend to 4e-8.

## 5. Verdict

**Working — recommended as the crypto-alts deployment, replacing or upgrading the single-sleeve BAB book.**
At matched volatility it improves every headline on the live book: Sharpe 1.22 → 1.39 full and
1.06 → 1.31 OOS, MaxDD −30 % → −24 %, and pooled-bear Sharpe 1.49 → 1.59. It holds up in every
leave-one-out, at 30 bp and under 10 %/yr short carry. The honest caveats are the semi-OOS
provenance (§2), the walk-forward control's 2021 miss (§4), and 2026 YTD being negative across
all sleeves. Configurations evaluated: 15 subsets + 1 levered primary + 1 walk-forward control.
The sleeve-level variant counts are in each sleeve's report.

## 6. Files
* `code/crypto-alts/alt-sleeve-blend/`: `common.py` (sleeve loader), `01_blend.py` (rule, subsets,
  walk-forward), `02_final.py` (reproduction, stress, bootstrap, DSR, truncation test), `03_figures.py`,
  **`strategy.py`** (`load_inputs`, `sleeve_weights`, `blend_weights`), `blend_01.csv`, `blend_01_nets.parquet`,
  `final_02.log`, `weights_final.parquet`.
* Sleeve code: `code/crypto-alts/xs-momentum-neutral/strategy.py`, `code/crypto-alts/token-dilution/strategy.py`,
  `code/crypto-alts/volume-attention/strategy.py`, `code/crypto-perps/funding-xs-crowding/strategy.py`
  (imported read-only).
* `alphas/crypto-alts/alt-sleeve-blend/spec.md`, figures `01_equity.png` … `05_exposure.png`, `backtest_series.parquet`.
