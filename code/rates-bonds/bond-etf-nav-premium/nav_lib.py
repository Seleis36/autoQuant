"""Frames and helpers for the bond-ETF NAV premium / flow research.

Timing: nav[t] and shares[t] are posted after the close of t, so a signal built on them is
HELD from close t+1 (`lag=1` below). Returns are dividend-adjusted closes; the premium uses
the unadjusted close.
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
PANEL = os.path.join(rl.DATA_DIR, "SPDR_BOND_panel_d.parquet")
IS = ("2008-01-01", "2017-12-31")
OOS = ("2018-01-01", "2026-12-31")
SPLITS = {"IS": IS, "OOS": OOS, "full": (IS[0], OOS[1])}
HEDGES = ["IEF", "HYG"]


def load():
    p = pd.read_parquet(PANEL)
    w = {c: p.pivot(index="date", columns="ticker", values=c).sort_index()
         for c in ["close", "adj_close", "volume", "nav", "shares"]}
    sector = p.drop_duplicates("ticker").set_index("ticker")["sector"]
    ret = w["adj_close"].pct_change(fill_method=None)
    prem = np.log(w["close"] / w["nav"])
    prem = prem.where(prem.abs() < 0.2)
    hedge = etf_close(HEDGES).reindex(ret.index).pct_change(fill_method=None)
    return dict(close=w["close"], adj=w["adj_close"], volume=w["volume"], nav=w["nav"],
                shares=w["shares"], ret=ret, prem=prem, sector=sector, hedge=hedge,
                dv=w["close"] * w["volume"])


def trailing_betas(ret, hedge, win=120, minp=60):
    """Rolling OLS betas of each fund on [IEF, HYG], using returns up to and including t."""
    x1, x2 = hedge["IEF"], hedge["HYG"]
    v1, v2 = x1.rolling(win, min_periods=minp).var(), x2.rolling(win, min_periods=minp).var()
    c12 = x1.rolling(win, min_periods=minp).cov(x2)
    det = v1 * v2 - c12 ** 2
    b1, b2 = {}, {}
    for c in ret.columns:
        cy1 = ret[c].rolling(win, min_periods=minp).cov(x1)
        cy2 = ret[c].rolling(win, min_periods=minp).cov(x2)
        b1[c] = (cy1 * v2 - cy2 * c12) / det
        b2[c] = (cy2 * v1 - cy1 * c12) / det
    return pd.DataFrame(b1), pd.DataFrame(b2)


def residual_returns(ret, hedge, b1, b2):
    """Fund return minus yesterday's betas times today's hedge returns (tradable hedge)."""
    return ret - b1.shift(1).mul(hedge["IEF"], axis=0) - b2.shift(1).mul(hedge["HYG"], axis=0)


def zscore(x, win, minp=None):
    minp = minp or max(20, win // 2)
    s = x.rolling(win, min_periods=minp).std()
    return (x - x.rolling(win, min_periods=minp).mean()) / s.where(s > 1e-6)


def sharpe(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(ANN) if len(r) > 50 and r.std() > 0 else np.nan


def book(w_fund, d, b1, b2, cost_bps=2.0, lag=1, hedge=True):
    """w_fund[t]: fund weights from data through close t, held from close t+lag.

    With hedge=True the book's IEF and HYG betas are neutralised with those two ETFs, using the
    betas known at the entry close. Cost on every traded leg. Returns (net, gross, turnover/yr).
    """
    w = w_fund.shift(lag).fillna(0.0)                  # held from close t (after shift) to t+1
    wh = pd.DataFrame(0.0, index=w.index, columns=HEDGES)
    if hedge:
        wh["IEF"] = -(w * b1.shift(lag - 1 if lag > 0 else 0).reindex_like(w)).sum(axis=1)
        wh["HYG"] = -(w * b2.shift(lag - 1 if lag > 0 else 0).reindex_like(w)).sum(axis=1)
    w_all = pd.concat([w, wh], axis=1)
    r_all = pd.concat([d["ret"], d["hedge"]], axis=1).reindex(w_all.index).fillna(0.0)
    w_eff = w_all.shift(1).fillna(0.0)
    gross = (w_eff * r_all).sum(axis=1)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    net = gross - turn * cost_bps / 1e4
    return net, gross, turn.sum() / (len(turn) / ANN)
