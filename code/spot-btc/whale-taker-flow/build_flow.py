"""Hourly Binance spot BTCUSDT taker flow split by aggTrade notional size, from the tick store.

An aggTrade merges the fills of one taker order at one price, so its notional is a lower
bound on the parent order size (a sweep across price levels is split). Buckets in USD:
  b0 < 1k <= b1 < 10k <= b2 < 100k <= b3 < 1M <= b4
Per hour and bucket: taker-buy notional, taker-sell notional, buy count, sell count.
Output -> data/BTCUSDT_spot_takerflow_size_1h.parquet (derived from the tick store; rebuild
with this script, it is resumable per month via a scratch directory).
"""
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(REPO, "data", "ticks", "binance", "spot", "aggTrades", "BTCUSDT")
SCRATCH = os.path.join(REPO, "data", "_scratch_takerflow_btc")
OUT = os.path.join(REPO, "data", "BTCUSDT_spot_takerflow_size_1h.parquet")
EDGES = np.array([1e3, 1e4, 1e5, 1e6])


def one_month(path):
    tag = os.path.basename(path).replace(".parquet", "")
    dst = os.path.join(SCRATCH, f"{tag}.parquet")
    if os.path.exists(dst):
        return tag, "cached"
    f = pq.ParquetFile(path)
    parts = []
    for g in range(f.metadata.num_row_groups):
        t = f.read_row_group(g, columns=["ts", "price", "qty", "buyer_maker"])
        ts = t.column("ts").to_numpy().astype("datetime64[h]").astype(np.int64)
        notional = t.column("price").to_numpy() * t.column("qty").to_numpy()
        sell = t.column("buyer_maker").to_numpy(zero_copy_only=False)
        b = np.searchsorted(EDGES, notional, side="right")
        key = ts * 10 + b
        df = pd.DataFrame({"key": key, "buy": np.where(sell, 0.0, notional), "sell": np.where(sell, notional, 0.0),
                           "nb": (~sell).astype(np.int64), "ns": sell.astype(np.int64)})
        parts.append(df.groupby("key").sum())
    agg = pd.concat(parts).groupby(level=0).sum()
    hour = pd.to_datetime((agg.index.values // 10).astype("int64") * 3600 * 10**9)
    agg = agg.assign(hour=hour, bucket=agg.index.values % 10).reset_index(drop=True)
    tmp = dst + ".tmp"
    agg.to_parquet(tmp)
    os.replace(tmp, dst)
    return tag, len(agg)


def main(workers=4):
    os.makedirs(SCRATCH, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC, "*.parquet")))
    with ProcessPoolExecutor(workers) as ex:
        for tag, n in ex.map(one_month, files):
            print(tag, n, flush=True)
    df = pd.concat([pd.read_parquet(p) for p in sorted(glob.glob(os.path.join(SCRATCH, "*.parquet")))])
    wide = df.pivot_table(index="hour", columns="bucket", values=["buy", "sell", "nb", "ns"], aggfunc="sum").fillna(0)
    wide.columns = [f"{v}_b{int(b)}" for v, b in wide.columns]
    wide = wide.sort_index()
    tmp = OUT + ".tmp"
    wide.to_parquet(tmp)
    os.replace(tmp, OUT)
    print("wrote", OUT, wide.shape, wide.index.min(), wide.index.max())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
