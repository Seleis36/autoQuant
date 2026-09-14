"""term-structure-carry -- reference rule for VIXY (short/flat), NOT a passing strategy.

Rule: short VIXY (ProShares VIX Short-Term Futures ETF) with weight -`size` when the VIX term
structure is in contango (VIX3M / VIX > `threshold`), flat otherwise. Weight set at close t is
held from close t to close t+1.

Research result (past_research/vol-complex/term-structure-carry/): net Sharpe ~0.8 full sample
2011-2026 @5bp/side (0.88 IS 2011-18 / 0.70 OOS 2019-26), MaxDD -63%, return skew -1.3.
It does NOT meet the "Sharpe >= 1.5" criterion and nothing tried (~140 variants) did. This
module exists so the next researcher can import the baseline rather than re-derive it.

Timing caveat: the VIX / VIX3M closes are 16:15 ET while VIXY's close is 16:00 ET, so a
same-day signal has 15 minutes of look-ahead on days the slope crosses the threshold. Use
`lag=1` for a strictly knowable signal (Sharpe drops to ~0.6).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def target_weight(vixy_close: pd.Series, vix: pd.Series, vix3m: pd.Series,
                  threshold: float = 1.0, size: float = 1.0, lag: int = 0) -> pd.Series:
    """Target weight in VIXY (negative = short) to hold from close_t to close_{t+1}.

    vixy_close : daily VIXY closes (only the index is used, for alignment).
    vix, vix3m : daily ^VIX and ^VIX3M closes (yfinance), tz-naive DatetimeIndex.
    threshold  : contango threshold on VIX3M / VIX.
    size       : gross weight when short (max leverage 1.0 validated).
    lag        : extra days of signal lag (1 = strictly knowable before the fill).
    """
    idx = pd.DatetimeIndex(vixy_close.index).sort_values()
    slope = (vix3m.reindex(idx).ffill() / vix.reindex(idx).ffill())
    w = pd.Series(np.where(slope > threshold, -size, 0.0), index=idx)
    if lag:
        w = w.shift(lag).fillna(0.0)
    return w
