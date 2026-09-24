"""Commodity panel: continuous front futures (=F) paired with the ETF that actually holds them.

The yfinance =F series is a stitched front contract with NO roll adjustment: a holder never
earns the jump between contracts, so =F returns overstate the long return in contango
(NG=F -3.5%/yr vs UNG -24.9%/yr, 2010-2026). Book P&L on the ETF column; use the =F column
only for signals.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import pandas as pd
from research_lib import load_series

# commodity -> (continuous future, ETF holding it)
PAIRS = {
    "gold":   ("GC=F", "GLD"),
    "silver": ("SI=F", "SLV"),
    "copper": ("HG=F", "CPER"),
    "crude":  ("CL=F", "USO"),
    "natgas": ("NG=F", "UNG"),
    "corn":   ("ZC=F", "CORN"),
    "soy":    ("ZS=F", "SOYB"),
    "wheat":  ("ZW=F", "WEAT"),
}


def load_panel(pairs=PAIRS):
    """Returns (fut, etf): DataFrames of daily closes, columns = commodity names,
    on the union of business days, forward-filled at most 3 days (holiday mismatches)."""
    fut = pd.DataFrame({k: load_series(f).Close for k, (f, e) in pairs.items()})
    etf = pd.DataFrame({k: load_series(e).Close for k, (f, e) in pairs.items()})
    ix = fut.index.union(etf.index)
    ix = ix[ix.dayofweek < 5]
    fut = fut.reindex(ix).ffill(limit=3)
    etf = etf.reindex(ix).ffill(limit=3)
    return fut, etf
