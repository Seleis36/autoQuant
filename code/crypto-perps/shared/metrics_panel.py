"""Binance USD-M `metrics` archive (5-minute open interest and long/short ratios) for a
cross-section of perps, plus a lag-safe daily panel builder.

Archive coverage (checked 2026-09-30 against the S3 listing): BTCUSDT from 2020-09-01, every
other perp (ETH included) only from **2021-12-01** or its listing date if later.

Columns of `data/<SYM>_metrics_5m.parquet` (index = archive `create_time`, UTC, naive):
  sum_open_interest                 OI in coins
  sum_open_interest_value           OI in USDT
  count_toptrader_long_short_ratio  top-20% accounts: # net long / # net short
  sum_toptrader_long_short_ratio    top-20% accounts: long position / short position
  count_long_short_ratio            all accounts: # net long / # net short  (the retail crowd)
  sum_taker_long_short_vol_ratio    taker buy / taker sell volume over the 5 minutes

Fetch is threaded and resumable: raw daily CSVs are kept in `data/_scratch_metrics/<SYM>/`
until the parquet is written, and an existing parquet is only extended.

    python code/crypto-perps/shared/metrics_panel.py ETHUSDT SOLUSDT ...   # or 'all'

Live (REST, 30 days only): fapi.binance.com/futures/data/globalLongShortAccountRatio etc.;
the REST stamp is 5 minutes later than the archive `create_time` for the same value.
"""
import os
import sys
import shutil
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, _HERE)
import fetch_binance_vision as fbv  # noqa: E402
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402

SCRATCH = os.path.join(DATA_DIR, "_scratch_metrics")
ALT_START = "2021-12-01"
COLS = ["sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio", "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio"]


def path_of(sym):
    return os.path.join(DATA_DIR, f"{sym}_metrics_5m.parquet")


def _one(symbol, day):
    stamp = day.strftime("%Y-%m-%d")
    dst = os.path.join(SCRATCH, symbol, f"{stamp}.csv")
    if os.path.exists(dst):
        return dst
    url = f"{fbv.BASE}/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{stamp}.zip"
    blob = fbv._get(url)
    if blob is None:
        return None
    raw = fbv._unzip(blob, url, verify=False)
    tmp = dst + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(raw)
    os.replace(tmp, dst)
    return dst


