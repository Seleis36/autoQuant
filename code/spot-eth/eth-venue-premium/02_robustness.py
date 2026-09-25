"""eth-venue-premium 02: robustness of the pre-registered PRIMARY spec.

(a) parameter neighbourhood: z_window x enter x exit x trend (all cells reported, IS->OOS rank corr)
(b) cost sensitivity; (c) execution delay: signal lagged 1-3 extra hours
(d) 30-day block bootstrap of daily returns; (e) walk-forward re-selection (2y train, 90d apply)
(f) premium source: ETH vs BTC vs mean of both z; state agreement
(g) correlation with the live spot-btc/coinbase-premium sleeve (on BTC)
"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pandas as pd
from ethdata import rl, bars, bt, row, to_daily, IS_END, OOS_START
from fetch_coinbase import load as cb_load

H = 24 * 365
bn = bars("ETHUSDT", "1h")["Close"]
cb = cb_load("ETH-USD")["Close"].reindex(bn.index)
bnb = bars("BTCUSDT", "1h")["Close"].reindex(bn.index)
cbb = cb_load("BTC-USD")["Close"].reindex(bn.index)
ret = bn.pct_change()
vol = ret.ewm(halflife=480, min_periods=480).std() * np.sqrt(H)
vs40 = (0.40 / vol).clip(0, 1).fillna(0)


def zscore(p, win):
    p = p.dropna()
    return ((p - p.rolling(win).mean()) / p.rolling(win).std()).reindex(bn.index)


def hysteresis(z, enter, exit_):
    zv = z.to_numpy(float); out = np.zeros(len(zv)); s = 0.0
    for i, v in enumerate(zv):
        if not np.isnan(v):
            if s == 0.0 and v > enter: s = 1.0
            elif s == 1.0 and v < exit_: s = 0.0
        out[i] = s
    return pd.Series(out, index=z.index)


prem_e, prem_b = cb / bn - 1, cbb / bnb - 1
trends = {"none": 1.0, "SMA40d": (bn > bn.rolling(960).mean()).astype(float),
          "SMA50d": (bn > bn.rolling(1200).mean()).astype(float), "SMA100d": (bn > bn.rolling(2400).mean()).astype(float)}
pd.set_option("display.width", 250, "display.max_rows", 400)

# (a) neighbourhood
zc = {win: zscore(prem_e, win) for win in [360, 720, 1440]}
rows, W = [], {}
for win, en, ex, tr in itertools.product([360, 720, 1440], [-0.5, 0.0, 0.5, 1.0], [-1.0, -1.5, -2.0], trends):
    if ex >= en: continue
    w = hysteresis(zc[win], en, ex) * trends[tr] * vs40
    net, s = bt(w, bn)
    W[(win, en, ex, tr)] = net
    rows.append(row(to_daily(net), ann=365, extra=dict(win=win, enter=en, exit=ex, trend=tr, Turn=s["Turnover_ann"])))
A = pd.DataFrame(rows)
print("(a) neighbourhood:", len(A), "cells")
print(A.groupby("trend")[["Sh_Full", "Sh_IS", "Sh_OOS"]].describe().loc[:, (slice(None), ["min", "50%", "max"])].round(2).to_string())
print("share of cells with OOS > 1:", round((A.Sh_OOS > 1).mean(), 2), " IS->OOS spearman:", round(A.Sh_IS.corr(A.Sh_OOS, method="spearman"), 2))
print(A[(A.win == 720) & (A.trend == "SMA50d")][["enter", "exit", "Sh_Full", "Sh_IS", "Sh_OOS", "Turn"]].round(2).to_string(index=False))
A.to_csv(os.path.join(os.path.dirname(__file__), "02_neighbourhood.csv"), index=False)

primary_w = hysteresis(zc[720], 0.0, -1.5) * trends["SMA50d"] * vs40
# (b) costs
print("\n(b) cost sensitivity (PRIMARY)")
for cbp in [0, 5, 10, 20, 30]:
    print(cbp, {k: round(float(v), 2) for k, v in row(to_daily(bt(primary_w, bn, cost_bps=cbp)[0]), ann=365).items() if k.startswith("Sh")})
# (c) execution delay
print("\n(c) extra signal lag (hours)")
st = hysteresis(zc[720], 0.0, -1.5)
for lag in [0, 1, 2, 3, 6]:
    w = st.shift(lag).fillna(0) * trends["SMA50d"] * vs40
    print(lag, {k: round(float(v), 2) for k, v in row(to_daily(bt(w, bn)[0]), ann=365).items() if k.startswith("Sh")})
# (d) bootstrap
nd = to_daily(bt(primary_w, bn)[0]).loc["2017-10-01":]
rng = np.random.default_rng(0); B, L = 2000, 30; x = nd.values; n = len(x); sh = []
for _ in range(B):
    idx = np.concatenate([np.arange(s, s + L) % n for s in rng.integers(0, n, n // L + 1)])[:n]
    y = x[idx]; sh.append(y.mean() / y.std() * np.sqrt(365))
sh = np.array(sh)
print(f"\n(d) bootstrap: mean {sh.mean():.2f}, 5-95% [{np.percentile(sh,5):.2f}, {np.percentile(sh,95):.2f}], P(Sh>1) {np.mean(sh>1):.2f}, P(Sh>0) {np.mean(sh>0):.2f}")
s_full = rl.perf_stats(nd, ann=365)
for ntr in [1, 10, 100, 250]:
    print(f"    DSR n_trials={ntr}: {rl.deflated_sharpe(s_full['Sharpe'], len(nd), ntr, skew=s_full['Skew'], kurt=s_full['Kurt'] + 3, ann=365):.3f}")
# (e) walk-forward over the win=720 / SMA50d grid of (enter, exit) and trend choice
print("\n(e) walk-forward: every 90d pick best trailing-730d Sharpe among the 144 neighbourhood cells")
D = {k: to_daily(v) for k, v in W.items()}
Dm = pd.DataFrame(D)
starts = pd.date_range("2019-10-01", Dm.index[-1], freq="90D")
wf, picks = [], []
for s0 in starts:
    tr = Dm.loc[s0 - pd.Timedelta(days=730): s0 - pd.Timedelta(days=1)]
    shp = tr.mean() / tr.std()
    best = shp.idxmax(); picks.append(best)
    wf.append(Dm.loc[s0: s0 + pd.Timedelta(days=89), best])
wf = pd.concat(wf)
print("WF", {k: round(float(v), 2) for k, v in row(wf, ann=365).items() if k in ("Sh_Full", "Sh_IS", "Sh_OOS", "CAGR", "MDD")})
print("PRIMARY same window", {k: round(float(v), 2) for k, v in row(nd.loc[wf.index[0]:], ann=365).items() if k in ("Sh_Full", "Sh_IS", "Sh_OOS")})
print("most picked:", pd.Series([str(p) for p in picks]).value_counts().head(5).to_dict())
# (f) premium sources
print("\n(f) premium source (win 720, 0/-1.5, SMA50d, vol40)")
zb = zscore(prem_b, 720)
zm = (zc[720] + zb) / 2
se, sb, sm = hysteresis(zc[720], 0, -1.5), hysteresis(zb, 0, -1.5), hysteresis(zm, 0, -1.5)
print("state agreement ETH vs BTC:", round(float((se == sb).mean()), 3), " z corr:", round(zc[720].corr(zb), 3))
for k, s_ in [("ETH prem", se), ("BTC prem", sb), ("mean z", sm), ("both states", se * sb)]:
    net, s = bt(s_ * trends["SMA50d"] * vs40, bn)
    print(k, {kk: round(float(v), 2) for kk, v in row(to_daily(net), ann=365).items() if kk in ("Sh_Full", "Sh_IS", "Sh_OOS", "MDD")}, "Turn", round(s["Turnover_ann"]))
# (g) correlation with the BTC coinbase-premium sleeve (its published spec on BTC)
vb = (bnb.pct_change().ewm(halflife=480, min_periods=480).std() * np.sqrt(H))
wb = sb * (bnb > bnb.rolling(1200).mean()).astype(float) * (0.40 / vb).clip(0, 1).fillna(0)
btc_net, _ = bt(wb, bnb)
print("\n(g) daily corr with BTC coinbase-premium sleeve:", round(to_daily(btc_net).corr(nd), 2))
