"""intl-relative-trend -- slow time-series trend of country ETFs relative to SPY.

Mechanism: the US-vs-rest-of-world equity spread moves in multi-year regimes (1985-89 Japan,
1990s US, 2002-07 ex-US/EM, 2008-2026 US). A 6/12/24-month trend on each country's
SPY-beta-hedged spread, and on the equal-weight ex-US aggregate, rides those regimes. Evidence:
Sharpe ~0.35-0.6 in each of 1980-2000 (local indices x FX), 2001-2012 and 2013-2026 (ETFs).

Book (daily closes, SPY calendar, all signals from data up to and including the close of t):
  1. spread_i = r_i - beta_i(t-1) * r_SPY, beta = rolling 252d close-to-close beta (min 126)
     for each of the 9 country ETFs, plus the EW average of the available ones ("EXUS").
  2. signal = mean over L in (126, 252, 504) of sign(log cumulative spread return over L days).
  3. On the last trading day of each month: position_i = signal_i / vol_i, vol = 126d std of the
     spread (annualised). ETF weight = position; SPY weight = -sum(position_i * beta_i).
     AGG sleeve: the EXUS position split equally across the available country ETFs.
     DIV sleeve: the 9 per-country spreads.
  4. Each sleeve scaled to `target_vol` ex-ante on the trailing 126d covariance of the traded
     ETFs + SPY; blend 50/50; the blend re-scaled to `target_vol`; per-rebalance scalar <= cap.
  5. Weights held until the next month-end rebalance.

`target_weights(close)` returns a daily DataFrame of target weights (fraction of equity) for the
9 country ETFs + SPY, known at the close of each day; the backtest applies them to the next
day's return (fill at the same close the signal is computed on).
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from trading_calendar import month_end_sessions  # noqa: E402

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
BENCH = "SPY"
LOOKBACKS = (126, 252, 504)
BETA_WIN = 252
VOL_WIN = 126
COV_WIN = 126
TARGET_VOL = 0.10
SCALAR_CAP = 3.0
ANN = 252.0


def _rebalance_dates(index):
    """Last trading day of each month; the final date is judged by the NYSE calendar."""
    return month_end_sessions(index)


def _roll_beta(ret, names, bench=BENCH, win=BETA_WIN):
    x = ret[bench]
    v = x.rolling(win, min_periods=win // 2).var()
    return pd.DataFrame({t: ret[t].rolling(win, min_periods=win // 2).cov(x) / v for t in names})


def _trend(spread, lookbacks):
    lp = np.log((1 + spread.fillna(0.0)).cumprod()).where(spread.notna())
    return sum(np.sign(lp - lp.shift(l)) for l in lookbacks) / len(lookbacks)


def _vol_target(w, ret, target, cov_win=COV_WIN, cap=SCALAR_CAP):
    out = w * 0.0
    for d in w.index:
        wd = w.loc[d]
        cols = wd[wd != 0].index
        hist = ret.loc[:d, cols].iloc[-cov_win:]
        if len(cols) == 0 or len(hist) < 60:
            continue
        cov = hist.fillna(0.0).cov().values * ANN
        v = float(np.sqrt(max(wd[cols].values @ cov @ wd[cols].values, 1e-12)))
        out.loc[d, cols] = wd[cols] * min(target / v, cap)
    return out


def sleeve_weights(close, lookbacks=LOOKBACKS, beta_win=BETA_WIN, vol_win=VOL_WIN):
    """Unscaled rebalance-date weights for the AGG and DIV sleeves (ETFs + SPY hedge)."""
    close = close[COUNTRIES + [BENCH]]
    ret = close.pct_change(fill_method=None)
    ret = ret.where(close.notna())
    ret["EXUS"] = ret[COUNTRIES].mean(axis=1, skipna=True)
    names = COUNTRIES + ["EXUS"]
    beta = _roll_beta(ret, names, win=beta_win)
    spread = ret[names] - beta.shift(1).mul(ret[BENCH], axis=0)
    sig = _trend(spread, lookbacks)
    vol = spread.rolling(vol_win, min_periods=60).std() * np.sqrt(ANN)
    reb = _rebalance_dates(close.index)
    pos = (sig / vol).loc[reb]
    pos = pos.where(np.isfinite(pos), 0.0).fillna(0.0)
    b = beta.loc[reb].fillna(1.0)
    div = pos[COUNTRIES].copy()
    div[BENCH] = -(pos[COUNTRIES] * b[COUNTRIES]).sum(axis=1)
    avail = close.loc[reb, COUNTRIES].notna() & ret[COUNTRIES].rolling(beta_win).count().loc[reb].ge(beta_win // 2)
    n = avail.sum(axis=1).replace(0, np.nan)
    agg = avail.astype(float).div(n, axis=0).mul(pos["EXUS"], axis=0).fillna(0.0)
    agg[BENCH] = -pos["EXUS"] * b["EXUS"]
    return agg, div, ret[COUNTRIES + [BENCH]]


def target_weights(close, lookbacks=LOOKBACKS, beta_win=BETA_WIN, vol_win=VOL_WIN,
                   target_vol=TARGET_VOL, blend=0.5, cap=SCALAR_CAP):
    """Daily target weights (date x [9 country ETFs + SPY]) for the intl-relative-trend book.

    close: DataFrame of daily closes (auto-adjusted) with at least the 9 country ETFs and SPY,
    on the SPY trading calendar. Missing (not yet listed) names must be NaN.
    blend: weight of the AGG sleeve (1 - blend on DIV)."""
    agg, div, ret = sleeve_weights(close, lookbacks, beta_win, vol_win)
    a = _vol_target(agg, ret, target_vol, cap=cap)
    d = _vol_target(div, ret, target_vol, cap=cap)
    w = blend * a + (1 - blend) * d
    w = _vol_target(w, ret, target_vol, cap=cap)
    return w.reindex(close.index).ffill().fillna(0.0)[COUNTRIES + [BENCH]]
