"""Residual momentum screen (Blitz-Huij-Martens 2011; Gutierrez-Pirinsky 2007) on S&P 500 members.

Residual r_t - bM*M_t - bS*S_t with (bM, bS) from a trailing daily OLS (market = EW members,
sector = EW members of the stock's GICS sector), estimated over `est` days ending at t.
Signal = sum of residuals over [t-L, t-skip] / (their std * sqrt(n)) -- a residual t-stat.
Plus: raw 12-1, 52-week-high proximity (George-Hwang), frog-in-the-pan information
discreteness (Da-Gurun-Warachka), and sector-neutral / beta-hedged monthly books at 5 bp."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "quality-value-composite"))
from common import *
from panel import load_panel

P = load_panel()
close = P["close"]; dates = close.index; tix = close.columns
ret = close.pct_change(fill_method=None)
mem = P["member"]
sec = sector_map(P)
r = ret.where(mem)
M = r.mean(axis=1)
Ssec = pd.DataFrame(index=dates, columns=tix, dtype=float)
for s, cols in sec.groupby(sec).groups.items():
    cols = [c for c in cols if c in tix]
    Ssec[cols] = np.repeat(r[cols].mean(axis=1).values[:, None], len(cols), axis=1)
rr = ret.fillna(0.0)


def betas(est):
    k = dict(window=est, min_periods=int(est * 0.8))
    Mf = pd.DataFrame(np.repeat(M.values[:, None], len(tix), axis=1), index=dates, columns=tix)
    x1, x2, y = Mf, Ssec.fillna(0.0), rr
    m1, m2, my = x1.rolling(**k).mean(), x2.rolling(**k).mean(), y.rolling(**k).mean()
    c11 = (x1 * x1).rolling(**k).mean() - m1 * m1
    c22 = (x2 * x2).rolling(**k).mean() - m2 * m2
    c12 = (x1 * x2).rolling(**k).mean() - m1 * m2
    c1y = (x1 * y).rolling(**k).mean() - m1 * my
    c2y = (x2 * y).rolling(**k).mean() - m2 * my
    det = c11 * c22 - c12 * c12
    bM = (c22 * c1y - c12 * c2y) / det
    bS = (c11 * c2y - c12 * c1y) / det
    return bM, bS, Mf


def resid_mom(est=252, L=252, skip=21, factors="MS"):
    bM, bS, Mf = betas(est)
    if factors == "M":
        k = dict(window=est, min_periods=int(est * 0.8))
        bM = (Mf * rr).rolling(**k).mean() - Mf.rolling(**k).mean() * rr.rolling(**k).mean()
        bM = bM / (Mf.rolling(**k).var(ddof=0)); bS = 0.0 * bM
    # residuals using betas known at t (applied to the formation window ending at t)
    n = L - skip
    sr = rr.rolling(n).sum().shift(skip); sM = Mf.rolling(n).sum().shift(skip); sS = Ssec.fillna(0).rolling(n).sum().shift(skip)
    res_sum = sr - bM * sM - bS * sS
    # residual variance over the formation window: E[(r - bM M - bS S)^2] expanded
    e2 = lambda a, b: (a * b).rolling(n).sum().shift(skip)
    SS = e2(rr, rr) + bM**2 * e2(Mf, Mf) + bS**2 * e2(Ssec.fillna(0), Ssec.fillna(0)) \
        - 2 * bM * e2(rr, Mf) - 2 * bS * e2(rr, Ssec.fillna(0)) + 2 * bM * bS * e2(Mf, Ssec.fillna(0))
    var = (SS - res_sum**2 / n) / (n - 1)
    return res_sum / np.sqrt(var.clip(lower=1e-10) * n), res_sum


sig = {}
lc = np.log(close)
sig["raw_12_1"] = lc.shift(21) - lc.shift(252)
sig["raw_12_1_sector_rel"] = sig["raw_12_1"]           # sector-demeaned by the book anyway
t_ms, s_ms = resid_mom(252, 252, 21, "MS")
sig["resid_MS_12_1_t"] = t_ms; sig["resid_MS_12_1_sum"] = s_ms
t_m, s_m = resid_mom(252, 252, 21, "M")
sig["resid_M_12_1_t"] = t_m
t6, _ = resid_mom(252, 126, 21, "MS"); sig["resid_MS_6_1_t"] = t6
t_long, _ = resid_mom(504, 252, 21, "MS"); sig["resid_MS_12_1_est504_t"] = t_long
sig["hi52"] = close / close.rolling(252, min_periods=200).max()
pos = (ret > 0).astype(float).rolling(231).mean().shift(21); neg = (ret < 0).astype(float).rolling(231).mean().shift(21)
ID = np.sign(sig["raw_12_1"]) * (neg - pos)                      # information discreteness (low = continuous)
sig["fip_mom"] = sig["raw_12_1"].where(ID < ID.median(axis=1).values[:, None])   # momentum among continuous-info names
sig["resid_fip"] = t_ms.where(ID < ID.median(axis=1).values[:, None])

base = mem & close.notna()
rebal = month_ends(dates); rebal = rebal[rebal >= "2010-12-31"]
beta = ret.rolling(252, min_periods=200).cov(M).div(M.rolling(252, min_periods=200).var(), axis=0)
mw = mem.astype(float); mw = mw.div(mw.sum(axis=1), axis=0)
rows = []; W = {}
for k, s in sig.items():
    mask = base & s.notna()
    z = sector_z(s, sec, mask)
    for kind in ("quintile", "linear"):
        for hedge in ("none", "beta"):
            w = hold_monthly(book_weights(z, mask, kind=kind), rebal).loc["2011-01-01":]
            if hedge == "beta":
                bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
                w = w - mw.loc[w.index].mul(bw, axis=0)
            net, st = xs_backtest(w, ret.loc["2011-01-01":], cost_bps=5.0, name=k)
            row = splits_row(net, st); row.update({"signal": k, "kind": kind, "hedge": hedge}); rows.append(row)
            W[(k, kind, hedge)] = net
d = pd.DataFrame(rows).set_index(["signal", "kind", "hedge"])
pd.set_option("display.width", 200)
print(d.round(3).to_string())
d.round(4).to_csv(os.path.join(HERE, "screen1_results.csv"))
pd.DataFrame({"|".join(k): v for k, v in W.items()}).to_parquet(os.path.join(HERE, "nets_0_screen1.parquet"))
pickle.dump({k: sig[k] for k in ("resid_MS_12_1_t", "hi52", "raw_12_1")}, open("/tmp/rm_sig.pkl", "wb"))
