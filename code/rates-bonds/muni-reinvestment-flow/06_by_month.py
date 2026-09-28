"""muni-reinvestment-flow -- is the month-start effect bigger in the large reinvestment months?
A-priori group (muni market convention: the largest coupon + principal redemption dates are
Jan 1, Jun 1, Jul 1, Dec 1): BIG = {1, 6, 7, 12}; OTHER = the remaining eight months.
Judged on the NAV sample (1990-2016, not used to discover the effect); ETFs 2017-26 shown for info."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
R = pd.read_csv(os.path.join(_HERE, "04_etf_D.csv"), index_col=0)
R.index = pd.PeriodIndex(R.index, freq="M")
sys.path.insert(0, _HERE); sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from importlib import import_module
from mlib import D_series
h3 = import_module("03_nav_holdout")
nv = h3.navs(); rt = h3.tsy_price_returns(10)
D = {}
for f in h3.FUNDS:
    y = nv[f"{f}_nav"].pct_change().dropna(); y = y[y.abs() < 0.05]
    D[f], _, _ = D_series(y.reindex(y.index.intersection(rt.index)), rt)
N = pd.DataFrame(D).mean(axis=1)
BIG = {1, 6, 7, 12}
def tab(s, lab):
    out = []
    for w, (a, b) in lab.items():
        x = s.loc[a:b]
        for g, m in (("BIG", x.index.month.isin(BIG)), ("OTHER", ~x.index.month.isin(BIG))):
            v = x[m]
            out.append(dict(window=w, group=g, mean_bp=v.mean() * 1e4, t=v.mean() / v.std() * np.sqrt(len(v)), n=len(v)))
    return pd.DataFrame(out)
print("six-fund NAV D (bp/month)")
print(tab(N, {"1990-99": ("1990", "1999"), "2000-07": ("2000", "2007"), "2008-16": ("2008", "2016"),
              "2017-26": ("2017", "2026")}).round(2).to_string(index=False))
print("\nNAV D by calendar month, 2000-2016 mean bp:")
x = N.loc["2000":"2016"]; print((x.groupby(x.index.month).mean() * 1e4).round(1).to_string())
etf = R[["MUB", "TFI", "ITM", "SHM"]].mean(axis=1)
print("\nETF 4-basket D (bp/month)")
print(tab(etf, {"2008-16": ("2008", "2016"), "2017-26": ("2017", "2026")}).round(2).to_string(index=False))
