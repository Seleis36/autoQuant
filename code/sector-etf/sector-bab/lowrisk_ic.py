"""Re-framing: the rest of the low-risk family at sector level -- total vol, idiosyncratic
vol, MAX (Bali-Cakici-Whitelaw lottery), return skewness, correlation to SPY (Asness et al.
2020 'betting against correlation'), beta. Rank IC vs next 21-day beta-residual return,
non-overlapping monthly samples. Negative IC = low-risk premium exists."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel(); S = data.SECTORS
r = c.pct_change(); spy = r["SPY"]
mask = data.universe_mask(c[S])
beta = sx.beta_to(r[S], spy, 126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
sig = {
    "beta126": beta,
    "vol63": r[S].rolling(63).std(),
    "ivol63": resid.rolling(63).std(),
    "max21": r[S].rolling(21).max(),
    "skew63": r[S].rolling(63).skew(),
    "corr126": r[S].rolling(126).corr(spy),
}
fwd = np.log1p(resid).rolling(21).sum().shift(-21)
me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()
rows = []
for k, s in sig.items():
    ss = s.where(mask)[me]; ff = fwd.where(mask)[me]
    ic = ss.rank(axis=1).corrwith(ff.rank(axis=1), axis=1).dropna()
    for seg, (a, b) in sx.SPLITS.items():
        v = ic.loc[a:b]
        rows.append(dict(sig=k, seg=seg, IC=v.mean(), t=v.mean() / v.std() * np.sqrt(len(v))))
print(pd.DataFrame(rows).pivot(index="sig", columns="seg", values=["IC", "t"]).round(3))
