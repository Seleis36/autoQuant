"""Re-framings: (a) today's SPY move -> tomorrow's VIXY (vol overreaction to equity moves),
(b) VIXY-vs-VIXM curve residual reversal (front-end overreaction relative to mid-curve)."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel()
R = P[["VIXY", "VIXM", "SPY"]].pct_change()
zs = R["SPY"] / R["SPY"].rolling(63).std().shift(1)
fv = R["VIXY"].shift(-1)
for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    d = pd.concat([zs.rename("z"), fv.rename("f")], axis=1).loc[a:b].dropna()
    q = pd.cut(d["z"], [-99, -2, -1, -0.5, 0, 0.5, 1, 2, 99])
    g = d.groupby(q, observed=True)["f"].agg(["mean", "count"]); g["mean"] *= 1e4
    print(k, "\n", g.round(1).T)
rows = {}
def run(name, w, close=P["VIXY"], cost=5.0):
    net, st = vc.bt(w.fillna(0), close, cost); rows[name] = vc.split_row(net, {"Exp": st["AvgExposure"], "TO": st["Turnover_ann"]})
    return net
slope = (P["VIX3M"] / P["VIX"]).shift(1)
for th in (-0.5, -1.0, -1.5, -2.0):
    run(f"short VIXY after SPY z<{th}", pd.Series(np.where(zs < th, -1.0, 0.0), index=P.index))
    run(f"  same & contango(lag1)", pd.Series(np.where((zs < th) & (slope > 1), -1.0, 0.0), index=P.index))
run("lin L/S clip(z/2)", (zs / 2).clip(-1, 1))
run("long VIXY after SPY z>1", pd.Series(np.where(zs > 1, 1.0, 0.0), index=P.index))
# SPY-hedged: book = w*VIXY - w*beta*SPY
beta = (R["VIXY"].rolling(63).cov(R["SPY"]) / R["SPY"].rolling(63).var())
for th in (-1.0, -1.5):
    w = pd.Series(np.where(zs < th, -1.0, 0.0), index=P.index)
    W = pd.DataFrame({"VIXY": w, "SPY": -w * beta}).fillna(0)
    net, st = vc.bt_xs(W, P[["VIXY", "SPY"]], 5)
    rows[f"hedged short after z<{th}"] = vc.split_row(net, {"Exp": W["VIXY"].mean(), "TO": st["Turnover_ann"]})
# (b) curve residual: VIXY vs VIXM
bm = (R["VIXY"].rolling(63).cov(R["VIXM"]) / R["VIXM"].rolling(63).var())
res = R["VIXY"] - bm.shift(1) * R["VIXM"]
zr = res / res.rolling(63).std().shift(1)
for L in (1, 3, 5):
    zz = zr.rolling(L).sum() / np.sqrt(L)
    s = -(zz / 2).clip(-1, 1)                           # fade: residual up -> short VIXY / long beta*VIXM
    W = pd.DataFrame({"VIXY": s, "VIXM": -s * bm}).fillna(0)
    gross = W.abs().sum(axis=1).replace(0, np.nan)
    W = W.div(gross.clip(lower=1), axis=0).fillna(0)
    net, st = vc.bt_xs(W, P[["VIXY", "VIXM"]], 7)
    rows[f"curve resid fade L={L}"] = vc.split_row(net, {"Exp": W["VIXY"].mean(), "TO": st["Turnover_ann"]})
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).T.round(2))
