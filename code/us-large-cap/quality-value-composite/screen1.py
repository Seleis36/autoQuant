"""Screen 1: each fundamental signal alone -- sector-neutral z, monthly rebalance, quintile and
linear dollar-neutral books, 5 bp/side. IC vs next-month return. IS 2011-17 / OOS 2018-26."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from signals import build
from common import *

CACHE = "/tmp/qvc_signals.pkl"
if os.path.exists(CACHE):
    S, P, aux = pickle.load(open(CACHE, "rb"))
else:
    S, P, aux = build()
    pickle.dump((S, P, aux), open(CACHE, "wb"))

close = P["close"]; ret = close.pct_change(fill_method=None)
sec = sector_map(P)
base = P["member"] & aux["mcap"].notna()
rebal = month_ends(close.index)
rebal = rebal[rebal >= "2010-12-31"]
fwd21 = close.shift(-21) / close - 1

rows = []
Z = {}
for k, sig in S.items():
    mask = base & sig.notna()
    z = sector_z(sig, sec, mask)
    Z[k] = z
    ic = ic_series(z.loc[rebal], fwd21.loc[rebal], mask.loc[rebal])
    ics = ic_summary(ic)
    for kind in ("quintile", "linear"):
        net, st, w = run_book(z, mask, ret, rebal, kind=kind, name=k)
        r = splits_row(net, st)
        r.update({"signal": k, "kind": kind, "IC": ics["IC"], "IC_t": ics["IC_t"],
                  "IC_IS": ic.loc[:"2017"].mean(), "IC_OOS": ic.loc["2018":].mean()})
        rows.append(r)
res = pd.DataFrame(rows).set_index(["signal", "kind"])
pd.set_option("display.width", 200)
print(res.round(3).to_string())
res.round(4).to_csv(os.path.join(HERE, "screen1_results.csv"))
pickle.dump(Z, open("/tmp/qvc_Z.pkl", "wb"))
# signal correlation (average cross-sectional rank corr at rebalance dates)
names = list(Z)
C = pd.DataFrame(np.nan, index=names, columns=names)
for i, a in enumerate(names):
    for b in names[i:]:
        cc = []
        for d in rebal[::3]:
            x = Z[a].loc[d]; y = Z[b].loc[d]; m = x.notna() & y.notna()
            if m.sum() > 50:
                cc.append(x[m].rank().corr(y[m].rank()))
        C.loc[a, b] = C.loc[b, a] = np.mean(cc)
print(C.round(2).to_string())
C.round(3).to_csv(os.path.join(HERE, "screen1_signal_corr.csv"))
