"""Shared plumbing for intl-rebalance-flow.

Mechanism: balanced funds, target-date funds and global pensions hold the US and the rest of
the world in fixed proportions and rebalance on the calendar (month- and quarter-ends). When
US equities out-run international equities over the period, the rebalance sells US and buys
international, so the international-minus-US spread should rise into / just after the
turn of the period, then give it back (Harvey-Mazzoleni-Melone 2025 for stocks vs bonds;
Parker-Schoar-Sun 2023 for target-date funds' contrarian rebalancing).

Conventions
-----------
* `ret` is close-to-close; the return on day t is earned by a weight set at the close of t-1.
* Month-ends in research come from the data index (last session of each month); the live
  strategy uses `trading_calendar.month_end_sessions` (judged by the NYSE calendar).
* Relative day j: j = 0 is the last session of month m (L), j = -1 the session before,
  j = +1 the first session of month m+1.
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import data as D  # noqa: E402

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
SPL = {"FULL": ("1999-06-01", "2026-12-31"), "IS": ("1999-06-01", "2012-12-31"),
       "OOS": ("2013-01-01", "2026-12-31")}


def load(start="1998-12-01"):
    C = D.load_panel(COUNTRIES + ["EFA", "EEM", "ACWI", "SPY"], "Close", start=start)
    return C, C.pct_change()


def roll_beta(y, x, win=252, minp=126):
    return y.rolling(win, min_periods=minp).cov(x) / x.rolling(win, min_periods=minp).var()


def intl_basket(ret, names=COUNTRIES):
    """Equal-weight daily return of the available country ETFs (NaN until 2 names exist)."""
    r = ret[names]
    n = r.notna().sum(axis=1)
    return r.mean(axis=1).where(n >= 2)


def spreads(ret, names=COUNTRIES, beta_win=252):
    """Daily intl basket return, SPY return, lagged beta and the hedged spread."""
    ri = intl_basket(ret, names)
    rs = ret["SPY"]
    b = roll_beta(ri, rs, beta_win).shift(1)
    return pd.DataFrame({"intl": ri, "spy": rs, "beta": b,
                         "hedged": ri - b * rs, "dollar": ri - rs})


def month_end_positions(index):
    """Integer positions of the last session of each month in `index` (research only)."""
    idx = pd.DatetimeIndex(index)
    per = idx.to_period("M")
    last = pd.Series(np.arange(len(idx)), index=idx).groupby(per).max()
    return last.values


def relative_day_frame(index):
    """For each session: offset from the nearest month-end (j in -10..+10) and the month the
    window belongs to. j<=0 -> month-end of this month, j>=1 -> month-end of previous month."""
    idx = pd.DatetimeIndex(index)
    pos = np.arange(len(idx))
    per = idx.to_period("M")
    last_pos = pd.Series(pos, index=idx).groupby(per).transform("max").values
    first_pos = pd.Series(pos, index=idx).groupby(per).transform("min").values
    j_back = pos - last_pos            # 0 at L, negative before
    j_fwd = pos - first_pos + 1        # 1 at first session of month
    return pd.DataFrame({"j_back": j_back, "j_fwd": j_fwd, "per": per}, index=idx)


def spread_book_weights(pos, close, beta, names=COUNTRIES):
    """Turn a daily position in the hedged spread (units of 'EW intl basket - beta*SPY',
    set at the close of t) into ETF weights: pos/n on each available country, -pos*beta SPY."""
    avail = close[names].notna()
    w = avail.astype(float).div(avail.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w = w.mul(pos, axis=0)
    w["SPY"] = -pos * beta.shift(-1).reindex(pos.index).fillna(1.0)   # beta known at t
    return w.fillna(0.0)


def run_book(w, close, cost=5.0, spy_cost=1.0, name="book"):
    """Daily net return of target weights set at close t (applied to t+1)."""
    cols = list(w.columns)
    ret = close[cols].pct_change().fillna(0.0)
    We = w.reindex(close.index).fillna(0.0).shift(1).fillna(0.0)
    gross = (We * ret).sum(axis=1)
    dW = (We - We.shift(1).fillna(0.0)).abs()
    c = pd.Series(cost, index=cols)
    if "SPY" in c.index:
        c["SPY"] = spy_cost
    net = gross - (dW * c / 1e4).sum(axis=1)
    return net.rename(name), gross.rename(name), dW.sum(axis=1), We


def stats(net, splits=SPL, turn=None, We=None):
    out = {}
    for k, (a, b) in splits.items():
        n = net.loc[a:b]
        out[k] = n.mean() / n.std() * np.sqrt(252) if n.std() > 0 else np.nan
    full = net.loc[splits["FULL"][0]:]
    eq = (1 + full).cumprod()
    out["CAGR"] = eq.iloc[-1] ** (252 / len(full)) - 1
    out["Vol"] = full.std() * np.sqrt(252)
    out["MaxDD"] = (eq / eq.cummax() - 1).min()
    if turn is not None:
        out["Turn/yr"] = turn.loc[full.index].sum() / (len(full) / 252)
    if We is not None:
        out["Gross"] = We.abs().sum(axis=1).loc[full.index].mean()
        out["Active%"] = (We.abs().sum(axis=1).loc[full.index] > 0).mean() * 100
    return pd.Series(out)
