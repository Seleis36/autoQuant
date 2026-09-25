"""Screen: does a driver's past-k-day move predict a sector's next-5-day beta-residual return?
Economically-paired drivers first (oil->XLE, copper->XLB/XLI, rates->XLF/XLU/XLRE, dollar->XLB/XLK),
then every sector x every driver for the multiple-testing picture. Non-overlapping 5-day samples.
lag0 = driver through close t; lag1 = through t-1 (guards against drivers settling after 4pm ET)."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
S = data.SECTORS
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
fwd5 = resid.rolling(5).sum().shift(-5)

def px(t):
    return data.load_ohlcv(t)["Close"].reindex(c.index).ffill(limit=3)
drv = {}
for t, nm in [("CL=F", "oil"), ("HG=F", "copper"), ("GC=F", "gold"), ("NG=F", "natgas"), ("DX-Y.NYB", "dollar")]:
    p = px(t); x = np.log(p).diff(); drv[nm] = x.where(x.abs() < 0.25)       # drop roll/negative-price junk
drv["y10"] = px("^TNX").diff() / 10          # in % points... ^TNX is yield*1 (e.g. 4.2) -> change in pct pts / 10
drv["y10"] = px("^TNX").diff()
drv["slope"] = (px("^TNX") - px("^IRX")).diff()
drv["spy"] = spy
for s_ in S:
    drv[f"sec_{s_}"] = resid[s_]
D = pd.DataFrame(drv)
pairs = [("XLE", "oil"), ("XLE", "natgas"), ("XLB", "copper"), ("XLB", "gold"), ("XLI", "copper"),
         ("XLF", "y10"), ("XLF", "slope"), ("XLU", "y10"), ("XLRE", "y10"), ("XLB", "dollar"),
         ("XLK", "dollar"), ("XLE", "dollar"), ("XLP", "y10")]
rows = []
for (sec, d), k, lag in itertools.product([(a, b) for a in S for b in D.columns if b != f"sec_{a}"], [1, 5, 21], [0, 1]):
    x = D[d].rolling(k).sum().shift(lag)
    y = fwd5[sec]
    for seg, (a, b) in [("IS", ("2000-09-01", "2014-12-31")), ("OOS", sx.OOS)]:
        xx = x.loc[a:b].iloc[::5]; yy = y.loc[a:b].iloc[::5]
        m = xx.notna() & yy.notna()
        if m.sum() < 100: continue
        cc = np.corrcoef(xx[m], yy[m])[0, 1]
        rows.append(dict(sec=sec, drv=d, k=k, lag=lag, seg=seg, corr=cc, t=cc * np.sqrt(m.sum())))
df = pd.DataFrame(rows)
p = df.pivot_table(index=["sec", "drv", "k", "lag"], columns="seg", values="t")
df.to_csv(os.path.join(os.path.dirname(__file__), "screen.csv"))
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 400)
print("== economically paired (t-stats)")
print(p.loc[[pp for pp in p.index if (pp[0], pp[1]) in pairs]].round(2))
print("\n== share of |t|>2 among all IS tests:", (p["IS"].abs() > 2).mean().round(3), "n=", p["IS"].notna().sum())
print("== IS |t|>2.5 and same sign OOS:")
q = p[(p["IS"].abs() > 2.5)]
print(q.assign(same=np.sign(q["IS"]) == np.sign(q["OOS"])).round(2))
