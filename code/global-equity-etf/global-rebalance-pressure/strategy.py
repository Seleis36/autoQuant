"""global-rebalance-pressure -- month-end stock/bond rebalancing pressure on global equities.

Mechanism (Harvey, Mazzoleni & Melone 2025): balanced, pension and target-date funds that hold
stocks and bonds in fixed proportions rebalance on the calendar. After stocks out-run bonds
over the month they must sell equities into the month-end, and they buy after stocks lag.
Since 1995 the pressure sits in the last four sessions of the month, in SPY and in the
US-listed international ETFs alike.

Book (daily closes, SPY calendar, everything known at the close of t):
  1. Z_t = sum over the sessions since the previous month-end close of (r_SPY - r_IEF), divided
     by (252d std of the daily difference, min 126) x sqrt(sessions so far).
  2. If session t+1 is one of the last 4 of its month (NYSE calendar for the live edge):
        position_t = -clip(Z_t, -2, 2) / 2 * GROSS   (short equities when stocks are overweight)
     else 0. Position applies to a fixed global mix: 0.6 SPY + 0.4 EFA.
  3. Weights are re-set every close inside the window (Z updates daily) and are flat
     outside it (~19 % of sessions).

`target_weights(close)` -> DataFrame of target weights (fraction of equity) for SPY and EFA,
known at the close of t, applied to t+1's return (fill at the close the signal is computed on).
`close` must contain SPY, EFA and IEF.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from trading_calendar import month_end_sessions, next_session_days_left  # noqa: E402

EQUITY = "SPY"
BOND = "IEF"
MIX = {"SPY": 0.6, "EFA": 0.4}
WINDOW = (3, 2, 1, 0)          # sessions left in the month after the earned session
CLIP = 2.0
GROSS = 1.0                    # gross exposure at |Z| >= CLIP
VOL_WIN, VOL_MINP = 252, 126
COLUMNS = list(MIX)


def drift_z(close, equity=EQUITY, bond=BOND, vol_win=VOL_WIN, vol_minp=VOL_MINP):
    """Calendar-fund stock-minus-bond drift since the previous month-end close, z-scored."""
    r = close[[equity, bond]].pct_change()
    d = r[equity] - r[bond]
    idx = close.index
    me = pd.Series(idx.isin(month_end_sessions(idx)), index=idx)
    grp = me.shift(1, fill_value=False).astype(int).cumsum()
    cum = d.fillna(0.0).groupby(grp.values).cumsum()
    n = d.notna().astype(int).groupby(grp.values).cumsum()
    vol = d.rolling(vol_win, min_periods=vol_minp).std()
    return (cum / (vol * np.sqrt(n.clip(lower=1)))).where(n >= 1)


def target_weights(close, window=WINDOW, clip=CLIP, gross=GROSS, mix=MIX):
    close = close.sort_index()
    z = drift_z(close)
    active = next_session_days_left(close.index).isin(window)
    pos = (-z.clip(-clip, clip) / clip * gross).where(active, 0.0).fillna(0.0)
    return pd.DataFrame({k: pos * v for k, v in mix.items()}, index=close.index)[list(mix)]
