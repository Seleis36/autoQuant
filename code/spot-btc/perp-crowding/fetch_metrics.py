"""Parallel, resumable fetch of Binance USD-M futures `metrics` (open interest, top-trader and
global long/short ratios, taker long/short volume ratio; 5-minutely) for BTCUSDT.

Same output file and schema as `code/shared/fetch_binance_vision.py metrics`
(data/BTCUSDT_metrics_5m.parquet), but downloads daily files with a thread pool and keeps
per-day raw CSVs in a scratch dir so an interrupted run resumes instead of restarting.
Archive starts 2020-09-01.
"""
import io
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
import fetch_binance_vision as fbv  # noqa: E402
from research_lib import DATA_DIR, _atomic_parquet  # noqa: E402

SCRATCH = os.path.join(DATA_DIR, "_scratch_metrics")


def _one(symbol, day):
    stamp = day.strftime("%Y-%m-%d")
    dst = os.path.join(SCRATCH, symbol, f"{stamp}.csv")
    if os.path.exists(dst):
        return dst
    url = f"{fbv.BASE}/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{stamp}.zip"
    blob = fbv._get(url)
    if blob is None:
        return None
    raw = fbv._unzip(blob, url, verify=False)
    tmp = dst + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(raw)
    os.replace(tmp, dst)
    return dst


def fetch(symbol="BTCUSDT", start="2020-09-01", end=None, workers=8):
    os.makedirs(os.path.join(SCRATCH, symbol), exist_ok=True)
    end = pd.Timestamp(end) if end else pd.Timestamp.utcnow().tz_localize(None).normalize() - pd.Timedelta(days=1)
    days = pd.date_range(start, end, freq="D")
    with ThreadPoolExecutor(workers) as ex:
        paths = [p for p in ex.map(lambda d: _one(symbol, d), days) if p]
    df = pd.concat([pd.read_csv(p) for p in sorted(paths)])
    df["ts"] = pd.to_datetime(df["create_time"])
    df = df.set_index("ts").drop(columns=["create_time", "symbol"]).apply(pd.to_numeric, errors="coerce")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    _atomic_parquet(df, os.path.join(DATA_DIR, f"{symbol}_metrics_5m.parquet"))
    return df


if __name__ == "__main__":
    d = fetch(sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT")
    print(d.index.min(), d.index.max(), len(d), list(d.columns))
