"""overnight-sentiment-reversal -- target weights for the deployment agent.

Mechanism (Aboody, Even-Tov, Lehavy & Trueman 2018): a sector ETF's overnight return
(Open_t / Close_{t-1}) proxies investor sentiment; sectors whose recent overnight returns were
high subsequently under-perform, net of the market. Book: long low-overnight / short
high-overnight sectors, linear in the signal rank, SPY hedge to zero beta.

Convention: inputs are daily bars up to and including the close of day t; the returned row t is
the target weight to hold from the close of t (fills at that close, earns t+1).
"""
import numpy as np
import pandas as pd

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]


def target_weights(close, open_, lookbacks=(21, 42, 63, 126, 252), tranche_days=21,
                   beta_halflife=126, min_history=252, gross=1.0):
    """close, open_: DataFrames (date x ticker) with the 11 sector ETFs and SPY, auto-adjusted.

    Returns a DataFrame of target weights on the same index, columns SECTORS + ['SPY'].
    Sector legs sum to ~0 with gross `gross`; SPY carries the beta hedge.
    """
    cols = [s for s in SECTORS if s in close.columns]
    c = close[cols + ["SPY"]]
    o = open_[cols + ["SPY"]]
    r = c.pct_change()
    on = np.log(o / c.shift(1))[cols]
    listed = c[cols].notna() & c[cols].shift(min_history).notna()
    # mean cross-sectional rank of -overnight over the look-backs
    ens = 0
    for k in lookbacks:
        s = (-on.rolling(k).sum()).where(listed)
        rk = s.rank(axis=1, pct=True)
        ens = ens + rk.sub(rk.mean(axis=1), axis=0)
    ens = (ens / len(lookbacks)).where(listed)
    ens = ens.sub(ens.mean(axis=1), axis=0)
    w = ens.div(ens.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross
    w = w.rolling(tranche_days, min_periods=1).mean()          # 21 staggered monthly tranches
    spy = r["SPY"]
    cov = r[cols].apply(lambda x: x.ewm(halflife=beta_halflife, min_periods=beta_halflife).cov(spy))
    beta = cov.div(spy.ewm(halflife=beta_halflife, min_periods=beta_halflife).var(), axis=0).fillna(1.0)
    out = w.copy()
    for s in SECTORS:
        if s not in out.columns:
            out[s] = 0.0
    out["SPY"] = -(w * beta).sum(axis=1)
    return out[SECTORS + ["SPY"]]
