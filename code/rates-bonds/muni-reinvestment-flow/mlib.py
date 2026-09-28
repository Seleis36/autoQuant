"""Helpers shared by the muni-reinvestment-flow scripts."""
import numpy as np
import pandas as pd


def hedged_premium(y, x):
    """y - b0 x_t - b1 x_{t-1}, betas from a trailing 252-day OLS, lagged one day."""
    Z = pd.concat([y, x, x.shift(1)], axis=1, keys=["y", "a", "b"]).dropna()
    m = Z.rolling(252, min_periods=126).cov()
    Saa, Sbb, Sab = m.xs("a", level=1)["a"], m.xs("b", level=1)["b"], m.xs("a", level=1)["b"]
    Sya, Syb = m.xs("a", level=1)["y"], m.xs("b", level=1)["y"]
    det = Saa * Sbb - Sab ** 2
    b0 = ((Sya * Sbb - Syb * Sab) / det).shift(1)
    b1 = ((Syb * Saa - Sya * Sab) / det).shift(1)
    return (Z.y - b0 * Z.a - b1 * Z.b).dropna()


def trading_day_of_month(idx):
    s = pd.Series(np.arange(len(idx)), index=idx)
    return s - s.groupby(idx.to_period("M")).transform("min") + 1


def D_series(y, x, n=5):
    """Per month: sum of hedged premium over trading days 1..n minus n x mean over the rest."""
    p = hedged_premium(y, x)
    day = trading_day_of_month(p.index)
    per = p.index.to_period("M")
    first = p[day <= n].groupby(per[day <= n]).sum()
    rest = p[day > n].groupby(per[day > n]).mean() * n
    return (first - rest).dropna(), p, day
