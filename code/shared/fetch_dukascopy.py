"""Tick-level FX from Dukascopy's public datafeed, aggregated to bid/ask bars.

Why this replaces yfinance `=X` for FX research:

  * `=X` is an *indicative* feed with no bid/ask and no volume, so every cost assumption
    made against it is a guess. `calendar-flow-ensemble` lived or died on whether the
    true cost was 2 bp or 10 bp (net Sharpe 0.35 vs -1.03) and the data could not answer.
    Dukascopy ships the actual two-sided ECN quote, so the spread becomes a measurement.
  * `=X` daily rows are stamped a day late -- the row stamped D is the close at 00:00 UTC
    on D, covering UTC day D-1, so the Monday row is Friday's session (see
    `past_research/fx-majors/calendar-flow-ensemble/`, and the +-22 Sharpe that a naive
    alignment against US closes manufactures). Ticks carry their own UTC stamp, so bars
    built here cover exactly the window they are labelled with and need no lag rule.

Wire format, confirmed against the live feed rather than assumed:

    https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM}/{DD}/{HH}h_ticks.bi5

  * **MM is 0-indexed** (00 = January); DD and HH are not. Verified by the weekend hole:
    2024/00/06 and 2024/00/07 are empty (Sat/Sun 6-7 Jan) while 00/05 and 00/08 are not.
  * The body is LZMA, decompressing to 20-byte big-endian records
    `(ms_since_hour, ask_points, bid_points, ask_volume, bid_volume)` as `>IIIff`.
  * Prices are integers in *points*: divide by 10**digits, where digits is 3 for
    JPY-quoted pairs and 5 for the rest. Checked: EURUSD 110150 -> 1.10150 and
    USDJPY 141558 -> 141.558 on 2024-01-02.
  * A missing hour is a 0-byte 200, not a 404 -- weekends and holidays look like success.

Output goes to the partitioned store in `bars.py` as OHLC on the **mid**, plus the
columns that make honest costing possible:

    Open High Low Close   mid, so a return series is spread-neutral
    Bid Ask               last quote of the bar
    Spread SpreadBps      time-weighted average spread over the bar
    Ticks                 quote count, the liquidity proxy `=X` never had
    Volume                Dukascopy's indicative bid+ask volume
"""
import argparse
import concurrent.futures as cf
import lzma
import os
import random
import struct
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bars as barstore
import research_lib

BASE = "https://datafeed.dukascopy.com/datafeed"
UA = {"User-Agent": "autoquant-research/1.0"}
_REC = struct.Struct(">IIIff")

#: The seven majors the fx-majors brief trades, in Dukascopy's naming.
MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]

#: Dukascopy history is thin before this for most pairs; the feed starts ~2003.
DEFAULT_START = "2010-01-01"


def digits(symbol):
    """Decimal places in the quote: JPY crosses print 3, everything else 5."""
    return 3 if symbol.upper().endswith("JPY") else 5


def _url(symbol, when, hour):
    return (f"{BASE}/{symbol.upper()}/{when.year:04d}/{when.month - 1:02d}/"
            f"{when.day:02d}/{hour:02d}h_ticks.bi5")


def _get(url, tries=7, timeout=60):
    """bytes, or None when the hour is not published. Empty body = market closed.

    The feed throttles hard: a handful of parallel requests earns a 503, and hammering
    through it earns a longer one. Backoff is exponential with jitter, and 503/429 wait
    noticeably longer than a transport blip, because the server is asking us to slow
    down rather than reporting a fault.
    """
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            last = e
            wait = (3.0 if e.code in (429, 503) else 1.0) * (2 ** attempt)
        except Exception as e:  # noqa: BLE001 -- transient, retried
            last = e
            wait = 1.0 * (2 ** attempt)
        time.sleep(min(wait, 45.0) * (0.6 + 0.8 * random.random()))
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


