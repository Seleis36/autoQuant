"""muni-treasury-lead-lag -- research book (NOT a deployable strategy: the idea is filed as
Failed, see the report). Municipal bond ETFs follow Treasuries with a lag; hold the catch-up,
hedged.

Mechanism. Municipal bonds trade by appointment and are marked from evaluated prices that
absorb a Treasury move over several days. Muni ETF prices inherit part of that lag: their
return over the next one to three sessions loads positively on the Treasury return of the
last few (lag-1 beta 0.07-0.20, lag-2 0.04-0.13, against 0.25-0.50 on the same day; LQD shows
none). After a Treasury rally the muni ETFs are still to catch up, so the book is long them
and short the duration it carries; after a sell-off the reverse.

Signal (at the close of day t)
    z      = (IEF return over the last `k` sessions) / (trailing 250-session daily vol x sqrt(k))
    pos    = clip(z, -1, 1)                      # +1 after a 1-sigma Treasury rally
Book (weights per unit of capital)
    each muni ETF with a beta: pos x scale / n
    IEF: -(sum of muni weights x their trailing 250-session beta to IEF)
Row t of the returned frame is the weight held from close t to close t+1 and uses closes up
to and including t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MUNI = ["MUB", "TFI", "ITM", "SHM", "SUB", "PZA", "HYD", "VTEB"]
HEDGE = "IEF"
TICKERS = MUNI + [HEDGE]
DEFAULTS = dict(k=3, vol_window=250, beta_window=250, minp=120, scale=1.0, munis=tuple(MUNI))


def target_weights(close: pd.DataFrame, **kw) -> pd.DataFrame:
    """close: daily closes adjusted for distributions, columns including TICKERS."""
    p = {**DEFAULTS, **kw}
    munis = [m for m in p["munis"] if m in close.columns]
    idx = pd.DatetimeIndex(close.index).sort_values()
    close = close.reindex(idx)
    ret = close.pct_change(fill_method=None)
    ief = ret[HEDGE]
    vol = ief.rolling(p["vol_window"], min_periods=p["minp"]).std()
    z = ief.rolling(p["k"]).sum() / (vol * np.sqrt(p["k"]))
    pos = z.clip(-1, 1)
    beta = pd.DataFrame({m: ret[m].rolling(p["beta_window"], min_periods=p["minp"]).cov(ief)
                         / ief.rolling(p["beta_window"], min_periods=p["minp"]).var() for m in munis})
    live = close[munis].notna() & beta.notna()
    n = live.sum(axis=1).replace(0, np.nan)
    w = live.astype(float).div(n, axis=0).mul(pos * p["scale"], axis=0).fillna(0.0)
    w[HEDGE] = -(w[munis] * beta.fillna(0.0)).sum(axis=1)
    return w.where(pos.notna(), 0.0).fillna(0.0)


if __name__ == "__main__":
    import os
    import sys
    HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(HERE, "..", "shared"))
    from rb_data import etf_close
    px = etf_close(TICKERS)
    w = target_weights(px)
    print(w.tail(8).round(3).to_string())
    print("avg gross %.2f  max gross %.2f" % (w.loc["2010":].abs().sum(axis=1).mean(), w.abs().sum(axis=1).max()))
