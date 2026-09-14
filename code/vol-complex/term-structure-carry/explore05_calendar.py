import sys, os, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsc_lib import *
pd.set_option("display.width", 220)
df = load_all(); f = features(df)
r = df.vixy.pct_change().dropna()          # return realised on day t (close t-1 -> close t)
cal = r.index
fomc = pd.DatetimeIndex(pd.to_datetime(pd.read_csv("code/rates-bonds/treasury-flow-calendar/calendar_snapshots/fomc.csv")["date"]))
fomc = fomc[(fomc >= cal[0]) & (fomc <= cal[-1])]
def third_friday(y, m):
    d = pd.Timestamp(y, m, 15); return d + pd.offsets.Week(weekday=4) if d.weekday() != 4 else d
opex = pd.DatetimeIndex([third_friday(y, m) for y in range(2011, 2027) for m in range(1, 13)])
vxexp = pd.DatetimeIndex([third_friday(y, m) - pd.Timedelta(days=30) for y in range(2011, 2027) for m in range(1, 13)])
def offsets_table(events, name, rng=range(-4, 5)):
    ev = events[(events >= cal[0]) & (events <= cal[-1])]
    pos = cal.searchsorted(ev)             # first trading day >= event
    rows = []
    for k in rng:
        idx = [p + k for p in pos if 0 <= p + k < len(cal)]
        x = r.iloc[idx]
        rows.append({"k": k, "mean_bp": x.mean() * 1e4, "t": x.mean() / x.std() * np.sqrt(len(x)), "n": len(x),
                     "IS_bp": x.loc[:IS_END].mean() * 1e4, "OOS_bp": x.loc[OOS_START:].mean() * 1e4})
    print(f"\n== VIXY return by trading-day offset from {name} (k=0 is the event day itself)")
    print(pd.DataFrame(rows).round(1).to_string(index=False))
offsets_table(fomc, "FOMC statement day")
offsets_table(opex, "monthly opex (3rd Friday)")
offsets_table(vxexp, "VIX futures expiry (Wed)")
# month-turn
s = pd.Series(cal, index=cal); from_end = s.groupby(cal.to_period("M")).cumcount(ascending=False); from_start = s.groupby(cal.to_period("M")).cumcount()
rows = []
for k in range(0, 5):
    for lab, m in [("last-%d" % k, from_end == k), ("first+%d" % k, from_start == k)]:
        x = r[m.values]
        rows.append({"day": lab, "mean_bp": x.mean() * 1e4, "t": x.mean() / x.std() * np.sqrt(len(x)), "IS_bp": x.loc[:IS_END].mean() * 1e4, "OOS_bp": x.loc[OOS_START:].mean() * 1e4})
print("\n== month turn"); print(pd.DataFrame(rows).round(1).to_string(index=False))
# weekday IS/OOS
rows = []
for d in range(5):
    x = r[r.index.dayofweek == d]
    rows.append({"dow": d, "mean_bp": x.mean() * 1e4, "t": x.mean() / x.std() * np.sqrt(len(x)), "IS_bp": x.loc[:IS_END].mean() * 1e4, "OOS_bp": x.loc[OOS_START:].mean() * 1e4,
                 "IS_t": x.loc[:IS_END].mean() / x.loc[:IS_END].std() * np.sqrt(len(x.loc[:IS_END])), "OOS_t": x.loc[OOS_START:].mean() / x.loc[OOS_START:].std() * np.sqrt(len(x.loc[OOS_START:]))})
print("\n== weekday"); print(pd.DataFrame(rows).round(1).to_string(index=False))
print("\nunconditional VIXY mean bp/day:", round(r.mean() * 1e4, 1), " t:", round(r.mean() / r.std() * np.sqrt(len(r)), 2))
