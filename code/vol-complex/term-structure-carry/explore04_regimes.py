import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
df = load_all(); f = features(df)
closes = df[["vixy", "spy"]]
COST = {"vixy": 5.0, "spy": 5.0}
res = {}
def run(name, lag=0, **legs):
    w = pd.DataFrame({k: v for k, v in legs.items()}, index=df.index).fillna(0.0)
    if lag: w = w.shift(lag).fillna(0.0)
    net, st = bt_multi(w, closes, COST, name=name)
    r = report(net)
    res[name] = {"Sh_full": r.Sharpe["full"], "Sh_IS": r.Sharpe["IS"], "Sh_OOS": r.Sharpe["OOS"],
                 "CAGR": r.CAGR["full"], "MDD": r.MaxDD["full"], "Vol": r.Vol["full"], "Skew": r.Skew["full"],
                 "TO": st["Turnover_ann"], "Gross": st["GrossExp"], "t_NW": r.t_NW["full"]}
    return net
contango = (f.slope > 1).astype(float)
sma200 = df.spy / df.spy.rolling(200).mean(); sma50 = df.spy / df.spy.rolling(50).mean()
sma100 = df.spy / df.spy.rolling(100).mean()
run("contango & SPY>SMA200", vixy=-contango * (sma200 > 1))
run("contango & SPY>SMA100", vixy=-contango * (sma100 > 1))
run("contango & SPY>SMA50", vixy=-contango * (sma50 > 1))
run("SPY>SMA200 only", vixy=-(sma200 > 1).astype(float))
run("contango & SPY<SMA200", vixy=-contango * (sma200 < 1))
# VIX level buckets
for lo, hi in [(0, 13), (13, 16), (16, 20), (20, 25), (25, 35), (35, 100)]:
    run(f"contango & VIX in [{lo},{hi})", vixy=-contango * ((df.vix >= lo) & (df.vix < hi)))
# spike fade: VIX off its 5d/10d high by >x%, VIX > 20
for w, x in [(5, 0.10), (10, 0.15), (10, 0.25), (21, 0.25)]:
    off = df.vix / df.vix.rolling(w).max()
    run(f"spike fade: VIX<{1-x:.2f}*max{w} & VIX>20", vixy=-((off < 1 - x) & (df.vix > 20)).astype(float))
    run(f"contango | spike-fade({w},{x})", vixy=-(((off < 1 - x) & (df.vix > 20)) | (f.slope > 1)).astype(float))
# slope quantiles, expanding-window-free: fixed bins
for lo, hi in [(0.8, 0.95), (0.95, 1.0), (1.0, 1.05), (1.05, 1.1), (1.1, 1.15), (1.15, 1.25), (1.25, 2)]:
    run(f"slope in [{lo},{hi})", vixy=-((f.slope >= lo) & (f.slope < hi)).astype(float))
# combos
c1 = ((f.slope > 1) & (sma200 > 1) & (f.vrp10 > 0)).astype(float)
run("contango & SPY>SMA200 & VRP10>0", vixy=-c1)
run("... lag1", lag=1, vixy=-c1)
c2 = ((f.slope > 1) & (sma200 > 1) & (f.vix_ma10 < 1)).astype(float)
run("contango & SPY>SMA200 & VIX<MA10", vixy=-c2)
c3 = ((f.slope > 1) & (sma200 > 1) & (df.vix > 15)).astype(float)
run("contango & SPY>SMA200 & VIX>15", vixy=-c3)
out = pd.DataFrame(res).T
print(out.round(2).to_string())
