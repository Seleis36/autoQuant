"""Per-venue daily candles for the alt cross-section (public endpoints, no key).

Caches (flat `data/`, one file per instrument):
  data/BINANCE_<SYM>USDT_1d.parquet   Binance spot 1d klines incl. taker-buy volume and trades
  data/COINBASE_<SYM>USD_1d.parquet   Coinbase Exchange 1d candles
  data/UPBIT_KRW<SYM>_d.parquet       Upbit KRW-market 1d candles (same file name as
                                      code/spot-eth/kimchi-froth/fetch_upbit.py writes)

Every bar here is stamped at its OPEN, UTC, tz-naive: the row stamped D covers
[D 00:00, D+1 00:00) UTC and its Close is the price at D+1 00:00 UTC -- the same instant as
the yfinance crypto close stamped D. A signal built from row D may therefore be traded at the
yfinance close of D (research_lib shifts the weight one bar before applying returns).

Binance REST drops delisted symbols; for those `binance_daily` falls back to the monthly
archive on data.binance.vision, which keeps them.
"""
import io, json, os, sys, time, urllib.error, urllib.request, zipfile
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402

UA = {"User-Agent": "autoquant-research/1.0", "accept": "application/json"}

# yfinance ticker -> exchange base symbol, where they differ
BASE_OVERRIDE = {"TON11419-USD": "TON", "RENDER-USD": "RENDER", "SHIB-USD": "SHIB",
                 "BONK-USD": "BONK", "PEPE-USD": "PEPE"}
# Binance renamed a few spot pairs; older history lives under the old symbol
BINANCE_ALIASES = {"RENDER": ["RNDR"], "POL": ["MATIC"]}


def base_of(ticker):
    return BASE_OVERRIDE.get(ticker, ticker.split("-")[0])


def _get(url, tries=6, timeout=30, allow_404=False):
    last = None
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404) and allow_404:
                return None
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.5 * (a + 1))
    raise RuntimeError(f"GET failed: {url}") from last


# ------------------------------------------------------------------ Binance spot 1d

KCOLS = ["ot", "Open", "High", "Low", "Close", "Volume", "ct", "QuoteVolume", "Trades",
         "TakerBuyBase", "TakerBuyQuote", "ig"]


