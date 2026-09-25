"""Robustness of the pre-declared reference book raw|ENS (mean rank of -overnight over
k in {21,42,63,126,252}, linear, 21-day tranches, SPY beta hedge):
cost stress, stationary block bootstrap of Sharpe, DSR over all trials of this idea,
3-year rolling Sharpe, beta/corr to SPY, and a vectorbt re-computation of the P&L."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx
from strategy import target_weights

c = data.load_panel(); o = data.load_panel(field="Open")
W = target_weights(c, o)
rows = []
for cost in [0, 2, 5, 10]:
    st, net = sx.summary(W, c, name=f"cost{cost}", cost_bps=cost); rows.append(st)
print(sx.fmt(pd.DataFrame(rows)))
st, net = sx.summary(W, c)
net = net.loc["1999-12-01":]          # first year needs 252d of history
spy = c["SPY"].pct_change().loc[net.index]
print(f"corr to SPY {net.corr(spy):.2f}, beta {net.cov(spy)/spy.var():.3f}")
# bootstrap (stationary, mean block 21d)
rng = np.random.default_rng(0); x = net.values; n = len(x); B = 2000; out = []
for _ in range(B):
    idx = []; i = rng.integers(n)
    while len(idx) < n:
        idx.append(i); i = (i + 1) % n if rng.random() > 1 / 21 else rng.integers(n)
    y = x[idx]; out.append(y.mean() / y.std() * np.sqrt(252))
out = np.array(out)
print(f"bootstrap Sharpe 5/50/95%: {np.percentile(out,5):.2f} / {np.percentile(out,50):.2f} / {np.percentile(out,95):.2f};  P(Sh>0)={np.mean(out>0):.3f}  P(Sh>1)={np.mean(out>1):.3f}")
sr = net.mean() / net.std() * np.sqrt(252)
for N in [66, 150]:
    print(f"DSR at N={N}: {sx.dsr(sr, len(net), N, skew=net.skew(), kurt=net.kurtosis() + 3):.3f}")
roll = net.rolling(756).apply(lambda z: z.mean() / z.std() * np.sqrt(252))
print("3y rolling Sharpe quantiles:", roll.dropna().quantile([0, .1, .25, .5, .75, .9, 1]).round(2).to_dict())
print("share of 3y windows < 0:", round((roll.dropna() < 0).mean(), 3))
# vectorbt cross-check (target percent, fills at close, same cost)
import vectorbt as vbt
cols = W.columns
px = c[cols].loc["1999-01-01":].ffill()
tw = W[cols].loc["1999-01-01":].fillna(0)
pf = vbt.Portfolio.from_orders(px.bfill(), size=tw, size_type="targetpercent",
                               fees=2e-4, group_by=True, cash_sharing=True, call_seq="auto",
                               freq="1D", init_cash=1e6)
vr = pf.returns()
vr = vr.loc[net.index]
print(f"vectorbt: Sharpe {vr.mean()/vr.std()*np.sqrt(252):.2f}  vs research_lib {sr:.2f}; daily corr {vr.corr(net):.3f}")
