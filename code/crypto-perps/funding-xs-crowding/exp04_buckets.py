"""exp04 — where does the contrarian-funding edge live? Absolute-level buckets of the
annualised trailing-k funding, forward 7d return in excess of the EW universe, IS vs OOS.
Non-overlapping sampling (every 7th day) for the t-stats."""
import numpy as np
import pandas as pd
import common as c

close, vol, fund, mask = c.load()
fwd = close.shift(-7) / close - 1
ew = fwd.where(mask).mean(axis=1)
xs = fwd.sub(ew, axis=0).where(mask)
bins = [-np.inf, -0.2, 0.0, 0.08, 0.1, 0.12, 0.3, 0.6, np.inf]
for k in (7, 30):
    fa = fund.rolling(k, min_periods=int(k * .7)).mean() * 365
    for seg, (a, b) in (("IS", c.IS), ("OOS", c.OOS)):
        idx = close.loc[a:b].index[::7]
        d = pd.DataFrame({"f": fa.loc[idx].stack(), "x": xs.loc[idx].stack()}).dropna()
        d["b"] = pd.cut(d.f, bins)
        g = d.groupby("b", observed=True).x
        out = pd.DataFrame({"n": g.size(), "mean_bp": g.mean() * 1e4,
                            "t": g.mean() / g.std() * np.sqrt(g.size())})
        print(f"\nk={k} {seg}\n", out.round(1).to_string())
