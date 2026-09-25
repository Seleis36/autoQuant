"""strategy.target_weights must reproduce the research book (slowvol.py CORE4-slow).
Run slowvol.py first: it writes slowvol_returns.parquet, which is regenerable and not committed."""
import sys, os
_H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _H)
sys.path.insert(0, os.path.join(_H, "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx
from strategy import target_weights
c = data.load_panel(); o = data.load_panel(field="Open")
W, sl, K = target_weights(c, o, return_sleeves=True)
st, net = sx.summary_rf(W, c, name="strategy.py", start="2002-01-01")
print(sx.fmt(st.to_frame().T.rename(columns={"CAGRx": "CAGR"})))
ref = pd.read_parquet(os.path.join(_H, "slowvol_returns.parquet"))["CORE4-slow"]
j = pd.concat([net, ref], axis=1).dropna()
print("daily corr with research CORE4-slow:", round(j.corr().iloc[0, 1], 4), " max abs diff:", float((j.iloc[:, 0] - j.iloc[:, 1]).abs().max()))
print("yearly risk weights:"); print(K.groupby(K.index.year).mean().loc[2002:].round(2).T.to_string())
g = W.abs().sum(axis=1).loc["2002":]
print(f"gross mean {g.mean():.2f}, 99% {g.quantile(.99):.2f}, max {g.max():.2f};  net mean {W.sum(axis=1).loc['2002':].mean():.2f}")
