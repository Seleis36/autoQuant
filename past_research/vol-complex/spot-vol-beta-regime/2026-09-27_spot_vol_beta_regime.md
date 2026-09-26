# spot-vol-beta-regime — spot-vol correlation as a fragility gauge

**Status: Failed.** A weak or broken spot-vol correlation does precede larger VIX spikes: IC with the
next-21-day VIX spike is +0.14…+0.19 IS and +0.10…+0.16 OOS. The problem is using it:
* as a gate, it removes short-vol carry faster than tail losses (carry 0.60 → grid median 0.42);
* on the COT book from idea 1 it lowers IS Sharpe (1.04 → median 0.68);
* a long-VIXY fragility leg loses (−0.11);
* it has no information on SPY returns.

41 configurations plus IC screens were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

Normally vol is a hedge: VIXY-vs-SPY daily correlation is about −0.8 and the beta about −3.9. When the
correlation weakens or turns positive (spot up and vol up together), the market is often
paying for upside calls in a melt-up or hedging into a rally: Jan-2018 before Volmageddon, Feb-2020,
Jul-2024. The hypothesis: broken spot-vol correlation flags fragility. Short vol should step aside,
or go long vol, and possibly equities should be derisked.

## 2. Screen (01_screen.py)

Features: rolling 10/21/63-day correlation and beta of VIXY vs SPY (16:00 closes), of Δlog VIX vs
SPY (lagged one day), the share of "SPY up and VIXY up" days, and deviations from the 252-day norm.

| feature | IC fwd 21d VIXY IS | OOS | IC fwd 21d VIX spike IS | OOS |
|---|---|---|---|---|
| corr VIXY-SPY 10d | 0.00 | 0.11 | **0.14** | **0.15** |
| corr VIXY-SPY 21d | 0.03 | 0.12 | **0.17** | **0.16** |
| corr ΔVIX-SPY 10d | 0.05 | 0.10 | **0.19** | 0.10 |
| corr21 − corr252 | 0.03 | 0.15 | 0.15 | 0.18 |
| up-up day share 21d / 63d | −0.04 / 0.02 | 0.20 / 0.23 | 0.02 / −0.01 | 0.22 / 0.26 (sign unstable) |
| beta VIXY-SPY 21/63d | 0.01 / −0.02 | 0.04 / −0.07 | ~0 | ~0 |

Correlation with the idea-1 COT score is −0.13…−0.24, and with log VIX −0.1…−0.2: a partly new
signal. It predicts spikes, but only weakly predicts VIXY *returns* in IS.

## 3. Trading tests (02_gates.py, 03_spy_reframe.py)

Pre-declared grid: short VIXY in contango (lagged slope) only when the feature is below its rolling
252-day quantile q. Four features × q ∈ {0.5, 0.7, 0.85}, applied to (a) carry and (b) the idea-1
COT book.

| | full | IS | OOS | 2022+ |
|---|---|---|---|---|
| carry (lag 1), reference | 0.60 | 0.66 | 0.54 | 0.17 |
| carry & corr gate, grid median (12) | 0.42 | 0.38 | 0.47 | |
| carry × 12-rule ensemble | 0.46 | 0.42 | 0.51 | −0.04 |
| COT book, reference | 1.00 | 1.04 | 0.96 | 0.38 |
| COT & corr gate, grid median (12) | 0.77 | 0.68 | 0.92 | |
| COT × 12-rule ensemble | 0.91 | 0.75 | 1.07 | 0.24 |
| best single (COT & corr10 < q0.85) | 1.09 | 0.84 | 1.39 | 0.21 |
| long VIXY when corr21rel > q0.9 | −0.11 | −0.68 | 0.25 | |
| SPY at 0.5 when ΔVIX-SPY corr > q0.85 (3 variants, 1999–2026) | 0.41–0.44 | 0.68–0.73 | 0.75–0.80 | B&H 0.43 / 0.78 / 0.79 |

Only a few COT-gated variants improve OOS, and all are worse IS and in 2022+. Picking one on OOS would
be selection. The ensemble is below the ungated COT book on full-sample, IS and 2022+ Sharpe.

## 4. Why it fails

It repeats the core lesson of `term-structure-carry`: the short-vol premium is earned in the same
turbulent weeks that carry the tail risk. The correlation gate is flat 30–60 % of the time. It sits
out the weeks with the richest premium (post-spike, when spot-vol correlation is noisy) as well as
the pre-spike melt-ups. Being long vol on the signal does not pay for the carry it bleeds. For SPY,
the IC on forward 21-day return and drawdown is within ±0.1 with unstable sign across 1999–2010,
IS and OOS.

## 5. Files

`code/vol-complex/spot-vol-beta-regime/`: `01_screen.py`, `02_gates.py` (28-rule grid, ensembles,
long-vol leg), `03_spy_reframe.py` (SPY IC and derisking rules). No alpha spec.
