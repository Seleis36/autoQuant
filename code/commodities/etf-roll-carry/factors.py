"""Commodity factor signals on the 8-commodity ETF panel. All values known at the close of day t."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import numpy as np, pandas as pd
from panel import load_panel
from fetch_cot import cot_panel
from research_lib import rank_xs

ANN = 252


def carry(fut, etf, k):
    """Annualised realised roll yield: ETF log return minus stitched =F log return over k days."""
    lf, le = np.log(fut.clip(lower=0.01)), np.log(etf)
    return ((le - le.shift(k)) - (lf - lf.shift(k))) * ANN / k


def build(fut, etf, mask):
    le = np.log(etf)
    r = etf.pct_change()
    f = {}
    f["carry"] = sum(rank_xs(carry(fut, etf, k), mask) for k in (63, 126, 252)) / 3
    f["mom"] = sum(rank_xs(le - le.shift(k), mask) for k in (63, 126, 252)) / 3
    comm = cot_panel(lambda d: (d.pm_long + d.sw_long - d.pm_short - d.sw_short) / d.oi, etf.index)
    mm = cot_panel(lambda d: (d.mm_long - d.mm_short) / d.oi, etf.index)
    f["hp"] = rank_xs(-comm, mask)                          # hedgers net short -> long
    f["hp52"] = rank_xs(-(comm - comm.rolling(252).mean()), mask)   # vs own 1y average
    f["spec"] = rank_xs(mm, mask)                           # managed money net long -> long
    f["skew"] = rank_xs(-r.rolling(252).skew(), mask)      # low skew -> long
    return f
