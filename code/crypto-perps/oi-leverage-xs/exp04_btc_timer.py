"""exp04 — is the BTC leverage timer (flat when z(log OI value / mcap) > 1) new information?

1. Partial Spearman IC of z on forward 7/30d BTC returns controlling for the 30d return and
   distance to SMA50 (trend); correlation of z with the retail L/S ratio used by the live
   spot-btc perp-crowding sleeve.
2. Additivity: SMA50 x inverse-vol baseline (the spot-btc reference) with and without the
   leverage gate (AND), and the live perp-crowding rule with and without it.
3. Sensitivity (reported, not selected): threshold 0.5 / 1 / 1.5, z window 180 / 365 / 730.
Sample: 2021-03 (first z) -> 2026-09; IS through 2023-12. 10 bp.
"""
import os
import importlib.util
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)
import sys  # noqa: E402
sys.path.insert(0, os.path.join(rcx.ROOT, "code", "crypto-alts", "shared"))
import cmc  # noqa: E402
import metrics_panel as mp  # noqa: E402
import research_lib as rl  # noqa: E402

btc = rl.load_series("BTC-USD")["Close"].loc["2019-01-01":]
close = btc.to_frame("BTC-USD")
idmap = cmc.yahoo_map(close)
supply = cmc.wide("circulatingSupply", idmap, index=btc.index)["BTC-USD"]
dm = mp.daily_metrics(["BTCUSDT"])
oiv = dm["sum_open_interest_value"]["BTCUSDT"].reindex(btc.index)
L = np.log(oiv / (supply * btc))
ls = np.log(dm["count_long_short_ratio"]["BTCUSDT"].reindex(btc.index))


def zf(x, win=365):
    return (x - x.rolling(win, min_periods=win // 2).mean()) / x.rolling(win, min_periods=win // 2).std()


z = zf(L)
ret = btc.pct_change()
trend = np.log(btc / btc.rolling(50).mean())
mom30 = btc.pct_change(30)
IS_END = "2023-12-31"


def partial_ic(y, x, ctrls):
    d = pd.concat([y, x] + ctrls, axis=1).dropna().rank()
    X = np.column_stack([np.ones(len(d))] + [d.iloc[:, 2 + i] for i in range(len(ctrls))])
    ry = d.iloc[:, 0] - X @ np.linalg.lstsq(X, d.iloc[:, 0], rcond=None)[0]
    rx = d.iloc[:, 1] - X @ np.linalg.lstsq(X, d.iloc[:, 1], rcond=None)[0]
    return np.corrcoef(ry, rx)[0, 1], len(d)


for h in (7, 30):
    f = btc.shift(-h) / btc - 1
    for per, (a, b) in {"IS": ("2021-01-01", IS_END), "OOS": ("2024-01-01", "2026-12-31")}.items():
        sl = slice(a, b)
        raw = pd.concat([f, z], axis=1).loc[sl].dropna().corr(method="spearman").iloc[0, 1]
        pic, n = partial_ic(f.loc[sl], z.loc[sl], [mom30.loc[sl], trend.loc[sl]])
        pic2, _ = partial_ic(f.loc[sl], z.loc[sl], [mom30.loc[sl], trend.loc[sl], ls.loc[sl]])
        print(f"h{h} {per}: IC {raw:+.3f}  partial|mom30,trend {pic:+.3f}  partial|+retail ratio {pic2:+.3f}  (n={n})")
print("corr(z, trend)", round(z.corr(trend), 2), " corr(z, mom30)", round(z.corr(mom30), 2),
      " corr(z, retail log ratio)", round(z.corr(ls), 2))

vt = rl.vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0)
sma = (btc > btc.rolling(50).mean()).astype(float)
ls_gate = (ls < ls.expanding(min_periods=90).median()).astype(float)   # perp-crowding rule
gate = (z <= 1).astype(float).where(z.notna())
start = z.dropna().index[0]
rules = {
    "buy&hold": pd.Series(1.0, index=btc.index),
    "lev gate alone (z<=1)": gate,
    "inv-vol alone": vt,
    "lev gate x inv-vol": gate * vt,
    "SMA50 x inv-vol (baseline)": sma * vt,
    "SMA50 x inv-vol x lev gate": sma * vt * gate,
    "perp-crowding (ls<median) x inv-vol": ls_gate * vt,
    "perp-crowding x inv-vol x lev gate": ls_gate * vt * gate,
}
rows, nets = [], {}
for nm, w in rules.items():
    net, st = rl.backtest(w.fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
    nets[nm] = net
    r = {"rule": nm}
    for per, (a, b) in {"full": (start, "2026-12-31"), "IS": (start, IS_END), "OOS": ("2024-01-01", "2026-12-31")}.items():
        r[f"SR_{per}"] = rl.perf_stats(net.loc[a:b])["Sharpe"]
    r.update(CAGR=st["CAGR"], MaxDD=st["MaxDD"], expo=st["AvgExposure"], turn=st["Turnover_ann"])
    rows.append(r)
for thr in (0.5, 1.5):
    for win in (365,):
        g = (zf(L, win) <= thr).astype(float)
        net, st = rl.backtest((g * vt).fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
        rows.append({"rule": f"lev gate x inv-vol, thr {thr}", "SR_full": rl.perf_stats(net)["Sharpe"],
                     "SR_IS": rl.perf_stats(net.loc[:IS_END])["Sharpe"], "SR_OOS": rl.perf_stats(net.loc["2024":])["Sharpe"],
                     "MaxDD": st["MaxDD"], "expo": st["AvgExposure"]})
for win in (180, 730):
    g = (zf(L, win) <= 1).astype(float)
    net, st = rl.backtest((g * vt).fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
    rows.append({"rule": f"lev gate x inv-vol, window {win}", "SR_full": rl.perf_stats(net)["Sharpe"],
                 "SR_IS": rl.perf_stats(net.loc[:IS_END])["Sharpe"], "SR_OOS": rl.perf_stats(net.loc["2024":])["Sharpe"],
                 "MaxDD": st["MaxDD"], "expo": st["AvgExposure"]})
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).round(2).to_string(index=False))
print("daily corr lev-gate x inv-vol vs SMA50 x inv-vol:", round(nets["lev gate x inv-vol"].corr(nets["SMA50 x inv-vol (baseline)"]), 2),
      "| vs perp-crowding:", round(nets["lev gate x inv-vol"].corr(nets["perp-crowding (ls<median) x inv-vol"]), 2))
print("share of days gated out:", round(1 - gate.loc[start:].mean(), 3),
      "| gated-out days by year:", (1 - gate.loc[start:]).groupby(gate.loc[start:].index.year).mean().round(2).to_dict())
