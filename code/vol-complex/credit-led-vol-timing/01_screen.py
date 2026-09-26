"""Credit -> vol lead-lag. Credit excess return proxy: HYG minus beta*IEF (rolling 252-day hedge ratio),
and LQD minus beta*IEF. All 16:00 closes. Features -> forward VIXY returns / VIX spikes."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel()
R = P[["HYG", "LQD", "IEF", "SPY", "VIXY"]].pct_change()
def hedged(a, b="IEF", w=252):
    beta = (R[a].rolling(w).cov(R[b]) / R[b].rolling(w).var()).shift(1)
    return R[a] - beta * R[b]
cx = {"HY": hedged("HYG"), "IG": hedged("LQD")}
# credit residual vs SPY too (credit-specific info beyond equity)
beta_hs = (cx["HY"].rolling(252).cov(R["SPY"]) / R["SPY"].rolling(252).var()).shift(1)
cx["HYresSPY"] = cx["HY"] - beta_hs * R["SPY"]
F = {}
for k, s in cx.items():
    for w in (1, 5, 10, 21, 63):
        F[f"{k}_{w}"] = s.rolling(w).sum()
# drawdown of HYG from 63d high (credit stress)
F["HYG_dd63"] = P["HYG"] / P["HYG"].rolling(63).max() - 1
F["HY_vs_SPY_21"] = cx["HY"].rolling(21).sum() - (R["SPY"].rolling(21).sum()) * 0.3
F = pd.DataFrame(F)
lr = np.log(P["VIXY"]).diff()
fwd = {h: lr.shift(-1).rolling(h).sum().shift(-(h - 1)) for h in (1, 5, 21)}
rows = []
for c in F.columns:
    row = {"f": c}
    for k, (a, b) in {"IS": vc.IS, "OOS": vc.OOS}.items():
        for h, f in fwd.items():
            d = pd.concat([F[c], f], axis=1).loc[a:b].dropna()
            d = d.iloc[::max(1, h)]
            row[f"ic{h}_{k}"] = d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")
    rows.append(row)
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).set_index("f").round(3))
print("corr with SPY 21d return:", F.corrwith(R["SPY"].rolling(21).sum()).round(2).to_dict())