def _klines_frame(rows):
    df = pd.DataFrame(rows, columns=KCOLS)
    df = df[pd.to_numeric(df["ot"], errors="coerce").notna()]
    v = pd.to_numeric(df["ot"]).astype("int64")
    df["ts"] = pd.to_datetime(v.where(v < 1e14, v // 1000), unit="ms")   # archive switched ms -> us in 2025
    df = df.drop(columns=["ot", "ct", "ig"]).set_index("ts").apply(pd.to_numeric, errors="coerce")
    return df


def _binance_rest(sym, start="2017-07-01"):
    out, t = [], int(pd.Timestamp(start).timestamp() * 1000)
    while True:
        b = _get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&startTime={t}&limit=1000",
                 allow_404=True)
        if b is None:
            return None
        rows = json.loads(b)
        if not rows:
            break
        out += rows
        if len(rows) < 1000:
            break
        t = rows[-1][0] + 86_400_000
        time.sleep(0.1)
    return _klines_frame(out) if out else None


def _binance_archive(sym, start="2017-07-01"):
    out = []
    m = pd.Timestamp(start).replace(day=1)
    end = pd.Timestamp.now("UTC").tz_convert(None)
    while m < end:
        stamp = m.strftime("%Y-%m")
        url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/1d/{sym}-1d-{stamp}.zip"
        blob = _get(url, allow_404=True)
        if blob is not None:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                csv = z.read(z.namelist()[0])
            out.append(pd.read_csv(io.BytesIO(csv), header=None, names=KCOLS))
        m = (m + pd.Timedelta(days=32)).replace(day=1)
    if not out:
        return None
    rows = pd.concat(out).values.tolist()
    return _klines_frame(rows)


def binance_path(base):
    return os.path.join(DATA_DIR, f"BINANCE_{base}USDT_1d.parquet")


def binance_daily(base, refresh=False):
    """Binance spot <base>USDT daily klines (Open..Close, Volume in base, QuoteVolume in USDT,
    Trades, TakerBuyBase, TakerBuyQuote). Empty frame if Binance never listed the pair."""
    p = binance_path(base)
    if os.path.exists(p) and not refresh:
        return pd.read_parquet(p)
    parts = []
    for s in [base] + BINANCE_ALIASES.get(base, []):
        sym = f"{s}USDT"
        df = _binance_rest(sym)
        if df is None:
            df = _binance_archive(sym)
        if df is not None and len(df):
            parts.append(df)
    df = (pd.concat(parts[::-1]) if parts else
          pd.DataFrame(columns=KCOLS[1:6] + KCOLS[7:11], index=pd.DatetimeIndex([], name="ts"), dtype=float))
    df = df[~df.index.duplicated(keep="last")].sort_index()
    # the still-open current day is not a finished bar
    today = pd.Timestamp.now("UTC").tz_convert(None).normalize()
    df = df[df.index < today]
    _atomic_parquet(df, p)
    return df


# ------------------------------------------------------------------ Coinbase 1d

def coinbase_path(base):
    return os.path.join(DATA_DIR, f"COINBASE_{base}USD_1d.parquet")


def coinbase_daily(base, refresh=False, start="2016-01-01"):
    p = coinbase_path(base)
    if os.path.exists(p) and not refresh:
        return pd.read_parquet(p)
    out, t0 = [], pd.Timestamp(start)
    end = pd.Timestamp.now("UTC").tz_convert(None).normalize()
    step = pd.Timedelta(days=300)
    while t0 < end:
        t1 = min(t0 + step, end)
        b = _get(f"https://api.exchange.coinbase.com/products/{base}-USD/candles?granularity=86400"
                 f"&start={t0.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={t1.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                 allow_404=True)
        if b is None:
            break
        out += json.loads(b)
        t0 = t1
        time.sleep(0.15)
    df = pd.DataFrame(out, columns=["t", "Low", "High", "Open", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["t"], unit="s")
    df = df.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[df.index < end]
    _atomic_parquet(df, p)
    return df


# ------------------------------------------------------------------ Upbit KRW 1d

def upbit_path(base):
    return os.path.join(DATA_DIR, f"UPBIT_KRW{base}_d.parquet")


def upbit_daily(base, refresh=False, start="2017-09-01"):
    p = upbit_path(base)
    if os.path.exists(p) and not refresh:
        return pd.read_parquet(p)
    out, to = [], None
    market = f"KRW-{base}"
    while True:
        b = _get(f"https://api.upbit.com/v1/candles/days?market={market}&count=200" + (f"&to={to}" if to else ""),
                 allow_404=True)
        rows = json.loads(b) if b else []
        if not rows:
            break
        out += rows
        first = min(r["candle_date_time_utc"] for r in rows)
        if first <= start:
            break
        to = first + "Z"
        time.sleep(0.15)
    if not out:
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "QuoteVolume"])
    else:
        df = pd.DataFrame(out)
        df["ts"] = pd.to_datetime(df["candle_date_time_utc"])
        df = df.set_index("ts").rename(columns={"opening_price": "Open", "high_price": "High", "low_price": "Low",
                                                "trade_price": "Close", "candle_acc_trade_price": "QuoteVolume",
                                                "candle_acc_trade_volume": "Volume"})
        df = df[["Open", "High", "Low", "Close", "Volume", "QuoteVolume"]].astype(float)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        today = pd.Timestamp.now("UTC").tz_convert(None).normalize()
        df = df[df.index < today]
    _atomic_parquet(df, p)
    return df


def panel(loader, tickers, field="Close"):
    """Wide [date x yfinance ticker] frame of one field from a venue loader."""
    cols = {}
    for t in tickers:
        try:
            df = loader(base_of(t))
        except Exception as e:  # noqa: BLE001
            print(f"skip {t}: {e}")
            continue
        if len(df) and field in df:
            cols[t] = df[field]
    return pd.DataFrame(cols).sort_index()
