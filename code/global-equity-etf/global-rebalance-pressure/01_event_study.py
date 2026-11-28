"""Event study: slope of the return on session t+1 on the calendar-fund drift Z_t, grouped by
the position of t+1 in the month (days_left of t+1: 0 = last session; 'M+1' = first session
of the next month, 'M+2' second). Pooled 'other' = days_left >= 6 of t+1 (mid-month placebo).
ETF era: drift SPY-IEF (and SPY-TLT, GLOBAL-IEF); outcomes SPY, EFA, BASKET, GLOBAL.
Backcast 1962-98: drift S&P - syn10, outcome S&P."""
import numpy as np, pandas as pd
from grp_lib import load_etf, load_back, drift_z, days_left, month_end_flags, slope_t, SPL, BACK

def profile(z, y, periods, me):
    dl = days_left(z.index, me)
    first = me.shift(1).fillna(False).astype(bool)
    second = first.shift(1).fillna(False).astype(bool)
    lab = dl.astype(str)
    lab[first] = "M+1"; lab[second] = "M+2"
    lab[(dl >= 6) & ~first & ~second] = "other"
    df = pd.DataFrame({"z": z, "y": y.shift(-1), "lab": lab.shift(-1)}).dropna()
    out = {}
    for pn, (a, b) in periods.items():
        d = df.loc[a:b]
        for l in ["5", "4", "3", "2", "1", "0", "M+1", "M+2", "other"]:
            g = d[d.lab == l]
            out.setdefault(pn, {})[l] = "%6.1f(%5.2f)" % slope_t(g.z.values, g.y.values)
    return pd.DataFrame(out).T

C, R = load_etf()
me = month_end_flags(R.index)
pd.set_option("display.width", 220)
for dname, (e, b) in {"SPY-IEF": ("SPY", "IEF"), "SPY-TLT": ("SPY", "TLT"), "GLOBAL-IEF": ("GLOBAL", "IEF")}.items():
    z = drift_z(R[e], R[b], me)
    for on in ["SPY", "EFA", "BASKET", "GLOBAL"]:
        print(f"\n=== drift {dname} -> {on} (bp per z, t); column = days left in month of the earned day")
        print(profile(z, R[on], SPL, me).to_string())

Bk = load_back()
meb = month_end_flags(Bk.index)
zb = drift_z(Bk.EQ, Bk.BD, meb)
print("\n=== BACKCAST drift S&P-syn10 -> S&P")
print(profile(zb, Bk.EQ, {**BACK, "1999-2026": ("1999-01-01", "2026-12-31")}, meb).to_string())