def decode_ticks(blob, symbol, hour_start):
    """bi5 bytes -> DataFrame(ts, bid, ask, bid_vol, ask_vol). Empty body -> empty frame."""
    cols = ["bid", "ask", "bid_vol", "ask_vol"]
    if not blob:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="ts"))
    raw = lzma.decompress(blob)
    n = len(raw) // _REC.size
    if n == 0:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="ts"))
    arr = np.frombuffer(raw[: n * _REC.size], dtype=">u4,>u4,>u4,>f4,>f4")
    scale = 10.0 ** digits(symbol)
    ts = pd.Timestamp(hour_start) + pd.to_timedelta(arr["f0"].astype("int64"), unit="ms")
    out = pd.DataFrame({
        "bid": arr["f2"].astype("float64") / scale,
        "ask": arr["f1"].astype("float64") / scale,
        "bid_vol": arr["f4"].astype("float64"),
        "ask_vol": arr["f3"].astype("float64"),
    }, index=pd.DatetimeIndex(ts, name="ts"))
    return out.sort_index()


def ticks_to_bars(ticks, freq="1m"):
    """Tick quotes -> OHLC-on-mid bars with a time-weighted spread.

    Time-weighted, not a plain mean over ticks: quotes arrive in bursts exactly when the
    book is widest, so averaging over ticks reports a market more expensive than the one
    that was actually tradable. The last tick of the bar has no successor inside it and
    is weighted by the remainder to the bar close.
    """
    if ticks.empty:
        return pd.DataFrame()
    step = pd.Timedelta(seconds=barstore.freq_seconds(freq))
    pf = barstore.pandas_freq(freq)

    t = ticks.index
    bucket = t.floor(pf)
    nxt = pd.Series(t, index=t).shift(-1)
    bar_end = bucket + step
    # Weight = time to the next tick, clipped at the bar boundary so no weight leaks
    # across bars; the final tick of each bar runs to that bar's close.
    end = pd.Series(np.minimum(nxt.values.astype("datetime64[ns]"),
                               bar_end.values.astype("datetime64[ns]")), index=t)
    end = end.fillna(pd.Series(bar_end, index=t))
    w = (end - pd.Series(t, index=t)).dt.total_seconds().clip(lower=0).values

    mid = (ticks["bid"] + ticks["ask"]).values / 2.0
    spread = (ticks["ask"] - ticks["bid"]).values
    g = pd.DataFrame({
        "b": bucket, "mid": mid, "spread": spread,
        "bid": ticks["bid"].values, "ask": ticks["ask"].values,
        "vol": (ticks["bid_vol"] + ticks["ask_vol"]).values,
        "w": w, "sw": spread * w, "bw": np.where(mid > 0, spread / mid * 1e4, np.nan) * w,
    })
    a = g.groupby("b").agg(
        Open=("mid", "first"), High=("mid", "max"), Low=("mid", "min"), Close=("mid", "last"),
        Bid=("bid", "last"), Ask=("ask", "last"), Volume=("vol", "sum"),
        Ticks=("mid", "size"), _sw=("sw", "sum"), _bw=("bw", "sum"), _w=("w", "sum"))
    wsum = a["_w"].replace(0.0, np.nan)
    a["Spread"] = a["_sw"] / wsum
    a["SpreadBps"] = a["_bw"] / wsum
    a.index.name = "ts"
    return a.drop(columns=["_sw", "_bw", "_w"])


