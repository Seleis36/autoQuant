"""Book grid. Selection is done on IS (2004-2014) only; OOS columns are written to the CSV
and printed only with --oos.

Book: within-group (muni / taxable) quintile or tercile long-short on the lagged discount
signal, equal weight, gross 1 (0.5 long / 0.5 short), one-session skip, 10 bp per side.
Turnover control: (a) rebalance every k sessions, (b) hysteresis bands (enter in the extreme
q, leave only after crossing the group median).
"""
import sys
import itertools
import numpy as np
import pandas as pd
import cef_lib as cl

d = cl.load()
disc, ret, group = d["disc"], d["ret"], d["group"]
COST = 10.0


def signals():
    return {
        "level": disc, "z20": cl.zscore(disc, 20), "z60": cl.zscore(disc, 60),
        "z120": cl.zscore(disc, 120), "z250": cl.zscore(disc, 250),
        "chg5": disc.diff(5), "chg21": disc.diff(21),
    }


def run(min_dv=1e6):
    mask = cl.liquid_mask(d, min_dv)
    rows = []
    for name, s in signals().items():
        for q, k, grp in itertools.product((0.2, 0.33), (1, 5, 10, 21), (True, False)):
            w = cl.hold_every(cl.ls_weights(s, mask, q=q, group=group if grp else None), k)
            net, gross, st = cl.xs_backtest(w, ret, COST)
            rows.append(dict(kind="rebal", sig=name, q=q, k=k, grp=grp, IS=cl.sharpe(net, *cl.IS),
                             IS_gross=cl.sharpe(gross, *cl.IS), OOS=cl.sharpe(net, *cl.OOS),
                             OOS_gross=cl.sharpe(gross, *cl.OOS), full=cl.sharpe(net, cl.IS[0], None),
                             turn=st["Turnover_ann"]))
        for q_in, q_out in ((0.2, 0.5), (0.2, 0.35), (0.1, 0.5), (0.33, 0.5)):
            w = cl.hysteresis_weights(s, mask, group, q_in, q_out)
            net, gross, st = cl.xs_backtest(w, ret, COST)
            rows.append(dict(kind="hyst", sig=name, q=q_in, k=q_out, grp=True, IS=cl.sharpe(net, *cl.IS),
                             IS_gross=cl.sharpe(gross, *cl.IS), OOS=cl.sharpe(net, *cl.OOS),
                             OOS_gross=cl.sharpe(gross, *cl.OOS), full=cl.sharpe(net, cl.IS[0], None),
                             turn=st["Turnover_ann"]))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    res = run()
    res.to_csv("03_grid.csv", index=False)
    show = ["kind", "sig", "q", "k", "grp", "IS", "IS_gross", "turn"]
    if "--oos" in sys.argv:
        show += ["OOS", "OOS_gross", "full"]
    pd.set_option("display.width", 200)
    print(len(res), "cells")
    print(res.sort_values("IS", ascending=False)[show].head(30).round(2).to_string(index=False))
    print("\nIS net Sharpe by signal (mean over cells):")
    print(res.groupby(["kind", "sig"])["IS"].agg(["mean", "max", "min"]).round(2).to_string())
