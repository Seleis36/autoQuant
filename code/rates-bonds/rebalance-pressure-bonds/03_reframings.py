"""Re-framings of the two parts that showed the right sign in both halves.

1. Month-start reversal: magnitude-scaled, extremes only, quarter-ends, different exits.
2. Calendar signal into month-end as a conditioner of the DEPLOYED unconditional month-end
   long (treasury-flow-calendar): does knowing who is overweight improve that leg?
3. Does the month-start leg add to the deployed sleeve?
4. Reference only (cross-asset, not a rates-bonds book): the paper's stocks-minus-bonds trade.
5. The bond leg by stock-bond correlation regime (why the threshold signal is not a bond signal).
"""
import os
import sys
import numpy as np
import pandas as pd
import rp_lib as rp

sys.path.insert(0, os.path.join(rp.ROOT, "code", "rates-bonds", "shared"))
from deployed_sleeves import load_strategy

pd.set_option("display.width", 220)
d = rp.load()
eq, bd, etf = d["eq"], d["bd"], d["etf"]
thr = rp.threshold_signal(eq, bd)
cal, left = rp.calendar_signal(eq, bd)
inst = {"syn10": bd, "IEF": etf["IEF"], "TLT": etf["TLT"]}
SPL = {"IS 1990-09": rp.IS, "OOS 2010-26": rp.OOS, "2010-17": ("2010", "2017"), "2018-26": ("2018", "2026")}


def bt(pos, r, cost=2.0):
    w = pos.shift(1).fillna(0.0)
    gross = w * r
    return (gross - w.diff().abs().fillna(0.0) * cost / 1e4).where(r.notna()), gross.where(r.notna())


def line(tag, pos, cost=2.0):
    out = [tag.ljust(44)]
    for iname, r in inst.items():
        net, gross = bt(pos, r, cost)
        out.append(iname + " " + " ".join("%5.2f/%5.2f" % (rp.sharpe(gross, a, b), rp.sharpe(net, a, b)) for a, b in SPL.values()))
    print(" | ".join(out))


print("gross/net Sharpe at 2 bp for:", list(SPL))
me = cal.where(left == 0).dropna()
sd = me.expanding(36).std().shift(1)
z = (me / sd)
print("\n1. month-start reversal variants (held over the first session unless stated)")
variants = {
    "sign": -np.sign(me),
    "scaled clip(z,-1,1)": -z.clip(-1, 1),
    "scaled clip(z,-2,2)/2": -z.clip(-2, 2) / 2,
    "extremes |z|>0.5": -np.sign(me).where(z.abs() > 0.5, 0.0),
    "extremes |z|>1": -np.sign(me).where(z.abs() > 1.0, 0.0),
    "quarter-ends only": -np.sign(me).where(me.index.month.isin([3, 6, 9, 12]), 0.0),
    "non-quarter month-ends": -np.sign(me).where(~me.index.month.isin([3, 6, 9, 12]), 0.0),
    "short side only (stocks overweight)": -np.sign(me).clip(upper=0),
    "long side only (bonds overweight)": -np.sign(me).clip(lower=0),
}
for name, p in variants.items():
    line(name, p.reindex(cal.index).fillna(0.0))
line("sign, held 2 sessions", (-np.sign(me)).reindex(cal.index).ffill(limit=1).fillna(0.0))
# prior-month relative return instead of the drift weight (same thing, simpler definition)
rel = (np.log1p(eq) - np.log1p(bd)).groupby(eq.index.to_period("M")).cumsum()
line("sign of MTD stock-minus-bond return", (-np.sign(rel.where(left == 0))).fillna(0.0))
# placebo: the same position one session later / on the second session only
line("PLACEBO second session only", (-np.sign(me)).reindex(cal.index).shift(1).fillna(0.0))
line("PLACEBO mid-month (session 10)", (-np.sign(me)).reindex(cal.index).shift(9).fillna(0.0))

print("\n2. conditioning the deployed month-end long (last 3 sessions) on who is overweight")
m3 = ((left >= 1) & (left <= 3)) | False
uncond = pd.Series(np.where((left.shift(-1) <= 2) & (left >= 1) | ((left <= 3) & (left >= 1)), 1.0, 0.0), index=cal.index)
uncond = ((left >= 1) & (left <= 3)).astype(float)          # next session is one of the last 3
line("unconditional long last 3", uncond)
line("long only if stocks overweight", uncond.where(cal > 0, 0.0))
line("long only if bonds overweight", uncond.where(cal <= 0, 0.0))
line("long 1.5x / 0.5x by sign", uncond * np.where(cal > 0, 1.5, 0.5))

print("\n3. deployed treasury-flow-calendar on TLT, with and without the month-start leg (2 bp)")
tfc = load_strategy("treasury-flow-calendar")
tlt = etf["TLT"].dropna()
w_dep = tfc.target_weight(pd.Series(1.0, index=tlt.index))
leg = (-np.sign(me)).reindex(cal.index).fillna(0.0).reindex(tlt.index).fillna(0.0)
for name, w in (("deployed", w_dep), ("deployed + month-start leg", (w_dep + leg).clip(-1, 1)),
                ("deployed + 0.5 x leg", (w_dep + 0.5 * leg).clip(-1, 1)), ("month-start leg alone", leg)):
    net, gross = bt(w, tlt)
    print("%-28s IS(2002-09) %.2f  OOS 2010-26 %.2f  2010-17 %.2f  2018-26 %.2f  full %.2f  ann %.2f%%" % (
        name, rp.sharpe(net, "2002", "2009"), rp.sharpe(net, *rp.OOS), rp.sharpe(net, "2010", "2017"),
        rp.sharpe(net, "2018", "2026"), rp.sharpe(net), net.mean() * 252 * 100))

print("\n4. reference, cross-asset: SPY minus IEF on the paper's signals (2 bp per leg)")
spread = etf["SPY"] - etf["IEF"]
pos_thr = -np.sign(thr)
pos_cal = (-np.sign(cal)).where((left >= 1) & (left <= 5), 0.0)
for name, pos in (("threshold", pos_thr), ("calendar last 5", pos_cal), ("both, averaged", (pos_thr + pos_cal) / 2)):
    w = pos.shift(1).fillna(0)
    gross = (w * spread)
    net = gross - w.diff().abs().fillna(0) * 2 * 2 / 1e4
    print("%-18s gross/net  2002-09 %.2f/%.2f   2010-26 %.2f/%.2f   2024-26 %.2f/%.2f" % (
        name, rp.sharpe(gross, "2002", "2009"), rp.sharpe(net, "2002", "2009"), rp.sharpe(gross, *rp.OOS), rp.sharpe(net, *rp.OOS),
        rp.sharpe(gross, *rp.POST), rp.sharpe(net, *rp.POST)))

print("\n5. threshold signal -> next-day bond return, by trailing 250d stock-bond correlation")
corr = eq.rolling(250).corr(bd)
for lab, m in (("corr < -0.2", corr < -0.2), ("-0.2..0.2", (corr >= -0.2) & (corr <= 0.2)), ("corr > 0.2", corr > 0.2)):
    s, t, n = rp.nw_t(bd.shift(-1).where(m) * 1e4, (thr * 100).where(m))
    s2, t2, _ = rp.nw_t(eq.shift(-1).where(m) * 1e4, (thr * 100).where(m))
    print("%-12s n %5d  bond slope %+6.2f (t %+.1f)   stock slope %+6.2f (t %+.1f)" % (lab, n, s, t, s2, t2))
