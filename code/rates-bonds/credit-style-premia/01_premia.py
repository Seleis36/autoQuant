"""Each pre-registered hedged leg, held statically (monthly beta reset), 2 bp per side, in
EXCESS of cash on the leg's net exposure (the first run forgot this: a leg long 1 VCSH and
short 0.25 of hedges earned 4 %/yr of "alpha" in 2023-25 that was the T-bill rate).
IS 2012-07 -> 2018-12, OOS 2019-01 -> 2026-10. The prediction for every family is a positive
alpha, except `long_ig`, which is the short side of the IG defensive trade (predicted negative).
"""
import numpy as np
import pandas as pd
import csp_lib as cs

pd.set_option("display.width", 220)
px, ret = cs.load()
print("first prices:", {t: str(px[t].first_valid_index().date()) for t in cs.ALL})
rebal = cs.month_end_flags(ret.index)
rows, legs = [], {}
for fam, (tickers, hedges) in cs.FAMILIES.items():
    for x in tickers:
        w = cs.leg_weights(ret, x, hedges, rebal=rebal)
        net, gross, turn = cs.run_excess(w, ret)
        legs[x] = net
        b = w[list(hedges)].where(w[x] > 0)
        row = dict(family=fam, etf=x, hedge="+".join(hedges), b_rate=-b[hedges[0]].mean(), b_credit=-b[hedges[1]].mean(), turn=turn)
        for k, (a, e) in cs.SPLITS.items():
            s = cs.stats(net, a, e)
            row.update({f"{k}_sharpe": s["sharpe"], f"{k}_ann%": s["ann"], f"{k}_t": s["t"]})
        s = cs.stats(net, cs.IS[0])
        row.update(vol=s["vol"], maxdd=s["dd"])
        rows.append(row)
out = pd.DataFrame(rows)
out.to_csv("01_premia.csv", index=False)
print(out.round(2).to_string(index=False))
pd.DataFrame(legs).to_parquet("01_leg_returns.parquet")

print("\nfamily averages (equal weight of the family's legs, each scaled to 1 % daily-vol-equivalent is NOT applied: raw alpha)")
L = pd.DataFrame(legs)
for fam, (tickers, _) in cs.FAMILIES.items():
    f = L[tickers].mean(axis=1)
    print("%-9s" % fam, {k: "%.2f (%.2f%%/yr, t %.1f)" % (cs.stats(f, a, e)["sharpe"], cs.stats(f, a, e)["ann"], cs.stats(f, a, e)["t"]) for k, (a, e) in cs.SPLITS.items()})
print("\ncorrelation of family alphas (daily, 2014+):")
F = pd.DataFrame({fam: L[t].mean(axis=1) for fam, (t, _) in cs.FAMILIES.items()})
print(F.loc["2014":].corr().round(2).to_string())
print("\nby year, family alpha in % (net):")
print((F.groupby(F.index.year).sum() * 100).round(2).T.to_string())
