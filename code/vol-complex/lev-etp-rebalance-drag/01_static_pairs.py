"""Static-hold leveraged-ETP pairs, rebalanced every H sessions.

Pair A: short $1 UVXY, long $L VIXY (L = UVXY leverage: 2.0 until 2018-02-27, 1.5 from 2018-02-28).
Pair B: short $1 UVXY, short $k SVXY with k = L_uvxy / |L_svxy| (2/1 before, 1.5/0.5 after), gross scaled to 1.
Pair C: long $1 SVXY, long $|L_svxy| VIXY (inverse vs 1x, both long -> no borrow).
Holdings are share counts fixed between rebalances (weights drift). Cost 5 bp/side on traded notional
at each rebalance; borrow charged daily on short notional at b %/yr. Leverage schedule is public ex ante.
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
import vc_data as vc

P = vc.panel().loc["2011-10-05":]
px = P[["UVXY", "VIXY", "SVXY"]]
chg = pd.Timestamp("2018-02-28")
Lu = pd.Series(np.where(P.index < chg, 2.0, 1.5), index=P.index)
Ls = pd.Series(np.where(P.index < chg, 1.0, 0.5), index=P.index)

def target(kind, t):
    if kind == "A":
        w = {"UVXY": -1.0, "VIXY": Lu[t], "SVXY": 0.0}
    elif kind == "B":
        w = {"UVXY": -1.0, "VIXY": 0.0, "SVXY": -Lu[t] / Ls[t]}
    else:
        w = {"UVXY": 0.0, "VIXY": Ls[t], "SVXY": 1.0}
    g = sum(abs(v) for v in w.values())
    return {k: v / g for k, v in w.items()}

def sim(kind, H, cost_bps=5.0, borrow=0.0):
    dates = px.index
    cap = 1.0
    sh = pd.Series(0.0, index=px.columns)
    rets = []
    for i, t in enumerate(dates):
        p = px.loc[t]
        if i > 0:
            pnl = (sh * (p - px.iloc[i - 1])).sum()
            short_notional = (-(sh.clip(upper=0)) * px.iloc[i - 1]).sum()
            pnl -= short_notional * borrow / 252
            rets.append(pnl / cap); cap += pnl
        # rebalance at close t (every H sessions, also on the leverage-change day)
        if i % H == 0 or t == chg:
            w = pd.Series(target(kind, t))
            new = w * cap / p
            cap -= (abs(new - sh) * p).sum() * cost_bps / 1e4
            sh = new
    return pd.Series([0.0] + rets, index=dates)

rows = {}
for kind in ("A", "B", "C"):
    for H in (1, 5, 10, 21, 63):
        for b in ((0.0, 0.05) if kind != "C" else (0.0,)):
            r = sim(kind, H, borrow=b)
            rows[(kind, H, b)] = vc.split_row(r, {"vol": r.std() * np.sqrt(252)})
res = pd.DataFrame(rows).T
res.index.names = ["pair", "H", "borrow"]
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 100)
print(res.round(3))
r = P["VIXY"].pct_change()
for k, (a, b) in vc.SPLITS.items():
    x = r.loc[a:b].dropna()
    print(k, "VIXY AC1 %.3f AC2 %.3f  var ratio 5d %.3f 21d %.3f" % (x.autocorr(1), x.autocorr(2),
          np.log1p(x).rolling(5).sum().var() / (5 * np.log1p(x).var()), np.log1p(x).rolling(21).sum().var() / (21 * np.log1p(x).var())))
