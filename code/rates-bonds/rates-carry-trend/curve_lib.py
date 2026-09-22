"""Synthetic constant-maturity Treasury total returns from CMT par yields.

Why synthesise at all: the tradable ETFs (SHY/IEF/TLT) only start in 2002 and only
have deep, liquid history from ~2010. CMT yields go back to 1976 and are never
revised, so a signal can be *designed* on 1990-2009 -- a period in which the
instruments this strategy trades did not exist -- and then tested on the ETF era.

Daily total return of a par bond held one day, at constant maturity n:

    r_t = y_{t-1}/252                      carry (accrual)
          - D(y_{t-1}, n) * dy             duration
          + 0.5 * C(y_{t-1}, n) * dy^2     convexity

with y in decimals, dy = y_t - y_{t-1}, and D, C the closed-form modified duration
and convexity of a par bond with semiannual coupons.
"""
import os, sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from fetch_fred_daily import fred  # noqa: E402

M = 2.0  # semiannual coupons
CMT = {2: "DGS2", 5: "DGS5", 10: "DGS10", 20: "DGS20", 30: "DGS30", 1: "DGS1", 0.25: "DGS3MO"}


def par_duration(y, n, m=M):
    """Modified duration of a par bond, y decimal annual, n years."""
    y = np.maximum(np.asarray(y, dtype=float), 1e-4)
    return (1.0 - (1.0 + y / m) ** (-n * m)) / y


def par_convexity(y, n, m=M):
    y = np.maximum(np.asarray(y, dtype=float), 1e-4)
    a = (1.0 + y / m)
    return (2.0 / y ** 2) * (1.0 - a ** (-n * m)) - (2.0 * n) / (y * a ** (n * m + 1))


def yields(maturities=(0.25, 1, 2, 5, 10, 20, 30), start="1976-01-01"):
    df = pd.DataFrame({n: fred(CMT[n]) for n in maturities}).sort_index()
    df = df.loc[start:] / 100.0            # decimals
    return df.ffill(limit=5).dropna(how="any")


def total_returns(y, maturities=(2, 5, 10, 30)):
    """Daily synthetic total return per constant-maturity point."""
    out = {}
    for n in maturities:
        yy = y[n]
        dy = yy.diff()
        D = pd.Series(par_duration(yy.shift(1), n), index=yy.index)
        C = pd.Series(par_convexity(yy.shift(1), n), index=yy.index)
        out[n] = yy.shift(1) / 252.0 - D * dy + 0.5 * C * dy ** 2
    return pd.DataFrame(out).dropna(how="all")


def excess_returns(tr, y, cash=0.25):
    """Total return minus the daily accrual on cash -- what a funded position earns."""
    return tr.sub(y[cash].shift(1) / 252.0, axis=0)


def carry(y, maturities=(2, 5, 10, 30), cash=0.25):
    """Yield pickup over cash plus one-year roll-down, per year, in decimals.

        carry_n = (y_n - y_cash) + D_n * (y_n - y_{n-1y}) / 1y

    The roll point is the next-shorter *quoted* CMT tenor, scaled to a 1-year roll,
    which is the standard desk approximation and needs no curve interpolation model.
    """
    roll_pt = {2: 1, 5: 2, 10: 5, 30: 20}
    out = {}
    for n in maturities:
        rp = roll_pt[n]
        D = pd.Series(par_duration(y[n], n), index=y.index)
        out[n] = (y[n] - y[cash]) + D * (y[n] - y[rp]) / float(n - rp)
    return pd.DataFrame(out)
