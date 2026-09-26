"""Daily vol-ETP dollar-volume sentiment: share of long-vol ETP dollar volume (UVXY, VIXY, VXX)
vs inverse (SVXY), and abnormal volume; IC vs forward VIXY returns; relation to the COT AM score."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import vc_data as vc
from strategy import scores_on_sessions
from fetch_cot_vix import fetch_tff

P = vc.panel()
C = vc.load_close(["UVXY", "VIXY", "VXX", "SVXY"]).reindex(P.index)
V = vc.load_close(["UVXY", "VIXY", "VXX", "SVXY"], "Volume").reindex(P.index)
DV = (C * V).fillna(0)
longv = DV[["UVXY", "VIXY", "VXX"]].sum(axis=1)
inv = DV["SVXY"]
F = {}
for w in (5, 21, 63):
    F[f"longshare_{w}"] = (longv.rolling(w).sum() / (longv + inv).rolling(w).sum())
    F[f"log_ratio_{w}"] = np.log(longv.rolling(w).sum() / inv.rolling(w).sum())
F["longshare_z21_252"] = (F["longshare_21"] - F["longshare_21"].rolling(252).mean()) / F["longshare_21"].rolling(252).std()
F["abn_long_dv"] = np.log(longv.rolling(5).mean() / longv.rolling(126).mean())
F["abn_inv_dv"] = np.log(inv.rolling(5).mean() / inv.rolling(126).mean())
F = pd.DataFrame(F)
lr = np.log(P["VIXY"]).diff()
fwd = {h: lr.shift(-1).rolling(h).sum().shift(-(h - 1)) for h in (1, 5, 21)}
rows = []
for c in F.columns:
    row = {"f": c}
    for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
        for h, f in fwd.items():
            d = pd.concat([F[c], f], axis=1).loc[a:b].dropna().iloc[::h]
            row[f"ic{h}_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
    rows.append(row)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).set_index("f").round(3))
S = scores_on_sessions(fetch_tff(), P.index).mean(axis=1)
print("corr with COT avg score:", F.corrwith(S).round(2).to_dict())
print("corr with log VIX:", F.corrwith(np.log(P["VIX"])).round(2).to_dict())
print(F.resample("YE").mean()[["longshare_21", "log_ratio_21"]].round(2).T)
