"""Shared loaders for eth-perp-crowding: Binance USD-M `metrics` (5-minute positioning snapshots)
for ETHUSDT and BTCUSDT, daily Binance spot bars, and the BTC `perp-crowding` spec imported
unchanged so the ETH run is a replication rather than a re-fit."""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "code", "spot-eth", "shared"))
import evalkit as ek  # noqa: E402

DATA = os.path.join(REPO, "data")
EVAL_START = "2022-06-01"          # 2021-12-01 archive start + the spec's 180-day rank warm-up
SPLITS = {"Full": (EVAL_START, None), "IS": (EVAL_START, "2023-12-31"), "OOS": ("2024-01-01", None)}

RATIOS = {"glob": "count_long_short_ratio",            # all accounts (the retail head count)
          "topacc": "count_toptrader_long_short_ratio",  # top-trader accounts
          "toppos": "sum_toptrader_long_short_ratio"}    # top-trader positions


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


btc_spec = _load(os.path.join(REPO, "code", "spot-btc", "perp-crowding", "strategy.py"), "btc_perp_crowding")


def metrics(symbol="ETHUSDT"):
    m = pd.read_parquet(os.path.join(DATA, f"{symbol}_metrics_5m.parquet"))
    m.index = pd.to_datetime(m.index)
    return m.sort_index()


def daily_level(series, index, cutoff_hours=1.0, log=True):
    """Last 5-minute snapshot usable `cutoff_hours` before each daily close, one value per bar."""
    s = series.dropna()
    if log:
        s = np.log(s[s > 0])
    s = s.copy()
    s.index = s.index + pd.Timedelta(hours=cutoff_hours)
    return s.resample("1D", label="left", closed="left").last().reindex(index)


def closes():
    return ek.daily("ETHUSDT")["Close"], ek.daily("BTCUSDT")["Close"]
