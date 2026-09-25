"""Re-framing: the TOM33+PREF+PREH window book with (a) inverse-vol sizing (Moreira-Muir),
(b) SMA200 trend gate on the basket, (c) a tilt instead of on/off: 1+x in-window, 1-x out.
Per-year P&L of the base book printed to see where it earns."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import data, sxlib as sx
import books as bk  # noqa: builds windows (re-prints its table)

c = bk.c; S = bk.S
on = pd.concat([bk.win[p] for p in ["TOM33", "PREF", "PREH"]], axis=1).any(axis=1).astype(float)
B = bk.basket("EW")
ewret = (B.shift(1) * c.pct_change()).sum(axis=1)
idx = (1 + ewret).cumprod()
vol = ewret.ewm(halflife=20, min_periods=20).std() * np.sqrt(252)
trend = (idx > idx.rolling(200).mean()).astype(float)
rows = []
for tv, tr in itertools.product([None, 0.15, 0.20], [False, True]):
    sc = pd.Series(1.0, index=c.index) if tv is None else (tv / vol).clip(upper=2.0).fillna(0)
    g = trend if tr else 1.0
    W = B.mul(on * sc * g, axis=0)
    st, net = sx.summary(W, c, name=f"win|tv{tv}|trend{int(tr)}"); rows.append(st)
    Wb = B.mul(sc * g, axis=0)
    st, _ = sx.summary(Wb, c, name=f"always|tv{tv}|trend{int(tr)}"); rows.append(st)
for x in [0.25, 0.5]:
    W = B.mul(1 - x + 2 * x * on, axis=0)
    st, _ = sx.summary(W, c, name=f"tilt{x}"); rows.append(st)
print("\n#### overlays")
print(sx.fmt(pd.DataFrame(rows)))
_, net = sx.summary(B.mul(on, axis=0), c)
print((net.groupby(net.index.year).sum() * 100).round(1).to_string())
