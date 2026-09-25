"""EDA: cross-sectional rank IC of past k-day sector returns (raw-minus-SPY and
beta-residual) against the next h-day relative return. IS only for choosing; OOS shown
for reference. Answers: at which horizons do sector ETFs reverse, at which do they trend?"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx

c = data.load_panel()
r = c.pct_change()
spy = r["SPY"]
sec = r[data.SECTORS]
beta = sx.beta_to(sec, spy, halflife=126)
resid = sec - beta.shift(1).mul(spy, axis=0)     # beta known before the day
rel = sec.sub(spy, axis=0)
mask = data.universe_mask(c[data.SECTORS])

def ic(sig, fwd, mask):
    s = sig.where(mask); f = fwd.where(mask)
    return s.rank(axis=1).corrwith(f.rank(axis=1), axis=1)

rows = []
for name, base in [("rel", rel), ("resid", resid)]:
    lr = np.log1p(base.fillna(0)).where(base.notna())
    cum = lambda k: lr.rolling(k).sum()
    for h in [1, 5, 21]:
        fwd = lr.rolling(h).sum().shift(-h)
        for k in [1, 2, 3, 5, 10, 21, 42, 63, 126, 252]:
            x = ic(cum(k), fwd, mask)
            for seg, (a, b) in sx.SPLITS.items():
                v = x.loc[a:b].dropna()
                # non-overlapping t-stat approx: use every h-th obs
                vv = v.iloc[::h]
                rows.append(dict(base=name, h=h, k=k, seg=seg, IC=v.mean(), t=vv.mean()/vv.std()*np.sqrt(len(vv))))
df = pd.DataFrame(rows)
p = df.pivot_table(index=["base", "h", "k"], columns="seg", values=["IC", "t"])
pd.set_option("display.width", 200)
print(p.round(3))
