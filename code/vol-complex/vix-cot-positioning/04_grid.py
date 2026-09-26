"""Pre-declared grid: short VIXY when contango AND positioning z > theta. Select on IS only.

Grid (declared before running): feature in {am_z52, am_z104, am_z156, comp = (am_z - lev_z)/2 @104,156},
theta in {-0.5, 0, 0.25, 0.5, 1.0}, slope lag in {0, 1}. 5*5*2 = 50 configs.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import vc_data as vc
from cot_lib import session_features

P = vc.panel()
F = session_features(P.index)
feats = {"am_z52": F["am_net_z52"], "am_z104": F["am_net_z104"], "am_z156": F["am_net_z156"],
         "comp104": (F["am_net_z104"] - F["lev_net_z104"]) / 2,
         "comp156": (F["am_net_z156"] - F["lev_net_z156"]) / 2}
slope = P["VIX3M"] / P["VIX"]
rows = {}
for lag in (0, 1):
    cont = (slope.shift(lag) > 1)
    net, st = vc.bt(pd.Series(np.where(cont, -1.0, 0), index=P.index), P["VIXY"], 5)
    rows[("carry", "-", lag)] = vc.split_row(net, {"TO": st["Turnover_ann"], "TiM": -st["AvgExposure"]})
    for fn, f in feats.items():
        for th in (-0.5, 0, 0.25, 0.5, 1.0):
            w = pd.Series(np.where(cont & (f > th), -1.0, 0.0), index=P.index)
            net, st = vc.bt(w, P["VIXY"], 5)
            rows[(fn, th, lag)] = vc.split_row(net, {"TO": st["Turnover_ann"], "TiM": -st["AvgExposure"]})
res = pd.DataFrame(rows).T
res.index.names = ["feat", "theta", "lag"]
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
print(res.round(2))
for lag in (0, 1):
    sub = res.xs(lag, level="lag").drop(index="carry", level=0)
    best = sub["IS"].idxmax()
    print("lag", lag, "IS-best", best, sub.loc[best].round(2).to_dict())
    print("lag", lag, "median over grid: full %.2f IS %.2f OOS %.2f" % tuple(sub[["Sh", "IS", "OOS"]].median()))
