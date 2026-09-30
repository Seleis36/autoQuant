"""exp04 — honesty checks on the best exp03 cell (A+B: spot age < 30 d, 1.5x squeeze stop):
yearly profile, ex-2025, funding a short-perp would pay, 20/30 bp, DSR at N = 28 cells
(exp02 16 + exp03 12), correlation with retail-crowding-xs."""
import numpy as np
import pandas as pd
import exp03_reframe as X   # re-runs exp03 (prints its table) and exposes book/ev/close
import research_lib as rl
from common import daily_funding_sym

rows = {}
for H in (30, 60):
    w = X.book(X.ev[X.ev.age < 30], H, stop=1.5)
    for c in (10, 30):
        net, _ = rl.backtest_xs(w, X.close, cost_bps=c)
        net = net.loc["2020":]
        fund = pd.Series(0.0, index=net.index)
        sym_of = dict(zip(X.ev.b, X.ev.sym))
        for b in w.columns:
            if b == "BTC" or not (w[b] != 0).any():
                continue
            f = daily_funding_sym(sym_of[b], lag_hours=0)
            if f is not None:
                fund += (-w[b].shift(1).fillna(0.0)).reindex(net.index).fillna(0) * f.reindex(net.index).fillna(0.0)
        for lab, n in {f"H{H} {c}bp spot": net, f"H{H} {c}bp +perp funding": net + fund}.items():
            ps = rl.perf_stats(n)
            ex25 = n[n.index.year != 2025]
            yr = n.groupby(n.index.year).apply(lambda r: r.mean() / r.std() * np.sqrt(365))
            rows[lab] = dict(SR=ps["Sharpe"], SR_ex2025=rl.perf_stats(ex25)["Sharpe"],
                             CAGR_ex2025=rl.perf_stats(ex25)["CAGR"], MaxDD=ps["MaxDD"],
                             yrs_pos=int((yr > 0).sum()), yrs=len(yr), median_yr_SR=yr.median(),
                             DSR_N28=rl.deflated_sharpe(ps["Sharpe"], len(n), 28, ps["Skew"], ps["Kurt"] + 3),
                             fund_ann=fund.mean() * 365)
print(pd.DataFrame(rows).T.round(3).to_string())
p = "../retail-crowding-xs/exp04_net.parquet"
rc = pd.read_parquet(p).iloc[:, 0]
w = X.book(X.ev[X.ev.age < 30], 60, stop=1.5)
net, _ = rl.backtest_xs(w, X.close, cost_bps=10)
j = pd.concat([net, rc], axis=1, join="inner").loc["2022-03-01":]
print("corr with retail-crowding-xs:", round(j.corr().iloc[0, 1], 3))
