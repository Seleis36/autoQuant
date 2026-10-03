"""Wikipedia daily pageviews (Wikimedia REST API, keyless) for crypto articles, cached flat at
data/WIKI_PAGEVIEWS_d.parquet (one column per article, `user` agent = humans only).

Timing: the count for UTC day D is published by the API during D+1 (typically within a few
hours, occasionally later), so research lags it one full day.
History: the pageviews API starts 2015-07-01.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
from research_lib import _atomic_parquet  # noqa: E402

PATH = os.path.join(REPO, "data", "WIKI_PAGEVIEWS_d.parquet")
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
ARTICLES = ["Ethereum", "Bitcoin", "Cryptocurrency", "Vitalik_Buterin", "Smart_contract",
            "Decentralized_finance", "Non-fungible_token", "Binance", "Coinbase", "Tether_(cryptocurrency)"]
UA = "autoQuant-research/1.0"


def _one(article, start="20150701"):
    end = pd.Timestamp.utcnow().strftime("%Y%m%d")
    url = f"{BASE}/{urllib.parse.quote(article, safe='')}/daily/{start}/{end}"
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                items = json.load(r)["items"]
            break
        except Exception:
            time.sleep(2 * (i + 1))
    else:
        raise RuntimeError(url)
    s = pd.Series({pd.Timestamp(i["timestamp"][:8]): i["views"] for i in items}, name=article)
    return s.sort_index()


def fetch():
    df = pd.concat([_one(a) for a in ARTICLES], axis=1)
    _atomic_parquet(df, PATH)
    return df


def load(refresh=False):
    if refresh or not os.path.exists(PATH):
        return fetch()
    return pd.read_parquet(PATH)


if __name__ == "__main__":
    d = fetch()
    print(d.index.min().date(), d.index.max().date(), d.shape)
    print(d.notna().sum().to_dict())
    print(d.tail(3).to_string())
