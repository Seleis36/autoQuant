"""exchange-netflow 02: price/flow divergence. Accumulation = ETH down over n days while net
outflow z > Z (bullish); distribution = ETH up while net inflow z > Z (bearish -> veto the TF)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily, IS_END, OOS_START
from coinmetrics import load
eth = bars("ETHUSDT", "1h").resample("1D").agg({"Close": "last"})["Close"].dropna()
m = load("eth").reindex(eth.index).shift(1)
z = lambda x: (x - x.rolling(365, min_periods=180).mean()) / x.rolling(365, min_periods=180).std()
A = "2018-06-01"; rows = []
for n in [3, 7, 14]:
    nfz = z((m.FlowInExNtv - m.FlowOutExNtv).rolling(n).sum() / m.SplyCur)
    pr = np.log(eth / eth.shift(n))
    for Z in [0.5, 1.0, 1.5]:
        for name, ev in [("accum: px<0 & outflow", (pr < 0) & (nfz < -Z)), ("distrib: px>0 & inflow", (pr > 0) & (nfz > Z))]:
            for H in [7, 30]:
                fwd = np.log(eth.shift(-H) / eth); rr = dict(n=n, Z=Z, ev=name, H=H)
                for part, (a, b) in {"IS": (A, IS_END), "OOS": (OOS_START, None)}.items():
                    f = fwd[ev].loc[a:b].dropna(); u = fwd.loc[a:b].dropna()
                    rr[f"n_{part}"] = len(f); rr[f"ex_bp_{part}"] = round((f.mean() - u.mean()) * 1e4)
                    rr[f"t_{part}"] = round((f.mean() - u.mean()) / f.std() * np.sqrt(len(f) / H), 2)
                rows.append(rr)
pd.set_option("display.width", 200)
print(pd.DataFrame(rows).to_string(index=False))
# distribution veto on the trend filter
w_tf = trend_filter_weights_daily(eth); tf, _ = rl.backtest(w_tf, eth, cost_bps=10)
print("TF:", {k: round(float(v), 2) for k, v in row(tf.loc[A:], ann=365).items() if k.startswith("Sh")})
for n in [7, 14]:
    nfz = z((m.FlowInExNtv - m.FlowOutExNtv).rolling(n).sum() / m.SplyCur)
    for Z in [1.0, 1.5]:
        veto = ((np.log(eth / eth.shift(n)) > 0) & (nfz > Z)).astype(float)
        net, _ = rl.backtest(w_tf * (1 - veto), eth, cost_bps=10)
        print(f"TF with distribution veto n{n} Z{Z}:", {k: round(float(v), 2) for k, v in row(net.loc[A:], ann=365).items() if k.startswith("Sh")})
