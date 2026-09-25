"""Calendar features for US equity flow effects, all known ex-ante (before the close of
the day that sets the weight for the next day).

  tdom      trading day of month relative to month end: last trading day = -1, first
            trading day of the new month = +1 (so the turn of the month is -1..+3)
  fomc_day  offset in trading days from the most recent scheduled FOMC statement day
            (0 = statement day) -- CMVJ (2019) FOMC-cycle weeks are built from this
  pre_hol   True on the last trading day before a weekday market holiday

The trading calendar is SPY's own (1993+), extended past the last bar with NYSE-like
business days so the *next* day's features are defined on the last bar.
"""
import os
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
UNSCHEDULED = pd.to_datetime(["1998-10-15", "2001-01-03", "2001-04-18", "2001-09-17",
                              "2008-01-22", "2008-10-08", "2020-03-03", "2020-03-15"])


def fomc_dates(scheduled_only=True):
    d = pd.to_datetime(pd.read_csv(os.path.join(_HERE, "fomc_snapshot.csv"))["date"])
    if scheduled_only:
        d = d[~d.isin(UNSCHEDULED)]
    return pd.DatetimeIndex(sorted(set(d)))


def features(idx):
    idx = pd.DatetimeIndex(idx)
    s = pd.Series(idx, index=idx)
    per = idx.to_period("M")
    pos_from_end = s.groupby(per).cumcount(ascending=False) + 1          # 1 = last day
    pos_from_start = s.groupby(per).cumcount() + 1                        # 1 = first day
    tdom = pd.Series(np.where(pos_from_start <= 10, pos_from_start, -pos_from_end), index=idx)
    # the final (incomplete) month: last bar is not necessarily month end -> mark with calendar
    last = idx[-1]
    if last.to_period("M") == per[-1]:
        bdays = pd.bdate_range(last, last + pd.offsets.MonthEnd(0))
        n_left = len(bdays) - 1
        m = per == per[-1]
        tdom[m] = np.where(pos_from_start[m] <= 10, pos_from_start[m], -(pos_from_end[m] + n_left))
    # FOMC offsets (trading days since last scheduled statement day, which counts as 0)
    f = fomc_dates()
    pos = np.searchsorted(idx.values, f.values)                         # statement day or next trading day
    fpos = np.full(len(idx), np.nan)
    j = 0
    k = np.array(sorted(set(p for p in pos if p < len(idx))))
    for i in range(len(idx)):
        while j + 1 < len(k) and k[j + 1] <= i:
            j += 1
        if len(k) and k[j] <= i:
            fpos[i] = i - k[j]
    # days to next FOMC (for pre-FOMC): -1 = the trading day before
    nxt = np.full(len(idx), np.nan)
    for p in k:
        for dlt in range(1, 6):
            if p - dlt >= 0:
                nxt[p - dlt] = -dlt if np.isnan(nxt[p - dlt]) else nxt[p - dlt]
    # pre-holiday: next business day (Mon-Fri) is not a trading day
    nb = idx + pd.offsets.BDay(1)
    nxt_trade = pd.Series(idx[1:].append(pd.DatetimeIndex([nb[-1]])), index=idx)
    pre_hol = pd.Series(nxt_trade.values > nb.values, index=idx)
    return pd.DataFrame({"tdom": tdom, "fomc_off": fpos, "to_fomc": nxt, "pre_hol": pre_hol}, index=idx)


def next_day_features(idx):
    """Features of the NEXT trading day, aligned on day t (what the weight set at t earns)."""
    f = features(idx)
    return f.shift(-1)
