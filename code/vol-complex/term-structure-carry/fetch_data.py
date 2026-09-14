"""Pull the vol-complex universe into the shared flat daily cache (data/<TICKER>_d.parquet)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import research_lib as rl

for t in ["^VIX", "^VIX3M", "^VIX9D", "^VVIX", "VXX", "UVXY", "SVXY", "VIXY", "SPY"]:
    try:
        df = rl.load_series(t)
        print(f"{t:8s} {df.index.min().date()} -> {df.index.max().date()}  n={len(df)}  cols={list(df.columns)}")
    except Exception as e:
        print(f"{t:8s} FAILED: {e}")
