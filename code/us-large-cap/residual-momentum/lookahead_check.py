"""Lookahead / live-consistency check for strategy.residual_momentum_weights.

Truncate every input at a date d (mid-month and month-end) and recompute: the weights on d must
equal the full-sample weights on d. Any difference means the function reads the future (or,
for a mid-month d, that a partially observed month is being treated as finished)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from strategy import residual_momentum_weights, _panel_inputs

X = _panel_inputs()
full = residual_momentum_weights(X)
for d in ["2016-06-15", "2019-03-29", "2021-11-10", "2024-08-30", "2026-09-10"]:
    d = pd.Timestamp(d)
    d = X["close"].index[X["close"].index.get_indexer([d], method="ffill")[0]]
    Xt = {k: (v.loc[:d] if isinstance(v, (pd.DataFrame, pd.Series)) and k != "sector" else v) for k, v in X.items()}
    wt = residual_momentum_weights(Xt)
    a = full.loc[d].reindex(wt.columns).fillna(0); b = wt.loc[d]
    print(d.date(), "max |dw| =", float((a - b).abs().max()), " gross", round(float(b.abs().sum()), 3))
