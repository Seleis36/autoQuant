"""Rebalancing-pressure signals (Harvey, Mazzoleni & Melone 2025) and data for testing them
on the Treasury leg.

A notional 60/40 fund's equity weight drifts with stock and bond returns:
    w[t] = w[t-1](1+r_eq) / (w[t-1](1+r_eq) + (1-w[t-1])(1+r_bd))
* threshold fund (band d): trades back to 60 % on the session after |w-0.6| >= d
* calendar fund: trades back to 60 % at the last close of each month
Signal = w[t] - 0.6 at close t (positive = stocks overweight = the fund must sell stocks and
BUY bonds). The paper averages the threshold signal over d = 0 ... 2.5 %.

Data
* stocks : S&P 500 price index (^GSPC), stitched 1982-2026 -- used for the drift only
* bonds  : synthetic 10y constant-maturity total return (FRED CMT, `rb_data.cmt_returns`)
           1982-2026 for the drift; traded instruments are syn10 before 2010 and IEF / TLT
           from 2002-07.
Timing trap: CMT yields are a 15:30 ET mark, the S&P closes at 16:00. The synthetic bond's
"next-day" return therefore starts 30 minutes BEFORE the stock close that built the signal.
ETF tests have no such overlap; the synthetic sample is the design sample only.
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
from rb_data import etf_close, cmt_returns  # noqa: E402

ANN = 252.0
IS = ("1990-01-01", "2009-12-31")
OOS = ("2010-01-01", "2026-12-31")
PAPER = ("1997-01-01", "2023-12-31")
POST = ("2024-01-01", "2026-12-31")
TARGET = 0.6


def _read(name):
    df = pd.read_parquet(os.path.join(rl.DATA_DIR, name))
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df["Close"][~df.index.duplicated(keep="last")].sort_index()


def sp500():
    parts = [_read("IDX_GSPC_d_long.parquet"), _read("IDX_GSPC_d_pre2010.parquet"), _read("IDX_GSPC_d.parquet")]
    s = pd.concat(parts)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load():
    eq = sp500().pct_change()
    syn = cmt_returns(maturities=(10, 30))
    etf = etf_close(["SPY", "IEF", "TLT"]).pct_change(fill_method=None)
    idx = eq.index.intersection(syn.index)
    idx = idx[idx >= "1982-02-01"]
    return dict(eq=eq.reindex(idx), bd=syn[10].reindex(idx), syn30=syn[30].reindex(idx),
                etf=etf.reindex(idx), idx=idx)


def drift_weight(eq, bd, reset):
    """Equity weight at each close; `reset[t]` True means the fund trades back to target at
    close t, so the weight carried into t+1 is the target. Returned value is the PRE-trade
    weight at close t (the deviation the fund has to close)."""
    w = np.empty(len(eq))
    prev = TARGET
    e, b, rs = eq.fillna(0).values, bd.fillna(0).values, np.asarray(reset, dtype=bool)
    for i in range(len(w)):
        num = prev * (1 + e[i])
        cur = num / (num + (1 - prev) * (1 + b[i]))
        w[i] = cur
        prev = TARGET if rs[i] else cur
    return pd.Series(w, index=eq.index)


def threshold_signal(eq, bd, bands=np.arange(0.0, 0.0251, 0.001)):
    """Average over bands of (pre-trade weight - target). A fund with band d trades at the
    close where the breach is observed."""
    out = []
    for d in bands:
        w = np.empty(len(eq))
        prev = TARGET
        e, b = eq.fillna(0).values, bd.fillna(0).values
        for i in range(len(w)):
            num = prev * (1 + e[i])
            cur = num / (num + (1 - prev) * (1 + b[i]))
            w[i] = cur
            prev = TARGET if abs(cur - TARGET) >= d else cur
        out.append(w - TARGET)
    return pd.Series(np.mean(out, axis=0), index=eq.index)


def month_position(index):
    """(days_left, is_last): sessions remaining in the month after t (0 on the last session),
    from the observed index. The last, possibly incomplete, month is judged by the NYSE
    calendar so the sample end is not mistaken for a month-end."""
    from pandas.tseries.offsets import CustomBusinessDay
    from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr, USPresidentsDay,
                                        GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay, nearest_workday)

    def _ny(d):
        return d + pd.Timedelta(days=1) if d.weekday() == 6 else d

    class NYSE(AbstractHolidayCalendar):
        rules = [Holiday("NewYear", month=1, day=1, observance=_ny), USMartinLutherKingJr, USPresidentsDay,
                 GoodFriday, USMemorialDay,
                 Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
                 Holiday("Independence", month=7, day=4, observance=nearest_workday), USLaborDay,
                 USThanksgivingDay, Holiday("Christmas", month=12, day=25, observance=nearest_workday)]

    index = pd.DatetimeIndex(index)
    fut = pd.date_range(index[-1] + pd.Timedelta(days=1), periods=40, freq=CustomBusinessDay(calendar=NYSE()))
    cal = index.append(fut)
    s = pd.Series(np.arange(len(cal)), index=cal)
    left = s.groupby(cal.to_period("M")).transform("max") - s
    return left.reindex(index)


def calendar_signal(eq, bd):
    left = month_position(eq.index)
    return drift_weight(eq, bd, (left == 0).values) - TARGET, left


def sharpe(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(ANN) if len(r) > 50 and r.std() > 0 else np.nan


def nw_t(y, x, lags=5):
    """Slope and Newey-West t of y on x (with intercept)."""
    df = pd.concat([y, x], axis=1).dropna()
    if len(df) < 60:
        return np.nan, np.nan, len(df)
    yy, xx = df.iloc[:, 0].values, df.iloc[:, 1].values
    X = np.column_stack([np.ones(len(xx)), xx])
    beta = np.linalg.lstsq(X, yy, rcond=None)[0]
    u = yy - X @ beta
    xu = X * u[:, None]
    S = xu.T @ xu
    for L in range(1, lags + 1):
        g = xu[L:].T @ xu[:-L]
        S += (1 - L / (lags + 1)) * (g + g.T)
    XtXi = np.linalg.inv(X.T @ X)
    V = XtXi @ S @ XtXi
    return beta[1], beta[1] / np.sqrt(V[1, 1]), len(df)
