"""Upbit KRW market daily candles (public API, no key) -> data/UPBIT_<MARKET>_d.parquet.

Upbit daily candles are aligned to 00:00 UTC (candle_date_time_utc); the row stamped D covers
[D, D+1) UTC and its trade_price is the close at D+1 00:00 UTC -- same convention as a Binance
daily bar resampled from 1m. 200 candles per request, paged backwards with `to`.
"""
import json, os, sys, time, urllib.request
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402


def _get(url):
    for a in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "autoQuant", "accept": "application/json"}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.5 * (a + 1))
    raise RuntimeError(url)


def fetch(market="KRW-ETH", start="2017-09-01"):
    out, to = [], None
    while True:
        url = f"https://api.upbit.com/v1/candles/days?market={market}&count=200" + (f"&to={to}" if to else "")
        rows = _get(url)
        if not rows:
            break
        out += rows
        first = min(r["candle_date_time_utc"] for r in rows)
        if first <= start:
            break
        to = first + "Z"
        time.sleep(0.15)
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["candle_date_time_utc"])
    df = df.set_index("ts").rename(columns={"opening_price": "Open", "high_price": "High", "low_price": "Low",
                                            "trade_price": "Close", "candle_acc_trade_price": "QuoteVolume",
                                            "candle_acc_trade_volume": "Volume"})
    df = df[["Open", "High", "Low", "Close", "Volume", "QuoteVolume"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def load(market="KRW-ETH", refresh=False):
    p = os.path.join(DATA_DIR, f"UPBIT_{market.replace('-', '')}_d.parquet")
    if refresh or not os.path.exists(p):
        _atomic_parquet(fetch(market), p)
    return pd.read_parquet(p)


if __name__ == "__main__":
    for m in sys.argv[1:] or ["KRW-ETH", "KRW-BTC"]:
        d = load(m, refresh=True)
        print(m, d.index.min(), d.index.max(), len(d))
