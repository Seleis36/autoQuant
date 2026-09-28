"""fomc-cycle-weeks -- do Treasury returns follow the FOMC-cycle even-week pattern?

Cieslak, Morse & Vissing-Jorgensen (JF 2019): since 1994 the US equity premium is earned in
EVEN weeks of FOMC-cycle time (weeks 0, 2, 4, 6), attributed to systematic informal Fed
communication after the bi-weekly Board meetings (mostly dovish news). If that channel is
monetary news, Treasuries should respond too -- long duration in even weeks.

FOMC-cycle time = calendar days since the most recent scheduled statement (day 0).
CMVJ weeks: week 0 = days -1..3, week 1 = 4..8, week 2 = 9..13, week 3 = 14..18,
week 4 = 19..23, week 5 = 24..28, week 6 = 29..33, beyond = 34+ (and days <= -2 before the
next meeting fall into the preceding cycle's weeks). Day -1 is assigned to week 0 of the
NEXT meeting, as in the paper.
Returns: synthetic 10y and 2y excess (1994+), IEF / TLT / SHY excess (2002+), SPY for reference.
The treasury-flow-calendar legs (last 3 days of the month, FOMC day -1 and 0) are also
shown separately, and the even-week effect is re-computed with those days removed.
Split fixed in advance: IS 1994-2009, OOS 2010-2026.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "shared"))
from rb_data import etf_close, cmt_returns, fred, ANN  # noqa: E402

pd.set_option("display.width", 220)
SNAP = os.path.join(_HERE, "..", "treasury-flow-calendar", "calendar_snapshots")


def cycle_week(idx):
    f = pd.to_datetime(pd.read_csv(os.path.join(SNAP, "fomc.csv"))["date"])
    f = f[f >= "1993-06-01"].sort_values().reset_index(drop=True)
    # statement day on a trading day
    pos = idx.searchsorted(f.values)
    f = pd.DatetimeIndex(idx[np.clip(pos, 0, len(idx) - 1)]).unique()
    wk = pd.Series(np.nan, index=idx)
    last = pd.Series(f, index=f).reindex(idx, method="ffill")
    nxt = pd.Series(f, index=f).reindex(idx, method="bfill")
    d_since = (idx - pd.DatetimeIndex(last.values)).days
    d_to = (pd.DatetimeIndex(nxt.values) - idx).days
    d = pd.Series(d_since, index=idx, dtype=float)
    d[(d_to == 1)] = -1                       # day before the next statement -> week 0
    wk = pd.cut(d, [-2, 3, 8, 13, 18, 23, 28, 33, 1e4], labels=[0, 1, 2, 3, 4, 5, 6, 7], right=True)
    return wk.astype(float), pd.Series(idx.isin(f), index=idx), pd.Series(np.asarray(d_to == 1), index=idx)


def main():
    bill = fred("DGS3MO") / 100 / ANN
    syn = cmt_returns(maturities=(2, 10), excess=True)
    px = etf_close(["IEF", "TLT", "SHY", "SPY"])
    ex = px.pct_change().sub(bill.reindex(px.index).ffill().shift(1), axis=0)
    R = pd.concat([syn.rename(columns={2: "syn2", 10: "syn10"}), ex], axis=1).loc["1994":]
    idx = R.index
    wk, is_f, is_fm1 = cycle_week(idx)
    per = idx.to_period("M")
    s = pd.Series(np.arange(len(idx)), index=idx)
    last3 = (s.groupby(per).transform("max") - s) < 3
    flowcal = last3 | is_f | is_fm1
    rows = []
    for sp, (a, b) in {"IS 94-09": ("1994", "2009"), "OOS 10-26": ("2010", "2026")}.items():
        for excl in (False, True):
            for w in range(8):
                m = (wk == w)
                if excl:
                    m &= ~flowcal
                for c in R.columns:
                    x = R[c].loc[a:b][m.loc[a:b].values].dropna()
                    rows.append(dict(split=sp, excl_flowcal=excl, week=w, inst=c, bp=x.mean() * 1e4,
                                     t=x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 5 else np.nan, n=len(x)))
            for lab, m in (("even(0,2,4,6)", wk.isin([0, 2, 4, 6])), ("odd(1,3,5)", wk.isin([1, 3, 5]))):
                if excl:
                    m = m & ~flowcal
                for c in R.columns:
                    x = R[c].loc[a:b][m.loc[a:b].values].dropna()
                    rows.append(dict(split=sp, excl_flowcal=excl, week=lab, inst=c, bp=x.mean() * 1e4,
                                     t=x.mean() / x.std() * np.sqrt(len(x)), n=len(x)))
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(_HERE, "01_event_study.csv"), index=False)
    for excl in (False, True):
        print(f"\n=== mean daily excess return, bp (t) -- flow-calendar days {'EXCLUDED' if excl else 'included'} ===")
        tt = t[t.excl_flowcal == excl]
        p = tt.pivot_table(index=["week"], columns=["split", "inst"], values="bp", aggfunc="first")
        q = tt.pivot_table(index=["week"], columns=["split", "inst"], values="t", aggfunc="first")
        cols = [(sp, c) for sp in ("IS 94-09", "OOS 10-26") for c in ("syn10", "IEF", "TLT", "syn2", "SPY")]
        out = p[cols].round(1).astype(str) + " (" + q[cols].round(1).astype(str) + ")"
        print(out.to_string())


if __name__ == "__main__":
    main()
