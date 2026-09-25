"""Coinbase Exchange hourly candles (public, no key) -> data/COINBASE_<BASE><QUOTE>_1h.parquet.

Bars stamped at the OPEN (UTC, tz-naive), same convention as Binance klines. 300 candles per
request; incremental: only fetches after the last cached bar unless --full.
"""
import json, os, sys, time, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402


def _get(url):
    for a in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "autoQuant"}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (a + 1))
    raise RuntimeError(url)


def path(product):
    return os.path.join(DATA_DIR, f"COINBASE_{product.replace('-', '')}_1h.parquet")


def fetch(product="ETH-USD", start="2017-08-01", gran=3600):
    out, t0 = [], pd.Timestamp(start)
    end = pd.Timestamp.now("UTC").tz_localize(None).floor("h")
    step = pd.Timedelta(seconds=gran * 300)
    while t0 < end:
        t1 = min(t0 + step, end)
        out += _get(f"https://api.exchange.coinbase.com/products/{product}/candles?granularity={gran}"
                    f"&start={t0.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={t1.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        t0 = t1
        time.sleep(0.12)
    df = pd.DataFrame(out, columns=["t", "Low", "High", "Open", "Close", "Volume"])
    df["ts"] = pd.to_datetime(df["t"], unit="s")
    df = df.set_index("ts")[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def load(product="ETH-USD", refresh=False, full=False):
    p = path(product)
    if full or not os.path.exists(p):
        _atomic_parquet(fetch(product), p)
    elif refresh:
        old = pd.read_parquet(p)
        new = fetch(product, start=str(old.index.max() - pd.Timedelta(hours=2)))
        df = pd.concat([old, new]); df = df[~df.index.duplicated(keep="last")].sort_index()
        _atomic_parquet(df, p)
    return pd.read_parquet(p)


if __name__ == "__main__":
    for prod in sys.argv[1:] or ["ETH-USD"]:
        d = load(prod, refresh=True)
        print(prod, d.index.min(), d.index.max(), len(d))
