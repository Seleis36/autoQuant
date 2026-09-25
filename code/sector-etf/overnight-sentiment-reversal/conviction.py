"""Re-framing: bet bigger when overnight 'sentiment' diverges more across sectors.
Signal = mean over k in {21,42,63,126,252} of -sum(overnight)/ (sqrt(k) * pooled overnight vol),
cross-sectionally demeaned but NOT gross-normalised; gross = dispersion / its trailing 1y median,
capped at 2. Compared with the gross-1 ENS book; also both rescaled to 6% ex-post vol for a
like-for-like Sharpe comparison (Sharpe is scale-free anyway)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx
from strategy import target_weights, SECTORS as S

c = data.load_panel(); o = data.load_panel(field="Open")
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126).fillna(1)
on = np.log(o / c.shift(1))[S]
mask = data.universe_mask(c[S])
pooled = on.stack().rolling(252 * 9, min_periods=500).std().unstack() if False else on.rolling(252, min_periods=126).std().mean(axis=1)
sig = sum((-on.rolling(k).sum() / (np.sqrt(k))).div(pooled, axis=0) for k in [21, 42, 63, 126, 252]) / 5
s = sig.where(mask); s = s.sub(s.mean(axis=1), axis=0)
disp = s.abs().sum(axis=1)
w_unit = s.div(disp.replace(0, np.nan), axis=0).fillna(0)
g = (disp / disp.rolling(252, min_periods=126).median()).clip(upper=2).fillna(1)
rows = []
for nm, w in [("unit-gross", w_unit), ("dispersion-scaled", w_unit.mul(g, axis=0))]:
    w = sx.tranche(w, 21); W = w.copy(); W["SPY"] = -(w * beta).sum(axis=1)
    st, _ = sx.summary(W, c, name=nm); rows.append(st)
st, _ = sx.summary(target_weights(c, o), c, name="ENS rank (reference)"); rows.append(st)
print(sx.fmt(pd.DataFrame(rows)))
