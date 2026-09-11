import yfinance as yf, pandas as pd, numpy as np
h = yf.download("EURUSD=X", period="20d", interval="1h", progress=False, multi_level_index=False, auto_adjust=True)
d = yf.download("EURUSD=X", period="30d", interval="1d", progress=False, multi_level_index=False, auto_adjust=True)
h.index = h.index.tz_convert("UTC")
print(h.tail(3)); print(d.tail(6)[["Open","Close"]])
# for each daily bar, find the hourly bar whose close is closest to the daily close and daily open
for dt, row in d.tail(6).iterrows():
    c = row["Close"]; o = row["Open"]
    win = h[(h.index >= dt.tz_localize("UTC") - pd.Timedelta(days=2)) & (h.index <= dt.tz_localize("UTC") + pd.Timedelta(days=2))]
    ic = (win["Close"] - c).abs().idxmin(); io = (win["Open"] - o).abs().idxmin()
    print(dt.date(), "daily close", round(c,5), "~ hourly close at", ic, round(win.loc[ic,"Close"],5), "| daily open", round(o,5), "~ hourly open at", io)
