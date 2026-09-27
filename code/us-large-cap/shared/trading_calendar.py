"""NYSE month-end sessions for us-large-cap strategies (a copy of
code/global-equity-etf/shared/trading_calendar.py, kept inside this asset class so that an edit
there cannot move a us-large-cap book).

History uses the data's own index. Only *future* trading days (is tomorrow in a new month?)
need a calendar, which comes from this list of NYSE full-day closures. The list **must be
extended each year** (source: nyse.com/markets/hours-calendars); past its last year, only
weekends are skipped.
"""
import pandas as pd

NYSE_HOLIDAYS = pd.DatetimeIndex(pd.to_datetime([
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"]))


def future_trading_days(after, n=10):
    """The next n NYSE sessions strictly after `after`."""
    out, d = [], pd.Timestamp(after).normalize()
    while len(out) < n:
        d += pd.Timedelta(days=1)
        if d.weekday() < 5 and d not in NYSE_HOLIDAYS:
            out.append(d)
    return pd.DatetimeIndex(out)


def month_end_sessions(index):
    """Sessions in `index` whose next session is in a different month (the last trading day
    of each month). The final date is judged by the calendar, not the data, so a partially
    observed month never looks finished."""
    index = pd.DatetimeIndex(index)
    nxt = index[1:].append(future_trading_days(index[-1], 1))
    return index[(nxt.month != index.month) | (nxt.year != index.year)]
