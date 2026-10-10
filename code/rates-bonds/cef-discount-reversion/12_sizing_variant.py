"""A third of the book's turnover is not entries and exits but re-sizing: with sides forced
equal, every arrival or departure changes every other weight. Variant: a fixed `unit` per
name on both sides (no equalising; gross scaled down only above the cap), so existing
positions are left alone. The price is a floating net exposure.

Scored IN SAMPLE ONLY for the decision; OOS printed for the record with --oos. Not adopted
unless clearly better at the 20 bp stress cost.
"""
import sys
import numpy as np
import pandas as pd
import cef_lib as cl
import strategy as S

d = cl.load()
ret, group = d["ret"], d["group"]
close, nav, volume = d["close"], d["nav"], d["volume"]
p = S.DEFAULTS
disc = S.clean_discount(close, nav)
mask = S.liquid_mask(close, nav, volume, disc, p["min_dv"], p["min_price"], p["liq_win"], p["min_hist"])
rdev = S.relative_deviation(disc, mask, group, p["win"], p["minp"], p["group_min"])
st = S._states(rdev, p["x_in"], p["x_out"])


def fixed_unit(unit, cap=1.0):
    w = st * unit
    g = w.abs().sum(axis=1)
    return w.div((g / cap).clip(lower=1.0), axis=0).shift(1).fillna(0.0)


base = S.target_weights(close, nav, volume, group)
print("%-28s %s" % ("sizing", "IS 10bp / 20bp | turnover | avg gross | mean |net| | max |net|" + (" | OOS 10bp / 20bp" if "--oos" in sys.argv else "")))
for name, w in (("spec (sides equalised)", base), ("fixed 5 % per name", fixed_unit(0.05)), ("fixed 3 % per name", fixed_unit(0.03)),
                ("fixed 2.5 % per name", fixed_unit(0.025))):
    n10, _, s10 = cl.xs_backtest(w, ret, 10.0, lag=0)
    n20, _, _ = cl.xs_backtest(w, ret, 20.0, lag=0)
    net_exp = w.loc["2004":].sum(axis=1)
    line = "%-28s %.2f / %.2f | %.1fx | %.2f | %.3f | %.2f" % (name, cl.sharpe(n10, *cl.IS), cl.sharpe(n20, *cl.IS), s10["Turnover_ann"],
                                                           w.loc["2004":].abs().sum(axis=1).mean(), net_exp.abs().mean(), net_exp.abs().max())
    if "--oos" in sys.argv:
        line += " | %.2f / %.2f" % (cl.sharpe(n10, *cl.OOS), cl.sharpe(n20, *cl.OOS))
    print(line)
