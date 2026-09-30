"""exp01 — feature screen: does the perp/spot volume share (leveraged speculation intensity)
predict cross-sectional spot returns?

s = log(perp quote volume / spot quote volume), daily, Binance.
Normalisations (pre-declared): raw, sm7 (7d mean), dm90 (sm7 - 90d mean), z90, surge
(7d mean - previous 30d mean). Both signs, q30, beta-neutral, hold 1 or 7-day tranches.
"""
import sys
import os
import numpy as np
import pandas as pd

from common import load, IS, OOS
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "rcx", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "retail-crowding-xs", "common.py"))
rcx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcx)

close, vol, pq, sq, share, mask = load()
beta = rcx.btc_beta(close)
SPL = {"full": ("2020-09-01", "2026-12-31"), "IS": IS, "OOS": OOS}


def evaluate(w, name, cost=10.0):
    import research_lib as rl
    net, st = rl.backtest_xs(w, close, cost_bps=cost, name=name)
    row = {"name": name}
    for k, (a, b) in SPL.items():
        row[f"SR_{k}"] = rl.perf_stats(net.loc[a:b])["Sharpe"]
    full = rl.perf_stats(net.loc[SPL["full"][0]:])
    row.update(CAGR=full["CAGR"], MaxDD=full["MaxDD"], Turn=st["Turnover_ann"])
    return net, row


sm7 = share.rolling(7, min_periods=5).mean()
feats = {
    "raw": share,
    "sm7": sm7,
    "dm90": sm7 - share.rolling(90, min_periods=60).mean(),
    "z90": (sm7 - share.rolling(90, min_periods=60).mean()) / share.rolling(90, min_periods=60).std(),
    "surge": sm7 - share.shift(7).rolling(30, min_periods=20).mean(),
}
rows, ics = [], []
for fn, f in feats.items():
    ic = rcx.ic_table(-f, close, mask)
    for per, (a, b) in {"IS": IS, "OOS": OOS}.items():
        seg = ic.loc[a:b]
        ics.append({"feat": fn, "per": per, **{f"IC{h}": seg[h].mean() for h in seg},
                    **{f"t{h}": seg[h].mean() / seg[h].std() * np.sqrt(seg[h].notna().sum() / h) for h in seg}})
    for sign in (-1, 1):
        for h in (1, 7):
            w = rcx.tranche(rcx.beta_neutral(rcx.quantile_ls(sign * f, mask), beta), h)
            _, row = evaluate(w, f"{'-' if sign < 0 else '+'}{fn}_h{h}")
            rows.append(row)
pd.set_option("display.width", 200)
print("contrarian ICs (signal = -feature)")
print(pd.DataFrame(ics).round(3).to_string(index=False))
res = pd.DataFrame(rows)
print(res.round(2).to_string(index=False))
res.to_csv("exp01_results.csv", index=False)
print("universe:", mask.sum(axis=1).loc["2020-09-01":].describe().round(1).to_dict())
print("median share by coin (exp):", np.exp(share.where(mask).median()).dropna().round(2).sort_values().to_dict())
