"""fomc-global-beta -- the FOMC global equity premium on the country-ETF basket (sleeve).

Brusa, Savor & Wilson (2020) and Lucca & Moench (2015): equity markets worldwide earn a large
premium in the 24h before and on scheduled FOMC statement days. Book: long the equal-weight
basket of the available country ETFs over the statement day (0) and the trading day before (-1),
i.e. from the close of day -2 to the close of day 0; flat otherwise (~6 % of days).

Standalone Sharpe 0.45 net (IS 0.45 / OOS 0.51). Too small to deploy alone; used as a sleeve
in `global-etf-sleeve-blend`.

`target_weights(close)` -> daily weights (fraction of equity) for the 9 country ETFs, known at the
close of day t, applied to day t+1's return. Future trading days (for the live edge) come from
`shared/trading_calendar.py`; history uses the close index itself.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from trading_calendar import future_trading_days  # noqa: E402

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
_HERE = os.path.dirname(os.path.abspath(__file__))
# unscheduled (intermeeting) actions were not known in advance -> excluded
UNSCHEDULED = pd.to_datetime(["1998-10-15", "2001-01-03", "2001-04-18", "2001-09-17",
                              "2008-01-22", "2008-10-08", "2020-03-03", "2020-03-15"])
OFFSETS = (-1, 0)       # trading-day offsets from the statement day whose returns are earned
GROSS = 1.0


def fomc_dates(path=os.path.join(_HERE, "fomc_snapshot.csv")):
    d = pd.to_datetime(pd.read_csv(path)["date"])
    d = d[~d.isin(UNSCHEDULED)]
    return pd.DatetimeIndex(sorted(set(d)))


def window_mask(index, offsets=OFFSETS, dates=None):
    """True at close t when day t+1's return falls in an FOMC window."""
    index = pd.DatetimeIndex(index)
    dates = fomc_dates() if dates is None else dates
    fut = future_trading_days(index[-1], 10)
    cal = index.append(fut)
    on = np.zeros(len(index), dtype=bool)
    for S in dates:
        if S < cal[0] or S > cal[-1]:
            continue
        i = cal.searchsorted(S)            # statement day's position (always a trading day)
        for k in offsets:
            j = i + k - 1                  # weight set at the close before the earned day
            if 0 <= j < len(index):
                on[j] = True
    return pd.Series(on, index=index)


def target_weights(close, offsets=OFFSETS, gross=GROSS, names=COUNTRIES):
    close = close[names]
    on = window_mask(close.index, offsets)
    avail = close.notna()
    w = avail.astype(float).div(avail.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return w.mul(on.astype(float), axis=0) * gross
