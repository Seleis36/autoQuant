"""session-momentum 02: costed seasonal / session strategies (10 bp per side).

A. standalone daily window holds: long ETH during UTC hours [a, b), flat otherwise.
B. conditional intraday momentum: long during [k, 24) only if the first k hours of the UTC day were up.
C. weekday overlays on the live trend filter: flat on day X, where X is picked on IS data only.
Hourly grid; trend-filter daily weight applied from 00:00 UTC of the following day.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import bars, bt, row, to_daily, trend_filter_weights_daily, IS_END

h = bars("ETHUSDT", "1h"); c = h["Close"]
hr = pd.Series(c.index.hour, index=c.index)
d = c.resample("1D").last()
w_tf = trend_filter_weights_daily(d).shift(1, freq="D").reindex(c.index, method="ffill").fillna(0)
tf, _ = bt(w_tf, c)
pd.set_option("display.width", 220, "display.max_rows", 300)
R = lambda net, **kw: row(to_daily(net), ann=365, extra=kw)

# weight at bar t applies to bar t+1's return: to be long DURING hour H, w must be 1 at bar H-1.
def window_weight(a, b):
    held = ((hr >= a) & (hr < b)) if a < b else ((hr >= a) | (hr < b))
    return held.astype(float).shift(-1).fillna(0)

print("A. standalone window holds")
rows = []
for a in range(0, 24, 2):
    for L in [2, 4, 6, 8, 12]:
        b = (a + L) % 24
        net, s = bt(window_weight(a, b), c)
        rows.append(R(net, a=a, b=b, Turn=s["Turnover_ann"]))
A = pd.DataFrame(rows)
print(A.sort_values("Sh_IS", ascending=False).head(10).round(2).to_string(index=False))
print("median", A[["Sh_Full", "Sh_IS", "Sh_OOS"]].median().round(2).to_dict(), "N", len(A))
for cb in [0, 2, 5]:
    net, _ = bt(window_weight(21, 23), c, cost_bps=cb)
    print(f"  21-23 UTC at {cb} bp:", {k: round(float(v), 2) for k, v in R(net).items() if k.startswith("Sh")})

print("\nB. conditional: long [k,24) if first k hours up")
lr = np.log(c).diff()
day = c.index.floor("D")
rows = []
for k in [4, 8, 12, 16, 20]:
    cum = lr.groupby(day).cumsum()                       # cumulative log return since 00:00 through bar t
    first_up = cum.where(hr == k - 1).groupby(day).transform("max") > 0   # known at close of bar k-1
    held = (hr >= k) & first_up
    net, s = bt(held.astype(float).shift(-1).fillna(0), c)
    rows.append(R(net, k=k, Turn=s["Turnover_ann"]))
    # as a tilt on the trend filter: in TF, add exposure only in the conditional window
    net2, _ = bt((w_tf + 0.5 * held.astype(float).shift(-1).fillna(0) * (w_tf > 0)).clip(upper=1), c)
    rows.append(R(net2, k=f"TF+0.5*cond{k}"))
print(pd.DataFrame(rows).round(2).to_string(index=False))

print("\nC. weekday overlays on the trend filter")
wd_ret = to_daily(np.log(c).diff().fillna(0)).loc[:IS_END]
wd_mean = wd_ret.groupby(wd_ret.index.dayofweek).mean()
worst = int(wd_mean.idxmin())
print("IS weekday means (bp):", (wd_mean * 1e4).round(1).to_dict(), "-> worst IS weekday", worst)
rows = [R(tf, v="TF (live)")]
for skip in [[worst], [3], [1, 3], [3, 6]]:
    flat = pd.Series(c.index.dayofweek, index=c.index).isin(skip).astype(float).shift(-1).fillna(0)
    net, s = bt(w_tf * (1 - flat), c)
    rows.append(R(net, v=f"TF skip {skip}", Turn=s["Turnover_ann"], rho=np.corrcoef(net, tf)[0, 1]))
print(pd.DataFrame(rows).round(2).to_string(index=False))
