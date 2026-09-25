"""Screen: is sector momentum/reversal conditional on the calendar? IC of past relative
performance (QTD, YTD, 63d) vs next-5-day beta-residual return, split by where the NEXT 5 days
fall: last 5 trading days of a quarter (window dressing), first 5 of a quarter, December
(tax-loss), first 5 of January, other. Non-overlapping, sampled on bucket start days."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx
S = data.SECTORS
c = data.load_panel(); r = c.pct_change(); spy = r["SPY"]
beta = sx.beta_to(r[S], spy, 126)
lres = np.log1p(r[S] - beta.shift(1).mul(spy, axis=0))
mask = data.universe_mask(c[S])
idx = c.index; s = pd.Series(idx, index=idx)
q = idx.to_period("Q"); y = idx.year
pos_q_end = s.groupby(q).cumcount(ascending=False)       # 0 = last day of quarter
pos_q_start = s.groupby(q).cumcount()                     # 0 = first day of quarter
qtd = lres.groupby(q).cumsum(); ytd = lres.groupby(y).cumsum()
sig = {"QTD": qtd, "YTD": ytd, "R63": lres.rolling(63).sum()}
fwd = lres.rolling(5).sum().shift(-5)
# decision day t, window = t+1..t+5
nxt_end = pos_q_end.shift(-1); nxt_start = pos_q_start.shift(-1)
bucket = pd.Series("other", index=idx)
bucket[(nxt_end == 4)] = "Q-end last5"
bucket[(nxt_start == 0)] = "Q-start first5"
bucket[(nxt_start == 0) & (idx.shift(1, freq=None) if False else (pd.Series(idx.month, index=idx).shift(-1) == 1))] = "Jan first5"
dec_start = (pd.Series(idx.month, index=idx).shift(-1) == 12) & (pd.Series(idx.month, index=idx) == 11)
bucket[dec_start] = "Dec first5"
rows = []
for k, sg in sig.items():
    ic = sg.where(mask).rank(axis=1).corrwith(fwd.where(mask).rank(axis=1), axis=1)
    for b in bucket.unique():
        for seg, (a, bb) in [("IS", sx.IS), ("OOS", sx.OOS)]:
            m = (bucket == b)
            x = ic[m].loc[a:bb].dropna()
            if b == "other":
                x = x.iloc[::5]
            rows.append(dict(sig=k, bucket=b, seg=seg, IC=x.mean(), t=x.mean() / x.std() * np.sqrt(len(x)), n=len(x)))
print(pd.DataFrame(rows).pivot_table(index=["sig", "bucket"], columns="seg", values=["IC", "t", "n"]).round(3))
