"""options-expiry-drift — short ETH over the eight hours before the month-end Deribit expiry.

Mechanism: Deribit ETH (and BTC) options settle at 08:00 UTC against the 30-minute TWAP of the
index. The last Friday of each month is the monthly/quarterly expiry, where open interest is
concentrated. In the hours before it ETH falls on average (-50 bp 2020-23, -70 bp 2024-26 over
00:00-08:00 UTC, against +10 / +25 bp on other Fridays and +27 bp on last Fridays before listed
options had open interest), consistent with hedge unwinds / pinning ahead of settlement. The
sleeve is short 1x over that window and flat otherwise. See
past_research/spot-eth/options-expiry-drift/.

Needs a short leg -> simulated book (the spot testnet is long/flat only).

Bar convention (lookahead-safe, same as the other spot-eth hourly sleeves):
    * `close`: hourly Binance ETHUSDT closes indexed by bar OPEN time (UTC, tz-naive); the bar
      stamped t covers [t, t+1h);
    * the weight at index t is the weight to hold over bar t+1 (close_t -> close_{t+1}), i.e. it
      is acted on at time t+1h. The calendar is a pure function of the timestamp.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_ORD = {"first": 0, "second": 1, "third": 2}


def expiry_fridays(index: pd.DatetimeIndex, which: str = "last") -> pd.DatetimeIndex:
    """Midnights (UTC) of the chosen Friday of every month spanned by `index` (plus one month)."""
    start = index.min().normalize() - pd.Timedelta(days=7)
    end = index.max().normalize() + pd.Timedelta(days=45)
    fr = pd.date_range(start, end, freq="W-FRI")
    s = pd.Series(fr, index=fr)
    g = s.groupby([fr.year, fr.month])
    if which == "last":
        return pd.DatetimeIndex(g.max().to_numpy())
    return pd.DatetimeIndex(g.nth(_ORD[which]).to_numpy())


def target_weight(
    close: pd.Series,
    entry_hour: int = 0,
    exit_hour: int = 8,
    size: float = -1.0,
    which: str = "last",
) -> pd.Series:
    """Target weight for ETH on hourly bars: `size` (default -1 = short 1x) from `entry_hour` to
    `exit_hour` UTC on the last Friday of each month, 0 otherwise.

    Parameters
    ----------
    close : hourly ETHUSDT closes (index = bar open time, UTC, tz-naive). Only the index is used.
    entry_hour : hour (UTC) on the expiry Friday at which the position is opened; may be negative
        (e.g. -4 = Thursday 20:00). 0 = Friday 00:00.
    exit_hour : hour (UTC) on the expiry Friday at which it is closed (8 = the 08:00 settlement).
    size : weight held in the window (-1.0 = short one times equity).
    which : 'last' (the monthly / quarterly expiry) -- 'first' / 'second' / 'third' are placebos.

    Returns
    -------
    pd.Series aligned to `close.index`; w[t] is held over the bar stamped t+1h. To be short over
    [Fri 00:00, Fri 08:00) the weight is non-zero on the bars stamped Thu 23:00 ... Fri 06:00.
    """
    idx = pd.DatetimeIndex(close.index)
    if idx.tz is not None:                           # a live feed may hand over tz-aware UTC stamps
        idx = idx.tz_convert("UTC").tz_localize(None)
    w = np.zeros(len(idx))
    held = idx + pd.Timedelta(hours=1)               # the bar over which w[t] is held starts here
    for f in expiry_fridays(idx, which):
        a, b = f + pd.Timedelta(hours=entry_hour), f + pd.Timedelta(hours=exit_hour)
        w[(held >= a) & (held < b)] = size
    return pd.Series(w, index=close.index)