def fetch(symbol, start=None, end=None, workers=16, keep_scratch=False):
    old = None
    if os.path.exists(path_of(symbol)):
        old = pd.read_parquet(path_of(symbol))
        start = (old.index.max().normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    start = start or ("2020-09-01" if symbol == "BTCUSDT" else ALT_START)
    end = pd.Timestamp(end) if end else pd.Timestamp.now('UTC').tz_localize(None).normalize() - pd.Timedelta(days=1)
    days = pd.date_range(start, end, freq="D")
    if len(days) == 0:
        return old
    os.makedirs(os.path.join(SCRATCH, symbol), exist_ok=True)
    with ThreadPoolExecutor(workers) as ex:
        paths = [p for p in ex.map(lambda d: _one(symbol, d), days) if p]
    if not paths:
        return old
    frames = []
    for p in sorted(paths):
        try:
            frames.append(pd.read_csv(p))
        except Exception:  # noqa: BLE001 -- an empty day file
            pass
    df = pd.concat(frames)
    df["ts"] = pd.to_datetime(df["create_time"])
    df = df.set_index("ts").drop(columns=["create_time", "symbol"]).apply(pd.to_numeric, errors="coerce")
    if old is not None:
        df = pd.concat([old, df])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    _atomic_parquet(df, path_of(symbol))
    if not keep_scratch:
        shutil.rmtree(os.path.join(SCRATCH, symbol), ignore_errors=True)
    return df


def load_metrics(sym):
    p = path_of(sym)
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    return df


def daily_from_frame(df, cutoff_hour=23, how="last"):
    """Daily rows of one symbol's 5-minute frame (archive stamp convention), see daily_metrics."""
    # stamp t belongs to day D iff D-1 + cutoff <= t < D + cutoff, i.e. D = floor(t - cutoff) + 1
    key = (df.index - pd.Timedelta(hours=cutoff_hour)).floor("D") + pd.Timedelta(days=1)
    g = df.groupby(key)
    return g.last() if how == "last" else g.mean()


def daily_metrics(syms, cutoff_hour=23, how="last"):
    """One value per calendar day D per symbol and column, usable at the close of D.

    The close of day D is D+1 00:00 UTC. We only use archive stamps strictly before
    D `cutoff_hour`:00 (default 23:00), i.e. a one-hour safety margin before the close --
    the archive stamp is the start of its 5-minute window, and the REST feed publishes the
    same value 5 minutes later.
      how="last": the last value before the cutoff
      how="mean": the mean of the stamps in [D-1 cutoff, D cutoff)
    Returns dict column -> DataFrame[date x sym].
    """
    out = {c: {} for c in COLS}
    for s in syms:
        df = load_metrics(s)
        if df is None or df.empty:
            continue
        agg = daily_from_frame(df, cutoff_hour, how)
        for c in COLS:
            if c in agg:
                out[c][s] = agg[c]
    return {c: pd.DataFrame(v).sort_index() for c, v in out.items()}


# REST endpoint -> (archive column, JSON field). History is 30 days only.
REST = {
    "count_long_short_ratio": ("globalLongShortAccountRatio", "longShortRatio"),
    "count_toptrader_long_short_ratio": ("topLongShortAccountRatio", "longShortRatio"),
    "sum_toptrader_long_short_ratio": ("topLongShortPositionRatio", "longShortRatio"),
    "sum_open_interest": ("openInterestHist", "sumOpenInterest"),
    "sum_open_interest_value": ("openInterestHist", "sumOpenInterestValue"),
}


def fetch_rest(sym, column="count_long_short_ratio", period="5m", limit=500, end=None):
    """Live values from fapi.binance.com/futures/data/*, re-stamped to the ARCHIVE convention.

    The REST timestamp is 5 minutes later than the archive `create_time` of the same value
    (checked on DOGEUSDT 2026-09-27: REST 23:00 = 2.5907 = archive 22:55 2.590851), so 5 minutes
    are subtracted; `daily_from_frame` then applies the same < 23:00 cutoff as the backtest.
    Pages backwards from `end` (default now) until `limit` rows are collected (500 per call)."""
    import json
    import urllib.request
    ep, field = REST[column]
    rows, t_end = [], end
    while len(rows) < limit:
        q = f"symbol={sym}&period={period}&limit={min(500, limit - len(rows))}"
        if t_end is not None:
            q += f"&endTime={int(pd.Timestamp(t_end).timestamp() * 1000)}"
        url = f"https://fapi.binance.com/futures/data/{ep}?{q}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=fbv.UA), timeout=30) as r:
            page = json.loads(r.read())
        if not page:
            break
        rows = page + rows
        t_end = pd.Timestamp(page[0]["timestamp"], unit="ms") - pd.Timedelta(minutes=1)
        if len(page) < 500:
            break
    if not rows:
        return pd.Series(dtype=float, name=column)
    idx = pd.to_datetime([r["timestamp"] for r in rows], unit="ms") - pd.Timedelta(minutes=5)
    s = pd.Series([float(r[field]) for r in rows], index=idx, name=column)
    return s[~s.index.duplicated(keep="last")].sort_index()


if __name__ == "__main__":
    import funding_panel as fp
    syms = sys.argv[1:]
    if syms == ["all"]:
        syms = [v for v in fp.PERP_OF.values()]
    for s in syms:
        try:
            d = fetch(s)
            print(s, None if d is None else (d.index.min(), d.index.max(), len(d)), flush=True)
        except Exception as e:  # noqa: BLE001
            print(s, "FAILED", e, flush=True)
