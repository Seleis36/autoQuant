"""Event-window book: long high-yield-tercile payers during [-W, -1] bars before the PREDICTED
ex-date (entry at close of bar -W-1, exit at close of bar -1), each long hedged with its sector's
EW member basket; gross 1 when names are present; 5 bp."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import sector_map, splits_row, xs_backtest
from panel import load_panel
P = load_panel()
close = P["close"]; dates = close.index; tix = list(close.columns)
ret = close.pct_change(fill_method=None); mem = P["member"]; sec = sector_map(P)
import runpy
try:
    runpy.run_path(os.path.join(HERE, "screen1.py"), run_name="screen1_events")
except ImportError:
    pass
ev = pd.read_parquet("/tmp/div_events_dy.parquet")
secw = {}
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in tix]; m = mem[cols].astype(float)
    secw[s] = m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
rows = []
for cond in ("high", "all"):
    e = ev if cond == "all" else ev[ev.terc == "high"]
    for W in (20, 10, 5):
        F = np.zeros((len(dates), len(tix)))
        for i, c in zip(e.ri.values, e.ci.values):
            F[i - W - 1:i - 1, c] = 1.0             # held at closes of bars -W-1 .. -2 -> earns bars -W .. -1
        fl = pd.DataFrame(F, index=dates, columns=tix).astype(bool) & mem
        n = fl.sum(axis=1)
        wl = fl.astype(float).div(n.replace(0, np.nan), axis=0).fillna(0.0) * 0.5
        wh = pd.DataFrame(0.0, index=dates, columns=tix)
        for s, cols in sec.groupby(sec).groups.items():
            cols = [c for c in cols if c in tix]
            wh[cols] -= secw[s][cols].mul(wl[cols].sum(axis=1), axis=0)
        w = (wl + wh).loc["2011-01-01":]
        for cost in (5.0, 0.0):
            net, st = xs_backtest(w, ret.loc["2011-01-01":], cost_bps=cost)
            r = splits_row(net, st); r.update({"cond": cond, "W": W, "cost": cost, "names": n.loc["2011":].mean()}); rows.append(r)
d = pd.DataFrame(rows).set_index(["cond", "W", "cost"])
print(d.round(3).to_string()); d.round(4).to_csv(os.path.join(HERE, "screen2_eventbook_results.csv"))
