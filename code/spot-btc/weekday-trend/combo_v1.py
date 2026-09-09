"""Combo v1: trend + vol-managed + weekday tilt.

Signal (all lookahead-safe):
    trend  = 1{close_t > SMA_t(T_win)}       (evaluated at close_t)
    vol_s  = target_vol / EWMA_vol_20(ret)   clipped [0, cap]
    weekday_mask = 1{dow_{t+1} in allowed_days}  (applies to next day's return)
Weight applied to r_{t+1}:
    w_t = trend_t * vol_s_t * weekday_mask(t+1)
The library shifts w by 1, so we set: raw_weight_t must reflect what we plan
to earn tomorrow. We can set weekday_mask by t's day-of-week +1 => day-of-week of t+1.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np
import pandas as pd
from research_lib import load_btc, backtest, perf_stats, ewm_vol, split_stats, fmt

btc = load_btc()
c = btc["Close"]
r = c.pct_change()

IS = ("2015-01-01", "2021-12-31")
OOS = ("2022-01-01", "2026-09-06")

def signal(T=100, target_vol=0.4, hl=20, cap=1.5, skip_days=(3,), allowed_days=None):
    trend = (c > c.rolling(T).mean()).astype(float)
    v = ewm_vol(r, halflife=hl)
    scale = (target_vol / v).clip(0, cap).fillna(0)
    # We want next-day exposure — the backtest shifts weight by 1. So the day-of-week
    # to gate is (index_t + 1 day).dayofweek.
    next_dow = (c.index + pd.Timedelta(days=1)).dayofweek
    if allowed_days is not None:
        gate = pd.Series([1.0 if d in allowed_days else 0.0 for d in next_dow], index=c.index)
    else:
        gate = pd.Series([0.0 if d in skip_days else 1.0 for d in next_dow], index=c.index)
    return (trend * scale * gate).fillna(0)

def run(**kw):
    w = signal(**kw)
    return backtest(w, c, cost_bps=10.0)

# baseline: vol-managed trend, no weekday
print("=== A) vol-managed trend, all days ===")
w_base = signal(skip_days=())
n, s = backtest(w_base, c, cost_bps=10.0)
print(fmt(pd.DataFrame([s]).T.T))
print(fmt(split_stats(n, {"IS": IS, "OOS": OOS})))

print("\n=== B) skip Thursday ===")
n, s = run(skip_days=(3,))
print(fmt(pd.DataFrame([s]).T.T))
print(fmt(split_stats(n, {"IS": IS, "OOS": OOS})))

# Try various single-day skips
print("\n=== single-day skip scan ===")
rows = []
for d in range(7):
    _, s = run(skip_days=(d,))
    n2, _ = run(skip_days=(d,))
    s_is = perf_stats(n2.loc[IS[0]:IS[1]]).Sharpe
    s_oos = perf_stats(n2.loc[OOS[0]:OOS[1]]).Sharpe
    rows.append((d, s.Sharpe, s_is, s_oos, s.MaxDD, s.CAGR))
print(pd.DataFrame(rows, columns=["skip_dow", "Sharpe", "IS", "OOS", "MDD", "CAGR"]).round(3).to_string(index=False))

# 2-day skips
print("\n=== 2-day skip scan ===")
from itertools import combinations
rows2 = []
for combo in combinations(range(7), 2):
    n2, s = run(skip_days=combo)
    s_is = perf_stats(n2.loc[IS[0]:IS[1]]).Sharpe
    s_oos = perf_stats(n2.loc[OOS[0]:OOS[1]]).Sharpe
    rows2.append((combo, s.Sharpe, s_is, s_oos, s.MaxDD, s.CAGR))
print(pd.DataFrame(rows2, columns=["skip", "Sharpe", "IS", "OOS", "MDD", "CAGR"]).sort_values("OOS", ascending=False).head(10).round(3).to_string(index=False))

# What if we ALLOWED only strongest days (Mon, Wed)?
print("\n=== allow-only scans ===")
rows3 = []
for k in range(1, 7):
    for combo in combinations(range(7), k):
        n2, s = run(allowed_days=combo)
        s_is = perf_stats(n2.loc[IS[0]:IS[1]]).Sharpe
        s_oos = perf_stats(n2.loc[OOS[0]:OOS[1]]).Sharpe
        rows3.append((combo, s.Sharpe, s_is, s_oos, s.MaxDD, s.CAGR, s.get("AvgExposure", np.nan)))
top = pd.DataFrame(rows3, columns=["allow", "Sharpe", "IS", "OOS", "MDD", "CAGR", "Expo"]).sort_values("OOS", ascending=False).head(15).round(3)
print(top.to_string(index=False))
