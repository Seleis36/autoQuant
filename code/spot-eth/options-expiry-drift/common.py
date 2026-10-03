"""Event calendar and price lookups for options-expiry-drift.

Deribit ETH options settle at 08:00 UTC against the 30-minute TWAP of the index (07:30-08:00).
Every Friday is a weekly expiry; the LAST Friday of a month is the monthly expiry and, in
Mar/Jun/Sep/Dec, the quarterly one -- where most open interest sits. The calendar is a pure
function of the date, so nothing here can look ahead.

Sample starts 2020-01-01 (Deribit ETH options had negligible open interest before 2020); the
start was fixed before any return was computed.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "spot-eth", "shared"))
import evalkit as ek  # noqa: E402
from ethdata import load_bars  # noqa: E402

START = "2020-01-01"
IS_END, OOS_START = "2023-12-31 23:59:59", "2024-01-01"
EXPIRY_HOUR = 8


def price_at(symbol="ETHUSDT", start="2019-12-01"):
    """Series p with p[t] = last trade price at time t (close of the 1m bar that ends at t)."""
    c = load_bars(symbol, "1m", start=start)["Close"]
    c.index = c.index + pd.Timedelta(minutes=1)
    return c


def expiries(end, start=START):
    """All Friday 08:00 UTC expiries with their class: 'quarterly', 'monthly' or 'weekly'."""
    # Classify against whole calendar months: generate Fridays past `end` so that the last Friday
    # of a month cut short by the sample end is not mistaken for a month-end expiry.
    fr = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(days=35), freq="W-FRI") + pd.Timedelta(hours=EXPIRY_HOUR)
    last = pd.Series(fr, index=fr).groupby([fr.year, fr.month]).transform("max").to_numpy() == fr.to_numpy()
    kind = np.where(last & np.isin(fr.month, (3, 6, 9, 12)), "quarterly", np.where(last, "monthly", "weekly"))
    out = pd.Series(kind, index=fr, name="kind")
    return out[out.index <= pd.Timestamp(end)]


def placebo_times(end, start=START, weekday=1):
    """Same clock time on another weekday (default Tuesday) -- daily expiries only, tiny open interest."""
    d = pd.date_range(start, end, freq="D")
    return d[d.weekday == weekday] + pd.Timedelta(hours=EXPIRY_HOUR)


def window_ret(p, times, a, b):
    """Log return of p from t+a to t+b for each event time t (a, b are Timedeltas); NaN if missing."""
    t0 = pd.DatetimeIndex(times) + a
    t1 = pd.DatetimeIndex(times) + b
    p0 = p.reindex(t0, method="ffill", tolerance=pd.Timedelta(minutes=30)).to_numpy()
    p1 = p.reindex(t1, method="ffill", tolerance=pd.Timedelta(minutes=30)).to_numpy()
    return pd.Series(np.log(p1 / p0), index=pd.DatetimeIndex(times))
