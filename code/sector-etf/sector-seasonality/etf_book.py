"""Part B: the same-month seasonal signal traded on the ETFs (daily book, month-end
rebalance, SPY hedge to beta 0, 2 bp/side). All 24 signal x construction cells."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx, french
from seasonal_grid import sigs, qw, xs_weights  # noqa  (re-runs Part A print)

c = data.load_panel()
r = c.pct_change()
S = data.SECTORS
beta = sx.beta_to(r[S], r["SPY"], halflife=126).fillna(1.0)
mask = c[S].notna()
# month-end trading days: the last trading day of each calendar month
me = c.index.to_series().groupby(c.index.to_period("M")).max()
rows = []
for (L, kind), sig in sigs.items():
    for n in [2, 3, "lin"]:
        sd = sig.copy(); sd.index = sd.index.to_period("M")
        sd = sd.reindex(me.index.to_period("M") if hasattr(me.index, "to_period") else me.index)
        sd.index = me.values
        av = mask.reindex(sd.index) & sd.notna()
        w = qw(sd, av, n) if n != "lin" else xs_weights(sd, av, "lin")
        w = w.reindex(c.index).ffill().fillna(0)
        w = w.where(mask, 0)
        W = w.copy(); W["SPY"] = -(w * beta).sum(axis=1)
        st, _ = sx.summary(W, c, name=f"L{L}|{kind}|{n}")
        rows.append(st)
df = pd.DataFrame(rows)
print(sx.fmt(df.sort_values("Sh_IS", ascending=False)))
df.to_csv(os.path.join(os.path.dirname(__file__), "partB_etf.csv"))
