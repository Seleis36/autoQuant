"""Bulk crypto history from `data.binance.vision`, the public archive behind Binance.

Why this instead of the REST klines endpoint the older fetchers page through: REST hands
back 1000 bars a request, so nine years of 1m BTCUSDT is ~4,700 round trips with a
rate-limit sleep between each. The archive ships the same bars as one ~2 MB zip per
month. No key, no rate limit that matters, and the monthly files are immutable, so a
re-run only fetches what is missing.

Datasets, and what each actually costs to pull:

  klines        spot or USD-M futures OHLCV. ~2 MB/month at 1m. Bulk-cacheable.
  bookTicker    best bid/ask on every book update. **USD-M futures only** -- there is no
                spot bookTicker in this archive -- and ~199 MB *per day* for BTCUSDT.
                Never cached raw: aggregated to 1m spread statistics as it streams.
  metrics       open interest and long/short ratios, 5-minutely. Daily files, ~12 KB.
  fundingRate   perp funding settlements. Monthly, under a kilobyte.

Two traps live in this archive, both silent:

  1. **Timestamps changed units mid-2025.** Files up to ~2024 stamp klines in
     milliseconds (13 digits); later ones use microseconds (16). A loader that hardcodes
     `unit="ms"` reads 2025 bars as the year 57000 and pandas will not complain. Every
     timestamp here goes through `_to_datetime`, which picks the unit by magnitude.
  2. **The current month has no monthly file.** It appears only after the month closes,
     so a fetch that stops at the monthly boundary silently ends weeks early. `_periods`
     falls back to daily files for the tail.

Writes into the partitioned store in `bars.py`; bar stamps are OPEN times, UTC, tz-naive.
"""
import argparse
import hashlib
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bars as barstore
from research_lib import DATA_DIR, _atomic_parquet

BASE = "https://data.binance.vision"
UA = {"User-Agent": "autoquant-research/1.0"}

#: Binance kline CSV column order. `ig` is their unused trailing field.
KLINE_COLS = ["ot", "Open", "High", "Low", "Close", "Volume",
              "ct", "qv", "n", "tb", "tq", "ig"]

#: Kept out of the bar store: `ct` is derivable from the open stamp and the frequency,
#: and `ig` has never carried a value.
KLINE_DROP = ["ct", "ig"]


# ------------------------------------------------------------------ transport

def _get(url, tries=5, timeout=120):
    """Return response bytes, or None on a clean 404 (the archive's 'not published')."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:  # noqa: BLE001 -- transient network, retried below
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


def _unzip(blob, url="", verify=True):
    """Single-member zip -> bytes, checked against the archive's .CHECKSUM when present."""
    if verify and url:
        want = _get(url + ".CHECKSUM")
        if want:
            got = hashlib.sha256(blob).hexdigest()
            expect = want.decode().split()[0].strip()
            if got != expect:
                raise RuntimeError(f"checksum mismatch for {url}: {got} != {expect}")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return z.read(z.namelist()[0])


def _to_datetime(s):
    """Binance stamps: milliseconds before ~2025, microseconds after. Pick by magnitude.

    A 13-digit value is ms since epoch (year ~2001-2286); a 16-digit one is us. Deciding
    per-series rather than per-file keeps a frame that straddles the switch coherent.
    """
    v = pd.to_numeric(s, errors="coerce")
    unit = np.where(v > 1e14, "us", "ms")
    if len(set(unit.tolist() if hasattr(unit, "tolist") else unit)) == 1:
        return pd.to_datetime(v, unit=unit[0] if len(v) else "ms")
    out = pd.Series(pd.NaT, index=v.index if hasattr(v, "index") else None, dtype="datetime64[ns]")
    us = v > 1e14
    out[us] = pd.to_datetime(v[us], unit="us")
    out[~us] = pd.to_datetime(v[~us], unit="ms")
    return out


# ------------------------------------------------------------------ paths

def _utcnow():
    """tz-naive UTC now. `Timestamp.utcnow()` is deprecated and `now("UTC")` is aware."""
    return pd.Timestamp.now("UTC").tz_convert(None)


def _market_root(market):
    if market == "spot":
        return "data/spot"
    if market in ("um", "futures", "perp"):
        return "data/futures/um"
    if market == "cm":
        return "data/futures/cm"
    raise ValueError(f"unknown market {market!r}; use 'spot' or 'um'")


def _periods(start, end, monthly_lag_days=3):
    """Monthly windows for closed months, then daily for the ragged tail.

    The archive publishes a month only once it has closed (and a day or two after), so
    everything from that boundary to `end` has to come from daily files or the fetch ends
    weeks short without saying so.
    """
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    cutoff = (_utcnow().normalize()
              - pd.Timedelta(days=monthly_lag_days)).replace(day=1)
    out = []
    m = start.replace(day=1)
    while m < min(cutoff, end + pd.Timedelta(days=1)):
        out.append(("monthly", m))
        m = (m + pd.Timedelta(days=32)).replace(day=1)
    d = max(start, m)
    while d <= end:
        out.append(("daily", d))
        d += pd.Timedelta(days=1)
    return out


