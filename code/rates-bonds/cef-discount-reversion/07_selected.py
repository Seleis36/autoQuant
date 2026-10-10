"""Robustness battery on the deployable book (strategy.target_weights, spec defaults).

strategy weights already carry the one-session signal lag, so `lag=0` below means "as
deployed" and extra lag is added on top.
"""
import numpy as np
import pandas as pd
import cef_lib as cl
import strategy as S

pd.set_option("display.width", 220)
import research_lib as rl

d = cl.load()
ret, group = d["ret"], d["group"]
close, nav, volume = d["close"], d["nav"], d["volume"]
w = S.target_weights(close, nav, volume, group)


def row(net):
    return {k: round(cl.sharpe(net, a, b), 2) for k, (a, b) in cl.SPLITS.items()}


def full(net, a=None, b=None):
    x = net.loc[a:b]
    st = rl.perf_stats(x, ann=252)
    return "Sharpe %.2f  CAGR %.1f%%  vol %.1f%%  maxDD %.1f%%  t_NW %.1f" % (
        st["Sharpe"], st["CAGR"] * 100, st["Vol"] * 100, st["MaxDD"] * 100, st["t_NW"])


net10, gross, st10 = cl.xs_backtest(w, ret, 10.0, lag=0)
print("== headline, 10 bp per side")
for k, (a, b) in cl.SPLITS.items():
    print(k, full(net10, a, b))
print("turnover %.1fx / yr   avg gross %.2f   max gross %.2f   avg names %.0f (long %.0f / short %.0f)" % (
    st10["Turnover_ann"], w.loc["2004":].abs().sum(axis=1).mean(), w.abs().sum(axis=1).max(),
    (w != 0).sum(axis=1).loc["2004":].mean(), (w > 0).sum(axis=1).loc["2004":].mean(), (w < 0).sum(axis=1).loc["2004":].mean()))
hold = (w != 0).astype(int)
print("avg holding period %.1f sessions; share of sessions with a position %.2f; max single-name weight %.3f" % (
    hold.sum().sum() / (hold.diff().abs().sum().sum() / 2), (w.abs().sum(axis=1) > 0).loc["2004":].mean(), w.abs().max().max()))
print("net exposure: mean %.4f  max |net| %.4f" % (w.sum(axis=1).mean(), w.sum(axis=1).abs().max()))
print("skew %.2f  kurt %.1f  worst day %.2f%%  best day %.2f%%" % (net10.skew(), net10.kurtosis(), net10.min() * 100, net10.max() * 100))

print("\n== extra entry lag on top of the deployed one-session skip, 10 bp")
for lag in (-1, 0, 1, 2, 4):
    n, g, _ = cl.xs_backtest(w, ret, 10.0, lag=lag)
    tag = "(NOT tradable: uses the NAV of the entry close)" if lag < 0 else ""
    print(lag, row(n), "gross", row(g), tag)

print("\n== cost ladder, bp per side")
for c in (0, 5, 10, 15, 20, 25, 30):
    n, _, s = cl.xs_backtest(w, ret, c, lag=0)
    print(c, row(n), "CAGR full %.1f%%  OOS %.1f%%" % (s["CAGR"] * 100, n.loc[cl.OOS[0]:].mean() * 252 * 100))

print("\n== borrow fee on shorts (bp / yr), 10 bp cost")
for b in (0, 100, 300, 500):
    n, _, _ = cl.xs_backtest(w, ret, 10.0, lag=0, borrow_bps=b)
    print(b, row(n))

