"""CoinMetrics community API (free, no key, live-obtainable) daily asset metrics.

Cache: data/COINMETRICS_<ASSET>_d.parquet, one column per metric, index = UTC day (the day the
value COVERS). A daily value stamped D summarises [D, D+1) and is not complete until after
D+1 00:00, so lag it by at least one day before using it as a signal on the D+1 close.

Caveat: CoinMetrics revises some metrics (exchange flows especially, as address tagging
improves). A backtest on today's vintage of FlowInExNtv / SplyExNtv is NOT point-in-time.
"""
import json, os, sys, time, urllib.parse, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
from research_lib import _atomic_parquet  # noqa: E402

BASE = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"


def _get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "autoQuant"}), timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(url)


def fetch(asset, metrics, start="2014-01-01"):
    q = urllib.parse.urlencode(dict(assets=asset, metrics=",".join(metrics), frequency="1d",
                                    page_size=10000, start_time=start, ignore_unsupported_errors="true"))
    url, rows = f"{BASE}?{q}", []
    while url:
        js = _get(url)
        rows += js.get("data", [])
        url = js.get("next_page_url")
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
    df = df.drop(columns=["asset"]).set_index("time").sort_index()
    return df.apply(pd.to_numeric, errors="coerce")


def path(asset):
    return os.path.join(DATA, f"COINMETRICS_{asset.upper()}_d.parquet")


def load(asset, metrics=None, refresh=False):
    p = path(asset)
    if refresh or not os.path.exists(p):
        _atomic_parquet(fetch(asset, metrics), p)
    df = pd.read_parquet(p)
    return df if metrics is None else df[[m for m in metrics if m in df.columns]]


ETH_METRICS = ["PriceUSD", "CapMrktCurUSD", "CapMVRVCur", "SplyCur", "IssTotNtv", "FeeTotNtv",
               "AdrActCnt", "TxCnt", "TxTfrCnt", "FlowInExNtv", "FlowOutExNtv", "SplyExNtv",
               "AdrBalCnt", "volume_reported_spot_usd_1d"]
STABLES = ["usdt", "usdc", "busd", "dai"]

if __name__ == "__main__":
    e = load("eth", ETH_METRICS, refresh=True)
    print("eth", e.index.min(), e.index.max(), e.shape, e.notna().sum().to_dict())
    for a in STABLES:
        s = load(a, ["SplyCur", "CapMrktCurUSD"], refresh=True)
        print(a, s.index.min(), s.index.max(), f"{s['SplyCur'].iloc[-1]/1e9:.1f}bn")
