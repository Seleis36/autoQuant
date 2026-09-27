"""Screen 4 diagnostics: (a) beta-hedged single signals -- is the hedge the alpha?
(b) blend long/short leg attribution, (c) blend vs market correlation."""
import os, sys, pickle
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *
from screen2 import Z, beta, base, sec, rebal, ret, P, xs_backtest

mw = P["member"].astype(float); mw = mw.div(mw.sum(axis=1), axis=0)


def hedge(w):
    bw = (w * beta.reindex_like(w).fillna(1.0)).sum(axis=1)
    return w - mw.loc[w.index].mul(bw, axis=0)


rows = []
for k, z in Z.items():
    mask = base & z.notna()
    w = hold_monthly(book_weights(z, mask, kind="quintile"), rebal).loc["2011-01-01":]
    n0, s0 = xs_backtest(w, ret.loc["2011-01-01":], cost_bps=5.0)
    n1, s1 = xs_backtest(hedge(w), ret.loc["2011-01-01":], cost_bps=5.0)
    exb = (w * beta.reindex_like(w)).sum(axis=1).mean()
    r = {"signal": k, "book_beta": exb}
    r.update({f"raw_{a}": b for a, b in splits_row(n0).items()})
    r.update({f"bh_{a}": b for a, b in splits_row(n1).items()})
    rows.append(r)
d = pd.DataFrame(rows).set_index("signal").round(3)
pd.set_option("display.width", 200)
print(d.to_string())
d.to_csv(os.path.join(HERE, "screen4_betahedged_singles.csv"))

# pure hedge leg: long EW market x (-avg beta) -- what does shorting beta alone earn?
b = pd.read_parquet("/tmp/qvc_blend_net.parquet")["blend"]
spy = ret.where(P["member"]).mean(axis=1).loc[b.index]
print("\nblend corr to EW market:", round(b.corr(spy), 3),
      " down-market (EW<-1%) mean bp:", round(b[spy < -0.01].mean() * 1e4, 2),
      " up-market (EW>+1%) mean bp:", round(b[spy > 0.01].mean() * 1e4, 2))
