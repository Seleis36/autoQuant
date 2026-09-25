"""Monthly / weekly cross-sectional book helpers for the country-ETF cross-section.

Convention: a signal frame `sig` (date x ticker) is read at the close of each rebalance date
(last trading day of the month by default); target weights are held until the next rebalance
and `research_lib.backtest_xs` applies them from the next bar (shift 1) and charges turnover.
"""
import os, sys
import numpy as np
import pandas as pd
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import research_lib as rl  # noqa: E402

ANN = 252.0
COUNTRY10 = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA", "SPY"]


def rebalance_dates(index, freq="M"):
    """Research-only: last date of each period *in the data*. The final, partially observed
    period is treated as finished, so do NOT use this in a live `strategy.py`; use
    `trading_calendar.month_end_sessions`, which judges the final date by the NYSE calendar."""
    s = pd.Series(index, index=index)
    if freq == "M":
        return pd.DatetimeIndex(s.groupby([index.year, index.month]).max().values)
    if freq == "W":
        return pd.DatetimeIndex(s.groupby(index.to_period("W-FRI")).max().values)
    if freq == "Q":
        return pd.DatetimeIndex(s.groupby([index.year, index.quarter]).max().values)
    raise ValueError(freq)


def hold(w_reb, index):
    """Weights set on rebalance dates, carried forward until the next one."""
    return w_reb.reindex(index).ffill().fillna(0.0)


def rank_weights(sig, mask=None, gross=1.0):
    """Demeaned cross-sectional rank, scaled to sum |w| = gross (dollar-neutral)."""
    s = sig.where(mask) if mask is not None else sig
    r = s.rank(axis=1)
    r = r.sub(r.mean(axis=1), axis=0)
    return r.div(r.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross


def tercile_weights(sig, mask=None, k=3, gross=1.0):
    """Long top-k / short bottom-k, equal weight, gross split half/half."""
    s = sig.where(mask) if mask is not None else sig
    hi = s.rank(axis=1, ascending=False) <= k
    lo = s.rank(axis=1, ascending=True) <= k
    w = hi.astype(float).div(hi.sum(axis=1).replace(0, np.nan), axis=0) * gross / 2 \
        - lo.astype(float).div(lo.sum(axis=1).replace(0, np.nan), axis=0) * gross / 2
    return w.fillna(0.0)


def vol_target_book(w, ret, target=0.10, lookback=126, cap=3.0):
    """Scale the whole book to an ex-ante vol target from the trailing covariance of the
    constituents (estimated on data up to the rebalance date -> no look-ahead)."""
    out = w.copy() * 0.0
    for d in w.index:
        hist = ret.loc[:d].iloc[-lookback:]
        wd = w.loc[d]
        cols = wd[wd != 0].index
        if len(cols) == 0 or len(hist) < 60:
            continue
        cov = hist[cols].fillna(0.0).cov().values * ANN
        v = float(np.sqrt(max(wd[cols].values @ cov @ wd[cols].values, 1e-12)))
        out.loc[d, cols] = wd[cols] * min(target / v, cap)
    return out


def run(w_reb, close, cost_bps=5.0, name="book", spy_cost_bps=None):
    """Daily P&L of rebalance-date weights; per-name costs (SPY cheaper if given)."""
    W = hold(w_reb, close.index)
    ret = close.pct_change()
    We = W.shift(1).fillna(0.0)
    gross = (We * ret.fillna(0.0)).sum(axis=1)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    c = pd.Series(cost_bps, index=W.columns)
    if spy_cost_bps is not None and "SPY" in c.index:
        c["SPY"] = spy_cost_bps
    net = gross - (dW * c / 1e4).sum(axis=1)
    net.name = name
    turn = dW.sum(axis=1)
    return net, gross, turn, We


def summarize(net, splits, turn=None, We=None, name=None):
    row = {}
    for k, (a, b) in splits.items():
        n = net.loc[a:b]
        n = n[n.index >= n.ne(0).idxmax()] if n.ne(0).any() else n
        row[f"{k}_SR"] = n.mean() / n.std() * np.sqrt(ANN) if n.std() > 0 else np.nan
        row[f"{k}_CAGR"] = (1 + n).prod() ** (ANN / max(len(n), 1)) - 1
    full = net[net.index >= net.ne(0).idxmax()] if net.ne(0).any() else net
    eq = (1 + full).cumprod()
    row["MaxDD"] = (eq / eq.cummax() - 1).min()
    row["Vol"] = full.std() * np.sqrt(ANN)
    row["t_NW"] = rl.newey_west_t(full.values, lags=21)
    if turn is not None:
        row["Turn/yr"] = turn.loc[full.index].sum() / (len(full) / ANN)
    if We is not None:
        row["Gross"] = We.abs().sum(axis=1).loc[full.index].mean()
        row["Net"] = We.sum(axis=1).loc[full.index].mean()
    return pd.Series(row, name=name)
