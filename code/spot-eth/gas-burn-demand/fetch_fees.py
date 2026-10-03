"""Refresh data/COINMETRICS_ETH_d.parquet (superset of the shared metric list, plus BlkCnt) and
print CoinMetrics' own end-of-day completion times, i.e. how late a daily value is published."""
import json
import os
import sys
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
import coinmetrics as cm  # noqa: E402

METRICS = cm.ETH_METRICS + ["BlkCnt"]

if __name__ == "__main__":
    df = cm.fetch("eth", METRICS, start="2015-07-30")
    old = pd.read_parquet(cm.path("eth")) if os.path.exists(cm.path("eth")) else pd.DataFrame()
    keep = [c for c in old.columns if c not in df.columns]
    if keep:
        df = df.join(old[keep], how="left")
    cm._atomic_parquet(df, cm.path("eth"))
    print("eth", df.index.min().date(), df.index.max().date(), df.shape)

    url = (cm.BASE + "?assets=eth&metrics=AssetEODCompletionTime&frequency=1d&page_size=10000"
           "&start_time=2024-01-01")
    rows = []
    while url:
        js = cm._get(url)
        rows += js["data"]
        url = js.get("next_page_url")
    t = pd.DataFrame(rows)
    day = pd.to_datetime(t["time"]).dt.tz_localize(None)
    done = pd.to_datetime(pd.to_numeric(t["AssetEODCompletionTime"]), unit="s")
    lag_h = (done - (day + pd.Timedelta(days=1))).dt.total_seconds() / 3600
    print("hours after the UTC day ends until the daily row is complete (2024+):")
    print(lag_h.describe(percentiles=[0.5, 0.9, 0.99]).round(2).to_string())
