"""Bootstrap, deflated Sharpe and circular-shift placebo on the exact strategy.py spec (1 h cutoff)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
from btc_data import btc_daily, evaluate  # noqa: E402
import research_lib as rl  # noqa: E402
from exp01_screen import MET  # noqa: E402
import strategy as S  # noqa: E402

START = "2021-03-01"
rng = np.random.default_rng(3)
close = btc_daily().Close
ls = pd.read_parquet(MET)["count_long_short_ratio"]
w = S.target_weight(close, ls)
net = evaluate(w, close, start=START)[0].loc[START:]
sh = lambda x: x.mean() / x.std() * np.sqrt(365)  # noqa: E731
v = net.values
nb = int(np.ceil(len(v) / 21))
bs = np.array([sh(v[np.concatenate([np.arange(s, s + 21) for s in rng.integers(0, len(v) - 21, nb)])[:len(v)]]) for _ in range(2000)])
print(f"spec P1 Sharpe {sh(net):.2f} | bootstrap median {np.median(bs):.2f} 5-95% [{np.percentile(bs, 5):.2f}, {np.percentile(bs, 95):.2f}] P(>1) {np.mean(bs > 1):.2f}")
for n in (16, 80):
    print(f"DSR with {n} trials: {rl.deflated_sharpe(sh(net), len(net), n, net.skew(), net.kurt() + 3):.3f}")
lsv = ls.values
pl = []
for _ in range(200):
    k = int(rng.integers(90 * 288, len(lsv) - 90 * 288))
    lss = pd.Series(np.roll(lsv, k), index=ls.index)
    pl.append(sh(evaluate(S.target_weight(close, lss), close, start=START)[0].loc[START:]))
pl = np.array(pl)
print(f"placebo (ratio circularly shifted >= 90 d): mean {pl.mean():.2f} sd {pl.std():.2f} max {pl.max():.2f} p = {np.mean(pl >= sh(net)):.3f}")
