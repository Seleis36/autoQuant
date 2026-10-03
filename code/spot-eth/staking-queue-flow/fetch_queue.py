"""Daily Ethereum validator entry/exit queue history from validatorqueue.com (etheralpha's public
repo), cached flat at data/VALIDATORQUEUE_ETH_d.parquet. History starts 2023-05-21 (one month
after withdrawals were enabled); queues and staked amount are in ETH."""
import json
import os
import sys
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "shared"))
from research_lib import _atomic_parquet  # noqa: E402

URL = "https://raw.githubusercontent.com/etheralpha/validatorqueue-com/main/historical_data.json"
PATH = os.path.join(REPO, "data", "VALIDATORQUEUE_ETH_d.parquet")


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "autoQuant"})
    with urllib.request.urlopen(req, timeout=60) as r:
        df = pd.DataFrame(json.load(r))
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")].apply(pd.to_numeric, errors="coerce")
    _atomic_parquet(df, PATH)
    return df


def load(refresh=False):
    if refresh or not os.path.exists(PATH):
        return fetch()
    return pd.read_parquet(PATH)


if __name__ == "__main__":
    d = fetch()
    print(d.index.min().date(), d.index.max().date(), d.shape, "missing days:",
          len(pd.date_range(d.index.min(), d.index.max())) - len(d))
