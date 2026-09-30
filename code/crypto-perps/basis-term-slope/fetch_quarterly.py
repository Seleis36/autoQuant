"""Binance COIN-M quarterly futures, continuous CURRENT_QUARTER and NEXT_QUARTER daily klines
(dapi/v1/continuousKlines, keyless, history from 2020-06) for BTCUSD and ETHUSD.

Writes data/BINANCE_<PAIR>_CQ_1d.parquet and data/BINANCE_<PAIR>_NQ_1d.parquet (bar-open stamps,
UTC; the Close of row D is the price at D+1 00:00 UTC). A continuous series switches contract
at expiry (last Friday of Mar/Jun/Sep/Dec, 08:00 UTC); `expiry_after` gives the expiry that a
given close belongs to.
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
sys.path.insert(0, os.path.join(ROOT, "code", "crypto-alts", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402
import venues  # noqa: E402

TYPES = {"CURRENT_QUARTER": "CQ", "NEXT_QUARTER": "NQ"}


def path_of(pair, typ):
    return os.path.join(DATA_DIR, f"BINANCE_{pair}_{TYPES[typ]}_1d.parquet")


def fetch(pair="BTCUSD", typ="CURRENT_QUARTER", start="2020-01-01"):
    out, t = [], int(pd.Timestamp(start).timestamp() * 1000)
    while True:
        url = (f"https://dapi.binance.com/dapi/v1/continuousKlines?pair={pair}&contractType={typ}"
               f"&interval=1d&startTime={t}&limit=1500")
        with urllib.request.urlopen(urllib.request.Request(url, headers=venues.UA), timeout=30) as r:
            rows = json.loads(r.read())
        if not rows:
            break
        out += rows
        if len(rows) < 1500:
            break
        t = rows[-1][0] + 86_400_000
        time.sleep(0.2)
    df = venues._klines_frame(out)
    df = df[df.index < pd.Timestamp.now("UTC").tz_convert(None).normalize()]
    _atomic_parquet(df, path_of(pair, typ))
    return df


def quarterly_expiries(start="2019-01-01", end="2028-12-31"):
    """Last Friday of Mar/Jun/Sep/Dec, 08:00 UTC."""
    out = []
    for m in pd.date_range(start, end, freq="QE-DEC"):
        d = m.normalize()
        while d.weekday() != 4:
            d -= pd.Timedelta(days=1)
        out.append(d + pd.Timedelta(hours=8))
    return pd.DatetimeIndex(out)


def expiry_after(ts, k=0):
    """The (k+1)-th quarterly expiry strictly after timestamp ts."""
    ex = quarterly_expiries()
    return ex[ex > ts][k]


if __name__ == "__main__":
    for pair in ("BTCUSD", "ETHUSD"):
        for typ in TYPES:
            d = fetch(pair, typ)
            print(pair, typ, d.index.min(), d.index.max(), len(d))
