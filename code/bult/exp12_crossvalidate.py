"""Exp 12 - Cross-exchange / cross-vendor validation of the 20-23 UTC session effect."""
import sys, os, json, time, urllib.request, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
from research_lib import *
pd.set_option("display.width", 240)

def sess_sr(close, hours=(20,21,22), label=""):
    r = close.pct_change().dropna()
    m = r[pd.DatetimeIndex(r.index).hour.isin(hours)]
    dr = m.groupby(pd.DatetimeIndex(m.index).normalize()).sum()
    rest = r[~pd.DatetimeIndex(r.index).hour.isin(hours)]
    dr2 = rest.groupby(pd.DatetimeIndex(rest.index).normalize()).sum()
    return pd.Series({
        "n_days": len(dr), "win_bp/d": dr.mean()*1e4, "win_SR": dr.mean()/dr.std()*np.sqrt(365),
        "win_vol%": dr.std()*np.sqrt(365)*100,
        "rest_bp/d": dr2.mean()*1e4, "rest_SR": dr2.mean()/dr2.std()*np.sqrt(365),
        "rest_vol%": dr2.std()*np.sqrt(365)*100}, name=label)

rows = {}
# 1) Binance (baseline)
b = pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h.parquet"))["Close"]
rows["Binance BTCUSDT full"] = sess_sr(b)
rows["Binance 2024+"]        = sess_sr(b.loc["2024-01-11":])

# 2) Bitstamp (independent exchange, USD spot) - paginate back
def bitstamp(limit_days=1100):
    out, end = [], int(pd.Timestamp.utcnow().timestamp())
    for _ in range(40):
        u = f"https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=3600&limit=1000&end={end}"
        try: d = json.loads(urllib.request.urlopen(u, timeout=30).read())["data"]["ohlc"]
        except Exception as e: print("  bitstamp stop:", e); break
        if not d: break
        out = d + out
        end = int(d[0]["timestamp"]) - 3600
        time.sleep(0.2)
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["timestamp"].astype(int), unit="s")
    return df.drop_duplicates("ts").set_index("ts")["close"].astype(float).sort_index()
try:
    bs = bitstamp(); print(f"Bitstamp: {len(bs)} bars {bs.index[0]} -> {bs.index[-1]}")
    rows["Bitstamp BTCUSD"] = sess_sr(bs)
    rows["Bitstamp 2024+"]  = sess_sr(bs.loc["2024-01-11":])
except Exception as e: print("bitstamp failed", e)

# 3) yfinance hourly (different vendor/aggregation)
try:
    import yfinance as yf
    y = yf.download("BTC-USD", period="730d", interval="1h", progress=False, auto_adjust=True,
                    multi_level_index=False)["Close"]
    y.index = pd.DatetimeIndex(y.index).tz_convert("UTC").tz_localize(None)
    print(f"yfinance 1h: {len(y)} bars {y.index[0]} -> {y.index[-1]}")
    rows["yfinance BTC-USD 1h"] = sess_sr(y)
except Exception as e: print("yfinance hourly failed", e)

# 4) Binance.US (separate venue/orderbook)
def binance_us():
    out, ms = [], int(pd.Timestamp("2021-01-01").timestamp()*1000)
    end = int(pd.Timestamp.utcnow().timestamp()*1000)
    while ms < end:
        u = f"https://api.binance.us/api/v3/klines?symbol=BTCUSD&interval=1h&startTime={ms}&limit=1000"
        try: d = json.loads(urllib.request.urlopen(u, timeout=30).read())
        except Exception: break
        if not d: break
        out += d; ms = d[-1][6]+1; time.sleep(0.1)
    df = pd.DataFrame(out).iloc[:, :7]
    df.columns = ["ot","o","h","l","c","v","ct"]
    df["ts"] = pd.to_datetime(df["ot"], unit="ms")
    return df.set_index("ts")["c"].astype(float)
try:
    bu = binance_us(); print(f"Binance.US: {len(bu)} bars {bu.index[0]} -> {bu.index[-1]}")
    rows["Binance.US BTCUSD"] = sess_sr(bu)
except Exception as e: print("binance.us failed", e)

print("\n=== 20:00-23:00 UTC window vs REST OF DAY, across venues/vendors ===")
print(pd.DataFrame(rows).T.round(2).to_string())

# 5) ETH sanity check: same mechanism should show in ETH if it is a real US-flow effect
try:
    import json as _j
    out, ms = [], int(pd.Timestamp("2017-08-17").timestamp()*1000)
    end = int(pd.Timestamp.utcnow().timestamp()*1000)
    while ms < end:
        u = f"https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=1h&startTime={ms}&limit=1000"
        d = _j.loads(urllib.request.urlopen(u, timeout=30).read())
        if not d: break
        out += d; ms = d[-1][6]+1; time.sleep(0.1)
    e = pd.DataFrame(out).iloc[:, :7]; e.columns=["ot","o","h","l","c","v","ct"]
    e["ts"] = pd.to_datetime(e["ot"], unit="ms"); e = e.set_index("ts")["c"].astype(float)
    print(f"\nETH cross-asset check ({len(e)} bars):")
    print(pd.DataFrame({"ETHUSDT full": sess_sr(e), "ETHUSDT 2024+": sess_sr(e.loc['2024-01-11':])}).T.round(2).to_string())
except Exception as ex: print("eth failed", ex)
