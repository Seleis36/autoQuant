"""Lookahead / live-edge checks on strategy.target_weights.

(a) Truncation: cut every input at date T and recompute; the weights on the last 40 rows up
    to T must equal the full-history run. Any dependence on data after T shows up here.
(b) Short history: the live runner will not feed 23 years of bars. Recompute from the last
    N sessions only and compare the latest weights with the full-history run.
(c) Shuffle test: the same book on a signal shifted INTO the future must do much better
    (it does: lag -1 in 07) and on a random permutation of tickers must earn nothing.
"""
import numpy as np
import pandas as pd
import cef_lib as cl
import strategy as S

close, nav, volume, group, adj = S.load_inputs()
w_full = S.target_weights(close, nav, volume, group)

print("(a) truncation")
worst = 0.0
for T in ("2008-10-15", "2012-06-13", "2016-02-29", "2018-12-31", "2020-03-18", "2021-12-31",
          "2022-09-30", "2024-05-08", "2025-11-14", "2026-07-22"):
    T = pd.Timestamp(T)
    c, n, v = close.loc[:T], nav.loc[:T], volume.loc[:T]
    w_t = S.target_weights(c, n, v, group)
    a, b = w_t.iloc[-40:], w_full.loc[w_t.index[-40:]]
    diff = (a - b).abs()
    worst = max(worst, diff.max().max())
    bad = diff.max()[diff.max() > 1e-12]
    print(T.date(), "max |dw| over last 40 rows: %.2e" % diff.max().max(), "tickers differing:", list(bad.index))
print("worst:", worst)

print("\n(b) short history (latest row vs full-history run)")
for N in (300, 400, 500, 750, 1000):
    w_n = S.target_weights(close.iloc[-N:], nav.iloc[-N:], volume.iloc[-N:], group)
    d = (w_n.iloc[-1] - w_full.iloc[-1]).abs()
    d20 = (w_n.iloc[-20:] - w_full.iloc[-20:]).abs()
    print(N, "max |dw| last row %.4f  sum |dw| %.3f   last-20-rows max %.4f" % (d.max(), d.sum(), d20.max().max()))

print("\n(c) permutation placebo: fund i trades on fund j's signal (10 bp)")
d = cl.load()
ret = d["ret"]
rng = np.random.default_rng(7)
res = []
for k in range(20):
    perm = rng.permutation(w_full.columns)
    wp = pd.DataFrame(w_full.values, index=w_full.index, columns=perm).reindex(columns=w_full.columns)
    net, gross, _ = cl.xs_backtest(wp, ret, 10.0, lag=0)
    res.append((cl.sharpe(gross, "2004", None), cl.sharpe(net, "2004", None)))
res = np.array(res)
print("gross Sharpe mean %.2f (sd %.2f, max %.2f)   net mean %.2f" % (res[:, 0].mean(), res[:, 0].std(), res[:, 0].max(), res[:, 1].mean()))
