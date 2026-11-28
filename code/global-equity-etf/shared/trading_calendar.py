"""NYSE trading calendar for the live edge of month-end / event-window strategies.

History uses the data's own index. Only *future* trading days (is tomorrow in a new month? is
the FOMC statement 1 or 2 sessions away?) need a calendar. That comes from this list of NYSE
full-day closures, which **must be extended each year** (source: nyse.com/markets/hours-calendars).
Past the list's last year, only weekends are skipped.
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


def next_session_days_left(index, n_future=30):
    """For each session t in `index`: how many sessions remain in the month AFTER the next
    session t+1 (0 = t+1 is the last session of its month). The next session of the final
    date, and the month-end status of every date, come from the NYSE calendar, so a partially
    observed month never looks finished. Added 2026-11 for the month-end flow sleeves."""
    index = pd.DatetimeIndex(index)
    cal = index.append(future_trading_days(index[-1], n_future))
    nxt = cal[1:]
    is_me = (nxt.month != cal[:-1].month) | (nxt.year != cal[:-1].year)
    import numpy as np
    me = np.append(is_me, False)                       # last calendar entry: unknown, unused
    # sessions left after each calendar day = count of sessions until the next month-end flag
    left = np.zeros(len(cal), dtype=int)
    k = 0
    for i in range(len(cal) - 1, -1, -1):
        if me[i]:
            k = 0
        left[i] = k
        k += 1
    return pd.Series(left[1:len(index) + 1], index=index)
