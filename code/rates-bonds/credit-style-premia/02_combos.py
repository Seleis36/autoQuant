"""Combinations and re-framings of the hedged credit premia (all in excess of cash, 2 bp).

1. Pre-registered combination: equal risk across the families predicted positive
   (fallen, short_hy, short_ig, loans), each family = equal weight of its ETFs, family risk
   = trailing 250-session vol, reset monthly.
2. Betting-against-beta proper: short-dated vs long-dated within the same market, beta-neutral
   (SJNK/SHYG/HYS vs HYG; VCSH/IGSB/SPSB vs VCLT/IGLB/SPLB), i.e. the low-risk side financed by
   the high-risk side rather than by generic hedges.
3. Conditional versions: hold a family only after credit has sold off (HYG - beta x IEF down
   over the last 63 / 126 sessions), when forced selling is the stated mechanism.
4. Decay: rolling 3-year alpha t-stat of each family.
"""
import numpy as np
import pandas as pd
import csp_lib as cs

pd.set_option("display.width", 220)
px, ret = cs.load()
rebal = cs.month_end_flags(ret.index)
rf = cs.cash_return(ret.index)
L = pd.read_parquet("01_leg_returns.parquet")
F = pd.DataFrame({fam: L[t].mean(axis=1) for fam, (t, _) in cs.FAMILIES.items()})


def show(tag, r):
    print("%-58s" % tag, " ".join("%s %5.2f (%+.2f%%, t %+.1f)" % (k, cs.stats(r, a, b)["sharpe"], cs.stats(r, a, b)["ann"], cs.stats(r, a, b)["t"])
                                  for k, (a, b) in cs.SPLITS.items()), "| 2022+ %.2f" % cs.stats(r, "2022-01-01")["sharpe"])


print("1. combinations of family alphas")
pos = ["fallen", "short_hy", "short_ig", "loans"]
vol = F.rolling(250, min_periods=120).std().where(rebal).ffill().shift(1)
for name, cols in (("equal risk: fallen + short_hy + short_ig + loans", pos), ("equal risk: fallen + short_hy", ["fallen", "short_hy"]),
                   ("equal risk: short_hy + short_ig (defensive only)", ["short_hy", "short_ig"])):
    w = (1 / vol[cols]).div((1 / vol[cols]).sum(axis=1), axis=0)
    show(name, (w * F[cols]).sum(axis=1).where(w.notna().all(axis=1)))
show("equal weight of the four", F[pos].mean(axis=1).where(F[pos].notna().all(axis=1)))

print("\n2. betting against beta inside one market (long short-dated, short beta x long-dated, cash-neutral)")


def bab(lo, hi, win=250, minp=120):
    b = (ret[lo].rolling(win, min_periods=minp).cov(ret[hi]) / ret[hi].rolling(win, min_periods=minp).var()).where(rebal).ffill()
    w_eff = b.shift(1)
    gross = (ret[lo] - rf) - w_eff * (ret[hi] - rf)
    turn = w_eff.diff().abs().fillna(0)
    return (gross - turn * 2e-4).where(w_eff.notna() & ret[lo].notna())


babs = {}
for lo, hi in (("SJNK", "HYG"), ("SHYG", "HYG"), ("HYS", "HYG"), ("VCSH", "VCLT"), ("IGSB", "IGLB"), ("SPSB", "SPLB"), ("VCSH", "LQD"), ("BKLN", "HYG")):
    babs[f"{lo}-b*{hi}"] = bab(lo, hi)
    show(f"{lo} - beta x {hi}", babs[f"{lo}-b*{hi}"])
show("average of the HY three", pd.DataFrame({k: v for k, v in babs.items() if k.endswith("HYG") and not k.startswith("BKLN")}).mean(axis=1))
show("average of the IG three (vs long-dated)", pd.DataFrame({k: babs[k] for k in ("VCSH-b*VCLT", "IGSB-b*IGLB", "SPSB-b*SPLB")}).mean(axis=1))

print("\n3. held only after a credit sell-off (duration-stripped HYG return over the look-back < 0)")
b_hy = (ret["HYG"].rolling(250, min_periods=120).cov(ret["IEF"]) / ret["IEF"].rolling(250, min_periods=120).var()).shift(1)
prem = ((ret["HYG"] - rf) - b_hy * (ret["IEF"] - rf)).fillna(0.0)
for look in (63, 126):
    cond = (prem.rolling(look).sum() < 0).where(rebal).ffill().shift(1).fillna(False).astype(bool)
    for fam in ("fallen", "short_hy", "short_ig", "loans"):
        show(f"{fam}, after {look}d credit loss (on {cond.loc[cs.IS[0]:].mean():.0%} of days)", F[fam].where(cond, 0.0).where(F[fam].notna()))
        show(f"{fam}, after {look}d credit GAIN", F[fam].where(~cond, 0.0).where(F[fam].notna()))

print("\n4. rolling 3-year t-stat of each family's alpha (year-end)")
roll = F.rolling(756, min_periods=600).apply(lambda x: x.mean() / x.std() * np.sqrt(len(x)), raw=True)
print(roll.groupby(roll.index.year).last().round(1).T.to_string())
