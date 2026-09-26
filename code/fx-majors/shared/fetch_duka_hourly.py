"""Hourly bid/ask candles for the seven majors from Dukascopy's public datafeed.

Why hourly candles and not ticks: the tick crawl (`code/shared/fetch_dukascopy.py`) is
~24 requests per pair per day. Dukascopy also serves one file per pair, side and *month*
holding every hourly candle, so 2010-2026 for seven majors is ~2,800 requests (a couple of
hours at the rate the feed grants) instead of ~700k.

What it answers for fx-majors research:
  * the **spread that stood at the fill time**: the `=X` daily row is the 00:00 UTC quote,
    so the cost of a daily rebalance is half the ask-bid gap at the close of the 23:00 UTC
    candle, per pair and per day -- a measurement, not a flat guess;
  * hourly mid returns at any daily cut (16:00 London fix, 21:00 NY close, 00:00 UTC).

Wire format (checked against the live feed):
    {BASE}/{SYM}/{YYYY}/{MM0}/{BID|ASK}_candles_hour_1.bi5    MM0 is 0-indexed
    LZMA -> 24-byte records `>IIIIIf` = (sec_from_month_start, open, close, low, high, vol)
    prices in points: / 10**digits (3 for JPY pairs, 5 otherwise). Weekend hours are
    present as flat zero-volume candles and are dropped here.

Output: data/<SYM>_duka_1h.parquet, index = candle OPEN time UTC (tz-naive), columns
    BidOpen BidHigh BidLow BidClose AskOpen AskHigh AskLow AskClose Volume
Resumable: raw month files are kept under data/_duka_1h_raw/ until consolidated.
"""
import concurrent.futures as cf
import lzma
import os
import struct
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
DATA = os.path.join(REPO, "data")
RAW = os.path.join(DATA, "_duka_1h_raw")
BASE = "https://datafeed.dukascopy.com/datafeed"
UA = {"User-Agent": "autoquant-research/1.0"}
REC = struct.Struct(">IIIIIf")
MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]


def _digits(sym):
    return 3 if sym.endswith("JPY") else 5


def _get(url, tries=12):
    wait = 2.0
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""
        except Exception:
            pass
        time.sleep(wait)
        wait = min(wait * 1.7, 60)
    raise RuntimeError(f"gave up on {url}")


def fetch_month(sym, year, month, side):
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, f"{sym}_{year}_{month:02d}_{side}.bin")
    if os.path.exists(path):
        return open(path, "rb").read()
    blob = _get(f"{BASE}/{sym}/{year}/{month - 1:02d}/{side}_candles_hour_1.bi5")
    raw = lzma.decompress(blob) if blob else b""
    with open(path + ".tmp", "wb") as fh:
        fh.write(raw)
    os.replace(path + ".tmp", path)
    return raw


def decode(raw, sym, year, month, side):
    if not raw:
        return pd.DataFrame()
    a = np.frombuffer(raw, dtype=np.dtype([("t", ">u4"), ("o", ">u4"), ("c", ">u4"),
                                           ("l", ">u4"), ("h", ">u4"), ("v", ">f4")]))
    sc = 10.0 ** _digits(sym)
    idx = pd.Timestamp(year=year, month=month, day=1) + pd.to_timedelta(a["t"].astype(np.int64), unit="s")
    p = side.capitalize()
    return pd.DataFrame({f"{p}Open": a["o"] / sc, f"{p}High": a["h"] / sc, f"{p}Low": a["l"] / sc,
                         f"{p}Close": a["c"] / sc, f"{p}Vol": a["v"].astype(float)}, index=idx)


def prefetch(syms, start="2010-01", end=None, workers=12):
    """Download every raw month file in parallel (the feed throttles per request, not per
    client, so a small pool is several times faster than a serial crawl). Idempotent."""
    end = pd.Period(end or pd.Timestamp.now("UTC").strftime("%Y-%m"), "M")
    months = list(pd.period_range(pd.Period(start, "M"), end, freq="M"))
    # Stratified order: one month per year for every pair first (Jan, then Jul, Apr, Oct,
    # ...), so an interrupted crawl still leaves an unbiased sample across pairs and years.
    order = {m: k for k, m in enumerate([1, 7, 4, 10, 2, 8, 5, 11, 3, 9, 6, 12])}
    months.sort(key=lambda p: (order[p.month], p.year))
    jobs = [(s, p.year, p.month, side) for p in months for s in syms for side in ("BID", "ASK")]
    with cf.ThreadPoolExecutor(workers) as ex:
        for k, _ in enumerate(ex.map(lambda j: fetch_month(*j), jobs)):
            if k % 100 == 0:
                print(f"  {k}/{len(jobs)} files", flush=True)


def build(sym, start="2010-01", end=None, verbose=True):
    end = pd.Period(end or pd.Timestamp.now("UTC").strftime("%Y-%m"), "M")
    frames = []
    for per in pd.period_range(pd.Period(start, "M"), end, freq="M"):
        parts = []
        for side in ("BID", "ASK"):
            raw = fetch_month(sym, per.year, per.month, side)
            parts.append(decode(raw, sym, per.year, per.month, side))
        if parts[0].empty or parts[1].empty:
            if verbose:
                print(f"  {sym} {per}: empty", flush=True)
            continue
        m = parts[0].join(parts[1], how="inner")
        frames.append(m)
        if verbose and per.month == 12:
            print(f"  {sym} {per} done", flush=True)
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["Volume"] = df.pop("BidVol") + df.pop("AskVol")
    df = df[df["Volume"] > 0]                      # weekend / holiday filler candles
    out = os.path.join(DATA, f"{sym}_duka_1h.parquet")
    df.to_parquet(out + ".tmp.parquet")
    os.replace(out + ".tmp.parquet", out)
    if verbose:
        print(f"{sym}: {len(df)} hourly candles {df.index.min()} -> {df.index.max()}", flush=True)
    return df


def load_hourly(sym):
    return pd.read_parquet(os.path.join(DATA, f"{sym}_duka_1h.parquet"))


if __name__ == "__main__":
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else MAJORS
    prefetch(syms)
    for s in syms:
        build(s)