def fetch_day(symbol, day, workers=4):
    """All 24 hourly tick files for one UTC day, fetched concurrently."""
    day = pd.Timestamp(day).normalize()
    frames = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_get, _url(symbol, day, h)): h for h in range(24)}
        for fut in cf.as_completed(futs):
            h = futs[fut]
            blob = fut.result()
            if blob:
                frames.append(decode_ticks(blob, symbol, day + pd.Timedelta(hours=h)))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def fetch_fx_bars(symbol="EURUSD", start=DEFAULT_START, end=None, freq="1m",
                  workers=4, verbose=True, flush_every=20):
    """Build `freq` bid/ask bars for `symbol` over [start, end] into the bar store.

    Skips days already present, so an interrupted pull resumes rather than restarting.
    """
    end = pd.Timestamp(end) if end else (pd.Timestamp.now("UTC").tz_convert(None)
                                         .normalize() - pd.Timedelta(days=1))
    start = pd.Timestamp(start)
    have = set()
    for y in barstore.cached_years(symbol, freq):
        idx = barstore.load_bars(symbol, freq, start=f"{y}-01-01",
                                 end=f"{y}-12-31 23:59:59").index
        have |= set(pd.DatetimeIndex(idx).normalize().unique())

    buf, total, done = [], 0, 0
    for day in pd.date_range(start, end, freq="D"):
        if day.dayofweek == 5:                      # Saturday: the feed is closed all day
            continue
        if day in have:
            continue
        ticks = fetch_day(symbol, day, workers=workers)
        if ticks.empty:
            continue
        bar = ticks_to_bars(ticks, freq)
        if bar.empty:
            continue
        buf.append(bar)
        done += 1
        if verbose and done % 20 == 0:
            print(f"    {symbol} {day.date()}  {len(bar):>5} bars  "
                  f"median spread {bar['SpreadBps'].median():.2f} bps", flush=True)
        if len(buf) >= flush_every:
            total += barstore.write_bars(pd.concat(buf), symbol, freq)
            buf = []
    if buf:
        total += barstore.write_bars(pd.concat(buf), symbol, freq)
    return total


# ------------------------------------------------------------------ raw ticks

def _write_ticks(df, path):
    """Ticks -> zstd parquet, delta-packed stamps. Empty frames are written too: an empty
    day file is how a holiday is remembered as done rather than re-fetched forever."""
    out = df.reset_index()
    out["ts"] = out["ts"].astype("datetime64[us]")
    out = out.astype({"bid": "float64", "ask": "float64",
                      "bid_vol": "float32", "ask_vol": "float32"})
    tmp = f"{path}.{os.getpid()}.tmp"
    out.to_parquet(tmp, index=False, compression="zstd",
                   use_dictionary=["bid", "ask", "bid_vol", "ask_vol"],
                   column_encoding={"ts": "DELTA_BINARY_PACKED"})
    os.replace(tmp, path)


