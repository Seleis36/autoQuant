"""equity-credit-lead-lag -- do equity moves lead credit-ETF returns at daily frequency?

Traded objects (duration-stripped credit premia, hedge ratios fixed from published
effective durations, not fitted):
  HY  = HYG - 0.47 IEF      (HYG ~3.4y / IEF ~7.3y; credit-spread-trend convention)
  JNK = JNK - 0.47 IEF
  IG  = LQD - 1.15 IEF      (LQD ~8.4y)
  EM  = EMB - 1.0 IEF       (EMB ~7.3y)
Predictors, all known at the close of day t:
  spy_k   = SPY return over the last k days (k = 1, 2, 5)
  resid_k = the credit premium's own k-day return minus beta * SPY k-day return, beta from a
            trailing 252-day regression (the part of equity news the credit ETF has NOT absorbed,
            with the sign flipped: negative residual = credit lagging).
Targets: forward 1-, 2-, 5-day excess return of the credit premium starting at t+1.
Split fixed in advance: IS 2007-04 -> 2017-12, OOS 2018 -> 2026 (2010-2017 shown separately
so the GFC does not carry the IS number).
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, rl  # noqa: E402

pd.set_option("display.width", 220)
HEDGE = {"HY": ("HYG", 0.47), "JNK": ("JNK", 0.47), "IG": ("LQD", 1.15), "EM": ("EMB", 1.0)}


def load():
    for t in ("JNK",):
        rl.load_series(t)
    px = etf_close(["SPY", "IEF", "HYG", "JNK", "LQD", "EMB"])
    r = px.pct_change()
    cr = pd.DataFrame({k: r[t] - h * r["IEF"] for k, (t, h) in HEDGE.items()})
    return r, cr


def main():
    r, cr = load()
    spy = r["SPY"]
    rows = []
    splits = {"IS07-17": ("2007-04", "2017"), "IS10-17": ("2010", "2017"), "OOS18-26": ("2018", "2026")}
    for k in cr.columns:
        y = cr[k]
        for kk in (1, 2, 5):
            spy_k = spy.rolling(kk).sum()
            y_k = y.rolling(kk).sum()
            beta = y.rolling(252, min_periods=126).cov(spy) / spy.rolling(252, min_periods=126).var()
            resid_k = -(y_k - beta * spy_k)              # positive = credit has lagged equities up
            for h in (1, 2, 5):
                fwd = y[::-1].rolling(h).sum()[::-1].shift(-1)
                for pname, p in (("spy", spy_k), ("resid", resid_k), ("own", y_k)):
                    df = pd.concat([p, fwd], axis=1).dropna()
                    for sp, (a, b) in splits.items():
                        d = df.loc[a:b]
                        if len(d) < 200:
                            continue
                        # non-overlapping sample for t-stat: every h-th day
                        dn = d.iloc[::max(h, kk)]
                        c = dn.iloc[:, 0].corr(dn.iloc[:, 1])
                        rows.append(dict(credit=k, pred=pname, k=kk, h=h, split=sp, corr=c,
                                         t=c * np.sqrt(len(dn)), n=len(dn)))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "01_screen.csv"), index=False)
    for pname in ("spy", "resid", "own"):
        print(f"\n=== predictor {pname}: corr(pred_k, fwd h-day credit excess), non-overlapping ===")
        print(t[t.pred == pname].pivot_table(index=["credit", "k", "h"], columns="split", values="corr").round(3).to_string())


if __name__ == "__main__":
    main()
