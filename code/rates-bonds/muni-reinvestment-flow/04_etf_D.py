"""muni-reinvestment-flow -- the NAV holdout statistic (03) computed on the traded ETFs.
D_m = sum of hedged daily premium over trading days 1..5 minus 5 x mean over days 6..end,
premium = r_ETF - b0 r_T,t - b1 r_T,t-1 with trailing 252d OLS betas (lagged one day), where
r_T is the matching Treasury ETF (IEF for MUB/TFI/ITM/HYD, SHY for SHM). Also the NAV of the
iShares-equivalent Vanguard fund over the same months, and the month-by-month correlation of
D between ETF and NAV (does the NAV effect show up in traded prices?)."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from importlib import import_module
from rb_data import etf_close
h3 = import_module("03_nav_holdout")
from mlib import D_series

px = etf_close(["MUB", "TFI", "SHM", "ITM", "HYD", "IEF", "SHY"]); r = px.pct_change()
nv = h3.navs(); rt = h3.tsy_price_returns(10)
res = {}
for e, hdg in (("MUB", "IEF"), ("TFI", "IEF"), ("ITM", "IEF"), ("HYD", "IEF"), ("SHM", "SHY")):
    D, _, _ = D_series(r[e].dropna(), r[hdg])
    res[e] = D
for f in ("VWITX", "VWLTX", "VMLTX"):
    y = nv[f"{f}_nav"].pct_change().dropna(); y = y[y.abs() < 0.05]
    D, _, _ = D_series(y.reindex(y.index.intersection(rt.index)), rt)
    res[f] = D
R = pd.DataFrame(res)
for w, (a, b) in {"2008-16": ("2008", "2016"), "2017-26": ("2017", "2026")}.items():
    d = R.loc[a:b]
    out = pd.DataFrame({"mean_bp": d.mean() * 1e4, "t": d.mean() / d.std() * np.sqrt(d.count()), "hit": (d > 0).mean(), "n": d.count()})
    print(f"\n=== {w} ==="); print(out.round(2).to_string())
print("\nmonthly correlation of D, ETFs vs VWITX NAV:")
print(R.loc["2008":].corr()["VWITX"].round(2).to_string())
R.to_csv(os.path.join(_HERE, "04_etf_D.csv"))
