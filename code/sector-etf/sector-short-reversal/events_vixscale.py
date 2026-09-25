"""Re-framings 2-3: (a) fade only extreme 1-day beta-residual moves (|z|>thr), hold h
days, SPY-hedged; (b) cross-sectional reversal with size proportional to VIX/20 (Nagel's
liquidity-provision return scales with VIX) instead of a hard gate. Plus per-year table of
the cross-sectional VIX>25 cell that looked best OOS in grid.py (to see if it is 2008/2020)."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
S = data.SECTORS
r = c.pct_change()
spy = r["SPY"]
beta = sx.beta_to(r[S], spy, halflife=126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
rvol = resid.ewm(halflife=63, min_periods=63).std().shift(1)
z = resid / rvol
mask = data.universe_mask(c[S])
vix = data.load_ohlcv("^VIX")["Close"].reindex(c.index).ffill()

rows = []
for thr, h in itertools.product([2.0, 2.5, 3.0], [1, 3, 5, 10]):
    ev = (-np.sign(z) * (z.abs() > thr)).where(mask, 0).fillna(0)
    w = sx.tranche(ev, h) / 9.0 * h ** 0  # 1/9 per live event-day, averaged over h tranches
    w = ev.rolling(h, min_periods=1).sum() / 9.0
    W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1)
    s, _ = sx.summary(W, c, name=f"event|z>{thr}|h{h}")
    rows.append(s)
for k, n, cap in itertools.product([1, 2, 3, 5], [1, 3, 5], [2.0]):
    cum = r[S].sub(spy, axis=0).rolling(k).sum() / (r[S].ewm(halflife=63, min_periods=63).std() * np.sqrt(k))
    s_ = (-cum).where(mask); s_ = s_.sub(s_.mean(axis=1), axis=0)
    w = s_.div(s_.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    w = w.mul((vix / 20).clip(upper=cap), axis=0)
    w = sx.tranche(w, n)
    W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1)
    s, _ = sx.summary(W, c, name=f"vixscale|k{k}|n{n}")
    rows.append(s)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
print(sx.fmt(df))

# per-year of grid best-OOS cell rel|k3|volz|n3|vix>25
k, n = 3, 3
cum = r[S].sub(spy, axis=0).rolling(k).sum() / (r[S].ewm(halflife=63, min_periods=63).std() * np.sqrt(k))
s_ = (-cum).where(mask); s_ = s_.sub(s_.mean(axis=1), axis=0)
w = s_.div(s_.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0).mul((vix > 25).astype(float), axis=0)
w = sx.tranche(w, n); W = w.copy(); W["SPY"] = -(w * beta.fillna(1)).sum(axis=1)
_, net = sx.summary(W, c)
yr = net.groupby(net.index.year).sum()
print((yr * 100).round(2).to_string())
