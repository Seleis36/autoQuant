"""Deribit DVOL (30-day implied vol index) for ETH, daily and hourly, public API (no key).

Writes data/DERIBIT_DVOL_ETH_1d.parquet and data/DERIBIT_DVOL_ETH_1h.parquet. Bars are stamped at
the bar OPEN (UTC); a daily bar D's Close is the index value at D+1 00:00 UTC. History from 2021-03-24.
Deribit returns the latest 1000 points before end_timestamp, so we page backwards.
"""
import json, os, sys, time, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402


def _get(url):
    for a in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "autoQuant"}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (a + 1))
    raise RuntimeError(url)


def fetch_dvol(currency="ETH", resolution=86400, start="2021-03-24"):
    ms = lambda t: int(pd.Timestamp(t).timestamp() * 1000)
    out, end, floor = [], ms(pd.Timestamp.now("UTC").tz_localize(None)), ms(start)
    while end > floor:
        rows = _get(f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={currency}"
                    f"&resolution={resolution}&start_timestamp={floor}&end_timestamp={end}")["result"]["data"]
        if not rows:
            break
        out += rows
        end = rows[0][0] - 1
        time.sleep(0.2)
    df = pd.DataFrame(out, columns=["t", "Open", "High", "Low", "Close"])
    df["ts"] = pd.to_datetime(df["t"], unit="ms")
    df = df.set_index("ts")[["Open", "High", "Low", "Close"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


def load(freq="1d", refresh=False, currency="ETH"):
    p = os.path.join(DATA_DIR, f"DERIBIT_DVOL_{currency}_{freq}.parquet")
    if refresh or not os.path.exists(p):
        _atomic_parquet(fetch_dvol(currency, 86400 if freq == "1d" else 3600), p)
    return pd.read_parquet(p)


if __name__ == "__main__":
    for f in ["1d", "1h"]:
        d = load(f, refresh=True)
        print(f, d.index.min(), d.index.max(), len(d))
