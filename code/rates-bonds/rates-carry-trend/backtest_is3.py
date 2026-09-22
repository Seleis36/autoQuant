"""Step 3 (IS only) -- duration-neutral curve trades.

Outright duration carry+trend tops out at IS Sharpe 0.6 (step 2), and its last two
IS blocks are 0.13-0.23. Curve trades (2s10s, 5s30s, butterflies) are the other
classic rates sleeve: duration-neutral, so they are not a repackaged bond beta, and
they are directly tradable as duration-weighted SHY/IEF/TLT pairs.
"""
import os, sys
import numpy as np, pandas as pd
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
sys.path.insert(0, os.path.join(H, "..", "..", "shared"))
from curve_lib import yields, total_returns, excess_returns, par_duration
from research_lib import perf_stats
from backtest_is2 import band
from backtest_is import IS, ANN
pd.set_option("display.width", 220, "display.max_columns", 40)

MATS = (2, 5, 10, 30)
y = yields(); tr = total_returns(y, MATS); ex = excess_returns(tr, y)[list(MATS)]

# duration-neutral spread returns: long the long end, short DV01-matched short end
def spread_ret(long_n, short_n):
    Dl = pd.Series(par_duration(y[long_n].shift(1), long_n), index=y.index)
    Ds = pd.Series(par_duration(y[short_n].shift(1), short_n), index=y.index)
    h = (Dl / Ds).clip(0, 20)
    return (ex[long_n] - h * ex[short_n]).rename(f"{short_n}s{long_n}s"), h

pairs = [(10, 2), (30, 5), (30, 10), (5, 2)]
S = {}; H_ = {}
for ln, sn in pairs:
    s, h = spread_ret(ln, sn); S[s.name] = s; H_[s.name] = h
S = pd.DataFrame(S)
print("=== buy-and-hold duration-neutral steepeners, IS 1990-2009 ===")
print(pd.DataFrame({k: perf_stats(S[k].loc[IS[0]:IS[1]].dropna(), ann=ANN, name=k)
                    for k in S}).T[["CAGR", "Vol", "Sharpe", "MaxDD", "t_NW"]].round(3))

# signals: slope carry (the spread's own yield pickup) and spread trend
slope = pd.DataFrame({f"{sn}s{ln}s": y[ln] - y[sn] for ln, sn in pairs})
sidx = (1 + S.fillna(0)).cumprod()


def run(sig, rets, leg_vol=0.05, tvol=0.10, smooth=21, tol=0.05, cost=2.0, name="s", legs=None):
    v = rets.rolling(252, min_periods=126).std() * np.sqrt(ANN)
    w = (sig * (leg_vol / v)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    pr = (w.shift(1) * rets).sum(axis=1)
    pv = pr.rolling(252, min_periods=126).std() * np.sqrt(ANN)
    w = w.mul((tvol / pv).clip(0, 3).shift(1).fillna(0.0), axis=0)
    g = w.abs().sum(axis=1); w = w.div((g / 6.0).clip(lower=1.0), axis=0)
    if smooth: w = w.rolling(smooth).mean()
    w = band(w.fillna(0.0), tol=tol)
    we = w.shift(1).fillna(0.0)
    # turnover counts BOTH legs of each spread
    lg = pd.Series(legs if legs is not None else {c: 1.0 for c in w.columns})
    turn = ((we - we.shift(1).fillna(0.0)).abs() * lg).sum(axis=1)
    net = ((we * rets).sum(axis=1) - turn * cost / 1e4).rename(name)
    st = perf_stats(net.dropna(), ann=ANN, name=name)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ANN)
    st["AvgGross"] = we.abs().sum(axis=1).mean()
    return net, st, w


legs = {f"{sn}s{ln}s": 1.0 + float(np.nanmedian(H_[f"{sn}s{ln}s"])) for ln, sn in pairs}
print("\nspread leg multipliers (1 + DV01 hedge ratio):", {k: round(v, 2) for k, v in legs.items()})

cands = {
    "slope_carry": (slope / 0.01).clip(-1.5, 1.5),
    "slope_carry_sign": np.sign(slope),
    "spread_trend": sum(np.sign(sidx / sidx.rolling(L).mean() - 1) for L in (63, 126, 252)) / 3,
    "slope_z": ((slope - slope.rolling(1260, min_periods=504).mean())
                / slope.rolling(1260, min_periods=504).std()).clip(-2, 2),
}
cands["carry+trend"] = (cands["slope_carry"].clip(-1, 1) + cands["spread_trend"]) / 2
cands["z+trend"] = (cands["slope_z"].clip(-1, 1) + cands["spread_trend"]) / 2
rows, nets = {}, {}
for k, s in cands.items():
    n, st, w = run(s, S, name=k, legs=legs)
    nets[k] = n
    r = perf_stats(n.loc[IS[0]:IS[1]].dropna(), ann=ANN, name=k)
    wi = w.loc[IS[0]:IS[1]]
    t = ((wi.shift(1) - wi.shift(2)).abs() * pd.Series(legs)).sum(axis=1)
    r["Turnover_ann"] = t.sum() / (len(t) / ANN); r["AvgGross"] = wi.abs().sum(axis=1).mean()
    rows[k] = r
print("\n=== IS 1990-2009, curve trades, 2bp/side on every leg ===")
print(pd.DataFrame(rows).T[["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "t_NW", "Turnover_ann", "AvgGross"]].round(3))

print("\n=== IS 5-year blocks ===")
for k in nets:
    n = nets[k].loc[IS[0]:IS[1]]
    line = "  ".join(f"{a}-{b}:{n.loc[a:b].mean()/n.loc[a:b].std()*np.sqrt(ANN):5.2f}"
                     for a, b in [("1990", "1994"), ("1995", "1999"), ("2000", "2004"), ("2005", "2009")])
    print(f"  {k:18s} {line}")
