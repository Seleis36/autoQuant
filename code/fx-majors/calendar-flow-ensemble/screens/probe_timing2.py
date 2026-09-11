import yfinance as yf, pandas as pd, numpy as np, sys
sys.path.insert(0, "code/shared"); from research_lib import load_series
for tk in ["EURUSD=X","USDJPY=X"]:
    h = yf.download(tk, period="729d", interval="1h", progress=False, multi_level_index=False, auto_adjust=True)["Close"]
    h.index = h.index.tz_convert("UTC")
    d = load_series(tk)["Close"]; d = d[d.index >= h.index.min().tz_localize(None) - pd.Timedelta(days=3)]
    rd = np.log(d).diff().dropna()
    print(tk, "hourly rows", len(h), h.index.min(), h.index.max())
    print("vol by weekday of daily stamp (bp):", (rd.groupby(rd.index.dayofweek).std()*1e4).round(0).to_dict())
    print("hourly bars per UTC hour:", h.groupby(h.index.hour).size().to_dict())
    best = []
    for hr in range(24):
        s = h[h.index.hour == hr]; s.index = s.index.tz_localize(None).normalize()
        s = s[~s.index.duplicated(keep="last")]
        rs = np.log(s).diff().dropna()
        for lag in [0, 1]:
            a = rd.reindex(rs.index + pd.Timedelta(days=lag)).values  # daily stamp D+lag vs hourly-close series stamped D
            m = ~np.isnan(a)
            c = np.corrcoef(a[m], rs.values[m])[0,1] if m.sum() > 100 else np.nan
            best.append((hr, lag, round(c,3), int(m.sum())))
    df = pd.DataFrame(best, columns=["utc_hour","stamp_lag","corr","n"]).sort_values("corr", ascending=False)
    print(df.head(8).to_string(index=False))
