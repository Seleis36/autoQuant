"""Earnings-date helpers built on data/SP500_earnings_dates.parquet (from fetch_earnings.py).

    from earnings import load_earnings, reaction_day_matrix
    E = load_earnings()                       # ticker, date, hour, eps fields
    R = reaction_day_matrix(E, index, cols)   # bool: is this bar the first close reflecting the print

Timing: Yahoo stamps announcements 16:00 ET for after-close (AMC) and 06:00-09:00 ET for
before-open (BMO). BMO -> reaction bar is the announcement day itself; AMC -> next trading
day. Unknown hour (10:00-15:59) is treated as during-session -> same day.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR

PATH = os.path.join(DATA_DIR, "SP500_earnings_dates.parquet")


def load_earnings():
    E = pd.read_parquet(PATH)
    E["date"] = pd.to_datetime(E["date"])
    E = E[E.date >= "2009-06-01"].drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"])
    E["amc"] = E["hour"] >= 16
    return E.reset_index(drop=True)


def reaction_day_matrix(E, index, cols, validate_gap_days=45):
    """bool DataFrame[index x cols]: bar t is the reaction bar of an announcement.
    Announcements closer than `validate_gap_days` to the previous one for the same ticker
    are dropped (Yahoo duplicates / restated dates)."""
    index = pd.DatetimeIndex(index)
    R = pd.DataFrame(False, index=index, columns=cols)
    pos = pd.Series(np.arange(len(index)), index=index)
    E = E[E.ticker.isin(cols)].copy()
    E["gap"] = E.groupby("ticker")["date"].diff().dt.days
    E = E[(E.gap.isna()) | (E.gap >= validate_gap_days)]
    # map announcement calendar day -> first trading day >= date (BMO) or > date (AMC)
    i_ge = index.searchsorted(E["date"].values, side="left")     # first bar >= date
    i_gt = index.searchsorted(E["date"].values, side="right")    # first bar > date
    i = np.where(E["amc"].values, i_gt, i_ge)
    ok = i < len(index)
    for t, k in zip(E["ticker"].values[ok], i[ok]):
        R.iat[k, R.columns.get_loc(t)] = True
    return R


def window_matrix(R, before=0, after=0):
    """bool: bar t is within [-before, +after] trading bars of a reaction bar."""
    W = R.copy().astype(int)
    for k in range(1, before + 1):
        W = W + R.shift(-k, fill_value=False).astype(int)
    for k in range(1, after + 1):
        W = W + R.shift(k, fill_value=False).astype(int)
    return W > 0
