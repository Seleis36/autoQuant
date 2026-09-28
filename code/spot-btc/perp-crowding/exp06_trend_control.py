"""Longer-horizon trend controls for the retail-ratio state, and a multi-horizon partial IC."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp02_backtest import START, exp_rank  # noqa: E402
from exp04_validate import glob_daily  # noqa: E402

d = btc_daily()
close = d.Close
r = close.pct_change()
vs = rl.vol_target_scalar(r, target=0.40, halflife=20, cap=1.0)
g = glob_daily(close.index)
on = (exp_rank(g) < 0).astype(float).where(exp_rank(g).notna(), 0.0)
rows = []
for nm, w in [("P1 retail-ratio state", on)] + [(f"1{{ret_{k}>0}}", (close.pct_change(k) > 0).astype(float)) for k in (10, 14, 20, 30, 60)] + \
             [(f"close>SMA{k}", (close > close.rolling(k).mean()).astype(float)) for k in (10, 20, 30, 50, 100)]:
    net, st = evaluate(w * vs, close, start=START, name=nm)
    st["corr_state_P1"] = w.loc[START:].corr(on.loc[START:])
    rows.append(st)
pd.set_option("display.width", 200)
print(pd.concat(rows).round(2).to_string())
# partial IC of the ratio after ranks of ret_1,3,7,14,30 and SMA50 state
for h in (1, 3):
    fwd = close.shift(-h) / close - 1
    samp = close.index[::h]
    for half, (a, b) in {"IS": ("2020-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
        X = pd.DataFrame({"g": g, "y": fwd, **{f"r{k}": close.pct_change(k) for k in (1, 3, 7, 14, 30)},
                          "tr": (close > close.rolling(50).mean()).astype(float)}).loc[samp].loc[a:b].dropna()
        R = (X.rank() - X.rank().mean()) / X.rank().std()
        C = np.column_stack([R[c] for c in R.columns if c not in ("g", "y")] + [np.ones(len(R))])
        e = R.g - C @ np.linalg.lstsq(C, R.g, rcond=None)[0]
        p = (e / e.std() * R.y).values
        print(f"h={h} {half}: partial IC of ratio | ret1,3,7,14,30, SMA50 = {p.mean():.3f} (t {rl.newey_west_t(p, 1):.2f}), n={len(p)}")
