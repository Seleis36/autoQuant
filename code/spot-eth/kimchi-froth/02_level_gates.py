"""kimchi-froth 02: level-based froth gates (flat when the ETH kimchi premium > c) on the trend filter,
vol-scaled B&H and the eth-venue-premium strategy (daily-sampled kp applied to the hourly book)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eth-venue-premium"))
import numpy as np, pandas as pd
from ethdata import rl, bars, bt, row, to_daily, trend_filter_weights_daily
from fetch_upbit import load as up
from fetch_coinbase import load as cb_load
from strategy import target_weight
bn = bars("ETHUSDT", "1h")["Close"]
eth = bn.resample("1D").last().dropna()
fx = rl.load_series("KRW=X")["Close"].reindex(eth.index).ffill().shift(1)
kp = up("KRW-ETH")["Close"].reindex(eth.index) / (eth * fx) - 1
A = "2018-01-01"
vs = rl.vol_target_scalar(eth.pct_change(), target=0.5, halflife=20, cap=1.0)
w_tf = trend_filter_weights_daily(eth)
rows = []
for base_name, base in [("TF", w_tf), ("vs", vs)]:
    for c in [None, 0.03, 0.05, 0.08]:
        g = 1.0 if c is None else (kp <= c).astype(float)       # NaN kp -> 0 -> flat? treat NaN as pass
        if c is not None: g = g.where(kp.notna(), 1.0)
        net, st = rl.backtest(base * g, eth, cost_bps=10)
        rows.append(row(net.loc[A:], ann=365, extra=dict(v=f"{base_name} kp<={c}", off=(1 - g).loc[A:].mean() if c else 0)))
# on the hourly eth-venue-premium book: kp of day D (known at D+1 00:00) gates hours of D+1
w_vp = target_weight(bn, cb_load("ETH-USD")["Close"])
for c in [None, 0.03, 0.05, 0.08]:
    if c is None: g = 1.0
    else:
        gd = (kp <= c).astype(float).where(kp.notna(), 1.0)
        g = gd.shift(1, freq="D").reindex(bn.index, method="ffill").fillna(1.0)
    rows.append(row(to_daily(bt(w_vp * g, bn)[0]).loc[A:], ann=365, extra=dict(v=f"venue-prem kp<={c}")))
pd.set_option("display.width", 200)
print(pd.DataFrame(rows)[["v", "Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD", "off"]].round(3).to_string(index=False))
print("days kp>5%:", int((kp > 0.05).sum()), "by year:", (kp > 0.05).groupby(kp.index.year).sum().to_dict())
