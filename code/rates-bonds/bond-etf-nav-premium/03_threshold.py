"""Last re-framing: trade only large dislocations of the TRADABLE model premium, so that
the gross per trade can exceed four sides of cost.

    mp[t]  = official premium of t-1 + today's residual return (vs IEF / HYG)
    dev    = mp - mean(mp, 60)
    long when dev <= -x (bp), flat again when dev >= -x_out ; short symmetric
    each position `unit` of capital, hedged with IEF / HYG at trailing betas, gross capped at 1

Filled at the close the signal is computed on (the sim convention). That close is also the
last input of the signal, so bid-ask bounce flatters every number below: an upper bound.
Also shows how fast the dislocation decays (slope of the next k-day residual return on dev).
"""
import itertools
import numpy as np
import pandas as pd
import nav_lib as nl

pd.set_option("display.width", 200)
d = nl.load()
ret, prem, sector = d["ret"], d["prem"], d["sector"]
b1, b2 = nl.trailing_betas(ret, d["hedge"])
res = nl.residual_returns(ret, d["hedge"], b1, b2)
mask = (d["dv"].rolling(60, min_periods=30).median() >= 5e5) & prem.notna()
mp = prem.shift(1) + res
dev = (mp - mp.rolling(60, min_periods=30).mean()).where(mask)

print("decay: pooled slope of the next residual return on dev (no skip), by horizon")
cum = res.fillna(0).cumsum()
for a, b in (nl.IS, nl.OOS):
    out = []
    for k in (1, 2, 3, 5, 10):
        f = (cum.shift(-k) - cum).where(res.notna())
        x, y = dev.loc[a:b].stack().dropna(), f.loc[a:b].stack().dropna()
        j = x.index.intersection(y.index)
        out.append("%dd %.3f" % (k, (x.loc[j] * y.loc[j]).sum() / (x.loc[j] ** 2).sum()))
    print(a[:4], "-", b[:4], " ".join(out))
off = prem.where(mask) - prem.rolling(60, min_periods=30).mean()
f1 = (cum.shift(-2) - cum.shift(-1)).where(res.notna())
x, y = off.stack().dropna(), f1.stack().dropna(); j = x.index.intersection(y.index)
print("official premium dev, WITH the skip, next-day slope: %.3f" % ((x.loc[j] * y.loc[j]).sum() / (x.loc[j] ** 2).sum()))


def states(sig, x_in, x_out):
    a = sig.values
    st = np.zeros(a.shape[1]); out = np.zeros_like(a)
    for i in range(a.shape[0]):
        x = a[i]; ok = ~np.isnan(x)
        st[~ok] = 0
        st[ok & (st > 0) & (x >= -x_out)] = 0
        st[ok & (st < 0) & (x <= x_out)] = 0
        st[ok & (x <= -x_in)] = 1
        st[ok & (x >= x_in)] = -1
        out[i] = st
    return pd.DataFrame(out, index=sig.index, columns=sig.columns)


rows = []
for x_in, xo, unit in itertools.product((0.0025, 0.005, 0.0075, 0.01, 0.015), (0.0, 0.5), (0.1,)):
    st = states(dev, x_in, x_in * xo)
    w = st * unit
    g = w.abs().sum(axis=1)
    w = w.div((g / 1.0).clip(lower=1.0), axis=0)
    r = {}
    for c in (0.0, 2.0, 5.0):
        net, gross, turn = nl.book(w, d, b1, b2, cost_bps=c, lag=0)
        r[c] = net
    rows.append(dict(x_in_bp=x_in * 1e4, x_out=xo, IS_gross=nl.sharpe(r[0.0], *nl.IS), OOS_gross=nl.sharpe(r[0.0], *nl.OOS),
                     IS_2bp=nl.sharpe(r[2.0], *nl.IS), OOS_2bp=nl.sharpe(r[2.0], *nl.OOS),
                     IS_5bp=nl.sharpe(r[5.0], *nl.IS), OOS_5bp=nl.sharpe(r[5.0], *nl.OOS), turn=turn,
                     avg_gross=w.abs().sum(axis=1).loc["2012":].mean(),
                     OOS_ret2bp=r[2.0].loc[nl.OOS[0]:].mean() * 252 * 100))
out = pd.DataFrame(rows)
out.to_csv("03_threshold.csv", index=False)
print(out.round(2).to_string(index=False))
best = out.sort_values("IS_2bp", ascending=False).iloc[0]
print("\nIS-best at 2 bp: x_in %.0f bp, x_out %.1f -> IS %.2f / OOS %.2f at 2 bp; %.2f / %.2f at 5 bp" % (
    best.x_in_bp, best.x_out, best.IS_2bp, best.OOS_2bp, best.IS_5bp, best.OOS_5bp))
# the IS-best cell with one extra session of delay (what remains once the close is not the signal's own print)
st = states(dev, best.x_in_bp / 1e4, best.x_in_bp / 1e4 * best.x_out)
w = st * 0.1; w = w.div((w.abs().sum(axis=1)).clip(lower=1.0), axis=0)
for lag in (0, 1, 2):
    net, gross, turn = nl.book(w, d, b1, b2, cost_bps=2.0, lag=lag)
    print("entry delay %d: gross %.2f / %.2f   net 2bp %.2f / %.2f" % (lag, nl.sharpe(gross, *nl.IS), nl.sharpe(gross, *nl.OOS),
                                                                    nl.sharpe(net, *nl.IS), nl.sharpe(net, *nl.OOS)))
