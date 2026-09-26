"""Re-framing: does a broken spot-vol correlation predict SPY returns / drawdowns (melt-up fragility)?"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vol-regime-equity-timing"))
import numpy as np, pandas as pd
import vc_data as vc
from ve_lib import long_panel, bt_excess, row

L = long_panel()
r = L["SPY"].pct_change()
dv = np.log(L["VIX"]).diff()
F = {"corrvix10": dv.rolling(10).corr(r).shift(1), "corrvix21": dv.rolling(21).corr(r).shift(1),
     "corrvix21rel": (dv.rolling(21).corr(r) - dv.rolling(252).corr(r)).shift(1)}
ls = np.log(L["SPY"])
f21 = ls.shift(-21) - ls
dd21 = (L["SPY"].shift(-1).rolling(21).min().shift(-20) / L["SPY"] - 1)
for fn, f in F.items():
    out = []
    for k, (a, b) in {"PRE": ("1999", "2010"), "IS": vc.IS, "OOS": vc.OOS}.items():
        d = pd.concat([f, f21, dd21], axis=1).loc[a:b].dropna().iloc[::5]
        out.append(f"{k}: ret21 IC {d.iloc[:,0].corr(d.iloc[:,1], method='spearman'):+.3f} dd21 IC {d.iloc[:,0].corr(d.iloc[:,2], method='spearman'):+.3f}")
    print(fn, " | ".join(out))
rows = {}
for fn, f in F.items():
    thr = f.rolling(252, min_periods=126).quantile(0.85)
    net, we = bt_excess(pd.Series(np.where(f > thr, 0.5, 1.0), index=L.index), L); rows[f"SPY 0.5 when {fn}>q.85"] = row(net, we)
net, we = bt_excess(pd.Series(1.0, index=L.index), L); rows["SPY B&H"] = row(net, we)
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 20)
print(pd.DataFrame(rows).T.round(2))
