"""Books on the official premium and on tradable stand-ins, IS 2008-17 / OOS 2018-26.

A. official premium, one-session skip (the honest timing)          -- rank L/S, hedged
B. official premium with NO skip (uses the NAV of the entry close; NOT tradable) -- upper bound
C. model premium, tradable at close t without the NAV of t:
       mp[t] = prem[t-1] + residual return of t (vs IEF / HYG betas known at t-1)
   i.e. yesterday's official premium plus today's unexplained price move
D. residual return alone (1 / 2 / 5 sessions): plain idiosyncratic reversal, no NAV at all
E. flows (creations / redemptions), one-session skip
F. the same on sub-universes: credit-like funds only, and extremes only (|z| > 1.5)
G. near-substitute pairs (same index family): long the cheaper, short the richer

All fund legs and both hedges pay `cost` per side. Gross and net are printed side by side
(2 bp is of the same order as the gross P&L here, so a negative net says nothing on sign).
"""
import itertools
import numpy as np
import pandas as pd
import nav_lib as nl

pd.set_option("display.width", 220)
d = nl.load()
ret, prem, shares, sector = d["ret"], d["prem"], d["shares"], d["sector"]
b1, b2 = nl.trailing_betas(ret, d["hedge"])
res = nl.residual_returns(ret, d["hedge"], b1, b2)
liq = {"2M": (d["dv"].rolling(60, min_periods=30).median() >= 2e6) & prem.notna(),
       "0.5M": (d["dv"].rolling(60, min_periods=30).median() >= 5e5) & prem.notna()}
CREDIT = sector.index[sector.isin(["hy", "loans", "convert", "preferred", "muni_hy", "em", "ig", "ig_float"])]
flow1 = shares.pct_change(fill_method=None).where(lambda x: x.abs() < 0.5)


