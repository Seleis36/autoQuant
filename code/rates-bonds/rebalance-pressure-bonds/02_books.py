"""Bond-leg books on the rebalancing signals. Design sample: synthetic 10y 1990-2009.
Test sample: IEF and TLT 2010-2026. 2 bp per side. Gross printed next to net.

A  threshold, every day      : pos = clip(signal / trailing sd, -1, 1)           (long bonds when stocks overweight)
B  calendar, into month-end  : same sign, held only when the NEXT session is one of the last N of the month
C  month-start reversal      : pos = -clip(month-end deviation / sd, -1, 1), held for the first k sessions
                               of the new month (the month-end bond buying is given back)
   'sign' versions use +-1 instead of the scaled deviation.
"""
import itertools
import numpy as np
import pandas as pd
import rp_lib as rp

pd.set_option("display.width", 220)
d = rp.load()
eq, bd, etf = d["eq"], d["bd"], d["etf"]
thr = rp.threshold_signal(eq, bd)
cal, left = rp.calendar_signal(eq, bd)
COST = 2.0


def scaled(sig, how):
    if how == "sign":
        return np.sign(sig)
    sd = sig.expanding(500).std().shift(1)
    return (sig / sd).clip(-1, 1)


def bt(pos, r, cost=COST):
    w = pos.shift(1).fillna(0.0)
    gross = w * r
    net = gross - w.diff().abs().fillna(0.0) * cost / 1e4
    return net.where(r.notna()), gross.where(r.notna()), w.diff().abs().sum() / (len(w) / 252.0), (w != 0).mean()


def month_start_pos(k, how):
    """Deviation at the month-end close, reversed, carried over the first k sessions."""
    me = cal.where(left == 0)
    base = -scaled(me.dropna(), how).reindex(cal.index)
    pos = base.ffill(limit=k - 1) if k > 1 else base
    return pos.fillna(0.0)


books = {}
for how in ("scaled", "sign"):
    books[f"A threshold {how}"] = scaled(thr, how).fillna(0.0)
    for n in (5, 3, 1):
        m = (left >= 1) & (left <= n)
        books[f"B calendar last{n} {how}"] = scaled(cal, how).where(m, 0.0).fillna(0.0)
    for k in (1, 2, 3, 5):
        books[f"C month-start k{k} {how}"] = month_start_pos(k, how)

inst = {"syn10": bd, "IEF": etf["IEF"], "TLT": etf["TLT"]}
rows = []
nets = {}
for name, pos in books.items():
    r = {}
    for iname, ret in inst.items():
        net, gross, turn, expo = bt(pos, ret)
        nets[(name, iname)] = net
        for lab, (a, b) in (("IS 1990-09", rp.IS), ("OOS 2010-26", rp.OOS), ("2022-26", ("2022-01-01", "2026-12-31"))):
            r[f"{iname} {lab} net"] = rp.sharpe(net, a, b)
            r[f"{iname} {lab} gross"] = rp.sharpe(gross, a, b)
    rows.append(dict(book=name, turn=turn, expo=expo, **r))
out = pd.DataFrame(rows).set_index("book")
out.to_csv("02_books.csv")
show = ["syn10 IS 1990-09 gross", "syn10 IS 1990-09 net", "syn10 OOS 2010-26 net", "IEF OOS 2010-26 gross", "IEF OOS 2010-26 net",
        "TLT OOS 2010-26 gross", "TLT OOS 2010-26 net", "IEF 2022-26 net", "TLT 2022-26 net", "turn", "expo"]
print(out[show].round(2).to_string())

print("\nIS-best on syn10 net:", out["syn10 IS 1990-09 net"].idxmax(), round(out["syn10 IS 1990-09 net"].max(), 2))

# month-start reversal, detail: mean return of the first session by the sign of the month-end deviation
print("\nfirst session of the month, bond return (bp) by sign of the month-end deviation")
me_dev = cal.where(left == 0)
for iname, ret in inst.items():
    nxt = ret.shift(-1)
    for lab, (a, b) in (("1982-89", ("1982", "1989")), ("1990-2009", rp.IS), ("2010-2026", rp.OOS), ("2010-17", ("2010", "2017")), ("2018-26", ("2018", "2026"))):
        x = pd.concat([me_dev, nxt], axis=1).loc[a:b].dropna()
        if len(x) < 20:
            continue
        up, dn = x[x.iloc[:, 0] > 0].iloc[:, 1] * 1e4, x[x.iloc[:, 0] < 0].iloc[:, 1] * 1e4
        t = (up.mean() - dn.mean()) / np.sqrt(up.var() / len(up) + dn.var() / len(dn))
        print("%-6s %-10s stocks-overweight months: %+6.1f (n %3d)   bonds-overweight: %+6.1f (n %3d)   diff t %.1f" % (
            iname, lab, up.mean(), len(up), dn.mean(), len(dn), t))
