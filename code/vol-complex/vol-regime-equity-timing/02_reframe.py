"""Re-framings: (a) BTZ-style monthly VRP (VIX^2 - RV^2) predicting 1-3 month SPY returns,
(b) COT vol-ETP crowding (idea 1) as SPY risk gate, (c) weekly rebalanced slope/IV versions."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "vix-cot-positioning"))
import numpy as np, pandas as pd
import statsmodels.api as sm
from ve_lib import long_panel, bt_excess, row, SPL
from strategy import scores_on_sessions
from fetch_cot_vix import fetch_tff

P = long_panel()
r = P["SPY"].pct_change()
rf = (P["IRX"] / 100 / 252).shift(1)
ex = r - rf
vix = P["VIX"].shift(1)
rv2 = (r ** 2).rolling(21).sum() * 252 / 21 * 1e4     # annualised variance in VIX^2 units
vrp = vix ** 2 - rv2                                 # known at close t
# month-end sampling
me = P.index.to_series().groupby([P.index.year, P.index.month]).last().values
M = pd.DataFrame({"vrp": vrp.loc[me], "vix": vix.loc[me]}, index=pd.DatetimeIndex(me))
lp = np.log(P["SPY"])
for h in (1, 3):
    fwd = (lp.shift(-21 * h) - lp).loc[me]
    for k, (a, b) in SPL.items():
        d = pd.concat([M["vrp"], fwd.rename("f")], axis=1).loc[a:b].dropna()
        m = sm.OLS(d["f"], sm.add_constant(d["vrp"] / 100)).fit(cov_type="HAC", cov_kwds={"maxlags": 3 * h})
        print(f"h={h}m {k:10s} n={len(d)} beta={m.params.iloc[1]:.4f} t={m.tvalues.iloc[1]:.2f} R2={m.rsquared:.3f}")
rows = {}
def add(name, w, start="1999-01-01"):
    net, we = bt_excess(w, P); rows[name] = row(net, we, start)
add("SPY B&H", pd.Series(1.0, index=P.index))
# monthly VRP rule: weight fixed through the month from month-end t signal
z = (M["vrp"] - M["vrp"].expanding(36).mean()) / M["vrp"].expanding(36).std()
for k in (0.25, 0.5):
    wm = (1 + k * z).clip(0, 1.5)
    add(f"monthly 1+{k}*z(VRP)", wm.reindex(P.index).ffill())
add("monthly VRP>0", (M["vrp"] > 0).astype(float).reindex(P.index).ffill())
add("monthly VRP>median(exp)", (M["vrp"] > M["vrp"].expanding(36).median()).astype(float).reindex(P.index).ffill())
# COT crowding gate on SPY
S = scores_on_sessions(fetch_tff(), P.index)
avgz = S.mean(axis=1)
add("COT: SPY 1 unless avg z < -1 (0.5)", np.where(avgz < -1, 0.5, 1.0), "2008-01-01")
add("COT: SPY 1+0.25*avgz clip", (1 + 0.25 * avgz).clip(0.5, 1.5).fillna(1), "2008-01-01")
add("SPY B&H 08+", pd.Series(1.0, index=P.index), "2008-01-01")
# weekly-rebalanced versions (reduce the 1-day-lag whipsaw)
fri = P.index.to_series().dt.dayofweek == 4
for nm, w in {"slope>1": ((P["VIX3M"] / P["VIX"]).shift(1) > 1).astype(float),
              "IV15 cap1.5": (15 / vix).clip(upper=1.5)}.items():
    add(f"weekly {nm}", w.where(fri).ffill(), "2006-08-01" if "slope" in nm else "1999-01-01")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 20)
print(pd.DataFrame(rows).T.round(2))
