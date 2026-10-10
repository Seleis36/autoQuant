"""Re-framing 1: the same signals, three months fresher.

01 decides at month-end with the vintage of the 1st of that month, so the average datum is
85 days old. Here the decision is taken at the close of the SECOND session of each month with
the vintage dated the 1st of that same month -- everything published through the 1st, one
session of safety margin, nothing later. Positions are held session-2 to session-2 and scored
on daily returns.

Re-framing 2: macro NEWS instead of macro momentum -- the month-on-month change in each
momentum z-score (what the last month of releases added), which is closer to what a market
that prices releases on the day could still be digesting.

Re-framing 3: the paper-style composite needs both legs; score growth and inflation in the
regimes where each should matter (inflation above / below 3 % year on year, point in time).

Same protocol: design 1996-06..2009-12 on syn10, test 2010..2026 on IEF / TLT, 2 bp per side.
"""
import os
import sys
import numpy as np
import pandas as pd
import mm_lib as mm

sys.path.insert(0, os.path.join(mm.ROOT, "code", "rates-bonds", "rebalance-pressure-bonds"))
from rp_lib import month_position

pd.set_option("display.width", 220)
syn = mm.cmt_returns(maturities=(10,), excess=True)[10]
etf = mm.etf_close(["IEF", "TLT"]).pct_change(fill_method=None)
dff = mm.fred("DFF")
rf = (dff / 100 / 360).reindex(syn.index.union(etf.index)).ffill()
R = pd.DataFrame({"syn10": syn, "IEF": etf["IEF"] - rf.reindex(etf.index), "TLT": etf["TLT"] - rf.reindex(etf.index)}).loc["1996":]
idx = R.index

# decision sessions: the second session of each month
s = pd.Series(np.arange(len(idx)), index=idx)
day_in_month = s - s.groupby(idx.to_period("M")).transform("min")
dec = idx[day_in_month == 1]
vint = pd.DatetimeIndex([d.replace(day=1) for d in dec])            # vintage dated the 1st of that month
sig = mm.build_signals(vint)
sig.index = dec[-len(sig):] if len(sig) != len(dec) else dec
sig = sig.loc["1996-06":]
print("decisions:", sig.index[0].date(), "->", sig.index[-1].date(), "| mean data age at decision: %.0f days" % sig["age_days"].mean())

DESIGN, TEST = ("1996-06-01", "2009-12-31"), ("2010-01-01", "2026-12-31")
SUBS = {"design": DESIGN, "test": TEST, "10-14": ("2010", "2014"), "15-19": ("2015", "2019"), "20-26": ("2020", "2026")}


def sh(r, a=None, b=None):
    r = r.loc[a:b].dropna()
    return r.mean() / r.std() * np.sqrt(252) if len(r) > 120 and r.std() > 0 else np.nan


def bt(w_dec, inst, cost=2.0):
    w = w_dec.reindex(idx).ffill()
    pos = w.shift(1)
    net = pos * R[inst] - pos.diff().abs().fillna(0.0) * cost / 1e4
    return net.where(pos.notna() & R[inst].notna())


cands = {}
for k in (3, 6, 12):
    g, f = sig[f"growth{k}"], sig[f"infl{k}"]
    cands[f"macro{k}"] = -((g + f) / 2).clip(-1, 1)
    cands[f"growth{k}"] = -g.clip(-1, 1)
    cands[f"infl{k}"] = -f.clip(-1, 1)
    cands[f"news macro{k}"] = -((g.diff() + f.diff()) / 2).clip(-1, 1)
    cands[f"news growth{k}"] = -g.diff().clip(-1, 1)
    cands[f"news infl{k}"] = -f.diff().clip(-1, 1)
gm = sig[["growth3", "growth6", "growth12"]].mean(axis=1)
fm = sig[["infl3", "infl6", "infl12"]].mean(axis=1)
cands["macro avg"] = -((gm + fm) / 2).clip(-1, 1)
cands["news macro avg"] = -((gm.diff() + fm.diff()) / 2).clip(-1, 1)

rows = []
for name, w in cands.items():
    row = {"signal": name}
    for inst in ("syn10", "IEF", "TLT"):
        net = bt(w, inst)
        for lab, (a, b) in SUBS.items():
            if inst != "syn10" and lab == "design":
                continue
            if inst == "TLT" and lab not in ("test",):
                continue
            row[f"{inst} {lab}"] = sh(net, a, b)
    rows.append(row)
out = pd.DataFrame(rows).set_index("signal")
out.to_csv("02_timely.csv")
print(out.round(2).to_string())
best = out["syn10 design"].idxmax()
print("\ndesign-best:", best, "%.2f -> test syn10 %.2f  IEF %.2f  TLT %.2f" % (out.loc[best, "syn10 design"], out.loc[best, "syn10 test"], out.loc[best, "IEF test"], out.loc[best, "TLT test"]))
print("design/test rank corr (syn10): %.2f" % out[["syn10 design", "syn10 test"]].corr(method="spearman").iloc[0, 1])
print("cells with the same sign and |Sharpe| > 0.3 in design and test (syn10):", [i for i in out.index if abs(out.loc[i, "syn10 design"]) > 0.3 and abs(out.loc[i, "syn10 test"]) > 0.3 and np.sign(out.loc[i, "syn10 design"]) == np.sign(out.loc[i, "syn10 test"])])

print("\nre-framing 3: by inflation regime (CPI year-on-year as known at the decision, above / below 3 %)")
vt = mm.Vintages()
yoy = pd.Series({d: (lambda x: float(np.log(x).diff(12).iloc[-1]) if x is not None and len(x) > 24 else np.nan)(vt.as_of("CPIAUCSL", v)) for d, v in zip(dec, vint)})
hi = (yoy > 0.03).reindex(sig.index)
print("share of months with inflation > 3%%: design %.2f  test %.2f" % (hi.loc[:DESIGN[1]].mean(), hi.loc[TEST[0]:].mean()))
for name in ("growth6", "infl6", "macro6", "news infl6"):
    for regime, m in (("high infl", hi), ("low infl", ~hi)):
        net = bt(cands[name].where(m, 0.0), "syn10")
        print("%-12s %-9s design %.2f  test %.2f" % (name, regime, sh(net, *DESIGN), sh(net, *TEST)))
