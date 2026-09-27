"""Robustness of the fixed spec (resid_MS_12_1_t, sector-neutral linear, monthly, beta-hedged,
vol-managed): parameter neighbourhood (estimation window, formation length, skip), hedge
instrument (EW member basket vs RSP), cost 2/5/10 bp, yearly Sharpe, leg attribution,
10 % vol leverage. The neighbourhood is reported, never used to pick the spec."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from strategy import residual_momentum_weights, _panel_inputs
from common import splits_row, month_ends
from xs_lib import xs_backtest
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import load_series

X = _panel_inputs()
ret = X["close"].pct_change(fill_method=None)
ret["RSP"] = X["rsp"].pct_change(fill_method=None)
rows = []


def run(name, cost=5.0, **kw):
    w = residual_momentum_weights(X, **kw).loc["2011-01-01":]
    r = ret.reindex(columns=w.columns).loc["2011-01-01":]
    net, st = xs_backtest(w, r, cost_bps=cost, name=name)
    row = splits_row(net, st); row.update({"cfg": name, "avg_gross": st["AvgGross"]}); rows.append(row)
    return net, w


base_net, base_w = run("SPEC")
for est in (189, 378):
    run(f"est={est}", est=est)
for L in (189, 315):
    run(f"L={L}", L=L)
for skip in (10, 42):
    run(f"skip={skip}", skip=skip)
run("no volman", vol_manage=False)
run("no beta hedge", hedge=None)
run("hedge=RSP", hedge="RSP")
run("quintile", kind="quintile")
run("cost 2bp", cost=2.0); run("cost 10bp", cost=10.0)
d = pd.DataFrame(rows).set_index("cfg")
pd.set_option("display.width", 200)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "screen3_robust_results.csv"))

lev = 0.10 / (base_net.loc[:"2017"].std() * np.sqrt(252))
n10, s10 = xs_backtest(base_w * lev, ret.reindex(columns=base_w.columns).loc["2011-01-01":], cost_bps=5.0)
print(f"\nlevered x{lev:.2f} to 10% IS vol:", {k: round(v, 3) for k, v in splits_row(n10, s10).items()},
      "avg gross", round(s10["AvgGross"], 2), "max gross", round((base_w * lev).abs().sum(axis=1).max(), 2))
yr = n10.groupby(n10.index.year).agg(lambda x: x.mean() / x.std() * np.sqrt(252))
ry = n10.groupby(n10.index.year).sum()
print(pd.DataFrame({"sharpe": yr, "ret": ry}).round(2).T.to_string())
spy = load_series("SPY")["Close"].pct_change().reindex(n10.index)
print("corr to SPY:", round(n10.corr(spy), 3))
# leg attribution (gross): stock legs vs hedge
wl = base_w.clip(lower=0); ws = base_w.clip(upper=0)
r_ = ret.reindex(columns=base_w.columns).loc["2011-01-01":].fillna(0)
print("gross ann. return, positive-weight names %.3f, negative-weight names %.3f" %
      ((wl.shift(1) * r_).sum(axis=1).mean() * 252, (ws.shift(1) * r_).sum(axis=1).mean() * 252))
n10.to_frame("rm10").to_parquet(os.path.join(HERE, "nets_0_spec10.parquet"))
