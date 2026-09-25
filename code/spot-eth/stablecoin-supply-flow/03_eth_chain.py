"""stablecoin-supply-flow 03: stablecoins on the Ethereum chain (DefiLlama), 2020-06+ where coverage
is complete. Growth of ETH-chain supply and Ethereum's share of all stablecoins. Same lag rule
(value stamped D-1 used at bar D's close)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
from ethdata import rl, bars, row, trend_filter_weights_daily
from fetch_stablecoins import load as dl
eth = bars("ETHUSDT", "1h").resample("1D").agg({"Close": "last"})["Close"].dropna()
E = dl("ETHEREUM").reindex(eth.index).ffill().shift(1); T = dl("ALL").reindex(eth.index).ffill().shift(1)
share = E / T
vs = rl.vol_target_scalar(eth.pct_change(), target=0.5, halflife=20, cap=1.0)
A = "2020-06-01"
tf, _ = rl.backtest(trend_filter_weights_daily(eth), eth, cost_bps=10)
print("TF 2020-06+:", {k: round(float(v), 2) for k, v in row(tf.loc[A:], ann=365).items() if k.startswith("Sh")})
bh, _ = rl.backtest(vs, eth, cost_bps=10)
print("vs B&H 2020-06+:", {k: round(float(v), 2) for k, v in row(bh.loc[A:], ann=365).items() if k.startswith("Sh")})
for name, x in [("eth-chain supply", E), ("eth share", share), ("all supply", T)]:
    for n in [7, 30]:
        g = np.log(x / x.shift(n))
        net, st = rl.backtest((g > 0).astype(float) * vs, eth, cost_bps=10); net = net.loc[A:]
        print(f"{name:16s} g{n}>0 x vs:", {k: round(float(v), 2) for k, v in row(net, ann=365).items() if k in ("Sh_Full", "Sh_IS", "Sh_OOS", "MDD")},
              "rho_tf", round(net.corr(tf.loc[A:]), 2), "TIM", round(st["TimeInMkt"], 2))