# ------------------------------------------------------------------ klines

def fetch_klines(symbol="BTCUSDT", freq="1m", market="spot",
                 start="2017-08-17", end=None, verify=True, verbose=True):
    """Pull OHLCV into the partitioned bar store. Returns bars written."""
    end = pd.Timestamp(end) if end else _utcnow().normalize()
    root = _market_root(market)
    have = set()
    for y in barstore.cached_years(symbol, freq):
        have |= set(barstore.load_bars(symbol, freq, start=f"{y}-01-01",
                                       end=f"{y}-12-31 23:59:59").index)

    total, buf = 0, []
    for kind, when in _periods(start, end):
        stamp = when.strftime("%Y-%m" if kind == "monthly" else "%Y-%m-%d")
        url = (f"{BASE}/{root}/{kind}/klines/{symbol}/{freq}/"
               f"{symbol}-{freq}-{stamp}.zip")
        blob = _get(url)
        if blob is None:
            if verbose and kind == "monthly":
                print(f"    miss  {stamp} (not published)", flush=True)
            continue
        csv = _unzip(blob, url, verify=verify)
        df = pd.read_csv(io.BytesIO(csv), header=None, names=KLINE_COLS,
                         comment=None, on_bad_lines="skip")
        # Some 2025+ files carry a header row; it survives as a non-numeric first record.
        df = df[pd.to_numeric(df["ot"], errors="coerce").notna()]
        df["ts"] = _to_datetime(df["ot"])
        df = df.drop(columns=["ot"] + KLINE_DROP).set_index("ts")
        df = df.apply(pd.to_numeric, errors="coerce")
        buf.append(df)
        if verbose:
            print(f"    {kind:7s} {stamp}  {len(df):>7,} bars  "
                  f"{df.index[0]} -> {df.index[-1]}", flush=True)
        if sum(len(b) for b in buf) > 500_000:
            total += barstore.write_bars(pd.concat(buf), symbol, freq)
            buf = []
    if buf:
        total += barstore.write_bars(pd.concat(buf), symbol, freq)
    return total


# ------------------------------------------------------------------ bookTicker

def _spread_minutes(csv_bytes, carry=None):
    """Aggregate raw book updates to per-minute spread statistics.

    The spread is **time-weighted**: each quote is weighted by how long it stood before
    the next update. A plain mean over updates overweights the bursts of requoting that
    follow a trade, which is exactly when the book is widest, so it reports a market
    more expensive than the one you would actually have traded. `carry` is the last row
    of the previous chunk, so the weight of the quote straddling a chunk boundary is not
    silently dropped.
    """
    df = pd.read_csv(io.BytesIO(csv_bytes))
    if df.empty:
        return None, carry
    if carry is not None:
        df = pd.concat([carry, df], ignore_index=True)
    df = df.sort_values("transaction_time")
    bid = pd.to_numeric(df["best_bid_price"], errors="coerce")
    ask = pd.to_numeric(df["best_ask_price"], errors="coerce")
    t = pd.to_datetime(df["transaction_time"], unit="ms")

    mid = (bid + ask) / 2.0
    spread = (ask - bid)
    # Weight = time this quote stood. The final quote of the chunk has no successor yet,
    # so it is carried rather than given a fabricated duration.
    dt = t.shift(-1) - t
    w = dt.dt.total_seconds()

    g = pd.DataFrame({"ts": t.dt.floor("min"), "spread": spread, "mid": mid,
                      "bid": bid, "ask": ask, "w": w}).dropna(subset=["spread", "mid"])
    last = df.iloc[[-1]].copy()
    g = g[g["w"].notna()]
    if g.empty:
        return None, last

    g["sw"] = g["spread"] * g["w"]
    g["bw"] = (g["spread"] / g["mid"] * 1e4) * g["w"]
    agg = g.groupby("ts").agg(
        _sw=("sw", "sum"), _bw=("bw", "sum"), _w=("w", "sum"),
        Bid=("bid", "last"), Ask=("ask", "last"), Quotes=("spread", "size"))
    out = pd.DataFrame({
        "Spread": agg["_sw"] / agg["_w"],
        "SpreadBps": agg["_bw"] / agg["_w"],
        "Bid": agg["Bid"], "Ask": agg["Ask"], "Quotes": agg["Quotes"],
    })
    return out, last


