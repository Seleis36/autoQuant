"""CBOE SKEW (SPX OTM-put richness) -> forward VIXY returns, spikes; attribution vs VIX level/slope.
SKEW is an index computed like VIX (closing 16:15-ish) -> lagged 1 session everywhere."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import statsmodels.api as sm
import vc_data as vc, research_lib as rl
from strategy import scores_on_sessions
from fetch_cot_vix import fetch_tff

P = vc.panel()
sk = rl.load_series("^SKEW")["Close"].reindex(P.index).ffill().shift(1)
vix = P["VIX"].shift(1)
F = pd.DataFrame({"skew": sk, "skew_z252": (sk - sk.rolling(252).mean()) / sk.rolling(252).std(),
                  "skew_d5": sk.diff(5), "skew_d21": sk.diff(21),
                  "skew_over_vix": sk / vix, "skew_resid_vix": sk - sk.rolling(252).cov(np.log(vix)) / np.log(vix).rolling(252).var() * np.log(vix)})
lr = np.log(P["VIXY"]).diff()
fwd = {h: lr.shift(-1).rolling(h).sum().shift(-(h - 1)) for h in (5, 21, 63)}
spike = P["VIX"].shift(-1).rolling(21).max().shift(-20) / P["VIX"] - 1
rows = []
for c in F.columns:
    row = {"f": c}
    for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
        for h, f in fwd.items():
            d = pd.concat([F[c], f], axis=1).loc[a:b].dropna().iloc[::5]
            row[f"ic{h}_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
        d = pd.concat([F[c], spike], axis=1).loc[a:b].dropna().iloc[::5]
        row[f"spk_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
    rows.append(row)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).set_index("f").round(3))
S = scores_on_sessions(fetch_tff(), P.index).mean(axis=1)
print("corr with COT score:", F.corrwith(S).round(2).to_dict())
print("corr with log VIX:", F.corrwith(np.log(vix)).round(2).to_dict())
f21 = fwd[21]
X = pd.DataFrame({"skew_z": F["skew_z252"], "logvix": np.log(vix), "slope": (P["VIX3M"] / P["VIX"]).shift(1)})
for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
    d = pd.concat([X, f21.rename("y")], axis=1).loc[a:b].dropna().iloc[::5]
    m = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    print(k, "t", m.tvalues.round(2).to_dict())
