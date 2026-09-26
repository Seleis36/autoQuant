"""Selection-free ensemble over the 04 grid, SPY-beta attribution, stress events, SVXY version."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import statsmodels.api as sm
import vc_data as vc
from cot_lib import session_features

P = vc.panel()
F = session_features(P.index)
feats = {"am_z52": F["am_net_z52"], "am_z104": F["am_net_z104"], "am_z156": F["am_net_z156"],
         "comp104": (F["am_net_z104"] - F["lev_net_z104"]) / 2,
         "comp156": (F["am_net_z156"] - F["lev_net_z156"]) / 2}
slope = P["VIX3M"] / P["VIX"]
rows = {}
def ens(lag, fset=feats, ths=(-0.5, 0, 0.25, 0.5, 1.0)):
    cont = slope.shift(lag) > 1
    ws = [np.where(cont & (f > th), -1.0, 0.0) for f in fset.values() for th in ths]
    return pd.Series(np.mean(ws, axis=0), index=P.index)

spy = P["SPY"].pct_change()
out = {}
for lag in (0, 1):
    w = ens(lag)
    for inst, scale in (("VIXY", 1.0),):
        net, st = vc.bt(w * scale, P[inst], 5)
        rows[f"ens25 lag{lag} {inst}"] = vc.split_row(net, {"TO": st["Turnover_ann"], "Exp": st["AvgExposure"]})
        out[lag] = net
    # continuous alternative: size = clip(0.5 + comp156/2, 0, 1) in contango
    c = (slope.shift(lag) > 1)
    wc = -(0.5 + feats["comp156"] / 2).clip(0, 1).where(c, 0.0)
    net, st = vc.bt(wc, P["VIXY"], 5)
    rows[f"cont comp156 lag{lag}"] = vc.split_row(net, {"TO": st["Turnover_ann"], "Exp": st["AvgExposure"]})
    # SVXY long version (-0.5x after 2018-02-27): size 1 SVXY ~ -1 VIXY pre, -0.5 post
    net, st = vc.bt(-w, P["SVXY"], 5)
    rows[f"ens25 lag{lag} long SVXY"] = vc.split_row(net, {"TO": st["Turnover_ann"], "Exp": st["AvgExposure"]})
    cnet, _ = vc.bt(pd.Series(np.where(slope.shift(lag) > 1, -1.0, 0), index=P.index), P["VIXY"], 5)
    rows[f"carry lag{lag}"] = vc.split_row(cnet)
    out[f"carry{lag}"] = cnet
res = pd.DataFrame(rows).T
pd.set_option("display.width", 220)
print(res.round(2))

net = out[1]
print("corr ens(lag1) vs carry(lag1):", round(net.corr(out["carry1"]), 3))
for k, (a, b) in vc.SPLITS.items():
    d = pd.concat([net.rename("y"), spy.rename("spy")], axis=1).loc[a:b].dropna()
    m = sm.OLS(d["y"], sm.add_constant(d["spy"])).fit(cov_type="HAC", cov_kwds={"maxlags": 10})
    resid = d["y"] - m.params["spy"] * d["spy"]
    print(k, "beta %.2f alpha_ann %.3f t %.2f  hedged Sharpe %.2f" % (
        m.params["spy"], m.params["const"] * 252, m.tvalues["const"], vc.sh(resid)))
print("yearly Sharpe ens lag1:\n", vc.yearly_sharpe(net).round(2).to_dict())
print("yearly Sharpe carry lag1:\n", vc.yearly_sharpe(out["carry1"]).round(2).to_dict())
for a, b in [("2015-08-17", "2015-08-31"), ("2018-01-29", "2018-02-12"), ("2020-02-20", "2020-03-20"),
             ("2022-01-01", "2022-06-30"), ("2024-07-29", "2024-08-09"), ("2025-03-25", "2025-04-15")]:
    print(a, b, "ens %.3f  carry %.3f  exposure %.2f" % ((1 + net.loc[a:b]).prod() - 1,
          (1 + out["carry1"].loc[a:b]).prod() - 1, ens(1).shift(1).loc[a:b].mean()))
net.to_frame("ens25_lag1").to_parquet(os.path.join(os.path.dirname(__file__), "ens_returns.parquet"))
