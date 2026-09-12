"""exp03 -- hourly Coinbase premium: does the signal have intraday structure?

Hourly bars indexed by OPEN time. Signal at bar T uses bars <= T (known at T+1h = close of bar T).
Target = Binance return over the NEXT k bars (T+1 .. T+k).  Decision hour = hour of T+1 (when we act).
IS <= 2022-12-31, OOS >= 2023-01-01 (same split as daily).
"""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "shared"))
from research_lib import DATA_DIR, newey_west_t
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)

def naive(df):
    return (df.tz_convert("UTC").tz_localize(None) if df.index.tz is not None else df).sort_index()
b = naive(pd.read_parquet(os.path.join(DATA_DIR, "BTCUSDT_1h_flow.parquet")))
c = naive(pd.read_parquet(os.path.join(DATA_DIR, "COINBASE_BTCUSD_1h.parquet")))
idx = b.index.intersection(c.index)
b, c = b.loc[idx], c.loc[idx]
px = b["Close"]
prem = c["Close"] / px - 1
r1 = px.pct_change().shift(-1)                       # return of bar T+1
def fwd(k): return px.shift(-k) / px - 1              # return over bars T+1..T+k
sig = {
    "p1": prem,
    "p4": prem.rolling(4).mean(),
    "p24": prem.rolling(24).mean(),
    "z1_30d": (prem - prem.rolling(720).mean()) / prem.rolling(720).std(),
    "z4_30d": (prem.rolling(4).mean() - prem.rolling(720).mean()) / prem.rolling(720).std(),
    "z24_30d": (prem.rolling(24).mean() - prem.rolling(720).mean()) / prem.rolling(24).std().rolling(720).mean(),
    "dp4": prem.rolling(4).mean() - prem.rolling(24).mean(),   # premium momentum
}
IS_END, OOS_START = "2022-12-31", "2023-01-01"
HOURS = (idx + pd.Timedelta(hours=1)).hour   # hour at which we act
dec_hour = pd.Series(HOURS, index=idx)

def tercile_spread(x, y):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 100: return np.nan, np.nan
    q = pd.qcut(df["x"].rank(method="first"), 3, labels=False)
    s = pd.Series(0.0, index=df.index); s[q == 2] = df["y"][q == 2]; s[q == 0] = -df["y"][q == 0]
    return (df["y"][q == 2].mean() - df["y"][q == 0].mean()) * 1e4, newey_west_t(s.values, 6)

print("=== unconditional (all hours): tercile spread bp (NW t) of next-k-bar return | IS / OOS")
for k in (1, 4, 8, 24):
    y = fwd(k)
    line = f"k={k:2d} "
    for nm, x in sig.items():
        a = tercile_spread(x.loc[:IS_END], y.loc[:IS_END]); o = tercile_spread(x.loc[OOS_START:], y.loc[OOS_START:])
        line += f"| {nm}: {a[0]:6.1f}({a[1]:4.1f}) / {o[0]:6.1f}({o[1]:4.1f}) "
    print(line)

print("\n=== by decision hour (UTC), signal z4_30d, next-4h return: spread bp (t)  IS | OOS ; also top-tercile mean bp IS|OOS")
x = sig["z4_30d"]; y = fwd(4)
rows = []
for H in range(24):
    m = dec_hour == H
    a = tercile_spread(x[m].loc[:IS_END], y[m].loc[:IS_END]); o = tercile_spread(x[m].loc[OOS_START:], y[m].loc[OOS_START:])
    # top tercile mean
    def top(seg_x, seg_y):
        df = pd.DataFrame({"x": seg_x, "y": seg_y}).dropna()
        q = pd.qcut(df["x"].rank(method="first"), 3, labels=False)
        t = df["y"][q == 2]
        return t.mean() * 1e4, t.mean() / t.std() * np.sqrt(365 * 6)
    ta = top(x[m].loc[:IS_END], y[m].loc[:IS_END]); to = top(x[m].loc[OOS_START:], y[m].loc[OOS_START:])
    rows.append(dict(H=H, sp_is=a[0], t_is=a[1], sp_os=o[0], t_os=o[1], top_is=ta[0], topSh_is=ta[1], top_os=to[0], topSh_os=to[1]))
print(pd.DataFrame(rows).set_index("H").round(2).to_string())

print("\n=== by decision hour, signal p24 (raw 24h mean premium), next-24h return: spread bp (t) IS | OOS")
x = sig["p24"]; y = fwd(24)
rows = []
for H in range(24):
    m = dec_hour == H
    a = tercile_spread(x[m].loc[:IS_END], y[m].loc[:IS_END]); o = tercile_spread(x[m].loc[OOS_START:], y[m].loc[OOS_START:])
    rows.append(dict(H=H, sp_is=a[0], t_is=a[1], sp_os=o[0], t_os=o[1]))
print(pd.DataFrame(rows).set_index("H").round(2).T.to_string())
