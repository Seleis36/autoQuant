"""Can the book be made robust to cost? The rank book of 03/04 breaks even near 20 bp/side
out of sample, and the Abdi-Ranaldo half-spread of these funds averages 11-15 bp.

(1) Re-cost the 03/04 book with each fund's own estimated half-spread.
(2) Threshold family: act only on dislocations that are large in PRICE terms, so calm
    markets generate few trades.
        dev   = disc - rolling mean(disc, win)             (log points)
        rdev  = dev - median of dev within muni / taxable   (group-relative)
        long  when rdev <= -x_in, until rdev >= -x_out ; short symmetric
        size  = `unit` per name, gross capped at 1, sides forced equal (dollar-neutral)
    Selection: IS (2004-14) net Sharpe at a 20 bp stress cost. OOS printed only with --oos.
"""
import sys
import itertools
import numpy as np
import pandas as pd
import cef_lib as cl

pd.set_option("display.width", 220)
d = cl.load()
disc, ret, group = d["disc"], d["ret"], d["group"]
mask = cl.liquid_mask(d, 1e6)
half = pd.read_parquet("05_half_spread_monthly.parquet")
# previous month's estimate, carried daily
hs = half.shift(1).reindex(disc.index, method="ffill").reindex(columns=disc.columns)
hs = hs.fillna(hs.median(axis=1).to_frame().values.repeat(hs.shape[1], axis=1).mean() if False else 15e-4)


def bt_spread(w, lag=1, mult=1.0):
    """Per-name cost = mult x that fund's estimated half-spread (prior month)."""
    w_eff = w.shift(1 + lag).fillna(0.0)
    r = ret.reindex(w.index).fillna(0.0)
    gross = (w_eff * r).sum(axis=1)
    dw = (w_eff - w_eff.shift(1).fillna(0.0)).abs()
    cost = (dw * hs.shift(1)).sum(axis=1) * mult
    return gross - cost, (dw * hs.shift(1)).sum().sum() / dw.sum().sum() * 1e4


def group_median(x):
    out = pd.DataFrame(np.nan, index=x.index, columns=x.columns)
    for g in group.dropna().unique():
        cols = group.index[group == g]
        n = x[cols].notna().sum(axis=1)
        out[cols] = np.repeat(x[cols].median(axis=1).where(n >= 10).values[:, None], len(cols), axis=1)
    return out


def threshold_weights(sig, x_in, x_out, unit=0.05, gross_cap=1.0, neutral=True):
    a = sig.values
    state = np.zeros(a.shape[1])
    out = np.zeros_like(a)
    for i in range(a.shape[0]):
        x = a[i]
        ok = ~np.isnan(x)
        state[~ok] = 0.0
        state[ok & (state > 0) & (x >= -x_out)] = 0.0
        state[ok & (state < 0) & (x <= x_out)] = 0.0
        state[ok & (x <= -x_in)] = 1.0
        state[ok & (x >= x_in)] = -1.0
        out[i] = state
    st = pd.DataFrame(out, index=sig.index, columns=sig.columns)
    nl, ns = (st > 0).sum(axis=1), (st < 0).sum(axis=1)
    if neutral:
        side = np.minimum(nl, ns) * unit                 # notional per side
        side = np.minimum(side, gross_cap / 2)
        w = (st > 0).astype(float).div(nl.replace(0, np.nan), axis=0).mul(side, axis=0).fillna(0.0) \
            - (st < 0).astype(float).div(ns.replace(0, np.nan), axis=0).mul(side, axis=0).fillna(0.0)
    else:
        w = st * unit
        g = w.abs().sum(axis=1)
        w = w.div((g / gross_cap).clip(lower=1.0), axis=0)
    return w


def sig_dev(win, kind):
    m = disc.rolling(win, min_periods=win // 2).mean()
    dev = disc - m
    if kind == "z":
        dev = dev / disc.rolling(win, min_periods=win // 2).std().where(lambda s: s > 1e-4)
    dev = dev.where(mask)
    return dev - group_median(dev)


if __name__ == "__main__":
    print("== (1) the 03/04 rank book re-costed")
    w0 = cl.hysteresis_weights(cl.zscore(disc, 120), mask, group, 0.33, 0.5)
    for label, c in (("flat 10", 10.0), ("flat 15", 15.0), ("flat 20", 20.0)):
        net, _, _ = cl.xs_backtest(w0, ret, c)
        print(label, {k: round(cl.sharpe(net, a, b), 2) for k, (a, b) in cl.SPLITS.items()})
    for mult in (0.5, 1.0):
        net, avg = bt_spread(w0, mult=mult)
        print("own AR half-spread x%.1f (trade-weighted %.1f bp)" % (mult, avg * mult),
              {k: round(cl.sharpe(net, a, b), 2) for k, (a, b) in cl.SPLITS.items()})

    print("\n== (2) threshold family")
    rows = []
    grid = [("dev", w, xi, xo) for w in (60, 120, 250) for xi in (0.015, 0.025, 0.035, 0.05) for xo in (0.0, 0.5)] + \
           [("z", w, xi, xo) for w in (60, 120, 250) for xi in (1.0, 1.5, 2.0, 2.5) for xo in (0.0, 0.5)]
    for kind, win, x_in, xo in grid:
        s = sig_dev(win, kind)
        w = threshold_weights(s, x_in, x_in * xo)
        r = {}
        for c in (10.0, 20.0):
            net, gross, st = cl.xs_backtest(w, ret, c)
            r[f"IS{int(c)}"] = cl.sharpe(net, *cl.IS)
            r[f"OOS{int(c)}"] = cl.sharpe(net, *cl.OOS)
            r[f"ISret{int(c)}"] = net.loc[cl.IS[0]:cl.IS[1]].mean() * 252 * 100
            r[f"OOSret{int(c)}"] = net.loc[cl.OOS[0]:].mean() * 252 * 100
        netA, avg = bt_spread(w)
        rows.append(dict(kind=kind, win=win, x_in=x_in, x_out=xo, **r, IS_AR=cl.sharpe(netA, *cl.IS),
                         OOS_AR=cl.sharpe(netA, *cl.OOS), turn=st["Turnover_ann"], gross_exp=st["GrossExp"],
                         IS_gross=cl.sharpe(gross, *cl.IS), OOS_gross=cl.sharpe(gross, *cl.OOS)))
    res = pd.DataFrame(rows)
    res.to_csv("06_threshold_grid.csv", index=False)
    cols = ["kind", "win", "x_in", "x_out", "IS20", "IS10", "IS_AR", "ISret10", "IS_gross", "turn", "gross_exp"]
    if "--oos" in sys.argv:
        cols += ["OOS20", "OOS10", "OOS_AR", "OOSret10", "OOS_gross"]
    print(len(res), "cells; sorted by IS net Sharpe at 20 bp")
    print(res.sort_values("IS20", ascending=False)[cols].round(2).to_string(index=False))
