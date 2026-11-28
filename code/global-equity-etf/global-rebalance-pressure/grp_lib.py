"""global-rebalance-pressure -- month-end stock/bond rebalancing pressure on global equities.

Harvey, Mazzoleni & Melone (2025, NBER w33554): funds that hold stocks and bonds in fixed
proportions and rebalance on the calendar must SELL equities at month-end after stocks
out-ran bonds over the month (and buy after they lagged). The selling is predictable from
public prices, and it depresses equity returns over the last sessions of the month.

Signal at close t (calendar fund): Z_t = sum of daily (r_EQ - r_BOND) from the session after
the previous month-end through t, divided by (trailing 252d std of that daily difference x
sqrt(n sessions)).  Z > 0: stocks overweight -> expect equities DOWN into the month-end close.

Data
* ETF era (2002-08 ->): SPY (equity drift), IEF (10y bond drift); traded: SPY, EFA, the
  9-country basket.
* Backcast (1962 -> 1998, untouched by any choice): S&P 500 price index and a synthetic 10y
  constant-maturity total return from FRED DGS10 (par-bond duration). DGS10 is a ~15:30 ET
  mark, the S&P closes 16:00 -> the bond leg of the signal is 30 min stale, which can only
  blur the signal, never front-run the traded equity return.
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
import data as D  # noqa: E402
import research_lib as rl  # noqa: E402

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
SPL = {"FULL": ("2002-08-01", "2026-12-31"), "IS": ("2002-08-01", "2012-12-31"),
       "OOS": ("2013-01-01", "2026-12-31")}
BACK = {"1962-79": ("1962-03-01", "1979-12-31"), "1980-98": ("1980-01-01", "1998-12-31"),
        "1962-98": ("1962-03-01", "1998-12-31")}


def load_etf(start="2001-06-01"):
    C = D.load_panel(COUNTRIES + ["EFA", "EEM", "ACWI", "SPY", "IEF", "TLT"], "Close", start=start)
    R = C.pct_change()
    avail = R[COUNTRIES].notna().sum(axis=1)
    R["BASKET"] = R[COUNTRIES].mean(axis=1).where(avail >= 2)
    R["GLOBAL"] = 0.6 * R["SPY"] + 0.4 * R["EFA"]
    return C, R


def _read_close(name):
    df = pd.read_parquet(os.path.join(rl.DATA_DIR, name))
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df["Close"][~df.index.duplicated(keep="last")].sort_index()


def sp500_long():
    parts = [_read_close("IDX_GSPC_d_long.parquet"), _read_close("IDX_GSPC_d_pre2010.parquet"),
             _read_close("IDX_GSPC_d.parquet")]
    s = pd.concat(parts)
    return s[~s.index.duplicated(keep="last")].sort_index()


def syn10_returns():
    """Daily total return of a 10y par bond re-struck each day at the DGS10 yield."""
    y = D.load_fred("DGS10") / 100.0
    y = y[~y.index.duplicated()].sort_index()
    y0 = y.shift(1)
    c = y0 / 2.0
    n = 20
    # price of yesterday's par bond (coupon y0) at today's yield, minus 1, plus carry
    yt = y / 2.0
    price = c / yt * (1 - (1 + yt) ** -n) + (1 + yt) ** -n
    dt = y.index.to_series().diff().dt.days.fillna(1)
    carry = y0 * dt / 365.0
    return (price - 1 + carry).dropna()


def load_back():
    eq = sp500_long().pct_change()
    bd = syn10_returns()
    idx = eq.index.intersection(bd.index)
    return pd.DataFrame({"EQ": eq.reindex(idx), "BD": bd.reindex(idx)}).dropna()


def month_end_flags(index):
    """Research: True on the last session of each month in the data index."""
    idx = pd.DatetimeIndex(index)
    per = idx.to_period("M")
    pos = pd.Series(np.arange(len(idx)), index=idx)
    return pd.Series(pos.values == pos.groupby(per).transform("max").values, index=idx)


def days_left(index, month_end=None):
    """Sessions remaining in the month after t (0 on the last session)."""
    idx = pd.DatetimeIndex(index)
    me = month_end_flags(idx) if month_end is None else month_end
    grp = me[::-1].cumsum()[::-1]           # same id for sessions up to and including each month-end
    pos = pd.Series(np.arange(len(idx)), index=idx)
    last = pos.groupby(grp.values).transform("max")
    return (last - pos).astype(int)


def drift_z(r_eq, r_bd, month_end=None, vol_win=252, minp=126):
    """Calendar-fund drift through close t since the previous month-end close, z-scored."""
    d = (r_eq - r_bd)
    idx = d.index
    me = month_end_flags(idx) if month_end is None else month_end.reindex(idx).fillna(False)
    grp = me.shift(1).fillna(False).astype(int).cumsum()      # new group starts after a month-end
    cum = d.fillna(0.0).groupby(grp.values).cumsum()
    n = d.notna().astype(int).groupby(grp.values).cumsum()
    vol = d.rolling(vol_win, min_periods=minp).std()
    return (cum / (vol * np.sqrt(n.clip(lower=1)))).where(n >= 1)


def slope_t(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x)[ok], np.asarray(y)[ok]
    if len(x) < 20:
        return np.nan, np.nan
    X = x - x.mean()
    b = (X * y).sum() / (X ** 2).sum()
    res = y - y.mean() - b * X
    return b * 1e4, b / np.sqrt((res ** 2).sum() / (len(y) - 2) / (X ** 2).sum())