def fetch_fx_ticks(symbol="EURUSD", start=DEFAULT_START, end=None, freq="1m",
                   workers=1, verbose=True):
    """Every tick for `symbol` into the tick store, plus `freq` bars into the bar store.

    One crawl, both products: the ~24 requests a day cost is the throttle, not the disk,
    so the raw ticks are kept rather than thrown away after barring. Resumable at day
    granularity -- each day lands in `<SYMBOL>/.partial/` as it is fetched, and a month is
    consolidated into `<YYYY-MM>.parquet` (and barred) only once every weekday in it is
    present. A day that exhausts the retries is logged and left missing, so the next run
    picks it up instead of the crawl dying three weeks in.
    """
    import ticks as tickstore

    sym = symbol.upper()
    out_dir = tickstore.fx_ticks_dir(sym)
    part_dir = os.path.join(out_dir, ".partial")
    os.makedirs(part_dir, exist_ok=True)
    today = pd.Timestamp.now("UTC").tz_convert(None).normalize()
    end = min(pd.Timestamp(end), today - pd.Timedelta(days=1)) if end else today - pd.Timedelta(days=1)
    have = set(tickstore.cached_months(out_dir))

    # Newest first: at the throttled rate a full crawl takes months, and recent years
    # are the ones research reaches for first.
    months = pd.period_range(pd.Timestamp(start), end, freq="M")[::-1]
    written = 0
    for per in months:
        m = str(per)
        if m in have:
            continue
        days = pd.date_range(max(per.start_time, pd.Timestamp(start)),
                             min(per.end_time.normalize(), end), freq="D")
        days = days[days.dayofweek != 5]            # Saturday: the feed is closed all day
        failed = 0
        for day in days:
            p = os.path.join(part_dir, f"{day:%Y-%m-%d}.parquet")
            if os.path.exists(p):
                continue
            try:
                t = fetch_day(sym, day, workers=workers)
            except RuntimeError as e:
                failed += 1
                print(f"    {sym} {day.date()}: FAILED, will retry next run ({e})", flush=True)
                continue
            if t.empty:
                t = decode_ticks(b"", sym, day)
            _write_ticks(t, p)
        month_closed = per.end_time.normalize() <= end
        if failed or not month_closed:
            continue
        parts = [os.path.join(part_dir, f"{d:%Y-%m-%d}.parquet") for d in days]
        frames = [pd.read_parquet(p) for p in parts]
        month = pd.concat([f for f in frames if len(f)], ignore_index=True) \
            if any(len(f) for f in frames) else frames[0]
        month = month.set_index("ts").sort_index()
        _write_ticks(month, os.path.join(out_dir, f"{m}.parquet"))
        bar = ticks_to_bars(month.astype("float64"), freq) if len(month) else pd.DataFrame()
        if len(bar):
            barstore.write_bars(bar, sym, freq)
        for p in parts:
            os.remove(p)
        written += 1
        if verbose:
            mb = os.path.getsize(os.path.join(out_dir, f"{m}.parquet")) / 1e6
            med = bar["SpreadBps"].median() if len(bar) else float("nan")
            print(f"    {sym} {m}: {len(month):>10,} ticks  {mb:6.1f} MB  "
                  f"{len(bar):>6,} bars  median spread {med:.2f} bps", flush=True)
    return written


# ------------------------------------------------------------------ spread profile

def sample_days(start, end, per_quarter=5, seed=7):
    """A stratified sample of weekdays: `per_quarter` days from each calendar quarter.

    The full tick history is not reachable from a throttled free feed -- seven majors
    over sixteen years is ~700k hourly files, which at the rate this server grants is
    measured in days of wall clock. But the question the spread data has to answer is
    distributional ("what did it actually cost to trade EURUSD at 03:00 in 2015"), and a
    stratified sample answers that to well inside the precision any cost model needs.

    Stratifying by quarter rather than sampling uniformly keeps the crisis periods --
    2015 SNB, 2016 Brexit, 2020 March -- from being crowded out by calm years, which is
    exactly where a flat cost assumption does its damage.
    """
    rng = np.random.default_rng(seed)
    days = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")
    days = days[days.dayofweek < 5]
    out = []
    for _, grp in pd.Series(days, index=days).groupby(days.to_period("Q")):
        idx = grp.index
        take = min(per_quarter, len(idx))
        out.extend(pd.DatetimeIndex(rng.choice(idx.values, size=take, replace=False)))
    return pd.DatetimeIndex(sorted(out))


