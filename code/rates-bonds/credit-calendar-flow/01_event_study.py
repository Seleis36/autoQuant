"""credit-calendar-flow -- calendar flow effects in the duration-stripped credit premium.

`treasury-flow-calendar` found robust calendar flows in DURATION (TLT month-end, FOMC,
pre-auction). This asks whether the CREDIT premium has its own calendar:
  * turn of the month: HY / IG mutual-fund and ETF inflows arrive at the start of the month
    (payroll-date contributions, coupon reinvestment -- HY coupons are paid on the 1st/15th),
    and month-end index rebalancing drops downgraded / short bonds;
  * day of week, pre-holiday, FOMC / CPI / payroll days, mid-month (15th) coupon dates.
Credit premia (hedge ratios fixed from published effective durations):
  HY = HYG - 0.47 IEF, JNK = JNK - 0.47 IEF, IG = LQD - 1.15 IEF; raw HYG / LQD shown too.
Mean daily return (bp) and t-stat by trading day relative to month end (-5 .. +5), weekday,
pre-holiday, event days. Split fixed in advance: IS 2007-04 -> 2017, OOS 2018 -> 2026.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, rl  # noqa: E402

pd.set_option("display.width", 220)
SNAP = os.path.join(_HERE, "..", "treasury-flow-calendar", "calendar_snapshots")


def premia():
    rl.load_series("JNK")
    px = etf_close(["HYG", "JNK", "LQD", "IEF", "TLT", "SPY"])
    r = px.pct_change()
    return pd.DataFrame({"HY": r.HYG - 0.47 * r.IEF, "JNK": r.JNK - 0.47 * r.IEF, "IG": r.LQD - 1.15 * r.IEF,
                         "HYG": r.HYG, "LQD": r.LQD, "TLT": r.TLT, "SPY": r.SPY}).loc["2007-04-12":]


def tdm(idx):
    """trading day relative to month end: -1 = last trading day, +1 = first of next month."""
    s = pd.Series(np.arange(len(idx)), index=idx)
    per = idx.to_period("M")
    last = s.groupby(per).transform("max")
    first = s.groupby(per).transform("min")
    fwd = s - first + 1          # 1 = first trading day of month
    bwd = s - last - 1           # -1 = last trading day
    return fwd, bwd


def ev_days(name, idx):
    d = pd.to_datetime(pd.read_csv(os.path.join(SNAP, f"{name}.csv"))["date"])
    pos = idx.searchsorted(d.values)
    return set(idx[pos[pos < len(idx)]])


def table(R, keys):
    rows = []
    for key, mask in keys.items():
        for sp, (a, b) in {"IS": ("2007-04", "2017"), "OOS": ("2018", "2026")}.items():
            m = mask.loc[a:b]
            for c in R.columns:
                x = R[c].loc[a:b][m.values].dropna()
                rows.append(dict(key=key, split=sp, inst=c, bp=x.mean() * 1e4,
                                 t=x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 5 else np.nan, n=len(x)))
    return pd.DataFrame(rows)


def main():
    R = premia().dropna(subset=["HY", "IG"])
    idx = R.index
    fwd, bwd = tdm(idx)
    keys = {}
    for k in (-5, -4, -3, -2, -1):
        keys[f"ME{k}"] = (bwd == k)
    for k in (1, 2, 3, 4, 5):
        keys[f"MS+{k}"] = (fwd == k)
    keys["mid_rest"] = (fwd > 5) & (bwd < -5)
    for i, dn in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        keys[dn] = pd.Series(idx.dayofweek == i, index=idx)
    gaps = pd.Series(idx[1:] - idx[:-1], index=idx[:-1]).reindex(idx)
    keys["pre_holiday"] = (gaps > pd.Timedelta(days=1)) & (idx.dayofweek != 4)
    keys["post_holiday"] = pd.Series(pd.Series(idx, index=idx).diff() > pd.Timedelta(days=1), index=idx) & (idx.dayofweek != 0)
    for name in ("fomc", "cpi", "payrolls"):
        e = ev_days(name, idx)
        keys[name] = pd.Series(idx.isin(list(e)), index=idx)
    day = pd.Series(idx.day, index=idx)
    keys["around_15th(14-16)"] = day.between(14, 16) & (fwd > 5) & (bwd < -5)
    t = table(R, {k: pd.Series(v, index=idx) if not isinstance(v, pd.Series) else v for k, v in keys.items()})
    t.to_csv(os.path.join(_HERE, "01_event_study.csv"), index=False)
    print("mean daily return, bp (t-stat)")
    for inst in ("HY", "JNK", "IG", "HYG", "LQD", "TLT"):
        p = t[t.inst == inst].pivot_table(index="key", columns="split", values=["bp", "t"])
        p = p.reindex(list(keys))
        print(f"\n=== {inst} ===")
        print(p.round(2).to_string())


if __name__ == "__main__":
    main()
