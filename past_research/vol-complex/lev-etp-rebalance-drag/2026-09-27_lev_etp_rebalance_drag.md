# lev-etp-rebalance-drag — shorting the leveraged vol ETP's path dependence

**Status: Failed.** A static-hold pair of short UVXY against long L × VIXY (rebalanced every 5–10
sessions) earns net Sharpe ~0.6. But that is **3.6–4.1 % CAGR at 6–7 % vol, before the short-borrow
fee**, and most of it is UVXY's own fee and financing drag. At a 5 % borrow fee (UVXY has usually
cost more) OOS Sharpe is −0.13…+0.13. Gating on high VIX, where the variance edge "should" be
largest, makes it worse. 51 configurations were evaluated.

Date: 2026-09-27 · Asset class: vol-complex · Author: research agent (Opus 5.5)

## 1. Idea

UVXY (2× until 2018-02-27, 1.5× after) and SVXY (−1× then −0.5×) rebalance daily to constant
leverage on the same short-term VIX-futures index as VIXY (1×). Over a multi-day hold, a
leveraged product's return differs from L × the 1× product's return by a term that is
**second-order in the path**. For short $1 UVXY / long $L VIXY held n days:

P&L ≈ −½ L(L−1) · Σ_{i<j} r_i r_j, so E[P&L] ≈ −L(L−1) · [Σ autocovariances + ½ n(n−1) μ²]

With iid returns the expected P&L is ≈ 0 (the famous "volatility decay" is a median/log effect, not
a mean effect). It becomes positive only if daily returns **mean-revert** within the hold. VIX
futures do mean-revert: VIXY AC(1) = −0.05, and the variance ratio is 0.90 at 5 days and 0.81 at
21 days. The trade is therefore short realised-path trendiness, a vol-of-vol premium orthogonal to
the direction of VIX. `term-structure-carry` dismissed the *daily-rebalanced* version analytically;
this tests the static-hold version.

## 2. Method (01_static_pairs.py, 02_regime.py)

* Share holdings are fixed between rebalances (the weights drift), and reset every H ∈ {1, 5, 10,
  21, 63} sessions and on the 2018-02-28 leverage change. The public leverage schedule is known ex ante.
* Pairs, with gross exposure normalised to 1:
  * **A**: short UVXY / long L·VIXY;
  * **B**: short UVXY / short (L_UVXY / |L_SVXY|)·SVXY, the classic "short both" delta-neutral pair;
  * **C**: long SVXY / long |L_SVXY|·VIXY, which needs no borrow.
* Cost 5 bp per side on traded notional. Borrow 0 / 5 / 10 % per year on short notional, charged
  daily. Sample 2011-10 → 2026-09.

## 3. Results

| pair | H | borrow | Sharpe full | IS | OOS | CAGR | vol | MaxDD |
|---|---|---|---|---|---|---|---|---|
| A | 1 | 0 | 0.57 | 0.67 | 0.45 | 2.0 % | 3.6 % | −6 % |
| A | 1 | 5 % | 0.05 | 0.28 | −0.27 | 0.1 % | | |
| A | 5 | 0 | **0.61** | 0.75 | 0.44 | 3.6 % | 6.2 % | −11 % |
| A | 5 | 5 % | 0.31 | 0.54 | **−0.13** | 1.7 % | | |
| A | 10 | 0 | 0.59 | 0.67 | 0.53 | 4.1 % | 7.2 % | −14 % |
| A | 10 | 5 % | 0.34 | 0.48 | 0.13 | 2.2 % | | |
| A | 21 / 63 | 0 | 0.00 / −0.18 | | | | 14 % / 90 % | −52 % / −111 % |
| B | 5 / 10 | 0 | 0.61 / 0.60 | 0.83 / 0.75 | 0.27 / 0.43 | 10 % / 11 % | 18–21 % | −23…−29 % |
| B | 5 / 10 | 5 % | 0.32 / 0.37 | | −0.40 / −0.02 | | | |
| C (long/long) | 1–63 | – | −0.58…−0.10 | | | | | |
| A, H = 5, hold only if VIX(t−1) > 18 / 22 / 26 | | 0 | 0.32 / 0.00 / −0.09 | | 0.07 / −0.19 / −0.37 | | | |
| A, H = 10, same gates | | 0 | 0.38 / 0.07 / 0.00 | | 0.28 / −0.11 / −0.26 | | | |

## 4. Why it fails

1. **The H = 1 control is informative.** The daily-rebalanced pair should earn exactly zero if UVXY
   tracked L × VIXY. It earns 2 %/yr (Sharpe 0.57): that is UVXY's higher expense ratio and
   leverage-financing drag. A short collects that fee only to pay it back, and more, as borrow. The
   5–10-day hold adds only ~1.5–2 %/yr of genuine path (mean-reversion) edge on top.
2. **Borrow is the binding constraint.** UVXY borrow has historically been several percent a year
   and spikes when retail shorts crowd in. At 5 % every version is ≤ 0.37 full and ≤ 0.13 OOS. The
   simulated book would not charge this, so a deployment would look better in sim than it could
   ever be in reality. That is a reason *not* to deploy, not a reason to.
3. **The variance edge is not where the variance is.** Gating on high VIX was meant to concentrate
   exposure where σ² is large. It turns the edge negative, because high-VIX weeks are trending
   (spikes and their unwinds), which is the path the pair is short. Holds of 21–63 days blow up for
   the same reason (MaxDD −52 % / −111 %).
4. Long SVXY plus long VIXY avoids borrow but loses in every configuration: the inverse product's
   own path/fee drag works against a long holder.

## 5. Conclusion

Leveraged vol-ETP decay is a median/log phenomenon. Its mean component is small, concentrated in
calm mean-reverting weeks, and smaller than the borrow on the product you must short. Not a
deployable edge. Do not revisit unless a borrow-free way to be short the leveraged product exists.

## 6. Files

`code/vol-complex/lev-etp-rebalance-drag/`: `01_static_pairs.py` (static-hold simulator, pairs
A/B/C × H × borrow, VIXY variance ratios), `02_regime.py` (VIX-level gating). No alpha spec.
