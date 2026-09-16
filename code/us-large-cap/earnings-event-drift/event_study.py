"""Earnings event study on the S&P 500 panel: sector-residual returns around the reaction
bar, pre-window (announcement premium), post-window conditional on reaction (PEAD),
IS (2010-17) / OOS (2018-26). Also validates Yahoo dates via the volume spike."""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from xs_lib import *
from earnings import load_earnings, reaction_day_matrix

P = load_panel()
C, V, M = P["close"], P["volume"], P["member"]
sec = P["sector"].fillna("UNK")
ret = C.pct_change(); logret = np.log(C).diff()
mask = M & C.notna()
E = load_earnings()
print("earnings rows", len(E), "tickers", E.ticker.nunique(), "amc share", E.amc.mean().round(2))
R = reaction_day_matrix(E, C.index, C.columns) & mask
print("reaction bars", R.sum().sum(), " per year", R.sum().sum() / 16.7)
# validation: volume ratio on reaction bar vs 20d avg
vr = (V / V.rolling(20).mean().shift(1))
print("median vol ratio on reaction bar:", vr.where(R).stack().dropna().median().round(2), " day-1:", vr.shift(-1).where(R).stack().dropna().median().round(2), " day+1:", vr.shift(1).where(R).stack().dropna().median().round(2))
print("share of reaction bars with vol ratio>1.5:", (vr.where(R).stack().dropna() > 1.5).mean().round(2))

res = group_demean(ret, sec, mask)                # daily sector-residual return
lres = res.where(mask)   # simple residual returns (log1p sum understates by var/2 ~ 1bp/day)

def win_ret(a, b):
    """residual return summed over bars [t+a, t+b] relative to reaction bar t (a<=b)."""
    out = 0
    for k in range(a, b + 1):
        out = out + lres.shift(-k)
    return out

def report(name, x, ev):
    s = x.where(ev).stack().dropna()
    si = s[s.index.get_level_values(0) < "2018-01-01"]; so = s[s.index.get_level_values(0) >= "2018-01-01"]
    t = lambda v: v.mean() / v.std() * np.sqrt(len(v))
    print(f"{name:32s} N={len(s):6d} mean {s.mean()*1e4:+6.0f}bp t={t(s):5.1f} | IS {si.mean()*1e4:+6.0f}bp t={t(si):4.1f} | OOS {so.mean()*1e4:+6.0f}bp t={t(so):4.1f} | hit {(s>0).mean():.2f}")

print("\n== unconditional windows (sector-residual, bp)")
for name, (a, b) in {"pre[-10,-6]": (-10, -6), "pre[-5,-2]": (-5, -2), "pre[-1]": (-1, -1), "pre[-5,-1]": (-5, -1),
                     "react[0]": (0, 0), "react[0,+1]": (0, 1), "post[+1]": (1, 1), "post[+2,+5]": (2, 5),
                     "post[+2,+10]": (2, 10), "post[+2,+21]": (2, 21), "post[+2,+42]": (2, 42)}.items():
    report(name, win_ret(a, b), R)

print("\n== PEAD: post windows conditional on reaction-bar residual return quintile (cross-sectional within reaction bars)")
react = lres.shift(0).where(R)                      # reaction day residual (the print's surprise proxy)
react2 = (lres.shift(0) + lres.shift(1)).where(R)   # 2-day
for lab, rr in [("react1", react), ("react2", react2)]:
    # quintile by rank across all events in a rolling 63-day window is complex; use fixed z: rr / vol20
    vol20 = logret.rolling(20).std().shift(1)
    z = rr.div(vol20)
    for cond_name, ev in {"z>+2": z > 2, "z in(1,2)": (z > 1) & (z <= 2), "z in(-1,1)": (z > -1) & (z <= 1), "z in(-2,-1)": (z > -2) & (z <= -1), "z<-2": z < -2}.items():
        for w_name, (a, b) in {"post[+1,+5]": (1, 5), "post[+2,+21]": (2, 21), "post[+2,+42]": (2, 42)}.items():
            report(f"{lab} {cond_name} {w_name}", win_ret(a, b), ev & R)
    print()
