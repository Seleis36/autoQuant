"""weekday-trend — deployable strategy for spot BTC.

Signal is 100% lookahead-safe:
    * everything is computed on data up to and including close of day t;
    * the returned target weight for day t is the weight to hold FROM close
      of t TO close of t+1 (i.e. it earns r_{t+1});
    * the day-of-week filter zeroes the weight when day t+1 is a Thursday.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def target_weight(
    close: pd.Series,
    trend_win: int = 200,
    momentum_win: int = 20,
    vol_target: float = 0.40,
    vol_halflife: int = 20,
    cap: float = 1.5,
    skip_dow: tuple[int, ...] = (3,),
) -> pd.Series:
    """Return the long-only target weight series for spot BTC/USD.

    Parameters
    ----------
    close : daily BTC closes (any timezone-naive index). Only Close is used.
    trend_win : SMA lookback for the trend filter (days).
    momentum_win : lookback for the sign(return) momentum filter (days).
    vol_target : annualised vol target used as sizing scalar numerator.
    vol_halflife : EWMA half-life (days) for the realised-vol estimator.
    cap : cap on the vol-scalar. 1.5 => max 1.5x notional.
    skip_dow : tuple of day-of-week integers (0=Mon .. 6=Sun) on which the
        strategy must be flat. The default (3,) is Thursday.

    Returns
    -------
    pd.Series aligned to `close.index`, values in [0, cap]. Weight at index t
    should be applied to the return from close_t to close_{t+1}.
    """
    close = close.sort_index()
    ret = close.pct_change()

    trend = (close > close.rolling(trend_win).mean()).astype(float)
    mom = (close.pct_change(momentum_win) > 0).astype(float)

    ewv = ret.ewm(halflife=vol_halflife, min_periods=vol_halflife).std() * np.sqrt(365.0)
    scale = (vol_target / ewv).clip(lower=0.0, upper=cap).fillna(0.0)

    next_dow = (close.index + pd.Timedelta(days=1)).dayofweek
    gate = pd.Series(
        [0.0 if d in skip_dow else 1.0 for d in next_dow],
        index=close.index,
    )

    return (trend * mom * scale * gate).fillna(0.0)
