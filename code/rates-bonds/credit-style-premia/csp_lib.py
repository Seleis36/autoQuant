"""Structural credit premia in ETFs, each expressed as a hedged long:

    leg = long X  -  b_rate x IEF  -  b_credit x (HYG or LQD)

with (b_rate, b_credit) the trailing OLS betas of X's daily return on the two hedges, known
at the rebalance close. The leg's return is X's alpha against a rates factor and a credit
factor that are both liquid and shortable. Betas and weights are reset on the last session
of each month (NYSE calendar, so the sample end is not mistaken for a month-end).

Families fixed before any return was computed (literature in the report):
  fallen     fallen-angel HY          ANGL FALN            vs IEF + HYG
  short_hy   short-dated HY           SJNK SHYG HYS        vs IEF + HYG
  short_ig   short-dated IG           VCSH IGSB SPSB       vs IEF + LQD
  long_ig    long-dated IG (the short side of the IG defensive trade) VCLT IGLB SPLB vs TLT + LQD
  loans      senior floating-rate     BKLN SRLN            vs IEF + HYG
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "shared"))
import research_lib as rl  # noqa: E402
from rb_data import etf_close  # noqa: E402

ANN = 252.0
IS = ("2012-07-01", "2018-12-31")
OOS = ("2019-01-01", "2026-12-31")
SPLITS = {"IS": IS, "OOS": OOS, "full": (IS[0], OOS[1])}

FAMILIES = {
    "fallen": (["ANGL", "FALN"], ("IEF", "HYG")),
    "short_hy": (["SJNK", "SHYG", "HYS"], ("IEF", "HYG")),
    "short_ig": (["VCSH", "IGSB", "SPSB"], ("IEF", "LQD")),
    "long_ig": (["VCLT", "IGLB", "SPLB"], ("TLT", "LQD")),
    "loans": (["BKLN", "SRLN"], ("IEF", "HYG")),
}
HEDGES = ["IEF", "TLT", "HYG", "LQD", "SHY"]
ALL = sorted({t for v in FAMILIES.values() for t in v[0]} | set(HEDGES))


def load():
    px = etf_close(ALL, include_pre2010=False)
    return px.loc["2010":], px.loc["2010":].pct_change(fill_method=None)


def month_end_flags(index):
    """True on the last NYSE session of each month (judged with a forward calendar)."""
    sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "rebalance-pressure-bonds"))
    from rp_lib import month_position
    return month_position(index) == 0


def two_factor_betas(y, x1, x2, win=250, minp=120):
    v1, v2 = x1.rolling(win, min_periods=minp).var(), x2.rolling(win, min_periods=minp).var()
    c12 = x1.rolling(win, min_periods=minp).cov(x2)
    cy1, cy2 = y.rolling(win, min_periods=minp).cov(x1), y.rolling(win, min_periods=minp).cov(x2)
    det = v1 * v2 - c12 ** 2
    return (cy1 * v2 - cy2 * c12) / det, (cy2 * v1 - cy1 * c12) / det


def leg_weights(ret, x, hedges, win=250, minp=120, rebal=None):
    """Weights (date x [x, h1, h2]) of a unit-long hedged leg, reset at month-end closes."""
    h1, h2 = hedges
    b1, b2 = two_factor_betas(ret[x], ret[h1], ret[h2], win, minp)
    w = pd.DataFrame({x: 1.0, h1: -b1, h2: -b2})
    w = w.where(b1.notna() & b2.notna())
    rebal = month_end_flags(ret.index) if rebal is None else rebal
    w = w.where(rebal).ffill()                       # carried until the next month-end
    return w.where(ret[x].notna().cumsum() > 0).fillna(0.0)


def run(w, ret, cost_bps=2.0):
    """w[t] held from close t. Returns (net, gross, turnover per year)."""
    w_eff = w.shift(1).fillna(0.0)
    r = ret.reindex(columns=w.columns).fillna(0.0)
    gross = (w_eff * r).sum(axis=1)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = gross - turn * cost_bps / 1e4
    live = w_eff.abs().sum(axis=1) > 0
    return net.where(live), gross.where(live), turn.sum() / (max(live.sum(), 1) / ANN)


def cash_return(index):
    """Daily risk-free return (effective fed funds, act/360, known the day before)."""
    sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "rates-carry-trend"))
    from fetch_fred_daily import fred
    dff = fred("DFF")
    return (dff.reindex(index.union(dff.index)).ffill().shift(1).reindex(index) / 100.0 / 360.0) * (365.0 / 252.0)


def run_excess(w, ret, cost_bps=2.0):
    """As `run`, but in EXCESS of cash: a leg that is long 1 and short 0.3 of hedges holds
    0.7 of net exposure, and the T-bill return on that is not alpha."""
    net, gross, turn = run(w, ret, cost_bps)
    rf = cash_return(ret.index)
    carry = w.shift(1).fillna(0.0).sum(axis=1) * rf
    return net - carry, gross - carry, turn


def stats(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    if len(r) < 120:
        return dict(sharpe=np.nan, ann=np.nan, vol=np.nan, t=np.nan, dd=np.nan, n=len(r))
    eq = (1 + r).cumprod()
    return dict(sharpe=r.mean() / r.std() * np.sqrt(ANN), ann=r.mean() * ANN * 100, vol=r.std() * np.sqrt(ANN) * 100,
                t=rl.newey_west_t(r.values, lags=21), dd=(eq / eq.cummax() - 1).min() * 100, n=len(r))
