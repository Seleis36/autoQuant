"""fx-sleeve-blend -- POST-HOC check (not one of the four declared books): walk-forward risk
weights proportional to each sleeve's expanding net Sharpe (clipped at 0) up to the prior
31 Dec; equal weights in 2010. Reported to show whether allocation, not selection, is what
the equal-risk blend is missing."""
import os, sys, importlib
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared")); sys.path.insert(0, HERE)
from fx_panel import ANN, backtest, load_px, split_table  # noqa: E402
b = importlib.import_module("01_blend")
px = load_px(); S = b.build(px)
nets = {k: backtest(v, px, cost=None)[0] for k, v in S.items()}
wt = pd.DataFrame(1.0, index=px.index, columns=list(S))
for y in sorted(set(px.index.year))[1:]:
    for k, n in nets.items():
        h = n[n != 0].loc[: f"{y-1}-12-31"]
        wt.loc[str(y), k] = max(h.mean() / h.std() * np.sqrt(ANN), 0.0) if len(h) >= 250 else 1.0
W = sum(S[k].mul(wt[k], axis=0) for k in S).div(wt.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
W = b.cap(b.vol_scale(W, px))
net, gross, turn, st = backtest(W, px, cost=None)
print(split_table(net).round(2).to_string()); print("turnover", round(st["Turnover_ann"], 1), "maxgross", round(W.abs().sum(axis=1).max(), 2))
print(wt.groupby(wt.index.year).first().round(2).to_string())
