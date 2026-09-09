"""Scan hour-of-week BTC returns to find persistent intraday edges."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np
import pandas as pd
from research_lib import perf_stats, ANN

df = pd.read_parquet("data/BTCUSDT_1h.parquet")
c = df["Close"]
r = c.pct_change().dropna()
r.index = pd.to_datetime(r.index)

# 1) hour of day, IS/OOS
r_is = r.loc[:"2022-01-01"]
r_oos = r.loc["2022-01-01":]

def stats_by_hour(r):
    grp = r.groupby(r.index.hour)
    return pd.DataFrame({
        "N": grp.count(),
        "mean_bp": grp.mean() * 1e4,
        "sharpe": grp.mean() / grp.std() * np.sqrt(24 * 365),
    })

print("=== Hour of day (UTC), IS 2017-08 -> 2022-01 ===")
print(stats_by_hour(r_is).round(3))
print()
print("=== Hour of day (UTC), OOS 2022-01 -> 2026-09 ===")
print(stats_by_hour(r_oos).round(3))
print()

# 2) day of week
print("=== Day of week (0=Mon), IS ===")
grp = r_is.groupby(r_is.index.dayofweek)
print(pd.DataFrame({"mean_bp": grp.mean() * 1e4, "sharpe": grp.mean() / grp.std() * np.sqrt(24 * 365)}).round(3))
print("=== Day of week, OOS ===")
grp = r_oos.groupby(r_oos.index.dayofweek)
print(pd.DataFrame({"mean_bp": grp.mean() * 1e4, "sharpe": grp.mean() / grp.std() * np.sqrt(24 * 365)}).round(3))
print()

# 3) hour x day (mean bp) both halves
def h_d(r):
    idx = pd.MultiIndex.from_arrays([r.index.dayofweek, r.index.hour], names=["dow", "hr"])
    s = pd.Series(r.values, index=idx)
    m = s.groupby(level=[0, 1]).mean().unstack("hr") * 1e4
    return m
print("=== IS hour-of-week mean (bp) ===")
print(h_d(r_is).round(1))
print("=== OOS hour-of-week mean (bp) ===")
print(h_d(r_oos).round(1))
