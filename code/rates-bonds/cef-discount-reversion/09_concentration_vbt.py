"""Where does the P&L come from, and does an independent engine agree?

(a) best / worst days and what was held; Sharpe with the best days removed
(b) P&L by fund and by sponsor; the book without the PIMCO funds
(c) vectorbt cross-check of the deployable weights (targetpercent orders at the close)
"""
import numpy as np
import pandas as pd
import cef_lib as cl
import strategy as S

pd.set_option("display.width", 220)
d = cl.load()
ret, group, uni = d["ret"], d["group"], d["uni"]
close, nav, volume = d["close"], d["nav"], d["volume"]
w = S.target_weights(close, nav, volume, group)
net, gross, st = cl.xs_backtest(w, ret, 10.0, lag=0)
w_eff = w.shift(1).fillna(0.0)
pnl = (w_eff * ret.fillna(0.0))

print("(a) extreme days (net, 10 bp)")
for day in list(net.nlargest(5).index) + list(net.nsmallest(5).index):
    top = pnl.loc[day].abs().nlargest(3)
    print(day.date(), "%+.2f%%" % (net.loc[day] * 100), {k: "%+.2f%% (w %+.3f, r %+.1f%%)" % (pnl.loc[day, k] * 100, w_eff.loc[day, k], ret.loc[day, k] * 100) for k in top.index})
for k in (5, 10, 20, 50):
    for name, (a, b) in (("IS", cl.IS), ("OOS", cl.OOS)):
        x = net.loc[a:b]
        trimmed = x.drop(x.nlargest(k).index)
        print("drop best %d days %s: Sharpe %.2f (was %.2f), ann %.1f%%" % (k, name, cl.sharpe(trimmed), cl.sharpe(x), trimmed.mean() * 252 * 100))

print("\n(b) P&L by fund / sponsor (gross, sum of daily, %)")
by_fund = pnl.loc["2004":].sum().sort_values(ascending=False) * 100
tot = by_fund.sum()
print("total %.0f%%; top 10 funds %.0f%% of it; funds with positive P&L %d / %d traded" % (
    tot, by_fund.head(10).sum() / tot * 100, (by_fund > 0).sum(), (by_fund != 0).sum()))
print(by_fund.head(10).round(1).to_dict())
print(by_fund.tail(5).round(1).to_dict())
spons = uni["sponsor"].reindex(by_fund.index)
print((by_fund.groupby(spons).sum().sort_values(ascending=False) / tot * 100).round(1).head(8).to_dict())
for label, drop in (("ex PIMCO", spons.index[spons.str.contains("PIMCO|Pacific Investment", case=False, na=False)]),
                    ("ex top-10 P&L funds", by_fund.head(10).index)):
    keep = [c for c in close.columns if c not in set(drop)]
    wk = S.target_weights(close[keep], nav[keep], volume[keep], group[keep])
    n, _, _ = cl.xs_backtest(wk, ret[keep], 10.0, lag=0)
    n20, _, _ = cl.xs_backtest(wk, ret[keep], 20.0, lag=0)
    print(label, "(%d funds dropped)" % len(drop), "10bp IS/OOS %.2f / %.2f   20bp %.2f / %.2f" % (
        cl.sharpe(n, *cl.IS), cl.sharpe(n, *cl.OOS), cl.sharpe(n20, *cl.IS), cl.sharpe(n20, *cl.OOS)))

print("\n(c) vectorbt cross-check, 10 bp fees, weights as deployed")
import vectorbt as vbt
start = "2004-01-01"
px = d["adj"].loc[start:].copy()
cols = [c for c in px.columns if w[c].abs().sum() > 0]
px = px[cols]
ww = w.loc[start:, cols].copy()
# vectorbt needs a price on every bar an order is placed; carry the last price over gaps
px_f = px.ffill()
size = ww.where(px_f.notna(), 0.0)
size = size.where((size != size.shift(1)) | (size != 0), np.nan)   # skip no-op zero orders
pf = vbt.Portfolio.from_orders(px_f, size=size, size_type="targetpercent", fees=0.001, freq="1D",
                               cash_sharing=True, group_by=True, call_seq="auto", init_cash=1e6)
r_vbt = pf.returns()
r_lib = net.loc[start:]
print("vectorbt  Sharpe IS %.2f  OOS %.2f  full %.2f   total return %.0f%%" % (
    cl.sharpe(r_vbt, *cl.IS), cl.sharpe(r_vbt, *cl.OOS), cl.sharpe(r_vbt), pf.total_return() * 100))
print("research  Sharpe IS %.2f  OOS %.2f  full %.2f   total return %.0f%%" % (
    cl.sharpe(r_lib, *cl.IS), cl.sharpe(r_lib, *cl.OOS), cl.sharpe(r_lib), ((1 + r_lib).prod() - 1) * 100))
# research_lib convention: w[t] earns ret[t+1]; vectorbt fills the order at close t -> same
both = pd.concat([r_vbt.rename("vbt"), r_lib.rename("lib")], axis=1).dropna()
print("daily return correlation %.4f" % both.corr().iloc[0, 1])
