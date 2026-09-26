"""Tick store: raw trades and quotes on the dedicated ext4 disk, one parquet per month.

The bar store (`bars.py`) lives on the distro's own disk, whose VHDX sits on C:. Ticks are
two orders of magnitude bigger -- BTCUSDT aggTrades alone are ~30 GB of parquet -- so they
live on their own virtual disk on D:, set up by `ticks_disk.ps1`:

    D:\\WSL\\autoquant-ticks.vhdx  ->  /mnt/wsl/autoquant-ticks  <-  data/ticks (symlink)

Layout:

    data/ticks/binance/<spot|um>/aggTrades/<SYMBOL>/<YYYY-MM>.parquet
        ts           timestamp[us], UTC, tz-naive -- the trade time
        price, qty   float64
        buyer_maker  bool; True means the taker SOLD (the resting bid was the maker)
        n_trades     int32, raw fills merged into this aggregate (same price, same taker)
        agg_id       int64, Binance's aggregate-trade id, contiguous within a market

    data/ticks/dukascopy/<SYMBOL>/<YYYY-MM>.parquet
        ts, bid, ask, bid_vol, ask_vol   -- every top-of-book change

Only closed months are written as `<YYYY-MM>.parquet`; an in-progress Dukascopy crawl keeps
per-day files under `<SYMBOL>/.partial/` until the month completes.

**The mount guard is load-bearing.** When the disk is not attached (after `wsl --shutdown`,
before the logon task has run), `/mnt/wsl` is a *tmpfs*: a fetcher that wrote there would
fill RAM, and a loader would see an empty store and report "no data" as if it were a fact.
`ticks_root()` refuses both. Remount with `schtasks.exe /run /tn "autoQuant ticks disk"`.
`AQ_TICKS_DIR` overrides the location (tests, one-off scratch pulls) and skips the check.
"""
import glob
import os
import re

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import bars as barstore
import research_lib

REMOUNT_HINT = 'schtasks.exe /run /tn "autoQuant ticks disk"'


class TickStoreUnavailable(RuntimeError):
    pass


def ticks_root(create=False):
    """Absolute path of the tick store, or raise if the backing disk is not mounted."""
    override = os.environ.get("AQ_TICKS_DIR")
    if override:
        if create:
            os.makedirs(override, exist_ok=True)
        return override
    link = os.path.join(research_lib.DATA_DIR, "ticks")
    real = os.path.realpath(link)
    if not os.path.ismount(real):
        raise TickStoreUnavailable(
            f"tick disk not mounted at {real} (data/ticks -> {real}). "
            f"Remount from WSL with: {REMOUNT_HINT}")
    return real


def aggtrades_dir(symbol, market="um"):
    return os.path.join(ticks_root(), "binance", market, "aggTrades", symbol.upper())


def fx_ticks_dir(symbol):
    return os.path.join(ticks_root(), "dukascopy", symbol.upper())


def month_path(directory, month):
    return os.path.join(directory, f"{pd.Timestamp(month):%Y-%m}.parquet")


