"""session-momentum 03: year-by-year stability of the Thursday drag and of the TF skip-Thursday uplift,
plus cost sensitivity of the overlay."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
from ethdata import bars, bt, row, to_daily, trend_filter_weights_daily
h = bars("ETHUSDT", "1h"); c = h["Close"]
d = c.resample("1D").last()
w_tf = trend_filter_weights_daily(d).shift(1, freq="D").reindex(c.index, method="ffill").fillna(0)
flat = pd.Series(c.index.dayofweek == 3, index=c.index).astype(float).shift(-1).fillna(0)
dr = to_daily(c.pct_change().fillna(0))
thu = dr[dr.index.dayofweek == 3]; oth = dr[dr.index.dayofweek != 3]
tab = pd.DataFrame({"thu_bp": thu.groupby(thu.index.year).mean() * 1e4, "other_bp": oth.groupby(oth.index.year).mean() * 1e4})
a = to_daily(bt(w_tf, c)[0]); b = to_daily(bt(w_tf * (1 - flat), c)[0])
sh = lambda x: x.groupby(x.index.year).apply(lambda y: y.mean() / y.std() * np.sqrt(365))
tab["TF_Sh"] = sh(a); tab["TFskipThu_Sh"] = sh(b)
print(tab.round(2).to_string())
print("years with Thursday below other days:", int((tab.thu_bp < tab.other_bp).sum()), "of", len(tab))
for cb in [5, 10, 20]:
    print(cb, "bp:", {k: round(float(v), 2) for k, v in row(to_daily(bt(w_tf * (1 - flat), c, cost_bps=cb)[0]), ann=365).items() if k.startswith("Sh")},
          "TF:", {k: round(float(v), 2) for k, v in row(to_daily(bt(w_tf, c, cost_bps=cb)[0]), ann=365).items() if k.startswith("Sh")})
