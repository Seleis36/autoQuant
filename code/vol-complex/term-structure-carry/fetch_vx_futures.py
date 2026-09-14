"""Fetch every VIX futures contract's daily history from CBOE's public CDN and store a long
table at data/CBOE_VX_futures_d.parquet (flat cache convention: one file per instrument).

Files live at .../historical_data/VX/VX_<expiry>.csv. Expiry = the Wednesday 30 days before
the 3rd Friday of the following month (moved to the prior business day on CBOE holidays);
we simply try the computed Wednesday and its +-1..3 day neighbours.
"""
import os, sys, time, io
import pandas as pd, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
import research_lib as rl

OUT = os.path.join(rl.DATA_DIR, "CBOE_VX_futures_d.parquet")
BASE = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{}.csv"

def third_friday(y, m):
    d = pd.Timestamp(y, m, 15)
    return d + pd.offsets.Week(weekday=4) if d.weekday() != 4 else d

def expiries(start_year=2004, end_year=2027):
    out = []
    for y in range(start_year, end_year + 1):
        for m in range(1, 13):
            # contract for month (y,m): 30 days before 3rd Friday of month+1
            ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
            out.append(third_friday(ny, nm) - pd.Timedelta(days=30))
    return out

def fetch(exp):
    for off in [0, -1, 1, -2, 2, -3]:
        d = (exp + pd.Timedelta(days=off)).strftime("%Y-%m-%d")
        try:
            r = requests.get(BASE.format(d), timeout=30)
        except Exception:
            continue
        if r.status_code == 200 and r.text.startswith("Trade Date"):
            df = pd.read_csv(io.StringIO(r.text))
            df["expiry"] = pd.Timestamp(d)
            return df
    return None

frames = []
old = pd.read_parquet(OUT) if os.path.exists(OUT) else None
have = set(old["expiry"].unique()) if old is not None else set()
for exp in expiries():
    if exp > pd.Timestamp.today() + pd.Timedelta(days=400):
        break
    # refresh unexpired contracts, skip fully-expired ones already cached
    if exp in have and exp < pd.Timestamp.today() - pd.Timedelta(days=3):
        continue
    df = fetch(exp)
    if df is None:
        print("miss", exp.date(), flush=True); continue
    frames.append(df); print("ok  ", exp.date(), len(df), flush=True)
    time.sleep(0.2)

new = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
if old is not None and len(new):
    old = old[~old["expiry"].isin(new["expiry"].unique())]
    new = pd.concat([old, new], ignore_index=True)
elif old is not None:
    new = old
new["Trade Date"] = pd.to_datetime(new["Trade Date"])
new = new.sort_values(["Trade Date", "expiry"]).reset_index(drop=True)
rl._atomic_parquet(new, OUT)
print("saved", OUT, len(new), new["Trade Date"].min(), new["Trade Date"].max())
