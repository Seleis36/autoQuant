"""First backtests: VIXY weight driven by asset-manager / leveraged-fund net positioning."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import vc_data as vc
from cot_lib import session_features

P = vc.panel()
F = session_features(P.index)
px = P["VIXY"]
slope = P["VIX3M"] / P["VIX"]
carry = pd.Series(np.where(slope > 1, -1.0, 0.0), index=P.index)
rows = {}
def run(name, w, close=px, cost=5.0):
    net, st = vc.bt(w.fillna(0), close, cost)
    rows[name] = vc.split_row(net, {"TO": st["Turnover_ann"], "Exp": st["AvgExposure"]})
    return net

base = run("short always", pd.Series(-1.0, index=P.index))
ref = run("carry ref (slope>1)", carry)
for sig in ["am_net", "am_net_z52", "am_net_z104", "am_net_z156", "am_net_pct104",
            "lev_net_z52", "lev_net_z104", "lev_net_z156", "oth_net_z104", "dealer_net_z104"]:
    s = F[sig]
    sgn = -1 if sig.startswith("am") or sig.startswith("dealer") else 1   # am high -> short VIXY
    if "pct" in sig:
        z = (s - 0.5) * 4
    elif sig == "am_net":
        z = (s - s.expanding(52*5).median()) / 0.08
    else:
        z = s
    w_ls = (sgn * z).clip(-1, 1)
    run(f"{sig} lin L/S", w_ls)
    run(f"{sig} sign L/S", np.sign(sgn * z))
    run(f"{sig} short-only", (sgn * z).clip(-1, 0).where(sgn * z < 0, 0) * 0 + np.where(sgn * z < 0, -1.0, 0.0))
    run(f"{sig} gate carry", carry.where(sgn * z < 0, 0.0))
res = pd.DataFrame(rows).T
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
print(res.round(2))
