"""treasury-flow-calendar -- deployable strategy for TLT (long/short, unlevered).

Three calendar legs, each a documented flow effect in the Treasury market:

  * month-end  (+1): long over the last 3 trading days of each month
                     (index duration extension / insurer window dressing; Hartley & Schwarz 2019)
  * FOMC       (+1): long the trading day before and the day of each FOMC statement
  * pre-auction(-1): short the 2 trading days before each 10y and 20y note/bond auction
                     (dealer concession; Lou, Yan & Zhang 2013)

target_weight(t) = clip(month_end_t + fomc_t + pre_auction_t, -1, 1) is the weight to hold
FROM the close of day t TO the close of day t+1. A leg is "on" at t when day t+1 is one of
its days, so every leg needs to know the *next* trading days -- which is why this module
carries a NYSE holiday calendar: at the last close of the month we must already know that
tomorrow is the first day of the next month, not the last of this one.

Every calendar used is published in advance (Fed: one year ahead; Treasury: tentative
quarterly schedule, firm announcement ~1 week ahead; NYSE holidays: years ahead), so the
signal is knowable at the close it is set on.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay,
                                    USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "calendar_snapshots")


class NYSECalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("NewYear", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


def _load_dates(name: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(pd.read_csv(os.path.join(SNAP, f"{name}.csv"))["date"]))


def default_fomc_dates() -> pd.DatetimeIndex:
    return _load_dates("fomc")


def default_auction_dates(tenors=("10y", "20y")) -> pd.DatetimeIndex:
    a = pd.read_csv(os.path.join(SNAP, "auctions.csv"), parse_dates=["auction_date"])
    return pd.DatetimeIndex(sorted(a.loc[a.tenor.isin(tenors), "auction_date"].unique()))


def trading_calendar(index: pd.DatetimeIndex, horizon_days: int = 40) -> pd.DatetimeIndex:
    """Observed trading days in `index`, extended forward by NYSE business days.

    The observed part is authoritative (it is what actually traded); the extension only
    exists so the last few bars can see the days that follow them.
    """
    index = pd.DatetimeIndex(index).sort_values()
    cbd = CustomBusinessDay(calendar=NYSECalendar())
    future = pd.date_range(index[-1] + pd.Timedelta(days=1), periods=horizon_days, freq=cbd)
    return index.append(future)


def _flag_next_day(cal: pd.DatetimeIndex, days: pd.DatetimeIndex) -> pd.Series:
    """1.0 on trading day t when t+1 (the next trading day in `cal`) is in `days`."""
    nxt = pd.Series(cal[1:], index=cal[:-1])                  # t -> t+1
    return nxt.isin(pd.DatetimeIndex(days)).astype(float)


def month_end_days(cal: pd.DatetimeIndex, n_days: int = 3) -> pd.DatetimeIndex:
    s = pd.Series(cal, index=cal)
    rank_from_end = s.groupby(cal.to_period("M")).cumcount(ascending=False)
    return cal[rank_from_end.values < n_days]


def event_offset_days(cal: pd.DatetimeIndex, events, offsets) -> pd.DatetimeIndex:
    """Trading days at the given offsets (in trading days) from each event date."""
    ev = pd.DatetimeIndex(sorted(set(pd.to_datetime(events))))
    ev = ev[(ev >= cal[0]) & (ev <= cal[-1])]
    p0 = cal.searchsorted(ev)                                 # first trading day >= event
    out = [cal[p + k] for p in p0 for k in offsets if 0 <= p + k < len(cal)]
    return pd.DatetimeIndex(sorted(set(out)))


def target_weight(
    close: pd.Series,
    fomc_dates=None,
    auction_dates=None,
    month_end_n: int = 3,
    fomc_before: int = 1,
    auction_before: int = 2,
    cap: float = 1.0,
) -> pd.Series:
    """Target weight in TLT to hold from close_t to close_{t+1}, in [-cap, cap].

    Parameters
    ----------
    close : daily TLT closes (tz-naive DatetimeIndex). Only the index is used; the value
        series is accepted so the interface matches the other strategies in this repo.
    fomc_dates : FOMC statement dates. Default: committed snapshot (through 2027-12).
    auction_dates : 10y and 20y auction dates (reopenings included). Default: committed
        snapshot; refresh with `calendars.refresh()` for dates past the snapshot.
    month_end_n : long the last `month_end_n` trading days of each month.
    fomc_before : long this many days before the FOMC statement day, plus the day itself.
    auction_before : short this many trading days before each auction.
    cap : absolute cap on the netted weight.
    """
    fomc = default_fomc_dates() if fomc_dates is None else pd.DatetimeIndex(pd.to_datetime(fomc_dates))
    auc = default_auction_dates() if auction_dates is None else pd.DatetimeIndex(pd.to_datetime(auction_dates))

    idx = pd.DatetimeIndex(close.index).sort_values()
    cal = trading_calendar(idx)

    me = _flag_next_day(cal, month_end_days(cal, month_end_n))
    fo = _flag_next_day(cal, event_offset_days(cal, fomc, list(range(-fomc_before, 1))))
    pa = _flag_next_day(cal, event_offset_days(cal, auc, list(range(-auction_before, 0))))

    w = (me + fo - pa).clip(-cap, cap)
    return w.reindex(idx).fillna(0.0)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(HERE, "../../shared"))
    import research_lib as rl
    c = rl.load_series("TLT")["Close"]
    w = target_weight(c)
    print(w.tail(15))
    print("exposure share:", (w != 0).mean().round(3), " long:", (w > 0).mean().round(3), " short:", (w < 0).mean().round(3))
