"""Macro momentum as a monthly duration timer, point-in-time throughout.

Protocol (fixed before the first run)
  design sample : month-ends 1996-06 .. 2009-12, synthetic 10y excess return
  test sample   : 2010-01 .. 2026-09, IEF and TLT excess of cash (and syn10)
  signal        : macro_k = (growth_k + inflation-acceleration_k) / 2, k = 3 / 6 / 12 months
  position      : w = -clip(macro, -1, 1), set at month-end, earning the next month
  cost          : 2 bp per side on the monthly change in w
  also scored   : growth only, inflation only, their sum across k; sign versions;
                  credit premium (HYG - beta x IEF) on +growth, 2008+
Decision at month-end t sees the vintage of the 1st of that month (monthly grid).
"""
import numpy as np
import pandas as pd
import mm_lib as mm

pd.set_option("display.width", 220)
R = mm.monthly_returns()
dates = R.index[(R.index >= "1996-05-31") & (R.index <= "2026-09-30")]
sig = mm.build_signals(dates)
sig.to_csv("01_signals.csv")
print("signal months:", sig.index[0].date(), "->", sig.index[-1].date(), "| mean data age at decision: %.0f days" % sig["age_days"].mean())
print(sig[[c for c in sig if c.startswith(("growth", "infl"))]].describe().loc[["mean", "std", "min", "max"]].round(2).to_string())

DESIGN, TEST = ("1996-06-01", "2009-12-31"), ("2010-01-01", "2026-12-31")
SUBS = {"design 96-09": DESIGN, "test 10-26": TEST, "10-14": ("2010", "2014"), "15-19": ("2015", "2019"), "20-26": ("2020", "2026")}


def bt(w, r, cost=2.0):
    w = w.reindex(r.index)
    pos = w.shift(1)
    net = pos * r - pos.diff().abs().fillna(0.0) * cost / 1e4
    return net.where(pos.notna() & r.notna())


cands = {}
for k in (3, 6, 12):
    g, f = sig[f"growth{k}"], sig[f"infl{k}"]
    cands[f"macro{k}"] = -((g + f) / 2).clip(-1, 1)
    cands[f"growth{k}"] = -g.clip(-1, 1)
    cands[f"infl{k}"] = -f.clip(-1, 1)
    cands[f"macro{k} sign"] = -np.sign(g + f)
gm = sig[["growth3", "growth6", "growth12"]].mean(axis=1)
fm = sig[["infl3", "infl6", "infl12"]].mean(axis=1)
cands["macro avg(3,6,12)"] = -((gm + fm) / 2).clip(-1, 1)
cands["growth avg"] = -gm.clip(-1, 1)
cands["infl avg"] = -fm.clip(-1, 1)

rows = []
for name, w in cands.items():
    row = {"signal": name}
    for inst in ("syn10", "IEF", "TLT"):
        net = bt(w, R[inst])
        for lab, (a, b) in SUBS.items():
            if inst != "syn10" and lab == "design 96-09":
                continue
            row[f"{inst} {lab}"] = mm.sharpe_m(net, a, b)
    row["turn/yr"] = w.diff().abs().sum() / (len(w) / 12)
    rows.append(row)
out = pd.DataFrame(rows).set_index("signal")
out.to_csv("01_macro_timer.csv")
print("\nnet Sharpe of the long/short timer (monthly, 2 bp)")
print(out.round(2).to_string())
print("\nbenchmark, long-only excess return Sharpe:")
for inst in ("syn10", "IEF", "TLT"):
    print(inst, {lab: round(mm.sharpe_m(R[inst], a, b), 2) for lab, (a, b) in SUBS.items()})
best = out["syn10 design 96-09"].idxmax()
print("\ndesign-best on syn10:", best, round(out.loc[best, "syn10 design 96-09"], 2), "-> test syn10 %.2f  IEF %.2f  TLT %.2f" % (
    out.loc[best, "syn10 test 10-26"], out.loc[best, "IEF test 10-26"], out.loc[best, "TLT test 10-26"]))

print("\npredictive regressions: next-month syn10 excess return (bp) on the signal (per 1 z)")
for name in ("growth6", "infl6", "growth12", "infl12"):
    x = sig[name]
    for lab, (a, b) in (("design", DESIGN), ("test", TEST)):
        df = pd.concat([R["syn10"].shift(-1) * 1e4, x], axis=1).loc[a:b].dropna()
        beta = np.polyfit(df.iloc[:, 1], df.iloc[:, 0], 1)[0]
        res = df.iloc[:, 0] - beta * df.iloc[:, 1]
        se = res.std() / (df.iloc[:, 1].std() * np.sqrt(len(df)))
        print("%-9s %-6s slope %+7.1f bp  t %+.2f  n %d" % (name, lab, beta, beta / se, len(df)))

print("\ncredit premium (HYG - beta x IEF) on +growth, 2 bp, IS 2008-17 / OOS 2018-26")
for k in (3, 6, 12):
    net = bt(sig[f"growth{k}"].clip(-1, 1), R["credit"], cost=4.0)
    print("growth%d: %.2f / %.2f   (long-only premium: %.2f / %.2f)" % (
        k, mm.sharpe_m(net, "2008", "2017"), mm.sharpe_m(net, "2018", "2026"),
        mm.sharpe_m(R["credit"], "2008", "2017"), mm.sharpe_m(R["credit"], "2018", "2026")))
