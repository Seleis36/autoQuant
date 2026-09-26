"""Pre-declared families of SPY timing on vol-complex state. All index signals lagged 1 session
(VIX closes 16:15 ET) -- signal known at close t-1, weight held t -> t+1."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from ve_lib import long_panel, bt_excess, row

P = long_panel()
r = P["SPY"].pct_change()
vix = P["VIX"].shift(1); slope = (P["VIX3M"] / P["VIX"]).shift(1)
rv21 = (r.rolling(21).std() * np.sqrt(252) * 100)          # known at close t (SPY 16:00)
rv10 = (r.rolling(10).std() * np.sqrt(252) * 100)
vrp = vix - rv21                                           # VIX(t-1) vs RV through t
rows = {}
def add(name, w, start="1999-01-01"):
    net, we = bt_excess(w, P); rows[name] = row(net, we, start)
one = pd.Series(1.0, index=P.index)
add("SPY B&H", one); add("SPY B&H (06-07+)", one, "2006-08-01")
add("slope>1", (slope > 1).astype(float), "2006-08-01")
add("slope>0.95", (slope > 0.95).astype(float), "2006-08-01")
add("slope>1.05", (slope > 1.05).astype(float), "2006-08-01")
for tgt in (12, 15, 18):
    add(f"IV target {tgt}/VIX cap1.5", (tgt / vix).clip(upper=1.5))
    add(f"IV target {tgt}/VIX cap1.0", (tgt / vix).clip(upper=1.0))
for tgt in (12, 15):
    add(f"RV target {tgt}/RV21 cap1.5 (non-vol bench)", (tgt / rv21).clip(upper=1.5))
add("MM var-managed c/RV21^2 cap2", (1.0 / (rv21 / 16) ** 2).clip(upper=2.0))
add("MM var-managed via VIX^2 cap2", (1.0 / (vix / 18) ** 2).clip(upper=2.0))
add("VRP>0 (VIX>RV21)", (vrp > 0).astype(float))
add("VRP>0 else 0.5", np.where(vrp > 0, 1.0, 0.5))
add("VIX < MA20", (vix < vix.rolling(20).mean()).astype(float))
add("VIX < 1.1*MA20", (vix < 1.1 * vix.rolling(20).mean()).astype(float))
add("VIX < 30", (vix < 30).astype(float))
add("slope>1 x IV15 cap1.5", (slope > 1) * (15 / vix).clip(upper=1.5), "2006-08-01")
add("slope>1 or VIX<20", ((slope > 1) | (vix < 20)).astype(float), "2006-08-01")
add("slope>1 & VRP>0", ((slope > 1) & (vrp > 0)).astype(float), "2006-08-01")
add("contrarian: slope<0.9 -> 1.5x else 1", np.where(slope < 0.9, 1.5, 1.0), "2006-08-01")
res = pd.DataFrame(rows).T
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 20)
print(res.round(2))
