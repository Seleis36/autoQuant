"""Blend of sleeves with ex-ante risk weights, evaluated on the NETTED combined weight matrix
(costs on combined turnover) in excess of T-bills.
  k_i(t) = (target / sqrt(N)) / sigma_i(t), sigma_i = EWM(126) vol of sleeve i's own net returns
  through close t, updated at month ends only; total gross capped at 3.
Variants:
  CORE4   ON, CAL, DIP, RATE                       (the four with positive IS and OOS)
  CORE3   ON, CAL, DIP                             (drop the t<2 RATE sleeve)
  ALL7    CORE4 + REV, BAB, SEAS reference books  (no hindsight on which ideas failed)
  WF7     ALL7, but a sleeve is only held in year Y if its expanding net Sharpe through Y-1 > 0
          (first decision 2002 with >= 3y of history; a sleeve with no history is excluded)
"""
import sys, os, itertools
_H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _H)
from sleeves import all_sleeves  # noqa: sets sys.path
from failed_refs import refs
import numpy as np, pandas as pd
import data, sxlib as sx

TARGET = 0.10
c = data.load_panel(); o = data.load_panel(field="Open")
SL = all_sleeves(c, o); SL.update(refs(c))
cols = data.SECTORS + ["SPY"]
SL = {k: v.reindex(columns=cols).fillna(0) for k, v in SL.items()}
R = {k: sx.summary(W, c, name=k)[1] for k, W in SL.items()}
R = pd.DataFrame(R)
me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()
vol = R.ewm(halflife=126, min_periods=126).std() * np.sqrt(252)
vol = vol.where(me.reindex(vol.index)).ffill()


def blend(names, wf=False):
    n = len(names)
    k = (TARGET / np.sqrt(n)) / vol[names]
    if wf:
        yrs = R.index.year
        on = pd.DataFrame(0.0, index=R.index, columns=names)
        for Y in range(2002, R.index[-1].year + 1):
            past = R.loc[: f"{Y-1}-12-31", names]
            ok = []
            for nm in names:
                x = past[nm].dropna(); x = x[x != 0]
                ok.append(len(x) > 756 and x.mean() > 0)
            on.loc[str(Y)] = np.array(ok, dtype=float)
        nact = on.sum(axis=1).replace(0, np.nan)
        k = (TARGET / np.sqrt(nact)).values[:, None] / vol[names] * on
    k = k.reindex(c.index).fillna(0)
    Wt = sum(SL[nm].mul(k[nm], axis=0) for nm in names)
    g = Wt.abs().sum(axis=1)
    Wt = Wt.mul((3.0 / g).clip(upper=1.0).fillna(1.0), axis=0)
    return Wt

rows, nets = [], {}
sets = {"CORE4": ["ON", "CAL", "DIP", "RATE"], "CORE3": ["ON", "CAL", "DIP"],
        "ALL7": ["ON", "CAL", "DIP", "RATE", "REV", "BAB", "SEAS"]}
for nm, names in sets.items():
    Wt = blend(names)
    st, net = sx.summary_rf(Wt, c, name=nm, start="2000-06-01"); rows.append(st); nets[nm] = net
    st5, _ = sx.summary_rf(Wt, c, name=nm + "@5bp", cost_bps=5, start="2000-06-01"); rows.append(st5)
Wt = blend(sets["ALL7"], wf=True)
st, net = sx.summary_rf(Wt, c, name="WF7", start="2002-01-01"); rows.append(st); nets["WF7"] = net
for k_ in SL:
    st, _ = sx.summary_rf(SL[k_], c, name=f"sleeve {k_}", start="2000-06-01"); rows.append(st)
bh = pd.DataFrame(0.0, index=c.index, columns=cols); bh["SPY"] = 1
st, _ = sx.summary_rf(bh, c, name="SPY B&H (excess)", start="2000-06-01"); rows.append(st)
df = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(sx.fmt(df.rename(columns={"CAGRx": "CAGR"})))
pd.DataFrame(nets).to_parquet(os.path.join(_H, "blend_returns.parquet"))
df.to_csv(os.path.join(_H, "blend.csv"))
print(R.loc["2000-06":].corr().round(2))
