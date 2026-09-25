"""upshock-continuation 03: is E x uptrend additive to the live trend filter?
Daily-return regression on the trend filter (alpha, t_NW) per half, and return blends."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
from ethdata import rl, bars, bt, row, to_daily, trend_filter_weights_daily, IS_END, OOS_START
exec(open(os.path.join(os.path.dirname(__file__), "02_ensemble.py")).read().split("cells = []")[0])
cells = []
for k in [1, 2, 4, 8, 12]:
    z = np.log(c / c.shift(k)) / (sig.shift(k) * np.sqrt(k))
    for Z in [2.0, 2.5, 3.0]:
        for H in [12, 24, 48]:
            cells.append(hold_weights(z > Z, H))
E = pd.concat(cells, axis=1).mean(axis=1)
d = c.resample("1D").last()
w_tf = trend_filter_weights_daily(d).shift(1, freq="D").reindex(c.index, method="ffill").fillna(0)
tf = to_daily(bt(w_tf, c)[0]); eu = to_daily(bt(E * up, c)[0]); e = to_daily(bt(E, c)[0])
for name, y in [("E x uptrend", eu), ("E", e)]:
    for part, (a, b) in {"IS": (None, IS_END), "OOS": (OOS_START, None)}.items():
        Y = y.loc[a:b]; X = tf.loc[a:b]
        beta = np.cov(Y, X)[0, 1] / X.var()
        res = Y - beta * X
        print(f"{name:12s} {part}: beta {beta:.2f} alpha/yr {res.mean()*365*100:.1f}% t_NW {rl.newey_west_t(res.values):.2f}  IR {res.mean()/res.std()*np.sqrt(365):.2f}")
for wE in [0.0, 0.25, 0.5]:
    # E x uptrend scaled 3x (avg exposure 0.11 -> ~0.33, comparable to trend filter), capped by total 1
    bl = (1 - wE) * tf + wE * to_daily(bt((3 * E * up).clip(upper=1), c)[0])
    print(wE, {k: round(v, 2) for k, v in row(bl, ann=365).items()})
