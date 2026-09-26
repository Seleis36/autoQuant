"""Spot-vol correlation / beta regime -> forward VIXY returns and forward vol spikes.
Features from 16:00 closes (VIXY, SPY) are known at t; VIX-index-based ones are lagged 1 day."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel()
R = P[["VIXY", "SPY"]].pct_change()
dv = np.log(P["VIX"]).diff()
F = {}
for w in (10, 21, 63):
    F[f"corr_vixy_spy_{w}"] = R["VIXY"].rolling(w).corr(R["SPY"])
    F[f"beta_vixy_spy_{w}"] = R["VIXY"].rolling(w).cov(R["SPY"]) / R["SPY"].rolling(w).var()
    F[f"corr_dvix_spy_{w}"] = dv.rolling(w).corr(R["SPY"]).shift(1)
    F[f"upup_{w}"] = ((R["SPY"] > 0) & (R["VIXY"] > 0)).rolling(w).mean()
F["beta63_minus_252"] = F["beta_vixy_spy_63"] - (R["VIXY"].rolling(252).cov(R["SPY"]) / R["SPY"].rolling(252).var())
F["corr21_minus_252"] = F["corr_vixy_spy_21"] - R["VIXY"].rolling(252).corr(R["SPY"])
F = pd.DataFrame(F)
lr = np.log(P["VIXY"]).diff()
fwd = {h: lr.shift(-1).rolling(h).sum().shift(-(h - 1)) for h in (5, 21)}
spike = {h: (P["VIX"].shift(-1).rolling(h).max().shift(-(h - 1)) / P["VIX"] - 1) for h in (21,)}
rows = []
for c in F.columns:
    row = {"f": c}
    for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
        for h, f in fwd.items():
            d = pd.concat([F[c], f], axis=1).loc[a:b].dropna().iloc[::5]
            row[f"ic{h}_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
        d = pd.concat([F[c], spike[21]], axis=1).loc[a:b].dropna().iloc[::5]
        row[f"spike21_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
    rows.append(row)
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).set_index("f").round(3))
# correlation with idea-1 COT score and with VIX level
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
from strategy import scores_on_sessions
from fetch_cot_vix import fetch_tff
S = scores_on_sessions(fetch_tff(), P.index).mean(axis=1)
print("corr with COT avg score:", F.corrwith(S).round(2).to_dict())
print("corr with log VIX:", F.corrwith(np.log(P["VIX"])).round(2).to_dict())
