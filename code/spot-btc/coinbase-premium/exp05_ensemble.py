"""exp05 -- context for the candidate:
  (1) hourly trend x vol baseline WITHOUT the premium (is the premium adding anything?)
  (2) asymmetric daily gate: long in trend unless premium z is very negative
  (3) correlation / ensemble with weekday-trend (existing Working sleeve) on the same closes
  (4) cost sensitivity of the hourly hysteresis candidate
"""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "spot-btc", "weekday-trend"))
from research_lib import DATA_DIR, backtest, split_stats, ANN, perf_stats
from strategy import target_weight as wt_weight   # weekday-trend
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
IS_END, OOS_START = "2022-12-31", "2023-01-01"
def naive(df): return (df.tz_convert("UTC").tz_localize(None) if df.index.tz is not None else df).sort_index()
b = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h_flow.parquet")))
c = naive(pd.read_parquet(os.path.join(DATA_DIR, "COINBASE_BTCUSD_1h.parquet")))
idx = b.index.intersection(c.index); b, c = b.loc[idx], c.loc[idx]
px, cx = b["Close"], c["Close"]
prem = cx / px - 1
z1 = (prem - prem.rolling(720).mean()) / prem.rolling(720).std()
HANN = 365 * 24
ret_h = px.pct_change()
ewv_h = ret_h.ewm(halflife=20 * 24, min_periods=20 * 24).std() * np.sqrt(HANN)
vscale_h = (0.40 / ewv_h).clip(0, 1).fillna(0)
def sm(z, enter, exit_):
    zv = z.values; w = np.zeros(len(zv)); s = 0.0
    for i in range(len(zv)):
        v = zv[i]
        if np.isnan(v): w[i] = s; continue
        if s == 0.0 and v > enter: s = 1.0
        elif s == 1.0 and v < exit_: s = 0.0
        w[i] = s
    return pd.Series(w, index=z.index)
def rep(w, name, px=px, ann=HANN, cost=10):
    net, st = backtest(w, px, cost_bps=cost, ann=ann)
    sp = split_stats(net, {"IS": (None, IS_END), "OOS": (OOS_START, None)}, ann=ann)
    return net, dict(name=name, Sharpe=st["Sharpe"], IS=sp.loc["IS", "Sharpe"], OOS=sp.loc["OOS", "Sharpe"], CAGR=st["CAGR"],
                     MaxDD=st["MaxDD"], TO=st["Turnover_ann"], Expo=st["AvgExposure"], tNW=st["t_NW"])
rows = []
print("=== (1) hourly baselines vs premium hysteresis (10bp)")
for n in (20, 50, 100, 200):
    g = (px > px.rolling(n * 24).mean()).astype(float) * vscale_h
    rows.append(rep(g, f"sma{n} x vol, hourly, no premium")[1])
    # daily-sampled version of the same (rebalance only at 00:00 UTC)
    gd = g.where(g.index.hour == 23).ffill().fillna(0)
    rows.append(rep(gd, f"sma{n} x vol, daily-sampled, no premium")[1])
    rows.append(rep(sm(z1, 0.0, -1.5) * g, f"sma{n} x vol x hyst(0,-1.5)")[1])
    rows.append(rep(sm(z1, 1.0, -1.0) * g, f"sma{n} x vol x hyst(1,-1)")[1])
rows.append(rep(sm(z1, 0.0, -1.5) * vscale_h, "vol x hyst(0,-1.5), no trend")[1])
rows.append(rep(sm(z1, 0.0, -1.5), "hyst(0,-1.5) only")[1])
rows.append(rep(pd.Series(1.0, index=px.index), "buy&hold")[1])
print(pd.DataFrame(rows).set_index("name").round(2).to_string())

print("\n=== (2) asymmetric daily gate: sma50 x vol x 1{z90 > -thr}")
P = pd.read_parquet(os.path.join(HERE, "panel.parquet"))
close = P["close"]; ret = close.pct_change()
ewv = ret.ewm(halflife=20, min_periods=20).std() * np.sqrt(ANN); vscale = (0.40 / ewv).clip(0, 1).fillna(0)
z90 = P["cbprem_bin_z90"]
rows = []
for thr in (0.0, 0.5, 1.0, 1.5, 99):
    rows.append(rep(P["sma50_up"] * vscale * (z90 > -thr).astype(float), f"sma50 x vol x z90>-{thr}", px=close, ann=ANN)[1])
print(pd.DataFrame(rows).set_index("name").round(2).to_string())

print("\n=== (3) ensemble with weekday-trend on Binance daily closes (same sample), 10bp")
w_wt = wt_weight(close)
w_prem_h = sm(z1, 0.0, -1.5) * (px > px.rolling(50 * 24).mean()).astype(float) * vscale_h
w_prem_d = w_prem_h.where(w_prem_h.index.hour == 23).ffill().fillna(0)
w_prem_d.index = w_prem_d.index.floor("D"); w_prem_d = w_prem_d[~w_prem_d.index.duplicated(keep="last")].reindex(close.index).fillna(0)
n_wt, s_wt = rep(w_wt, "weekday-trend", px=close, ann=ANN)
n_pr, s_pr = rep(w_prem_d, "premium hyst (daily-sampled)", px=close, ann=ANN)
n_en, s_en = rep(0.5 * (w_wt + w_prem_d), "50/50 ensemble", px=close, ann=ANN)
n_mx, s_mx = rep(np.maximum(w_wt, w_prem_d), "max(weights)", px=close, ann=ANN)
print(pd.DataFrame([s_wt, s_pr, s_en, s_mx]).set_index("name").round(2).to_string())
print("daily return corr weekday-trend vs premium:", round(n_wt.corr(n_pr), 3), " OOS:", round(n_wt.loc[OOS_START:].corr(n_pr.loc[OOS_START:]), 3))

print("\n=== (4) cost sensitivity, hourly candidate sma50 x vol x hyst(0,-1.5)")
w = sm(z1, 0.0, -1.5) * (px > px.rolling(50 * 24).mean()).astype(float) * vscale_h
for cst in (0, 3, 5, 10, 20):
    print(cst, "bp:", {k: round(v, 2) for k, v in rep(w, "x", cost=cst)[1].items() if k in ("Sharpe", "IS", "OOS", "CAGR")})
print("\n=== yearly Sharpe of candidate vs buy&hold")
net, _ = backtest(w, px, cost_bps=10, ann=HANN); bh, _ = backtest(pd.Series(1.0, index=px.index), px, cost_bps=10, ann=HANN)
yr = pd.DataFrame({"cand": net.groupby(net.index.year).apply(lambda s: s.mean() / s.std() * np.sqrt(HANN)),
                   "bh": bh.groupby(bh.index.year).apply(lambda s: s.mean() / s.std() * np.sqrt(HANN)),
                   "cand_ret": net.groupby(net.index.year).apply(lambda s: (1 + s).prod() - 1)})
print(yr.round(2).T.to_string())
