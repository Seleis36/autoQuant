"""Day-by-day profile: slope of the return on relative day j (j=-6..+3 around the last
session L, j=+1 = first session of next month) on the drift measured from the previous
month-end through the close of day j-1 (j <= 0) or through L (j >= 1, completed month)."""
import sys, os
import numpy as np, pandas as pd
from lib import load, spreads, month_end_positions, SPL
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

C, R = load()
B = D.load_panel(["TLT", "IEF"], start="1998-12-01").pct_change()
S = spreads(R)
idx = S.index; pe = month_end_positions(idx)
drifts = {"US-INTL": S["spy"] - S["intl"], "US-TLT": S["spy"] - B["TLT"]}
vols = {k: v.rolling(252, min_periods=126).std().shift(1) for k, v in drifts.items()}
outs = {"SPY": S["spy"].values, "INTL": S["intl"].values, "hedged": S["hedged"].values}

def slope(x, y):
    ok = np.isfinite(x) & np.isfinite(y); x, y = x[ok], y[ok]
    X = x - x.mean(); b = (X * y).sum() / (X ** 2).sum()
    res = y - y.mean() - b * X
    return b * 1e4, b / np.sqrt((res ** 2).sum() / (len(y) - 2) / (X ** 2).sum())

for dn, dr in drifts.items():
    for on, y in outs.items():
        res = {}
        for j in range(-6, 4):
            xs, ys, ds = [], [], []
            for a, b in zip(pe[:-1], pe[1:]):
                end = b + j - 1 if j <= 0 else b
                p = b + j
                if end - a < 4 or p >= len(idx): continue
                xs.append(dr.iloc[a + 1:end + 1].sum() / (vols[dn].iloc[end] * np.sqrt(end - a)))
                ys.append(y[p]); ds.append(idx[b])
            xs, ys, ds = np.array(xs), np.array(ys), pd.DatetimeIndex(ds)
            for pn, (a_, b_) in SPL.items():
                m = (ds >= a_) & (ds <= b_)
                res.setdefault(pn, {})[j] = "%5.1f(%5.2f)" % slope(xs[m], ys[m])
        print(f"\n=== drift {dn} -> outcome {on}  [bp per z (t)] by relative day")
        print(pd.DataFrame(res).T.to_string())
