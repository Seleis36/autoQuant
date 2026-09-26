"""Shared pieces for the non-synchronous overreaction study."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np, pandas as pd
import data as D

ASIA = ["EWJ", "EWY", "EWA", "FXI", "INDA", "EEM"]
EUROPE = ["EWG", "EWU", "EFA"]
AMERICAS = ["EWC", "EWZ"]


def load(start="2003-01-01"):
    tick = ASIA + EUROPE + AMERICAS + ["ACWI", "SPY"]
    C = D.load_panel(tick, "Close", start=start)
    O = D.load_panel(tick, "Open", start=start)
    return C, O


def rolling_beta(y, x, win=250, minp=120):
    """beta of each column of y on series x, rolling, using data up to and including t."""
    cov = y.rolling(win, min_periods=minp).cov(x)
    var = x.rolling(win, min_periods=minp).var()
    return cov.div(var, axis=0)


def residual_signal(C, O, names, beta_win=250, z_win=60):
    """US-session residual u_{i,t} = r^oc_i - beta_{t-1} r^oc_SPY, z-scored by its own
    trailing std (lagged one day so today's move does not scale itself)."""
    roc = (C / O - 1)
    b = rolling_beta(roc[names], roc["SPY"], beta_win).shift(1)
    u = roc[names] - b.mul(roc["SPY"], axis=0)
    sd = u.rolling(z_win, min_periods=40).std().shift(1)
    return u, u / sd


def hedged_book(w, C, names, beta_win=250, cost_etf=5.0, cost_spy=1.0):
    """w: target weights (known at close t) on `names`; add a SPY leg that removes the
    close-to-close beta of the book; returns (net, gross, turnover-etf, turnover-spy)."""
    r = C.pct_change()
    bcc = rolling_beta(r[names], r["SPY"], beta_win).shift(0)  # known at close t
    spy_w = -(w * bcc).sum(axis=1)
    W = w.copy(); W["SPY"] = spy_w
    W = W.fillna(0.0)
    We = W.shift(1).fillna(0.0)
    gross = (We * r[W.columns].fillna(0.0)).sum(axis=1)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    t_etf = dW[names].sum(axis=1); t_spy = dW["SPY"]
    net = gross - t_etf * cost_etf / 1e4 - t_spy * cost_spy / 1e4
    return net, gross, t_etf, t_spy
