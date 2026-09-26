"""Abnormal vol-ETP dollar volume: partial regression vs price state, then pre-declared gates.
Grid: feature in {abn_long, abn_inv, abn_all} x lookback short {5, 10} x threshold {0, 0.25, 0.5}
= 18 carry gates; plus ensemble; plus overlay on the COT book."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import statsmodels.api as sm
import vc_data as vc
from strategy import target_weight
from fetch_cot_vix import fetch_tff

P = vc.panel()
C = vc.load_close(["UVXY", "VIXY", "VXX", "SVXY"]).reindex(P.index)
V = vc.load_close(["UVXY", "VIXY", "VXX", "SVXY"], "Volume").reindex(P.index)
DV = (C * V).fillna(0)
legs = {"long": DV[["UVXY", "VIXY", "VXX"]].sum(axis=1), "inv": DV["SVXY"], "all": DV.sum(axis=1)}
def abn(x, s): return np.log(x.rolling(s).mean() / x.rolling(126).mean())
lr = np.log(P["VIXY"]).diff()
f21 = lr.shift(-1).rolling(21).sum().shift(-20)
X = pd.DataFrame({"abn": abn(legs["all"], 5), "logvix": np.log(P["VIX"]).shift(1),
                  "slope": (P["VIX3M"] / P["VIX"]).shift(1), "vixmom": np.log(P["VIX"] / P["VIX"].rolling(21).mean()).shift(1),
                  "vixy21": np.log(P["VIXY"]).diff(21)})
for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    d = pd.concat([X, f21.rename("y")], axis=1).loc[a:b].dropna().iloc[::5]
    m = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    print(k, "t-stats", m.tvalues.round(2).to_dict())
cont = ((P["VIX3M"] / P["VIX"]).shift(1) > 1)
carry = pd.Series(np.where(cont, -1.0, 0), index=P.index)
cot = target_weight(P["VIXY"], P["VIX"], P["VIX3M"], fetch_tff())
rows = {}
def run(nm, w):
    net, st = vc.bt(w.fillna(0), P["VIXY"], 5)
    rows[nm] = vc.split_row(net, {"2022+": vc.sh(net.loc["2022":]), "Exp": st["AvgExposure"], "TO": st["Turnover_ann"]}); return net
cn = run("carry lag1", carry); cotn = run("COT book", cot)
votes, votes_cot, votes_sa = [], [], []
for leg, x in legs.items():
    for s in (5, 10):
        a = abn(x, s)
        for th in (0.0, 0.25, 0.5):
            g = a > th
            run(f"carry & abn_{leg}{s}>{th}", carry.where(g, 0.0))
            votes.append(carry.where(g, 0.0)); votes_cot.append(np.minimum(cot, carry.where(g, 0.0)))
            votes_sa.append(pd.Series(np.where(g, -1.0, 0.0), index=P.index))
en = run("carry x ens18", sum(votes) / len(votes))
run("standalone short when abn>th, ens18 (no contango gate)", sum(votes_sa) / len(votes_sa))
# union with COT: max short of the two books; and average of the two books
u = run("avg(COT, carry x ens18)", (cot + sum(votes) / len(votes)) / 2)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 60); pd.set_option("display.max_columns", 20)
res = pd.DataFrame(rows).T
print(res.round(2))
print("median of 18 carry gates:", res.filter(like="carry & abn", axis=0)[["Sh", "IS", "OOS", "2022+"]].median().round(2).to_dict())
print("corr(ens18, COT) %.2f  corr(ens18, carry) %.2f" % (en.corr(cotn), en.corr(cn)))
