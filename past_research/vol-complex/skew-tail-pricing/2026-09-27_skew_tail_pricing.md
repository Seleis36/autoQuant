# skew-tail-pricing — the CBOE SKEW index as a short-vol timer

**Status: Failed.** High SKEW (expensive SPX out-of-the-money puts) precedes weaker short-VIXY
returns: 21-day IC +0.17 IS / +0.22 OOS, 63-day IC +0.24 / +0.26. But the information is the VIX
level and slope again. With those and the COT score as controls, SKEW's t-stat is −0.8…+1.0. Every
SKEW gate lowers both carry and the COT book: ensembles 0.41 and 0.79 vs 0.60 and 1.00. 16
configurations plus screens were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

The CBOE SKEW index measures the risk-neutral skewness of 30-day SPX returns, i.e. the price of
deep OTM puts relative to ATM options. It is an options-surface input no vol-complex study had used.
There are two competing hypotheses:
* **(a) hedged market.** High SKEW means insurance is already bought, so short VIX futures is safer.
* **(b) informed tail hedging.** High SKEW means someone expects a tail, so avoid short vol.

The literature (e.g. Bevilacqua & Tunaru; CBOE's own notes) mostly finds SKEW a poor crash
predictor. The question was whether it times the VIX-futures premium.

## 2. Screen (01_screen.py)

`^SKEW` from yfinance (2009+), cached `data/IDX_SKEW_d.parquet`, lagged one session. Spearman IC vs
forward VIXY log return:

| feature | 5d IS | 21d IS | 63d IS | 21d OOS | 63d OOS | 21d VIX-spike OOS |
|---|---|---|---|---|---|---|
| SKEW level | 0.04 | 0.17 | 0.24 | 0.22 | 0.26 | 0.23 |
| SKEW z-score (252 d) | 0.04 | 0.09 | 0.16 | 0.12 | 0.09 | 0.18 |
| SKEW 5 / 21-day change | −0.05 / −0.01 | −0.01 / 0.05 | | 0.04 / 0.10 | | |
| SKEW / VIX | 0.11 | 0.21 | 0.35 | 0.34 | 0.46 | 0.31 |
| SKEW orthogonal to log VIX (rolling) | 0.05 | 0.16 | 0.31 | 0.07 | 0.18 | 0.02 |

The sign supports (b): expensive tails precede weaker short-vol returns. But SKEW/VIX is −0.94
correlated with log VIX, i.e. it is 1/VIX, and SKEW is −0.27 correlated with the COT crowding score.

## 3. Attribution and gates (02_gates.py)

HAC t-stats of the forward 21-day VIXY return on SKEW, log VIX, lagged slope and the COT score:

| | SKEW z | SKEW ⟂ VIX | log VIX | COT score |
|---|---|---|---|---|
| IS | −0.79 | −0.47 | −2.83 / −1.24 | −1.08 / −1.89 |
| OOS | +0.31 | +1.01 | −2.11 / −2.02 | −1.76 / −1.69 |

Pre-declared gates: short in contango (lagged slope) only when the SKEW measure is below its
rolling-252 quantile q, with q ∈ {0.5, 0.7, 0.85}:

| | full | IS | OOS | 2022+ |
|---|---|---|---|---|
| carry reference / COT book | 0.60 / 1.00 | 0.66 / 1.04 | 0.54 / 0.96 | 0.17 / 0.38 |
| carry & SKEW < q 0.5 / 0.7 / 0.85 | 0.38 / 0.63 / 0.57 | 0.52 / 0.72 / 0.47 | 0.25 / 0.54 / 0.67 | |
| carry & SKEW⟂VIX < q | 0.02 / 0.19 / 0.36 | | | |
| COT & SKEW < q | 0.63 / 0.87 / 0.88 | 0.80 / 0.87 / 0.72 | 0.42 / 0.90 / 1.07 | |
| COT & SKEW⟂VIX < q | 0.45 / 0.50 / 0.69 | | | |
| carry × 6-rule ensemble | 0.41 | 0.50 | 0.34 | −0.09 |
| COT × 6-rule ensemble | 0.79 | 0.88 | 0.69 | 0.02 |

## 4. Conclusion

SKEW's forecasting power for VIX futures is the VIX level in disguise, plus a slice of the
positioning information the COT signal already has. Orthogonalised, it is noise, and gating on it
removes carry days. Failed.

## 5. Files

`code/vol-complex/skew-tail-pricing/`: `01_screen.py`, `02_gates.py`. No alpha spec.
