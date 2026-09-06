"""Download full hourly BTCUSDT history from Binance (public, no key) -> parquet cache."""
import json, time, os, sys, urllib.request
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from research_lib import DATA_DIR

def fetch(symbol="BTCUSDT", interval="1h", start="2017-08-17", host="api.binance.com"):
    out, ms = [], int(pd.Timestamp(start).timestamp()*1000)
    end_ms = int(pd.Timestamp.utcnow().timestamp()*1000)
    while ms < end_ms:
        url = (f"https://{host}/api/v3/klines?symbol={symbol}&interval={interval}"
               f"&startTime={ms}&limit=1000")
        for attempt in range(5):
            try:
                d = json.loads(urllib.request.urlopen(url, timeout=30).read()); break
            except Exception as e:
                if attempt == 4: raise
                time.sleep(2*(attempt+1))
        if not d: break
        out += d
        ms = d[-1][6] + 1
        if len(out) % 20000 < 1000:
            print(f"  ... {len(out)} bars, at {pd.to_datetime(d[-1][0], unit='ms')}", flush=True)
        time.sleep(0.12)
    df = pd.DataFrame(out, columns=["ot","Open","High","Low","Close","Volume","ct","qv","n","tb","tq","ig"])
    df["ts"] = pd.to_datetime(df["ot"], unit="ms")          # bar OPEN time, UTC
    df = df.set_index("ts")[["Open","High","Low","Close","Volume","qv","n"]].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    for interval in ["1h"]:
        p = os.path.join(DATA_DIR, f"BTCUSDT_{interval}.parquet")
        print(f"fetching {interval} ...")
        df = fetch(interval=interval)
        df.to_parquet(p)
        print(f"saved {p}: {df.shape}  {df.index[0]} -> {df.index[-1]}")
