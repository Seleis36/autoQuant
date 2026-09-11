"""Shared FX-majors data loader. Uses the flat data/ cache via research_lib.load_series.

Bar convention: yfinance '=X' daily bars are stamped at 00:00 UTC of the trading day and
close at the ~24:00 UTC roll (Yahoo sources them at the London/NY boundary). We use Close only.
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "shared"))
import pandas as pd
from research_lib import load_series, DAILY_CACHE_START  # noqa: E402

PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"]
MACRO = ["DX-Y.NYB", "^TNX", "^IRX", "^FVX", "^TYX", "^VIX", "^GSPC", "GLD", "USO", "TLT", "SPY", "HYG"]
# USD-quoted foreign-currency ETFs — independent price source for cross-checking
ETFS = ["FXE", "FXB", "FXY", "FXA", "FXC", "FXF", "UUP"]


def load_closes(tickers, start=DAILY_CACHE_START, refresh=False):
    out = {}
    for t in tickers:
        df = load_series(t, start=start, cache=not refresh)
        out[t] = df["Close"]
    return pd.DataFrame(out)


def load_fx_usd_per_ccy(start=DAILY_CACHE_START, refresh=False):
    """Return closes converted to 'USD per 1 unit of foreign ccy' so that a positive
    return == foreign currency appreciates vs USD (i.e. long the foreign ccy, short USD).
    Columns: EUR GBP JPY AUD CAD CHF NZD."""
    px = load_closes(PAIRS, start=start, refresh=refresh)
    out = pd.DataFrame(index=px.index)
    out["EUR"] = px["EURUSD=X"]
    out["GBP"] = px["GBPUSD=X"]
    out["JPY"] = 1.0 / px["USDJPY=X"]
    out["AUD"] = px["AUDUSD=X"]
    out["CAD"] = 1.0 / px["USDCAD=X"]
    out["CHF"] = 1.0 / px["USDCHF=X"]
    out["NZD"] = px["NZDUSD=X"]
    return out


if __name__ == "__main__":
    refresh = "--refresh" in sys.argv
    fx = load_fx_usd_per_ccy(refresh=refresh)
    print(fx.tail()); print(fx.describe().T[["count", "min", "max"]])
    print(fx.index.min(), fx.index.max(), len(fx))
    m = load_closes(MACRO, refresh=refresh)
    print(m.tail()); print(m.count())
    try:
        e = load_closes(ETFS, refresh=refresh); print(e.count())
    except Exception as ex:
        print("ETF fetch failed", ex)
