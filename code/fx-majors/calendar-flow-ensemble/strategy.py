"""calendar-flow-ensemble -- target weights for a G10 FX basket vs USD from calendar/flow effects.

Sleeves (all pre-specified on economic grounds, see the report):
  1. month_end   : month-end equity-rebalancing flow. Short USD (long basket) when SPY is up
                   month-to-date, over the last 3 sessions of the month, scaled by MTD/3%.
  2. fomc        : short USD over the session containing a scheduled FOMC announcement.
  3. year_end    : short USD over the last 5 sessions of the calendar year.
  4. cross_rev   : 60-day z-score mean reversion on 9 G10 crosses, dollar-neutral.
  5. season      : calendar-month seasonality of the basket, sign estimated leave-one-year-out
                   from *past* years only (expanding), so it is out-of-sample at every date.

Conventions (verified against hourly data, see screens/probe_timing2.py):
  * `fx` is a DataFrame of USD-per-unit prices for EUR GBP JPY AUD CAD CHF NZD, indexed by the
    yfinance row stamp D. Row D closes at 00:00 UTC on D and covers UTC calendar day D-1
    (the row stamped Monday covers Friday's session).
  * `macro` holds US-close series (SPY, TLT) stamped on their trading day. The close stamped
    D-1 (20:00/21:00 UTC) is known before FX row D closes, so weights at row D use macro
    rows stamped <= D-1. Nothing stamped D is used.
  * The returned weight at row D is the target held from row D's close to row D+1's close.
    Positive weight = long the foreign currency / short USD.
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from fomc_dates import fomc_days  # noqa: E402

CCYS = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
CROSSES = [("AUD", "NZD"), ("EUR", "CHF"), ("EUR", "GBP"), ("AUD", "CAD"), ("NZD", "CAD"),
           ("CAD", "CHF"), ("GBP", "CHF"), ("EUR", "JPY"), ("AUD", "JPY")]
DEFAULTS = dict(me_sessions=3, me_scale=0.03, ye_sessions=5, cross_win=60, cross_scale=2.0,
                season_min_years=3, vol_halflife=20, vol_target=0.04, max_gross=1.5,
                sleeve_weights={"month_end": 1.0, "fomc": 1.0, "year_end": 1.0, "cross_rev": 1.0, "season": 1.0})


def _session(idx: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(idx - pd.tseries.offsets.BDay(1), index=idx)


def _basket(sig: pd.Series, idx, cols=CCYS) -> pd.DataFrame:
    return pd.DataFrame(np.repeat(np.asarray(sig, dtype=float)[:, None] / len(cols), len(cols), axis=1), index=idx, columns=cols)


def sleeve_weights(fx: pd.DataFrame, macro: pd.DataFrame, **kw) -> dict:
    p = {**DEFAULTS, **kw}
    fx = fx[CCYS].dropna().sort_index()
    r = np.log(fx).diff()
    alive = r.abs().sum(axis=1) > 0
    fx, r = fx[alive], r[alive].fillna(0.0)
    idx = fx.index
    sess = _session(idx)
    smon = sess.dt.to_period("M")
    macL = macro.reindex(idx.union(macro.index)).ffill().shift(1).reindex(idx)  # stamped <= D-1
    out = {}
    # 1. month-end equity rebalancing
    s_from_end = sess.groupby(smon).cumcount(ascending=False)          # 0 => session is last bday of month
    gate = (s_from_end.shift(-1) < p["me_sessions"]).astype(float)     # next row's session is in the last k
    mtd = np.log(macL["SPY"] / macL["SPY"].groupby(smon).transform("first"))
    out["month_end"] = _basket((mtd / p["me_scale"]).clip(-1, 1).fillna(0) * gate, idx)
    # 2. FOMC: announcement 14:00 ET on F sits inside row F+1 -> weight at row F
    fd = fomc_days(); tgt = pd.Series(0.0, index=idx); tgt[idx.isin(fd)] = 1.0
    out["fomc"] = _basket(tgt, idx)
    # 3. year-end: last 5 sessions of the calendar year
    y_from_end = sess.groupby(sess.dt.year).cumcount(ascending=False)
    out["year_end"] = _basket((y_from_end.shift(-1) < p["ye_sessions"]).astype(float), idx)
    # 4. cross mean reversion
    lp = np.log(fx); W = pd.DataFrame(0.0, index=idx, columns=CCYS)
    for a, b in CROSSES:
        s = lp[a] - lp[b]; z = (s - s.rolling(p["cross_win"]).mean()) / s.rolling(p["cross_win"]).std()
        w = (-z / p["cross_scale"]).clip(-1, 1).fillna(0) / len(CROSSES)
        W[a] += w / 2; W[b] -= w / 2
    out["cross_rev"] = W
    # 5. expanding leave-past-years-in calendar-month seasonality of the basket (past years only)
    bask = r.mean(axis=1); smonth = sess.dt.month; syear = sess.dt.year
    sig = pd.Series(0.0, index=idx)
    for y in sorted(syear.unique()):
        past = syear < y
        if past.sum() < p["season_min_years"] * 250:
            continue
        mbym = bask[past].groupby(smonth[past]).mean()
        sig[syear == y] = smonth[syear == y].map(np.sign(mbym)).fillna(0).values
    out["season"] = _basket(sig.shift(-1).fillna(0), idx)   # next row's session month
    return out


def target_weights(fx: pd.DataFrame, macro: pd.DataFrame, **kw) -> pd.DataFrame:
    """Combined target weights (columns CCYS). Each sleeve is scaled to equal ex-ante vol
    (EWMA of the sleeve's own realised return), summed, then vol-targeted and gross-capped."""
    p = {**DEFAULTS, **kw}
    sl = sleeve_weights(fx, macro, **kw)
    fx = fx[CCYS].dropna().sort_index(); r = np.log(fx).diff()
    alive = r.abs().sum(axis=1) > 0; r = r[alive].fillna(0.0); idx = r.index
    total = pd.DataFrame(0.0, index=idx, columns=CCYS)
    for k, W in sl.items():
        W = W.reindex(idx).fillna(0.0)
        ret = (W.shift(1) * r).sum(axis=1)
        v = ret.ewm(halflife=p["vol_halflife"] * 5, min_periods=60).std() * np.sqrt(252)
        v = v.clip(lower=0.005)
        total += W.mul((0.02 / v).fillna(0).clip(upper=20), axis=0) * p["sleeve_weights"].get(k, 1.0)
    pret = (total.shift(1) * r).sum(axis=1)
    pv = (pret.ewm(halflife=p["vol_halflife"] * 5, min_periods=60).std() * np.sqrt(252)).clip(lower=0.005)
    total = total.mul((p["vol_target"] / pv).fillna(0).clip(upper=10), axis=0)
    g = total.abs().sum(axis=1); scale = (p["max_gross"] / g).clip(upper=1.0).fillna(1.0)
    return total.mul(scale, axis=0).fillna(0.0)
