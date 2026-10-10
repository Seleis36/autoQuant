"""Wide frames, cleaning and the backtest wrapper for the bond-CEF discount research.

Timing convention used everywhere in this folder
    disc[t]   = ln(close[t] / nav[t])              -- NOT knowable at close t (NAV is published
                                                      in the evening)
    signal[t] = f(disc[..t])                       -- knowable before the open of t+1
    weight held from close t+1 to close t+2        -- `lag=1` in `xs_backtest`
so a position is entered one full session after the last price that built its signal. That
also keeps bid-ask bounce in the signal's closing print out of the fill.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, HERE)
import research_lib as rl  # noqa: E402
import strategy as S  # noqa: E402

ANN = 252.0
PANEL = os.path.join(rl.DATA_DIR, "CEF_BOND_panel_d.parquet")
UNIVERSE_CSV = os.path.join(HERE, "cef_universe.csv")
IS = ("2004-01-01", "2014-12-31")
OOS = ("2015-01-01", "2026-12-31")
SPLITS = {"IS": IS, "OOS": OOS, "full": (IS[0], OOS[1])}


def load(start="2003-01-01"):
    """dict of wide frames: close (unadjusted), adj, nav, volume, ret (total), dollar volume,
    disc (log price/NAV, cleaned by `strategy.clean_discount`), open/high/low, plus `group`
    (ticker -> muni/taxable) and `uni` (metadata)."""
    p = pd.read_parquet(PANEL)
    p = p[p["date"] >= start]
    wide = {c: p.pivot(index="date", columns="ticker", values=c).sort_index()
            for c in ["open", "high", "low", "close", "adj_close", "volume", "nav"]}
    close, adj, nav, vol = wide["close"], wide["adj_close"], wide["nav"], wide["volume"]
    nav = nav.where(nav > 0)
    close = close.where(close > 0)
    ret = adj.pct_change(fill_method=None)
    # Real one-day moves reach +54 % (OXLC, 2020-03-19) and are kept. Only a print that moves
    # by more than a factor of 3 is treated as a data break.
    ret = ret.where(np.log(close).diff().abs() <= S.GLITCH)
    ret[[c for c in ret.columns if c in S.EXCLUDE]] = np.nan
    disc = S.clean_discount(close, nav, anchor_last=True)
    uni = pd.read_csv(UNIVERSE_CSV).set_index("ticker")
    group = uni["group"].reindex(close.columns)
    return dict(close=close, adj=adj, nav=nav, volume=vol, ret=ret, dv=close * vol,
                disc=disc, group=group, uni=uni, open=wide["open"].where(wide["open"] > 0),
                high=wide["high"].where(wide["high"] > 0), low=wide["low"].where(wide["low"] > 0))


def liquid_mask(d, min_dv=1e6, min_price=3.0, win=60, min_hist=250):
    """Point-in-time tradable universe (same rule as the deployable strategy)."""
    return S.liquid_mask(d["close"], d["nav"], d["volume"], d["disc"], min_dv, min_price, win, min_hist)


def zscore(disc, win, minp=None):
    minp = minp or max(20, win // 2)
    m = disc.rolling(win, min_periods=minp).mean()
    s = disc.rolling(win, min_periods=minp).std()
    return (disc - m) / s.where(s > 1e-4)


def group_demean(sig, group):
    out = sig.copy()
    for g in group.dropna().unique():
        cols = group.index[group == g]
        out[cols] = sig[cols].sub(sig[cols].mean(axis=1), axis=0)
    return out


def ls_weights(sig, mask, q=0.2, gross=1.0, group=None, min_names=10):
    """Long the lowest-`q` signal names / short the highest-`q`, equal weight, each side
    gross/2. With `group`, the sort is done inside each group and sides are sized by the
    group's share of names (so the book is dollar-neutral within muni and within taxable)."""
    s = sig.where(mask)
    if group is None:
        groups = [s.columns]
    else:
        groups = [group.index[group == g] for g in group.dropna().unique()]
    w = pd.DataFrame(0.0, index=s.index, columns=s.columns)
    n_tot = s.notna().sum(axis=1).replace(0, np.nan)
    for cols in groups:
        sg = s[cols]
        n = sg.notna().sum(axis=1)
        k = (n * q).round().clip(lower=1)
        lo = sg.rank(axis=1, ascending=True).le(k, axis=0) & sg.notna()
        hi = sg.rank(axis=1, ascending=False).le(k, axis=0) & sg.notna()
        share = (n / n_tot).where(n >= min_names, 0.0)
        wl = lo.astype(float).div(lo.sum(axis=1).replace(0, np.nan), axis=0)
        ws = hi.astype(float).div(hi.sum(axis=1).replace(0, np.nan), axis=0)
        w[cols] = (wl - ws).mul(share * gross / 2, axis=0).fillna(0.0)
    # renormalise so gross is `gross` when some group is too thin to trade
    g = w.abs().sum(axis=1).replace(0, np.nan)
    return w.div(g, axis=0).fillna(0.0) * gross


