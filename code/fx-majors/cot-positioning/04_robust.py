"""cot-positioning -- robustness of the chosen composite C (6 contrarian legs).

  * parameter neighbourhood: z-window {52,104,156,260} x change horizon {2,4,8} weeks
  * leave-one-leg-out (6 books) and leave-one-currency-out (7 books)
  * H.10 noon-rate replication 2007-2026 (independent price source, weekly, 1 bp)
  * exposure profile of the deployed book: gross distribution, max, time at cap
  * rebalance-day shift: Tuesday row instead of Monday row (the report is older by a day)
"""
import os
import sys
import importlib

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, HERE)
from fx_panel import CCYS, ANN, backtest, load_px, split_table  # noqa: E402
from fetch_cot_fx import on_fx_rows  # noqa: E402
from macro_data import h10_fx  # noqa: E402
from research_lib import perf_stats  # noqa: E402
s01 = importlib.import_module("01_screen")
c3 = importlib.import_module("03_composite")


def run(sig, px, AV, **kw):
    W = c3.book(on_fx_rows(sig, px.index, AV), px, **kw)
    net, gross, turn, st = backtest(W, px, cost=None)
    t = split_table(net)
    return net, W, {"FULL": t.loc["FULL", "Sharpe"], "IS": t.loc["IS", "Sharpe"], "OOS": t.loc["OOS", "Sharpe"],
                    "t": t.loc["FULL", "t_NW"], "turn": st["Turnover_ann"]}


def main():
    px = load_px()
    AV = s01.avail_all()
    rows = []
    for win in (52, 104, 156, 260):
        for dh in (2, 4, 8):
            L = c3.legs(win=win, dh=dh)
            _, _, r = run(c3.combine(list(L.values())), px, AV)
            rows.append({"test": f"win{win}_dh{dh}", **r})
    L = c3.legs()
    for k in L:
        _, _, r = run(c3.combine([v for kk, v in L.items() if kk != k]), px, AV)
        rows.append({"test": f"drop_{k}", **r})
    C = c3.combine(list(L.values()))
    for c in CCYS:
        sig = C.copy()
        sig[c] = np.nan
        _, _, r = run(sig, px, AV)
        rows.append({"test": f"drop_ccy_{c}", **r})
    net, W, r = run(C, px, AV)
    rows.append({"test": "BASE_C", **r})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.round(2).to_string())
    df.to_csv(os.path.join(HERE, "04_robust.csv"))

    g = W.abs().sum(axis=1)
    g = g[g > 0]
    print("\ngross exposure: mean %.2f  median %.2f  p95 %.2f  max %.2f  share at cap(3.0) %.3f"
          % (g.mean(), g.median(), g.quantile(.95), g.max(), (g >= 2.999).mean()))
    print("net USD exposure of the book (sum of ccy weights): max |.| %.2e" % W.sum(axis=1).abs().max())

    # Tuesday-row rebalance: shift the weekly decision one row later
    s = pd.Series(px.index, index=px.index)
    sec = s.groupby(px.index.to_period("W-SUN")).transform(lambda x: x.iloc[1] if len(x) > 1 else x.iloc[0]).eq(s).values
    Wt = W.reindex(px.index)[sec].reindex(px.index).ffill().fillna(0.0)
    n2, *_ , st2 = backtest(Wt, px, cost=None)
    print("Tuesday-row rebalance:", split_table(n2).round(2)["Sharpe"].to_dict())

    # H.10 replication 2007-2026 (noon NY rows, weekly, 1 bp)
    h = h10_fx().loc["2006-06-01":].ffill().dropna()
    hidx = h.index
    sr = on_fx_rows(C, hidx + pd.Timedelta(hours=17), AV)
    sr.index = hidx
    Wh = s01.weekly_hold(s01.xs(sr), hidx)
    rh = h.pct_change()
    nh = (Wh.shift(1) * rh[CCYS]).sum(axis=1) - (Wh.shift(1) - Wh.shift(2)).abs().sum(axis=1) * 1e-4
    nh = nh.loc["2007-07-01":]
    print("H.10 replication (unit book):", {p: round(perf_stats(nh.loc[a:b], ann=252)["Sharpe"], 2) for p, a, b in
          (("2007-09", "2007", "2009"), ("2010-19", "2010", "2019"), ("2020-26", "2020", "2026"), ("ALL", "2007", "2026"))})


if __name__ == "__main__":
    main()
