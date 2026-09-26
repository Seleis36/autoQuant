"""Diagnostic: asset-manager LONG share vs SHORT share separately (long-vol ETP holdings vs
inverse-vol ETP holdings), same 25-vote ensemble machinery, and carry vs strategy by sub-period."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import vc_data as vc, fetch_cot_vix as cot
from cot_lib import zscore

P = vc.panel()
t = cot.fetch_tff().set_index("date")
legs = {"am_long_share": t["am_long"] / t["oi"], "-am_short_share": -t["am_short"] / t["oi"],
        "am_net": (t["am_long"] - t["am_short"]) / t["oi"]}
cont = (P["VIX3M"] / P["VIX"]).shift(1) > 1
rows = {}
for nm, x in legs.items():
    Z = pd.DataFrame({w: zscore(x, w, int(w * .67)) for w in (52, 104, 156)})
    S = cot.on_session_rows(Z, P.index, t["avail_utc"])
    w = pd.Series(np.mean([np.where(cont & (S[c] > th), -1.0, 0) for c in S for th in (-0.5, 0, .25, .5, 1)], axis=0), index=P.index)
    net, st = vc.bt(w, P["VIXY"], 5)
    rows[nm] = vc.split_row(net, {"2022+": vc.sh(net.loc["2022":]), "Exp": st["AvgExposure"]})
cnet, _ = vc.bt(pd.Series(np.where(cont, -1.0, 0), index=P.index), P["VIXY"], 5)
rows["carry lag1"] = vc.split_row(cnet, {"2022+": vc.sh(cnet.loc["2022":])})
print(pd.DataFrame(rows).T.round(2))
