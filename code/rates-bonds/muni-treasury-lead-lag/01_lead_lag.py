"""Do municipal bond ETFs follow Treasuries with a lag?

Munis trade by appointment; their evaluated prices adjust to a Treasury move over days. If the
ETF price inherits part of that, the muni ETF's return over the next sessions is predictable
from today's Treasury return, and a book that is long the muni ETF / short beta x IEF after a
Treasury rally (and the reverse after a sell-off) earns the catch-up.

Protocol fixed up front: IS 2008-01 .. 2017-12, OOS 2018-01 .. 2026-10; 2 bp per side on
every leg; signal at close t, position held from close t (the sim convention; all inputs are
closing prices of liquid ETFs, IEF itself being the signal).

Part 1  distributed-lag regression of each muni ETF's return on IEF's return at lags 0..5
Part 2  the hedged residual (muni - beta x IEF) on lagged IEF returns: what a hedged book earns
Part 3  books: position = clip(k-day IEF return / its trailing vol, -1, 1) in the hedged muni
        leg; k = 1, 2, 3, 5; all days or |z| > 1 only; equal weight over the muni ETFs
Part 4  placebo: the same with the signal lagged a further 5 sessions, and with LQD (a liquid
        credit ETF that should NOT lag) in place of the munis
"""
import os
import sys
import itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "shared"))
from rb_data import etf_close

pd.set_option("display.width", 220)
MUNI = ["MUB", "TFI", "ITM", "SHM", "SUB", "PZA", "HYD", "VTEB"]
HEDGE = "IEF"
IS, OOS = ("2008-01-01", "2017-12-31"), ("2018-01-01", "2026-12-31")
px = etf_close(MUNI + [HEDGE, "LQD", "SHY"]).loc["2007-10":]
ret = px.pct_change(fill_method=None)
ief = ret[HEDGE]


def sh(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(252) if len(r) > 60 and r.std() > 0 else np.nan


def ols(y, X):
    df = pd.concat([y, X], axis=1).dropna()
    Y, Z = df.iloc[:, 0].values, np.column_stack([np.ones(len(df)), df.iloc[:, 1:].values])
    b = np.linalg.lstsq(Z, Y, rcond=None)[0]
    u = Y - Z @ b
    xu = Z * u[:, None]
    S = xu.T @ xu
    for L in range(1, 6):
        g = xu[L:].T @ xu[:-L]
        S += (1 - L / 6) * (g + g.T)
    V = np.linalg.inv(Z.T @ Z) @ S @ np.linalg.inv(Z.T @ Z)
    return b[1:], b[1:] / np.sqrt(np.diag(V)[1:]), len(df)


print("Part 1: beta of the muni ETF's return on IEF's return at lag j (t-stat)")
lags = pd.concat({f"L{j}": ief.shift(j) for j in range(0, 6)}, axis=1)
rows = []
for m in MUNI + ["LQD"]:
    for lab, (a, b) in (("IS", IS), ("OOS", OOS)):
        beta, t, n = ols(ret[m].loc[a:b], lags.loc[a:b])
        rows.append(dict(etf=m, split=lab, n=n, **{f"b{j}": beta[j] for j in range(6)}, **{f"t{j}": t[j] for j in range(6)},
                         sum_lagged=beta[1:].sum()))
p1 = pd.DataFrame(rows)
p1.to_csv("01_distributed_lag.csv", index=False)
print(p1[["etf", "split", "n", "b0", "b1", "t1", "b2", "t2", "b3", "t3", "sum_lagged"]].round(3).to_string(index=False))

print("\nPart 2/3: hedged books (equal weight over muni ETFs with data), gross / net Sharpe at 2 bp")
beta = pd.DataFrame({m: ret[m].rolling(250, min_periods=120).cov(ief) / ief.rolling(250, min_periods=120).var() for m in MUNI + ["LQD"]})
vol = ief.rolling(250, min_periods=120).std()


def book(names, k, zmin=0.0, extra_lag=0, hold=1, cost=2.0):
    z = (ief.rolling(k).sum() / (vol * np.sqrt(k))).shift(extra_lag)
    pos = z.clip(-1, 1).where(z.abs() >= zmin, 0.0)
    if hold > 1:
        pos = pos.rolling(hold).mean()
    live = ret[names].notna() & beta[names].shift(1).notna()
    n = live.sum(axis=1).replace(0, np.nan)
    w_m = live.astype(float).div(n, axis=0).mul(pos, axis=0)                 # weights in the muni ETFs
    w_h = -(w_m * beta[names]).sum(axis=1)                                   # hedge in IEF
    wm, wh = w_m.shift(1).fillna(0.0), w_h.shift(1).fillna(0.0)
    gross = (wm * ret[names].fillna(0.0)).sum(axis=1) + wh * ief.fillna(0.0)
    turn = wm.diff().abs().sum(axis=1) + wh.diff().abs()
    return gross - turn * cost / 1e4, gross, turn.sum() / (len(turn) / 252)


rows = []
for k, zmin, hold in itertools.product((1, 2, 3, 5), (0.0, 1.0), (1, 3)):
    net, gross, turn = book(MUNI, k, zmin, hold=hold)
    rows.append(dict(k=k, zmin=zmin, hold=hold, IS_gross=sh(gross, *IS), OOS_gross=sh(gross, *OOS), IS_net=sh(net, *IS), OOS_net=sh(net, *OOS),
                     turn=turn, OOS_gross_ann=gross.loc[OOS[0]:].mean() * 252 * 100))
p3 = pd.DataFrame(rows)
p3.to_csv("01_books.csv", index=False)
print(p3.round(2).to_string(index=False))
b = p3.sort_values("IS_net", ascending=False).iloc[0]
print("IS-best net: k=%d zmin=%.1f hold=%d -> IS %.2f / OOS %.2f (gross %.2f / %.2f)" % (b.k, b.zmin, b.hold, b.IS_net, b.OOS_net, b.IS_gross, b.OOS_gross))

print("\nPart 4: placebos for k=1, all days, hold 1")
for lab, names, extra in (("munis, signal 5 sessions stale", MUNI, 5), ("LQD in place of munis", ["LQD"], 0), ("MUB only", ["MUB"], 0),
                          ("less liquid only (PZA, HYD, SUB, ITM)", ["PZA", "HYD", "SUB", "ITM"], 0)):
    net, gross, turn = book(names, 1, 0.0, extra_lag=extra)
    print("%-40s gross IS %5.2f OOS %5.2f | net IS %5.2f OOS %5.2f | turn %.0fx" % (lab, sh(gross, *IS), sh(gross, *OOS), sh(net, *IS), sh(net, *OOS), turn))
print("\nby sub-period, k=1 all days, gross / net:")
net, gross, _ = book(MUNI, 1, 0.0)
for a, b_ in (("2008", "2011"), ("2012", "2014"), ("2015", "2017"), ("2018", "2020"), ("2021", "2023"), ("2024", "2026")):
    print(a, b_, "%.2f / %.2f" % (sh(gross, a, b_), sh(net, a, b_)))
