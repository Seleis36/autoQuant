"""Market-level analogue: does SPY's (or the EW sector basket's) past-k overnight return
predict its next-h return (time series)? Non-overlapping correlations, t-stats."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx
c = data.load_panel(); o = data.load_panel(field="Open")
on = np.log(o / c.shift(1))["SPY"]; cc = np.log(c["SPY"]).diff()
for k, h in itertools.product([21, 63, 126, 252], [5, 21, 63]):
    x = on.rolling(k).sum(); y = cc.rolling(h).sum().shift(-h)
    out = []
    for a, b in [sx.IS, sx.OOS]:
        xx = x.loc[a:b].iloc[::h]; yy = y.loc[a:b].iloc[::h]; m = xx.notna() & yy.notna()
        cr = np.corrcoef(xx[m], yy[m])[0, 1]; out.append(f"{cr:+.3f} (t {cr*np.sqrt(m.sum()):+.1f})")
    print(f"k{k:>3} h{h:>2}  IS {out[0]}  OOS {out[1]}")
