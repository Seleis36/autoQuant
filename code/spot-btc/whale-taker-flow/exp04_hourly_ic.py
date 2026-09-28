"""Hourly-horizon ICs of the whale-minus-retail imbalance.

Flow row stamped hour t covers [t, t+1h); the signal at the END of hour t (t+1h) uses flow
through that hour. Forward return from close(t) (= price at t+1h) over the next k hours.
Features: LmS over trailing W hours, W in 6/24/72/168; partial IC controls for the
same-window return. Samples every k hours (non-overlapping). IS <= 2022, OOS 2023+,
and IC by year for the headline cell.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_hourly  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import FLOW, GROUPS, ranks  # noqa: E402


def hourly_groups():
    h = pd.read_parquet(FLOW)
    out = pd.DataFrame(index=h.index)
    for g, bs in GROUPS.items():
        out[f"buy_{g}"] = sum(h[f"buy_b{b}"] for b in bs if f"buy_b{b}" in h)
        out[f"sell_{g}"] = sum(h[f"sell_b{b}"] for b in bs if f"sell_b{b}" in h)
    return out


def lms(fl, W):
    s = fl.rolling(W, min_periods=int(W * 0.8)).sum()
    iL = (s.buy_L - s.sell_L) / (s.buy_L + s.sell_L)
    iS = (s.buy_S - s.sell_S) / (s.buy_S + s.sell_S)
    return iL - iS, iL, iS


def pic(x, y, c):
    m = x.notna() & y.notna() & c.notna()
    xr, yr, cr = ranks(x[m]), ranks(y[m]), ranks(c[m])
    xr = xr - (xr * cr).mean() / (cr * cr).mean() * cr
    p = (xr / xr.std() * yr).values
    return p.mean(), rl.newey_west_t(p, lags=1)


def main():
    h = btc_hourly().loc[:"2026-08-31 23:00"]
    close = h.Close
    fl = hourly_groups().reindex(close.index)
    rows = []
    for W in (6, 24, 72, 168):
        x, xL, xS = lms(fl, W)
        past = close.pct_change(W)
        for k in (1, 4, 12, 24, 72):
            fwd = close.shift(-k) / close - 1
            samp = close.index[::k]
            r = {"W": W, "k": k}
            for half, (a, b) in {"IS": ("2017-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
                ic, t = pic(x.loc[samp].loc[a:b], fwd.loc[samp].loc[a:b], past.loc[samp].loc[a:b])
                r[f"pIC_{half}"], r[f"t_{half}"] = ic, t
                ic2, t2 = pic(x.loc[samp].loc["2018-01-01":b] if half == "IS" else x.loc[samp].loc[a:b],
                              fwd.loc[samp].loc["2018-01-01":b] if half == "IS" else fwd.loc[samp].loc[a:b],
                              past.loc[samp].loc["2018-01-01":b] if half == "IS" else past.loc[samp].loc[a:b])
                if half == "IS":
                    r["pIC_IS18"], r["t_IS18"] = ic2, t2
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "exp04_hourly_ic.csv"), index=False)
    pd.set_option("display.width", 200)
    print(res.round(3).to_string(index=False))
    x, _, _ = lms(fl, 24)
    for k in (4, 24):
        fwd = close.shift(-k) / close - 1
        past = close.pct_change(24)
        samp = close.index[::k]
        yr = {}
        for y in range(2018, 2027):
            sl = slice(f"{y}-01-01", f"{y}-12-31")
            yr[y] = round(pic(x.loc[samp].loc[sl], fwd.loc[samp].loc[sl], past.loc[samp].loc[sl])[0], 3)
        print(f"W=24 k={k} partial IC by year:", yr)


if __name__ == "__main__":
    main()
