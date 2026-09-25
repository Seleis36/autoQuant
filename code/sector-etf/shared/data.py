"""Shared data plumbing for sector-etf research.

The flat daily cache (`data/<T>_d.parquet`) is filled back to 2010 only (it is shared with
the live runners, which own that convention). Sector SPDRs start 1998-12-22, so the
1999-2009 history lives beside it in `data/<T>_d_pre2010.parquet` -- the same split the
rates-bonds research uses -- and `load_panel` splices the two, rescaling the older file
onto the newer one at their overlap (both are auto-adjusted, but from different downloads).

Ragged start: XLRE lists 2015-10-08 and XLC 2018-06-19. Before that their columns are NaN
and every cross-sectional helper must treat them as "not in the universe", never as 0.
"""
import os
import sys
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "code", "shared"))
import research_lib as rl  # noqa: E402

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
ORIGINAL9 = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB"]
BENCH = "SPY"
ANN = 252.0
PRE_START = "1998-12-01"


def _pre_path(t):
    return rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")


def _read(path):
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[~df.index.duplicated(keep="last")].sort_index()


def refresh(tickers, max_age_hours=12.0, pre2010=True):
    """Bring the post-2010 file up to date (same merge rule as live_lib.daily) and make
    sure a pre-2010 file exists that reaches back to PRE_START. Existing pre-2010 files
    that start later (SPY's starts 2002) are extended backwards, never truncated."""
    import time
    import yfinance as yf
    for t in tickers:
        path = rl.daily_cache_path(t)
        stale = (not os.path.exists(path)) or (time.time() - os.path.getmtime(path)) > max_age_hours * 3600
        if stale:
            new = yf.download(t, start=rl.DAILY_CACHE_START, auto_adjust=True,
                              progress=False, multi_level_index=False).dropna()
            if len(new):
                new.index = pd.to_datetime(new.index).tz_localize(None)
                if os.path.exists(path):
                    old = _read(path)
                    new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
                rl._atomic_parquet(new, path)
        if not pre2010:
            continue
        pp = _pre_path(t)
        have = _read(pp) if os.path.exists(pp) else None
        if have is not None and have.index.min() <= pd.Timestamp("1999-01-05"):
            continue
        end = "2010-01-06" if have is None else str((have.index.min() + pd.Timedelta(days=5)).date())
        pre = yf.download(t, start=PRE_START, end=end, auto_adjust=True,
                          progress=False, multi_level_index=False).dropna()
        if not len(pre):
            continue
        pre.index = pd.to_datetime(pre.index).tz_localize(None)
        if have is not None:
            ov = pre.index.intersection(have.index)
            if len(ov):
                k = have.loc[ov[0], "Close"] / pre.loc[ov[0], "Close"]
                for c in ["Open", "High", "Low", "Close"]:
                    pre[c] = pre[c] * k
            pre = pd.concat([pre[pre.index < have.index.min()], have]).sort_index()
        rl._atomic_parquet(pre, pp)


def load_ohlcv(t, include_pre2010=True):
    df = _read(rl.daily_cache_path(t))
    pp = _pre_path(t)
    if include_pre2010 and os.path.exists(pp):
        pre = _read(pp)
        ov = pre.index.intersection(df.index)
        if len(ov):
            k = df.loc[ov[-1], "Close"] / pre.loc[ov[-1], "Close"]
            pre = pre.copy()
            for c in ["Open", "High", "Low", "Close"]:
                pre[c] = pre[c] * k
        df = pd.concat([pre[~pre.index.isin(df.index)], df]).sort_index()
    return df


def load_panel(tickers=None, field="Close", include_pre2010=True, start=None, end=None):
    """Wide frame (date x ticker) of one OHLCV field, on the SPY trading calendar.
    Tickers not yet listed are NaN (never forward-filled from nothing)."""
    tickers = tickers or SECTORS + [BENCH]
    cols = {t: load_ohlcv(t, include_pre2010)[field] for t in tickers}
    df = pd.DataFrame(cols)
    cal = load_ohlcv(BENCH, include_pre2010).index
    df = df.reindex(cal)
    # forward-fill interior holes only (after first valid print), max 3 days
    for c in df.columns:
        fv = df[c].first_valid_index()
        if fv is not None:
            df.loc[fv:, c] = df.loc[fv:, c].ffill(limit=3)
    return df.loc[start:end]


def universe_mask(close):
    """True where the ticker has a price today AND had one 1 year ago -- i.e. at least
    252 days of history, so rolling estimators are defined. Applied to sectors only."""
    ok = close.notna() & close.shift(252).notna()
    return ok
