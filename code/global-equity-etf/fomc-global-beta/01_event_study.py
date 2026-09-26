"""FOMC global premium (Brusa, Savor & Wilson 2020; Lucca & Moench 2015) on country ETFs.
Event-day returns by offset from the scheduled statement day (0), mean bp and t, IS/OOS,
for: EW country basket, SPY, EEM, and the high-minus-low beta spread (top-3 vs bottom-3 by
trailing 252d beta to SPY, known at t-1) -- the Savor-Wilson 'SML steepens on announcement days'.
Also CPI and payroll release days (8:30 ET, before the US open) for comparison."""
import sys
sys.path.insert(0, "../shared")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import data as D

UNSCHEDULED = pd.to_datetime(["1998-10-15", "2001-01-03", "2001-04-18", "2001-09-17",
                              "2008-01-22", "2008-10-08", "2020-03-03", "2020-03-15"])
fomc = pd.to_datetime(pd.read_csv("fomc_snapshot.csv")["date"]); fomc = pd.DatetimeIndex(sorted(set(fomc[~fomc.isin(UNSCHEDULED)])))
cpi = pd.DatetimeIndex(pd.to_datetime(pd.read_csv("cpi.csv").iloc[:, 0]))
nfp = pd.DatetimeIndex(pd.to_datetime(pd.read_csv("payrolls.csv").iloc[:, 0]))
NAMES = ["EWJ", "EWG", "EWU", "EWZ", "EWY", "EWA", "EWC", "FXI", "INDA"]
C = D.load_panel(NAMES + ["EEM", "EFA", "SPY"], "Close", start="2000-01-01")
R = C.pct_change()
beta = pd.DataFrame({t: R[t].rolling(252, min_periods=126).cov(R["SPY"]) / R["SPY"].rolling(252, min_periods=126).var() for t in NAMES}).shift(1)
rk = beta.rank(axis=1)
n = beta.notna().sum(axis=1)
hi = rk.gt(n - 3, axis=0); lo = rk.le(3)
HML = (R[NAMES].where(hi).mean(axis=1) - R[NAMES].where(lo).mean(axis=1))
series = {"EW9": R[NAMES].mean(axis=1), "SPY": R["SPY"], "EEM": R["EEM"], "EFA": R["EFA"], "HML_beta": HML,
          "EEM-SPY": R["EEM"] - R["SPY"]}
idx = C.index

def offsets(events):
    ev = pd.DatetimeIndex([idx[idx.searchsorted(d)] for d in events if d >= idx[0] and d <= idx[-1]])
    pos = pd.Series(np.arange(len(idx)), index=idx)
    off = pd.Series(np.nan, index=idx)
    for d in ev:
        i = pos[d]
        for k in range(-3, 4):
            if 0 <= i + k < len(idx) and (np.isnan(off.iloc[i + k]) or abs(k) < abs(off.iloc[i + k])):
                off.iloc[i + k] = k
    return off

for evname, events in [("FOMC", fomc), ("CPI", cpi), ("NFP", nfp)]:
    off = offsets(events)
    for per, (a, b) in {"IS 2001-12": ("2001", "2012"), "OOS 2013-26": ("2013", "2026")}.items():
        tab = {}
        for sname, s in series.items():
            x = s.loc[a:b]; o = off.loc[a:b]
            row = {}
            for k in [-3, -2, -1, 0, 1, 2, 3]:
                v = x[o == k].dropna()
                row[f"d{k:+d}"] = f"{v.mean()*1e4:6.1f} ({v.mean()/v.std()*np.sqrt(len(v)):4.1f})"
            v = x[o.isna()].dropna()
            row["other"] = f"{v.mean()*1e4:6.1f}"
            tab[sname] = row
        print(f"\n=== {evname} {per}: mean bp (t)")
        print(pd.DataFrame(tab).T.to_string())
