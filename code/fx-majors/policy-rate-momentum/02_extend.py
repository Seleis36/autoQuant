"""policy-rate-momentum -- extensions after the flat 01 screen.

1. Long history: the same books on Fed H.10 noon rates 1999-2026 (EUR starts 1999), to
   see whether the effect existed before 2010 and decayed, or never existed here.
2. Market-implied version: 12m / 6m / 3m change of the 10-year yield (OECD monthly
   average, usable one month after the observation month ends).
3. Re-framings: cycle-age (12m change minus 3m change: an established cycle without the
   fresh move the 01 screen says reverses), and the inverted 3m signal, reported as what
   it is -- a sign found after looking.
Costs: 1 bp per side (monthly books; cost drag is < 10 bp/yr either way).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import CCYS, ANN, lag_to_fx, load_px, split_table, carry_return  # noqa: E402
from macro_data import short_rates, h10_fx, long_yields_m, available_monthly  # noqa: E402
from research_lib import perf_stats  # noqa: E402
import importlib  # noqa: E402
scr = importlib.import_module("01_screen")

G8 = ["USD"] + CCYS


def monthly_book_returns(fx_usd_per, W_me):
    """Currency-space monthly backtest on a USD-per-ccy price frame.
    W_me: weights set at month-end dates (index = month-end dates of fx)."""
    m = fx_usd_per.resample("ME").last()
    r = m.pct_change()
    W = W_me.reindex(m.index).ffill()
    g = (W.shift(1) * r).sum(axis=1)
    turn = (W.shift(1) - W.shift(2)).abs().sum(axis=1)
    return (g - turn * 1e-4).iloc[1:]


def stats_m(x, label):
    x = x.dropna()
    x = x[x.index >= x.ne(0).idxmax()]
    s = perf_stats(x, ann=12, name=label)
    return s[["Sharpe", "CAGR", "Vol", "MaxDD", "t_NW", "N"]]


def main():
    fx = h10_fx().loc["1999-01-01":].ffill().dropna()
    rates = short_rates()
    ly = available_monthly(long_yields_m(), lag_months=1)       # month-end usable
    me = fx.resample("ME").last().index

    def pol_change(k):
        r = rates[G8]
        return (r - r.shift(int(round(k * 30.4375)))).reindex(me, method="ffill")

    def ly_change(k):
        y = ly[G8].reindex(ly.index.union(me)).ffill().reindex(me)
        return y - y.shift(k)

    sigs = {f"dpol{k}": pol_change(k) for k in (3, 6, 12, 24)}
    sigs.update({f"d10y{k}": ly_change(k) for k in (3, 6, 12)})
    sigs["cycle_age"] = pol_change(12) - pol_change(3)
    sigs["dpol3_inv"] = -pol_change(3)
    sigs["d10y3_inv"] = -ly_change(3)
    lvl = rates[G8].reindex(me, method="ffill")
    sigs["carry"] = lvl
    sigs["slope"] = ly[G8].reindex(ly.index.union(me)).ffill().reindex(me) - lvl

    out = []
    for name, s in sigs.items():
        for kind, f in (("lin", scr.xs_linear), ("bilat", scr.bilateral)):
            W = f(s.dropna(how="all"))
            net = monthly_book_returns(fx, W)
            for lab, a, b in (("1999-2009", "1999", "2009"), ("2010-2019", "2010", "2019"),
                              ("2020-2026", "2020", "2026"), ("ALL", "1999", "2026")):
                st = stats_m(net.loc[a:b], f"{name}_{kind}")
                st["period"] = lab
                out.append(st)
    df = pd.DataFrame(out)
    pv = df.pivot_table(index=df.index, columns="period", values="Sharpe")
    pv = pv[["1999-2009", "2010-2019", "2020-2026", "ALL"]]
    pd.set_option("display.width", 200)
    print("Monthly Sharpe (H.10 noon rates, 1 bp/side), spot only")
    print(pv.round(2).to_string())
    df.to_csv(os.path.join(HERE, "02_extend.csv"))


if __name__ == "__main__":
    main()
