"""Is COT positioning information beyond VIX level / slope? Quintiles + partial regressions."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import statsmodels.api as sm
import vc_data as vc
from cot_lib import session_features

P = vc.panel()
F = session_features(P.index)
lr = np.log(P["VIXY"]).diff()
f21 = lr.shift(-1).rolling(21).sum().shift(-20)
f5 = lr.shift(-1).rolling(5).sum().shift(-4)
X = pd.DataFrame({"am": F["am_net_z156"], "lev": F["lev_net_z156"], "oth": F["oth_net_z104"],
                  "logvix": np.log(P["VIX"]), "slope": P["VIX3M"] / P["VIX"],
                  "vixmom": np.log(P["VIX"] / P["VIX"].rolling(21).mean())})
print("corr of features (full):\n", X.corr().round(2))
for h, f in (("5d", f5), ("21d", f21)):
    for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
        d = pd.concat([X, f.rename("y")], axis=1).loc[a:b].dropna().iloc[::5]
        m = sm.OLS(d["y"], sm.add_constant(d[["am", "logvix", "slope", "vixmom"]])).fit(
            cov_type="HAC", cov_kwds={"maxlags": 5})
        print(h, k, "n", len(d), "coef", m.params.round(4).to_dict(), "t", m.tvalues.round(2).to_dict())
# quintiles of am z (annualised mean daily VIXY return next day, grouped)
r1 = P["VIXY"].pct_change().shift(-1)
for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    d = pd.concat([X["am"], r1.rename("r"), (X["slope"] > 1).rename("cont")], axis=1).loc[a:b].dropna()
    d["q"] = pd.qcut(d["am"], 5, labels=False)
    g = d.groupby("q")["r"].agg(["mean", "std", "count"])
    g["ann_mean"] = g["mean"] * 252; g["sh_short"] = -g["mean"] / g["std"] * np.sqrt(252)
    print(k, "\n", g.round(4))
    g2 = d.groupby(["cont", "q"])["r"].agg(["mean", "std", "count"])
    g2["sh_short"] = -g2["mean"] / g2["std"] * np.sqrt(252)
    print(g2.round(3))
