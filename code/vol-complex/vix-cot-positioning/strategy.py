"""vix-cot-positioning -- short VIXY in contango, gated by CFTC VIX-futures positioning.

Rule (all parameters defaulted to the alpha spec, alphas/vol-complex/vix-cot-positioning/spec.md):

  * From the weekly CFTC Traders-in-Financial-Futures report for VIX futures (code 1170E1)
    compute, per report, the asset-manager net share  am = (AM long - AM short) / OI  and the
    leveraged-fund net share  lev = (LF long - LF short) / OI.
  * Five positioning scores on the report grid: z-scores of am over 52 / 104 / 156 reports,
    and (z(am) - z(lev)) / 2 over 104 / 156 reports (min periods = 2/3 of the window).
  * Map each report to session rows only once public (release Friday 15:30 ET -> first used at
    Monday's close; holiday / shutdown weeks later, see fetch_cot_vix._avail).
  * contango_t = VIX3M / VIX at the close of t-1 > 1   (one-day lag: the index closes at 16:15 ET,
    after the 16:00 ETP fill).
  * weight_t = - mean over the 25 (score, theta) pairs, theta in {-0.5, 0, 0.25, 0.5, 1.0},
    of 1[contango_t and score_t > theta].    -> weight in [-1, 0], i.e. short VIXY 0..100 %.

The weight set at close t is held from close t to close t+1. Idea: asset managers in VIX futures
are dominated by the long-vol and inverse-vol ETP sponsors, so the net share is a crowding gauge of
retail vol-ETP positioning. When it is high relative to its own history (the crowd holds long-vol
insurance, typically after a spike) the short-vol premium is rich; when it is low (inverse-vol
products crowded, e.g. Jan-2018, Jul-2024) short vol is crowded and the strategy stands aside.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))

THRESHOLDS = (-0.5, 0.0, 0.25, 0.5, 1.0)
AM_WINDOWS = (52, 104, 156)
COMP_WINDOWS = (104, 156)


def _z(x: pd.Series, win: int) -> pd.Series:
    m = int(win * 0.67)
    return (x - x.rolling(win, min_periods=m).mean()) / x.rolling(win, min_periods=m).std()


def positioning_scores(tff: pd.DataFrame) -> pd.DataFrame:
    """tff: rows of data/CFTC_COT_tff_vix_w.parquet (columns date, oi, am_long, am_short,
    lev_long, lev_short, avail_utc). Returns the 5 scores indexed by report as-of date."""
    t = tff.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    am = (t["am_long"] - t["am_short"]) / t["oi"]
    lev = (t["lev_long"] - t["lev_short"]) / t["oi"]
    out = {f"am_z{w}": _z(am, w) for w in AM_WINDOWS}
    for w in COMP_WINDOWS:
        out[f"comp_z{w}"] = (_z(am, w) - _z(lev, w)) / 2
    return pd.DataFrame(out)


def scores_on_sessions(tff: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Positioning scores as known at each session close (release-lagged)."""
    from fetch_cot_vix import on_session_rows
    t = tff.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    return on_session_rows(positioning_scores(tff), pd.DatetimeIndex(idx), t["avail_utc"])


def target_weight(vixy_close: pd.Series, vix: pd.Series, vix3m: pd.Series, tff: pd.DataFrame,
                  thresholds=THRESHOLDS, slope_threshold: float = 1.0, slope_lag: int = 1,
                  size: float = 1.0) -> pd.Series:
    """Target weight in VIXY (negative = short), to hold from close_t to close_{t+1}.

    vixy_close  : VIXY daily closes (only the index is used).
    vix, vix3m  : ^VIX and ^VIX3M daily closes (yfinance), tz-naive session-date index.
    tff         : the VIX-futures TFF table (code/vol-complex/shared/fetch_cot_vix.fetch_tff()).
    slope_lag   : sessions of lag on VIX3M/VIX (1 = strictly known before the 16:00 fill).
    size        : gross short at full signal (1.0 = the validated maximum).
    """
    idx = pd.DatetimeIndex(vixy_close.index).sort_values()
    slope = vix3m.reindex(idx).ffill() / vix.reindex(idx).ffill()
    cont = (slope.shift(slope_lag) > slope_threshold).to_numpy()
    S = scores_on_sessions(tff, idx)
    votes = [cont & (S[c] > th).to_numpy() for c in S.columns for th in thresholds]
    return pd.Series(-size * np.mean(votes, axis=0), index=idx, name="VIXY")


if __name__ == "__main__":
    import vc_data as vc
    from fetch_cot_vix import fetch_tff
    P = vc.panel()
    w = target_weight(P["VIXY"], P["VIX"], P["VIX3M"], fetch_tff())
    print(w.tail(10))
