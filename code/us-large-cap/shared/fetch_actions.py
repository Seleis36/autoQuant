"""Split and cash-dividend history (ex-dates) for every priced S&P 500 panel name.

    python code/us-large-cap/shared/fetch_actions.py

Output: data/SP500_actions.parquet, long format: ticker, date, dividend, split.
Why: the daily cache is split- AND dividend-adjusted (auto_adjust). Share counts reported in
SEC filings are on the share basis of their own date, so market cap = adj price x reported
shares is wrong across every split. `split_factor_after()` in xbrl.py puts reported share
counts on today's basis with this table. The dividend column (ex-date, per share, split-
adjusted by Yahoo) is the raw material for dividend-calendar studies.
"""
import os, sys
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shared"))
from research_lib import DATA_DIR, _atomic_parquet, daily_cache_path
from universe import all_tickers_since

OUT = os.path.join(DATA_DIR, "SP500_actions.parquet")


def main():
    tickers = [t for t in all_tickers_since("2010-01-01") if os.path.exists(daily_cache_path(t))]
    rows = []
    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        d = yf.download(chunk, start="2009-01-01", actions=True, auto_adjust=False,
                        group_by="ticker", progress=False, threads=True)
        for t in chunk:
            if t not in d.columns.get_level_values(0):
                continue
            x = d[t].reindex(columns=["Dividends", "Stock Splits"]).fillna(0.0)
            x = x[(x["Dividends"] != 0) | (x["Stock Splits"] != 0)]
            for dt, r in x.iterrows():
                rows.append((t, dt, float(r["Dividends"]), float(r["Stock Splits"])))
        print(i + len(chunk), "/", len(tickers), len(rows), flush=True)
    df = pd.DataFrame(rows, columns=["ticker", "date", "dividend", "split"])
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    _atomic_parquet(df, OUT)
    print(df.shape, df.ticker.nunique(), "tickers ->", OUT)


if __name__ == "__main__":
    main()
