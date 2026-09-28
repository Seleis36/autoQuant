"""perp-crowding — contrarian retail positioning on Binance BTCUSDT perps, traded on spot BTC.

Status: Working (see past_research/spot-btc/perp-crowding/). Long/flat, unlevered, daily.

Mechanism: Binance's "global long/short account ratio" is the number of accounts net long
BTCUSDT perps divided by the number net short -- a head count of the retail crowd. When the
crowd is more long than it has usually been, BTC underperforms over the next 1-3 days; when
it is less long (retail fading a move or capitulated), BTC outperforms. The sleeve holds spot
BTC only while the crowd is below its own historical median, sized by inverse volatility.

Conventions (lookahead-safe):
    * `close`: daily BTCUSDT closes, index = bar OPEN date (UTC, tz-naive): bar D covers
      [D 00:00, D+1 00:00). The weight at index D is decided at D+1 00:00 UTC and held over
      bar D+1 (research_lib.backtest shifts by one bar).
    * `ls_ratio`: the 5-minute global long/short ACCOUNT ratio, indexed by the archive's
      `create_time` (data.binance.vision `metrics` column `count_long_short_ratio`). The REST
      endpoint `fapi /futures/data/globalLongShortAccountRatio` stamps the same value ~5 min
      later. For bar D the last snapshot stamped strictly before D+1 00:00 - cutoff_hours is
      used (22:55 with the default 1 h), so a live runner has it well before the close.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def crowd_level(ls_ratio: pd.Series, index: pd.DatetimeIndex, cutoff_hours: float = 1.0) -> pd.Series:
    """log(global L/S account ratio) as known `cutoff_hours` before each daily close."""
    s = ls_ratio[ls_ratio > 0].sort_index()
    s.index = s.index + pd.Timedelta(hours=cutoff_hours)       # usable only cutoff_hours after its stamp
    d = np.log(s).resample("1D", label="left", closed="left").last()
    return d.reindex(index)


def expanding_rank(x: pd.Series, min_history: int = 180) -> pd.Series:
    """Percentile of x_t among all PRIOR non-missing values, in [0, 1)."""
    xv = x.dropna()
    r = xv.expanding(min_periods=min_history).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    return r.reindex(x.index)


def target_weight(
    close: pd.Series,
    ls_ratio: pd.Series,
    cutoff_hours: float = 1.0,
    min_history: int = 180,
    threshold: float = 0.5,
    vol_target: float = 0.40,
    vol_halflife: int = 20,
    cap: float = 1.0,
    trend_sma: int | None = None,
) -> pd.Series:
    """Long/flat target weight for spot BTC, one value per daily bar.

    Parameters
    ----------
    close : daily BTCUSDT closes (bar-open index, UTC). Traded series.
    ls_ratio : 5-minute global long/short account ratio (create_time index, UTC).
    cutoff_hours : only snapshots at least this long before the daily close are used.
    min_history : daily observations required before the expanding rank is defined (flat before).
    threshold : hold BTC while the crowd's expanding percentile rank is below this.
    vol_target, vol_halflife, cap : inverse-EWMA-vol sizing (annualised with sqrt(365)), capped.
    trend_sma : optional extra gate close > SMA(trend_sma) (variant P2 uses 50); None = P1.

    Returns
    -------
    pd.Series aligned to `close.index`, values in [0, cap]; w[D] is held from close_D to close_{D+1}.
    """
    close = close.sort_index()
    lvl = crowd_level(ls_ratio, close.index, cutoff_hours)
    rk = expanding_rank(lvl, min_history)
    on = (rk < threshold).astype(float).where(rk.notna(), 0.0)
    r = close.pct_change()
    ewv = r.ewm(halflife=vol_halflife, min_periods=vol_halflife).std() * np.sqrt(365.0)
    size = (vol_target / ewv).clip(lower=0.0, upper=cap).fillna(0.0)
    w = on * size
    if trend_sma:
        w = w * (close > close.rolling(trend_sma).mean()).astype(float)
    return w.fillna(0.0)
