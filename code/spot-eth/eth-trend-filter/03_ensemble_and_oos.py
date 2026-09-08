"""Fine search + ensemble + OOS split.

- Fine grid around the winning ETH SMA(5,50).
- Multi-window ensemble (average of trend booleans).
- Add BTC-trend co-signal as a leading indicator.
- Full-sample vs IS (till 2023-12-31) vs OOS (2024-01-01 onward).
"""
import os, sys, itertools
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "code", "shared")))

import numpy as np, pandas as pd
from research_lib import load_btc, backtest, perf_stats, split_stats, fmt

eth = load_btc(ticker="ETH-USD")["Close"].rename("ETH")
btc = load_btc(ticker="BTC-USD")["Close"].rename("BTC")
df = pd.concat([eth, btc], axis=1, sort=True).dropna()
ratio = df["ETH"] / df["BTC"]
eth_c = df["ETH"]; btc_c = df["BTC"]

IS_END = "2023-12-31"
OOS_START = "2024-01-01"

def sma_cross(s, f, sl):
    return (s.rolling(f).mean() > s.rolling(sl).mean()).astype(float)

def price_above_sma(s, w):
    return (s > s.rolling(w).mean()).astype(float)

def eval_w(w, close, name):
    net, st = backtest(w, close, cost_bps=10.0, name=name)
    is_st = perf_stats(net.loc[:IS_END], name=f"{name}_IS")
    oos_st = perf_stats(net.loc[OOS_START:], name=f"{name}_OOS")
    return st, is_st, oos_st

print("== Fine grid on ETH SMA-cross, IS+OOS ==")
rows = []
for f, s in itertools.product([3,5,7,10,15,20,25,30,40,50], [30,50,70,100,120,150,200]):
    if f >= s: continue
    w = sma_cross(eth_c, f, s)
    st, ist, oost = eval_w(w, eth_c, f"{f}_{s}")
    rows.append({"f":f, "s":s, "Full_Sh":st.Sharpe, "IS_Sh":ist.Sharpe, "OOS_Sh":oost.Sharpe,
                 "CAGR":st.CAGR, "MDD":st.MaxDD, "TIM":st.TimeInMkt})
G = pd.DataFrame(rows).sort_values("OOS_Sh", ascending=False)
print(G.head(15).round(3).to_string(index=False))
print("\nSorted by IS_Sh:")
print(G.sort_values("IS_Sh", ascending=False).head(10).round(3).to_string(index=False))

# Multi-window trend ensemble
print("\n== Ensemble: average of multiple SMA long/flat booleans ==")
ensembles = {
    "eth_e1": [(10,50),(20,100),(30,150),(50,200)],
    "eth_e2": [(5,50),(10,100),(20,150),(30,200)],
    "eth_e3": [(5,30),(10,60),(20,120),(40,200)],
    "eth_e4": [(5,50),(20,100),(50,200)],
}
for name, combo in ensembles.items():
    ws = pd.concat([sma_cross(eth_c, f, s) for f,s in combo], axis=1)
    w = ws.mean(axis=1)
    st, ist, oost = eval_w(w, eth_c, name)
    print(f"{name}: Full Sh={st.Sharpe:.2f} IS Sh={ist.Sharpe:.2f} OOS Sh={oost.Sharpe:.2f} "
          f"CAGR={st.CAGR*100:.1f}% MDD={st.MaxDD*100:.1f}% TIM={st.TimeInMkt*100:.1f}%")

# BTC as co-signal
print("\n== ETH trend * BTC trend (both must be up) ==")
for (fe, se), (fb, sb) in [((5,50),(5,50)),((10,100),(20,100)),((20,100),(50,200)),
                            ((30,150),(50,200)),((10,50),(20,150)),((5,50),(50,200))]:
    w = sma_cross(eth_c, fe, se) * sma_cross(btc_c, fb, sb)
    st, ist, oost = eval_w(w, eth_c, "eb")
    print(f"ETH({fe},{se}) & BTC({fb},{sb}): Full Sh={st.Sharpe:.2f} IS={ist.Sharpe:.2f} OOS={oost.Sharpe:.2f} "
          f"CAGR={st.CAGR*100:.1f}% MDD={st.MaxDD*100:.1f}% TIM={st.TimeInMkt*100:.1f}%")

# Simple ETH-vs-own-SMA
print("\n== ETH price > own SMA(w) ==")
for w_win in [30,50,70,100,150,200]:
    w = price_above_sma(eth_c, w_win)
    st, ist, oost = eval_w(w, eth_c, f"above_{w_win}")
    print(f"above SMA({w_win}): Full Sh={st.Sharpe:.2f} IS={ist.Sharpe:.2f} OOS={oost.Sharpe:.2f} "
          f"CAGR={st.CAGR*100:.1f}% MDD={st.MaxDD*100:.1f}% TIM={st.TimeInMkt*100:.1f}%")

# ETH trend + BTC trend, ensemble
print("\n== Ensemble: ETH & BTC trend booleans averaged ==")
combo = [(sma_cross(eth_c, f, s), sma_cross(btc_c, f, s)) for f, s in [(5,50),(10,100),(20,150),(50,200)]]
ws = []
for (a, b) in combo:
    ws.append(a * b)  # both true
w = pd.concat(ws, axis=1).mean(axis=1)
st, ist, oost = eval_w(w, eth_c, "ensemble_both")
print(f"Ensemble ETH&BTC both up: Full Sh={st.Sharpe:.2f} IS={ist.Sharpe:.2f} OOS={oost.Sharpe:.2f} "
      f"CAGR={st.CAGR*100:.1f}% MDD={st.MaxDD*100:.1f}% TIM={st.TimeInMkt*100:.1f}%")
