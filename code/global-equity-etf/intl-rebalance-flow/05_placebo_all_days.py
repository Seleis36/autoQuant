"""Placebo for the stock-bond drift: on EVERY session t, regress r_SPY(t+1) and r_INTL(t+1)
on the trailing 15-session (SPY - TLT) drift through t (z-scored), and group the slopes by
the relative position of t+1 in the month (sessions-to-month-end). If the effect is
rebalancing, it should concentrate at the turn of the month; if it is generic reversal,
it should be flat."""
import sys, os
import numpy as np, pandas as pd
from lib import load, spreads, SPL
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import data as D

C, R = load()
B = D.load_panel(["TLT"], start="1998-12-01").pct_change()
S = spreads(R)
idx = S.index
dr = (S["spy"] - B["TLT"])
vol = dr.rolling(252, min_periods=126).std()
per = idx.to_period("M")
pos = pd.Series(np.arange(len(idx)), index=idx)
j_back = (pos - pos.groupby(per).transform("max"))          # 0 at last session
j_fwd = (pos - pos.groupby(per).transform("min") + 1)       # 1 at first session
rel = pd.Series(np.where(j_fwd <= 3, j_fwd, j_back), index=idx)  # +1..+3 start, else <=0
for W in [15]:
    sig = (dr.rolling(W).sum() / (vol * np.sqrt(W)))          # known at close t
    out = {}
    for on in ["spy", "intl"]:
        y = S[on].shift(-1)                                    # return t+1
        df = pd.DataFrame({"x": sig, "y": y, "rel": rel.shift(-1)}).dropna()
        for pn, (a, b) in SPL.items():
            d = df.loc[a:b]
            for r_, g in d.groupby("rel"):
                if r_ < -12: continue
                X = g.x - g.x.mean(); bta = (X * g.y).sum() / (X ** 2).sum()
                res = g.y - g.y.mean() - bta * X
                t = bta / np.sqrt((res ** 2).sum() / (len(g) - 2) / (X ** 2).sum())
                out.setdefault((on, pn), {})[int(r_)] = f"{bta*1e4:5.1f}({t:5.2f})"
            # pooled "other days" (rel in -12..-5 and +3)
            g = d[(d.rel <= -5) | (d.rel >= 3)]
            X = g.x - g.x.mean(); bta = (X * g.y).sum() / (X ** 2).sum()
            res = g.y - g.y.mean() - bta * X
            t = bta / np.sqrt((res ** 2).sum() / (len(g) - 2) / (X ** 2).sum())
            out[(on, pn)]["other"] = f"{bta*1e4:5.1f}({t:5.2f})"
    print(f"\n=== trailing {W}-session SPY-TLT drift -> next-day return, by relative day of the next day")
    print(pd.DataFrame(out).to_string())
