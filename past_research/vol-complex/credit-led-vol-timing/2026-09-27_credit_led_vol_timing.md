# credit-led-vol-timing — does high-yield credit lead equity vol?

**Status: Failed.** Duration-hedged HYG/LQD returns carry no in-sample information about forward
VIXY returns (IC −0.08…+0.08 at 1/5/21 days). The positive OOS ICs (+0.18…+0.31 at 21 days) have the
"short vol after credit stress" sign, which is post-spike normalisation that carry already harvests.
As gates:
* credit trend helps carry at one window only (HY21 > 0: 1.06 IS → 0.48 OOS);
* it lowers the COT book's OOS Sharpe (0.96 → 0.83).

23 configurations plus IC screens were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

"Credit leads equity" is market folklore with some academic support: bond-market informed trading
and the Merton link between equity vol and credit spreads. If high-yield spreads widen before
equity vol reprices, the HYG-vs-Treasury return would warn short-vol books (flat or long VIXY), and
credit healing would signal the post-spike short-vol window. This is a new information set relative
to `term-structure-carry` (prices of the vol complex) and `vix-cot-positioning` (positioning).

## 2. Data and signals

HYG, LQD, IEF, SPY and VIXY 16:00 closes (no index-timing issue). The credit excess-return proxy is
r_HYG − β·r_IEF, with β from a 252-day rolling regression lagged one day. The same is built for LQD,
plus an HY residual after SPY (credit-specific news), summed over 1/5/10/21/63 days, and the HYG
drawdown from its 63-day high.

## 3. Screen (01_screen.py): Spearman IC vs forward VIXY log return

| feature | 1d IS | 5d IS | 21d IS | 1d OOS | 5d OOS | 21d OOS |
|---|---|---|---|---|---|---|
| HY excess, 5d | 0.00 | −0.03 | −0.04 | 0.06 | 0.14 | 0.27 |
| HY excess, 21d | −0.01 | −0.04 | 0.04 | 0.03 | 0.08 | 0.26 |
| HY excess, 63d | −0.02 | −0.06 | −0.08 | 0.07 | 0.15 | 0.26 |
| IG excess, 21d | −0.01 | −0.04 | −0.05 | 0.01 | 0.03 | 0.23 |
| HY residual after SPY, 21d | −0.07 | −0.11 | −0.14 | −0.03 | 0.00 | 0.08 |
| HYG drawdown 63d | 0.03 | 0.04 | 0.06 | 0.10 | 0.18 | 0.31 |

The credit signals correlate 0.7 with the SPY 21-day return. Only the SPY-residual version is
credit-specific, and it has no consistent sign.

## 4. Rules (02_rules.py), net 5 bp, slope lagged one day

| rule | full | IS | OOS | 2022+ |
|---|---|---|---|---|
| carry reference | 0.60 | 0.66 | 0.54 | 0.17 |
| carry & HY 5/21/63d > 0 (credit trend) | 0.29 / **0.75** / 0.61 | 0.59 / 1.06 / 0.94 | 0.00 / 0.48 / 0.35 | −0.02 / 0.66 / 0.08 |
| carry & HY 5/21/63d < 0 (credit contrarian) | 0.47 / 0.02 / 0.10 | 0.28 / −0.21 / −0.22 | 0.63 / 0.23 / 0.42 | |
| −sign(HY 5/21/63d) long/short VIXY | −0.19 / 0.37 / 0.26 | 0.13 / 0.81 / 0.78 | −0.47 / 0.00 / −0.16 | |
| short VIXY if HYG 63d drawdown < −1/−2/−4 % | 0.39 / 0.19 / −0.07 | 0.15 / 0.15 / −0.45 | 0.64 / 0.24 / 0.21 | |
| carry OR HYG drawdown < −1/−2/−4 % | 0.60 / 0.61 / 0.52 | | 0.54 / 0.53 / 0.57 | |
| COT book (idea 1), reference | 1.00 | 1.04 | 0.96 | 0.38 |
| COT book & HY21 > 0 | 0.97 | 1.10 | 0.83 | 0.71 |

The HY21 trend gate is one window out of three. Its IS strength does not carry OOS, and the
neighbouring windows disagree. On the COT book it trades full-OOS Sharpe for 2022+ Sharpe. Adopting
it would be selecting on the weak period.

## 5. Conclusion

At the daily close, credit does not lead equity vol in a way a daily book can use. Most of the credit
signal is the equity move (ρ ≈ 0.7). The credit-specific residual is noise. The OOS correlation is the
same post-spike normalisation that contango carry already captures. Failed.

## 6. Files

`code/vol-complex/credit-led-vol-timing/`: `01_screen.py`, `02_rules.py`. No alpha spec.
