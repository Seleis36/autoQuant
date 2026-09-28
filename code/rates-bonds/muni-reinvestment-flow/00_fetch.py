"""Pre-2010 history for the muni ETFs -> data/<T>_d_pre2010.parquet (flat cache convention)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
import pandas as pd, yfinance as yf
from rb_data import rl
for t in ["MUB", "TFI", "SHM", "HYD", "PZA", "ITM", "SUB"]:
    path = rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")
    if not os.path.exists(path):
        df = yf.download(t, start="2007-01-01", end="2010-01-05", auto_adjust=True,
                         progress=False, multi_level_index=False).dropna()
        if len(df):
            df.index = pd.to_datetime(df.index).tz_localize(None)
            rl._atomic_parquet(df, path)
    if os.path.exists(path):
        d = pd.read_parquet(path); print(t, d.index.min().date(), d.index.max().date(), len(d))
