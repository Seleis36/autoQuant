"""Reconciles the proxy (Part A) and ETF (Part B) seasonal results: same signal, three return sets."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared")); sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import data, sxlib as sx, french
import seasonal_grid as sg
c = data.load_panel(); S = data.SECTORS
fr = french.sector_returns()
sig = sg.sigs[(30, "ex")]
# ETF monthly returns
m = c.resample("ME").last().pct_change()
avail_etf = m[S].notna()
for label, rets, av in [("proxy-11", fr, fr.notna()), ("proxy-etfavail", fr, avail_etf.reindex(fr.index).fillna(False)), ("etf", m[S], avail_etf)]:
    a = av.reindex(sig.index).fillna(False) & sig.notna()
    # availability must be judged at t+1 (the month traded)
    a = a.shift(-1).fillna(False).astype(bool) & sig.notna()
    w = sg.qw(sig, a, 2)
    rr = rets.reindex(sig.index)
    ret = (w.shift(1) * rr).sum(axis=1)
    for p in [("1999", "2014"), ("2015", "2026")]:
        x = ret.loc[p[0]:p[1]]
        print(label, p, round(x.mean() / x.std() * np.sqrt(12), 2), round(x.mean() * 1200, 2))
