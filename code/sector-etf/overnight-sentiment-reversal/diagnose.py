"""Is the overnight signal a static sector tilt or time-varying sentiment? And is it an
artefact of stale/erroneous opening prints?
 (1) average weight per sector and share of weight variance that is time-series
 (2) the signal demeaned by each sector's own expanding-mean overnight drift (pure
     time-variation) vs the static part alone
 (3) sanity on opens: share of days with Open == prev Close (stale), by era
 (4) per-year P&L of the reference cell ON63|lin|t21"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

S = data.SECTORS
c = data.load_panel(); o = data.load_panel(field="Open")
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
onr = np.log(o / c.shift(1))[S]
mask = data.universe_mask(c[S])

def lin(sig):
    s = sig.where(mask); s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
def book(sig, n=21):
    w = sx.tranche(lin(sig), n); W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1); return W

k = 63
sig = -onr.rolling(k).sum()
W = book(sig)
print("(1) mean weight by sector (1999-2014 | 2015+):")
print(pd.DataFrame({"IS": W[S].loc[:"2014"].mean(), "OOS": W[S].loc["2015":].mean()}).round(3).T.to_string())
tot = (W[S] ** 2).mean().sum(); stat = (W[S].mean() ** 2).sum()
print(f"    static share of weight 2nd moment: {stat / tot:.2f}")

# (2) time-series-demeaned (expanding mean of daily overnight, lagged) vs static
drift = onr.expanding(252).mean().shift(1)
sig_tv = -(onr - drift).rolling(k).sum()
sig_static = -drift * k
rows = []
for nm, s_ in [("raw ON63", sig), ("time-varying part", sig_tv), ("static drift part", sig_static)]:
    st, _ = sx.summary(book(s_), c, name=nm); rows.append(st)
print("(2)"); print(sx.fmt(pd.DataFrame(rows)))

# (3) stale opens
stale = (o[S] == c[S].shift(1)) & c[S].notna()
print("(3) share of days Open == prev Close, by era:")
print(stale.groupby(stale.index.year // 5 * 5).mean().round(3).to_string())
print("    mean |overnight| bp by era:")
print((onr.abs().groupby(onr.index.year // 5 * 5).mean() * 1e4).round(1).to_string())

# (4) per-year
_, net = sx.summary(W, c)
print("(4) per-year % :", (net.groupby(net.index.year).sum() * 100).round(1).to_dict())
