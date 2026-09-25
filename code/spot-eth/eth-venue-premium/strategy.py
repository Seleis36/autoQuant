"""eth-venue-premium — reusable signal for spot ETH (long/flat, unlevered, hourly).

Mechanism: the price of ETH on a USD venue (Coinbase ETH-USD) relative to Binance ETHUSDT. When the
USD-venue premium is high against its trailing 30-day distribution, ETH returns over the next 1-24 h
are higher on both venues. The spot-btc study showed the information sits in the Binance-USDT leg
(USDT/USD demand), and the ETH and BTC premium states agree ~91% of the time. A hysteresis state
machine turns the z-score into a low-turnover long/flat state; a 50-day trend filter and an
inverse-vol scalar size it. Parameters are the spot-btc/coinbase-premium spec, unchanged
(pre-registered replication; see past_research/spot-eth/eth-venue-premium/).

Bar convention (lookahead-safe):
    * inputs are hourly closes indexed by bar OPEN time (UTC, tz-naive), e.g. Binance klines and
      Coinbase candles; the bar stamped t covers [t, t+1h);
    * the weight at index t uses data up to and including the close of bar t (known at t+1h) and is
      the weight to hold over bar t+1 (close_t -> close_{t+1}).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HOURS_PER_YEAR = 365 * 24


def premium_zscore(binance_close: pd.Series, coinbase_close: pd.Series, z_window: int = 720) -> pd.Series:
    """USD-venue premium (coinbase/binance - 1), z-scored over its trailing `z_window` observed bars."""
    idx = binance_close.index.intersection(coinbase_close.index)
    prem = (coinbase_close.reindex(idx) / binance_close.reindex(idx) - 1.0).dropna()
    z = (prem - prem.rolling(z_window).mean()) / prem.rolling(z_window).std()
    return z.reindex(binance_close.index)


def hysteresis_state(z: pd.Series, enter: float = 0.0, exit_: float = -1.5) -> pd.Series:
    """1.0 once z rises above `enter`, back to 0.0 once z falls below `exit_`; NaN keeps the state."""
    zv = z.to_numpy(dtype=float)
    out = np.zeros(len(zv))
    s = 0.0
    for i, v in enumerate(zv):
        if not np.isnan(v):
            if s == 0.0 and v > enter:
                s = 1.0
            elif s == 1.0 and v < exit_:
                s = 0.0
        out[i] = s
    return pd.Series(out, index=z.index)


def target_weight(
    binance_close: pd.Series,
    coinbase_close: pd.Series,
    z_window: int = 720,
    enter: float = 0.0,
    exit_: float = -1.5,
    trend_hours: int = 50 * 24,
    vol_target: float = 0.40,
    vol_halflife: int = 20 * 24,
    cap: float = 1.0,
) -> pd.Series:
    """Long/flat target weight for spot ETH on hourly bars.

    Parameters
    ----------
    binance_close : hourly Binance ETHUSDT closes (index = bar open time, UTC, tz-naive). Traded series.
    coinbase_close : hourly Coinbase ETH-USD closes on the same convention.
    z_window : trailing window (bars) of the premium z-score (720 = 30 days).
    enter, exit_ : hysteresis thresholds on the z-score.
    trend_hours : SMA length (bars) of the trend filter (1200 = 50 days).
    vol_target : annualised vol target of the inverse-vol scalar.
    vol_halflife : EWMA half-life (bars) of the realised-vol estimator (480 = 20 days).
    cap : ceiling on the weight (1.0 = no leverage).

    Returns
    -------
    pd.Series aligned to `binance_close.index`, values in [0, cap]; w[t] is the weight to hold from
    close_t to close_{t+1}. Needs >= trend_hours bars of history (and >= z_window premium bars).
    """
    px = binance_close.sort_index()
    z = premium_zscore(px, coinbase_close.sort_index(), z_window)
    state = hysteresis_state(z, enter, exit_)
    trend = (px > px.rolling(trend_hours).mean()).astype(float)
    ret = px.pct_change()
    ewv = ret.ewm(halflife=vol_halflife, min_periods=vol_halflife).std() * np.sqrt(HOURS_PER_YEAR)
    scale = (vol_target / ewv).clip(lower=0.0, upper=cap).fillna(0.0)
    return (state * trend * scale).fillna(0.0)
