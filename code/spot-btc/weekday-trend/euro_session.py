"""European session drift — long BTC only during specific UTC hours."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np
import pandas as pd
from research_lib import perf_stats

df = pd.read_parquet("data/BTCUSDT_1h.parquet")
c = df["Close"]
r = c.pct_change().dropna()
r.index = pd.to_datetime(r.index)

IS = ("2017-08-17", "2021-12-31")
OOS = ("2022-01-01", "2026-09-06")

def strategy(hours_long, cost_bps=3.0):
    """Long from hour[0] close to hour[1] close each UTC day. hours_long = (start,end).
    Position is 1 if index_hour in (start, end], else 0.
    Cost charged on entry+exit.
    Returns hourly net return series.
    """
    start, end = hours_long
    h = r.index.hour
    if start < end:
        pos = ((h > start) & (h <= end)).astype(float)  # position during hour h
    else:  # wrap around midnight
        pos = ((h > start) | (h <= end)).astype(float)
    pos = pd.Series(pos, index=r.index)
    # Costs: use turnover on position changes
    pos_prev = pos.shift(1).fillna(0)
    trades = (pos - pos_prev).abs()
    net = pos * r - trades * cost_bps / 1e4
    return net, pos

def stats_ann(net):
    ann_hours = 24 * 365
    if net.std() == 0:
        return dict(sharpe=np.nan, cagr=0.0, mdd=0.0, N=0)
    sharpe = net.mean() / net.std() * np.sqrt(ann_hours)
    eq = (1 + net).cumprod()
    yrs = len(net) / ann_hours
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    dd = eq / eq.cummax() - 1
    return dict(sharpe=sharpe, cagr=cagr, mdd=dd.min(), N=len(net))

# scan single hour and windows
print("=== single-hour windows (long during hour h only) ===")
rows = []
for h in range(24):
    # long during hour h means pos=1 for that hour's index (return earned)
    pos = pd.Series((r.index.hour == h).astype(float), index=r.index)
    pos_prev = pos.shift(1).fillna(0)
    trades = (pos - pos_prev).abs()
    net = pos * r - trades * 3.0 / 1e4
    s_full = stats_ann(net)
    s_is = stats_ann(net.loc[IS[0]:IS[1]])
    s_oos = stats_ann(net.loc[OOS[0]:OOS[1]])
    rows.append((h, s_full["sharpe"], s_is["sharpe"], s_oos["sharpe"], s_full["cagr"], s_full["mdd"]))
print(pd.DataFrame(rows, columns=["h", "full", "IS", "OOS", "cagr", "mdd"]).round(3).to_string(index=False))

print("\n=== windows [start,end] long during those hours (inclusive of end, exclusive of start) ===")
rows = []
for start in range(24):
    for length in range(1, 13):
        end = (start + length) % 24
        pos_series = pd.Series(0.0, index=r.index)
        h = r.index.hour
        if start < end:
            mask = (h > start) & (h <= end)
        else:
            mask = (h > start) | (h <= end)
        pos_series[mask] = 1.0
        pos_prev = pos_series.shift(1).fillna(0)
        trades = (pos_series - pos_prev).abs()
        net = pos_series * r - trades * 3.0 / 1e4
        s_f = stats_ann(net)
        s_i = stats_ann(net.loc[IS[0]:IS[1]])
        s_o = stats_ann(net.loc[OOS[0]:OOS[1]])
        rows.append((start, end, length, s_f["sharpe"], s_i["sharpe"], s_o["sharpe"], s_f["cagr"], s_f["mdd"]))

d = pd.DataFrame(rows, columns=["start", "end", "len", "full", "IS", "OOS", "cagr", "mdd"])
print("Top 15 by min(IS,OOS):")
d["min_split"] = d[["IS", "OOS"]].min(axis=1)
print(d.sort_values("min_split", ascending=False).head(15).round(3).to_string(index=False))
