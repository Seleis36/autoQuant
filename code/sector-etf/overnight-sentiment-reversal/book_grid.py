"""Overnight-sentiment reversal book. Signal at close t:
   ON_k  = -(sum of log overnight returns Open_s/Close_{s-1} over the last k days)
   TUG_k = sum intraday - sum overnight (Lou-Polk-Skouras tug of war), k days
Cross-sectional weights over listed sectors (linear demeaned, or top/bottom 3), SPY hedge to
beta 0, rebalanced monthly or via daily h-day tranches. 2 bp/side. Every cell recorded."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

S = data.SECTORS
c = data.load_panel(); o = data.load_panel(field="Open")
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
onr = np.log(o / c.shift(1))[S]; inr = np.log(c / o)[S]
mask = data.universe_mask(c[S])
me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()

def weights(sig, cons):
    s = sig.where(mask)
    if cons == "lin":
        s = s.sub(s.mean(axis=1), axis=0)
        return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    k = 3
    lo = s.rank(axis=1) <= k; hi = s.rank(axis=1, ascending=False) <= k
    return hi.astype(float).div(hi.sum(axis=1), axis=0).fillna(0) * 0.5 - lo.astype(float).div(lo.sum(axis=1), axis=0).fillna(0) * 0.5

def hold(w, reb):
    if reb == "monthly":
        return w.where(me).ffill().fillna(0)
    return sx.tranche(w, int(reb[1:]))

rows, rets = [], {}
for kind, k, cons, reb in itertools.product(["ON", "TUG"], [42, 63, 126, 252], ["lin", "terc"], ["monthly", "t21", "t63"]):
    sig = -onr.rolling(k).sum() if kind == "ON" else inr.rolling(k).sum() - onr.rolling(k).sum()
    w = hold(weights(sig, cons), reb)
    W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1)
    name = f"{kind}{k}|{cons}|{reb}"
    st, net = sx.summary(W, c, name=name)
    st0, _ = sx.summary(W, c, name=name, cost_bps=0)
    st["Sh0_full"] = st0["Sh_full"]
    rows.append(st); rets[name] = net
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(sx.fmt(df.sort_values("Sh_IS", ascending=False)))
df.to_csv(os.path.join(os.path.dirname(__file__), "book_grid.csv"))
pd.DataFrame(rets).to_parquet(os.path.join(os.path.dirname(__file__), "book_grid_returns.parquet"))
