"""cot-positioning -- contrarian CFTC positioning on the seven G10 majors vs USD.

Signal. For each of EUR GBP JPY AUD CAD CHF NZD and each of three trader groups -- legacy
non-commercials, TFF leveraged funds, TFF asset managers -- take the group's net long in the
CME currency future as a share of open interest, on the weekly report (as-of Tuesday) grid:
    leg_level = -z(net share)            z over the trailing `win` reports
    leg_chg   = -z(net share - net share `dh` reports ago)
Six legs, equal-weighted (mean). Contrarian: fade crowded and freshly-built positioning.

Book. Each =X row takes the latest report released strictly before its 00:00 UTC stamp
(releases: Friday 15:30 ET, the following Monday in US-holiday weeks, backlog dates after
the 2013 / 2018-19 / 2025 shutdowns -- see fetch_cot_fx._avail). On the first =X row of
each ISO week the signal is demeaned across the 7 currencies (so the book is exactly
USD-neutral), scaled to sum|w| = 1, and multiplied by a vol-target scalar
    k = min(gross_cap, vol_target / EWMA-vol(unit book daily return, halflife 126))
estimated from the unit book's own past returns and re-set only at the weekly rebalance.
Weights are held until the next week's first row.

Conventions. `px` holds the seven =X closes (row D = the 00:00 UTC quote on D). Returned
weights are in TICKER space: EURUSD=X, GBPUSD=X, AUDUSD=X, NZDUSD=X carry the currency
weight; USDJPY=X, USDCAD=X, USDCHF=X carry minus it. Row D's weight is held from row D's
close to row D+1's close -- the bar the sim book fills and charges on.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from fetch_cot_fx import net_share, on_fx_rows, report_avail  # noqa: E402

CCYS = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
TICKER = {"EUR": ("EURUSD=X", 1), "GBP": ("GBPUSD=X", 1), "JPY": ("USDJPY=X", -1),
          "AUD": ("AUDUSD=X", 1), "CAD": ("USDCAD=X", -1), "CHF": ("USDCHF=X", -1),
          "NZD": ("NZDUSD=X", 1)}
TICKERS = [TICKER[c][0] for c in CCYS]
DEFAULTS = dict(win=156, dh=4, minp=52, vol_target=0.05, vol_halflife=126, vol_minp=60,
                gross_cap=3.0, groups=(("legacy", "nc"), ("tff", "lev"), ("tff", "am")))
ANN = 252.0


def _z(x, win, minp):
    return (x - x.rolling(win, min_periods=minp).mean()) / x.rolling(win, min_periods=minp).std()


def signal(cot_legacy: pd.DataFrame, cot_tff: pd.DataFrame, **kw) -> pd.DataFrame:
    """Composite contrarian signal on the report (as-of date) grid, columns CCYS."""
    p = {**DEFAULTS, **kw}
    src = {"legacy": cot_legacy, "tff": cot_tff}
    legs = []
    for rep, grp in p["groups"]:
        ns = net_share(src[rep], grp).reindex(columns=CCYS)
        legs.append(-_z(ns, p["win"], p["minp"]))
        legs.append(-_z(ns.diff(p["dh"]), p["win"], p["minp"]))
    ix = sorted(set().union(*[l.index for l in legs]))
    legs = [l.reindex(ix).ffill() for l in legs]
    return sum(legs) / len(legs)


def target_weights(px: pd.DataFrame, cot_legacy: pd.DataFrame, cot_tff: pd.DataFrame,
                   **kw) -> pd.DataFrame:
    """Ticker-space target weights on px's index (see module docstring)."""
    p = {**DEFAULTS, **kw}
    px = px[TICKERS].sort_index().ffill()
    moved = px.pct_change().abs().sum(axis=1) > 0          # drop no-quote rows (holidays)
    moved.iloc[0] = True
    pxm = px[moved]
    idx = pxm.index
    avail = pd.concat([report_avail(cot_legacy), report_avail(cot_tff)]).groupby(level=0).max()
    sig = on_fx_rows(signal(cot_legacy, cot_tff, **p), idx, avail)

    s = sig[CCYS].sub(sig[CCYS].mean(axis=1), axis=0)
    unit = s.div(s.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    rows = pd.Series(idx, index=idx)
    first = rows.groupby(idx.to_period("W-SUN")).transform("min").eq(rows).values
    unit = unit[first].reindex(idx).ffill().fillna(0.0)

    tick = lambda Wc: pd.DataFrame({TICKER[c][0]: TICKER[c][1] * Wc[c] for c in CCYS})[TICKERS]
    ret = pxm.pct_change().fillna(0.0)
    g = (tick(unit).shift(1).fillna(0.0) * ret).sum(axis=1)
    vol = g.ewm(halflife=p["vol_halflife"], min_periods=p["vol_minp"]).std() * np.sqrt(ANN)
    k = (p["vol_target"] / vol).clip(upper=p["gross_cap"])
    k = pd.Series(np.where(first, k, np.nan), index=idx).ffill().fillna(0.0)
    W = tick(unit.mul(k, axis=0))
    return W.reindex(px.index).ffill().fillna(0.0)


def load_inputs(refresh: bool = False):
    """Convenience loader for research and the live runner: (px, cot_legacy, cot_tff).
    refresh=True pulls fresh =X closes and this year's CFTC files."""
    sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
    from research_lib import load_series
    from fetch_cot_fx import fetch_legacy, fetch_tff, refresh_current_year
    if refresh:
        refresh_current_year()
    px = pd.DataFrame({t: load_series(t, cache=not refresh)["Close"] for t in TICKERS})
    return px, fetch_legacy(), fetch_tff()


if __name__ == "__main__":
    px, lg, tf = load_inputs()
    W = target_weights(px, lg, tf)
    print(W.tail(8).round(3))
    print("gross", W.abs().sum(axis=1).tail(1).round(3).iloc[0])
