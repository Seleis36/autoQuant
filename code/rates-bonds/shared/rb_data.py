"""Shared data plumbing for rates-bonds research.

* `etf_close(tickers)` -- daily adjusted closes from the flat cache, with the
  `*_d_pre2010.parquet` copies spliced on the front (rescaled at the overlap date), so
  SHY/IEF/TLT/LQD/HYG/AGG run from 2002-07 (HYG 2007-04) instead of 2010.
* `cmt_returns()` -- synthetic constant-maturity par-bond total and excess returns from the
  never-revised FRED CMT yields (re-uses `rates-carry-trend/curve_lib.py`), 1982+.
* `fred(sid)` -- the daily FRED cache (`data/FRED_<ID>_d.parquet`).
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "rates-bonds", "rates-carry-trend"))
import research_lib as rl  # noqa: E402
from fetch_fred_daily import fred  # noqa: E402,F401
import curve_lib  # noqa: E402

ANN = 252.0


def _read(path):
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    s = df["Close"]
    return s[~s.index.duplicated(keep="last")].sort_index()


def etf_close(tickers, include_pre2010=True, fetch_missing=True):
    out = {}
    for t in tickers:
        path = rl.daily_cache_path(t)
        if not os.path.exists(path):
            if not fetch_missing:
                continue
            rl.load_series(t)
        s = _read(path)
        pre = path.replace("_d.parquet", "_d_pre2010.parquet")
        if include_pre2010 and os.path.exists(pre):
            p = _read(pre)
            ov = p.index.intersection(s.index)
            if len(ov):
                p = p * (s.loc[ov[-1]] / p.loc[ov[-1]])
            s = pd.concat([p[~p.index.isin(s.index)], s]).sort_index()
        out[t] = s
    return pd.DataFrame(out).sort_index()


def cmt_returns(maturities=(2, 5, 10, 30), excess=False, start="1982-01-01"):
    y = curve_lib.yields(maturities=tuple(sorted(set(maturities) | {0.25})), start=start)
    tr = curve_lib.total_returns(y, maturities=maturities)
    if excess:
        tr = curve_lib.excess_returns(tr, y)
    return tr.dropna(how="all")


def stats_table(nets, splits, ann=ANN):
    """nets: dict name -> daily net return Series. Returns Sharpe per split + full."""
    rows = {}
    for k, r in nets.items():
        row = {}
        for sname, (a, b) in splits.items():
            seg = r.loc[a:b].dropna()
            row[sname] = seg.mean() / seg.std() * np.sqrt(ann) if len(seg) > 50 and seg.std() > 0 else np.nan
        rows[k] = row
    return pd.DataFrame(rows).T
