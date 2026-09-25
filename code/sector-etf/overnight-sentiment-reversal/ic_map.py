"""IC map of the overnight-return signal: lookback x horizon x normalisation, and the
intraday / close-to-close counterparts, all vs next-h-day beta-residual returns.
Overnight = Open_t / Close_{t-1} - 1 (both known at close t). Non-overlapping samples
every h days (h=1: daily)."""
import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

S = data.SECTORS
c = data.load_panel(); o = data.load_panel(field="Open")
r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
resid = r[S] - beta.shift(1).mul(spy, axis=0)
onr = np.log(o / c.shift(1)); inr = np.log(c / o)
on_rel = onr[S].sub(onr["SPY"], axis=0)
in_rel = inr[S].sub(inr["SPY"], axis=0)
on_res = onr[S] - beta.shift(1).mul(onr["SPY"], axis=0)
mask = data.universe_mask(c[S])
bases = {"on_rel": on_rel, "on_res": on_res, "on_raw": onr[S], "in_rel": in_rel,
         "cc_resid": np.log1p(resid)}
rows = []
for (bn, b), k, h in itertools.product(bases.items(), [5, 21, 42, 63, 126, 252], [1, 5, 21, 63]):
    s = b.rolling(k).sum().where(mask)
    f = np.log1p(resid).rolling(h).sum().shift(-h).where(mask)
    ic = s.rank(axis=1).corrwith(f.rank(axis=1), axis=1)
    for seg, (a, bb) in sx.SPLITS.items():
        x = ic.loc[a:bb].dropna().iloc[::h]
        rows.append(dict(base=bn, k=k, h=h, seg=seg, IC=x.mean(), t=x.mean() / x.std() * np.sqrt(len(x))))
df = pd.DataFrame(rows)
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 300)
print(df.pivot_table(index=["base", "h", "k"], columns="seg", values=["IC", "t"]).round(3))
df.to_csv(os.path.join(os.path.dirname(__file__), "ic_map.csv"))