def fetch_book_spreads(symbol="BTCUSDT", start=None, end=None, days=90,
                       market="um", chunk_rows=2_000_000, verbose=True):
    """Per-minute time-weighted spread from USD-M futures bookTicker.

    This is the file that turns a cost assumption into a measurement. It is also 199 MB
    per day for BTCUSDT (~6.9 GB a month), so it is deliberately *windowed* -- default
    the last 90 days -- and only the 1m aggregate is ever written to disk. Pulling nine
    years would be ~650 GB of download to produce ~200 MB of output.

    Stored as its own series, `<SYMBOL>_book` at 1m, so it joins onto price bars by
    timestamp without pretending to be OHLCV.
    """
    end = pd.Timestamp(end) if end else (_utcnow().normalize()
                                         - pd.Timedelta(days=1))
    start = pd.Timestamp(start) if start else end - pd.Timedelta(days=days - 1)
    root = _market_root(market)
    name = f"{symbol}_book"
    total = 0
    for day in pd.date_range(start, end, freq="D"):
        stamp = day.strftime("%Y-%m-%d")
        url = (f"{BASE}/{root}/daily/bookTicker/{symbol}/"
               f"{symbol}-bookTicker-{stamp}.zip")
        blob = _get(url)
        if blob is None:
            if verbose:
                print(f"    miss  bookTicker {stamp}", flush=True)
            continue
        csv = _unzip(blob, url, verify=False)   # 200 MB; the sha256 costs more than it buys
        part, _ = _spread_minutes(csv)
        if part is None or part.empty:
            continue
        total += barstore.write_bars(part, name, "1m")
        if verbose:
            print(f"    book  {stamp}  {len(part):>5,} min  "
                  f"median {part['SpreadBps'].median():.2f} bps", flush=True)
        del blob, csv, part
    return total


# ------------------------------------------------------------------ metrics / funding

def fetch_metrics(symbol="BTCUSDT", start="2020-01-01", end=None, verbose=True):
    """Open interest and long/short ratios, 5-minutely. Daily files only, ~12 KB each."""
    end = pd.Timestamp(end) if end else (_utcnow().normalize()
                                         - pd.Timedelta(days=1))
    out = []
    for day in pd.date_range(pd.Timestamp(start), end, freq="D"):
        stamp = day.strftime("%Y-%m-%d")
        url = (f"{BASE}/data/futures/um/daily/metrics/{symbol}/"
               f"{symbol}-metrics-{stamp}.zip")
        blob = _get(url)
        if blob is None:
            continue
        df = pd.read_csv(io.BytesIO(_unzip(blob, url, verify=False)))
        df["ts"] = pd.to_datetime(df["create_time"])
        out.append(df.set_index("ts").drop(columns=["create_time", "symbol"]))
        if verbose and len(out) % 100 == 0:
            print(f"    metrics {stamp}  {len(out)} days", flush=True)
    if not out:
        return None
    df = pd.concat(out).apply(pd.to_numeric, errors="coerce")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    path = os.path.join(DATA_DIR, f"{symbol}_metrics_5m.parquet")
    _atomic_parquet(df, path)
    return df


def fetch_funding(symbol="BTCUSDT", start="2019-09-01", end=None, verbose=True):
    """Perp funding settlements from the archive rather than 1000-row REST pages."""
    end = pd.Timestamp(end) if end else _utcnow()
    out = []
    for kind, when in _periods(start, end):
        stamp = when.strftime("%Y-%m" if kind == "monthly" else "%Y-%m-%d")
        url = (f"{BASE}/data/futures/um/{kind}/fundingRate/{symbol}/"
               f"{symbol}-fundingRate-{stamp}.zip")
        blob = _get(url)
        if blob is None:
            continue
        df = pd.read_csv(io.BytesIO(_unzip(blob, url, verify=False)))
        df.columns = [c.strip() for c in df.columns]
        tcol = "calc_time" if "calc_time" in df.columns else df.columns[0]
        df["ts"] = _to_datetime(df[tcol])
        keep = [c for c in ("last_funding_rate", "funding_interval_hours") if c in df.columns]
        out.append(df.set_index("ts")[keep])
    if not out:
        return None
    df = pd.concat(out).apply(pd.to_numeric, errors="coerce")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    _atomic_parquet(df, os.path.join(DATA_DIR, f"{symbol}_fundingRate.parquet"))
    return df


# ------------------------------------------------------------------ cli

def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("dataset", choices=["klines", "book", "metrics", "funding"])
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--freq", default="1m")
    p.add_argument("--market", default="spot", choices=["spot", "um", "cm"])
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--days", type=int, default=90, help="bookTicker window length")
    p.add_argument("--no-verify", action="store_true")
    a = p.parse_args()

    if a.dataset == "klines":
        n = fetch_klines(a.symbol, a.freq, a.market,
                         start=a.start or "2017-08-17", end=a.end, verify=not a.no_verify)
        print(f"\n{a.symbol} {a.freq} {a.market}: {n:,} bars in store")
        print(barstore.coverage(a.symbol, a.freq))
    elif a.dataset == "book":
        n = fetch_book_spreads(a.symbol, start=a.start, end=a.end, days=a.days)
        print(f"\n{a.symbol}_book 1m: {n:,} minutes")
    elif a.dataset == "metrics":
        df = fetch_metrics(a.symbol, start=a.start or "2020-01-01", end=a.end)
        print(df.tail() if df is not None else "no metrics")
    else:
        df = fetch_funding(a.symbol, start=a.start or "2019-09-01", end=a.end)
        print(df.tail() if df is not None else "no funding")


if __name__ == "__main__":
    main()