def rank_weights(sig, mask, frac=1 / 3, gross=1.0, min_n=4, zmin=None):
    """Long the lowest-signal third, short the highest, equal weight, each side gross/2."""
    s = sig.where(mask)
    if zmin is not None:
        s = s.where(s.abs() >= zmin)
    n = s.notna().sum(axis=1)
    k = (n * frac).round().clip(lower=1)
    lo = s.rank(axis=1).le(k, axis=0) & s.notna()
    hi = s.rank(axis=1, ascending=False).le(k, axis=0) & s.notna()
    if zmin is not None:
        lo, hi = lo & (s < 0), hi & (s > 0)
    w = lo.astype(float).div(lo.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2 \
        - hi.astype(float).div(hi.sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross / 2
    return w.where(n >= min_n, 0.0)


sig = {
    "A prem_z60": (nl.zscore(prem, 60), 1), "A prem_z20": (nl.zscore(prem, 20), 1),
    "A prem_dev60": (prem - prem.rolling(60, min_periods=30).mean(), 1),
    "B prem_z60 no-skip": (nl.zscore(prem, 60), 0),
}
mp = prem.shift(1) + res
sig["C model_prem z60"] = (nl.zscore(mp, 60), 0)
sig["C model_prem dev60"] = (mp - mp.rolling(60, min_periods=30).mean(), 0)
for k in (1, 2, 5):
    rk = res.rolling(k).sum()
    sig[f"D resid_{k}d z"] = (rk / res.rolling(60, min_periods=30).std() / np.sqrt(k), 0)
sig["E flow5"] = (-flow1.rolling(5).sum(), 1)          # sign: outflow -> long (flip to test)
sig["E flow21"] = (-flow1.rolling(21).sum(), 1)
sig["E flow5_z"] = (-nl.zscore(flow1.rolling(5).sum(), 250), 1)

rows = []
for (name, (s, lag)), (lname, mask), sub in itertools.product(sig.items(), liq.items(), ("all", "credit")):
    m = mask if sub == "all" else mask & mask.columns.isin(CREDIT)
    for zmin in (None, 1.5):
        if zmin is not None and "dev" in name or (zmin is not None and name.startswith("E flow") and "z" not in name):
            continue
        w = rank_weights(s, m, zmin=zmin)
        for hold in (1, 5):
            wk = w if hold == 1 else w.where(pd.Series(np.arange(len(w)) % hold == 0, index=w.index)).ffill().fillna(0.0)
            r = {}
            for c in (0.0, 2.0):
                net, gross, turn = nl.book(wk, d, b1, b2, cost_bps=c, lag=lag)
                r[c] = net
            rows.append(dict(sig=name, liq=lname, sub=sub, zmin=zmin, hold=hold, lag=lag,
                             IS_gross=nl.sharpe(r[0.0], *nl.IS), OOS_gross=nl.sharpe(r[0.0], *nl.OOS),
                             IS_net=nl.sharpe(r[2.0], *nl.IS), OOS_net=nl.sharpe(r[2.0], *nl.OOS), turn=turn))
out = pd.DataFrame(rows)
out.to_csv("02_books.csv", index=False)
print(len(out), "cells")
fam = out.assign(family=out.sig.str[0]).groupby("family")[["IS_gross", "OOS_gross", "IS_net", "OOS_net"]].agg(["mean", "max"]).round(2)
print(fam.to_string())
print("\nbest 12 by IS net (2 bp):")
print(out.sort_values("IS_net", ascending=False).head(12).round(2).to_string(index=False))
print("\nbest 8 tradable by IS gross (families A, C, D, E):")
print(out[~out.sig.str.startswith("B")].sort_values("IS_gross", ascending=False).head(8).round(2).to_string(index=False))
print("\nIS/OOS rank corr net: %.2f  gross: %.2f" % (out[["IS_net", "OOS_net"]].corr(method="spearman").iloc[0, 1],
                                                    out[["IS_gross", "OOS_gross"]].corr(method="spearman").iloc[0, 1]))

# G. near-substitute pairs: premium difference between two funds on (nearly) the same bonds
print("\nG. substitute pairs: long the cheaper / short the richer on the gap in official premium (skip 1)")
PAIRS = [("JNK", "SPHY"), ("JNK", "SJNK"), ("SPIB", "SPBO"), ("SPSB", "SPIB"), ("SPTI", "SPAB"), ("TFI", "SHM"),
         ("SPIP", "TIPX"), ("BWX", "IBND"), ("SPTL", "SPLB")]
rets = {}
for a, b in PAIRS:
    gap = nl.zscore(prem[a] - prem[b], 60)
    beta = (ret[a].rolling(120, min_periods=60).cov(ret[b]) / ret[b].rolling(120, min_periods=60).var()).clip(0, 3)
    pos = -np.sign(gap).where(gap.abs() >= 1.0, 0.0)
    for lag in (1, 0):
        w_a, w_b = pos.shift(lag), -(pos * beta).shift(lag)
        g = w_a.shift(1) * ret[a] + w_b.shift(1) * ret[b]
        t = (w_a.shift(1).diff().abs() + w_b.shift(1).diff().abs())
        n = g - t * 2e-4
        rets[(f"{a}-{b}", lag)] = (g, n)
        print("%-10s lag %d  gross IS %5.2f OOS %5.2f | net IS %5.2f OOS %5.2f" % (
            f"{a}-{b}", lag, nl.sharpe(g, *nl.IS), nl.sharpe(g, *nl.OOS), nl.sharpe(n, *nl.IS), nl.sharpe(n, *nl.OOS)))
for lag in (1, 0):
    g = pd.concat([rets[(f"{a}-{b}", lag)][0] for a, b in PAIRS], axis=1).mean(axis=1)
    n = pd.concat([rets[(f"{a}-{b}", lag)][1] for a, b in PAIRS], axis=1).mean(axis=1)
    print("all pairs  lag %d  gross IS %5.2f OOS %5.2f | net IS %5.2f OOS %5.2f" % (
        lag, nl.sharpe(g, *nl.IS), nl.sharpe(g, *nl.OOS), nl.sharpe(n, *nl.IS), nl.sharpe(n, *nl.OOS)))
