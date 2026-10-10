"""Event-study view before any book is built: does the lagged discount signal predict the
fund's next return, by horizon, with the same sign in IS (2004-14) and OOS (2015-26)?

Signal at close t (uses nav[t] -> usable from close t+1). Forward return h days is measured
from close t+1 to close t+1+h (one-session skip), in excess of the fund's group mean.
"""
import numpy as np
import pandas as pd
import cef_lib as cl

d = cl.load()
disc, ret, group = d["disc"], d["ret"], d["group"]
mask = cl.liquid_mask(d, 1e6)
lr = np.log1p(ret)


def fwd(h, skip=1):
    c = lr.fillna(0.0).cumsum()
    f = (c.shift(-(skip + h)) - c.shift(-skip)).where(ret.notna())
    return f


def gdm(x):
    return cl.group_demean(x.where(mask), group)


sigs = {
    "level": disc,
    "z20": cl.zscore(disc, 20), "z60": cl.zscore(disc, 60),
    "z120": cl.zscore(disc, 120), "z250": cl.zscore(disc, 250),
    "chg5": disc.diff(5), "chg21": disc.diff(21),
}
rows = []
for name, s in sigs.items():
    sg = gdm(s)
    for h in (1, 5, 10, 21):
        f = gdm(fwd(h))
        # sample every h days to avoid overlap in the t-stat
        idx = sg.index[::h]
        ic = sg.loc[idx].rank(axis=1).corrwith(f.loc[idx].rank(axis=1), axis=1)
        # quintile spread: low-signal (cheap) minus high-signal (rich)
        r_ = sg.loc[idx].rank(axis=1, pct=True)
        spread = f.loc[idx].where(r_ <= 0.2).mean(axis=1) - f.loc[idx].where(r_ >= 0.8).mean(axis=1)
        for sname, (a, b) in cl.SPLITS.items():
            i, sp = ic.loc[a:b].dropna(), spread.loc[a:b].dropna()
            rows.append(dict(sig=name, h=h, split=sname, IC=i.mean(),
                             t_IC=i.mean() / i.std() * np.sqrt(len(i)),
                             spread_bp=sp.mean() * 1e4, t_spread=sp.mean() / sp.std() * np.sqrt(len(sp)),
                             n=len(sp)))
out = pd.DataFrame(rows)
piv = out.pivot_table(index=["sig", "h"], columns="split", values=["IC", "spread_bp", "t_spread"])
piv = piv.reindex(columns=["IS", "OOS", "full"], level=1)
print(piv.round(3).to_string())
out.to_csv("02_signal_ic.csv", index=False)
