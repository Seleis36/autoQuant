"""exp02 — the BTC divergence gate: new information, or the live perp-crowding signal again?

z_x = (x - 365d mean) / 365d std for x in {div_pa = pos - acc, acc, pos}.
1. Partial IC30 of z_div controlling for z_acc, z_pos (each alone), mom30 and SMA50 distance.
2. Additivity on BTC x inverse-vol (40 %, cap 1), 10 bp, from the first z (2022-06):
   perp-crowding (acc < expanding median, the live spot-btc rule), SMA50, and each AND the gate
   "flat if z_div < -1". Also the gate built from z_pos alone and from -z_acc alone.
3. Sensitivity (not selection): threshold -0.5 / -1.5, window 180 / 730.
4. Replication with the same parameters on ETH, SOL, XRP, BNB, DOGE (metrics 2021-12+).
"""
import os
import sys
import importlib.util
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)
import metrics_panel as mp  # noqa: E402
import research_lib as rl  # noqa: E402
sys.path.insert(0, os.path.join(rcx.ROOT, "code", "crypto-alts", "shared"))
import venues  # noqa: E402


def zf(x, win=365):
    return (x - x.rolling(win, min_periods=win // 2).mean()) / x.rolling(win, min_periods=win // 2).std()


def series(sym, px_index):
    m = mp.daily_metrics([sym])
    acc = np.log(m["count_long_short_ratio"][sym]).reindex(px_index)
    pos = np.log(m["sum_toptrader_long_short_ratio"][sym]).reindex(px_index)
    return acc, pos


def partial_ic(y, x, ctrls):
    d = pd.concat([y, x] + ctrls, axis=1).dropna().rank()
    X = np.column_stack([np.ones(len(d))] + [d.iloc[:, 2 + i] for i in range(len(ctrls))])
    ry = d.iloc[:, 0] - X @ np.linalg.lstsq(X, d.iloc[:, 0], rcond=None)[0]
    rx = d.iloc[:, 1] - X @ np.linalg.lstsq(X, d.iloc[:, 1], rcond=None)[0]
    return np.corrcoef(ry, rx)[0, 1]


btc = rl.load_series("BTC-USD")["Close"].loc["2019-06-01":]
acc, pos = series("BTCUSDT", btc.index)
print("BTC top-trader position ratio first valid:", pos.first_valid_index(), "| account ratio:", acc.first_valid_index())
zd, za, zp = zf(pos - acc), zf(acc), zf(pos)
mom30 = btc.pct_change(30)
trend = np.log(btc / btc.rolling(50).mean())
f30 = btc.shift(-30) / btc - 1
for per, (a, b) in {"IS": ("2021-01-01", "2023-12-31"), "OOS": ("2024-01-01", "2026-12-31")}.items():
    sl = slice(a, b)
    print(per, "IC30 z_div", round(pd.concat([f30, zd], axis=1).loc[sl].dropna().corr(method="spearman").iloc[0, 1], 3),
          "| z_acc", round(pd.concat([f30, za], axis=1).loc[sl].dropna().corr(method="spearman").iloc[0, 1], 3),
          "| z_pos", round(pd.concat([f30, zp], axis=1).loc[sl].dropna().corr(method="spearman").iloc[0, 1], 3),
          "| partial z_div | z_acc,mom,trend", round(partial_ic(f30.loc[sl], zd.loc[sl], [za.loc[sl], mom30.loc[sl], trend.loc[sl]]), 3),
          "| partial z_div | z_pos,mom,trend", round(partial_ic(f30.loc[sl], zd.loc[sl], [zp.loc[sl], mom30.loc[sl], trend.loc[sl]]), 3))
print("corr z_div vs z_acc", round(zd.corr(za), 2), " vs z_pos", round(zd.corr(zp), 2))

ret = btc.pct_change()
vt = rl.vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0)
gate = (zd >= -1).astype(float).where(zd.notna())
pc = (acc < acc.expanding(min_periods=90).median()).astype(float)
sma = (btc > btc.rolling(50).mean()).astype(float)
start = zd.dropna().index[0]
rules = {
    "inverse-vol alone": vt,
    "div gate x inv-vol": gate * vt,
    "pos gate (flat if z_pos<-1) x inv-vol": (zp >= -1).astype(float) * vt,
    "acc gate (flat if z_acc>1) x inv-vol": (za <= 1).astype(float) * vt,
    "SMA50 x inv-vol": sma * vt,
    "SMA50 x inv-vol x div gate": sma * vt * gate,
    "perp-crowding x inv-vol (live spot-btc rule)": pc * vt,
    "perp-crowding x inv-vol x div gate": pc * vt * gate,
}
for thr in (-0.5, -1.5):
    rules[f"div gate thr {thr} x inv-vol"] = (zd >= thr).astype(float) * vt
for win in (180, 730):
    rules[f"div gate window {win} x inv-vol"] = (zf(pos - acc, win) >= -1).astype(float) * vt
rows, nets = [], {}
for nm, w in rules.items():
    net, st = rl.backtest(w.fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
    nets[nm] = net
    rows.append({"rule": nm, "SR_full": rl.perf_stats(net)["Sharpe"], "SR_IS": rl.perf_stats(net.loc[:"2023-12-31"])["Sharpe"],
                 "SR_OOS": rl.perf_stats(net.loc["2024":])["Sharpe"], "CAGR": st["CAGR"], "MaxDD": st["MaxDD"],
                 "expo": st["AvgExposure"], "turn": st["Turnover_ann"]})
pd.set_option("display.width", 220)
print("from", start.date())
print(pd.DataFrame(rows).round(2).to_string(index=False))
print("daily corr div-gate vs perp-crowding:", round(nets["div gate x inv-vol"].corr(nets["perp-crowding x inv-vol (live spot-btc rule)"]), 2),
      "| vs SMA50:", round(nets["div gate x inv-vol"].corr(nets["SMA50 x inv-vol"]), 2))
print("share of days gated out by year:", (1 - gate.loc[start:]).groupby(gate.loc[start:].index.year).mean().round(2).to_dict())

# replication
for tk, sym in (("ETH", "ETHUSDT"), ("SOL", "SOLUSDT"), ("XRP", "XRPUSDT"), ("BNB", "BNBUSDT"), ("DOGE", "DOGEUSDT")):
    px = venues.binance_daily(tk)["Close"].loc["2021-06-01":]
    a_, p_ = series(sym, px.index)
    z = zf(p_ - a_)
    r = px.pct_change()
    v = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
    s0 = z.dropna().index[0]
    out = {}
    for nm, w in {"inv-vol": v, "div gate x inv-vol": (z >= -1).astype(float) * v}.items():
        net, st = rl.backtest(w.fillna(0).loc[s0:], px.loc[s0:], cost_bps=10)
        out[nm] = f"{rl.perf_stats(net)['Sharpe']:.2f} (OOS {rl.perf_stats(net.loc['2024':])['Sharpe']:.2f})"
    f = px.shift(-30) / px - 1
    ic = pd.concat([z, f], axis=1).dropna().corr(method="spearman").iloc[0, 1]
    print(f"{tk} from {s0.date()} IC30 {ic:+.3f}", out)
