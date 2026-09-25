"""Re-framing: the one economically-paired relation with the same sign in both halves of the
screen -- oil's past-5-day move predicts a NEGATIVE next-week XLE beta-residual (XLE
over-reacts to crude, then gives it back). Fixed spec from the screen: signal = -z(oil 5d,
lagged 1 day), XLE vs beta-hedge SPY, position = clip(signal, -1, 1) * 0.5, 5-day tranches.
Also the XLE own-residual reversal alone, to see whether oil adds anything."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel(); S = data.SECTORS
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
oil = np.log(data.load_ohlcv("CL=F")["Close"].reindex(c.index).ffill(limit=3)).diff()
oil = oil.where(oil.abs() < 0.25).shift(1)
def z(x, k):
    return (x.rolling(k).sum() / (x.rolling(252, min_periods=126).std() * np.sqrt(k))).clip(-3, 3)
rows = []
for nm, sig in [("oil5", -z(oil, 5)), ("xle_own5", -z(resid["XLE"], 5)), ("oil5+own5", -(z(oil, 5) + z(resid["XLE"], 5)) / 2)]:
    pos = (sig.clip(-1, 1) * 0.5).fillna(0)
    pos = sx.tranche(pos, 5)
    W = pd.DataFrame(0.0, index=c.index, columns=S + ["SPY"])
    W["XLE"] = pos; W["SPY"] = -pos * beta["XLE"].fillna(1)
    st, net = sx.summary(W, c, name=nm, start="2001-01-01"); rows.append(st)
print(sx.fmt(pd.DataFrame(rows)))
