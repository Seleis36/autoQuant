"""upshock-continuation 04: yearly Sharpe, cost sensitivity, deflated Sharpe for E x uptrend."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
from ethdata import rl, bars, bt, row, to_daily, trend_filter_weights_daily
h = bars("ETHUSDT", "1h"); c = h["Close"]
lr = np.log(c).diff(); sig = lr.ewm(halflife=168, min_periods=168).std()
up = (c > c.rolling(960, min_periods=960).mean()).astype(float)
def hold_weights(ev, H):
    ev = ev.fillna(False).astype(int); grp = ev.cumsum(); since = ev.groupby(grp).cumcount()
    return ((grp > 0) & (since < H)).astype(float)
cells = [hold_weights(np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k)) > Z, H)
         for k in [1, 2, 4, 8, 12] for Z in [2.0, 2.5, 3.0] for H in [12, 24, 48]]
w = pd.concat(cells, axis=1).mean(axis=1) * up
for cb in [0, 5, 10, 20, 30]:
    print("cost", cb, {k: round(float(v), 2) for k, v in row(to_daily(bt(w, c, cost_bps=cb)[0]), ann=365).items() if k.startswith("Sh")})
nd = to_daily(bt(w, c)[0])
print(nd.groupby(nd.index.year).agg(lambda x: x.mean() / x.std() * np.sqrt(365)).round(2).to_dict())
print(nd.groupby(nd.index.year).agg(lambda x: (1 + x).prod() - 1).round(3).to_dict())
s = rl.perf_stats(nd, ann=365)
for n in [12, 57, 129]:
    print("DSR n_trials", n, round(rl.deflated_sharpe(s["Sharpe"], len(nd), n, skew=s["Skew"], kurt=s["Kurt"] + 3, ann=365), 3))
