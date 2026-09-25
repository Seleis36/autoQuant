"""Fetch daily stablecoin circulating supply from DefiLlama (free, no key, live-obtainable).

Writes flat caches in data/:
  DEFILLAMA_STABLE_ALL_d.parquet        total USD-pegged circulating (all chains)
  DEFILLAMA_STABLE_ETHEREUM_d.parquet   USD-pegged circulating on the Ethereum chain
  DEFILLAMA_STABLE_USDT_d.parquet       USDT (id 1), all chains
  DEFILLAMA_STABLE_USDC_d.parquet       USDC (id 2), all chains

DefiLlama stamps each row at 00:00 UTC of its date. Treat the value as known only at the
END of that day (i.e. use it from D+1 00:00), which is conservative.
"""
import os, sys, json, urllib.request
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "code", "shared"))
from research_lib import _atomic_parquet  # noqa: E402

URLS = {
    "ALL": "https://stablecoins.llama.fi/stablecoincharts/all",
    "ETHEREUM": "https://stablecoins.llama.fi/stablecoincharts/Ethereum",
    "USDT": "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=1",
    "USDC": "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=2",
}


def fetch(name):
    with urllib.request.urlopen(urllib.request.Request(URLS[name], headers={"User-Agent": "autoQuant"}), timeout=60) as r:
        js = json.load(r)
    rows = []
    for x in js:
        tc = x.get("totalCirculatingUSD") or x.get("totalCirculating") or {}
        rows.append((pd.to_datetime(int(x["date"]), unit="s"), float(tc.get("peggedUSD", float("nan")))))
    s = pd.DataFrame(rows, columns=["date", "supply_usd"]).set_index("date").sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s


def path(name):
    return os.path.join(DATA, f"DEFILLAMA_STABLE_{name}_d.parquet")


def load(name, refresh=False):
    p = path(name)
    if refresh or not os.path.exists(p):
        _atomic_parquet(fetch(name), p)
    return pd.read_parquet(p)["supply_usd"]


if __name__ == "__main__":
    for n in URLS:
        s = load(n, refresh=True)
        print(n, s.index.min(), s.index.max(), len(s), f"{s.iloc[-1]/1e9:.1f}bn")
