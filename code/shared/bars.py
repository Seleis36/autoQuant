"""Frequency-aware bar store for the shared `data/` cache.

The flat one-file-per-ticker layout in `research_lib` is right for daily series -- four
thousand rows, one small parquet, read it all every time. It falls over at 1m. BTCUSDT
alone is ~4.7M minutes since 2017 and a G10 FX universe at 1m is north of 100M rows, so
a backtest that wants 2023 onward should not be decompressing 2017.

Layout:

    data/bars/<SYMBOL>/<freq>/<year>.parquet

Conventions, identical to the flat cache and to `harness/live_lib`:

  * the index is the bar OPEN time, UTC, tz-naive;
  * a bar stamped t covers [t, t + freq);
  * `Open/High/Low/Close/Volume` are always present. Extra columns (spread, tick counts,
    taker flow) ride alongside and survive a round trip.

Resampling is always left-labelled and left-closed, so the 1m bar stamped 09:00 lands in
the 1h bar stamped 09:00 and never in the one stamped 08:00. Getting that backwards
shifts every signal one bar into the future, which is the one bug this file exists to
make impossible to write by accident.

`DATA_DIR` is read from `research_lib` at call time rather than bound at import, so the
three modules that write this directory -- research, the live runners, and these
fetchers -- can never disagree about where it is.
"""
import os
import re

import numpy as np
import pandas as pd

import research_lib

#: Aggregations that make an OHLCV bar out of finer bars. Extra columns not listed here
#: are summed if they look like counts and averaged otherwise -- see `_agg_for`.
_OHLCV_AGG = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
}

#: Columns that are counts or quantities and must be summed, not averaged, when
#: coarsening. `n` is trade count, `qv` quote volume, `tb`/`tq` taker-buy base/quote.
_SUM_COLS = {"Volume", "qv", "n", "tb", "tq", "Ticks", "BidVol", "AskVol"}

#: Columns that are levels or ratios and must be averaged. Spread in particular: the
#: mean spread over an hour is meaningful, the sum of sixty spreads is not.
_MEAN_COLS = {"Spread", "SpreadBps", "Bid", "Ask", "OpenInterest", "Mid"}

_FREQ_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200,
    "1d": 86400,
}


def _data_dir():
    """Resolved late so `monkeypatch.setattr(research_lib, "DATA_DIR", ...)` reaches us."""
    return research_lib.DATA_DIR


def freq_seconds(freq):
    if freq not in _FREQ_SECONDS:
        raise ValueError(f"unsupported freq {freq!r}; use one of {sorted(_FREQ_SECONDS)}")
    return _FREQ_SECONDS[freq]


def pandas_freq(freq):
    """'1m' -> '1min'. pandas renamed the minute alias; 'T'/'M' are ambiguous."""
    freq_seconds(freq)
    n, unit = re.match(r"^(\d+)([mhd])$", freq).groups()
    return f"{n}{'min' if unit == 'm' else unit}"


def safe_symbol(symbol):
    """Filesystem-safe symbol, byte-identical in intent to `research_lib.daily_cache_path`.

    `EURUSD=X` and `^GSPC` must not create surprise directories, and the mapping has to
    be stable: a symbol that round-trips to a different directory next release orphans
    every bar already cached under the old name.
    """
    return symbol.replace("-", "_").replace("^", "IDX_").replace("=", "_").replace("/", "_")


def bars_dir(symbol, freq):
    freq_seconds(freq)
    return os.path.join(_data_dir(), "bars", safe_symbol(symbol), freq)


def bars_path(symbol, freq, year):
    return os.path.join(bars_dir(symbol, freq), f"{int(year)}.parquet")


