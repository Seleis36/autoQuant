"""GICS-like sector for tickers not in the current Wikipedia snapshot, via yfinance .info.
Writes code/us-large-cap/shared/sectors_hist.csv (ticker, sector, industry)."""
import os, sys, time, warnings
warnings.filterwarnings("ignore")
import pandas as pd, yfinance as yf
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sectors_hist.csv")
rows = []
have = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame(columns=["ticker","sector","industry"])
done = set(have.ticker)
tk = [l.strip() for l in open(os.path.join(HERE, "tickers_hist.txt")) if l.strip() and l.strip() not in done]
for i, t in enumerate(tk):
    try:
        info = yf.Ticker(t).info
        rows.append({"ticker": t, "sector": info.get("sector"), "industry": info.get("industry")})
    except Exception as e:
        rows.append({"ticker": t, "sector": None, "industry": None})
    if (i+1) % 20 == 0 or i == len(tk)-1:
        pd.concat([have, pd.DataFrame(rows)]).to_csv(OUT, index=False); print("saved", i+1, flush=True)
    time.sleep(0.5)
