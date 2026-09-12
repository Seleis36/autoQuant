"""Fetch the exogenous-flow data used by coinbase-premium into the flat shared data/ cache.

All endpoints are public, no API key. Each file is named by instrument, never per-idea.

  data/BTCUSDT_funding_8h.parquet     Binance USDT-M perp funding rate, one row per 8h settlement
  data/BTCUSDT_premium_1h.parquet     Binance premium-index klines (mark-vs-index premium), hourly
  data/BTCUSDT_1h_flow.parquet        Binance spot hourly klines incl. taker-buy base/quote volume
  data/COINBASE_BTCUSD_1h.parquet     Coinbase Exchange BTC-USD hourly candles
  data/DERIBIT_DVOL_BTC_1d.parquet    Deribit BTC DVOL (30d implied vol index), daily
  data/BITSTAMP_USDTUSD_1d.parquet    Bitstamp USDT/USD daily (stablecoin premium)

Timestamps are bar OPEN times in UTC (tz-naive), matching data/BTCUSDT_1h.parquet.
"""
import json, os, sys, time, urllib.request, urllib.parse
import pandas as pd, numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "shared"))
from research_lib import DATA_DIR, _atomic_parquet


def get(url, tries=6, timeout=30, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "autoquant-research/1.0"})
    for a in range(tries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except Exception as e:
            if a == tries - 1:
                raise
            time.sleep(2 * (a + 1))


def ms(ts):
    return int(pd.Timestamp(ts).timestamp() * 1000)


def fetch_funding(symbol="BTCUSDT", start="2019-09-01"):
    out, t = [], ms(start)
    end = ms(pd.Timestamp.now('UTC').tz_localize(None))
    while t < end:
        d = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&startTime={t}&limit=1000")
        if not d:
            break
        out += d
        t = d[-1]["fundingTime"] + 1
        time.sleep(0.15)
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["fundingTime"], unit="ms")
    df["fundingRate"] = df["fundingRate"].astype(float)
    df["markPrice"] = pd.to_numeric(df["markPrice"], errors="coerce")
    df = df.set_index("ts")[["fundingRate", "markPrice"]]
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_binance_klines(host, path, symbol, interval, start, cols):
    out, t = [], ms(start)
    end = ms(pd.Timestamp.now('UTC').tz_localize(None))
    while t < end:
        d = get(f"https://{host}{path}?symbol={symbol}&interval={interval}&startTime={t}&limit=1000")
        if not d:
            break
        out += d
        t = d[-1][6] + 1
        if len(out) % 20000 < 1000:
            print(f"    {path} {len(out)} bars @ {pd.to_datetime(d[-1][0], unit='ms')}", flush=True)
        time.sleep(0.12)
    df = pd.DataFrame(out, columns=cols)
    df["ts"] = pd.to_datetime(df["ot"], unit="ms")
    keep = [c for c in cols if c not in ("ot", "ct", "ig")]
    df = df.set_index("ts")[keep].apply(pd.to_numeric, errors="coerce")
    return df[~df.index.duplicated(keep="last")].sort_index()


KCOLS = ["ot", "Open", "High", "Low", "Close", "Volume", "ct", "qv", "n", "tb", "tq", "ig"]


def fetch_coinbase(product="BTC-USD", start="2015-01-01", gran=3600):
    out = []
    t0 = pd.Timestamp(start)
    end = pd.Timestamp.now('UTC').tz_localize(None)
    step = pd.Timedelta(seconds=gran * 300)
    while t0 < end:
        t1 = min(t0 + step, end)
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles?granularity={gran}"
               f"&start={t0.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={t1.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        d = get(url)
        out += d
        t0 = t1
        if len(out) % 15000 < 300:
            print(f"    coinbase {len(out)} bars @ {t1}", flush=True)
        time.sleep(0.15)
    df = pd.DataFrame(out, columns=["t", "Low", "High", "Open", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["t"], unit="s")
    df = df.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_dvol(currency="BTC", start="2021-03-24"):
    """Deribit returns the most recent 1000 points before end_timestamp; page backwards."""
    out, end = [], ms(pd.Timestamp.now("UTC").tz_localize(None))
    floor = ms(start)
    while end > floor:
        d = get(f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={currency}"
                f"&resolution=86400&start_timestamp={floor}&end_timestamp={end}")
        rows = d["result"]["data"]
        if not rows:
            break
        out += rows
        end = rows[0][0] - 1
        if len(rows) < 1000:
            break
        time.sleep(0.2)
    df = pd.DataFrame(out, columns=["t", "Open", "High", "Low", "Close"])
    df["ts"] = pd.to_datetime(df["t"], unit="ms")
    df = df.set_index("ts")[["Open", "High", "Low", "Close"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_bitstamp_daily(pair="usdtusd", start="2019-01-01"):
    out, t = [], int(pd.Timestamp(start).timestamp())
    end = int(pd.Timestamp.now('UTC').timestamp())
    while t < end:
        d = get(f"https://www.bitstamp.net/api/v2/ohlc/{pair}/?step=86400&limit=1000&start={t}")
        rows = d["data"]["ohlc"]
        if not rows:
            break
        out += rows
        t = int(rows[-1]["timestamp"]) + 86400
        time.sleep(0.2)
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["timestamp"].astype(int), unit="s")
    df = df.set_index("ts")[["open", "high", "low", "close", "volume"]].astype(float)
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df[~df.index.duplicated(keep="last")].sort_index()


JOBS = {
    "BTCUSDT_funding_8h": lambda: fetch_funding(),
    "BTCUSDT_premium_1h": lambda: fetch_binance_klines("fapi.binance.com", "/fapi/v1/premiumIndexKlines",
                                                       "BTCUSDT", "1h", "2019-09-01", KCOLS),
    "BTCUSDT_1h_flow": lambda: fetch_binance_klines("api.binance.com", "/api/v3/klines",
                                                    "BTCUSDT", "1h", "2017-08-17", KCOLS),
    "COINBASE_BTCUSD_1h": lambda: fetch_coinbase(),
    "DERIBIT_DVOL_BTC_1d": lambda: fetch_dvol(),
    "BITSTAMP_USDTUSD_1d": lambda: fetch_bitstamp_daily(),
}

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    only = sys.argv[1:]
    for name, fn in JOBS.items():
        if only and name not in only:
            continue
        p = os.path.join(DATA_DIR, f"{name}.parquet")
        if os.path.exists(p) and "--refresh" not in sys.argv:
            print(f"cached  {name}")
            continue
        print(f"fetching {name} ...", flush=True)
        df = fn()
        _atomic_parquet(df, p)
        print(f"saved   {p}: {df.shape} {df.index[0]} -> {df.index[-1]}", flush=True)
