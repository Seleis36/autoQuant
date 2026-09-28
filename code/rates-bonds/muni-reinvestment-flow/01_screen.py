"""muni-reinvestment-flow -- seasonal flow effects in municipal bonds vs Treasuries.

Mechanism (practitioner-documented; e.g. muni strategists' "summer reinvestment season"):
  * June 1 / July 1 (and Dec 1 / Jan 1) are the largest muni coupon + principal redemption
    dates; tens of billions are reinvested while new-issue supply is seasonally light ->
    munis outperform Treasuries in June-August;
  * tax season: retail sells munis / funds see outflows into the April 15 deadline ->
    munis underperform in March-April.
Traded object: the duration-hedged muni premium  x = r_MUB - b * r_IEF, with b the trailing
252-day OLS beta (ex-ante; muni yields move ~0.6-0.8 for 1 of Treasuries). Also TFI (SPDR
muni), HYD (high-yield muni), SHM (short muni vs SHY) for breadth.

Pre-registered book (fixed before any number): long x from the first trading day of June
through the last trading day of August, short x from the first trading day of March through
the last trading day of April, flat otherwise. 3 bp/side per leg (muni ETF spreads are wider
than Treasury ETFs'). Split fixed in advance: IS 2008-2016, OOS 2017-2026.
Diagnostics: calendar-month profile and day-of-month (first 3 trading days) profile.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, ANN  # noqa: E402

pd.set_option("display.width", 220)
COST = 3e-4
PAIRS = {"MUB": "IEF", "TFI": "IEF", "HYD": "IEF", "SHM": "SHY", "ITM": "IEF"}


def premia():
    px = etf_close(sorted(set(PAIRS) | set(PAIRS.values())))
    r = px.pct_change()
    out, betas = {}, {}
    for m, t in PAIRS.items():
        d = r[[m, t]].dropna()
        b = (d[m].rolling(252, min_periods=126).cov(d[t]) / d[t].rolling(252, min_periods=126).var()).shift(1)
        out[m] = d[m] - b * d[t]
        betas[m] = b
    return pd.DataFrame(out), pd.DataFrame(betas), r


def season_weight(idx):
    m = pd.Series(idx.month, index=idx)
    w = pd.Series(0.0, index=idx)
    w[m.isin([6, 7, 8])] = 1.0
    w[m.isin([3, 4])] = -1.0
    return w


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(ANN) if len(x) > 100 and x.std() > 0 else np.nan


def main():
    X, B, r = premia()
    X = X.loc["2008":]
    idx = X.index
    print("calendar-month mean of the hedged premium, bp/month (t)")
    rows = []
    for c in X.columns:
        mm = X[c].groupby(idx.to_period("M")).sum()
        for sp, (a, b) in {"IS": ("2008", "2016"), "OOS": ("2017", "2026")}.items():
            s = mm.loc[a:b]
            g = s.groupby(s.index.month)
            for mo, v in g:
                rows.append(dict(inst=c, split=sp, month=mo, bp=v.mean() * 1e4,
                                 t=v.mean() / v.std() * np.sqrt(len(v)) if len(v) > 2 else np.nan))
    t = pd.DataFrame(rows)
    p = t[t.inst == "MUB"].pivot_table(index="month", columns="split", values=["bp", "t"]).round(1)
    print("MUB - b*IEF"); print(p.to_string())
    allm = t.groupby(["split", "month"]).bp.mean().unstack(0).round(1)
    print("\naverage over MUB/TFI/HYD/SHM/ITM, bp/month"); print(allm.to_string())

    # pre-registered seasonal book
    w_target = season_weight(idx)
    brows = []
    for c in X.columns:
        x = X[c]
        # the weight for day t is known in advance (calendar); set at close t-1
        we = w_target.reindex(x.index).fillna(0)
        b = B[c].reindex(x.index).abs().fillna(1)
        net = we * x - we.diff().abs().fillna(0) * (1 + b) * COST
        for sp, (a, bb) in {"IS": ("2008", "2016"), "OOS": ("2017", "2026"), "FULL": ("2008", "2026")}.items():
            n = net.loc[a:bb]
            brows.append(dict(inst=c, split=sp, sharpe=sh(n), ann_ret=n.mean() * ANN * 100,
                              vol=n.std() * np.sqrt(ANN) * 100, long_only=sh((we.clip(lower=0) * x).loc[a:bb]),
                              short_only=sh((we.clip(upper=0) * x).loc[a:bb])))
    bk = pd.DataFrame(brows)
    print("\npre-registered book: long Jun-Aug / short Mar-Apr, 3 bp/side/leg")
    print(bk.pivot_table(index="inst", columns="split", values=["sharpe", "ann_ret", "long_only", "short_only"]).round(2).to_string())

    # day-of-month: first 3 trading days (coupon on the 1st) vs rest
    per = idx.to_period("M")
    s = pd.Series(np.arange(len(idx)), index=idx)
    fwd = s - s.groupby(per).transform("min") + 1
    print("\nfirst 3 trading days of month vs rest, bp/day (t)")
    for c in X.columns:
        for sp, (a, b) in {"IS": ("2008", "2016"), "OOS": ("2017", "2026")}.items():
            x = X[c].loc[a:b]; f = fwd.loc[a:b]
            a1 = x[f <= 3]; a2 = x[f > 3]
            print(f"{c:4s} {sp:3s} first3 {a1.mean()*1e4:6.2f} ({a1.mean()/a1.std()*np.sqrt(len(a1)):5.2f})  "
                  f"rest {a2.mean()*1e4:6.2f} ({a2.mean()/a2.std()*np.sqrt(len(a2)):5.2f})")


if __name__ == "__main__":
    main()
