"""Quarterly-rebalance additions: S&P announces them after the close on the FIRST Friday of
Mar/Jun/Sep/Dec, effective before the open on the Monday after the THIRD Friday. Those dates
are known in advance, so the post-announcement drift is tradeable without an announcement
feed: enter at the close of the first session after the first Friday (after the announcement
jump), exit at the close of the third Friday (bar -1, when index funds buy).

Checks the assumed schedule (the reaction on the Monday after the first Friday should spike) and
measures the tradeable drift; ad-hoc (non-quarterly) additions are reported separately."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import runpy
g = runpy.run_path(os.path.join(HERE, "event_study.py"), run_name="es")
E, C, dates = g["E"], g["C"], g["dates"]


def nth_friday(y, m, n):
    d = pd.Timestamp(year=y, month=m, day=1)
    d += pd.Timedelta(days=(4 - d.weekday()) % 7)
    return d + pd.Timedelta(weeks=n - 1)


A = E[E.side == "add"].copy()
q = []
for _, e in A.iterrows():
    y, m = e.eff.year, e.eff.month
    if m not in (3, 6, 9, 12):
        q.append(False); continue
    f3 = nth_friday(y, m, 3)
    q.append(pd.Timestamp(f3) < e.eff <= pd.Timestamp(f3) + pd.Timedelta(days=4))
A["quarterly"] = q
print(A.quarterly.value_counts())
rows = []
for _, e in A[A.quarterly].iterrows():
    f1 = nth_friday(e.eff.year, e.eff.month, 1)
    i_ann = dates.searchsorted(f1, side="right")      # first session after the announcement
    i_m1 = e.ri - 1                                    # third Friday close (bar -1)
    c = e.ci
    if i_ann >= i_m1:
        continue
    rows.append({"ticker": e.ticker, "eff": e.eff,
                 "pre_ann_5": (C[i_ann - 1, c] - C[i_ann - 6, c]) * 1e4,
                 "ann_reaction": (C[i_ann, c] - C[i_ann - 1, c]) * 1e4,
                 "drift_to_m1": (C[i_m1, c] - C[i_ann, c]) * 1e4,
                 "day0": (C[e.ri, c] - C[i_m1, c]) * 1e4,
                 "post_1_5": (C[min(e.ri + 5, len(dates) - 1), c] - C[e.ri, c]) * 1e4,
                 "n_bars": i_m1 - i_ann})
Q = pd.DataFrame(rows)
f = lambda x: pd.Series({"mean": x.mean(), "t": x.mean() / x.std() * np.sqrt(len(x)), "median": x.median()})
print("quarterly additions N", len(Q), " avg bars in drift window", Q.n_bars.mean().round(1))
print(Q[["pre_ann_5", "ann_reaction", "drift_to_m1", "day0", "post_1_5"]].apply(f).round(1).to_string())
print("drift IS / OOS:", Q[Q.eff < "2018"].drift_to_m1.mean().round(1), Q[Q.eff >= "2018"].drift_to_m1.mean().round(1),
      " N", (Q.eff < "2018").sum(), (Q.eff >= "2018").sum())
Q.round(2).to_csv(os.path.join(HERE, "screen2_quarterly_events.csv"), index=False)
