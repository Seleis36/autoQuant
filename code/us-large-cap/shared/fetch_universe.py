"""Fetch daily OHLCV for a list of tickers into the flat shared cache data/<TICKER>_d.parquet.

Usage: python code/us-large-cap/shared/fetch_universe.py tickers.txt [--refresh]
Files already present are skipped unless --refresh. Tickers are yfinance-style (BRK-B).
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
import pandas as pd, yfinance as yf
from research_lib import daily_cache_path, _atomic_parquet, DAILY_CACHE_START

def main():
    tick_file = sys.argv[1]; refresh = "--refresh" in sys.argv
    tickers = [l.strip() for l in open(tick_file) if l.strip()]
    todo = [t for t in tickers if refresh or not os.path.exists(daily_cache_path(t))]
    print(f"{len(tickers)} tickers, {len(todo)} to fetch", flush=True)
    B = 50
    for i in range(0, len(todo), B):
        batch = todo[i:i+B]
        for attempt in range(3):
            try:
                df = yf.download(batch, start=DAILY_CACHE_START, auto_adjust=True, progress=False,
                                 group_by="ticker", threads=True)
                break
            except Exception as e:
                print("retry", e, flush=True); time.sleep(5)
        for t in batch:
            try:
                d = df[t].dropna(how="all") if len(batch) > 1 else df.dropna(how="all")
            except KeyError:
                print("missing", t, flush=True); continue
            if len(d) < 50:
                print("short/empty", t, len(d), flush=True); continue
            d.index = pd.to_datetime(d.index).tz_localize(None)
            _atomic_parquet(d, daily_cache_path(t))
        print(f"done {i+len(batch)}/{len(todo)}", flush=True)

if __name__ == "__main__":
    main()
