"""Why is CORE4 OOS (0.58) below the correlation arithmetic (~0.8)? Compare:
  dyn    : monthly EWM-vol risk weights (blend.py)
  isfix  : risk weights frozen at the IS (2000-2014) sleeve vols, applied unchanged after
  sum-of-returns version of isfix (no netting) to isolate the cost/netting effect
and print per-sleeve OOS contributions."""
import sys, os
_H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, _H)
import blend as B  # noqa (prints its table)
import numpy as np, pandas as pd
import sxlib as sx

names = ["ON", "CAL", "DIP", "RATE"]
isvol = B.R.loc["2000-06":"2014", names].std() * np.sqrt(252)
k = (B.TARGET / np.sqrt(4)) / isvol
print("\n#### IS-frozen risk weights:", k.round(2).to_dict())
Wt = sum(B.SL[n] * k[n] for n in names)
print("mean gross", Wt.abs().sum(axis=1).loc["2000-06":].mean().round(2), "max gross", Wt.abs().sum(axis=1).max().round(2))
st, net = sx.summary_rf(Wt, B.c, name="isfix", start="2000-06-01")
print(sx.fmt(st.to_frame().T.rename(columns={"CAGRx": "CAGR"})))
rf = sx.rf_daily(B.c.index)
contrib = {}
for n in names:
    Rn = B.R[n] - rf * B.SL[n].shift(1).sum(axis=1)       # sleeve excess return
    contrib[n] = Rn * k[n]
C = pd.DataFrame(contrib).loc["2015":]
print("OOS per-sleeve scaled excess Sharpe:", (C.mean() / C.std() * np.sqrt(252)).round(2).to_dict())
print("OOS per-sleeve ann. return contribution %:", (C.mean() * 252 * 100).round(2).to_dict())
tot = C.sum(axis=1); print("OOS sum-of-sleeves Sharpe:", round(tot.mean() / tot.std() * np.sqrt(252), 2))
print("OOS corr:"); print(C.corr().round(2))
