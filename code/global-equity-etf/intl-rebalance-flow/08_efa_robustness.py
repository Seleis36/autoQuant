"""Robustness of the EFA-vs-SPY last-session trade (signal = MTD SPY - EFA through L-1).
1. day profile j = -5..+3 (signal through j-1) of the EFA hedged spread, SPY, EFA
2. placebo anchors (pseudo month-end 1..15 sessions early) as books, net @2bp
3. cost ladder, sub-periods, quarter vs non-quarter, top-month concentration
4. +1 session lag (earn L+1 instead of L)"""
import sys, os
import numpy as np, pandas as pd
from lib import load, month_end_positions, run_book, stats, roll_beta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))

SPLx = {"FULL": ("2002-01-01", "2026-12-31"), "IS": ("2002-01-01", "2012-12-31"), "OOS": ("2013-01-01", "2026-12-31")}
C, R = load()
idx = C.index; pe = month_end_positions(idx)
rel = R["SPY"] - R["EFA"]
bt = roll_beta(R["EFA"], R["SPY"])                     # known at t
hed = R["EFA"] - bt.shift(1) * R["SPY"]
vol = hed.rolling(252, min_periods=126).std()          # known at t

def zs(end, a):
    return rel.iloc[a + 1:end + 1].sum() / (vol.iloc[end] * np.sqrt(end - a))

def slope(x, y):
    ok = np.isfinite(x) & np.isfinite(y); x, y = x[ok], y[ok]
    X = x - x.mean(); b = (X * y).sum() / (X ** 2).sum(); res = y - y.mean() - b * X
    return b * 1e4, b / np.sqrt((res ** 2).sum() / (len(y) - 2) / (X ** 2).sum())

print("=== 1. day profile, bp per z (t)")
for on, y in {"EFA_h": hed, "SPY": R["SPY"], "EFA": R["EFA"]}.items():
    res = {}
    for j in range(-5, 4):
        xs_, ys_, ds_ = [], [], []
        for a, b in zip(pe[:-1], pe[1:]):
            end = b + j - 1 if j <= 0 else b
            if end - a < 4 or b + j >= len(idx): continue
            xs_.append(zs(end, a)); ys_.append(y.iloc[b + j]); ds_.append(idx[b])
        xs_, ys_, ds_ = np.array(xs_), np.array(ys_), pd.DatetimeIndex(ds_)
        for pn, (a_, b_) in SPLx.items():
            m = (ds_ >= a_) & (ds_ <= b_)
            res.setdefault(pn, {})[j] = "%5.1f(%5.2f)" % slope(xs_[m], ys_[m])
    print(on); print(pd.DataFrame(res).T.to_string())

def book(anchor=0, earn=0, qmask=None, scale=2.0, cost=2.0, sizing="clip"):
    pos = pd.Series(0.0, index=idx)
    for a, b in zip(pe[:-1], pe[1:]):
        if qmask is not None and (idx[b].month in (3, 6, 9, 12)) != qmask: continue
        p = b - anchor; end = p - 1
        if end - a < 4 or not np.isfinite(vol.iloc[end]): continue
        z = zs(end, a)
        if not np.isfinite(z): continue
        x = np.clip(z, -2, 2) / 2 if sizing == "clip" else np.sign(z) * 0.5
        k = p - 1 + earn
        if k < len(idx): pos.iloc[k] = x * scale
    w = pd.DataFrame({"EFA": pos, "SPY": -pos * bt.fillna(1.0)})
    net, gross, turn, We = run_book(w, C, cost=cost)
    return net, gross, turn, We, pos

print("\n=== 2. placebo anchors (net @2bp)")
for an in range(0, 13):
    net, *_ = book(anchor=an)
    s = stats(net, SPLx)
    print(f"anchor L-{an:2d}: FULL {s.FULL:5.2f} IS {s.IS:5.2f} OOS {s.OOS:5.2f}")

print("\n=== 3. cost ladder / splits")
rows = {}
for c_ in [0.0, 1.0, 2.0, 3.0, 5.0]:
    net, gross, turn, We, _ = book(cost=c_)
    rows[f"cost {c_}bp"] = stats(net, SPLx, turn, We)
for lab, q in [("qend only", True), ("non-qend only", False)]:
    net, gross, turn, We, _ = book(qmask=q)
    rows[lab] = stats(net, SPLx, turn, We)
net, gross, turn, We, _ = book(sizing="sign"); rows["sign sizing"] = stats(net, SPLx, turn, We)
net, gross, turn, We, _ = book(earn=1); rows["+1 lag (earn L+1)"] = stats(net, SPLx, turn, We)
print(pd.DataFrame(rows).T.round(3).to_string())

net, gross, turn, We, pos = book()
for a_, b_ in [("2002", "2007"), ("2008", "2012"), ("2013", "2019"), ("2020", "2026"), ("2024", "2026")]:
    n = net.loc[a_:b_]; print(f"{a_}-{b_}: SR {n.mean() / n.std() * np.sqrt(252):5.2f}")
ev = net[pos.shift(1).fillna(0) != 0].loc["2002":]
srt = ev.sort_values(ascending=False)
print(f"events {len(ev)}, mean {ev.mean()*1e4:.1f}bp, hit {(ev > 0).mean():.2f}, top5 share of P&L {srt.iloc[:5].sum() / ev.sum():.2f}, "
      f"P&L ex top10 {srt.iloc[10:].sum() / ev.sum():.2f}")
print("worst 5:", (srt.iloc[-5:] * 1e4).round(0).to_dict())
print("best 5:", (srt.iloc[:5] * 1e4).round(0).to_dict())
