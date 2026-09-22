"""Fetch pre-2010 daily history for the credit ETFs, into the *_d_pre2010.parquet
convention already used by treasury-flow-calendar. HYG starts 2007-04, LQD 2002-07."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import pandas as pd, yfinance as yf
import research_lib as rl

for t in ["HYG", "IEF", "SHY", "LQD", "TLT", "SPY", "AGG"]:
    path = rl.daily_cache_path(t).replace("_d.parquet", "_d_pre2010.parquet")
    if os.path.exists(path):
        d = pd.read_parquet(path)
        print(t, "cached", d.index.min().date(), d.index.max().date(), len(d)); continue
    df = yf.download(t, start="2002-01-01", end="2010-01-05", auto_adjust=True,
                     progress=False, multi_level_index=False).dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    rl._atomic_parquet(df, path)
    print(t, "->", df.index.min().date(), df.index.max().date(), len(df))
