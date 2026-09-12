"""exp02 -- deep dive on the Coinbase premium signal.

 (a) decomposition: CB/Binance = (CB/Bitstamp) x (Bitstamp/Binance ~ USDT/USD)
 (b) horizon: forward return over 1..10 days by signal quintile
 (c) transform grid: smoothing L x z-window W  -> IS/OOS quintile spread (reported in full)
 (d) first long/flat rules at 10bp/side
"""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import newey_west_t, ANN, backtest, split_stats, fmt
IS_END, OOS_START = "2022-12-31", "2023-01-01"
P = pd.read_parquet(os.path.join(HERE, "panel.parquet"))
pd.set_option("display.width", 220)

def qtab(x, y, q=5):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    b = pd.qcut(df["x"].rank(method="first"), q, labels=False)
    g = df.groupby(b)["y"]
    return pd.DataFrame({"mean_bp": g.mean() * 1e4, "sharpe": g.mean() / g.std() * np.sqrt(ANN), "n": g.size()})

def spread(x, y):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 150: return np.nan, np.nan
    b = pd.qcut(df["x"].rank(method="first"), 5, labels=False)
    s = pd.Series(0.0, index=df.index); s[b == 4] = df["y"][b == 4]; s[b == 0] = -df["y"][b == 0]
    return (df["y"][b == 4].mean() - df["y"][b == 0].mean()) * 1e4, newey_west_t(s.values, 10)

# ---------------- (a) decomposition
print("=== (a) components: quintile spread bp / NW t   [IS | OOS]")
bs = P["cbprem_bin_mean"] - P["cbprem_bs_mean"]   # approx Bitstamp/Binance premium (USDT effect)
comps = {"CB/Binance (mean)": P["cbprem_bin_mean"], "CB/Bitstamp (mean)": P["cbprem_bs_mean"],
         "Bitstamp/Binance ~USDT": bs, "USDT/USD Bitstamp": P["usdt_prem"]}
for k, v in comps.items():
    a, b = P.loc[:IS_END], P.loc[OOS_START:]
    print(f"{k:26s} IS {spread(v.loc[:IS_END], a['ret_fwd'])[0]:7.1f} t={spread(v.loc[:IS_END], a['ret_fwd'])[1]:5.2f} | "
          f"OOS {spread(v.loc[OOS_START:], b['ret_fwd'])[0]:7.1f} t={spread(v.loc[OOS_START:], b['ret_fwd'])[1]:5.2f}")

# ---------------- (b) horizon
print("\n=== (b) horizon: mean fwd return (bp) over h days by quintile of cbprem_bin_z90, full sample")
z = P["cbprem_bin_z90"]
rows = {}
for h in (1, 2, 3, 5, 7, 10, 15):
    fwd = P["close"].shift(-h) / P["close"] - 1   # NOTE row D close -> D+h close; day-1 fwd = ret_fwd
    fwd = P["close"].shift(-h - 0) / P["close"].shift(0) - 1
    fwd = (P["close"].shift(-h) / P["close"] - 1)
    t = qtab(z, fwd)["mean_bp"] / h
    rows[h] = t
print(pd.DataFrame(rows).round(1).to_string())
print("(per-day bp; quintile 4 = highest premium)")

print("\n=== (b2) same for IS / OOS, h=1 and h=5")
for nm, seg in (("IS", P.loc[:IS_END]), ("OOS", P.loc[OOS_START:])):
    for h in (1, 5):
        fwd = seg["close"].shift(-h) / seg["close"] - 1
        print(nm, f"h={h}", (qtab(seg["cbprem_bin_z90"], fwd)["mean_bp"] / h).round(1).tolist())

# ---------------- (c) transform grid
print("\n=== (c) grid: smoothing L days of daily-mean premium, z-window W  -> spread bp (t)  IS | OOS")
base = P["cbprem_bin_mean"]
res = []
for L, W in itertools.product((1, 3, 5, 10), (0, 30, 60, 90, 180)):
    s = base.rolling(L).mean()
    x = s if W == 0 else (s - s.rolling(W).mean()) / s.rolling(W).std()
    a = spread(x.loc[:IS_END], P.loc[:IS_END, "ret_fwd"]); b = spread(x.loc[OOS_START:], P.loc[OOS_START:, "ret_fwd"])
    res.append(dict(L=L, W=W, sp_is=a[0], t_is=a[1], sp_os=b[0], t_os=b[1]))
print(pd.DataFrame(res).round(2).to_string())

# ---------------- (d) first long/flat rules
print("\n=== (d) long/flat rules, 10bp/side, weight decided at row D applied to ret_fwd")
close = P["close"]
ret = close.pct_change()
ewv = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN)
vscale = (0.40 / ewv).clip(0, 1).fillna(0)
rules = {
    "z90>0": (z > 0).astype(float),
    "z90>0.5": (z > 0.5).astype(float),
    "z90>0 x vol": (z > 0).astype(float) * vscale,
    "clip(z90,0,2)/2": z.clip(0, 2) / 2,
    "clip(z90,0,2)/2 x vol": (z.clip(0, 2) / 2) * vscale,
    "prem_mean>0": (base > 0).astype(float),
    "prem_mean>0 x vol": (base > 0).astype(float) * vscale,
    "prem>90d mean": (base > base.rolling(90).mean()).astype(float),
    "buy&hold": pd.Series(1.0, index=P.index),
}
out = {}
for k, w in rules.items():
    # backtest() shifts weights by one day internally; our row-D weight must earn ret_{D+1}
    net, st = backtest(w.fillna(0), close, cost_bps=10)
    sp = split_stats(net, {"IS": (None, IS_END), "OOS": (OOS_START, None)})
    out[k] = dict(Sharpe=st["Sharpe"], IS=sp.loc["IS", "Sharpe"], OOS=sp.loc["OOS", "Sharpe"], CAGR=st["CAGR"],
                  MaxDD=st["MaxDD"], TO=st["Turnover_ann"], Expo=st["AvgExposure"])
print(pd.DataFrame(out).T.round(2).to_string())
