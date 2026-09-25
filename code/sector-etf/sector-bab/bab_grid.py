"""Betting-against-beta across the SPDR sectors (Frazzini-Pedersen 2014; AFP 2018 show
BAB across industries), with the crypto-alts regime-hedge twist.

Constructions (all from close t, earn t+1, 2 bp/side, excess of T-bills):
  FP      rank weights, low-beta leg levered to beta 1, high-beta leg to beta 1 -> beta 0, net long
  TERC    long bottom-3 beta / short top-3 beta, equal dollars, SPY hedge to beta 0
  TERC-D  same, dollar-neutral, no hedge (negative beta)
  REGIME  TERC when SPY > SMA(200) [beta 0], TERC-D otherwise [negative beta]
  LOWVOL  long bottom-3 vol / short top-3 vol, SPY hedge to beta 0
Beta estimators: EWM(hl) daily for hl in {63, 126, 252}; FP-style (1y vol x 5y corr of
3-day returns, shrunk 0.6 to 1). Rebalance: monthly (last trading day) or daily 21-day tranches.
"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
S = data.SECTORS
r = c.pct_change()
spy = r["SPY"]
mask = data.universe_mask(c[S])

def fp_beta(r, spy):
    vol_i = r.rolling(252, min_periods=200).std(); vol_m = spy.rolling(252, min_periods=200).std()
    r3 = np.log1p(r).rolling(3).sum(); m3 = np.log1p(spy).rolling(3).sum()
    corr = r3.rolling(1260, min_periods=500).corr(m3)
    b = corr * vol_i.div(vol_m, axis=0)
    return 0.6 * b + 0.4

betas = {f"ewm{h}": sx.beta_to(r[S], spy, halflife=h, min_periods=h) for h in [63, 126, 252]}
betas["fp"] = fp_beta(r[S], spy)
vol = r[S].ewm(halflife=63, min_periods=63).std()
hedge_beta = sx.beta_to(r[S], spy, halflife=126).fillna(1.0)   # beta used for the SPY hedge
spy_idx = c["SPY"]
up = (spy_idx > spy_idx.rolling(200).mean())
me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()

def terc(sig, k=3):
    s = sig.where(mask)
    lo = s.rank(axis=1) <= k; hi = s.rank(axis=1, ascending=False) <= k
    return lo.astype(float).div(lo.sum(axis=1), axis=0).fillna(0) * 0.5 - hi.astype(float).div(hi.sum(axis=1), axis=0).fillna(0) * 0.5

def fp_weights(b):
    s = b.where(mask)
    z = s.rank(axis=1); z = z.sub(z.mean(axis=1), axis=0)
    k = 2 / z.abs().sum(axis=1)
    wl = (-z).clip(lower=0).mul(k, axis=0); wh = z.clip(lower=0).mul(k, axis=0)
    bl = (wl * s).sum(axis=1); bh = (wh * s).sum(axis=1)
    return wl.div(bl, axis=0).fillna(0) - wh.div(bh, axis=0).fillna(0)

def hold(w, reb):
    if reb == "monthly":
        return w.where(me).ffill().fillna(0)
    return sx.tranche(w, 21)

rows = []
for bname, b in betas.items():
    for cons, reb in itertools.product(["FP", "TERC", "TERC-D", "REGIME"], ["monthly", "tranche21"]):
        if cons == "FP":
            w = hold(fp_weights(b), reb); W = w.copy(); W["SPY"] = 0.0
        else:
            w = hold(terc(b), reb)
            h = -(w * hedge_beta).sum(axis=1)
            W = w.copy()
            if cons == "TERC":
                W["SPY"] = h
            elif cons == "TERC-D":
                W["SPY"] = 0.0
            else:
                W["SPY"] = h.where(up.shift(0), 0.0)
        st, net = sx.summary_rf(W, c, name=f"{bname}|{cons}|{reb}")
        st["beta_real"] = net.cov(spy.loc[net.index]) / spy.loc[net.index].var()
        rows.append(st)
for reb in ["monthly", "tranche21"]:
    w = hold(terc(vol), reb); W = w.copy(); W["SPY"] = -(w * hedge_beta).sum(axis=1)
    st, net = sx.summary_rf(W, c, name=f"vol63|LOWVOL|{reb}")
    st["beta_real"] = net.cov(spy.loc[net.index]) / spy.loc[net.index].var()
    rows.append(st)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
d = sx.fmt(df.rename(columns={"CAGRx": "CAGR"}))
print(d.sort_values("Sh_IS", ascending=False))
df.to_csv(os.path.join(os.path.dirname(__file__), "bab_grid.csv"))
