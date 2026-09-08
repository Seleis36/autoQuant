"""Compound signals: ETH trend + ETH-BTC ratio trend, plus vol targeting.

Ideas:
  A. ETH_SMA(fast) > ETH_SMA(slow): pure ETH trend baseline (long/flat).
  B. Ratio_SMA(fast) > Ratio_SMA(slow): pure ratio filter (already tested).
  C. A AND B: gated long only when both regimes agree.
  D. C + vol targeting.
  E. BTC trend + ratio trend (macro regime).
"""
import os, sys, itertools
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "code", "shared")))

import numpy as np, pandas as pd
from research_lib import load_btc, backtest, perf_stats, split_stats, fmt, vol_target_scalar, ANN

eth = load_btc(ticker="ETH-USD")["Close"].rename("ETH")
btc = load_btc(ticker="BTC-USD")["Close"].rename("BTC")
df = pd.concat([eth, btc], axis=1, sort=True).dropna()
ratio = df["ETH"] / df["BTC"]
eth_c = df["ETH"]; btc_c = df["BTC"]
eth_r = eth_c.pct_change()

def sma_cross(s, f, sl):
    return (s.rolling(f).mean() > s.rolling(sl).mean()).astype(float)

# A. ETH trend baseline
print("== A. Pure ETH trend (SMA crossover) ==")
rows = []
for f, s in itertools.product([5,10,20,30,50], [50,70,100,150,200]):
    if f>=s: continue
    w = sma_cross(eth_c, f, s)
    net, st = backtest(w, eth_c, cost_bps=10.0, name=f"eth_{f}_{s}")
    st["f"]=f; st["s"]=s
    rows.append(st)
A = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
print(fmt(A.head(8)))

# C. AND-gated: ETH trend AND ratio trend
print("\n== C. ETH trend AND ratio trend (gated long) ==")
rows = []
for (fe, se), (fr, sr) in itertools.product(
    [(20,100),(20,150),(30,100),(30,150),(50,150),(50,200)],
    [(20,100),(30,100),(50,150),(50,200),(30,150)]):
    w = sma_cross(eth_c, fe, se) * sma_cross(ratio, fr, sr)
    net, st = backtest(w, eth_c, cost_bps=10.0, name=f"eth{fe}_{se}_r{fr}_{sr}")
    st["fe"]=fe; st["se"]=se; st["fr"]=fr; st["sr"]=sr
    rows.append(st)
C = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
print(fmt(C.head(10)))

# D. Best C plus vol targeting
print("\n== D. Best-C + inverse-vol scalar (target 60% vol, cap 1.0) ==")
best = C.iloc[0]
fe, se, fr, sr = int(best.fe), int(best.se), int(best.fr), int(best.sr)
w_gate = sma_cross(eth_c, fe, se) * sma_cross(ratio, fr, sr)
for tgt in [0.4, 0.5, 0.6, 0.8, 1.0]:
    vs = vol_target_scalar(eth_r, target=tgt, halflife=20, cap=1.0)
    w = (w_gate * vs).clip(0, 1)
    net, st = backtest(w, eth_c, cost_bps=10.0, name=f"vt_{tgt}")
    print(f"target={tgt}: Sharpe={st['Sharpe']:.2f} CAGR={st['CAGR']*100:.1f}% MaxDD={st['MaxDD']*100:.1f}% Exp={st['AvgExposure']*100:.1f}%")

# E. Macro: BTC trend AND ratio trend → long ETH
print("\n== E. BTC trend AND ratio trend → long ETH ==")
rows = []
for (fb, sb), (fr, sr) in itertools.product(
    [(20,100),(30,150),(50,200),(20,200)],
    [(20,100),(30,100),(50,150),(50,200)]):
    w = sma_cross(btc_c, fb, sb) * sma_cross(ratio, fr, sr)
    net, st = backtest(w, eth_c, cost_bps=10.0, name=f"btc{fb}_{sb}_r{fr}_{sr}")
    st["fb"]=fb; st["sb"]=sb; st["fr"]=fr; st["sr"]=sr
    rows.append(st)
E = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
print(fmt(E.head(10)))
