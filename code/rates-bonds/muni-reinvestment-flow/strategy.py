"""muni-reinvestment-flow -- deployable strategy: long municipal bonds vs Treasuries over the
first five trading days of every month.

Mechanism. Municipal bonds pay most coupons and principal redemptions on the 1st of the month
(largest on Jan 1 / Jun 1 / Jul 1 / Dec 1). Muni funds, ETFs and separately managed accounts
reinvest that cash in the first days of the month, while new-issue supply is not timed to
it, so munis outperform duration-matched Treasuries at the start of the month. Measured on
muni fund NAVs, the first-five-day excess is absent in the 1990s, +6.5 bp/month (t 2.5) in
2000-07, +12.5 bp (t 2.6) in 2008-16 and +13.7 bp (t 4.6) in 2017-26. On traded ETF prices it
is visible from 2017 (t 4-7), weak in 2008-16.

Book. Four muni ETFs, equal notional 1/4 each (total muni notional `scale`):
    MUB, TFI, ITM  each hedged with  -beta x IEF
    SHM            hedged with       -beta x SHY
beta = trailing `beta_window`-day OLS beta of the muni ETF's daily return on its hedge's,
estimated on returns up to and including the decision close. Position is set at the close of
the LAST trading day of month m-1 and held through the close of trading day `n_days` of
month m; flat otherwise (so 5 of ~21 sessions a month are held, ~24 % exposure).

Calendar. "Is the next session trading day 1..n of a month?" needs the future session list
at the live edge. The observed index is authoritative for history; it is extended forward
with an NYSE holiday calendar (pandas rules; one-off closures such as national days of
mourning are not in the rules -- an unexpected closure only shifts the window by a day).

Conventions. Inputs are daily closes (US close, tz-naive). The returned weight on row t is the
target held from close t to close t+1 -- the bar the sim book fills and charges on.
Weights are in notional units per 1 unit of book capital.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay,
                                    USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay

PAIRS = {"MUB": "IEF", "TFI": "IEF", "ITM": "IEF", "SHM": "SHY"}
TICKERS = ["MUB", "TFI", "ITM", "SHM", "IEF", "SHY"]
DEFAULTS = dict(n_days=5, beta_window=252, beta_minp=126, scale=1.0, pairs=PAIRS)


def _new_year_observance(d):
    """NYSE: New Year's Day on a Sunday is observed Monday; on a Saturday it is NOT observed on
    the preceding Friday (e.g. Fri 2021-12-31 was a trading day). pandas' nearest_workday would
    close that Friday."""
    return d + pd.Timedelta(days=1) if d.weekday() == 6 else d


class NYSECalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("NewYear", month=1, day=1, observance=_new_year_observance),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


def trading_calendar(index: pd.DatetimeIndex, horizon_days: int = 40) -> pd.DatetimeIndex:
    """Observed sessions, extended forward by NYSE business days (for the live edge)."""
    index = pd.DatetimeIndex(index).sort_values()
    cbd = CustomBusinessDay(calendar=NYSECalendar())
    future = pd.date_range(index[-1] + pd.Timedelta(days=1), periods=horizon_days, freq=cbd)
    return index.append(future)


def hold_flags(index: pd.DatetimeIndex, n_days: int = 5) -> pd.Series:
    """1.0 on session t when session t+1 is one of the first `n_days` sessions of its month."""
    cal = trading_calendar(index)
    s = pd.Series(np.arange(len(cal)), index=cal)
    day = s - s.groupby(cal.to_period("M")).transform("min") + 1
    nxt_day = pd.Series(day.values[1:], index=cal[:-1])
    return (nxt_day <= n_days).astype(float).reindex(pd.DatetimeIndex(index)).fillna(0.0)


def target_weights(close: pd.DataFrame, **kw) -> pd.DataFrame:
    """Target weights (date x ticker) for the muni month-start book.

    close : daily closes (adjusted for distributions) with at least the columns in TICKERS.
    """
    p = {**DEFAULTS, **kw}
    pairs = p["pairs"]
    idx = pd.DatetimeIndex(close.index).sort_values()
    close = close.reindex(idx)
    r = close.pct_change()
    flag = hold_flags(idx, p["n_days"])
    cols = sorted(set(pairs) | set(pairs.values()))
    w = pd.DataFrame(0.0, index=idx, columns=cols)
    unit = p["scale"] / len(pairs)
    for m, h in pairs.items():
        beta = (r[m].rolling(p["beta_window"], min_periods=p["beta_minp"]).cov(r[h])
                / r[h].rolling(p["beta_window"], min_periods=p["beta_minp"]).var())
        ok = flag.astype(bool) & beta.notna() & close[m].notna() & close[h].notna()
        w.loc[ok, m] += unit
        w.loc[ok, h] -= unit * beta[ok]
    return w


if __name__ == "__main__":
    import os
    import sys
    HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(HERE, "..", "shared"))
    from rb_data import etf_close
    px = etf_close(TICKERS)
    w = target_weights(px)
    print(w.tail(12).round(3))
    print("share of sessions with a position:", (w.abs().sum(axis=1) > 0).mean().round(3))
