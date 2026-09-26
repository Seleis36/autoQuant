"""SKEW: partial regressions (level / VIX-orthogonal residual, with COT score), then a pre-declared
grid of gates: short VIXY in contango(lag1) only when SKEW measure < its rolling-252 quantile q.
Measures {skew level, skew_resid_vix} x q {0.5, 0.7, 0.85} on carry and on the COT book."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import statsmodels.api as sm
import vc_data as vc, research_lib as rl
from strategy import scores_on_sessions, target_weight
from fetch_cot_vix import fetch_tff

P = vc.panel()
sk = rl.load_series("^SKEW")["Close"].reindex(P.index).ffill().shift(1)
lvix = np.log(P["VIX"].shift(1))
b = (sk.rolling(252).cov(lvix) / lvix.rolling(252).var())
resid = sk - b * lvix
tff = fetch_tff()
S = scores_on_sessions(tff, P.index).mean(axis=1)
lr = np.log(P["VIXY"]).diff(); f21 = lr.shift(-1).rolling(21).sum().shift(-20)
for nm, s in (("skew", sk), ("skew_resid", resid)):
    X = pd.DataFrame({nm: (s - s.rolling(252).mean()) / s.rolling(252).std() if nm == "skew" else s / s.rolling(252).std(),
                      "logvix": lvix, "slope": (P["VIX3M"] / P["VIX"]).shift(1), "cot": S})
    for k, (a, bb) in {"IS": vc.IS, "OOS": vc.OOS}.items():
        d = pd.concat([X, f21.rename("y")], axis=1).loc[a:bb].dropna().iloc[::5]
        m = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
        print(nm, k, "t", m.tvalues.round(2).to_dict())
cont = ((P["VIX3M"] / P["VIX"]).shift(1) > 1)
carry = pd.Series(np.where(cont, -1.0, 0), index=P.index)
cot = target_weight(P["VIXY"], P["VIX"], P["VIX3M"], tff)
rows = {}
def run(nm, w):
    net, st = vc.bt(w.fillna(0), P["VIXY"], 5)
    rows[nm] = vc.split_row(net, {"2022+": vc.sh(net.loc["2022":]), "Exp": st["AvgExposure"]}); return net
run("carry lag1", carry); run("COT book", cot)
vc_, vcot = [], []
for nm, s in (("skew", sk), ("resid", resid)):
    for q in (0.5, 0.7, 0.85):
        ok = s < s.rolling(252, min_periods=126).quantile(q)
        run(f"carry & {nm}<q{q}", carry.where(ok, 0.0)); vc_.append(carry.where(ok, 0.0))
        run(f"COT & {nm}<q{q}", cot.where(ok, 0.0)); vcot.append(cot.where(ok, 0.0))
run("carry x ens6", sum(vc_) / 6); run("COT x ens6", sum(vcot) / 6)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 20)
res = pd.DataFrame(rows).T; print(res.round(2))
