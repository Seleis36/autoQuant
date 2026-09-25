"""session-momentum 01: map ETH intraday / weekly seasonality and session cross-predictability.

Hourly bars (UTC, left-labelled). IS <= 2023, OOS >= 2024.
(a) mean 1h log-return by UTC hour, t-stat, IS/OOS
(b) mean daily (00-24 UTC) return by weekday, IS/OOS
(c) session returns: S1 00-08 (Asia), S2 08-13 (Europe), S3 13-21 (US), S4 21-24 (US close).
    Correlation of each session with the preceding ones (same day, and previous day's sessions),
    plus 'first k hours of day -> rest of day' (Gao et al. intraday momentum).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
import numpy as np
import pandas as pd
from ethdata import bars, IS_END, OOS_START

h = bars("ETHUSDT", "1h"); c = h["Close"]
lr = np.log(c).diff().dropna()
P = {"IS": (None, IS_END), "OOS": (OOS_START, None)}
pd.set_option("display.width", 220, "display.max_rows", 200)

print("(a) hour of day, bp per hour")
rows = []
for hr in range(24):
    x = lr[lr.index.hour == hr]
    r = dict(hour=hr)
    for p, (a, b) in P.items():
        xs = x.loc[a:b]; r[f"bp_{p}"] = xs.mean() * 1e4; r[f"t_{p}"] = xs.mean() / xs.std() * np.sqrt(len(xs))
    rows.append(r)
print(pd.DataFrame(rows).round(2).to_string(index=False))

print("\n(b) weekday of the 00-24 UTC day, bp per day")
d = lr.groupby(lr.index.floor("D")).sum()
rows = []
for wd in range(7):
    x = d[d.index.dayofweek == wd]
    r = dict(wd=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][wd])
    for p, (a, b) in P.items():
        xs = x.loc[a:b]; r[f"bp_{p}"] = xs.mean() * 1e4; r[f"t_{p}"] = xs.mean() / xs.std() * np.sqrt(len(xs))
    rows.append(r)
print(pd.DataFrame(rows).round(2).to_string(index=False))

print("\n(c) session cross-predictability (Pearson corr of session log-returns)")
day = lr.index.floor("D"); hr = lr.index.hour
S = pd.DataFrame({
    "S1_00_08": lr[(hr < 8)].groupby(day[hr < 8]).sum(),
    "S2_08_13": lr[(hr >= 8) & (hr < 13)].groupby(day[(hr >= 8) & (hr < 13)]).sum(),
    "S3_13_21": lr[(hr >= 13) & (hr < 21)].groupby(day[(hr >= 13) & (hr < 21)]).sum(),
    "S4_21_24": lr[(hr >= 21)].groupby(day[hr >= 21]).sum(),
})
S["prevday"] = S.sum(axis=1).shift(1)
S["prevS4"] = S["S4_21_24"].shift(1)
S["S1S2"] = S["S1_00_08"] + S["S2_08_13"]
S["S1S2S3"] = S["S1S2"] + S["S3_13_21"]
pairs = [("prevday", "S1_00_08"), ("prevS4", "S1_00_08"), ("S1_00_08", "S2_08_13"), ("S1_00_08", "S3_13_21"),
         ("S1S2", "S3_13_21"), ("S2_08_13", "S3_13_21"), ("S3_13_21", "S4_21_24"), ("S1S2S3", "S4_21_24"),
         ("prevday", "S3_13_21")]
rows = []
for x, y in pairs:
    r = dict(pred=x, target=y)
    for p, (a, b) in P.items():
        z = S[[x, y]].loc[a:b].dropna()
        r[f"corr_{p}"] = z[x].corr(z[y]); r[f"t_{p}"] = r[f"corr_{p}"] * np.sqrt(len(z))
    rows.append(r)
print(pd.DataFrame(rows).round(3).to_string(index=False))

print("\n(d) first k hours of the UTC day -> remaining hours (corr), and last-hour-of-day target")
rows = []
for k in [1, 2, 4, 6, 8, 12, 16, 20]:
    first = lr[hr < k].groupby(day[hr < k]).sum()
    rest = lr[hr >= k].groupby(day[hr >= k]).sum()
    last = lr[hr == 23].groupby(day[hr == 23]).sum()
    mid = lr[(hr >= 1) & (hr < 23)].groupby(day[(hr >= 1) & (hr < 23)]).sum()
    r = dict(k=k)
    for p, (a, b) in P.items():
        z = pd.concat([first, rest], axis=1).loc[a:b].dropna()
        r[f"corr_{p}"] = z.iloc[:, 0].corr(z.iloc[:, 1]); r[f"t_{p}"] = r[f"corr_{p}"] * np.sqrt(len(z))
    rows.append(r)
print(pd.DataFrame(rows).round(3).to_string(index=False))
S.to_csv("/tmp/eth_sessions.csv")  # regenerable intermediate, kept out of the repo
