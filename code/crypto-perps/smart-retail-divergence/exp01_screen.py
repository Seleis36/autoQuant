"""exp01 — are Binance 'top traders' informed relative to the retail head count?

Series (Binance USD-M metrics, last stamp before D 23:00 UTC; see retail-crowding-xs):
  acc  = log global account ratio (all accounts, # net long / # net short) - the retail crowd
  tacc = log top-trader ACCOUNT ratio (top 20 % by margin balance, head count)
  pos  = log top-trader POSITION ratio (top 20 %, long notional / short notional)
Pre-declared divergences (informed-minus-crowd; "+" = long where large money is more long):
  div_pa = pos - acc        top-trader positions vs retail head count
  div_pt = pos - tacc       within top traders: notional vs head count (a few big longs)
Normalisations: raw and own-90d demeaned. Both signs, h7, q30, beta-neutral, same universe /
split / cost as retail-crowding-xs (IS 2022-03..2023-12, OOS 2024+, 10 bp).
Time series on BTC (2020-09+): IC of z365(div) with forward 7/30d returns, and
"BTC x inverse-vol, flat when z(div) < -1" (large money much less long than the crowd).
"""
import os
import importlib.util
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("rcx", os.path.join(_HERE, "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)
import metrics_panel as mp  # noqa: E402
import research_lib as rl  # noqa: E402

close, vol, met, mask = rcx.load()
beta = rcx.btc_beta(close)
acc = np.log(met["count_long_short_ratio"])
tacc = np.log(met["count_toptrader_long_short_ratio"])
pos = np.log(met["sum_toptrader_long_short_ratio"])
feats = {"div_pa": pos - acc, "div_pt": pos - tacc}
rows, ics = [], []
for fn, f in feats.items():
    for norm, g in {"raw": f, "dm90": f - f.rolling(90, min_periods=60).mean()}.items():
        ic = rcx.ic_table(g, close, mask)
        for per, (a, b) in {"IS": rcx.IS, "OOS": rcx.OOS}.items():
            seg = ic.loc[a:b]
            ics.append({"feat": f"{fn}_{norm}", "per": per, **{f"IC{h}": seg[h].mean() for h in seg},
                        **{f"t{h}": seg[h].mean() / seg[h].std() * np.sqrt(seg[h].notna().sum() / h) for h in seg}})
        for sign in (1, -1):
            w = rcx.tranche(rcx.beta_neutral(rcx.quantile_ls(sign * g, mask), beta), 7)
            _, row = rcx.evaluate(w, close, f"{'+' if sign > 0 else '-'}{fn}_{norm}_h7")
            rows.append(row)
# residual of div_pa on acc (is it just the retail ratio?)
d = feats["div_pa"].where(mask).rank(axis=1)
a_ = acc.where(mask).rank(axis=1)
print("XS corr(div_pa, acc):", round(d.corrwith(a_, axis=1).mean(), 2), " corr(div_pa, pos):",
      round(d.corrwith(pos.where(mask).rank(axis=1), axis=1).mean(), 2))
pd.set_option("display.width", 220)
print("ICs ('+' sign = long high divergence)")
print(pd.DataFrame(ics).round(3).to_string(index=False))
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp01_results.csv", index=False)

# BTC time series
bm = mp.daily_metrics(["BTCUSDT"])
b_acc = np.log(bm["count_long_short_ratio"]["BTCUSDT"])
b_tacc = np.log(bm["count_toptrader_long_short_ratio"]["BTCUSDT"])
b_pos = np.log(bm["sum_toptrader_long_short_ratio"]["BTCUSDT"])
btc = rl.load_series("BTC-USD")["Close"].loc["2020-01-01":]
ret = btc.pct_change()
vt = rl.vol_target_scalar(ret, target=0.40, halflife=20, cap=1.0)
trows = []
for nm, x in {"div_pa": b_pos - b_acc, "div_pt": b_pos - b_tacc}.items():
    x = x.reindex(btc.index)
    z = (x - x.rolling(365, min_periods=180).mean()) / x.rolling(365, min_periods=180).std()
    for h in (7, 30):
        f = btc.shift(-h) / btc - 1
        for per, (a, b) in {"IS": ("2021-01-01", "2023-12-31"), "OOS": ("2024-01-01", "2026-12-31")}.items():
            g = pd.concat([z, f], axis=1).loc[a:b].dropna()
            print(f"BTC {nm} h{h} {per}: IC {g.corr(method='spearman').iloc[0, 1]:+.3f} (n={len(g)})")
    start = z.dropna().index[0]
    for rule, w in {"flat if z<-1": (z >= -1).astype(float), "flat if z>1": (z <= 1).astype(float)}.items():
        net, st = rl.backtest((w.where(z.notna()) * vt).fillna(0).loc[start:], btc.loc[start:], cost_bps=10)
        trows.append({"rule": f"BTC {nm} {rule} x inv-vol", "SR_full": rl.perf_stats(net)["Sharpe"],
                      "SR_IS": rl.perf_stats(net.loc[:"2023-12-31"])["Sharpe"], "SR_OOS": rl.perf_stats(net.loc["2024":])["Sharpe"]})
net, _ = rl.backtest(vt.loc[start:], btc.loc[start:], cost_bps=10)
trows.append({"rule": "BTC inverse-vol alone", "SR_full": rl.perf_stats(net)["Sharpe"],
              "SR_IS": rl.perf_stats(net.loc[:"2023-12-31"])["Sharpe"], "SR_OOS": rl.perf_stats(net.loc["2024":])["Sharpe"]})
print(pd.DataFrame(trows).round(2).to_string(index=False))