def fetch_spread_profile(symbols=None, start="2012-01-01", end=None, per_quarter=4,
                         workers=4, verbose=True, out_name="fx_spread_profile"):
    """Measure the real cost of trading FX, by pair, year and hour of day.

    Writes `data/<out_name>.parquet` with one row per (symbol, year, hour) carrying the
    median, mean and 90th-percentile spread in bps plus the tick count behind it. That
    table is what replaces a flat "2 bp per side" guess -- which, measured against
    EURUSD, is roughly eight times the real median spread, and is wrong in both
    directions: far too punitive in the London session and far too generous at 22:00 UTC
    or through a Brexit-night gap.
    """
    symbols = symbols or MAJORS
    end = pd.Timestamp(end) if end else (pd.Timestamp.now("UTC").tz_convert(None).normalize()
                                         - pd.Timedelta(days=1))
    days = sample_days(start, end, per_quarter=per_quarter)
    rows = []
    for sym in symbols:
        got = 0
        for day in days:
            try:
                ticks = fetch_day(sym, day, workers=workers)
            except RuntimeError as e:
                if verbose:
                    print(f"    {sym} {day.date()} unavailable: {e}", flush=True)
                continue
            if ticks.empty:
                continue
            mid = (ticks["bid"] + ticks["ask"]) / 2.0
            bps = (ticks["ask"] - ticks["bid"]) / mid * 1e4
            f = pd.DataFrame({"bps": bps.values, "hour": ticks.index.hour,
                              "year": ticks.index.year})
            rows.append(f.assign(symbol=sym))
            got += 1
            if verbose and got % 10 == 0:
                print(f"    {sym} {day.date()}  {got}/{len(days)} days  "
                      f"median {bps.median():.3f} bps", flush=True)
        if verbose:
            print(f"  {sym}: {got} sampled days", flush=True)
    if not rows:
        return None
    allt = pd.concat(rows, ignore_index=True)
    prof = (allt.groupby(["symbol", "year", "hour"])["bps"]
                .agg(median="median", mean="mean",
                     p90=lambda x: x.quantile(0.90), ticks="size")
                .reset_index())
    path = os.path.join(research_lib.DATA_DIR, f"{out_name}.parquet")
    research_lib._atomic_parquet(prof, path)
    return prof


def spread_bps(symbol, when, profile=None):
    """Measured spread in bps for `symbol` at `when`, from the sampled profile.

    Falls back to the symbol's all-period median for an hour never sampled, and raises
    if the profile has not been built -- silently substituting a guess for a measurement
    is the failure this whole module exists to remove.
    """
    if profile is None:
        path = os.path.join(research_lib.DATA_DIR, "fx_spread_profile.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(
                "no spread profile cached; run "
                "`python code/shared/fetch_dukascopy.py profile`")
        profile = pd.read_parquet(path)
    t = pd.Timestamp(when)
    sub = profile[profile["symbol"] == symbol.upper()]
    if sub.empty:
        raise KeyError(f"{symbol} not in spread profile")
    hit = sub[(sub["year"] == t.year) & (sub["hour"] == t.hour)]
    if len(hit):
        return float(hit["median"].iloc[0])
    hit = sub[sub["hour"] == t.hour]
    return float(hit["median"].median() if len(hit) else sub["median"].median())


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("mode", nargs="?", default="bars", choices=["bars", "ticks", "profile"],
                   help="'bars' backfills 1m bid/ask bars (slow: ~24 requests per pair "
                        "per day); 'ticks' does the same crawl but also keeps every tick "
                        "in the tick store (see ticks.py); 'profile' samples days to "
                        "measure the spread curve")
    p.add_argument("--symbols", default=",".join(MAJORS))
    p.add_argument("--start", default=DEFAULT_START)
    p.add_argument("--end", default=None)
    p.add_argument("--freq", default="1m")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--per-quarter", type=int, default=4,
                   help="profile mode: days sampled from each calendar quarter")
    a = p.parse_args()
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]

    if a.mode == "profile":
        prof = fetch_spread_profile(syms, start=a.start, end=a.end,
                                    per_quarter=a.per_quarter, workers=a.workers)
        if prof is None:
            print("no data sampled")
            return
        print(prof.groupby("symbol")["median"].describe()[["mean", "50%", "max"]])
        return

    if a.mode == "ticks":
        for sym in syms:
            print(f"== {sym}", flush=True)
            n = fetch_fx_ticks(sym, start=a.start, end=a.end, freq=a.freq,
                               workers=a.workers)
            print(f"   {sym}: {n} months consolidated", flush=True)
        return

    for sym in syms:
        print(f"== {sym}", flush=True)
        n = fetch_fx_bars(sym, start=a.start, end=a.end, freq=a.freq, workers=a.workers)
        print(f"   {sym}: {n:,} bars", flush=True)
        print("  ", barstore.coverage(sym, a.freq), flush=True)


if __name__ == "__main__":
    main()
