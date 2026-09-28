"""fomc-front-end-reversal -- event study.

Observation carried over from post-fomc-drift (01_screen, 210 cells): the 2y yield reverses
part of its FOMC-statement-day move over the following week, in both 1994-2009 and 2010-2026.

Questions, before any strategy is built:
  1. Profile: cumulative 2y / 5y / 10y yield change on days t+1 ... t+10 after the statement
     day t, regressed on the day-t change (slope < 0 = reversal), IS 1994-2009 / OOS 2010-2026.
  2. Is it FOMC-specific?  Same regression on
       * all non-event days (generic short-term reversal of the front end),
       * non-event days whose |dy2| is at least the median FOMC-day |dy2| (size-matched),
       * CPI release days and payroll release days (other scheduled macro news),
       * the day BEFORE the statement (placebo timing).
Yields are FRED CMT (never revised); dy in bp.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import fred  # noqa: E402

pd.set_option("display.width", 220)
SNAP = os.path.join(_HERE, "..", "treasury-flow-calendar", "calendar_snapshots")


def ev_days(name, idx, start="1994-01-01"):
    d = pd.to_datetime(pd.read_csv(os.path.join(SNAP, f"{name}.csv"))["date"])
    d = d[(d >= start)]
    pos = idx.searchsorted(d.values)
    pos = pos[pos < len(idx)]
    return pd.DatetimeIndex(sorted(set(idx[pos])))


def slope_table(dy, days, horizons=(1, 2, 3, 5, 10)):
    """For event days, regress cum. change over t+1..t+h on the day-t change."""
    idx = dy.index
    pos = idx.get_indexer(days)
    pos = pos[(pos >= 0) & (pos < len(idx) - max(horizons) - 1)]
    x = dy.values[pos]
    out = {}
    cs = np.nancumsum(np.nan_to_num(dy.values))
    for h in horizons:
        fwd = cs[pos + h] - cs[pos]
        m = ~np.isnan(x)
        b = np.polyfit(x[m], fwd[m], 1)[0]
        res = fwd[m] - np.polyval(np.polyfit(x[m], fwd[m], 1), x[m])
        se = np.sqrt(res.var(ddof=2) / ((x[m] - x[m].mean()) ** 2).sum())
        out[f"b{h}"] = b
        out[f"t{h}"] = b / se
    out["n"] = len(pos)
    out["mean|dy|"] = np.nanmean(np.abs(x))
    return out


def main():
    ys = {k: fred(f"DGS{k}").dropna() * 100 for k in (2, 5, 10)}      # bp
    idx = ys[2].index
    fomc = ev_days("fomc", idx)
    cpi = ev_days("cpi", idx)
    nfp = ev_days("payrolls", idx)
    pre = idx[np.clip(idx.get_indexer(fomc) - 1, 0, None)]
    other = idx.difference(fomc.union(cpi).union(nfp))
    rows = []
    for mat in (2, 5, 10):
        dy = ys[mat].diff().reindex(idx)
        med = dy.reindex(fomc).abs().median()
        big_other = other[dy.reindex(other).abs() >= med]
        sets = {"FOMC": fomc, "FOMC-1 (placebo)": pre, "CPI": cpi, "NFP": nfp,
                "other days": other, f"other |dy|>=FOMC median": big_other}
        for sname, days in sets.items():
            for sp, (a, b) in {"IS 94-09": ("1994", "2009"), "OOS 10-26": ("2010", "2026")}.items():
                dd = days[(days >= a) & (days <= f"{b}-12-31")]
                r = slope_table(dy, dd)
                rows.append(dict(mat=f"{mat}y", set=sname, split=sp, **r))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "01_event_study.csv"), index=False)
    cols = ["mat", "set", "split", "n", "mean|dy|", "b1", "t1", "b2", "t2", "b3", "t3", "b5", "t5", "b10", "t10"]
    print("slope of cum. yield change over t+1..t+h on the day-t change (−1 = full reversal)")
    print(t[cols].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
