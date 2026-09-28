"""credit-calendar-flow -- the three a-priori windows as long-only books on the credit premia,
2 bp/side on both legs (hedged premia turn over 1 + hedge notional). IS 2007-04 -> 2017, OOS 2018 -> 2026."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _HERE)
from importlib import import_module
es = import_module("01_event_study")
R = es.premia().dropna(subset=["HY", "IG"]); idx = R.index
fwd, bwd = es.tdm(idx)
gaps = pd.Series(idx[1:] - idx[:-1], index=idx[:-1]).reindex(idx)
wins = {"TOM+1..+3": fwd.between(1, 3), "ME-3..-1": bwd.between(-3, -1),
        "ME-3..+3": fwd.between(1, 3) | bwd.between(-3, -1),
        "pre_holiday": ((gaps > pd.Timedelta(days=1)) & (idx.dayofweek != 4))}
hedge = {"HY": 0.47, "JNK": 0.47, "IG": 1.15, "HYG": 0.0, "LQD": 0.0}
rows = []
for wn, m in wins.items():
    w = m.astype(float)                       # held ON the window days -> set at prior close
    w_set = w.shift(-1).fillna(0)             # weight decided at close t-1 for day t (calendar known)
    for inst, h in hedge.items():
        we = w_set.shift(1).fillna(0)
        net = we * R[inst] - we.diff().abs().fillna(0) * (1 + h) * 2e-4
        for sp, (a, b) in {"IS": ("2007-04", "2017"), "OOS": ("2018", "2026")}.items():
            x = net.loc[a:b]
            rows.append(dict(window=wn, inst=inst, split=sp, sharpe=x.mean() / x.std() * np.sqrt(252),
                             ann_ret=x.mean() * 252 * 100, expo=we.loc[a:b].mean()))
t = pd.DataFrame(rows)
print(t.pivot_table(index=["window", "inst"], columns="split", values=["sharpe", "ann_ret"]).round(2).to_string())
