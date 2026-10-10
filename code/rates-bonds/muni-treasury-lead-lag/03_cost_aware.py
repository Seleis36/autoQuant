"""Cost-aware sizing. The z-score book takes the same position after a 1-sigma Treasury move
in a quiet year as in a wild one, but the muni catch-up is proportional to the move in bp and
the cost is fixed in bp: it bleeds in calm years (2014-19, 2024-25).

    move = IEF return over the last k sessions (not vol-scaled)
    pos  = sign(move) x clip((|move| - dead) / (full - dead), 0, 1)

so nothing is held below `dead` and the full position is reached at `full`.
Selection: IS (2008-17) net Sharpe at a 4 bp stress cost. Also prints dollar volumes, for a
liquidity rule on the universe.
"""
import os
import sys
import itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "shared"))
import research_lib as rl
from rb_data import etf_close
import book as S

pd.set_option("display.width", 220)
IS, OOS = ("2008-01-01", "2017-12-31"), ("2018-01-01", "2026-12-31")
px = etf_close(S.TICKERS).loc["2007-10":]
ret = px.pct_change(fill_method=None)
ief = ret["IEF"]

print("median daily dollar volume, $M:")
dv = {}
for t in S.MUNI:
    d = rl.load_series(t)
    x = (d["Close"] * d["Volume"]) / 1e6
    dv[t] = {"2012-14": x.loc["2012":"2014"].median(), "2018-20": x.loc["2018":"2020"].median(), "2024-26": x.loc["2024":].median(),
             "price": d["Close"].iloc[-1]}
print(pd.DataFrame(dv).round(1).to_string())


def sh(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(252) if len(r) > 60 and r.std() > 0 else np.nan


beta = pd.DataFrame({m: ret[m].rolling(250, min_periods=120).cov(ief) / ief.rolling(250, min_periods=120).var() for m in S.MUNI})


def book(k, dead, full, munis=S.MUNI, cost=2.0):
    move = ief.rolling(k).sum()
    pos = np.sign(move) * ((move.abs() - dead) / (full - dead)).clip(0, 1)
    live = px[list(munis)].notna() & beta[list(munis)].notna()
    n = live.sum(axis=1).replace(0, np.nan)
    w = live.astype(float).div(n, axis=0).mul(pos, axis=0).fillna(0.0)
    w["IEF"] = -(w[list(munis)] * beta[list(munis)].fillna(0)).sum(axis=1)
    we = w.shift(1).fillna(0.0)
    gross = (we * ret[w.columns].fillna(0.0)).sum(axis=1)
    turn = we.diff().abs().sum(axis=1)
    return gross, turn, w


rows = []
for k, dead, full in itertools.product((2, 3, 5), (0.0, 0.0025, 0.005, 0.0075), (0.01, 0.015, 0.02)):
    g, t, w = book(k, dead, full)
    r = {c: g - t * c / 1e4 for c in (0, 2, 4)}
    rows.append(dict(k=k, dead=dead, full=full, IS4=sh(r[4], *IS), IS2=sh(r[2], *IS), OOS4=sh(r[4], *OOS), OOS2=sh(r[2], *OOS),
                     IS0=sh(r[0], *IS), OOS0=sh(r[0], *OOS), turn=t.loc[IS[0]:].sum() / (len(t.loc[IS[0]:]) / 252),
                     gross_exp=w.loc[IS[0]:].abs().sum(axis=1).mean(), active=(w.loc[IS[0]:].abs().sum(axis=1) > 0).mean()))
out = pd.DataFrame(rows)
out.to_csv("03_cost_aware.csv", index=False)
cols = ["k", "dead", "full", "IS4", "IS2", "IS0", "turn", "gross_exp", "active"]
if "--oos" in sys.argv:
    cols += ["OOS4", "OOS2", "OOS0"]
print("\n%d cells, sorted by IS net Sharpe at 4 bp" % len(out))
print(out.sort_values("IS4", ascending=False)[cols].round(3).to_string(index=False))
if "--oos" in sys.argv:
    print("IS/OOS rank corr at 4 bp: %.2f ; at 2 bp: %.2f" % (out[["IS4", "OOS4"]].corr(method="spearman").iloc[0, 1],
                                                              out[["IS2", "OOS2"]].corr(method="spearman").iloc[0, 1]))
    print(out[["IS4", "OOS4", "IS2", "OOS2"]].describe().loc[["mean", "min", "max"]].round(2).to_string())
