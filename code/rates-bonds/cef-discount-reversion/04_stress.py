"""Stress the IS-selected book (hysteresis, 120d z-score, enter extreme third, leave at the
group median, within muni / taxable, one-session skip, 10 bp per side).

Every block prints IS (2004-14) / OOS (2015-26) / full net Sharpe.
"""
import numpy as np
import pandas as pd
import cef_lib as cl

pd.set_option("display.width", 200)
d = cl.load()
disc, ret, group = d["disc"], d["ret"], d["group"]
mask = cl.liquid_mask(d, 1e6)
z = cl.zscore(disc, 120)
w = cl.hysteresis_weights(z, mask, group, 0.33, 0.5)


def row(net):
    return {k: round(cl.sharpe(net, a, b), 2) for k, (a, b) in cl.SPLITS.items()}


print("== positions")
npos = (w != 0).sum(axis=1)
print("names held: mean %.1f  min(after 2005) %d  long %.1f short %.1f" % (
    npos.loc["2005":].mean(), npos.loc["2005":].min(), (w > 0).sum(axis=1).loc["2005":].mean(),
    (w < 0).sum(axis=1).loc["2005":].mean()))
hold = (w != 0).astype(int)
spells = (hold.diff().abs().sum().sum() / 2)
print("avg holding period (sessions): %.1f" % (hold.sum().sum() / max(spells, 1)))

print("\n== lag (sessions between the signal's close and the entry close)")
for lag in (0, 1, 2, 3, 5, 10):
    net, gross, st = cl.xs_backtest(w, ret, 10.0, lag=lag)
    print(lag, row(net), "gross", row(gross))

print("\n== cost ladder (bp per side), lag 1")
for c in (0, 5, 10, 15, 20, 30):
    net, gross, st = cl.xs_backtest(w, ret, c)
    print(c, row(net), "CAGR %.1f%%  vol %.1f%%  maxDD %.1f%%  turn %.0fx" % (
        st["CAGR"] * 100, st["Vol"] * 100, st["MaxDD"] * 100, st["Turnover_ann"]))

print("\n== borrow fee on the short side (bp / yr), 10 bp cost")
for b in (0, 100, 300, 500):
    net, _, _ = cl.xs_backtest(w, ret, 10.0, borrow_bps=b)
    print(b, row(net))

print("\n== legs, each against the equal-weight liquid group average (alpha attribution), 10 bp")
r = ret.fillna(0.0)
bench = pd.DataFrame(0.0, index=w.index, columns=w.columns)
for g in group.dropna().unique():
    cols = group.index[group == g]
    m = mask[cols].astype(float)
    bench[cols] = m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
for side, ws in (("long", w.clip(lower=0)), ("short", w.clip(upper=0))):
    # hedge the leg with the group benchmark, weighted by the leg's group exposure
    hedge = pd.DataFrame(0.0, index=w.index, columns=w.columns)
    for g in group.dropna().unique():
        cols = group.index[group == g]
        hedge[cols] = bench[cols].mul(ws[cols].sum(axis=1), axis=0)
    net_leg, _, _ = cl.xs_backtest(ws, ret, 10.0)
    net_h, _, _ = cl.xs_backtest(hedge, ret, 0.0)
    ex = net_leg - net_h
    print(side, "leg minus group avg:", row(ex), " ann excess %.1f%%" % (ex.loc[cl.IS[0]:].mean() * 252 * 100))
net_l, _, st_l = cl.xs_backtest(w.clip(lower=0) * 2, ret, 10.0)
print("long-only (gross 1) raw:", row(net_l), "CAGR %.1f%% maxDD %.1f%%" % (st_l["CAGR"] * 100, st_l["MaxDD"] * 100))
net_b, _, st_b = cl.xs_backtest(bench.div(bench.sum(axis=1).replace(0, np.nan), axis=0).fillna(0), ret, 0.0)
print("equal-weight liquid universe (buy & hold):", row(net_b), "CAGR %.1f%% maxDD %.1f%%" % (st_b["CAGR"] * 100, st_b["MaxDD"] * 100))

print("\n== by group, 10 bp")
for g in group.dropna().unique():
    cols = group.index[group == g]
    wg = cl.hysteresis_weights(z[cols], mask[cols], group[cols], 0.33, 0.5)
    net, _, _ = cl.xs_backtest(wg, ret[cols], 10.0)
    print(g, row(net))

print("\n== liquidity floor (median 60d $ volume), 10 bp")
for mdv in (5e5, 1e6, 2e6, 3e6):
    mk = cl.liquid_mask(d, mdv)
    net, _, st = cl.xs_backtest(cl.hysteresis_weights(z, mk, group, 0.33, 0.5), ret, 10.0)
    print("%.1fM" % (mdv / 1e6), row(net), "names %.0f" % mk.loc["2015":].sum(axis=1).mean())

print("\n== by year, 10 bp, lag 1")
net, gross, st = cl.xs_backtest(w, ret, 10.0)
yr = pd.DataFrame({"ret%": net.groupby(net.index.year).sum() * 100,
                   "sharpe": net.groupby(net.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan),
                   "gross%": gross.groupby(gross.index.year).sum() * 100})
print(yr.round(2).T.to_string())
net.to_frame("net").assign(gross=gross).to_csv("04_selected_daily.csv")
