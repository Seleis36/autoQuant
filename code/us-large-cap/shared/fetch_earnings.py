"""Fetch historical earnings-announcement dates for a ticker list via yfinance and store
them in one flat file: data/SP500_earnings_dates.parquet (ticker, date, hour, eps_est,
eps_act, surprise). `hour` is the Yahoo timestamp hour in US/Eastern: 16 => after close,
<= 9 => before open; the date is the announcement's calendar day (US/Eastern).
"""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared"))
import pandas as pd, yfinance as yf
from research_lib import DATA_DIR, _atomic_parquet

OUT = os.path.join(DATA_DIR, "SP500_earnings_dates.parquet")

def fetch_one(t):
    for attempt in range(3):
        try:
            ed = yf.Ticker(t).get_earnings_dates(limit=100)
            if ed is None or len(ed) == 0:
                return None
            idx = pd.DatetimeIndex(ed.index)
            if idx.tz is not None:
                idx = idx.tz_convert("US/Eastern")
            out = pd.DataFrame({"ticker": t, "date": idx.tz_localize(None).normalize(),
                                "hour": idx.hour,
                                "eps_est": ed.get("EPS Estimate", pd.Series(index=ed.index)).values,
                                "eps_act": ed.get("Reported EPS", pd.Series(index=ed.index)).values,
                                "surprise": ed.get("Surprise(%)", pd.Series(index=ed.index)).values})
            return out.drop_duplicates(subset=["ticker", "date"])
        except Exception as e:
            msg = str(e)
            if "Too Many" in msg or "429" in msg:
                time.sleep(20 * (attempt + 1))
            else:
                time.sleep(2)
    return None

def main():
    files = sys.argv[1:]
    tickers = []
    for f in files:
        tickers += [l.strip() for l in open(f) if l.strip()]
    tickers = sorted(set(tickers))
    have = pd.read_parquet(OUT) if os.path.exists(OUT) else pd.DataFrame()
    done = set(have.ticker.unique()) if len(have) else set()
    frames = [have] if len(have) else []
    todo = [t for t in tickers if t not in done]
    print(f"{len(tickers)} tickers, {len(todo)} to fetch", flush=True)
    for i, t in enumerate(todo):
        r = fetch_one(t)
        if r is not None:
            frames.append(r)
        else:
            print("none", t, flush=True)
        if (i + 1) % 25 == 0 or i == len(todo) - 1:
            _atomic_parquet(pd.concat(frames, ignore_index=True), OUT)
            print(f"saved {i+1}/{len(todo)}", flush=True)
        time.sleep(0.3)

if __name__ == "__main__":
    main()
