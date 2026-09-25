"""Sector short-term reversal: market-neutral book, long recent losers / short recent
winners among sector SPDRs, SPY hedge to zero beta. Grid over lookback k, holding
(tranches) n, signal form, and a VIX gate (Nagel 2012: reversal = liquidity provision,
paid more when VIX is high). Every cell is recorded; the count feeds the DSR."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
r = c.pct_change()
spy = r["SPY"]
S = data.SECTORS
sec = r[S]
beta = sx.beta_to(sec, spy, halflife=126)
resid = sec - beta.shift(1).mul(spy, axis=0)
mask = data.universe_mask(c[S])
vix = data.load_ohlcv("^VIX")["Close"].reindex(c.index).ffill()
vol = sec.ewm(halflife=63, min_periods=63).std()

def book(sig, n, gate=None, gross=1.0):
    s = sig.where(mask)
    s = s.sub(s.mean(axis=1), axis=0)
    w = s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0) * gross
    if gate is not None:
        w = w.mul(gate.astype(float), axis=0)
    w = sx.tranche(w, n)
    hedge = -(w * beta.fillna(1.0)).sum(axis=1)
    W = w.copy(); W["SPY"] = hedge
    return W

gates = {
    "none": None,
    "vix>med252": vix > vix.rolling(252, min_periods=126).median(),
    "vix>20": vix > 20,
    "vix>25": vix > 25,
}
rows = []
for base, k, form, n, g in itertools.product(["resid", "rel"], [1, 2, 3, 5], ["raw", "volz"], [1, 3, 5], gates):
    b = resid if base == "resid" else sec.sub(spy, axis=0)
    cum = b.rolling(k).sum()
    if form == "volz":
        cum = cum / (vol * np.sqrt(k))
    W = book(-cum, n, gates[g])
    s, net = sx.summary(W, c, name=f"{base}|k{k}|{form}|n{n}|{g}")
    s0, _ = sx.summary(W, c, cost_bps=0.0)
    s["Sh0_IS"] = s0["Sh_IS"]; s["Sh0_OOS"] = s0["Sh_OOS"]
    rows.append(s)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
out = sx.fmt(df.sort_values("Sh_IS", ascending=False))
print(len(df), "cells")
print(out.head(30))
print(out.sort_values("Sh_OOS", ascending=False).head(10))
df.to_csv(os.path.join(os.path.dirname(__file__), "grid_results.csv"))