def hysteresis_weights(sig, mask, group, q_in=0.2, q_out=0.5, gross=1.0):
    """Long while the within-group percentile rank has been <= q_in and has not yet risen above
    q_out; short symmetric. Equal weight inside each side, sides sized gross/2."""
    s = sig.where(mask)
    pr = pd.DataFrame(np.nan, index=s.index, columns=s.columns)
    for g in group.dropna().unique():
        cols = group.index[group == g]
        n = s[cols].notna().sum(axis=1)
        pr[cols] = s[cols].rank(axis=1, pct=True).where(n >= 10, np.nan, axis=0)
    a = pr.values
    state = np.zeros(a.shape[1])
    out = np.zeros_like(a)
    for i in range(a.shape[0]):
        x = a[i]
        ok = ~np.isnan(x)
        state[~ok] = 0.0
        enter_l = ok & (x <= q_in)
        enter_s = ok & (x >= 1 - q_in)
        exit_l = ok & (state > 0) & (x > q_out)
        exit_s = ok & (state < 0) & (x < 1 - q_out)
        state[exit_l | exit_s] = 0.0
        state[enter_l] = 1.0
        state[enter_s] = -1.0
        out[i] = state
    st = pd.DataFrame(out, index=s.index, columns=s.columns)
    wl = (st > 0).astype(float)
    ws = (st < 0).astype(float)
    w = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross / 2 \
        - ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0) * gross / 2
    return w


def hold_every(w, k):
    """Rebalance only every k-th session (weights carried in between)."""
    if k <= 1:
        return w
    keep = np.arange(len(w)) % k == 0
    return w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0)


def xs_backtest(w, ret, cost_bps=10.0, lag=1, borrow_bps=0.0, name="xs"):
    """w[t] is built from data through close t and is HELD from close t+lag to close t+lag+1.

    lag=1 is the honest convention here (NAV published after the close). Cost is charged on
    the traded notional at the entry close; `borrow_bps` is an annual fee on the short side.
    Returns (net, gross, stats).
    """
    w_eff = w.shift(1 + lag).fillna(0.0)          # weight earning ret[t]
    r = ret.reindex(w.index).fillna(0.0)
    gross = (w_eff * r).sum(axis=1)
    turn = (w_eff - w_eff.shift(1).fillna(0.0)).abs().sum(axis=1)
    short = w_eff.clip(upper=0).abs().sum(axis=1)
    net = gross - turn * cost_bps / 1e4 - short * borrow_bps / 1e4 / ANN
    st = rl.perf_stats(net, ann=ANN, name=name)
    st["Turnover_ann"] = turn.sum() / (len(turn) / ANN)
    st["GrossExp"] = w_eff.abs().sum(axis=1).mean()
    st["SharpeGross"] = gross.mean() / gross.std() * np.sqrt(ANN) if gross.std() > 0 else np.nan
    return net.rename(name), gross.rename(name), st


def sharpe(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(ANN) if len(r) > 50 and r.std() > 0 else np.nan