print("\n== legs, 10 bp")
nl, _, sl = cl.xs_backtest(w.clip(lower=0), ret, 10.0, lag=0)
ns, _, ss = cl.xs_backtest(w.clip(upper=0), ret, 10.0, lag=0)
print("long leg alone :", row(nl), "ann %.1f%%" % (nl.loc["2004":].mean() * 252 * 100))
print("short leg alone:", row(ns), "ann %.1f%%" % (ns.loc["2004":].mean() * 252 * 100))
mask = cl.liquid_mask(d)
ew = mask.astype(float).div(mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
nb, _, _ = cl.xs_backtest(ew, ret, 0.0, lag=1)
gl = w.clip(lower=0).sum(axis=1).shift(1).fillna(0)
print("long leg minus equal-weight liquid universe (same notional):", row(nl - gl * nb), "ann %.1f%%" % ((nl - gl * nb).loc["2004":].mean() * 252 * 100))
print("short leg plus equal-weight liquid universe (same notional):", row(ns + gl * nb), "ann %.1f%%" % ((ns + gl * nb).loc["2004":].mean() * 252 * 100))

print("\n== universe floors (median 60d $ volume), 10 bp")
for mdv in (5e5, 1e6, 2e6, 3e6):
    wv = S.target_weights(close, nav, volume, group, min_dv=mdv)
    n, _, s = cl.xs_backtest(wv, ret, 10.0, lag=0)
    n20, _, _ = cl.xs_backtest(wv, ret, 20.0, lag=0)
    print("$%.1fM" % (mdv / 1e6), row(n), "@20bp", row(n20), "avg gross %.2f" % wv.loc["2004":].abs().sum(axis=1).mean())

print("\n== one group at a time, 10 bp")
for g in ("muni", "taxable"):
    cols = group.index[group == g]
    wg = S.target_weights(close[cols], nav[cols], volume[cols], group[cols])
    n, _, _ = cl.xs_backtest(wg, ret[cols], 10.0, lag=0)
    print(g, row(n), "avg gross %.2f" % wg.loc["2004":].abs().sum(axis=1).mean())

print("\n== neighbours of the selected parameters, 10 bp / 20 bp (IS, OOS)")
for kw in (dict(), dict(win=40), dict(win=90), dict(x_in=0.015), dict(x_in=0.02), dict(x_in=0.035), dict(x_out=0.005), dict(x_out=0.0125),
           dict(unit=0.03), dict(unit=0.10), dict(min_hist=500), dict(group_min=5)):
    wv = S.target_weights(close, nav, volume, group, **kw)
    a, _, _ = cl.xs_backtest(wv, ret, 10.0, lag=0)
    b, _, _ = cl.xs_backtest(wv, ret, 20.0, lag=0)
    print(kw or "spec", "10bp", (round(cl.sharpe(a, *cl.IS), 2), round(cl.sharpe(a, *cl.OOS), 2)),
          "20bp", (round(cl.sharpe(b, *cl.IS), 2), round(cl.sharpe(b, *cl.OOS), 2)))

print("\n== by year, 10 bp")
n20, _, _ = cl.xs_backtest(w, ret, 20.0, lag=0)
yr = pd.DataFrame({"net10%": net10.groupby(net10.index.year).sum() * 100,
                   "net20%": n20.groupby(n20.index.year).sum() * 100,
                   "gross%": gross.groupby(gross.index.year).sum() * 100,
                   "sharpe10": net10.groupby(net10.index.year).apply(lambda x: x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan),
                   "avg_gross": w.abs().sum(axis=1).groupby(w.index.year).mean()})
print(yr.loc[2004:].round(2).T.to_string())

print("\n== sub-periods, 10 bp / 20 bp net Sharpe")
for a, b in (("2004", "2007"), ("2008", "2009"), ("2010", "2014"), ("2015", "2019"), ("2020", "2022"), ("2023", "2026")):
    print(a, b, round(cl.sharpe(net10, a, b), 2), round(cl.sharpe(n20, a, b), 2))

print("\n== market betas of the daily net return (full sample, 2007+)")
bench = {t: rl.load_series(t)["Close"].pct_change() for t in ("SPY", "HYG", "MUB", "TLT")}
for t, b in bench.items():
    x = pd.concat([net10, b], axis=1).dropna().loc["2010":]
    print(t, "beta %.3f  corr %.2f" % (x.cov().iloc[0, 1] / x.iloc[:, 1].var(), x.corr().iloc[0, 1]))

pd.DataFrame({"net10": net10, "net20": n20, "gross": gross}).to_csv("07_selected_daily.csv")
w.to_parquet("07_weights.parquet")

n_trials = 140 + 48
dsr = rl.deflated_sharpe(cl.sharpe(net10, *cl.OOS), len(net10.loc[cl.OOS[0]:]), n_trials,
                         skew=net10.loc[cl.OOS[0]:].skew(), kurt=net10.loc[cl.OOS[0]:].kurtosis() + 3, ann=252)
print("\nDeflated Sharpe prob (OOS, %d trials): %.3f" % (n_trials, dsr))
