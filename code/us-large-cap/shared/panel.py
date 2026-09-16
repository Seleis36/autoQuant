"""Wide daily panels for the S&P 500 universe from the flat cache data/<TICKER>_d.parquet.

    from panel import load_panel
    P = load_panel()            # dict of DataFrames: open, high, low, close, volume, member
Index: trading days (union of all tickers, 2010+). Columns: tickers with a cache file.
`member` is the point-in-time S&P 500 membership (bool), False where no price.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
sys.path.insert(0, HERE)
from research_lib import daily_cache_path, DATA_DIR
from universe import all_tickers_since, membership_matrix, sectors

CACHE = os.path.join(DATA_DIR, "SP500_panel_cache.parquet")  # not used; panels rebuilt from files


def load_panel(tickers=None, start="2010-01-01", min_days=250):
    tickers = tickers or all_tickers_since(start)
    frames = {}
    for t in tickers:
        p = daily_cache_path(t)
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index).tz_localize(None)
        d = d[~d.index.duplicated(keep="last")].sort_index()
        d = d.loc[start:]
        if len(d) < min_days:
            continue
        frames[t] = d
    fields = ["Open", "High", "Low", "Close", "Volume"]
    out = {}
    for f in fields:
        out[f.lower()] = pd.concat({t: frames[t][f] for t in frames}, axis=1).sort_index()
    idx = out["close"].index
    # drop non-trading rows (all-NaN) and require SPY-ish coverage
    valid = out["close"].notna().sum(axis=1) > 50
    for k in out:
        out[k] = out[k].loc[valid]
    M = membership_matrix(out["close"].index, min_date=start)
    M = M.reindex(columns=out["close"].columns, fill_value=False)
    member = M & out["close"].notna()
    # --- data-quality mask: yfinance recycles delisted symbols (TIE, MEE, CBE...) and
    # occasionally mis-adjusts a bar. Any |daily ret| > 50% is treated as bad data: the
    # ticker is dropped if it has >= 3 such bars, otherwise a +-1 day window is masked.
    ret = out["close"].pct_change()
    bad = ret.abs() > 0.5
    nbad = bad.sum()
    drop = nbad[nbad >= 3].index.tolist()
    bad_win = bad | bad.shift(1, fill_value=False) | bad.shift(-1, fill_value=False)
    member = member & ~bad_win
    member.loc[:, drop] = False
    # price floor: no trading of sub-$1 names (bad adjustments)
    member = member & (out["close"] > 1.0)
    out["member"] = member
    out["dropped_tickers"] = drop
    out["sector"] = sectors().reindex(out["close"].columns)
    return out


if __name__ == "__main__":
    P = load_panel()
    c = P["close"]; m = P["member"]
    print("shape", c.shape, c.index.min(), c.index.max())
    print("members per day (first/last):", m.sum(axis=1).iloc[[0, -1]].tolist())
    print("median members/day", m.sum(axis=1).median())
    print("sector coverage", P["sector"].notna().mean())
