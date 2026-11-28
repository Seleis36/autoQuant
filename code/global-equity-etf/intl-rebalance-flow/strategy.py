"""intl-rebalance-flow -- last-session US-vs-international rebalancing pressure (EFA vs SPY).

Mechanism: target-date, balanced and global funds hold US and international equity in fixed
proportions and rebalance at month-end. After the US out-ran international over the month,
the rebalance sells US equity at the month-end close: on the LAST session of the month SPY
under-performs EFA in proportion to the month-to-date gap, and it reverses the next session.

Book (daily closes, SPY calendar, everything known at the close of t):
  1. beta_t = rolling 252d (min 126) beta of EFA on SPY; hedged spread h = r_EFA - beta_{t-1} r_SPY.
  2. Z_t = month-to-date sum of (r_SPY - r_EFA) since the previous month-end close, divided by
     (252d std of h, min 126) x sqrt(sessions so far).
  3. If session t+1 is the last session of its month (NYSE calendar for the live edge):
        pos_t = clip(Z_t, -2, 2) / 2 * SCALE;  w_EFA = pos_t, w_SPY = -pos_t * beta_t
     else 0. One session a month in the market; no carry-over.

`target_weights(close)` -> DataFrame of target weights for EFA and SPY known at the close of t,
applied to t+1's return. `close` must contain EFA and SPY.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from trading_calendar import month_end_sessions, next_session_days_left  # noqa: E402

LEG = "EFA"
BENCH = "SPY"
SCALE = 2.0            # EFA weight at |Z| >= CLIP (SPY hedge ~ -beta x that)
CLIP = 2.0
BETA_WIN, BETA_MINP = 252, 126
VOL_WIN, VOL_MINP = 252, 126
COLUMNS = [LEG, BENCH]


def signal(close, leg=LEG, bench=BENCH):
    r = close[[leg, bench]].pct_change()
    x, y = r[bench], r[leg]
    beta = y.rolling(BETA_WIN, min_periods=BETA_MINP).cov(x) / x.rolling(BETA_WIN, min_periods=BETA_MINP).var()
    h = y - beta.shift(1) * x
    vol = h.rolling(VOL_WIN, min_periods=VOL_MINP).std()
    idx = close.index
    me = pd.Series(idx.isin(month_end_sessions(idx)), index=idx)
    grp = me.shift(1, fill_value=False).astype(int).cumsum()
    rel = (x - y)
    cum = rel.fillna(0.0).groupby(grp.values).cumsum()
    n = rel.notna().astype(int).groupby(grp.values).cumsum()
    z = (cum / (vol * np.sqrt(n.clip(lower=1)))).where(n >= 1)
    return z, beta


def target_weights(close, scale=SCALE, clip=CLIP):
    close = close.sort_index()
    z, beta = signal(close)
    active = next_session_days_left(close.index) == 0
    pos = (z.clip(-clip, clip) / clip * scale).where(active, 0.0).fillna(0.0)
    w = pd.DataFrame({LEG: pos, BENCH: -pos * beta.fillna(1.0)}, index=close.index)
    return w[COLUMNS]
