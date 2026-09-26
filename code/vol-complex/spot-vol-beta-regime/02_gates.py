"""Pre-declared grid: short VIXY in contango(lag1) only when spot-vol correlation is 'normal'
(feature below its own rolling-252 quantile q). Features x q = 4 x 3 = 12, plus overlay on the
idea-1 COT book, plus a long-VIXY 'fragility' leg."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import vc_data as vc
from strategy import target_weight
from fetch_cot_vix import fetch_tff

P = vc.panel()
R = P[["VIXY", "SPY"]].pct_change()
dv = np.log(P["VIX"]).diff()
F = {"corr10": R["VIXY"].rolling(10).corr(R["SPY"]), "corr21": R["VIXY"].rolling(21).corr(R["SPY"]),
     "corrvix10": dv.rolling(10).corr(R["SPY"]).shift(1),
     "corr21rel": R["VIXY"].rolling(21).corr(R["SPY"]) - R["VIXY"].rolling(252).corr(R["SPY"])}
cont = ((P["VIX3M"] / P["VIX"]).shift(1) > 1)
carry = pd.Series(np.where(cont, -1.0, 0), index=P.index)
cot = target_weight(P["VIXY"], P["VIX"], P["VIX3M"], fetch_tff())
rows = {}
def run(nm, w, cost=5.0):
    net, st = vc.bt(w.fillna(0), P["VIXY"], cost)
    rows[nm] = vc.split_row(net, {"2022+": vc.sh(net.loc["2022":]), "Exp": st["AvgExposure"]}); return net
cn = run("carry lag1", carry)
cotn = run("COT book (idea 1)", cot)
votes_c, votes_cot = [], []
for fn, f in F.items():
    for q in (0.5, 0.7, 0.85):
        thr = f.rolling(252, min_periods=126).quantile(q)
        ok = (f < thr)
        run(f"carry & {fn}<q{q}", carry.where(ok, 0.0))
        run(f"COT & {fn}<q{q}", cot.where(ok, 0.0))
        votes_c.append(carry.where(ok, 0.0)); votes_cot.append(cot.where(ok, 0.0))
run("carry x ens12 (selection-free)", sum(votes_c) / len(votes_c))
en = run("COT x ens12 (selection-free)", sum(votes_cot) / len(votes_cot))
# fragility long-vol leg: long VIXY when corr21rel above its q0.9 and backwardation-free
thr = F["corr21rel"].rolling(252, min_periods=126).quantile(0.9)
run("long VIXY when corr21rel > q0.9", pd.Series(np.where(F["corr21rel"] > thr, 1.0, 0.0), index=P.index))
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 100)
res = pd.DataFrame(rows).T
print(res.round(2))
print("median carry-gated: ", res.filter(like="carry &", axis=0)[["Sh", "IS", "OOS"]].median().round(2).to_dict())
print("median COT-gated:   ", res.filter(like="COT &", axis=0)[["Sh", "IS", "OOS"]].median().round(2).to_dict())
print("corr(COT book, COTxens12) %.2f" % cotn.corr(en))
