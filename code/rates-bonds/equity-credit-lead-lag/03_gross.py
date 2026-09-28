"""equity-credit-lead-lag -- round 3: gross vs net, both directions, 1-day and 5-day holds.
Separates the signal from the cost drag that dominates 02_books (daily sign flips on a
two-leg spread cost ~4 bp/day)."""
import os, sys
import numpy as np, pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _HERE)
from importlib import import_module
scr = import_module("01_screen")
pd.set_option("display.width", 220)

def sh(x):
    x = x.dropna(); return x.mean() / x.std() * np.sqrt(252) if len(x) > 200 else np.nan

r, cr = scr.load(); spy = r["SPY"]; rows = []
for k in cr.columns:
    y = cr[k]; hedge = scr.HEDGE[k][1]
    beta = y.rolling(252, min_periods=126).cov(spy) / spy.rolling(252, min_periods=126).var()
    for pname, p in (("spy1", spy), ("resid1", -(y - beta * spy)), ("own1", y), ("own5", y.rolling(5).sum())):
        for h in (1, 5):
            w = np.sign(p).rolling(h, min_periods=1).mean().fillna(0); we = w.shift(1).fillna(0)
            g = we * y; turn = we.diff().abs().fillna(0) * (1 + hedge)
            for c in (0, 1, 2):
                n = g - turn * c * 1e-4
                rows.append(dict(credit=k, pred=pname, h=h, cost_bp=c, IS=sh(n.loc["2007-04":"2017"]),
                                 IS10=sh(n.loc["2010":"2017"]), OOS=sh(n.loc["2018":]),
                                 turn_yr=turn.mean() * 252))
t = pd.DataFrame(rows)
print("follow-sign books (fade = minus gross Sharpe); cost in bp/side on both legs")
print(t.pivot_table(index=["credit", "pred", "h"], columns="cost_bp", values=["IS10", "OOS"]).round(2).to_string())
print(t[t.cost_bp == 0].groupby(["credit", "pred", "h"]).turn_yr.first().round(0).unstack().to_string())
t.to_csv(os.path.join(_HERE, "03_gross.csv"), index=False)
