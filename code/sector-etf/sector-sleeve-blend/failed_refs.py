"""Reference (canonical, not best-picked) books of the ideas that FAILED this session, so the
blend can be tested with them included -- the honest control for sleeve selection."""
import os, sys
_H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_H, "..", "shared"))
import numpy as np, pandas as pd
import data, sxlib as sx, french

S = data.SECTORS


def _lin(s, mask):
    s = s.where(mask); s = s.sub(s.mean(axis=1), axis=0)
    return s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)


def refs(c):
    r = c.pct_change(); spy = r["SPY"]
    beta = sx.beta_to(r[S], spy, 126).fillna(1)
    mask = data.universe_mask(c[S])
    me = c.index.to_series().groupby(c.index.to_period("M")).transform("max") == c.index.to_series()
    out = {}
    # REV: 5-day relative-return reversal, 5-day tranches, SPY-hedged (sector-short-reversal)
    w = sx.tranche(_lin(-(r[S].sub(spy, axis=0)).rolling(5).sum(), mask), 5)
    W = w.copy(); W["SPY"] = -(w * beta).sum(axis=1); out["REV"] = W
    # BAB: FP beta, bottom/top-3, monthly, SPY-hedged (sector-bab)
    import importlib.util
    b = sx.beta_to(r[S], spy, 252, 252)
    s = b.where(mask)
    lo = s.rank(axis=1) <= 3; hi = s.rank(axis=1, ascending=False) <= 3
    w = lo.astype(float).div(lo.sum(axis=1), axis=0).fillna(0) * 0.5 - hi.astype(float).div(hi.sum(axis=1), axis=0).fillna(0) * 0.5
    w = w.where(me).ffill().fillna(0)
    W = w.copy(); W["SPY"] = -(w * beta).sum(axis=1); out["BAB"] = W
    # SEAS: KLN canonical 20y same-month mean, top/bottom 2, SPY-hedged (sector-seasonality)
    fr = french.sector_returns()
    sig = pd.DataFrame(index=fr.index, columns=fr.columns, dtype=float)
    for t in fr.index:
        tgt = t + pd.offsets.MonthEnd(1)
        past = fr.loc[:t - pd.DateOffset(months=11)]
        past = past[(past.index > tgt - pd.DateOffset(years=20)) & (past.index.month == tgt.month)]
        if len(past) >= 10:
            sig.loc[t] = past.mean()
    medates = c.index[me.values]
    sd = sig.reindex(pd.DatetimeIndex(medates) + pd.offsets.MonthEnd(0)); sd.index = medates
    sd = sd.reindex(c.index).ffill().where(c[S].notna())
    lo = sd.rank(axis=1) <= 2; hi = sd.rank(axis=1, ascending=False) <= 2
    w = hi.astype(float).div(hi.sum(axis=1), axis=0).fillna(0) * 0.5 - lo.astype(float).div(lo.sum(axis=1), axis=0).fillna(0) * 0.5
    W = w.copy(); W["SPY"] = -(w * beta).sum(axis=1); out["SEAS"] = W
    return out
