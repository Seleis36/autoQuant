"""Does the rebalancing signal at close t predict the next session's return of
(a) stocks minus bonds (the paper's left-hand side), (b) the bond leg alone, (c) stocks alone?

Slope is in bp of next-day return per 1 percentage point of equity overweight.
Paper's claim: (a) negative, i.e. bonds up / stocks down after stocks became overweight.
"""
import numpy as np
import pandas as pd
import rp_lib as rp

pd.set_option("display.width", 220)
d = rp.load()
eq, bd, etf = d["eq"], d["bd"], d["etf"]
thr = rp.threshold_signal(eq, bd)
cal, left = rp.calendar_signal(eq, bd)
print("signal sd (pct pts): threshold %.2f  calendar %.2f ; corr %.2f" % (thr.std() * 100, cal.std() * 100, thr.corr(cal)))

nxt = lambda s: s.shift(-1)
targets = {"stocks-bonds (index, syn10)": nxt(eq - bd), "bond syn10": nxt(bd), "stocks S&P": nxt(eq),
           "bond IEF": nxt(etf["IEF"]), "bond TLT": nxt(etf["TLT"]), "SPY-IEF": nxt(etf["SPY"] - etf["IEF"])}
periods = {"IS 1990-2009": rp.IS, "OOS 2010-2026": rp.OOS, "paper 1997-2023": rp.PAPER, "post 2024-26": rp.POST,
           "1982-1996": ("1982-01-01", "1996-12-31")}
rows = []
for sname, sig, window in (("threshold", thr, None), ("calendar all days", cal, None),
                           ("calendar, next day in last 5", cal, (1, 5)), ("calendar, next day in last 3", cal, (1, 3)),
                           ("calendar, next day is last", cal, (1, 1)), ("calendar, next day = first of month", cal.shift(1), "first")):
    for tname, y in targets.items():
        for pname, (a, b) in periods.items():
            x = sig * 100
            if window == "first":
                # session t+1 is the first of a month: use the month-end deviation that was just traded
                m = left.shift(1) == 0          # t is the first session of the month
                x = (sig * 100).where(left == 0)  # signal: deviation at the month-end close itself
                yy = y.where(left == 0)
            elif window is not None:
                m = (left >= window[0]) & (left <= window[1])
                x, yy = x.where(m), y.where(m)
            else:
                yy = y
            slope, t, n = rp.nw_t(yy.loc[a:b] * 1e4, x.loc[a:b])
            rows.append(dict(signal=sname, target=tname, period=pname, slope_bp=slope, t=t, n=n))
out = pd.DataFrame(rows)
out.to_csv("01_event_study.csv", index=False)
for tname in targets:
    sub = out[out.target == tname]
    p = sub.pivot(index="signal", columns="period", values="slope_bp").round(2)
    t = sub.pivot(index="signal", columns="period", values="t").round(1)
    print("\n=== next-day", tname, "(slope bp per 1pt overweight | t)")
    print((p.astype(str) + " | " + t.astype(str))[list(periods)].to_string())
