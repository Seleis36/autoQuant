"""Prototype: dip-in-uptrend mean reversion on spot BTC daily.

Signal (all lookahead-safe, computed from close-of-t):
    trend    = 1{close_t > SMA_trend(close, T_win)}
    ref_high = rolling max of close over H_win days (up to t)
    drawdown = close_t / ref_high - 1
    dip      = 1{drawdown < -dip_thresh}
    raw_sig  = trend AND dip

On raw entry -> stay long for `hold` days (or until stop/target).
Sizing: inverse-vol scalar target_vol / ewma_vol_20 clipped [0, cap].
"""
import sys, os, itertools, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np
import pandas as pd
from research_lib import load_btc, backtest, perf_stats, ewm_vol, split_stats, fmt

btc = load_btc()
close = btc["Close"]
ret = close.pct_change()

def gen_signal(close, ret, T_win=100, H_win=10, dip_thresh=0.05,
               hold=5, target_vol=0.4, vol_hl=20, cap=1.5):
    sma = close.rolling(T_win).mean()
    trend = (close > sma).astype(int)
    ref_high = close.rolling(H_win).max()
    dd = close / ref_high - 1.0
    dip = (dd < -dip_thresh).astype(int)
    entry = ((trend == 1) & (dip == 1)).astype(int)
    # Hold for `hold` days after entry: max-decay filter
    active = entry.rolling(hold, min_periods=1).max().fillna(0)
    v = ewm_vol(ret, halflife=vol_hl)
    scalar = (target_vol / v).clip(0, cap).fillna(0)
    w = active * scalar
    return w

def run(**kw):
    w = gen_signal(close, ret, **kw)
    net, stats = backtest(w, close, cost_bps=10.0)
    return net, stats

# quick baseline: buy&hold
bh, bh_stats = backtest(pd.Series(1.0, index=close.index), close, cost_bps=0)
print("BUY & HOLD:")
print(fmt(pd.DataFrame([bh_stats]).T.T))
print()

# initial params
net, stats = run()
print("dip-in-uptrend defaults (T=100,H=10,dip=5%,hold=5,tvol=0.4):")
print(fmt(pd.DataFrame([stats]).T.T))
print()

# IS/OOS split
IS = ("2015-01-01", "2021-12-31")
OOS = ("2022-01-01", "2026-09-06")
splits = {"IS": IS, "OOS": OOS}
print("Splits (defaults):")
print(fmt(split_stats(net, splits)))
print()

# small sweep — coarse
print("=== Coarse sweep ===")
rows = []
for T in [50, 100, 150, 200]:
    for H in [5, 10, 20]:
        for dip in [0.03, 0.05, 0.08, 0.12]:
            for hold in [3, 5, 10]:
                w = gen_signal(close, ret, T_win=T, H_win=H, dip_thresh=dip, hold=hold)
                n, s = backtest(w, close, cost_bps=10.0)
                s_is = perf_stats(n.loc[IS[0]:IS[1]], name="is").loc["Sharpe"]
                s_oos = perf_stats(n.loc[OOS[0]:OOS[1]], name="oos").loc["Sharpe"]
                rows.append((T, H, dip, hold, s.Sharpe, s_is, s_oos, s.MaxDD, s.CAGR, s.get("Turnover_ann", np.nan), s.get("AvgExposure", np.nan)))

df = pd.DataFrame(rows, columns=["T", "H", "dip", "hold", "Sharpe", "SharpeIS", "SharpeOOS", "MaxDD", "CAGR", "Turnover", "Expo"])
df = df.sort_values("Sharpe", ascending=False)
print("Top 15 by full-sample Sharpe:")
print(df.head(15).to_string(index=False))
print()
print("Top 15 by OOS Sharpe:")
print(df.sort_values("SharpeOOS", ascending=False).head(15).to_string(index=False))