def cached_months(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(f[:7] for f in os.listdir(directory)
                  if re.match(r"^\d{4}-\d{2}\.parquet$", f))


def _load_months(directory, start=None, end=None, columns=None):
    """Concatenate the month files overlapping [start, end], trimmed to the window."""
    lo = pd.Timestamp(start) if start is not None else None
    hi = pd.Timestamp(end) if end is not None else None
    files = []
    for m in cached_months(directory):
        ms = pd.Timestamp(m + "-01")
        me = ms + pd.offsets.MonthBegin(1)
        if (lo is None or me > lo) and (hi is None or ms <= hi):
            files.append(os.path.join(directory, m + ".parquet"))
    if not files:
        return pd.DataFrame()
    cols = None if columns is None else ["ts"] + [c for c in columns if c != "ts"]
    df = pd.concat([pq.read_table(f, columns=cols).to_pandas() for f in files],
                   ignore_index=True)
    df = df.set_index("ts")
    if lo is not None:
        df = df[df.index >= lo]
    if hi is not None:
        df = df[df.index <= hi]
    return df


def load_aggtrades(symbol, market="um", start=None, end=None, columns=None):
    """Binance aggregate trades for `symbol`, indexed by trade time. Reads only months in range.

    A full month of BTCUSDT is ~40M rows (~1.5 GB in memory) -- pass a window.
    """
    return _load_months(aggtrades_dir(symbol, market), start, end, columns)


def load_fx_ticks(symbol, start=None, end=None, columns=None):
    """Dukascopy bid/ask ticks for `symbol`, closed months only."""
    return _load_months(fx_ticks_dir(symbol), start, end, columns)


# ------------------------------------------------------------------ trades -> bars

def flow_bars(trades, freq="1m"):
    """Aggregate trades -> OHLCV bars in the same schema as Binance klines.

    Columns: Open High Low Close Volume qv n tb tq -- identical meaning to the kline
    archive (`tb`/`tq` = taker-BUY base/quote volume), so a flow bar and a kline bar are
    interchangeable downstream and `bars.resample_bars` coarsens them correctly. VWAP is
    `qv / Volume`; it is not stored because averaging it on resample would be wrong.

    Accepts sub-minute frequencies ('1s', '5s', ...) for on-the-fly use; those are not
    cached in the bar store.
    """
    if trades.empty:
        return pd.DataFrame()
    px = trades["price"].to_numpy()
    q = trades["qty"].to_numpy()
    buy = ~trades["buyer_maker"].to_numpy(dtype=bool)
    n = trades["n_trades"].to_numpy() if "n_trades" in trades else np.ones(len(trades))
    g = pd.DataFrame({
        "b": trades.index.floor(barstore.pandas_freq(freq)),
        "px": px, "q": q, "qv": px * q, "n": n,
        "tb": np.where(buy, q, 0.0), "tq": np.where(buy, px * q, 0.0),
    })
    out = g.groupby("b", sort=True).agg(
        Open=("px", "first"), High=("px", "max"), Low=("px", "min"), Close=("px", "last"),
        Volume=("q", "sum"), qv=("qv", "sum"), n=("n", "sum"),
        tb=("tb", "sum"), tq=("tq", "sum"))
    out.index.name = "ts"
    out["n"] = out["n"].astype("int64")
    return out


def bar_symbol(symbol, market):
    """Bar-store name for a market: perps carry `_PERP`, as the 1h store already does."""
    return f"{symbol.upper()}_PERP" if market == "um" else symbol.upper()


def build_flow_bars(symbol, market="um", freq="1m", rebuild=False, verbose=True):
    """Materialise `freq` flow bars for every cached aggTrades month into the bar store.

    Month by month, so memory stays at one month of trades. Months whose bars are already
    present are skipped unless `rebuild`.
    """
    d = aggtrades_dir(symbol, market)
    name = bar_symbol(symbol, market)
    have = set()
    if not rebuild:
        for y in barstore.cached_years(name, freq):
            idx = barstore.load_bars(name, freq, start=f"{y}-01-01",
                                     end=f"{y}-12-31 23:59:59", columns=["Close"]).index
            have |= set(pd.DatetimeIndex(idx).strftime("%Y-%m").unique())
    total = 0
    for m in cached_months(d):
        if m in have:
            continue
        t = pq.read_table(month_path(d, m + "-01"),
                          columns=["ts", "price", "qty", "buyer_maker", "n_trades"]).to_pandas()
        b = flow_bars(t.set_index("ts"), freq)
        total += len(b)
        barstore.write_bars(b, name, freq)
        if verbose:
            print(f"    {name} {freq} {m}: {len(b):>6,} bars from {len(t):>11,} trades",
                  flush=True)
    return total


def summary():
    """What is in the tick store: rows are (source, market, symbol, months, first, last, GB)."""
    root = ticks_root()
    rows = []
    for d in sorted(glob.glob(os.path.join(root, "binance", "*", "aggTrades", "*"))
                    + glob.glob(os.path.join(root, "dukascopy", "*"))):
        ms = cached_months(d)
        if not ms:
            continue
        size = sum(os.path.getsize(os.path.join(d, m + ".parquet")) for m in ms)
        parts = os.path.relpath(d, root).split(os.sep)
        rows.append({"source": parts[0], "market": parts[1] if parts[0] == "binance" else "fx",
                     "symbol": parts[-1], "months": len(ms), "first": ms[0], "last": ms[-1],
                     "GB": round(size / 1e9, 2)})
    return pd.DataFrame(rows)
