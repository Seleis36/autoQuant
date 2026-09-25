"""stablecoin-supply-flow 02: (a) is the short-horizon growth gate additive to the trend filter?
(b) Griffin-Shams style mint events: large daily net issuance, alone and after ETH declines.
Same timing as 01 (supply stamped D-1 used at bar D's close)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START
from coinmetrics import load

eth = bars("ETHUSDT", "1h").resample("1D").agg({"Close": "last"})["Close"].dropna()
S = sum(load(a, ["SplyCur"])["SplyCur"].fillna(0) for a in ["usdt", "usdc", "busd", "dai"])
S = S.reindex(eth.index).ffill().shift(1)
r = eth.pct_change()
vs = rl.vol_target_scalar(r, target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
A = "2018-06-01"
tf, _ = rl.backtest(w_tf, eth, cost_bps=10); tf = tf.loc[A:]

print("(a) additivity of growth gates vs trend filter")
for n in [3, 7, 14]:
    g = np.log(S / S.shift(n))
    w = (g > 0).astype(float) * vs
    net, st = rl.backtest(w, eth, cost_bps=10); net = net.loc[A:]
    line = f"g{n}>0 x vs: " + " ".join(f"{k}={v:.2f}" for k, v in row(net, ann=365).items() if k.startswith("Sh"))
    for part, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
        Y, X = net.loc[a:b], tf.loc[a:b]
        beta = np.cov(Y, X)[0, 1] / X.var(); res = Y - beta * X
        line += f" | {part} beta {beta:.2f} alpha t {rl.newey_west_t(res.values):.2f}"
    print(line)
    for wt in [0.3, 0.5]:
        bl = (1 - wt) * tf + wt * net
        print(f"   blend {wt}:", {k: round(float(v), 2) for k, v in row(bl, ann=365).items() if k in ("Sh_Full", "Sh_IS", "Sh_OOS", "MDD")})

print("\n(b) mint events: daily net issuance above trailing-365d q-quantile; forward ETH log returns")
g1 = np.log(S / S.shift(1))
prev7 = np.log(eth / eth.shift(7))
rows = []
for q in [0.8, 0.9, 0.95]:
    thr = g1.rolling(365, min_periods=180).quantile(q)
    for cond in ["all", "after ETH -7d<0", "after ETH -7d>0"]:
        ev = g1 > thr
        if cond == "after ETH -7d<0": ev &= prev7 < 0
        if cond == "after ETH -7d>0": ev &= prev7 > 0
        for H in [1, 3, 7]:
            fwd = np.log(eth.shift(-H) / eth)
            rr = dict(q=q, cond=cond, H=H)
            for part, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
                f = fwd[ev].loc[a:b].dropna(); u = fwd.loc[a:b].dropna()
                rr[f"n_{part}"] = len(f)
                rr[f"ex_bp_{part}"] = (f.mean() - u.mean()) * 1e4
                # overlapping windows for H>1: deflate t by sqrt(H)
                rr[f"t_{part}"] = (f.mean() - u.mean()) / f.std() * np.sqrt(len(f) / H)
            rows.append(rr)
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).round(2).to_string(index=False))