def cached_years(symbol, freq):
    d = bars_dir(symbol, freq)
    if not os.path.isdir(d):
        return []
    out = []
    for f in os.listdir(d):
        m = re.match(r"^(\d{4})\.parquet$", f)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def _normalise(df):
    """Tz-naive UTC index, sorted, no duplicate stamps, float columns."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError(f"bars need a DatetimeIndex, got {type(df.index).__name__}")
    idx = df.index
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    df = df.copy()
    df.index = idx
    df.index.name = "ts"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def snap_to_grid(df, freq):
    """Floor bar stamps onto the frequency grid, keeping the last row per slot.

    The store's contract is that a bar stamped t covers [t, t + freq). Binance's own
    archive violates it: ~21.6k bars in late 2017 / early 2018 carry stamps like
    `06:00:20.799` instead of `06:00:00`, and the sub-minute offset differs *per symbol*
    (BTCUSDT .799 against ETHUSDT .810 for the same minute). Left alone, those rows look
    like gaps to `coverage`, and -- worse -- any cross-symbol join on timestamp drops
    them silently on both sides, because .799 != .810.

    Flooring is the honest repair: the exchange-side jitter is noise about which minute
    the bar belongs to, and it always belongs to the one it starts in.
    """
    if df.empty:
        return df
    snapped = df.index.floor(pandas_freq(freq))
    if (snapped == df.index).all():
        return df
    df = df.copy()
    df.index = snapped
    df.index.name = "ts"
    return df[~df.index.duplicated(keep="last")].sort_index()


def write_bars(df, symbol, freq, merge=True, snap=True):
    """Write `df` into the per-year partitions for (symbol, freq).

    With `merge` (the default) an existing partition is read, concatenated and
    de-duplicated keep-last, so a re-fetch of an overlapping window corrects old rows
    instead of duplicating them. Each partition lands through `_atomic_parquet`, because
    a research agent and a live runner do read this tree concurrently.

    `snap` floors stamps onto the frequency grid -- see `snap_to_grid` for the exchange
    quirk that makes this load-bearing rather than cosmetic.
    """
    df = _normalise(df)
    if snap:
        df = snap_to_grid(df, freq)
    if df.empty:
        return 0
    os.makedirs(bars_dir(symbol, freq), exist_ok=True)
    written = 0
    for year, chunk in df.groupby(df.index.year):
        path = bars_path(symbol, freq, year)
        if merge and os.path.exists(path):
            old = _normalise(pd.read_parquet(path))
            chunk = pd.concat([old, chunk])
            chunk = chunk[~chunk.index.duplicated(keep="last")].sort_index()
        research_lib._atomic_parquet(chunk, path)
        written += len(chunk)
    return written


def load_bars(symbol, freq, start=None, end=None, columns=None, resample_from=None):
    """Load bars for `symbol` at `freq`, reading only the year partitions in range.

    `resample_from` coarsens on the fly from a finer cached frequency, so a daily study
    can run off the 1m store without a second copy on disk:

        load_bars("BTCUSDT", "1h", resample_from="1m")

    Returns an empty frame with the standard columns when nothing is cached, so callers
    can branch on `.empty` rather than catching FileNotFoundError.
    """
    if resample_from is not None:
        fine = load_bars(symbol, resample_from, start=start, end=end)
        if fine.empty:
            return fine
        return resample_bars(fine, freq)

    years = cached_years(symbol, freq)
    if start is not None:
        y0 = pd.Timestamp(start).year
        years = [y for y in years if y >= y0]
    if end is not None:
        y1 = pd.Timestamp(end).year
        years = [y for y in years if y <= y1]
    if not years:
        return pd.DataFrame(columns=list(_OHLCV_AGG),
                            index=pd.DatetimeIndex([], name="ts"))

    frames = [pd.read_parquet(bars_path(symbol, freq, y), columns=columns) for y in years]
    df = _normalise(pd.concat(frames))
    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.index <= pd.Timestamp(end)]
    return df


def _agg_for(columns):
    agg = {}
    for c in columns:
        if c in _OHLCV_AGG:
            agg[c] = _OHLCV_AGG[c]
        elif c in _SUM_COLS:
            agg[c] = "sum"
        elif c in _MEAN_COLS:
            agg[c] = "mean"
        else:
            agg[c] = "last"
    return agg


def resample_bars(df, freq, agg=None):
    """Coarsen bars to `freq`, left-labelled and left-closed.

    Empty periods are dropped rather than forward-filled: a synthetic bar across a venue
    outage is indistinguishable from a real one downstream, and every rolling window then
    quietly spans the hole.
    """
    df = _normalise(df)
    if df.empty:
        return df
    a = dict(_agg_for(df.columns))
    if agg:
        a.update(agg)
    out = df.resample(pandas_freq(freq), label="left", closed="left").agg(a)
    return out.dropna(subset=[c for c in ("Close", "Open") if c in out.columns], how="all")


def coverage(symbol, freq, start=None, end=None):
    """Gap report for a cached series: expected vs present bars, and the worst holes.

    Crypto runs 24/7 so a missing minute is a real gap; FX stops over the weekend, so
    `weekend_gaps` is reported separately rather than counted as missing data.
    """
    df = load_bars(symbol, freq, start=start, end=end)
    if df.empty:
        return {"symbol": symbol, "freq": freq, "bars": 0, "start": None, "end": None,
                "missing": None, "pct_present": 0.0, "largest_gaps": []}
    step = pd.Timedelta(seconds=freq_seconds(freq))
    expected = int((df.index[-1] - df.index[0]) / step) + 1
    d = df.index.to_series().diff().dropna()
    holes = d[d > step]
    is_weekend = holes.index.dayofweek.isin([0, 6])  # gap ending Mon or Sun = weekend stop
    largest = sorted(
        ({"at": str(t), "gap": str(v)} for t, v in holes.items()),
        key=lambda r: pd.Timedelta(r["gap"]), reverse=True)[:5]
    return {
        "symbol": symbol, "freq": freq, "bars": len(df),
        "start": str(df.index[0]), "end": str(df.index[-1]),
        "missing": expected - len(df),
        "pct_present": round(100.0 * len(df) / expected, 3),
        "weekend_gaps": int(is_weekend.sum()),
        "largest_gaps": largest,
    }


def available():
    """Every (symbol, freq) pair in the bar store, with its cached year span."""
    root = os.path.join(_data_dir(), "bars")
    if not os.path.isdir(root):
        return pd.DataFrame(columns=["symbol", "freq", "years", "first", "last"])
    rows = []
    for sym in sorted(os.listdir(root)):
        for freq in sorted(os.listdir(os.path.join(root, sym))):
            ys = cached_years(sym, freq)
            if ys:
                rows.append({"symbol": sym, "freq": freq, "years": len(ys),
                             "first": ys[0], "last": ys[-1]})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    av = available()
    if av.empty:
        print("bar store empty -- run code/shared/fetch_binance_vision.py "
              "or code/shared/fetch_dukascopy.py")
        sys.exit(0)
    print(av.to_string(index=False))
    for _, r in av.iterrows():
        c = coverage(r["symbol"], r["freq"])
        print(f"\n{r['symbol']} {r['freq']}: {c['bars']} bars {c['start']} -> {c['end']}"
              f"  present {c['pct_present']}%  missing {c['missing']}"
              f"  weekend-gaps {c.get('weekend_gaps')}")
        for g in c["largest_gaps"]:
            print(f"    gap {g['gap']} at {g['at']}")
