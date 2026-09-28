"""Turn-of-month profile of BTC daily returns (Binance daily bars, 00:00 UTC).

For each daily bar, `tdm` = position relative to the month boundary: +1 = first calendar
day of the month, +2 = second..., -1 = last calendar day of the month, -2 = the one before.
(Crypto trades every calendar day, so calendar days = trading days.)
Mean return and t by tdm, IS (<= 2022) vs OOS (2023+), plus a same-weekday control.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily  # noqa: E402
import research_lib as rl  # noqa: E402


def tdm_index(idx):
    idx = pd.DatetimeIndex(idx)
    dom = idx.day
    dim = idx.days_in_month
    fwd = dom                      # 1..31
    bwd = dom - dim - 1            # -1 = last day
    return np.where(fwd <= 16, fwd, bwd)


def main():
    d = btc_daily()
    r = d.Close.pct_change().dropna()
    df = pd.DataFrame({"r": r, "tdm": tdm_index(r.index), "dow": r.index.dayofweek})
    rows = []
    for half, (a, b) in {"IS": ("2017-09-01", "2022-12-31"), "OOS": ("2023-01-01", None)}.items():
        s = df.loc[a:b]
        mu = s.r.mean()
        g = s.groupby("tdm").r
        t = g.mean() / g.std() * np.sqrt(g.count())
        rows.append(pd.DataFrame({"half": half, "mean_bp": g.mean() * 1e4, "ex_bp": (g.mean() - mu) * 1e4,
                                  "t": t, "n": g.count()}))
    res = pd.concat(rows).reset_index()
    pv = res.pivot_table(index="tdm", columns="half", values=["mean_bp", "t", "n"])
    sel = pv.loc[[-7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]
    pd.set_option("display.width", 200)
    print(sel.round(2).to_string())
    # window aggregates
    print("\nwindow   IS_mean_bp/day  IS_t   OOS_mean_bp/day  OOS_t   rest IS/OOS")
    for lo, hi in [(-3, 3), (-2, 3), (-1, 3), (-3, 5), (-5, 5), (-1, 4), (-2, 2), (1, 5), (-4, -1), (1, 3)]:
        m = df.tdm.between(lo, hi) & (df.tdm != 0)
        out = []
        for a, b in (("2017-09-01", "2022-12-31"), ("2023-01-01", None)):
            x = df.loc[a:b]
            mm = m.loc[a:b]
            xi, xo = x.r[mm], x.r[~mm]
            out += [xi.mean() * 1e4, xi.mean() / xi.std() * np.sqrt(len(xi)), xo.mean() * 1e4]
        print(f"[{lo:+d},{hi:+d}]  {out[0]:8.1f} {out[1]:6.2f}   {out[3]:8.1f} {out[4]:6.2f}    {out[2]:.1f}/{out[5]:.1f}")
    # yfinance BTC-USD long history 2014+ for a pre-sample check (Bitstamp-era data)
    y = rl.load_btc()["Close"].pct_change().dropna().loc[:"2017-08-31"]
    t2 = tdm_index(y.index)
    for lo, hi in [(-3, 3), (-2, 3), (-1, 3)]:
        m = (t2 >= lo) & (t2 <= hi)
        xi, xo = y[m], y[~m]
        print(f"pre-2017-09 BTC-USD [{lo:+d},{hi:+d}] in {xi.mean()*1e4:.1f} bp/d (t {xi.mean()/xi.std()*np.sqrt(len(xi)):.2f}) vs rest {xo.mean()*1e4:.1f}")


if __name__ == "__main__":
    main()
