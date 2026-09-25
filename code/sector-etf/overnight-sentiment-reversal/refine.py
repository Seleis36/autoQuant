"""Refinements declared before running (no lookback picking):
  form:  raw  = -sum overnight;  volz = -sum overnight / (overnight vol * sqrt k);
         res  = -sum of beta-residual overnight (sector ON minus beta * SPY ON)
  horizon ensemble: mean of cross-sectional ranks over k in {21, 42, 63, 126, 252}
  construction: linear, 21-day tranches, SPY hedge; also gross-scaled to 10 % ex-ante vol
"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

S = data.SECTORS
c = data.load_panel(); o = data.load_panel(field="Open")
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
onr_all = np.log(o / c.shift(1))
onr = onr_all[S]
on_res = onr - beta.shift(1).mul(onr_all["SPY"], axis=0)
mask = data.universe_mask(c[S])
onvol = onr.rolling(252, min_periods=126).std()
KS = [21, 42, 63, 126, 252]

def sig_of(form, k):
    if form == "raw": return -onr.rolling(k).sum()
    if form == "volz": return -onr.rolling(k).sum() / (onvol * np.sqrt(k))
    if form == "res": return -on_res.rolling(k).sum()

def xs_rank(s):
    s = s.where(mask); rk = s.rank(axis=1, pct=True); return rk.sub(rk.mean(axis=1), axis=0)

def lin(s):
    s = s.where(mask); s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

def book(sig, n=21):
    w = sx.tranche(lin(sig), n); W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1); return W

rows, rets = [], {}
for form in ["raw", "volz", "res"]:
    for k in KS:
        W = book(sig_of(form, k)); st, net = sx.summary(W, c, name=f"{form}|k{k}"); rows.append(st); rets[st.name] = net
    ens = sum(xs_rank(sig_of(form, k)) for k in KS) / len(KS)
    W = book(ens); st, net = sx.summary(W, c, name=f"{form}|ENS"); rows.append(st); rets[st.name] = net
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(sx.fmt(df))
df.to_csv(os.path.join(os.path.dirname(__file__), "refine.csv"))
pd.DataFrame(rets).to_parquet(os.path.join(os.path.dirname(__file__), "refine_returns.parquet"))
