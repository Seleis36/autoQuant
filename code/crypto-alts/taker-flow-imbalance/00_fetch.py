"""Fetch Binance spot 1d klines (with taker-buy volume) for the whole alt candidate list."""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from universe import ALTS, MAJORS
import venues as V

if __name__ == "__main__":
    for t in MAJORS + ALTS:
        b = V.base_of(t)
        try:
            df = V.binance_daily(b)
            print(t, b, len(df), df.index.min() if len(df) else None, df.index.max() if len(df) else None, flush=True)
        except Exception as e:
            print(t, "ERR", e, flush=True)
