"""Characteristic screen (feeds the choice of idea 6+): monthly rank IC of sector
characteristics vs next-month beta-residual return, non-overlapping. IS / OOS."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

S = data.SECTORS
c = data.load_panel(); o = data.load_panel(field="Open"); v = data.load_panel(field="Volume")
h = data.load_panel(field="High")
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
on = (o / c.shift(1) - 1)[S]; intra = (c / o - 1)[S]
on_rel = on.sub((o / c.shift(1) - 1)["SPY"], axis=0); in_rel = intra.sub((c / o - 1)["SPY"], axis=0)
mask = data.universe_mask(c[S])
L = lambda x, k: np.log1p(x).rolling(k).sum()
sig = {
    "mom12_1": L(resid, 252) - L(resid, 21),
    "mom12": L(resid, 252),
    "mom6": L(resid, 126),
    "mom3": L(resid, 63),
    "mom1": L(resid, 21),
    "rawmom12_1": np.log(c[S] / c[S].shift(252)) - np.log(c[S] / c[S].shift(21)),
    "hi52": c[S] / c[S].rolling(252).max(),
    "smooth12": L(resid, 252) / (resid.rolling(252).std() * np.sqrt(252)),   # residual-mom t-stat
    "overnight21": on_rel.rolling(21).sum(),
    "intraday21": in_rel.rolling(21).sum(),
    "overnight63": on_rel.rolling(63).sum(),
    "intraday63": in_rel.rolling(63).sum(),
    "volshock": (v[S].rolling(5).mean() / v[S].rolling(126).mean()),
    "dvol_trend": np.log(v[S].rolling(21).mean() / v[S].rolling(252).mean()),
    "tsmom_sign": np.sign(L(r[S], 252)),
}
fwd = L(resid, 21).shift(-21)
me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()
rows = []
for k, s in sig.items():
    ss = s.where(mask)[me]; ff = fwd.where(mask)[me]
    ic = ss.rank(axis=1).corrwith(ff.rank(axis=1), axis=1).dropna()
    for seg, (a, b) in sx.SPLITS.items():
        x = ic.loc[a:b]
        rows.append(dict(sig=k, seg=seg, IC=x.mean(), t=x.mean() / x.std() * np.sqrt(len(x))))
print(pd.DataFrame(rows).pivot(index="sig", columns="seg", values=["IC", "t"]).round(3))
