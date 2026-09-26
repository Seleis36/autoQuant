"""Shared data plumbing for global-equity-etf research.

The flat daily cache (`data/<T>_d.parquet`) is filled back to 2010 only (the live runners own
that convention). Country iShares start 1996-03 (EWJ/EWG/EWU/EWZ/EWY/EWA/EWC), EFA 2001-08,
EEM 2003-04, FXI 2004-10, ACWI 2008-03, INDA 2012-02. The pre-2010 history lives beside the
main file in `data/<T>_d_pre2010.parquet` -- the split the rates-bonds and sector-etf research
use -- and `load_ohlcv` splices the two, rescaling the older download onto the newer one at
their overlap (both are auto-adjusted, but from different downloads).

Local indices (`^N225` ...) and FX (`JPY=X` ...) are loaded through the same functions; they
live on their own exchange calendars, so `load_panel` reindexes onto the SPY calendar with a
short forward-fill (a local holiday leaves yesterday's close, which is what a trader saw).
"""
import os
import sys
import time
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "code", "shared"))
import research_lib as rl  # noqa: E402

COUNTRIES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
BROAD = ["EFA", "EEM", "ACWI"]
BENCH = "SPY"
UNIVERSE = COUNTRIES + BROAD + [BENCH]
ANN = 252.0
PRE_START = "1996-01-01"

# local index and USD-per-local FX quote for each country ETF (yfinance tickers)
LOCAL_INDEX = {"EWJ": "^N225", "EWG": "^GDAXI", "EWU": "^FTSE", "EWZ": "^BVSP",
               "EWY": "^KS11", "EWA": "^AXJO", "EWC": "^GSPTSE", "FXI": "^HSI",
               "INDA": "^NSEI"}
# yfinance FX quote and whether it is USD per local (True) or local per USD (False)
FX = {"EWJ": ("JPY=X", False), "EWG": ("EURUSD=X", True), "EWU": ("GBPUSD=X", True),
      "EWZ": ("BRL=X", False), "EWY": ("KRW=X", False), "EWA": ("AUDUSD=X", True),
      "EWC": ("CAD=X", False), "FXI": ("HKD=X", False), "INDA": ("INR=X", False)}
# where the home exchange sits relative to the US session
#   'asia'  : local close before the US open -> whole US session is non-synchronous
#   'europe': local close 11:30 ET -> US afternoon non-synchronous
#   'americas': fully synchronous (TSX 16:00 ET, B3 ~16:00-17:00 ET)
SESSION = {"EWJ": "asia", "EWY": "asia", "EWA": "asia", "FXI": "asia", "INDA": "asia",
           "EWG": "europe", "EWU": "europe", "EFA": "europe",
           "EWZ": "americas", "EWC": "americas", "EEM": "asia", "ACWI": "mixed"}


def _pre_path(t):
    return rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")


def _read(path):
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[~df.index.duplicated(keep="last")].sort_index()


def refresh(tickers, max_age_hours=12.0, pre2010=True):
    """Bring the post-2010 file up to date (existing rows kept unless re-downloaded) and make
    sure a pre-2010 file exists reaching back to PRE_START (or the listing date)."""
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
        if os.path.exists(pp):
            continue
        pre = yf.download(t, start=PRE_START, end="2010-01-06", auto_adjust=True,
                          progress=False, multi_level_index=False).dropna()
        if not len(pre):
            continue
        pre.index = pd.to_datetime(pre.index).tz_localize(None)
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


def load_panel(tickers=None, field="Close", include_pre2010=True, start=None, end=None,
               ffill_limit=3):
    """Wide frame (date x ticker) of one OHLCV field on the SPY trading calendar.
    Tickers not yet listed are NaN (never forward-filled from nothing)."""
    tickers = tickers or UNIVERSE
    cols = {}
    for t in tickers:
        try:
            cols[t] = load_ohlcv(t, include_pre2010)[field]
        except FileNotFoundError:
            continue
    df = pd.DataFrame(cols)
    cal = load_ohlcv(BENCH, include_pre2010).index
    df = df.reindex(df.index.union(cal)).sort_index()
    for c in df.columns:
        fv = df[c].first_valid_index()
        if fv is not None:
            df.loc[fv:, c] = df.loc[fv:, c].ffill(limit=ffill_limit)
    df = df.reindex(cal)
    return df.loc[start:end]


def load_dividends(t, refresh_div=False):
    """Cash distributions per share (ex-date indexed, unadjusted) from yfinance, cached at
    data/<T>_div.parquet. Ex-dates are public on the day, so this is point-in-time."""
    path = rl.daily_cache_path(t).replace("_d.parquet", "_div.parquet")
    if os.path.exists(path) and not refresh_div:
        s = pd.read_parquet(path)["Dividends"]
    else:
        import yfinance as yf
        s = yf.Ticker(t).dividends
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        rl._atomic_parquet(s.to_frame("Dividends"), path)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def splits(oos_start="2013-01-01"):
    """Pre-registered split for every idea in this session: IS <= 2012, OOS 2013+."""
    return {"IS": (None, pd.Timestamp(oos_start) - pd.Timedelta(days=1)),
            "OOS": (pd.Timestamp(oos_start), None)}


def load_unadjusted_close(t, refresh_raw=False):
    """Split-adjusted but NOT dividend-adjusted close (yfinance auto_adjust=False 'Close'),
    cached at data/<T>_d_unadj.parquet. Needed for yields: the auto-adjusted cache shrinks old
    prices by later dividends, which inflates historical yields."""
    path = rl.daily_cache_path(t).replace("_d.parquet", "_d_unadj.parquet")
    if os.path.exists(path) and not refresh_raw:
        s = pd.read_parquet(path)["Close"]
    else:
        import yfinance as yf
        df = yf.download(t, start=PRE_START, auto_adjust=False, progress=False,
                         multi_level_index=False).dropna()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        rl._atomic_parquet(df[["Close"]], path)
        s = df["Close"]
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_fred(series_id, refresh_fred=False):
    """Daily FRED series (e.g. H.10 FX `DEXJPUS`) cached at data/FRED_<ID>_d.parquet, same
    layout as the existing FRED_DGS10 file (one column named after the series)."""
    path = os.path.join(rl.DATA_DIR, f"FRED_{series_id}_d.parquet")
    if os.path.exists(path) and not refresh_fred:
        df = pd.read_parquet(path)
    else:
        import io, urllib.request
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = pd.read_csv(io.BytesIO(r.read()))
        raw.columns = ["DATE", series_id]
        raw["DATE"] = pd.to_datetime(raw["DATE"])
        df = raw.set_index("DATE")
        df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
        df = df.dropna()
        rl._atomic_parquet(df, path)
    df.index = pd.to_datetime(df.index)
    return df[series_id].sort_index()
