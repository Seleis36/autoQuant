"""Exploration: ETH-BTC ratio trend as a regime signal for long-ETH exposure.

Hypothesis: when ETH is trending up vs BTC (ratio SMA_fast > SMA_slow), spot ETH
delivers higher risk-adjusted returns than buy-and-hold. Filter out drawdowns
by going flat when ETH is losing vs BTC.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "shared")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "code", "shared")))

import numpy as np
import pandas as pd
from research_lib import load_btc, backtest, perf_stats, split_stats, fmt, ANN

# Load ETH and BTC daily
eth = load_btc(ticker="ETH-USD")["Close"].rename("ETH")
btc = load_btc(ticker="BTC-USD")["Close"].rename("BTC")
df = pd.concat([eth, btc], axis=1).dropna()
print(f"Aligned range: {df.index.min().date()} .. {df.index.max().date()}, N={len(df)}")

ratio = df["ETH"] / df["BTC"]

# Buy-and-hold ETH baseline
bh_w = pd.Series(1.0, index=df.index)
bh_ret, bh_stats = backtest(bh_w, df["ETH"], cost_bps=10.0, name="buy_and_hold")
print("\nBuy-and-hold ETH:")
print(fmt(bh_stats.to_frame().T))

# Baseline signal: long ETH when ratio_SMA(fast) > ratio_SMA(slow), else flat
def ratio_trend_weights(ratio, fast, slow):
    sf = ratio.rolling(fast).mean()
    ss = ratio.rolling(slow).mean()
    w = (sf > ss).astype(float)
    return w

fast_grid = [5, 10, 20, 30, 50]
slow_grid = [30, 50, 70, 100, 150, 200]

rows = []
for f in fast_grid:
    for s in slow_grid:
        if f >= s:
            continue
        w = ratio_trend_weights(ratio, f, s)
        net, st = backtest(w, df["ETH"], cost_bps=10.0, name=f"f{f}_s{s}")
        st["fast"] = f; st["slow"] = s
        rows.append(st)

grid = pd.DataFrame(rows).sort_values("Sharpe", ascending=False)
print("\nRatio SMA-crossover long/flat, sorted by Sharpe:")
print(fmt(grid.head(15)))
print("\nBottom 5:")
print(fmt(grid.tail(5)))
