"""Fetch daily closes for the global-equity-etf universe into data/."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
from research_lib import load_series

UNIVERSE = ["EFA", "EEM", "EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA",
            "EWC", "FXI", "INDA", "ACWI", "SPY"]

for t in UNIVERSE:
    df = load_series(t)
    print(f"{t:6s} {df.index.min().date()} → {df.index.max().date()}  n={len(df)}")
