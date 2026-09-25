"""Same-calendar-month seasonality (Heston-Sadka 2008, Keloharju-Linnainmaa-Nyberg 2016)
across the 11 SPDR sectors.

Signal for month m of year Y: mean return of the sector proxy (French 49 industries
mapped to GICS, `french.py`) in calendar month m over years Y-L..Y-1; variant 'ex' subtracts
the proxy's mean over *all* months of those years (pure seasonal component).
Part A: long history on the proxies themselves (1946-1998 = holdout before any ETF existed,
plus 1999-2026). Part B: traded on the ETFs from month-end close, SPY-hedged to beta 0.
"""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx, french

fr = french.sector_returns()
S = data.SECTORS

def seasonal_signal(fr, L, kind):
    """Row t (month end) -> signal for month t+1, using only months <= t-11."""
    out = pd.DataFrame(index=fr.index, columns=fr.columns, dtype=float)
    months = fr.index.month
    for i, t in enumerate(fr.index):
        tgt = (t + pd.offsets.MonthEnd(1))
        past = fr.loc[:t - pd.DateOffset(months=11)]           # last usable = same month last year
        past = past.loc[past.index > tgt - pd.DateOffset(years=L)]
        same = past[past.index.month == tgt.month]
        if len(same) < max(5, L // 2):
            continue
        sig = same.mean()
        if kind == "ex":
            sig = sig - past.mean()
        out.loc[t] = sig
    return out

def xs_weights(sig, avail, k):
    s = sig.where(avail)
    if k == "lin":
        s = s.sub(s.mean(axis=1), axis=0)
        return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    return pd.DataFrame(__import__("research_lib").quantile_weights(s, avail, q=k / 11, gross=1.0),
                        index=s.index, columns=s.columns)

def qw(s, avail, n):
    s = s.where(avail)
    rk_hi = s.rank(axis=1, ascending=False); rk_lo = s.rank(axis=1)
    L = (rk_hi <= n).astype(float); Sh = (rk_lo <= n).astype(float)
    return (L.div(L.sum(axis=1), axis=0) * 0.5 - Sh.div(Sh.sum(axis=1), axis=0) * 0.5).fillna(0)

sigs = {(L, kind): seasonal_signal(fr, L, kind) for L in [10, 20, 30, 50] for kind in ["raw", "ex"]}

# ---- Part A: proxies, monthly, gross (no hedge: dollar-neutral), 1946-1998 and 1999-2026
print("Part A: proxy L/S monthly Sharpe (gross, dollar-neutral)")
rowsA = []
for (L, kind), sig in sigs.items():
    for n in [2, 3, "lin"]:
        avail = fr.notna() & sig.notna()
        w = qw(sig, avail, n) if n != "lin" else xs_weights(sig, avail, "lin")
        ret = (w.shift(1) * fr).sum(axis=1)
        row = {"L": L, "kind": kind, "n": n}
        for a, b in [("1946", "1998"), ("1999", "2014"), ("2015", "2026")]:
            x = ret.loc[a:b]; x = x[w.shift(1).loc[a:b].abs().sum(axis=1) > 0]
            row[f"Sh{a[:4]}"] = x.mean() / x.std() * np.sqrt(12)
            row[f"mu{a[:4]}"] = x.mean() * 1200
        rowsA.append(row)
A = pd.DataFrame(rowsA)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(A.round(2))
A.to_csv(os.path.join(os.path.dirname(__file__), "partA_proxy.csv"))
