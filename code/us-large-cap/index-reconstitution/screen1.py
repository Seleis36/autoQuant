"""Tradeable post-inclusion reversal: short each ADDED name at the close of bar 0 (the effective
session; public by then), cover after H bars, hedged with its sector's EW member basket.
Per-event stats by half and by change type, and a sparse event book (fixed weight per event)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
import runpy
g = runpy.run_path(os.path.join(HERE, "event_study.py"), run_name="es")
E, C, dates, tix, ret, mem, sec, close = g["E"], g["C"], g["dates"], g["tix"], g["ret"], g["mem"], g["sec"], g["close"]
from common import splits_row
from xs_lib import xs_backtest

A = E[E.side == "add"].copy()
rows = []
for H in (1, 3, 5, 10, 20):
    i0 = A.ri.values; i1 = np.minimum(A.ri.values + H, len(dates) - 1)
    v = -(C[i1, A.ci.values] - C[i0, A.ci.values]) * 1e4          # short P&L, bp
    A[f"s{H}"] = v
    for name, m in {"all": np.ones(len(A), bool), "IS": (A.eff < "2018").values, "OOS": (A.eff >= "2018").values,
                    "acq-replacement": (A.kind == "acq").values, "cap-change": (A.kind == "cap").values}.items():
        x = v[m]
        rows.append({"H": H, "subset": name, "N": len(x), "mean_bp": x.mean(), "t": x.mean() / x.std() * np.sqrt(len(x)),
                     "hit": (x > 0).mean()})
d = pd.DataFrame(rows).set_index(["H", "subset"])
print(d.round(2).to_string())
d.round(3).to_csv(os.path.join(HERE, "screen1_short_additions.csv"))
print("by year (H=5):", A.groupby(A.eff.dt.year).s5.mean().round(0).to_dict())

# sparse book: each event short 1/K of capital (K = max concurrent events expected), sector-hedged
secw = {}
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in tix]; m = mem[cols].astype(float)
    secw[s] = m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
for H in (3, 5):
    W = pd.DataFrame(0.0, index=dates, columns=tix)
    for _, e in A.iterrows():
        a, b = e.ri, min(e.ri + H, len(dates) - 1)       # held at closes a .. b-1 -> earns bars a+1 .. b
        W.iloc[a:b, e.ci] -= 0.25
        s = sec.get(e.ticker, "UNK")
        if s in secw:
            cols = list(secw[s].columns)
            W.loc[W.index[a:b], cols] = W.loc[W.index[a:b], cols].values + 0.25 * secw[s].iloc[a:b].values
    w = W.loc["2011-01-01":]
    for cost in (5.0, 0.0):
        net, st = xs_backtest(w, ret.fillna(0).loc["2011-01-01":], cost_bps=cost)
        r = splits_row(net, st)
        print(f"H={H} cost={cost}: ", {k: round(v, 3) for k, v in r.items()}, "days active %.2f" % ((w.abs().sum(axis=1) > 0).mean()))
A.to_parquet("/tmp/recon_additions.parquet")
