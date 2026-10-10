"""Is the 2 bp cost defensible for the ETFs actually traded? Before 2015 most muni ETFs
traded $3-8M a day. Re-run the selected book on a point-in-time liquid universe: an ETF is
eligible while its trailing 60-session median dollar volume is above a floor.

Also: the effect by liquidity bucket (is the lag just stale closing prints in thin funds?).
"""
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "shared"))
import research_lib as rl
from rb_data import etf_close
import book as S

IS, OOS = ("2008-01-01", "2017-12-31"), ("2018-01-01", "2026-12-31")
px = etf_close(S.TICKERS).loc["2007-10":]
ret = px.pct_change(fill_method=None)
ief = ret["IEF"]
dv = pd.DataFrame({t: (rl.load_series(t)["Close"] * rl.load_series(t)["Volume"]) for t in S.MUNI}).reindex(px.index)
# pre-2010 volumes are not in the flat cache for most; treat missing as illiquid
med = dv.rolling(60, min_periods=30).median()


def sh(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(252) if len(r) > 60 and r.std() > 0 else np.nan


beta = pd.DataFrame({m: ret[m].rolling(250, min_periods=120).cov(ief) / ief.rolling(250, min_periods=120).var() for m in S.MUNI})
vol = ief.rolling(250, min_periods=120).std()
z = ief.rolling(3).sum() / (vol * np.sqrt(3))
pos = z.clip(-1, 1)


def book(mask, cost=2.0):
    live = px[S.MUNI].notna() & beta.notna() & mask
    n = live.sum(axis=1).replace(0, np.nan)
    w = live.astype(float).div(n, axis=0).mul(pos, axis=0).fillna(0.0)
    w["IEF"] = -(w[S.MUNI] * beta.fillna(0)).sum(axis=1)
    we = w.shift(1).fillna(0.0)
    gross = (we * ret[w.columns].fillna(0.0)).sum(axis=1)
    turn = we.diff().abs().sum(axis=1)
    active = we.abs().sum(axis=1) > 0
    return (gross - turn * cost / 1e4).where(active), gross.where(active), live.sum(axis=1)


print("eligible funds by year at each floor:")
for floor in (0, 5e6, 10e6, 20e6, 50e6):
    m = (med >= floor) if floor > 0 else pd.DataFrame(True, index=med.index, columns=med.columns)
    net, gross, n = book(m)
    net4, _, _ = book(m, 4.0)
    first = net.first_valid_index()
    print("floor $%3.0fM: first trade %s | funds 2012 %.1f 2016 %.1f 2020 %.1f 2025 %.1f | net 2bp IS %.2f OOS %.2f | 2010-17 %.2f | gross IS %.2f OOS %.2f | net 4bp IS %.2f OOS %.2f" % (
        floor / 1e6, first.date() if first is not None else None, n.loc["2012"].mean(), n.loc["2016"].mean(), n.loc["2020"].mean(), n.loc["2025"].mean(),
        sh(net, *IS), sh(net, *OOS), sh(net, "2010", "2017"), sh(gross, *IS), sh(gross, *OOS), sh(net4, *IS), sh(net4, *OOS)))

print("\nby liquidity rank each day (1 = most liquid of the eligible), k=3 book on that single fund, gross / net 2 bp, 2012-2026:")
rk = med.rank(axis=1, ascending=False)
for lo, hi in ((1, 2), (3, 4), (5, 8)):
    m = (rk >= lo) & (rk <= hi)
    net, gross, _ = book(m)
    print("rank %d-%d: gross %.2f  net %.2f   (2012-17 gross %.2f, 2018-26 gross %.2f)" % (lo, hi, sh(gross, "2012"), sh(net, "2012"), sh(gross, "2012", "2017"), sh(gross, *OOS)))
